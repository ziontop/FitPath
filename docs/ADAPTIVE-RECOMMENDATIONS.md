# FitPath — Adaptive Recommendations (design spec)

> **Status:** design proposal (no production code changed by this document).
> **Scope:** a deterministic, privacy-preserving, **non-LLM** engine that makes
> meal and workout suggestions *build on what the user has already done* and
> *keep improving from history*, while clearly explaining **how history changed
> the recommendation**.
>
> **Naming:** this is an **adaptive / history-based** engine. It is not AI and
> makes no ML claims — every number is computed from the user's own logged rows
> with published formulas. It lives under `/api/recommendations/*`, never
> `/api/ai/*`.

---

## 0. TL;DR

* **Meals** — rank the user's own logged foods with a transparent weighted score
  over five signals: **macro-fit to today's remaining gap**, **recency**,
  **frequency**, **adherent-day contribution** (did this food show up on days the
  user actually hit target?), and **category/time fit**, plus a small favorite
  bump. Portions are scaled to the remaining budget; results are **diversified**
  (MMR) so you never get three near-identical picks; cold start falls back to
  curated starters. Each pick returns `reason`, `history_basis`, `confidence`,
  and a one-tap `meal_payload`.
* **Workouts** — per exercise, read the recent completed working sets and apply
  **double progression gated by RPE**: *increase* after a top-of-range success at
  ≤ target RPE, *hold / add a rep* when inside the range, *repeat then reduce*
  after misses / high RPE, and *deload* after repeated stalls, a falling e1RM, or
  persistent high fatigue. Layoffs resume **lighter, not punished**. Each exercise
  returns `last_performance`, `change`, `reason`, `confidence`, and a `deload`
  flag.
* **Unified** — one envelope (`AdaptiveRecommendation`) powers the Today screen
  and two detail endpoints (`/meals`, `/workout`). Every payload carries a
  `version` + `algorithm` id so behavior is auditable. All queries are
  per-user-scoped; there are **no broad catches or silent defaults** (documented
  cold-start fallbacks only).
* **DB migration:** **none required.** Every signal is derived from existing
  tables (`meal_log`, `set_log`, `workout_session`, `program_exercise`,
  `nutrition_plan`, `profile`).

---

## 1. Design principles

1. **Deterministic** — same inputs ⇒ same output. No randomness; any tie-break or
   cross-day rotation is seeded by a stable key (date + user id + name) so it is
   reproducible and testable.
2. **Privacy-preserving & offline** — only the authenticated user's own rows are
   read (no cross-user aggregation, no third-party calls, no LLM).
3. **History-first & self-improving** — recommendations are functions of logged
   history; as more data accrues the signals sharpen and `confidence` rises. The
   engine explicitly rewards foods/loads that *worked* on the user's successful
   days.
4. **Explainable** — every suggestion ships `reason` (plain English),
   `history_basis` (the counts it is grounded in), and per-component sub-scores
   for audit.
5. **Auditable** — every response carries `version` (`"adaptive-v1"`) and
   `algorithm` (`"history-adaptive-deterministic"`).
6. **Additive & backward compatible** — new endpoints under
   `/api/recommendations/`; the existing `/api/recommendations/today`,
   `/api/programs/today`, and `/api/nutrition/today` shapes are unchanged.
7. **No silent failure** — a missing profile raises `400` (as
   `nutrition.nutrition_today` already does). Cold start / sparse history use
   **documented, explicit** fallbacks, never a bare `except: pass`.
8. **Reuse the science** — progression, deload, e1RM and macro constants come
   from `app/training/params.py` and the existing `performance` / `coach`
   helpers, so the adaptive engine and the rest of the app never disagree.

---

## 2. Data sources (existing tables only — no migration)

| Signal | Source | Notes |
| --- | --- | --- |
| Logged foods (name, category, kcal, macros, time, favorite) | `meal_log` | recency/frequency/macro-fit/adherence |
| Today's consumed | `meal_log` (today) | remaining gap + exclude already-eaten |
| Calorie/macro targets | `nutrition_plan` (active) → else derived from `profile` | via `nutrition.active_macro_targets` / `nutrition.goal_target_kcal` (single source of truth) |
| Working sets (weight, reps, rpe, warmup) | `set_log` ⨝ `workout_session` | progression, stalls, fatigue |
| e1RM trend & best | derived via `performance.exercise_performance` / `best_recent_e1rm` | Epley/Brzycki, reps capped at 10 |
| Prescription (sets, rep range, RPE, rest, scheme) | `program_exercise` (active program) | target range + cold-start fallback |
| Session cadence / adherence | `workout_session` dates | consistency, layoff, resume-safe |
| Meal timing / next slot | `coach.analyze_patterns` / `coach.predict_next_meal_detailed` | reuse existing pattern mining |

> **Assumption (documented):** historical targets are approximated by the
> *current* plan targets when scoring adherent days, because the app does not
> persist a per-day target snapshot. This is acceptable (targets change rarely)
> and is the same source of truth used everywhere else. Persisting historical
> targets would be a *future* enhancement and is the **only** thing that would
> ever justify a migration — it is **not** required for v1.

---

## 3. Versioning

Every response includes:

```json
{ "version": "adaptive-v1", "algorithm": "history-adaptive-deterministic" }
```

Bump `version` (`adaptive-v2`, …) whenever weights, thresholds, or rules change,
so stored/eyeballed outputs remain attributable to an exact rule set. Constants
live in one block (`app/ml/adaptive.py`, §8) tagged with citations.

---

## 4. Meal engine

### 4.1 Candidate aggregation

Read `meal_log` for the user over `MEAL_WINDOW_DAYS = 30` (configurable up to 60).
Group rows by a **normalized key** `(_norm(name), category)` where
`_norm` = lowercase + trim + collapse whitespace (reuse the spirit of
`services.mapping._normalize`). For each candidate accumulate:

* `logged_count` `n` — number of rows in the group,
* `last_eaten_at` — most recent timestamp,
* `base_*` — **median** kcal/protein/carbs/fat across the group (median resists a
  single mis-logged outlier better than mean),
* `favorite` — logical OR of the group's `favorite` flags,
* `eaten_days` — the set of calendar dates the food appears on,
* `eaten_hours` — list of hour-of-day values (for time-fit).

Foods **already logged today** are excluded from the candidate pool by default
(they are the strongest anti-repetition signal available without persistence).

### 4.2 Scoring components (each normalized to `[0, 1]`)

Let the **remaining gap** be `g = (gᴾ, gᶜ, gᶠ)` where
`gᴹ = max(0, target_macro − consumed_macro)` for macro `M ∈ {protein, carbs, fat}`
(grams). Let the food's macro vector be `f = (fᴾ, fᶜ, fᶠ)` (base grams).

**(1) Macro-fit `M` — cosine similarity to the remaining gap, kcal-tempered.**

```
cos(f, g) = (f · g) / (‖f‖ · ‖g‖)          # in [0,1] for non-negative vectors; 0 if either is 0
kcal_fit  = min(serving_kcal, budget) / max(serving_kcal, budget)   # 0..1, 1 = exact size match
M         = cos(f, g) * (KCAL_FIT_FLOOR + (1 - KCAL_FIT_FLOOR) * kcal_fit)
```

where `budget = remaining_kcal / meals_left_est` (see §4.4) and
`KCAL_FIT_FLOOR = 0.6` (a perfectly macro-shaped food is never zeroed just for
size). Cosine similarity captures *"does this food point in the direction of what
I still need?"* — a lean-protein food scores high when protein is the dominant
remaining need, and low once protein is met.

**(2) Recency `R` — exponential decay.**

```
days_since = (today − last_eaten_at.date()).days
R = 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)      # 1.0 today, 0.5 at 14d, 0.25 at 28d
```
with `RECENCY_HALF_LIFE_DAYS = 14`.

**(3) Frequency `F` — saturating ratio.**

```
F = n / (n + FREQ_SMOOTHING)                          # 1→0.25, 3→0.5, 9→0.75; saturates
```
with `FREQ_SMOOTHING = 3`. (Log-saturation is an equivalent alternative; the
smoothed ratio is simpler and monotone.)

**(4) Adherence `A` — contribution on on-target days.** See §4.3.

**(5) Category/time fit `T`.**

```
T = 1.0                              if candidate.category == predicted_category
  = 0.6                              elif median(eaten_hours) within TIME_FIT_WINDOW_MIN of now
  = 0.3                              otherwise
```
with `TIME_FIT_WINDOW_MIN = 90`. `predicted_category` comes from
`coach.predict_next_meal_detailed(...).predicted_category` (reused, not
reimplemented).

**(6) Favorite bump `Fav` = 1.0 if favorite else 0.0** (additive, not part of the
normalized weight budget).

### 4.2.1 Composite score & weights

```
score = W_M·M + W_R·R + W_F·F + W_A·A + W_T·T + W_FAV·Fav
```

| Weight | Symbol | Value | Rationale |
| --- | --- | --- | --- |
| Macro-fit | `W_M` | **0.35** | The pick must serve *today's* remaining needs first. |
| Adherence | `W_A` | **0.20** | Reward foods from days the user actually hit target. |
| Recency | `W_R` | **0.15** | Recent foods are in-rotation and available. |
| Frequency | `W_F` | **0.15** | Habitual foods are realistic to log again. |
| Category/time | `W_T` | **0.15** | Right food for the right slot. |
| Favorite | `W_FAV` | **+0.05** | Small explicit-preference bump (additive). |

`W_M + W_A + W_R + W_F + W_T = 1.00`. Sub-scores + weights are returned under
`components` for audit.

### 4.3 Adherence signal (the "successful-day" learner)

This is the core *self-improvement from history* mechanism.

1. For each day `D` in the window with ≥ 1 logged meal (excluding today), compute
   `kcal_D`, `protein_D` from `meal_log`.
2. Mark `D` **adherent** iff
   `KCAL_LOW·target_kcal ≤ kcal_D ≤ KCAL_HIGH·target_kcal` **and**
   `protein_D ≥ PROTEIN_MIN·target_protein` with
   `KCAL_LOW = 0.90`, `KCAL_HIGH = 1.10`, `PROTEIN_MIN = 0.90`.
3. Let `adherent_days` be that set.
4. For each candidate food:
   ```
   A = |eaten_days ∩ adherent_days| / |eaten_days|          # fraction of its days that were on-target
   ```
5. **Fallback:** if `|adherent_days| == 0` (no on-target day yet) or there are
   fewer than `MIN_DAYS_FOR_ADHERENCE = 5` observed days, set `A = 0.5`
   (neutral) for all candidates so the signal neither helps nor hurts until it is
   trustworthy.

Effect: a food that keeps appearing on the user's on-target days floats up; a food
that only appears on blow-out days sinks — learned purely from history.

### 4.4 Portion / serving adaptation

```
meals_left_est = max(1, round(remaining_kcal / typical_meal_kcal))   # typical from coach patterns
budget         = remaining_kcal / meals_left_est
portion        = clamp(round_to(budget / base_kcal, 0.25), PORTION_MIN, PORTION_MAX)   # if base_kcal>0 & remaining>0 else 1.0
```
with `PORTION_MIN = 0.5`, `PORTION_MAX = 2.0`. The suggested serving is
`round(base_* · portion)`; `meal_payload` uses the scaled numbers and echoes
`portion`. When the binding constraint is protein (protein gap ≫ kcal gap), an
alternative `portion = clamp(protein_gap / base_protein, …)` MAY be used; v1 uses
the kcal-based rule for determinism and documents the protein variant.

### 4.5 Diversification (Maximal Marginal Relevance)

Selecting the raw top-N by score can return three chicken-and-rice rows. Instead,
select greedily:

```
selected = []
pool = candidates sorted by score desc
while len(selected) < top_n and pool:
    for each c in pool:
        penalty = max(sim(c, s) for s in selected)  if selected else 0
        adj(c)  = score(c) − MMR_LAMBDA · penalty
    pick c* = argmax adj(c); move c* from pool to selected
```
with `MMR_LAMBDA = 0.5` and

```
sim(a, b) = 0.5·[a.category == b.category]
          + 0.3·cos(a.macros, b.macros)
          + 0.2·jaccard(tokens(a.name), tokens(b.name))
```

Hard rules layered on top:

* **≤ 2 per category** among the returned picks (unless the pool has < 3
  categories).
* **Drop near-duplicate names:** if `jaccard(tokens) ≥ 0.6` with an
  already-selected pick, skip.

### 4.6 Repetition prevention across days (no persistence, no migration)

To avoid suggesting the identical set every single day without storing history,
break score ties and rotate among **statistically equivalent** foods
(scores within `TIE_EPSILON = 0.02`) using a deterministic key:

```
rotation_rank = stable_hash(f"{user_id}:{today.isoformat()}:{norm_name}")
```

This is reproducible (testable by freezing the date) and needs no new column.
Foods already eaten today are excluded (§4.1), which is the primary within-day
anti-repeat.

### 4.7 Cold start & sparse fallbacks

| State | Rule | `confidence` |
| --- | --- | --- |
| **0 distinct foods** | Return curated `_FALLBACK_SUGGESTIONS` (from `nutrition.py`), re-ranked by macro-fit to the gap and portion-scaled. `history_basis` = "no logged meals yet — starter suggestions." | `low` |
| **1–2 distinct foods, or < 5 days** | Blend history candidates with the top fallback(s) to reach `top_n`; adherence neutralized (§4.3). | `low`→`medium` |
| **No active plan** | Use profile-derived targets (`nutrition.active_macro_targets` already falls back). | unaffected |
| **Missing profile** | Raise `400` (mirror `nutrition._require_profile`). | n/a |

### 4.8 Confidence (deterministic thresholds)

```
high   : days_observed ≥ 14  AND  distinct_foods ≥ 8
medium : days_observed ≥ 5   AND  distinct_foods ≥ 3
low    : otherwise (includes cold start)
```

### 4.9 Explanations

* **`reason`** — built from the dominant components (highest weighted
  contributors). Example:
  *"High protein to close your 42 g protein gap, and one of your go-to dinners
  (logged 6×)."*
* **`history_basis`** — the raw counts:
  *"From 27 meals across 21 days · eaten 6× (last 2 days ago) · on 4 of your 9
  on-target days."*
* **`components`** — the six sub-scores for audit.

### 4.10 Worked example (meals)

**Input** — active plan `2600 kcal / P195 / C300 / F75`; consumed so far today
`1400 kcal / P150 / C150 / F45`; now = 18:40; predicted slot = `dinner`.
Remaining gap `g = (P45, C150, F30)`; `remaining_kcal = 1200`.

Candidate **"Chicken & rice"** (dinner, logged 8×, last 1 day ago, base
`620 kcal / P52 / C60 / F14`, appears on 5 days, 4 of which adherent):

```
cos(f,g): f=(52,60,14), g=(45,150,30) → 0.915
budget = 1200 / max(1, round(1200/600)) = 1200/2 = 600
kcal_fit = min(620,600)/max(620,600) = 0.968
M = 0.915 · (0.6 + 0.4·0.968) = 0.915 · 0.987 = 0.903
R = 0.5^(1/14) = 0.952
F = 8/(8+3) = 0.727
A = 4/5 = 0.80
T = 1.0 (category == dinner)
Fav = 0

score = 0.35·0.903 + 0.20·0.80 + 0.15·0.952 + 0.15·0.727 + 0.15·1.0 + 0.05·0
      = 0.316 + 0.160 + 0.143 + 0.109 + 0.150 = 0.878
portion = clamp(round_to(600/620, .25), .5, 2) = 1.0
```

**Output row:**
```json
{
  "name": "Chicken & rice", "category": "dinner",
  "kcal": 620, "protein_g": 52, "carbs_g": 60, "fat_g": 14, "portion": 1.0,
  "score": 0.878,
  "components": {"macro_fit":0.903,"adherence":0.80,"recency":0.952,"frequency":0.727,"category_fit":1.0,"favorite":0.0},
  "reason": "Balanced protein + carbs to close your 45g protein / 150g carb gap, and a go-to dinner (logged 8×).",
  "history_basis": "From 27 meals over 21 days · eaten 8× (last 1 day ago) · on 4 of your 5 on-target days.",
  "confidence": "high",
  "logged_count": 8, "last_eaten_at": "2026-07-13T19:05",
  "meal_payload": {"name":"Chicken & rice","kcal":620,"category":"dinner","protein_g":52,"carbs_g":60,"fat_g":14}
}
```

MMR then ensures picks #2/#3 are *not* another rice bowl (e.g. a Greek-yogurt
snack for the protein-only tail of the gap).

---

## 5. Workout engine

### 5.1 Per-exercise session aggregation

For each exercise on today's program day, read its working (non-warmup) sets over
the last `WORKOUT_LOOKBACK_SESSIONS = 5` sessions (via
`performance._working_sets_stmt` + a per-session group, or
`performance.exercise_performance`). Per session compute:

* `top_set` — the heaviest working set (`max weight`, tie-break higher reps);
  `(weight, reps, rpe)`,
* `sets_completed` — count of working sets,
* `session_e1rm` — `max` e1RM across its sets (`performance._e1rm`).

Parse the prescription range from `program_exercise.target_reps` via
`programs.low_rep` (low) and the upper bound (`rep_high`). `target_rpe`,
`target_sets`, `progression`, and the plate `increment` (§8) come from the
prescription / params.

### 5.2 Decision rules — double progression gated by RPE

Evaluate in **priority order**; the first match wins. `last` = most recent
session's `top_set`.

| # | Action | Trigger (from logged history) | Next `weight` | Next `reps` | `deload` |
| --- | --- | --- | --- | --- | --- |
| 0 | `start` | No prior sets for this exercise | program `suggested_weight` (e1RM-derived, else `null`) | `rep_low`–`rep_high` | false |
| 1 | `deload` | `stall_count ≥ STALL_SESSIONS_FOR_DELOAD` **or** `last_e1rm ≤ best_recent_e1rm·(1−E1RM_REGRESS_PCT)` **or** last 2 sessions `rpe ≥ target_rpe+HIGH_RPE_MARGIN` **and** `reps < rep_low` | `round(last_weight·DELOAD_LOAD_FRACTION)` | `rep_low` | **true** |
| 2 | `reduce` | 2nd consecutive session with `top_reps < rep_low` (a real miss, not a layoff) | `last_weight − increment` | `rep_low` | false |
| 3 | `hold` (repeat) | 1st session with `top_reps < rep_low`, **or** `top_reps == rep_high` but `rpe > target_rpe` | `last_weight` | `min(rep_high, last_reps+1)` | false |
| 4 | `increase` | `top_reps ≥ rep_high` **and** `rpe ≤ target_rpe` **and** `sets_completed ≥ target_sets` | `last_weight + increment` (×2 if `rpe ≤ target_rpe−EASY_RPE_MARGIN`) | `rep_low` | false |
| 5 | `hold` (progress reps) | inside range: `rep_low ≤ top_reps < rep_high` | `last_weight` | `min(rep_high, last_reps+1)` | false |

Constants (§8): `STALL_SESSIONS_FOR_DELOAD = 3`, `E1RM_REGRESS_PCT = 0.05`,
`HIGH_RPE_MARGIN = 1.5`, `EASY_RPE_MARGIN = 2.0`. `increment` from
`LINEAR_INCREMENT_KG` (upper `1.25`, lower `2.5`) keyed by the lift's muscle
group; loads are snapped with `performance.round_to_increment`.

**Stall definition** (drives deload #1): a session is a *stall* if it did **not**
beat the previous *logged* session on either load or reps at the top set. Count
**consecutive** stalls over logged sessions only — calendar gaps never increment
`stall_count` (see §5.3).

`target_sets` is normally the prescription's; a deload MAY also cut volume toward
maintenance via `DELOAD_VOLUME_FRACTION` (0.50) — v1 keeps sets and cuts load
only, and documents the volume-cut variant.

### 5.3 Missed sessions / inconsistent user → resume safely

* `days_since_last = today − last_session_date` **for this exercise**.
* If `days_since_last > LAYOFF_DAYS = 14`: apply a one-time
  `LAYOFF_LOAD_FRACTION = 0.93` (≈ −7%) to the *hold/increase* branches, reset
  reps to `rep_low`, set `action = "hold"`, and `reason` = *"resuming after N days
  off — starting a touch lighter."* **Do not** treat the gap as a stall or a
  miss.
* Consecutive-stall and consecutive-miss counters iterate over **logged sessions
  in order**, so an inconsistent user is never punished for calendar gaps.

### 5.4 Day selection (which workout today)

* **Backward-compatible base:** the existing weekday rotation
  (`programs.weekly_schedule`) still powers `/programs/today`.
* **Adaptive option (for `/recommendations/workout` + the envelope):**
  **next-in-rotation** — find the most recent *completed* `workout_session` with a
  `program_day_id`, then recommend the next `day_index` in the program cycle. This
  suits inconsistent users (it advances the split when *they* train, not when the
  calendar says). If no completed session exists, fall back to the weekday
  rotation; if neither yields a day, `rest_day = true`.
* The endpoint accepts an optional `?program_day_id=` to force a specific day.

### 5.5 Confidence

```
high   : ≥ 4 logged sessions for this exercise
medium : 2–3 sessions
low    : 0–1 sessions (cold start = low)
```

Session-level `confidence` = the min across recommended exercises (a day is only
as trustworthy as its least-known lift).

### 5.6 Explanations

* **`last_performance`** — `{date, weight, reps, rpe, sets, e1rm}` of the most
  recent session (or `null` at cold start).
* **`change`** — `{weight_delta_kg, reps_delta, direction: "up"|"down"|"flat"}`.
* **`reason`** — e.g. *"You hit 3×8 @ RPE 7 last time (top of range with a rep in
  reserve) — adding 2.5 kg."* / *"Two stalled sessions and e1RM slipped 6% —
  deloading to 90% to resupercompensate."*
* **`history_basis`** — e.g. *"Based on your last 5 Bench Press sessions;
  e1RM 112 → 118 kg."*
* **`deload`** flag + session-level `deload` (true if the majority of main lifts
  are deloading).

### 5.7 Cold start

No logged sets ⇒ `action = "start"`, `suggested_weight` from
`performance.suggested_weight(best_recent_e1rm, low_rep, target_rpe)` (which is
`null` without any e1RM, so the UI prompts for a starting weight — matching
current `/programs/today` behavior). `reason` cites the program prescription.

### 5.8 Worked example (workout)

**Bench Press**, prescription `4×6-8 @ RPE 8`, plate increment `1.25 kg` (upper).
Last 3 logged sessions' top sets:

| Session | weight | reps | rpe | e1rm |
| --- | --- | --- | --- | --- |
| −10 d | 80 | 8 | 8.0 | ~99 |
| −6 d | 82.5 | 7 | 8.0 | ~102 |
| −3 d (last) | 82.5 | **8** | **7.5** | ~104 |

Last session: `top_reps (8) ≥ rep_high (8)` **and** `rpe (7.5) ≤ target_rpe (8)`
**and** `sets_completed (4) ≥ target_sets (4)` ⇒ **rule #4 increase**.
`rpe (7.5)` is not ≤ `target_rpe − EASY_RPE_MARGIN (6.0)`, so a single increment.
Snap to the **increment step** (not the default 2.5 kg), i.e.
`round_to_increment(82.5 + 1.25, step=1.25) = 83.75`, reps reset to `6`. (If the
lift only had 2.5 kg plates you would pass `step=2.5`, giving `85.0`; the engine
always rounds to the same step it increments by so the suggestion is loadable.)

**Output:**
```json
{
  "exercise_id": 2, "name": "Bench Press",
  "action": "increase", "suggested_weight": 83.75,
  "target_sets": 4, "target_reps": "6-8", "target_rpe": 8.0, "deload": false,
  "last_performance": {"date":"2026-07-11","weight":82.5,"reps":8,"rpe":7.5,"sets":4,"e1rm":104.0},
  "change": {"weight_delta_kg": 1.25, "reps_delta": -2, "direction": "up"},
  "e1rm_trend": {"first": 99.0, "last": 104.0, "direction": "up"},
  "confidence": "medium",
  "reason": "You hit 4×8 @ RPE 7.5 last time (top of range with a rep in reserve) — adding 1.25 kg and resetting to 6 reps.",
  "history_basis": "Based on your last 3 Bench Press sessions; e1RM 99 → 104 kg."
}
```

---

## 6. Unified API contract

### 6.1 Endpoints (all additive; `GET`; auth + user-scoped)

| Method | Path | Purpose | Powers |
| --- | --- | --- | --- |
| GET | `/api/recommendations/adaptive` | Full envelope: meals + workout + tip | **Today** screen |
| GET | `/api/recommendations/meals?category=&limit=` | Detailed adaptive meal picks | Nutrition screen |
| GET | `/api/recommendations/workout?program_day_id=` | Detailed adaptive workout | Workout screen |
| GET | `/api/recommendations/today` | **Unchanged** legacy shape | back-compat |

`/today` keeps returning `{ workout, nutrition, tip }` exactly as today. (Optionally
it MAY gain an **additive** `"adaptive"` key later; not required for v1.)

### 6.2 Envelope

```jsonc
// GET /api/recommendations/adaptive
{
  "version": "adaptive-v1",
  "algorithm": "history-adaptive-deterministic",
  "generated_at": "2026-07-14T18:40:00",
  "meals":   { /* AdaptiveMealsBlock (see 6.3) */ },
  "workout": { /* AdaptiveWorkoutBlock (see 6.3) */ },
  "tip": "Today is Push A — work up to Bench at RPE 8 (try 83.75 kg). You have 1200 kcal and 45 g protein left; a chicken-&-rice dinner closes most of it."
}
```

### 6.3 Pydantic response models (proposed — add to `app/schemas.py`)

> Routes MAY keep returning `dict`s (as they do now) and use these purely as
> `response_model=` for OpenAPI, or construct them directly. Field names match the
> JSON above 1:1.

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
MealCategory = Literal["breakfast", "lunch", "dinner", "snack"]
WorkoutAction = Literal["start", "increase", "hold", "reduce", "deload"]
Direction = Literal["up", "down", "flat"]

RECOMMENDATION_VERSION = "adaptive-v1"
RECOMMENDATION_ALGORITHM = "history-adaptive-deterministic"


# ---- shared ----
class MacroSet(BaseModel):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class MealPayload(BaseModel):
    """Ready to POST to /api/logs/meals (mirrors schemas.MealIn)."""
    name: str
    kcal: float
    category: MealCategory
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None


# ---- meals ----
class MealScoreComponents(BaseModel):
    macro_fit: float
    recency: float
    frequency: float
    adherence: float
    category_fit: float
    favorite: float


class AdaptiveMealSuggestion(BaseModel):
    name: str
    category: MealCategory
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    portion: float = 1.0
    score: float
    components: MealScoreComponents
    reason: str
    history_basis: str
    confidence: Confidence
    logged_count: int
    last_eaten_at: Optional[str] = None
    meal_payload: MealPayload


class NextMealHint(BaseModel):
    predicted_category: MealCategory
    predicted_time: str
    suggested_kcal: int


class MealHistoryBasis(BaseModel):
    window_days: int
    days_observed: int
    total_meals: int
    distinct_foods: int
    adherent_days: int


class AdaptiveMealsBlock(BaseModel):
    version: str = RECOMMENDATION_VERSION
    algorithm: str = RECOMMENDATION_ALGORITHM
    targets: MacroSet
    consumed: MacroSet
    remaining: MacroSet
    next_meal: NextMealHint
    history_basis: MealHistoryBasis
    confidence: Confidence
    suggestions: list[AdaptiveMealSuggestion]


# ---- workout ----
class LastPerformance(BaseModel):
    date: str
    weight: float
    reps: int
    rpe: Optional[float] = None
    sets: int
    e1rm: float


class WeightChange(BaseModel):
    weight_delta_kg: float
    reps_delta: int
    direction: Direction


class E1rmTrendMini(BaseModel):
    first: float
    last: float
    direction: Direction


class AdaptiveExerciseRec(BaseModel):
    exercise_id: int
    name: str
    action: WorkoutAction
    suggested_weight: Optional[float] = None
    target_sets: int
    target_reps: str
    target_rpe: Optional[float] = None
    deload: bool = False
    last_performance: Optional[LastPerformance] = None
    change: WeightChange
    e1rm_trend: Optional[E1rmTrendMini] = None
    confidence: Confidence
    reason: str
    history_basis: str


class WorkoutAdherence(BaseModel):
    sessions_last_14d: int
    scheduled_days_per_week: int
    consistency: Literal["on_track", "inconsistent", "returning"]


class AdaptiveWorkoutBlock(BaseModel):
    version: str = RECOMMENDATION_VERSION
    algorithm: str = RECOMMENDATION_ALGORITHM
    rest_day: bool = False
    program_day_id: Optional[int] = None
    name: Optional[str] = None
    deload: bool = False
    confidence: Confidence = "low"
    adherence: Optional[WorkoutAdherence] = None
    reason: str = ""
    exercises: list[AdaptiveExerciseRec] = Field(default_factory=list)


# ---- envelope ----
class AdaptiveRecommendation(BaseModel):
    version: str = RECOMMENDATION_VERSION
    algorithm: str = RECOMMENDATION_ALGORITHM
    generated_at: str
    meals: AdaptiveMealsBlock
    workout: AdaptiveWorkoutBlock
    tip: str
```

**Rest-day note:** when `rest_day` is `true`, `AdaptiveWorkoutBlock` returns
`exercises: []`, `reason` explaining recovery, and `confidence` reflecting data
volume — mirroring how `programs.today_workout` returns `{rest_day: true}` but in
the richer shape.

### 6.4 TypeScript types (proposed — add to `frontend/src/api/types.ts`)

```ts
export type Confidence = 'low' | 'medium' | 'high'
export type WorkoutAction = 'start' | 'increase' | 'hold' | 'reduce' | 'deload'
export type Direction = 'up' | 'down' | 'flat'

export interface MealPayload {
  name: string
  kcal: number
  category: MealCategory
  protein_g?: number
  carbs_g?: number
  fat_g?: number
}

export interface MealScoreComponents {
  macro_fit: number
  recency: number
  frequency: number
  adherence: number
  category_fit: number
  favorite: number
}

export interface AdaptiveMealSuggestion {
  name: string
  category: MealCategory
  kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
  portion: number
  score: number
  components: MealScoreComponents
  reason: string
  history_basis: string
  confidence: Confidence
  logged_count: number
  last_eaten_at?: string | null
  meal_payload: MealPayload
}

export interface NextMealHint {
  predicted_category: MealCategory
  predicted_time: string
  suggested_kcal: number
}

export interface MealHistoryBasis {
  window_days: number
  days_observed: number
  total_meals: number
  distinct_foods: number
  adherent_days: number
}

export interface AdaptiveMealsBlock {
  version: string
  algorithm: string
  targets: Macros
  consumed: Macros
  remaining: Macros
  next_meal: NextMealHint
  history_basis: MealHistoryBasis
  confidence: Confidence
  suggestions: AdaptiveMealSuggestion[]
}

export interface LastPerformance {
  date: string
  weight: number
  reps: number
  rpe?: number
  sets: number
  e1rm: number
}

export interface WeightChange {
  weight_delta_kg: number
  reps_delta: number
  direction: Direction
}

export interface E1rmTrendMini {
  first: number
  last: number
  direction: Direction
}

export interface AdaptiveExerciseRec {
  exercise_id: number
  name: string
  action: WorkoutAction
  suggested_weight?: number | null
  target_sets: number
  target_reps: string
  target_rpe?: number | null
  deload: boolean
  last_performance?: LastPerformance | null
  change: WeightChange
  e1rm_trend?: E1rmTrendMini | null
  confidence: Confidence
  reason: string
  history_basis: string
}

export interface WorkoutAdherence {
  sessions_last_14d: number
  scheduled_days_per_week: number
  consistency: 'on_track' | 'inconsistent' | 'returning'
}

export interface AdaptiveWorkoutBlock {
  version: string
  algorithm: string
  rest_day: boolean
  program_day_id?: number
  name?: string
  deload: boolean
  confidence: Confidence
  adherence?: WorkoutAdherence
  reason: string
  exercises: AdaptiveExerciseRec[]
}

export interface AdaptiveRecommendation {
  version: string
  algorithm: string
  generated_at: string
  meals: AdaptiveMealsBlock
  workout: AdaptiveWorkoutBlock
  tip: string
}
```

Reuses the existing `Macros` and `MealCategory` types already in `types.ts`.

### 6.5 `endpoints.ts` additions (proposed)

```ts
export const recommendations = {
  today: () => http.get<RecommendationsToday>('/recommendations/today'),
  adaptive: () => http.get<AdaptiveRecommendation>('/recommendations/adaptive'),
  meals: (category?: MealCategory, limit = 3) =>
    http.get<AdaptiveMealsBlock>(`/recommendations/meals${toQuery({ category, limit })}`),
  workout: (programDayId?: number) =>
    http.get<AdaptiveWorkoutBlock>(`/recommendations/workout${toQuery({ program_day_id: programDayId })}`),
}
```

---

## 7. Backward compatibility

* `/api/recommendations/today`, `/api/programs/today`, `/api/nutrition/today`
  keep their exact current shapes and behavior (the smoke/engine/hardening suites
  that assert those shapes stay green).
* `programs.today_workout` and `nutrition.nutrition_today` are **not** modified;
  the adaptive engine calls them (or their building blocks) but never mutates
  them.
* All new fields are additive; no field is renamed or removed.

---

## 8. Constants & tunables (single source, with citations)

Proposed home: a `# --- adaptive engine tunables ---` block in
`app/ml/adaptive.py` (I/O-free) plus reuse of `app/training/params.py`.

| Constant | Value | Meaning | Source |
| --- | --- | --- | --- |
| `RECOMMENDATION_VERSION` | `"adaptive-v1"` | audit id | — |
| `MEAL_WINDOW_DAYS` | 30 | food history window | matches current `nutrition._fetch_history_meals` |
| `RECENCY_HALF_LIFE_DAYS` | 14 | recency decay | design |
| `FREQ_SMOOTHING` | 3 | frequency smoothing K | design |
| `KCAL_FIT_FLOOR` | 0.6 | min macro-fit multiplier for size | design |
| `TIME_FIT_WINDOW_MIN` | 90 | ± minutes for time-fit | mirrors `coach` typical-time snap (120) |
| `W_M/W_A/W_R/W_F/W_T/W_FAV` | 0.35/0.20/0.15/0.15/0.15/+0.05 | meal weights | design |
| `KCAL_LOW / KCAL_HIGH` | 0.90 / 1.10 | adherent-day kcal band | design |
| `PROTEIN_MIN` | 0.90 | adherent-day protein floor | [MORTON] protein priority |
| `MIN_DAYS_FOR_ADHERENCE` | 5 | before adherence counts | design |
| `PORTION_MIN / MAX` | 0.5 / 2.0 | serving scaling clamp | design |
| `MMR_LAMBDA` | 0.5 | diversity penalty | Carbonell & Goldstein MMR |
| `TIE_EPSILON` | 0.02 | score-tie band for rotation | design |
| `MEAL_HIGH_CONF_DAYS / FOODS` | 14 / 8 | high confidence | design |
| `WORKOUT_LOOKBACK_SESSIONS` | 5 | recent sessions read | design |
| `STALL_SESSIONS_FOR_DELOAD` | 3 | stalls → deload | `params.LINEAR_STALL_SESSIONS` = 3 [RFIT-BBR] |
| `E1RM_REGRESS_PCT` | 0.05 | e1RM drop → deload | [RP-VOL] MRV regression signal |
| `HIGH_RPE_MARGIN` | 1.5 | RPE over target = fatigue | [SBS-RIR] |
| `EASY_RPE_MARGIN` | 2.0 | ≥2 RIR beyond target → double jump | [SBS-RIR] |
| `increment` (upper/lower) | 1.25 / 2.5 kg | load step | `params.LINEAR_INCREMENT_KG` [RFIT-BBR] |
| `DELOAD_LOAD_FRACTION` | 0.90 | deload load cut | `params.DELOAD_LOAD_FRACTION` [RP-VOL] |
| `LAYOFF_DAYS` | 14 | gap → resume-safe | design |
| `LAYOFF_LOAD_FRACTION` | 0.93 | return-from-layoff cut | design |
| `WORKOUT_HIGH_CONF_SESSIONS` | 4 | high confidence | design |

Citations (`[RFIT-BBR]`, `[SBS-RIR]`, `[RP-VOL]`, `[MORTON]`) are already defined
in `docs/TRAINING-SCIENCE.md` and `app/training/params.py`.

---

## 9. Implementation map (responsibilities)

```
app/ml/adaptive.py            (NEW, I/O-free, unit-testable — like coach.py)
  • tunable constants (§8) with citations
  • _norm(name), tokens(name), jaccard(a,b), cosine(u,v), stable_hash(key)
  • score_food(candidate, gap, budget, predicted_category, now, adherent_days) -> (score, components)
  • diversify(candidates, top_n) -> list            # MMR + category/name rules
  • portion_factor(base_kcal, budget) -> float
  • decide_progression(prescription, sessions, e1rm_ctx, layoff_days) -> ExerciseDecision
      (returns action, weight, reps, sets, deload, change, reason-kind)
  • confidence_meal(...) / confidence_workout(...)

app/services/adaptive.py      (NEW, orchestration + per-user data access)
  • adaptive_meals(db, user)   -> AdaptiveMealsBlock dict
      - reuse nutrition.active_macro_targets / goal_target_kcal / _fetch_* 
      - reuse coach.predict_next_meal_detailed for next_meal + typical kcal
      - compute adherent_days; aggregate candidates; score; diversify; build reasons
  • adaptive_workout(db, user, program_day_id=None) -> AdaptiveWorkoutBlock dict
      - reuse programs.active_program / weekly_schedule / low_rep / rep parsing
      - reuse performance.exercise_performance / best_recent_e1rm / suggested_weight / round_to_increment
      - next-in-rotation day selection; per-exercise decide_progression; reasons
  • adaptive_today(db, user) -> AdaptiveRecommendation dict  (+ tip)
  • _build_tip(meals_block, workout_block) -> str            (data-grounded)

app/routes/recommendations.py (MODIFY — add 3 GET routes; keep /today)
app/schemas.py                (MODIFY — add response models from §6.3; optional response_model=)

frontend/src/api/types.ts     (MODIFY — add types from §6.4)
frontend/src/api/endpoints.ts (MODIFY — add recommendations.adaptive/meals/workout)
frontend/src/api/mock.ts      (MODIFY — add mock responses if the mock client backs tests)

tests/test_adaptive.py        (NEW — matrix in §11)
```

Reused, **unchanged** helpers: `performance.suggested_weight`,
`performance.round_to_increment`, `performance.best_recent_e1rm`,
`performance.exercise_performance`, `programs.low_rep`, `programs.weekly_schedule`,
`nutrition.active_macro_targets`, `nutrition.goal_target_kcal`,
`coach.predict_next_meal_detailed`, `coach.analyze_patterns`,
`params.LINEAR_INCREMENT_KG`, `params.DELOAD_LOAD_FRACTION`,
`params.LINEAR_STALL_SESSIONS`.

---

## 10. Exact files to modify

**Backend**

| File | Change |
| --- | --- |
| `app/ml/adaptive.py` | **NEW** — pure scoring/decision functions + tunables (§8, §9). |
| `app/services/adaptive.py` | **NEW** — `adaptive_meals`, `adaptive_workout`, `adaptive_today`, `_build_tip`. |
| `app/routes/recommendations.py` | **MODIFY** — add `GET /adaptive`, `/meals`, `/workout`; keep `/today`. |
| `app/schemas.py` | **MODIFY** — add models from §6.3 (used as `response_model=` / return typing). |
| `app/training/params.py` | **OPTIONAL** — only if you prefer to co-locate the version id / reuse constants; not required (constants can live in `app/ml/adaptive.py`). |

**Frontend**

| File | Change |
| --- | --- |
| `frontend/src/api/types.ts` | **MODIFY** — add interfaces from §6.4. |
| `frontend/src/api/endpoints.ts` | **MODIFY** — add `recommendations.adaptive/meals/workout`. |
| `frontend/src/api/mock.ts` | **MODIFY** — add mock payloads if the mock client is used by FE tests. |
| `frontend/src/pages/Dashboard.tsx` | **OPTIONAL** — surface adaptive reasons/confidence on Today. |
| `frontend/src/pages/Nutrition.tsx` | **OPTIONAL** — render `suggestions[].reason` + one-tap `meal_payload` log. |
| `frontend/src/pages/Workout.tsx` | **OPTIONAL** — show per-exercise `action`/`change`/`deload`/`reason`. |

**Tests**

| File | Change |
| --- | --- |
| `tests/test_adaptive.py` | **NEW** — full matrix (§11). |
| `tests/test_engine.py` | **OPTIONAL** — add a couple of `/recommendations/adaptive` shape asserts. |

No changes to `app/models.py`, `alembic/`, or any log/route touching persistence.

---

## 11. Test matrix

> Follows existing conventions: `TestClient(app)`, temp SQLite via `FITPATH_DB`,
> `csrf_headers`, `make_user`, `put_profile`, per-user isolation, "never 500".

### 11.1 Pure unit (no DB) — `app/ml/adaptive.py`

| # | Test | Assert |
| --- | --- | --- |
| U1 | `cosine` basics | orthogonal→0, identical→1, zero-vector→0. |
| U2 | Recency decay | today→1.0; 14 d→0.5±ε; 28 d→0.25±ε; monotonic decreasing. |
| U3 | Frequency saturation | n=1→0.25, 3→0.5, 9→0.75; monotone; bounded < 1. |
| U4 | Macro-fit direction | protein-only gap ranks lean-protein food above a fat bomb. |
| U5 | `kcal_fit` temper | equal-macro-shape foods: the one nearer budget scores higher. |
| U6 | Adherence fraction | food on 4/5 adherent days → A=0.8; 0 adherent days → A=0.5 neutral. |
| U7 | Portion clamp | budget 300 / base 600 → 0.5; budget 1500 / base 600 → 2.0; base 0 → 1.0. |
| U8 | Diversify | 3 rice bowls in → ≤ 2 same-category out; near-dup names dropped. |
| U9 | Tie rotation | equal scores rotate deterministically by frozen date; stable across calls. |
| U10 | `decide_progression` increase | top_reps≥high & rpe≤target & sets≥target → `increase`, +increment, reps=low. |
| U11 | hold-in-range | reps inside range → `hold`, same weight, reps+1 (≤high). |
| U12 | repeat then reduce | 1st sub-low miss → `hold` same weight; 2nd consecutive → `reduce` −increment. |
| U13 | deload on stalls | 3 consecutive stalls → `deload`, 0.90×weight, `deload=true`. |
| U14 | deload on e1RM regress | last e1RM ≤ 0.95×recent best → `deload`. |
| U15 | deload on high RPE | last 2 sessions rpe≥target+1.5 & reps<low → `deload`. |
| U16 | easy → double jump | rpe ≤ target−2 at top of range → +2×increment. |
| U17 | layoff resume-safe | gap > 14 d → `hold`, 0.93×weight, reps=low, not counted as stall. |
| U18 | cold start | no sessions → `start`, weight = e1RM-derived or None. |
| U19 | confidence thresholds | meal & workout confidence bins match §4.8/§5.5 boundaries. |

### 11.2 Meals — service/API — `/api/recommendations/meals`

| # | Test | Assert |
| --- | --- | --- |
| M1 | Shape/version | keys present; `version="adaptive-v1"`, `algorithm` set; ≤ `limit` suggestions. |
| M2 | Cold start | new profile, 0 meals → curated fallbacks, `confidence="low"`, `history_basis` mentions no history; **200 not 500**. |
| M3 | Macro-adaptive | after logging a high-carb day with big protein gap, top pick's `components.macro_fit` high and protein-dense. |
| M4 | Recency | same food logged today vs 25 d ago → recent instance's `recency` higher. |
| M5 | Frequency | food logged 8× outranks a 1× food when other signals equal. |
| M6 | Adherence learns | seed adherent vs blow-out days; a food only on adherent days outranks an equal food only on blow-out days. |
| M7 | Diversify | seed 5× "chicken & rice" + others → not 3 identical picks; ≤ 2 per category. |
| M8 | Exclude eaten-today | a food already logged today is absent from suggestions. |
| M9 | Portion scaling | tiny remaining budget → `portion < 1`; `meal_payload` macros = base × portion (rounded). |
| M10 | `meal_payload` round-trips | POST the payload to `/api/logs/meals` → 200 and it validates against `MealIn`. |
| M11 | Category filter | `?category=breakfast` returns only breakfast-eligible picks (or documented fallback). |
| M12 | Determinism | two calls same day → identical ordering & scores. |
| M13 | Explanations | every suggestion has non-empty `reason` + `history_basis`; `components` sums are consistent with `score`. |
| M14 | No plan | no active nutrition plan → still 200 using profile-derived targets. |
| M15 | Missing profile | 400 (mirror `nutrition`), not 500. |

### 11.3 Workout — service/API — `/api/recommendations/workout`

| # | Test | Assert |
| --- | --- | --- |
| W1 | Shape/version | keys + version/algorithm; `exercises[]` items carry all §6.3 fields. |
| W2 | Cold start | program but no sets → every exercise `action="start"`, `suggested_weight` null, `confidence="low"`; 200. |
| W3 | Increase | log top-of-range @ ≤ target RPE across a session → `action="increase"`, `change.direction="up"`, weight +increment. |
| W4 | Hold in range | log mid-range reps → `action="hold"`, `weight_delta_kg=0`, `reps_delta≥0`. |
| W5 | Reduce | two consecutive sub-low sessions → `action="reduce"`, negative `weight_delta_kg`. |
| W6 | Deload (stall) | 3 stalled sessions → `deload=true`, `action="deload"`, ~0.90×; session `deload` true if majority. |
| W7 | Deload (e1RM drop) | descending e1RM ≥5% → `deload=true`. |
| W8 | Layoff | last session > 14 d ago → `reason` mentions resuming; weight ≈ 0.93×; not flagged stall/deload. |
| W9 | `last_performance` | equals the most recent working top set (warm-ups excluded). |
| W10 | Rest day | scheduled rest → `rest_day=true`, `exercises=[]`, recovery `reason`. |
| W11 | Day override | `?program_day_id=` forces that day's exercises. |
| W12 | Next-in-rotation | after completing day 0, adaptive day = day 1. |
| W13 | Determinism | two calls same day → identical output. |
| W14 | Confidence | 1 session→low, 2–3→medium, ≥4→high. |
| W15 | Adherence block | `sessions_last_14d`, `consistency` computed; inconsistent user → `"inconsistent"`/`"returning"`. |

### 11.4 Unified envelope — `/api/recommendations/adaptive`

| # | Test | Assert |
| --- | --- | --- |
| A1 | Shape | `{version, algorithm, generated_at, meals, workout, tip}`; sub-blocks match M1/W1. |
| A2 | Tip grounded | `tip` references real numbers (kcal/protein left and/or the lead lift). |
| A3 | Empty-state never 500 | fresh profile → 200 with cold-start meals + `rest_day`/`start` workout. |
| A4 | Back-compat | `/recommendations/today` shape unchanged (`{workout, nutrition, tip}`). |

### 11.5 Isolation & security (extend `test_review_hardening` style)

| # | Test | Assert |
| --- | --- | --- |
| I1 | Per-user meals | Bob's `/recommendations/meals` never contains Alice's foods. |
| I2 | Per-user workout | Bob's `/recommendations/workout` reflects only his sets/program. |
| I3 | Auth required | unauthenticated GET → 401. |
| I4 | Determinism ≠ leakage | two users with identical logs still isolated (no shared cache). |

### 11.6 Regression

* Re-run `test_smoke`, `test_engine`, `test_final_review`, `test_review_hardening`
  — all must stay green (the additive endpoints must not perturb existing shapes,
  and `/today` must be byte-compatible).

---

## 12. DB migration assessment

**No migration is required for v1.** Every signal is computed from existing
columns:

* meals: `meal_log.{name, category, kcal, protein_g, carbs_g, fat_g, eaten_at, favorite}`,
* targets: `nutrition_plan` / `profile` (existing derivation),
* workouts: `set_log.{weight, reps, rpe, is_warmup}`, `workout_session.{date, program_day_id}`,
* prescription: `program_exercise.{target_sets, target_reps, target_rpe, progression}`.

Anti-repetition and diversity are achieved **within a response** (MMR + exclude
eaten-today) and **across days** via a date-seeded deterministic rotation — no
persisted "suggestion history" table needed.

**The only feature that would ever need a migration** is *historically-accurate
adherence* (a per-day snapshot of the user's targets), e.g. a
`daily_target_snapshot(user_id, day, kcal, protein_g, carbs_g, fat_g)` table. v1
deliberately approximates with current targets to stay migration-free; this is
documented in §2 and can be revisited if targets are found to churn often.

---

## 13. Edge-case catalog

| Case | Handling |
| --- | --- |
| No meals logged ever | curated fallbacks, `confidence="low"`, honest `history_basis`. |
| Meals without macros (`protein_g` null) | treated as 0 for the vector; macro-fit still defined; food not penalized to −∞. |
| All macros already met (gap = 0) | `‖g‖=0` ⇒ macro-fit 0 for all; ranking falls back to recency/frequency/adherence; `reason` says "you've hit today's macros — a light option." |
| Remaining kcal ≤ 0 (over budget) | `portion=1.0`, suggest lower-kcal picks; `reason` notes being over target. |
| Single food dominates history | frequency saturates (< 1) and MMR/rotation prevent 3 identical picks. |
| Exercise never logged but program exists | `start` with e1RM-derived (or null) weight. |
| Warm-up-only session | ignored (working-set filter), treated as no working data. |
| Bodyweight sets (`weight=0`) | excluded from load progression (matches `performance` PR rules); reps-only note. |
| Calendar gap (missed weeks) | resume-safe (§5.3); never a stall/deload. |
| e1RM unreliable (high-rep sets) | reps capped at 10 by `performance._e1rm` (existing). |
| No active program | workout block `rest_day=true` with `reason` to generate a program. |
| Missing profile | `400` (never a silent default, never 500). |
| Two calls same day | identical output (determinism tests M12/W13/A-level). |

---

## 14. How this fixes the stated problems

* **"Build on what they've already done"** — meals rank the user's *own* logged
  foods; workouts progress from the user's *own* last sets.
* **"Continuously improve from history"** — the adherence signal literally learns
  which foods coincide with on-target days; double progression compounds load as
  performance improves; `confidence` rises as data accrues.
* **"Coherent adaptive feedback loop"** — one versioned envelope; meals react to
  the day's remaining gap and to logging outcomes; workouts react to set outcomes,
  fatigue, stalls, and layoffs.
* **"Explain how history changed the recommendation"** — `reason`,
  `history_basis`, per-component `components`, `last_performance`, and `change`
  make every suggestion self-documenting.
* **"Non-LLM / not AI"** — fully deterministic, offline, published formulas,
  surfaced under `/api/recommendations/*`.
