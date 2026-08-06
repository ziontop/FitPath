# Apple Health Integration — Architecture & Security Design

**Status:** Accepted (implementation-ready). Supersedes the earlier *Proposed* research draft.
**Last updated:** 2026-07-14
**Owner:** FitPath integrations
**Scope:** How FitPath (React/Vite PWA + FastAPI backend) ingests Apple Health data under 2026 platform
constraints, using two user-driven, web-compatible paths. This document is the source of truth for the
`apple-health-backend`, `apple-health-ui`, and `apple-health-qa` tasks. **No production code is changed by
this document** — all schema/endpoint/algorithm text below is the design contract to build against.

> **TL;DR** — A browser/PWA **cannot** read HealthKit directly. FitPath ships **(A) manual Apple Health
> export import** (`export.zip`/`export.xml`) with a *preview → select types → import* flow, and **(B) a
> user-configured iOS Shortcut** that pushes **daily aggregates** over a bearer-authenticated HTTPS POST.
> Provenance is tracked with **three generic tables** (`ApiSyncToken`, `HealthImportBatch`,
> `ImportedHealthRecord`) — **not** Apple-specific columns bolted onto each log table. v1 imports
> **steps, body mass, sleep, water, and workouts → `ActivityLog`**; it does **not** import dietary
> energy/macros. Everything is idempotent, re-runnable, and safely deletable without clobbering manual edits.

---

## 0. Decision log (what is locked, and why)

| # | Decision | Rationale |
|---|---|---|
| D1 | **No raw export retention between preview and import.** `POST …/preview` streams, parses, returns metadata, then discards the upload. The **browser keeps the `File`** and re-uploads it to `POST …/import`. **No server-side preview registry / temp-file handoff.** | Health data is "especially sensitive" (App Store §5.1.3). Keeping a parsed blob or the raw zip on the server between two requests creates a PHI-at-rest liability and a GC/cleanup problem. Re-uploading the same `File` object is cheap for the browser and keeps the server stateless between preview and commit. |
| D2 | **Generic provenance model, not per-log Apple columns.** Add `ApiSyncToken`, `HealthImportBatch`, `ImportedHealthRecord`. Do **not** add `apple_health_uid`/`source` columns to `step_log`/`weight_log`/etc. | Adding nullable Apple columns to five log tables is five migrations of dead weight for non-Apple rows, couples the log schema to one provider, and still can't express "which import wrote this / is it still unmodified / can I safely delete it." A side provenance table gives idempotency, update detection, safe deletion, multi-provider reuse, and a clean audit trail with **zero** changes to existing log tables. See §7 for the full resolution vs. the research draft's `HealthImportKey`. |
| D3 | **Everything under `/api/integrations/apple-health/*`.** | One cohesive surface (`preview`, `import`, `imports`, `data`, `tokens`, `shortcut`) that the SPA fallback never shadows (`app/main.py:118-123`). Replaces the research draft's split `/api/imports/*` + `/api/sync/*`. |
| D4 | **Shortcut ingest is bearer-only and explicitly CSRF-exempt.** The route derives the user **only** from the `Authorization: Bearer` header and ignores cookies entirely. | Keeps the ingest surface outside the cookie/CSRF trust boundary so a logged-in browser can never be CSRF-tricked into pushing health data (§6.3). |
| D5 | **v1 imports steps, body mass, sleep, water, workouts→`ActivityLog`. No dietary energy/macros.** | Apple exports nutrient *samples* with no meal name/category; synthesizing `MealLog` rows would poison the (name, category)-keyed adaptive engine and double-count manual meals (§5.3). |
| D6 | **On re-import, manual edits are preserved.** Insert / update / skip / **conflict(skip)** / invalid state machine, keyed by provenance (§6.4). | Improves on the research draft's "last-writer-wins" note now that provenance lets us *detect* a manual edit. Consistent with the safe-delete rule (D7). |
| D7 | **Imported-data deletion only removes rows FitPath itself imported and still owns.** Delete a local row **only if its current values still equal the recorded `imported_payload`**; a manually modified row is preserved and only its provenance link is dropped. | Users must be able to remove imported health data (privacy) without losing edits they made afterward. |
| D8 | **No account-deletion endpoint** is added. | Explicitly out of scope to avoid scope creep; the research draft's GDPR account-delete suggestion is deferred. Imported-data deletion (D7) is the required privacy control. The existing per-user logs **reset** (`app/routes/admin.py:163-169`) is extended to also clear the three new tables (§8.3). |

---

## 1. Platform constraints (authoritative)

### 1.1 A web app / PWA cannot access HealthKit directly
- HealthKit is a **native-only** framework (Swift/Obj-C). There is **no Web API** exposing it to Safari,
  Chrome, or an installed PWA; WebKit sandboxing plus health-data sensitivity means browser JavaScript
  cannot read or write Health data.
- Direct access requires a **native iOS/watchOS app** that declares the **HealthKit entitlement**, ships
  `Info.plist` usage strings (`NSHealthShareUsageDescription` for read, `NSHealthUpdateUsageDescription`
  for write), requests **per-type user authorization** at runtime, and passes App Store review.
- HealthKit **read authorization is deliberately opaque**: an app cannot distinguish "user denied read"
  from "no data exists," so any consumer must design for **data-may-be-absent**.
- **Implication:** Any true HealthKit access requires a native companion app (large cost, ongoing review) —
  **out of scope for v1**. The two options in §5 never touch HealthKit APIs; they consume data the **user
  themselves** exports or pushes.

Sources: Apple HealthKit documentation — <https://developer.apple.com/documentation/healthkit>;
App Store Review Guidelines §5.1.3 — <https://developer.apple.com/app-store/review/guidelines/>.

### 1.2 Store/policy constraints that still bind us
Even as a web app, these Apple rules bind any future native companion **and** are good-practice guardrails
for handling exported/pushed health data (fetched verbatim 2026-07-14):
- **§5.1.2(vi):** HealthKit data "may not be used for marketing, advertising or use-based data mining,
  including by third parties."
- **§5.1.3(i):** Do not use/disclose health/fitness/medical data for advertising, marketing, or use-based
  data mining; you may use it to provide a direct benefit to that user; **"You must disclose the specific
  health data that you are collecting."**
- **§5.1.3(ii):** Must not write false/inaccurate data into HealthKit; **may not store personal health
  information in iCloud.**

---

## 2. Apple Health export workflow & file structure

### 2.1 How a user exports
1. Open **Health** → tap the **profile picture** (top-right).
2. Scroll to **Export All Health Data**.
3. Confirm; the phone builds an archive (minutes for multi-year histories).
4. Share/save the resulting **`export.zip`** (AirDrop, Files, email, …).

Reference: Apple Support — "Share your data in Health on iPhone"
<https://support.apple.com/guide/iphone/share-your-health-data-iph5ede58c3d/ios>.

### 2.2 Archive layout
```
export.zip
└── apple_health_export/
    ├── export.xml            # main data (can be 100s of MB – GB)
    ├── export_cda.xml        # Clinical Document Architecture (ignored)
    ├── workout-routes/       # GPX per workout (ignored)
    └── electrocardiograms/   # ECG CSV/PDF (ignored)
```
> The parser locates the member whose name **ends exactly** with `apple_health_export/export.xml` and must
> **never** trust arbitrary member paths (Threat Model §9).

### 2.3 `<Record>` shape (quantity & category samples)
```xml
<Record type="HKQuantityTypeIdentifierStepCount"
        sourceName="iPhone" sourceVersion="18.5" unit="count"
        creationDate="2026-07-14 13:02:45 -0700"
        startDate="2026-07-14 12:30:00 -0700"
        endDate="2026-07-14 12:30:00 -0700" value="10"/>
```
Attributes we consume: `type`, `unit`, `value`, `startDate`, `endDate`, `sourceName` (`creationDate`,
`sourceVersion` informational). Category samples (e.g. sleep) put the state in `value`
(e.g. `HKCategoryValueSleepAnalysisAsleepCore`).

### 2.4 `<Workout>` shape
```xml
<Workout workoutActivityType="HKWorkoutActivityTypeRunning"
         duration="32.5" durationUnit="min"
         totalDistance="5.1" totalDistanceUnit="km"
         totalEnergyBurned="320" totalEnergyBurnedUnit="kcal"
         sourceName="Apple Watch"
         startDate="2026-07-14 06:30:00 -0700"
         endDate="2026-07-14 07:02:30 -0700">
   <MetadataEntry key="HKWeatherTemperature" value="19 degF"/>
</Workout>
```
> `durationUnit`/`totalDistanceUnit`/`totalEnergyBurnedUnit` vary (`s`/`min`, `km`/`mi`, `kcal`). Always
> read the unit attribute; never assume.

### 2.5 Date format
`YYYY-MM-DD HH:MM:SS ±ZZZZ` (space-separated, explicit UTC offset). Parse the offset, convert to the
sample's local wall-clock, then store **naive local** to match FitPath's existing convention
(`datetime.now()` / date columns — `app/routes/logs.py:109,250,316,416,458`).

### 2.6 Identifiers & units relevant to v1
| Apple identifier | Typical unit(s) | Kind | v1 |
|---|---|---|---|
| `HKQuantityTypeIdentifierStepCount` | `count` | quantity (cumulative) | ✅ steps |
| `HKQuantityTypeIdentifierBodyMass` | `kg`, `lb` | quantity (discrete) | ✅ weight |
| `HKQuantityTypeIdentifierDietaryWater` | `mL`, `fl_oz_us` | quantity (cumulative) | ✅ water |
| `HKCategoryTypeIdentifierSleepAnalysis` | value enum (below) | category (interval) | ✅ sleep |
| `HKWorkoutActivityType*` (in `<Workout>`) | duration/energy/distance | workout | ✅ activity |
| `HKQuantityTypeIdentifierDietaryEnergyConsumed` | `kcal` | quantity | ❌ (§5.3) |
| `HKQuantityTypeIdentifierDietaryProtein/Carbohydrates/FatTotal` | `g` | quantity | ❌ (§5.3) |

**Sleep analysis values** (iOS 16+ staged; older exports differ):
- Newer: `…InBed`, `…AsleepCore`, `…AsleepDeep`, `…AsleepREM`, `…AsleepUnspecified`, `…Awake`.
- Legacy (pre-iOS 16): `…InBed`, `…Asleep`.
- **Asleep total** = union of `AsleepCore + AsleepDeep + AsleepREM + AsleepUnspecified` (or legacy `Asleep`).
  **Exclude `InBed` and `Awake`** from asleep totals — `InBed` overlaps staged intervals, so summing both
  double-counts.

---

## 3. iOS Shortcuts capabilities & limits

- **Read Health:** the *Find Health Samples* action returns samples with permission and can filter by
  type/date and compute aggregates (today's step sum, last night's asleep hours). Aggregating **inside the
  Shortcut** means FitPath receives one clean number per metric per day and side-steps raw-export
  de-duplication (§9).
- **HTTP POST:** *Get Contents of URL* supports `POST`, a JSON body, and **custom headers**
  (`Authorization: Bearer …`) — this is how the Shortcut authenticates.
- **Automation/background limits:** Health-reading actions generally still require a **user tap**, even in a
  "Time of Day" automation set to "Run Immediately." **Treat the Shortcut as user-initiated "tap-to-sync,"
  not silent background sync.** Continuous background delivery needs a native HealthKit app
  (`enableBackgroundDelivery`) — out of scope.
- **Token storage:** Shortcuts iCloud-sync and can be shared; the bearer token pasted in is only as private
  as the Shortcut. Instruct users **not to share** it, and provide rotate/revoke (§6.5).

Sources: Apple Shortcuts User Guide — <https://support.apple.com/guide/shortcuts/>. *Uncertainty:* exact
prompt behavior varies by iOS version; **this design does not depend on unattended execution.**

---

## 4. Deployment requirement — HTTPS

The Shortcut carries a bearer secret in a request header. **The ingest endpoint MUST be served over HTTPS in
any real deployment** (set `FITPATH_COOKIE_SECURE=true` for the cookie flags too — `app/deps.py:30-37`).
HTTP-only is acceptable *only* for `localhost` dev. Document this in the Settings UI next to the token.

---

## 5. v1 supported types, mappings & units

Targets are the existing log models (`app/models.py`) with validation bounds from `app/schemas.py`. The
importer writes these models **directly** (it does not call the `/api/logs/*` HTTP endpoints) so it can
attach provenance atomically and apply the preserve-manual-edits policy (§6.4).

| Apple source | → FitPath model | Aggregation | Unit handling | Bounds (`schemas.py`) |
|---|---|---|---|---|
| `StepCount` records | `StepLog` (unique `user_id,logged_for` — `models.py:184-186`) | **Sum per local day**, one dominant source (§7.5.a) | `count` → int | `steps` 0–200000 (`schemas.py:92-94`) |
| `BodyMass` records | `WeightLog` (unique `user_id,logged_for` — `models.py:212-214`) | **Latest sample per day** (max `endDate`) | `kg` kept; `lb`→kg (`×0.45359237`), 1 dp | `weight_kg` >20 & <400 (`schemas.py:102-104`) |
| `SleepAnalysis` intervals | `SleepLog` (`models.py:160-171`) | Group by **wake date**; `hours` = Σ merged asleep-stage durations; `wake_time` = local `HH:MM` of last asleep `endDate` | value enum → hours; cap ≤24 | `hours` 0–24, `wake_time` `HH:MM` (`schemas.py:86-89`) |
| `DietaryWater` records | `WaterLog` (`models.py:189-199`) | **Sum per day → one row/day** | `mL` kept; `fl_oz_us`→mL (`×29.5735`), int | per-row `ml` 1–5000 (`schemas.py:97-99`); daily total split into ≤5000 chunks if needed (§5.4) |
| `<Workout>` records | `ActivityLog` (`models.py:143-157`) | **One `ActivityLog` per workout** | `duration`→minutes per `durationUnit`; `done_at` = `startDate` local | `minutes` >0 & ≤1440; `intensity∈{light,moderate,vigorous}` (`schemas.py:79-83,25`) |

### 5.1 Workout activity + intensity mapping
Apple `<Workout>` ≠ FitPath strength `WorkoutSession`/`SetLog` (the export has **no** sets×reps×RPE).
Map every Apple workout to **`ActivityLog`** (session minutes), never to `WorkoutSession`.
- **activity name:** strip the `HKWorkoutActivityType` prefix and map through a small table, humanized
  fallback otherwise:

  | Apple activity type | `ActivityLog.activity` |
  |---|---|
  | `Running`, `TrackAndField` | `Running` |
  | `Walking`, `Hiking` | `Walking` |
  | `Cycling` | `Cycling` |
  | `Swimming` | `Swimming` |
  | `TraditionalStrengthTraining`, `FunctionalStrengthTraining` | `Strength` |
  | `HighIntensityIntervalTraining` | `HIIT` |
  | `Yoga`, `Pilates`, `FlexibilityTraining`, `Cooldown`, `MindAndBody` | `Yoga` |
  | `Elliptical`, `Rowing`, `StairClimbing` | *humanized label* |
  | *(anything else)* | *humanized label of the raw type* |

- **minutes:** `duration` converted by `durationUnit` (`s`→/60, `min`→as-is), rounded; clamp to `(0,1440]`.
- **intensity (deterministic):** default by activity, with an optional energy-rate override:
  - default: Yoga/Walking/Flexibility/Cooldown → `light`;
    Cycling/Elliptical/Rowing/Swimming/Strength/Functional → `moderate`;
    Running/HIIT/StairClimbing → `vigorous`.
  - override when `totalEnergyBurned` present: `kcal/min < 5` → `light`, `5–10` → `moderate`,
    `> 10` → `vigorous`. Deterministic; documented; no heart-rate dependency.
- **done_at:** workout `startDate` (local, naive).

### 5.2 Sleep normalization
- Parse all `SleepAnalysis` intervals; keep only asleep stages (exclude `InBed`, `Awake`).
- Assign each interval to a **wake date** = local calendar date of its `endDate`.
- Within a wake date, **merge overlapping asleep intervals across sources** (union of intervals; do not
  simply add durations, which would double-count Watch+phone overlap). If multiple sources disagree, prefer
  the source contributing the **longest merged asleep span** (the "dominant source"); record the choice as a
  warning in the preview.
- `hours` = total merged asleep minutes / 60, capped ≤24. `wake_time` = `HH:MM` of the latest asleep
  `endDate`. If only `InBed` exists (no asleep stages), fall back to InBed duration but flag it as
  **time-in-bed, not asleep** in warnings.

### 5.3 Decision — dietary energy/macros NOT imported (v1)
Apple provides `DietaryEnergyConsumed`/`DietaryProtein`/`DietaryCarbohydrates`/`DietaryFatTotal` as
**per-nutrient time-series samples** with **no meal name or category**. FitPath's `MealLog` requires
`name`+`category`+`eaten_at`, and the adaptive engine mines meals keyed on **(name, category)**
(`app/routes/logs.py:149-153`). Importing nutrient samples would force fabricated "Imported meal" rows that
(a) pollute recent/favorite/frequent pickers and adaptive suggestions, (b) risk double-counting vs.
manually logged meals, and (c) usually don't exist unless the user runs a 3rd-party logger writing to
Health. **v1 skips them.** *Future option (out of scope):* a read-only `DailyNutritionSummary` table
(kcal/protein/carbs/fat per day, source-tagged) surfaced as a trend — **never** synthesized into `MealLog`.

### 5.4 Unit & value normalization rules
- Whitelist units per type; convert explicitly; **reject unknown units** (count `invalid`, never guess).
- Round steps/water/ml to int; weight to 1 dp.
- Clamp to schema bounds; values outside sane ranges → `invalid` (skip that record; never abort the import).
- Reject dates in the future beyond a small clock-skew allowance (e.g. +1 day) → `invalid`.
- **Water daily total > 5000 mL:** the per-row `WaterLog.ml` bound is 1–5000 (`schemas.py:98`). Store the
  aggregated day as a **single** `WaterLog` clamped to 5000 and warn, OR (preferred) store one row capped at
  5000; do **not** create hundreds of sip rows. The provenance `external_key` remains the date so the day
  stays idempotent regardless.

---

## 6. API design — everything under `/api/integrations/apple-health`

All request/response bodies are JSON except the two multipart uploads. Timestamps ISO-8601; dates
`YYYY-MM-DD`. New routes live under `/api/*` and are never shadowed by the SPA fallback
(`app/main.py:118-123`).

### 6.1 Manual export import (cookie + CSRF)

#### `POST /api/integrations/apple-health/preview` — multipart, **no writes**
- Auth: `current_user` (`app/deps.py:57`) + CSRF (browser sends `X-CSRF-Token`, `client.ts:92-96`).
- Body: `multipart/form-data` with field **`file`** = `export.zip` or `export.xml`.
- Behavior: stream → safe-parse (§7) → return metadata → **discard upload** (D1). Writes nothing.

```jsonc
// 200
{
  "filename": "export.zip",
  "date_range": { "start": "2019-03-01", "end": "2026-07-14" },
  "counts_by_type": { "steps": 2557, "weight": 431, "sleep": 1103, "water": 6820, "workouts": 512 },
  "units_detected": { "weight": ["kg"], "water": ["mL", "fl_oz_us"] },
  "samples": {                       // a few humanized rows per type; NEVER the raw file
    "steps":   [{ "date": "2026-07-14", "value": 8432, "sources": ["iPhone", "Apple Watch"] }],
    "weight":  [{ "date": "2026-07-14", "kg": 80.1 }],
    "sleep":   [{ "wake_date": "2026-07-14", "hours": 7.25, "wake_time": "06:45" }],
    "water":   [{ "date": "2026-07-14", "ml": 2100 }],
    "workouts":[{ "activity": "Running", "date": "2026-07-14", "minutes": 32, "intensity": "vigorous" }]
  },
  "warnings": [
    "Steps: multiple sources per day; totals use the dominant source and may differ slightly from the Health app.",
    "3 records had unknown units and will be skipped on import."
  ]
}
```
- Errors: `413` upload too large (§7.2 caps); `422` not a recognized Apple export / no `export.xml` member;
  `400` malformed/again-unsafe archive (zip bomb / entity attack). Error `detail` is generic — **never**
  echoes file contents.

#### `POST /api/integrations/apple-health/import` — multipart, **commits**
- Auth: same as preview.
- Body: `multipart/form-data`, field **`file`** (the same `File` the browser retained, re-uploaded — D1) +
  field **`types`** = JSON array or repeated form field of the selected types
  (subset of `["steps","weight","sleep","water","workouts"]`).
- Behavior: re-parse → run the import algorithm (§6.4) inside **one `HealthImportBatch`** → return per-type
  counts. Discards the upload afterward.

```jsonc
// 200
{
  "batch_id": 42,
  "source": "export",
  "status": "completed",                     // completed | partial | failed
  "date_range": { "start": "2019-03-01", "end": "2026-07-14" },
  "results": {
    "steps":    { "inserted": 2100, "updated": 12, "skipped": 445, "invalid": 0, "conflict": 3 },
    "weight":   { "inserted": 420,  "updated": 0,  "skipped": 11,  "invalid": 0, "conflict": 0 },
    "sleep":    { "inserted": 1100, "updated": 0,  "skipped": 3,   "invalid": 0, "conflict": 0 },
    "water":    { "inserted": 500,  "updated": 0,  "skipped": 0,   "invalid": 0, "conflict": 0 },
    "workouts": { "inserted": 510,  "updated": 0,  "skipped": 2,   "invalid": 0, "conflict": 0 }
  },
  "totals": { "inserted": 4630, "updated": 12, "skipped": 461, "invalid": 0, "conflict": 3 }
}
```
- `conflict` = incoming Apple value differs from what FitPath imported earlier, but the local row was
  manually edited since, so FitPath **preserved the edit** and skipped the overwrite (§6.4).

#### `GET /api/integrations/apple-health/imports` — history
```jsonc
// 200
{ "items": [
  { "id": 42, "source": "export", "status": "completed",
    "date_range": { "start": "2019-03-01", "end": "2026-07-14" },
    "records_inserted": 4630, "records_updated": 12, "records_skipped": 461, "records_invalid": 0,
    "created_at": "2026-07-14T21:03:11", "completed_at": "2026-07-14T21:03:49", "error": null }
] }
```

#### `DELETE /api/integrations/apple-health/data` — safe imported-data removal
- Body (all optional): `{ "types": ["steps",…], "from": "2026-01-01", "to": "2026-07-14" }`.
  Omitting all → all imported Apple data for the user.
- Behavior: the safe-delete algorithm (§8.2). Returns a report.
```jsonc
// 200
{ "deleted": { "steps": 2100, "weight": 420, "sleep": 1100, "water": 500, "workouts": 508 },
  "preserved_modified": { "weight": 2, "workouts": 2 },   // local rows kept because user edited them
  "provenance_removed": 4630 }
```

### 6.2 Multipart on the frontend (handoff note)
The existing `request()` helper **always** sets `Content-Type: application/json` and `JSON.stringify`s the
body (`frontend/src/api/client.ts:92-116`), which is wrong for file upload. The UI track must add an
**upload helper** that:
- sends a `FormData` body, **omits** the `Content-Type` header (the browser sets `multipart/form-data` with
  the boundary),
- keeps `credentials: 'include'` and echoes `X-CSRF-Token` from the `fitpath_csrf` cookie (`getCookie`),
- reuses `ApiError`/`extractDetail`/401 handling.

### 6.3 Shortcut ingest (bearer only) — `POST /api/integrations/apple-health/shortcut`
- **Auth boundary:** a new `bearer_token_user` dependency (`app/deps.py`) that reads **only**
  `Authorization: Bearer <token>` and **ignores cookies**. It never falls back to `current_user`.
- **Explicit CSRF exemption (D4):** add `/api/integrations/apple-health/shortcut` to
  `security._EXEMPT_PATHS` (`app/security.py:23`). The current middleware only enforces CSRF when a valid
  session cookie is present (`app/security.py:31-43`), so a cookieless Shortcut request already passes — but
  the explicit exemption is **defense-in-depth** for the case where a browser session cookie is somehow
  attached; combined with the cookie-ignoring dependency, the endpoint is fully decoupled from the
  cookie/CSRF trust boundary.
- **Payload:** daily aggregates already computed by the Shortcut (never raw samples):
```jsonc
// POST body
{
  "steps":    [{ "date": "2026-07-14", "count": 8432 }],
  "weight":   [{ "date": "2026-07-14", "kg": 80.1 }],
  "sleep":    [{ "date": "2026-07-14", "hours": 7.5, "wake_time": "06:45" }],  // date = wake date
  "water":    [{ "date": "2026-07-14", "ml": 2100 }],
  "workouts": [{ "activity": "Running", "start": "2026-07-14T06:30:00-07:00",
                 "end": "2026-07-14T07:02:00-07:00", "source": "Apple Watch",
                 "minutes": 32, "intensity": "vigorous", "kcal": 320 }]
}
```
```jsonc
// 200 — same idempotent state machine as file import, run in a "shortcut" batch
{ "batch_id": 87, "applied": { "steps": 1, "weight": 1, "sleep": 1, "water": 1, "workouts": 1 },
  "skipped":  { "steps": 0, "weight": 0, "sleep": 0, "water": 0, "workouts": 0 } }
```
- Errors: `401` missing/invalid/revoked/expired token; `422` malformed payload; `400` values out of range
  (per-field, not whole-request). The response **never** reflects stored health values back.

### 6.4 Token management (cookie + CSRF)
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/integrations/apple-health/tokens` | `{ "name": "iPhone 16", "expires_in_days": 365? }` | `201 { id, name, prefix, token, created_at, expires_at }` — **`token` shown once** |
| GET | `/api/integrations/apple-health/tokens` | — | `200 { items: [{ id, name, prefix, created_at, last_used_at, expires_at, revoked_at }] }` — **never the secret** |
| POST | `/api/integrations/apple-health/tokens/{id}/rotate` | — | `200 { id, name, prefix, token, … }` — new secret shown once; old hash replaced |
| DELETE | `/api/integrations/apple-health/tokens/{id}` | — | `204` — sets `revoked_at` |

**Token format & verification:**
- Full token = `fpk_<10-char base62 prefix>_<43-char urlsafe secret>` (secret ≥ 256 bits from
  `secrets.token_urlsafe(32)`).
- Store: `prefix = "fpk_<10-char>"` (non-secret, **indexed** lookup key), `token_hash = sha256(full_token)`
  hex. High-entropy secret ⇒ SHA-256 + constant-time compare is sufficient (GitHub-PAT style); `pwdlib`
  argon2 (already a dependency) is acceptable but unnecessary.
- Verify: parse `prefix` → single-row DB lookup → `secrets.compare_digest(sha256(presented), stored_hash)`
  → reject if `revoked_at` set or `expires_at` passed → update `last_used_at`.
- **Never log the full token or the hash.** The secret is returned exactly once at create/rotate.

---

## 7. Data model — generic provenance (three new tables)

SQLAlchemy 2.0 typed declarative, matching `app/models.py` conventions (typed `Mapped[...]`,
`ForeignKey(..., ondelete="CASCADE")`, `func.now()` server defaults, `__table_args__` indexes).

```python
# app/models.py (additions)

class ApiSyncToken(Base):
    """Personal bearer token for provider push (Option B). Provider-agnostic."""
    __tablename__ = "api_sync_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)          # user label
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)  # non-secret lookup
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)   # sha256(full token) hex
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (Index("ix_api_sync_token_user", "user_id"),)


class HealthImportBatch(Base):
    """One import run (file export or shortcut push). Audit + status."""
    __tablename__ = "health_import_batch"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="apple_health")
    source: Mapped[str] = mapped_column(String(16), nullable=False)         # export | shortcut
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")  # running|completed|partial|failed
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    date_start: Mapped[Optional[date]] = mapped_column(Date)
    date_end: Mapped[Optional[date]] = mapped_column(Date)
    error: Mapped[Optional[str]] = mapped_column(Text)                      # generic message, no PHI
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (Index("ix_health_import_batch_user", "user_id", "created_at"),)


class ImportedHealthRecord(Base):
    """Idempotency + update-detection + safe-delete link between an external sample and a local row."""
    __tablename__ = "imported_health_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="apple_health")
    resource_type: Mapped[str] = mapped_column(String(24), nullable=False)   # steps|weight|sleep|water|workout
    external_key: Mapped[str] = mapped_column(String(128), nullable=False)   # stable key (§7.5)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)    # sha256 of imported_payload
    imported_payload: Mapped[str] = mapped_column(Text, nullable=False)      # canonical JSON we wrote
    local_resource_type: Mapped[str] = mapped_column(String(24), nullable=False)  # step_log|weight_log|…
    local_resource_id: Mapped[int] = mapped_column(Integer, nullable=False)  # PK of the local row
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("health_import_batch.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "resource_type", "external_key",
                         name="uq_imported_health_record"),
        Index("ix_imported_health_record_user_type", "user_id", "provider", "resource_type"),
    )
```
Add all three to `models.py.__all__`. **No changes to `step_log`/`weight_log`/`sleep_log`/`water_log`/
`activity_log`.**

### 7.5 Stable external keys & payload hash
`external_key` is stable across re-exports/re-pushes so the same underlying datum always resolves to the
same provenance row. `resource_type` already namespaces it, so the key is compact:

| resource_type | external_key | Notes |
|---|---|---|
| `steps` | `"<local date>"` (`2026-07-14`) | per local calendar day |
| `weight` | `"<local date>"` | per local calendar day (latest sample) |
| `water` | `"<local date>"` | per local calendar day (summed) |
| `sleep` | `"<wake date>"` | per wake date; merged asleep intervals, dominant source |
| `workout` | `"<activity>|<source>|<startISO>|<endISO>"` | e.g. `Running|Apple Watch|2026-07-14T06:30:00|2026-07-14T07:02:00` |

`imported_payload` = canonical JSON of exactly the normalized values FitPath wrote (e.g.
`{"steps":8432}`, `{"kg":80.1}`, `{"hours":7.25,"wake_time":"06:45"}`, `{"ml":2100}`,
`{"activity":"Running","minutes":32,"intensity":"vigorous","done_at":"2026-07-14T06:30:00"}`).
`payload_hash` = `sha256` of that canonical JSON. A changed hash ⇒ Apple corrected the value ⇒ candidate
for **update**.

### 7.6 Import algorithm (per candidate record)
Runs inside one batch, for both file import and shortcut push:

```
key   = external_key(record)
inc   = normalized_payload(record)          # or 'invalid' → count invalid, continue
prov  = SELECT ImportedHealthRecord WHERE (user, provider, resource_type, key)

if prov is None:
    local = existing manual local row for this key?          # only possible for day-keyed steps/weight
    if local exists (manual, no provenance):
        count CONFLICT (preserve manual entry; do not overwrite); continue
    local = INSERT local row from inc
    INSERT prov(local_resource_*, imported_payload=inc, payload_hash=H(inc), batch)
    count INSERTED
else:
    if H(inc) == prov.payload_hash:
        count SKIPPED                                        # unchanged, idempotent no-op
    else:
        local = GET local row by prov.local_resource_id
        if local is None:                                    # row deleted out-of-band
            re-INSERT local; refresh prov; count INSERTED
        elif current_local_values == prov.imported_payload:  # untouched since our last import
            UPDATE local to inc; prov.imported_payload=inc; prov.payload_hash=H(inc); prov.batch=batch
            count UPDATED
        else:                                                # user edited since import
            count CONFLICT (preserve manual edit; leave prov as-is); continue
```
- **Append types (sleep/water/workout)** have no DB unique constraint; the provenance unique constraint is
  the *only* idempotency guard, so re-import never duplicates them. Manually created append rows (no
  provenance) are left untouched and coexist with imported rows (we do not attempt to dedupe imported vs.
  manual append rows in v1).
- **Day-keyed types (steps/weight)** are guarded by *both* the DB unique constraint
  (`uq_step_log_user_day`, `uq_weight_log_user_day`) and provenance. A pre-existing manual day row is a
  `conflict` (preserved), not overwritten — matching D6/D7.

### 7.7 Transaction & failure semantics (works with current `get_db()`)
`get_db()` yields one `Session`, **commits on success, rolls back on exception, closes in `finally`**
(`app/db.py:86-96`); routes normally only `db.flush()`.

- **Preview:** parse only; **no `add`/`flush`** ⇒ the terminal commit is a no-op. Guaranteed read-only.
- **Import (one batch, atomic):**
  1. `INSERT HealthImportBatch(status="running")`, `flush()`.
  2. Stream records; process in **chunks of ~1000** with a `db.flush()` + `expunge_all()` between chunks to
     bound memory on multi-year files (objects go to the DB inside the still-open transaction; nothing is
     visible to other connections yet).
  3. Set batch `status`, counts, `date_start/end`, `completed_at`.
  4. Return the response; **`get_db()`'s terminal `commit()` makes the whole import atomic** — all log rows,
     all provenance rows, and the batch status land together, or none do.
  - **Chunk-safe** here means *retry-safe via idempotency* (the provenance unique key makes a re-run resolve
    to insert/update/skip deterministically), **not** partial commits. A crash mid-import rolls everything
    back; the user simply re-imports the same file with no duplicates.
- **Durable failure record:** because the terminal rollback would also erase the `running` batch row, on an
  unexpected error the route opens a **separate short-lived `SessionLocal()`**, writes a
  `HealthImportBatch(status="failed", error=<generic message>)` (no health values), commits, closes, then
  raises `HTTPException(400/500)`. That separate transaction survives `get_db()`'s rollback because it is an
  independent connection (NullPool + WAL — `app/db.py:47-75`). The user sees the failed batch in history.
- **Shortcut push:** identical algorithm in a `source="shortcut"` batch; per-field validation errors are
  counted/`skipped` rather than aborting, so one bad metric never rejects the whole day.

---

## 8. Deletion, reset & retention

### 8.1 Raw upload retention — none
The uploaded `export.zip`/`export.xml` is streamed through `tempfile.SpooledTemporaryFile` (FastAPI
`UploadFile`) and **closed/deleted immediately** after parsing, in both preview and import. Nothing is
written under `/tmp` by hand, no parsed blob is cached between requests (D1), and **no health value or token
is ever written to application logs**.

### 8.2 `DELETE …/data` — safe imported-data removal (D7)
For each `ImportedHealthRecord` in scope (optional `types` + `from`/`to` date filter applied via the log
row's date):
1. Load the local row (`local_resource_type` + `local_resource_id`).
2. If the local row is **missing** → just drop the provenance row.
3. If the local row's **current values equal `imported_payload`** (unmodified) → **delete the local row**
   and the provenance row; count `deleted`.
4. If the local row was **modified** since import (values ≠ `imported_payload`) → **keep the local row**,
   drop only the provenance link; count `preserved_modified`.

Return the report shape in §6.1. This never destroys data the user edited or created themselves.

### 8.3 Reset behavior
`POST /api/admin/reset` currently clears the six log tables + workout sessions per user
(`app/routes/admin.py:32-36,163-169`). The implementation task must extend `_clear_user_logs` (or the reset
route) to also `DELETE` the user's `ImportedHealthRecord` and `HealthImportBatch` rows, so provenance never
dangles after a reset. `ApiSyncToken` rows are **not** cleared by reset (tokens are configuration, not log
data); they cascade only on account/user deletion.

### 8.4 Cascade on user deletion
All three tables carry `user_id ForeignKey(ondelete="CASCADE")`, so if a user row is ever deleted every
token, batch, and provenance row is removed by the DB (FKs enforced via `PRAGMA foreign_keys=ON` —
`app/db.py:72`). No account-deletion **endpoint** is added (D8).

---

## 9. Threat model

| Threat | Vector | Mitigation |
|---|---|---|
| **Zip bomb** | Tiny zip inflating to GBs | Enforce caps **before** reading: reject upload > **500 MB compressed**; reject the target member if `ZipInfo.file_size` > **3 GB** or `file_size / compress_size` > **200:1**; stream the single known member under a hard **byte budget** independent of the header. |
| **Path traversal / Zip-Slip** | Malicious member names (`../`, absolute) | Read **only** the member whose name ends with `apple_health_export/export.xml`; **never extract** arbitrary members; never write member contents to disk by their embedded names. |
| **XXE / billion laughs / quadratic blowup** | DTDs, external/nested entities | Parse with **`defusedxml`** `iterparse` (DTD/entity resolution + external fetch disabled). **Never** use bare stdlib `xml.etree` on the upload. |
| **Huge exports (GB)** | Memory/CPU exhaustion | Streaming `iterparse` + `elem.clear()` per record; caps on **max records (~5,000,000)** and **wall-clock (~120 s)**; chunked flush+expunge (§7.7); never build a DOM. Exceeding a cap → `partial` with a warning, or `413`/`422`. |
| **Duplicate / overlapping data** | Re-import, iPhone+Watch double count | Provenance unique key = idempotent upsert for every type (§7.6); day-keyed steps/weight also DB-unique; steps pick a **dominant source per day**; sleep merges intervals; prefer Shortcut-side daily aggregation. |
| **Token leakage / brute force** | Shared Shortcut, guessing | Store **hash only**; short non-secret indexed `prefix`; `secrets.compare_digest`; ≥256-bit secret; optional expiry; revoke/rotate; `last_used_at` audit; **HTTPS-only (§4)**; rate-limit + temporary lockout on repeated `401`s from an IP/prefix. |
| **CSRF into ingest** | Logged-in browser tricked into POSTing | Ingest is **bearer-only** and **explicitly CSRF-exempt** (D4/§6.3); the dependency ignores cookies, so a cookie-bearing forged request cannot authenticate. |
| **Cross-user write** | Spoofed user id in payload | **Never** accept a user id from the client; derive from the authenticated principal (bearer → token owner, cookie → session user). All writes are scoped to that user; token A cannot write user B. |
| **Invalid units / dates** | Unknown unit, false/future dates | Whitelist units; explicit conversion; parse `±ZZZZ`; reject unknown units + out-of-range + future dates → `invalid` (skip, never abort). |
| **Partial import / mid-run failure** | Crash on a large file | Atomic single-commit import (§7.7); idempotent retry; durable `failed` batch via a separate session; no duplicates on re-run. |
| **PHI at rest / in logs / 3rd parties** | Upload lingering, log leakage, analytics | No raw retention (§8.1); logs never contain health values or tokens; **no third-party/analytics/LLM** processing (FitPath's coach is offline/rule-based); never place PHI in iCloud (§1.2). |

---

## 10. Edge cases
- **Timezones/DST/travel:** Apple timestamps carry an offset; a sleep session or midnight-crossing interval
  is assigned to its **local wake date**; `hours` capped ≤24.
- **Sleep schema variants:** iOS ≥16 staged vs. legacy `Asleep`/`InBed`; InBed-only falls back to
  time-in-bed with a warning (§5.2).
- **Steps source overlap:** iPhone+Watch double-count → dominant source per day + approximation warning.
- **Weight unit per record:** kg vs lb varies by source; always read `unit`.
- **Water row explosion:** hundreds of sips → one aggregated `WaterLog`/day (clamped ≤5000, §5.4).
- **Empty/absent types:** authorization opacity means some types are simply missing → `0` counts, not errors.
- **Workout ≠ strength session:** never create `WorkoutSession`/`SetLog` from Apple workouts.
- **Very old data:** allowed; preview shows the full date range so the user can decide before committing.
- **Re-import after edits:** manual edits are preserved as `conflict` (§6.4), not overwritten.
- **Large multi-year `export.xml`:** preview itself streams (never buffers the whole file) and shows date
  range + counts before any commit.

---

## 11. UI flow (Settings → "Apple Health" card)

A new `Card` in `frontend/src/pages/Settings.tsx`, using existing `Card`/`CardHeader`/`Button`/`Segmented`/
`Input`/`Checkbox`/`EmptyState`/`useToast` and the `http` client + new upload helper (§6.2).

**Disclosure banner (required, §1.2 / §12):** "FitPath imports only Steps, Body mass, Sleep, Water, and
Workouts from Apple Health. Your data is processed on FitPath's server only, never shared with third parties
or used for ads, and you can delete it anytime."

1. **Manual import**
   - *Choose file* (`export.zip`/`export.xml`) → calls `preview`.
   - Show the **preview table**: per-type counts, date range, detected units, warnings.
   - **Type checkboxes** (Steps / Body mass / Sleep / Water / Workouts) → *Import selected*.
   - `import` re-uploads the retained `File`; show the per-type `{inserted, updated, skipped, invalid,
     conflict}` result and a link to history. Surface `conflict > 0` as "N days kept your manual edits."
2. **Import history** — list from `GET …/imports` (source, status, date range, counts, timestamps).
3. **Delete imported data** — optional date/type scope → `DELETE …/data`; confirm dialog; show the report
   ("preserved N modified rows").
4. **Shortcut sync (tap-to-sync)**
   - *Generate token* → reveal **once** with copy button + "store it now, you won't see it again."
   - Token list: name, `prefix`, created, last used, expires; **Rotate** / **Revoke** actions.
   - Step-by-step Shortcut guide (Appendix A) + explicit "requires HTTPS; tap-to-sync, not background."

---

## 12. Privacy & disclosure (App Store §5.1.2(vi)/§5.1.3 aligned)
- **Explicit disclosure** of the exact types collected (steps, body mass, sleep, water, workouts) shown
  before first import and in the Settings card (§11).
- **First-party processing only:** parse on FitPath's server; **no** third-party/analytics/LLM; no ad or
  use-based data mining; no PHI in iCloud.
- **Data minimization:** persist only the mapped, aggregated values FitPath already models; discard the raw
  upload immediately (§8.1).
- **User control:** delete imported data anytime (§8.2); rotate/revoke tokens anytime (§6.4).

---

## 13. Exact file list

**New (backend)**
- `app/services/apple_health.py` — safe zip open + `defusedxml.iterparse` streaming parser; per-type mappers
  (steps/weight/sleep/water/workouts); unit conversions; external-key + payload-hash helpers; import state
  machine (§6.4).
- `app/routes/apple_health.py` — router `prefix="/api/integrations/apple-health"`: `preview`, `import`,
  `imports`, `data` (cookie+CSRF); `tokens` CRUD + `rotate` (cookie+CSRF); `shortcut` (bearer-only).
- `alembic/versions/<rev>_apple_health_integration.py` — **one** migration creating the three tables.
- `tests/test_apple_health.py` — parser/security/idempotency/auth/import/delete tests (§15).
- `frontend/src/pages/Settings.css` additions (or a small `AppleHealthCard.tsx`) for the new card styles.

**Modified (backend)**
- `app/models.py` — add `ApiSyncToken`, `HealthImportBatch`, `ImportedHealthRecord` (+ `__all__`).
- `app/deps.py` — add `bearer_token_user` (Authorization-only, cookie-ignoring) dependency.
- `app/security.py` — add the `shortcut` path to `_EXEMPT_PATHS` (§6.3).
- `app/routes/admin.py` — extend reset to clear `ImportedHealthRecord` + `HealthImportBatch` (§8.3).
- `app/main.py` — `app.include_router(apple_health.router)` (§app/main.py:72-83).
- `app/schemas.py` — Pydantic bodies (`ShortcutSyncIn`, token create, delete-scope) + response models.
- `requirements.txt` — add `python-multipart` and `defusedxml` (§14).

**Modified (frontend)**
- `frontend/src/api/client.ts` — add a multipart upload helper (§6.2).
- `frontend/src/api/endpoints.ts` — add `appleHealth.{preview,import,imports,deleteData}` and
  `appleHealthTokens.{list,create,rotate,revoke}`.
- `frontend/src/api/types.ts` — response/request types.
- `frontend/src/api/mock.ts` — mock the new endpoints so demo mode keeps working.
- `frontend/src/pages/Settings.tsx` — the Apple Health card + Shortcut guide.

---

## 14. Dependencies
Add to `requirements.txt` (currently lacks both — `requirements.txt:1-9`):
- **`python-multipart`** — required for FastAPI `UploadFile` / `multipart/form-data`.
- **`defusedxml`** — safe streaming XML (`iterparse`) hardened against XXE/entity attacks.

No new frontend runtime dependencies (native `FormData`/`fetch`).

---

## 15. Migration plan

**Count: 1 Alembic migration** creating all three tables.

- Base revision is `8f9c28b008e4` (`alembic/versions/8f9c28b008e4_initial_schema.py`); the new revision's
  `down_revision = "8f9c28b008e4"`.
- Generate with `alembic revision --autogenerate -m "apple health integration tables"` (after adding the
  models), then **review** — the project uses **`render_as_batch=True`** (`alembic/env.py:58,82`), so
  indexes/constraints go through `with op.batch_alter_table(...) as batch_op:` exactly like the initial
  migration.
- `upgrade()` creates `api_sync_token`, `health_import_batch`, `imported_health_record` with FKs
  (`ondelete="CASCADE"` to `user`; `imported_health_record.batch_id` → `health_import_batch` `SET NULL`),
  the unique constraint `uq_imported_health_record`, and the listed indexes. `downgrade()` drops indexes
  then tables in reverse order.
- Apply with `alembic upgrade head`. `init_db()` (`app/db.py:99-101`) also creates them for dev/test via
  `Base.metadata.create_all`, so the test suite's temp DB (`tests/test_smoke.py:14-25`) works without
  running Alembic.

---

## 16. Test matrix (extend `tests/`, patterns from `tests/test_smoke.py`)

**Parser (unit, tiny fixture `export.xml` — Appendix B)**
- steps summed per day (dominant source, no iPhone+Watch double count);
- weight latest-per-day; kg kept, lb→kg conversion;
- sleep staged summation, legacy `Asleep` fallback, `InBed`-only → time-in-bed warning, midnight/DST crossing → correct wake date;
- water mL and fl_oz_us→mL, aggregated per day, >5000 clamp;
- workout activity mapping + intensity table + kcal/min override + duration-unit conversion;
- unknown unit / out-of-range / future date → `invalid` (not crash).

**Security**
- zip bomb: ratio/size cap trips → rejected;
- zip-slip member name rejected; only `…/export.xml` read;
- XXE / billion-laughs payload safely rejected (no expansion) under `defusedxml`;
- oversized upload → `413`; wall-clock/record cap → `partial`/`422`.

**Idempotency & state machine**
- re-import same file → all `skipped`, **0 net new** rows;
- Apple value changed + local unmodified → `updated`, single row;
- local manually edited after import → `conflict`, edit preserved;
- pre-existing manual day-row (steps/weight) → `conflict`, not overwritten;
- append types never duplicated across two imports.

**Auth boundary**
- `shortcut` accepts a valid bearer with **no cookie** (passes CSRF);
- missing/invalid/revoked/expired token → `401`;
- cookie is **ignored** on `shortcut` (a session cookie without a bearer → `401`);
- token brute-force lockout;
- cross-user isolation: token A cannot write user B's data;
- cookie+CSRF routes (`preview`/`import`/`tokens`/`data`) reject missing CSRF with `403` and no session with `401`.

**Import correctness**
- `preview` writes nothing (row counts unchanged before/after);
- `import` returns correct per-type `{inserted, updated, skipped, invalid, conflict}`;
- values land in `StepLog/WeightLog/SleepLog/WaterLog/ActivityLog` scoped to the user and honor schema bounds;
- one bad metric in a shortcut push doesn't reject the others;
- failed import persists a `failed` `HealthImportBatch` and rolls back all data (no partial rows).

**Deletion**
- `DELETE …/data` removes only unmodified imported rows; modified rows counted `preserved_modified`;
- date/type scoping honored;
- `admin/reset` clears provenance + batches (no dangling rows).

**E2E happy path**
- upload realistic export → preview → select types → import → verify Insights/Trends reflect the history →
  generate token → simulate shortcut push updating today → delete imported data → history reflects all runs.

---

## 17. Resolved inconsistencies (research draft vs. code audit)

| Topic | Research draft said | This design (final) | Why |
|---|---|---|---|
| **Provenance** | `HealthImportKey(source_hash)` dedupe + note that day-keyed types rely on their UNIQUE | **Generic 3-table model** (`ApiSyncToken`, `HealthImportBatch`, `ImportedHealthRecord`) | `source_hash` only prevents dupes; it can't detect Apple value updates, link to the local row for safe delete, record batch status, or generalize to other providers. **Generic provenance wins** (D2). |
| **Apple-specific columns** | (audit surfaced the *option* of `apple_health_uid`/source columns on each log) | **Rejected** — no per-log Apple columns | Five nullable columns on five tables couple the log schema to one provider and still can't express "unmodified since import." Side table is cleaner (D2). |
| **Preview → commit handoff** | `POST /api/imports/apple-health` returns `import_id`; `POST …/{id}/commit` (implies a server-side parsed/temp registry) | **Stateless**: `preview` discards; browser re-uploads the `File` to `import` | Avoids PHI-at-rest and a temp-registry GC problem (D1). |
| **Endpoint namespace** | Split `/api/imports/*` + `/api/sync/*` | Unified `/api/integrations/apple-health/*` | One cohesive, discoverable surface (D3). |
| **Re-import of edited days** | "last-writer-wins on day-keyed types" | **Preserve manual edits** (`conflict`) | Now that provenance detects edits, clobbering them is wrong and inconsistent with safe delete (D6/D7). |
| **CSRF for ingest** | Relies on the middleware naturally skipping cookieless requests | Keep that, **plus** an explicit `_EXEMPT_PATHS` entry and a cookie-ignoring dependency | Defense-in-depth against a cookie accidentally riding along (D4). |
| **Account deletion** | Recommended adding a GDPR account-delete endpoint | **Deferred / out of scope**; imported-data delete only | Avoid scope creep; imported-data deletion is the required privacy control (D8). |
| **Water** | append (recommended aggregate) | **Aggregate to one row/day**, tracked by provenance | Deterministic idempotency + no row explosion (§5, §5.4). |

---

## 18. References
- Apple — App Store Review Guidelines §5.1.2(vi), §5.1.3: <https://developer.apple.com/app-store/review/guidelines/>
- Apple — HealthKit (framework, entitlement, authorization): <https://developer.apple.com/documentation/healthkit>
- Apple — `HKQuantityTypeIdentifier`: <https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier>
- Apple Support — Share/Export data in Health on iPhone: <https://support.apple.com/guide/iphone/share-your-health-data-iph5ede58c3d/ios>
- Apple — Shortcuts User Guide (running & automations): <https://support.apple.com/guide/shortcuts/>
- OWASP — XML External Entity (XXE) Prevention; Python `defusedxml` docs.

---

## Appendix A — Sample Shortcut construction (Option B)
1. **Settings → Apple Health → Generate sync token**; copy the `fpk_…` token (shown once).
2. In **Shortcuts**, create "Sync FitPath":
   - **Find Health Samples** → Steps → Date is Today → aggregate **Sum** (→ `Steps`). Repeat for Body Mass
     (most recent), Sleep (last night asleep hours + wake time), Water (sum today). Optionally **Find
     Workouts** for today.
   - **Text** action → build the JSON body from §6.3.
   - **Get Contents of URL**: URL `https://<your-fitpath-host>/api/integrations/apple-health/shortcut`,
     Method `POST`, Request Body `JSON`, Header `Authorization` = `Bearer fpk_…`,
     Header `Content-Type` = `application/json`.
   - **Show Result** to confirm the applied counts.
3. (Optional) Add a **Time of Day** automation — expect a tap to allow Health access (tap-to-sync).
4. **Do not share** this Shortcut; the token authenticates as you. Rotate/revoke in Settings anytime.

## Appendix B — Minimal fixture `export.xml` for tests
```xml
<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
          startDate="2026-07-14 08:00:00 -0700" endDate="2026-07-14 08:10:00 -0700" value="1200"/>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Apple Watch" unit="count"
          startDate="2026-07-14 09:00:00 -0700" endDate="2026-07-14 09:05:00 -0700" value="800"/>
  <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Withings" unit="kg"
          startDate="2026-07-14 06:30:00 -0700" endDate="2026-07-14 06:30:00 -0700" value="80.1"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepCore"
          startDate="2026-07-13 23:30:00 -0700" endDate="2026-07-14 03:00:00 -0700"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepREM"
          startDate="2026-07-14 03:00:00 -0700" endDate="2026-07-14 06:45:00 -0700"/>
  <Record type="HKQuantityTypeIdentifierDietaryWater" sourceName="iPhone" unit="mL"
          startDate="2026-07-14 10:00:00 -0700" endDate="2026-07-14 10:00:00 -0700" value="500"/>
  <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="32" durationUnit="min"
           totalEnergyBurned="320" totalEnergyBurnedUnit="kcal"
           startDate="2026-07-14 06:30:00 -0700" endDate="2026-07-14 07:02:00 -0700" sourceName="Apple Watch"/>
</HealthData>
```
Expected import (one dominant source for steps): **steps = 1200 (14 Jul, iPhone dominant)**, weight = 80.1 kg
(14 Jul), sleep ≈ 7.25 h asleep with wake 06:45 (wake date 14 Jul), water = 500 mL (14 Jul), one Running
`ActivityLog` 32 min / vigorous. External keys: `steps:2026-07-14`, `weight:2026-07-14`,
`sleep:2026-07-14`, `water:2026-07-14`, `workout:Running|Apple Watch|2026-07-14T06:30:00|2026-07-14T07:02:00`.
