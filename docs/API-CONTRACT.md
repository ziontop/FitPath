# FitPath — API Contract (v1)

Shared source of truth for the **backend** (FastAPI) and **frontend** (React + Vite) tracks.
Build against this so both sides can progress in parallel. If a change is needed, update this
doc first, then both sides.

Base URL: **`/api`**. All bodies are JSON. Timestamps are ISO-8601 (`2026-07-02T14:30:00`);
dates are `YYYY-MM-DD`. Mass in **kg**, height in **cm** (a `units` preference affects display only).

---

## 1. Auth & sessions (httpOnly cookies + CSRF)

- On **register**/**login**, the server sets two cookies:
  - `fitpath_session` — **httpOnly**, `SameSite=Lax`, `Secure` in prod. Opaque session id (server-side store). Not readable by JS.
  - `fitpath_csrf` — **readable by JS** (not httpOnly), random token bound to the session.
- The frontend must send `credentials: 'include'` on every request.
- For every **state-changing** request (`POST`/`PUT`/`PATCH`/`DELETE`), the frontend must echo the CSRF
  token in header **`X-CSRF-Token`**; the server validates it against `fitpath_csrf` (double-submit).
- Unauthenticated access to a protected route → **401**. Missing/invalid CSRF on a mutation → **403**.

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/auth/register` | `{email, username, password}` | `201 {user}` + sets cookies |
| POST | `/api/auth/login` | `{identifier, password}` (identifier = email or username) | `200 {user}` + sets cookies |
| POST | `/api/auth/logout` | — | `204`, clears session |
| GET | `/api/auth/me` | — | `200 {user}` or `401` |

`user` = `{ id, email, username, created_at }`. Passwords hashed with **argon2** (pwdlib). Min length 8.

---

## 2. Enums

- `sex`: `male | female`
- `activity_level`: `sedentary | light | moderate | active | very_active`
- `nutrition_goal` (a.k.a. `goal`): `lose | maintain | gain`
- `training_goal`: `powerlifting | hypertrophy | maingain`
- `experience_level`: `beginner | intermediate | advanced`
- `equipment`: `full_gym | home_basic | bodyweight`
- `meal_category`: `breakfast | lunch | dinner | snack`
- `intensity`: `light | moderate | vigorous`
- `exercise_category`: `compound | isolation`
- `units`: `metric | imperial`

---

## 3. Profile

1:1 with the user. `GET` returns `404` if not yet created.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/profile` | current user's profile |
| PUT | `/api/profile` | upsert |

Profile body:
```jsonc
{
  "name": "Zina",
  "sex": "female",
  "age": 24,
  "height_cm": 168,
  "weight_kg": 62,
  "activity_level": "moderate",
  "goal": "maintain",            // nutrition goal
  "training_goal": "hypertrophy",
  "experience_level": "intermediate",
  "days_per_week": 4,
  "equipment": "full_gym",
  "units": "metric",
  "wake_time": "07:00",
  "water_goal_ml": 2500,
  "step_goal": 8000,
  "exercise_goal_min": 45
}
```

---

## 4. Nutrition / health logs (user-scoped, full CRUD)

Resource names are plural. Each row belongs to the authenticated user. Unless noted, `POST` returns
`200 {id, ...row}`; `GET` list returns `{items: [...]}`; `DELETE` returns `{ok: true}`.

### Meals — `/api/logs/meals`
| Method | Path | Body / Query |
|---|---|---|
| POST | `/api/logs/meals` | `{name, kcal, category, protein_g?, carbs_g?, fat_g?, eaten_at?}` |
| GET | `/api/logs/meals?date=YYYY-MM-DD` | list for a day (default today) |
| GET | `/api/logs/meals/recent?limit=10` | `{recent, favorites, frequent}` for quick re-log |
| PUT | `/api/logs/meals/{id}` | same shape as POST |
| DELETE | `/api/logs/meals/{id}` | |
| POST | `/api/logs/meals/{id}/favorite` | toggles; `{ok, favorite}` |

### Activities — `/api/logs/activities`
`{activity, minutes, intensity, done_at?}` — POST/GET(list)/PUT/DELETE.

### Sleep — `/api/logs/sleep`
`{hours, wake_time, logged_for?}` — POST/GET/PUT/DELETE.

### Steps — `/api/logs/steps` (one row per day)
`{steps, logged_for?}` — POST(upsert per day)/GET/DELETE.

### Water — `/api/logs/water`
`{ml, logged_at?}` — POST/GET/DELETE.

### Weight — `/api/logs/weight` (one row per day)
`{weight_kg, logged_for?}` — POST(upsert per day)/GET/PUT/DELETE.

---

## 5. Exercises catalog

Seeded reference data (with a flag for SBD main lifts). Optional per-user custom exercises.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/exercises?muscle=&equipment=&q=&limit=&offset=` | filter/search catalog |
| GET | `/api/exercises/{id}` | one |
| POST | `/api/exercises` | create custom (user-owned) |

`exercise` = `{ id, name, category, primary_muscle, secondary_muscles[], equipment, is_main_lift, is_custom }`.

---

## 6. Workouts & performance tracking

A **workout session** has many **set logs** (weight × reps × RPE). This is the core performance data.

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/api/workouts` | `{date?, name?, program_day_id?, notes?}` → session |
| GET | `/api/workouts?from=&to=&limit=&offset=` | list sessions (summary) |
| GET | `/api/workouts/{id}` | session incl. `sets[]` |
| PUT | `/api/workouts/{id}` | edit name/notes/date |
| DELETE | `/api/workouts/{id}` | cascade sets |
| POST | `/api/workouts/{id}/sets` | `{exercise_id, weight, reps, rpe?, is_warmup?, set_index?}` → set |
| PUT | `/api/workouts/{id}/sets/{set_id}` | edit |
| DELETE | `/api/workouts/{id}/sets/{set_id}` | |

Analytics:
| Method | Path | Response |
|---|---|---|
| GET | `/api/performance/summary` | `{total_volume, sessions_count, prs_count, e1rm_highlights[]}` |
| GET | `/api/performance/prs` | best e1RM & top set per exercise |
| GET | `/api/performance/exercise/{exercise_id}` | `{history[], e1rm_trend[], volume_trend[], best}` |
| GET | `/api/performance/volume?from=&to=` | weekly sets/volume per muscle group |

`e1RM` computed server-side (Epley default). PRs = max estimated 1RM and max weight per exercise.

---

## 7. Workout program (generated plan)

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/api/programs/generate` | `{training_goal?, days_per_week?, experience?, equipment?}` (defaults from profile) → program |
| GET | `/api/programs` | list user's programs (summary) |
| GET | `/api/programs/active` | active program w/ `days[]` → each `exercises[]` |
| GET | `/api/programs/{id}` | full program |
| PUT | `/api/programs/{id}` | edit / `{active: true}` to activate |
| DELETE | `/api/programs/{id}` | |
| GET | `/api/programs/today` | today's recommended session (or `{rest_day: true}`) with target sets/reps/rpe/rest, plus suggested working weights derived from performance history |

Shapes:
```jsonc
// program
{ "id":1, "name":"Hypertrophy Upper/Lower", "training_goal":"hypertrophy",
  "split_type":"upper_lower", "days_per_week":4, "active":true,
  "days":[ { "id":10, "day_index":0, "name":"Upper A",
             "exercises":[ { "exercise_id":3, "name":"Bench Press", "target_sets":4,
                             "target_reps":"6-10", "target_rpe":8, "rest_seconds":150,
                             "progression":"double_progression" } ] } ] }
```

---

## 8. Nutrition plan (generated) & daily targets

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/api/nutrition/plan/generate` | derive targets from profile (TDEE + goal) → plan |
| GET | `/api/nutrition/plan/active` | active plan |
| GET | `/api/nutrition/today` | `{targets:{kcal,protein_g,carbs_g,fat_g}, consumed:{...}, remaining:{...}, meal_suggestions:[...]}` |

```jsonc
// nutrition plan
{ "id":1, "goal":"gain", "target_kcal":2800, "protein_g":140, "carbs_g":340,
  "fat_g":78, "meals_per_day":4, "active":true }
```

---

## 9. Unified recommendations & AI coach

| Method | Path | Response |
|---|---|---|
| GET | `/api/recommendations/today` | `{ workout: <programs/today>, nutrition: <nutrition/today>, tip: "..." }` |
| GET | `/api/recommendations/adaptive` | Adaptive envelope `{version, algorithm, generated_at, meals, workout, tip}` (see §9a) |
| GET | `/api/recommendations/meals?category=&limit=` | Adaptive meal picks — `AdaptiveMealsBlock` (see §9a) |
| GET | `/api/recommendations/workout?program_day_id=` | Adaptive workout — `AdaptiveWorkoutBlock` (see §9a) |
| GET | `/api/ai/insights` | eating + training pattern analysis |
| GET | `/api/ai/predict-next-meal` | next meal time/category/kcal + macro gap + food picks |
| GET | `/api/ai/recommend-foods` | foods ranked by macro-fit |
| POST | `/api/ai/chat` | `{message}` → `{reply, intent, chips[]}` (extended to answer training questions) |
| POST | `/api/ai/parse-log` | `{text}` → structured meal payload |

`/api/recommendations/today` keeps its exact legacy shape (backward-compatible).

---

## 9a. Adaptive recommendations (additive, deterministic, non-LLM)

A history-based engine that builds meal + workout suggestions from the user's own
logged rows and explains **how history changed the recommendation**. Every
payload carries `version:"adaptive-v1"` and `algorithm:"history-adaptive-deterministic"`.
All queries are user-scoped; a missing profile → **400** (mirrors `/nutrition/today`).
No DB migration is required (derived from existing tables only). Full algorithm,
constants and worked examples live in **`docs/ADAPTIVE-RECOMMENDATIONS.md`**.

| Method | Path | Query | Powers |
|---|---|---|---|
| GET | `/api/recommendations/adaptive` | — | Today screen (meals + workout + tip) |
| GET | `/api/recommendations/meals` | `category?` (`breakfast\|lunch\|dinner\|snack`), `limit?` (1–10, default 3) | Nutrition screen |
| GET | `/api/recommendations/workout` | `program_day_id?` (force a specific day) | Workout screen |

```jsonc
// GET /api/recommendations/adaptive
{
  "version": "adaptive-v1",
  "algorithm": "history-adaptive-deterministic",
  "generated_at": "2026-07-14T18:40:00",
  "meals":   { /* AdaptiveMealsBlock */ },
  "workout": { /* AdaptiveWorkoutBlock */ },
  "tip": "Today is Push A — work up to Bench at RPE 8 (try 83.75 kg). You have 1200 kcal and 45 g protein left; a chicken-&-rice dinner closes most of it."
}
```

```jsonc
// AdaptiveMealsBlock  (GET /api/recommendations/meals)
{
  "version": "adaptive-v1", "algorithm": "history-adaptive-deterministic",
  "targets":   { "kcal": 2600, "protein_g": 195, "carbs_g": 300, "fat_g": 75 },
  "consumed":  { "kcal": 1400, "protein_g": 150, "carbs_g": 150, "fat_g": 45 },
  "remaining": { "kcal": 1200, "protein_g": 45,  "carbs_g": 150, "fat_g": 30 },
  "next_meal": { "predicted_category": "dinner", "predicted_time": "2026-07-14T19:05", "suggested_kcal": 600 },
  "history_basis": { "window_days": 30, "days_observed": 21, "total_meals": 27, "distinct_foods": 9, "adherent_days": 5 },
  "confidence": "high",
  "suggestions": [ {
    "name": "Chicken & rice", "category": "dinner",
    "kcal": 620, "protein_g": 52, "carbs_g": 60, "fat_g": 14, "portion": 1.0,
    "score": 0.878,
    "components": { "macro_fit": 0.903, "recency": 0.952, "frequency": 0.727, "adherence": 0.8, "category_fit": 1.0, "favorite": 0.0 },
    "reason": "Fits your remaining 45g protein / 150g carbs gap, a go-to dinner you've logged 8×.",
    "history_basis": "From 27 meals over 21 days · eaten 8× (last 1 day ago) · on 4 of 5 logged day(s) on-target.",
    "confidence": "high", "logged_count": 8, "last_eaten_at": "2026-07-13T19:05",
    "meal_payload": { "name": "Chicken & rice", "kcal": 620, "category": "dinner", "protein_g": 52, "carbs_g": 60, "fat_g": 14 }
  } ]
}
```

```jsonc
// AdaptiveWorkoutBlock  (GET /api/recommendations/workout)
{
  "version": "adaptive-v1", "algorithm": "history-adaptive-deterministic",
  "rest_day": false, "program_day_id": 10, "name": "Push A",
  "deload": false, "confidence": "medium",
  "adherence": { "sessions_last_14d": 6, "scheduled_days_per_week": 4, "consistency": "on_track" },
  "reason": "Push A: work up to Bench Press at the prescribed RPE; loads below are adapted from your recent logs.",
  "exercises": [ {
    "exercise_id": 2, "name": "Bench Press",
    "action": "increase", "suggested_weight": 83.75,
    "target_sets": 4, "target_reps": "6-8", "target_rpe": 8.0, "deload": false,
    "last_performance": { "date": "2026-07-11", "weight": 82.5, "reps": 8, "rpe": 7.5, "sets": 4, "e1rm": 104.0 },
    "change": { "weight_delta_kg": 1.25, "reps_delta": -2, "direction": "up" },
    "e1rm_trend": { "first": 99.0, "last": 104.0, "direction": "up" },
    "confidence": "medium",
    "reason": "You hit 8 reps @ RPE 7.5 last time (top of range with reps to spare) — adding 1.25 kg and resetting to 6 reps.",
    "history_basis": "Based on your last 3 Bench Press session(s); e1RM 99.0 → 104.0 kg."
  } ]
}
```

- `action` ∈ `start | increase | hold | reduce | deload`; `confidence` ∈ `low | medium | high`;
  `direction` ∈ `up | down | flat`; `consistency` ∈ `on_track | inconsistent | returning`.
- Rest day → `{ rest_day: true, exercises: [], ... }`; no active program →
  `{ rest_day: false, exercises: [], reason: "No active program yet…" }`.
- Cold start / sparse history → documented starter fallbacks (`confidence: "low"`),
  never a silent empty result.

---

## 10. Insights (existing, now user-scoped)

`GET /api/insights/today | /circadian | /trends?days=N | /streaks | /achievements | /heatmap?days=N`.
Same shapes as today, but scoped to the authenticated user and extended to include workout streaks
(`workout_streak`) and a "Consistent Lifter" style achievement.

---

## 11. Admin / demo

| Method | Path | Notes |
|---|---|---|
| POST | `/api/admin/seed-demo?days=N` | seed the current user with realistic demo data |
| POST | `/api/admin/reset` | clear current user's logs (keep profile) |
| GET | `/api/health` | `{status:"ok"}` (public) |

---

## 12. Apple Health integration

A browser/PWA cannot read HealthKit directly. FitPath supports (1) manual Apple Health
`export.zip`/`export.xml` import and (2) an iOS Shortcut push of daily aggregates.
v1 imports only `steps`, `weight`, `sleep`, `water`, and `workouts` (mapped to activity logs);
it does not import dietary energy/macros.

All endpoints are under `/api/integrations/apple-health`. Cookie routes require the normal session
and CSRF header. The Shortcut route is bearer-only and ignores cookies.

### Manual export preview/import

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/integrations/apple-health/preview` | multipart `file` = `export.zip` or `export.xml` | `{filename,date_range,counts_by_type,units_detected,samples,warnings}`; no writes |
| POST | `/api/integrations/apple-health/import` | multipart `file` + `types` JSON array or repeated field (`steps\|weight\|sleep\|water\|workouts`) | `{batch_id,source:"export",status,date_range,results,totals}` |
| GET | `/api/integrations/apple-health/imports` | — | `{items:[batch...]}` |
| DELETE | `/api/integrations/apple-health/data` | optional `{types?,from?,to?}` | `{deleted,preserved_modified,provenance_removed}` |

Preview is stateless: the server parses and discards the upload. The browser must keep the selected
`File` and re-upload it to `/import`.

```jsonc
// POST /preview response
{
  "filename": "export.zip",
  "date_range": { "start": "2019-03-01", "end": "2026-07-14" },
  "counts_by_type": { "steps": 2557, "weight": 431, "sleep": 1103, "water": 6820, "workouts": 512 },
  "units_detected": { "weight": ["kg"], "water": ["mL", "fl_oz_us"] },
  "samples": {
    "steps": [{ "date": "2026-07-14", "value": 8432, "sources": ["iPhone"] }],
    "weight": [{ "date": "2026-07-14", "kg": 80.1 }],
    "sleep": [{ "wake_date": "2026-07-14", "hours": 7.25, "wake_time": "06:45" }],
    "water": [{ "date": "2026-07-14", "ml": 2100 }],
    "workouts": [{ "activity": "Running", "date": "2026-07-14", "minutes": 32, "intensity": "vigorous" }]
  },
  "warnings": []
}
```

```jsonc
// POST /import response
{
  "batch_id": 42,
  "source": "export",
  "status": "completed",
  "date_range": { "start": "2019-03-01", "end": "2026-07-14" },
  "results": {
    "steps": { "inserted": 2100, "updated": 12, "skipped": 445, "invalid": 0, "conflict": 3 },
    "weight": { "inserted": 420, "updated": 0, "skipped": 11, "invalid": 0, "conflict": 0 },
    "sleep": { "inserted": 1100, "updated": 0, "skipped": 3, "invalid": 0, "conflict": 0 },
    "water": { "inserted": 500, "updated": 0, "skipped": 0, "invalid": 0, "conflict": 0 },
    "workouts": { "inserted": 510, "updated": 0, "skipped": 2, "invalid": 0, "conflict": 0 }
  },
  "totals": { "inserted": 4630, "updated": 12, "skipped": 461, "invalid": 0, "conflict": 3 }
}
```

`conflict` means FitPath preserved a manual edit instead of overwriting it. `DELETE /data` also preserves
manually edited imported rows and removes only their provenance link.

### Shortcut token lifecycle and bearer push

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/integrations/apple-health/tokens` | `{name, expires_in_days?}` | `201 {id,name,prefix,token,created_at,expires_at}`; `token` shown once |
| GET | `/api/integrations/apple-health/tokens` | — | `{items:[{id,name,prefix,created_at,last_used_at,expires_at,revoked_at}]}`; never the secret |
| POST | `/api/integrations/apple-health/tokens/{id}/rotate` | — | metadata plus new one-time `token` |
| DELETE | `/api/integrations/apple-health/tokens/{id}` | — | `204` |
| POST | `/api/integrations/apple-health/shortcut` | JSON daily aggregates, `Authorization: Bearer fpk_...` | `{batch_id,applied,skipped}` |

Shortcut payload:
```jsonc
{
  "steps": [{ "date": "2026-07-14", "count": 8432 }],
  "weight": [{ "date": "2026-07-14", "kg": 80.1 }],
  "sleep": [{ "date": "2026-07-14", "hours": 7.5, "wake_time": "06:45" }],
  "water": [{ "date": "2026-07-14", "ml": 2100 }],
  "workouts": [{ "activity": "Running", "start": "2026-07-14T06:30:00-07:00",
    "end": "2026-07-14T07:02:00-07:00", "source": "Apple Watch",
    "minutes": 32, "intensity": "vigorous", "kcal": 320 }]
}
```

---

## 13. Error format

All errors: `{ "detail": "human-readable message" }` with status `400/401/403/404/409/422`.
Validation errors follow FastAPI's default 422 shape.

## 14. Notes for both tracks
- Frontend: use one API client wrapper that (a) sends `credentials:'include'`, (b) attaches
  `X-CSRF-Token` from the `fitpath_csrf` cookie on mutations, (c) redirects to login on 401.
- Backend: a `current_user` dependency enforces auth + scopes every query by `user_id`.
- During parallel dev, the backend runs on `http://127.0.0.1:8000` and the Vite dev server proxies
  `/api` there (configure `server.proxy` in `vite.config.ts`). No CORS needed with the proxy; if
  CORS is used instead, allow the Vite origin with `allow_credentials=True`.
