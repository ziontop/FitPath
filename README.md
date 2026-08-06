# FitPath

A multi-user fitness tracker **and** training/nutrition coach — a mobile-first
single-page app inspired by Strava, Apple Health and BetterMe, wrapped around an
evidence-based training engine.

Log meals (with macros), workouts (sets × reps × RPE), activity, sleep, steps,
water and bodyweight. FitPath turns that into maintenance calories (BMR/TDEE),
Apple-Health-style rings, an activity heatmap, strength/e1RM trends, weekly
volume vs research-backed landmarks, streaks, achievements, an auto-generated
training program + nutrition plan, and an offline rule-based **AI coach** that
answers both nutrition *and* training questions grounded in your real data.

---

## What it is

- **Multi-user** with secure auth: argon2 password hashing, httpOnly session
  cookies + double-submit CSRF, and strict per-user data isolation (every query
  is scoped to the authenticated user).
- **Tracking**: meals (category + protein/carbs/fat), activities, sleep, steps,
  water, weight, and full workout sessions with per-set weight/reps/RPE.
- **Apple Health import**: manual `export.zip`/`export.xml` preview → select → import,
  plus optional iOS Shortcut tap-to-sync for daily aggregates.
- **Workouts & performance**: estimated 1RM (Epley/Brzycki), PRs, per-exercise
  history + e1RM/volume trends, and weekly sets/volume per muscle vs MEV–MAV.
- **Program generation**: an evidence-based split per training goal
  (powerlifting → Upper/Lower, hypertrophy → PPL, maingain → Full-Body),
  scaled to your days/week and **equipment** (a home_basic lifter gets
  dumbbell/bodyweight variants instead of an all-barbell program).
- **Nutrition generation**: TDEE + goal delta → kcal target and per-kg macro
  targets, with meal suggestions drawn from your own logged foods.
- **Recommendations & AI coach**: next-meal prediction, macro-fit food picks,
  eating-pattern mining, and a chat coach that also covers strength progress,
  weekly volume, workout streak/consistency, maintenance, and surplus/deficit —
  all offline (no LLM, no API keys), grounded in *your* numbers.
- **LearnFlow design system UI**: mobile-first SPA with a bottom nav, activity
  rings, charts, an activity heatmap, badges, and a first-class **dark mode**.

The shared frontend/backend API is specified in **[`docs/API-CONTRACT.md`](docs/API-CONTRACT.md)**.

---

## Architecture

```
rhythm-fit/
├── app/                     # FastAPI backend
│   ├── main.py              # app + middleware (CSRF, CORS) + single-origin SPA serving
│   ├── db.py                # SQLAlchemy engine/session (NullPool + WAL for SQLite)
│   ├── models.py            # SQLAlchemy 2.0 typed models (user-scoped, cascading)
│   ├── schemas.py           # Pydantic v2 request/response schemas (match the contract)
│   ├── auth.py / deps.py / security.py   # argon2 auth, session cookies, CSRF middleware
│   ├── seed_exercises.py    # idempotent exercise catalog seeder
│   ├── routes/              # profile, logs, workouts, performance, programs,
│   │                        #   nutrition, insights, recommendations, ai, admin, exercises
│   ├── services/            # engine: programs, nutrition, performance, mapping, streaks
│   ├── ml/                  # calories (BMR/TDEE), circadian, coach (patterns/recs/chat)
│   └── training/params.py   # researched training constants (read-only)
├── alembic/                 # database migrations (alembic upgrade head)
├── frontend/                # React + Vite + TypeScript SPA (built to frontend/dist)
├── scripts/seed_demo.py     # (re)seed the 3 demo accounts with rich backdated data
├── tests/                   # pytest suites (smoke, engine, hardening, final-review)
└── docs/API-CONTRACT.md     # source-of-truth API contract
```

- **Backend**: FastAPI + SQLAlchemy 2.0 ORM + Alembic migrations, on SQLite.
  The engine uses `NullPool` (a fresh connection per request) with WAL +
  `busy_timeout` so a just-committed write is always visible on the next request
  (no stale read-after-write across pooled connections).
- **Frontend**: React 19 + Vite + TypeScript, Recharts for charts, one typed API
  client that sends `credentials: 'include'` and attaches `X-CSRF-Token` on
  mutations.
- **Single-origin serving**: `npm run build` compiles the SPA to
  `frontend/dist`; FastAPI mounts `/assets` and falls back to `index.html` for
  client-side routes, so the whole app runs from one origin (no CORS needed in
  production). `/api/*` always wins over the SPA fallback.

---

## How to run

Prerequisites: Python 3.14 (the repo ships a `.venv`) and Node.js (for the
frontend build).

```powershell
cd C:\Users\t-zinaokoye\projects\rhythm-fit

# 1. (First time only) install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend; npm install; cd ..

# 2. Build the SPA (produces frontend/dist)
cd frontend; npm run build; cd ..

# 3. Run the app (serves the built SPA + the API from one origin)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8137
```

Then open the printed URL — **<http://127.0.0.1:8137>** — in a browser.
Interactive API docs are at **<http://127.0.0.1:8137/docs>**.

> ⚠️ **Port note:** port **8000** is often already occupied on this machine, so
> the command above uses **8137**. If that port is busy too, pick any free port
> (`--port <N>`) and open the URL it prints.

`run.cmd` / `run.ps1` are convenience launchers, but they default to port 8000 —
prefer the explicit `--port` command above.

### Demo logins

Three ready-made accounts (all passwords are `FitPathDemo!<n>`):

| Username           | Password        | Persona                                              |
| ------------------ | --------------- | ---------------------------------------------------- |
| `alex_cut`         | `FitPathDemo!1` | Cutting + powerlifting, 4-day Upper/Lower, full gym  |
| `sam_bulk`         | `FitPathDemo!2` | Bulking + hypertrophy, 6-day PPL, full gym           |
| `jordan_maingain`  | `FitPathDemo!3` | Maingaining + inconsistent, home_basic (DB/bodyweight) |

To (re)create these accounts with fresh, deterministic, backdated data
(SBD/e1RM trends, meals, steps, sleep, weight — all persona-appropriate):

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py
```

The script is idempotent: it deletes any existing demo users (cascade) and
replays their history **through the live API**, then verifies each account
(login works, e1RM trends have multiple dated points, the heatmap shows workout
days, streaks are sensible). It seeds the real `fitpath.sqlite3` by default
(honours `FITPATH_DB` if set).

---

## Running tests

```powershell
# Backend (pytest)
.\.venv\Scripts\python.exe -m pytest -q

# Frontend (vitest) + type-checked build
cd frontend
npm test
npm run build
```

Backend tests are self-contained (each suite points `FITPATH_DB` at a temp file
before importing the app, so the shared `fitpath.sqlite3` is never touched).

Database migrations: `alembic upgrade head` (the app also creates tables on
startup for dev/tests).

---

## API overview

Base URL `/api`; JSON bodies; httpOnly session cookie + `X-CSRF-Token` on
mutations. Full details in **[`docs/API-CONTRACT.md`](docs/API-CONTRACT.md)**.

| Area | Endpoints (summary) |
| --- | --- |
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Profile | `GET/PUT /profile` |
| Logs | `/logs/meals`, `/logs/activities`, `/logs/sleep`, `/logs/steps`, `/logs/water`, `/logs/weight` (CRUD) |
| Exercises | `GET /exercises`, `GET /exercises/{id}`, `POST /exercises` |
| Workouts | `POST/GET/PUT/DELETE /workouts`, `.../sets` (weight × reps × RPE) |
| Performance | `/performance/summary`, `/performance/prs`, `/performance/exercise/{id}`, `/performance/volume` |
| Programs | `POST /programs/generate`, `/programs`, `/programs/active`, `/programs/today`, `/programs/{id}` |
| Nutrition | `POST /nutrition/plan/generate`, `/nutrition/plan/active`, `/nutrition/today` |
| Recommendations & AI | `/recommendations/today`, `/ai/insights`, `/ai/predict-next-meal`, `/ai/recommend-foods`, `POST /ai/chat`, `POST /ai/parse-log` |
| Insights | `/insights/today`, `/circadian`, `/trends`, `/streaks`, `/achievements`, `/heatmap` |
| Admin/health | `POST /admin/seed-demo`, `POST /admin/reset`, `GET /api/health` |
| Apple Health | `/integrations/apple-health/preview`, `/import`, `/imports`, `/data`, `/tokens`, `/shortcut` |

The **AI coach** (`app/ml/coach.py`) is a fully offline, rule-based engine:
pattern mining, a macro-fit food recommender, next-meal prediction, and a chat
router. Its macro targets come from your **active nutrition plan** (single source
of truth), and it answers training questions — strength/e1RM progress, weekly
volume vs MEV/MAV, workout streak, consistency, maintenance, and whether you're
eating enough for your goal — grounded in your logged workouts and performance.

---

## Known limitations

- **Bodyweight (weight = 0) sets** count toward weekly *set* totals per muscle
  but contribute **0 to volume** (kg × reps) and don't establish an e1RM/PR, so a
  bodyweight-only exercise won't appear in `/performance/prs`. `prs_count` and
  the `/prs` list are kept consistent (both exclude weight-0-only exercises).
- **Equipment substitution** swaps a template lift for a same-muscle alternative
  the user's equipment allows, but keeps the original when the catalog has no
  allowed option for that muscle — e.g. a *bodyweight*-only lifter may still see a
  barbell Overhead Press or dumbbell Lateral Raise where no bodyweight variant
  exists. (home_basic → dumbbell/bodyweight works fully.)
- **Strength exercise minutes** are an estimate (~3.5 min per working set, capped
  at 90 min/session), not measured time.
- **AI coach is rule-based/offline** (no LLM). It's accurate and private but not
  free-form conversational; unrecognized questions fall back to a capability hint.
- **Cycled program days** can repeat names (e.g. a 3-day Full-Body request yields
  `A / B / A`); `day_index` disambiguates them.
- **Next-meal prediction** snaps the predicted time to your typical time for the
  predicted category (keeping time and label consistent); with little history it
  falls back to a median-interval + hour-of-day heuristic.

## Apple Health integration

FitPath is a web app/PWA, so it **cannot read HealthKit directly** from Safari,
Chrome, or an installed PWA. There is no native iOS app or HealthKit entitlement
in v1.

Supported paths:

1. **Manual export import** — export Apple Health data from the Health app, upload
   `export.zip` or `export.xml`, preview counts by type, choose which types to
   import, then commit. The server is stateless between preview and import: the
   browser re-uploads the selected file and raw exports are not retained.
2. **iOS Shortcut tap-to-sync** — create a bearer token in Settings, paste it into
   a Shortcut, and POST daily aggregate JSON to
   `/api/integrations/apple-health/shortcut`. Use HTTPS outside localhost; this is
   user-initiated tap-to-sync, not background HealthKit delivery.

v1 imports **steps, body mass, sleep, water, and workouts** (workouts become
activity logs). It **does not import dietary energy or macros**. Imported data is
scoped to the signed-in user, processed by FitPath only, not used for ads or
third-party analytics, and can be deleted later. Deletion preserves rows you
manually edited after import.
