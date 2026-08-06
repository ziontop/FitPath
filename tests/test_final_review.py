"""Regression tests for the final-review pass.

Locks in the fixes shipped in this round so they can't silently regress:

* **Bug 1** — workout ``date`` is settable (POST + PUT persist a past date; the
  ``WorkoutIn.date`` annotation resolves to a real ``date``, not ``NoneType``).
* **Bug 2** — a fresh login is immediately visible to ``GET /api/auth/me`` across
  independent clients (NullPool: no stale WAL read-after-write).
* **Bug 3** — a logged strength workout counts as exercise: it shows on the
  heatmap, in exercise-minutes, and in the activity/any + workout streaks, and
  earns the minute/session-keyed badges.
* **Bug 4** — the AI coach's macro targets equal the active nutrition plan's.
* **Bug 5** — the coach answers training questions (strength, volume, streak,
  surplus/deficit) grounded in real data, with correct intent routing.
* **Bug 6** — a 2-day template cycles (A/B/A) to fill a 3-day request.
* **Bug 7** — ``performance/summary.prs_count == len(performance/prs items)`` even
  with bodyweight (weight=0) sets present.
* **Bug 8** — a home_basic lifter's program uses dumbbell/bodyweight, not barbell.
* **Bug 10** — ``/api/workouts?limit>200`` soft-clamps instead of 422.
* **Bug 11** — the superseded ``/api/insights/predict`` route is gone (404).
"""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ.setdefault("FITPATH_DB", _tmp.name)

import app.db as db_module  # noqa: E402

if os.environ["FITPATH_DB"] == _tmp.name:
    db_module.DB_PATH = Path(_tmp.name)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas import WorkoutIn, WorkoutUpdate  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("fitpath_csrf")
    return {"X-CSRF-Token": token} if token else {}


def make_user(client: TestClient, password: str = "password123") -> dict:
    uid = uuid.uuid4().hex[:10]
    r = client.post(
        "/api/auth/register",
        json={"email": f"{uid}@ex.com", "username": f"u{uid}", "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()["user"]


def put_profile(client: TestClient, **overrides) -> None:
    payload = {
        "name": "Test", "sex": "male", "age": 28, "height_cm": 178,
        "weight_kg": 80, "activity_level": "moderate", "goal": "maintain",
        "training_goal": "hypertrophy", "experience_level": "intermediate",
        "days_per_week": 4, "equipment": "full_gym", "units": "metric",
        "wake_time": "07:00",
    }
    payload.update(overrides)
    r = client.put("/api/profile", json=payload, headers=csrf_headers(client))
    assert r.status_code == 200, r.text


def exercise_id(client: TestClient, name: str) -> int:
    items = client.get("/api/exercises", params={"q": name}).json()["items"]
    match = next((e for e in items if e["name"].lower() == name.lower()), None)
    assert match, f"seeded catalog missing {name}"
    return match["id"]


# ---------------------------------------------------------------------------
# Bug 1 — workout date is settable
# ---------------------------------------------------------------------------
def test_workout_date_annotation_resolves_to_date():
    # The forward-ref annotation must include real ``date`` (not resolve to NoneType).
    for model in (WorkoutIn, WorkoutUpdate):
        ann = model.model_fields["date"].annotation
        args = getattr(ann, "__args__", None) or [ann]
        assert date in args, f"{model.__name__}.date annotation is {ann!r}"


def test_workout_date_backdating_post_and_put():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)

        past = (date.today() - timedelta(days=17)).isoformat()
        created = client.post(
            "/api/workouts", json={"date": past, "name": "Backdated"}, headers=h
        )
        assert created.status_code == 201, created.text
        wid = created.json()["id"]
        assert created.json()["date"] == past  # persisted, not coerced to today

        earlier = (date.today() - timedelta(days=30)).isoformat()
        updated = client.put(
            f"/api/workouts/{wid}", json={"date": earlier}, headers=h
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["date"] == earlier
        assert client.get(f"/api/workouts/{wid}").json()["date"] == earlier


# ---------------------------------------------------------------------------
# Bug 2 — fresh login immediately visible to /me across fresh clients
# ---------------------------------------------------------------------------
def test_login_then_me_succeeds_twenty_times():
    with TestClient(app) as setup:
        user = make_user(setup)  # tables + session store are shared via the temp DB

    # Each iteration is a brand-new client (fresh cookie jar / connection), just
    # like a browser logging in and immediately hitting /me. With NullPool the
    # just-committed session row is always visible on the next request.
    for i in range(20):
        client = TestClient(app)
        r = client.post(
            "/api/auth/login",
            json={"identifier": user["username"], "password": "password123"},
        )
        assert r.status_code == 200, f"login {i}: {r.status_code}"
        me = client.get("/api/auth/me")
        assert me.status_code == 200, f"/me {i}: {me.status_code} {me.text}"
        assert me.json()["user"]["id"] == user["id"]


# ---------------------------------------------------------------------------
# Bug 3 — a strength workout counts as exercise everywhere
# ---------------------------------------------------------------------------
def test_workout_counts_toward_exercise_heatmap_and_streak():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)
        bench = exercise_id(client, "Bench Press")

        today = date.today().isoformat()
        wid = client.post(
            "/api/workouts", json={"date": today, "name": "Push"}, headers=h
        ).json()["id"]
        for _ in range(4):  # 4 working sets -> ~14 estimated exercise minutes
            client.post(
                f"/api/workouts/{wid}/sets",
                json={"exercise_id": bench, "weight": 80, "reps": 5, "rpe": 8},
                headers=h,
            )

        # No activity_log rows at all — exercise still registers from the workout.
        today_ins = client.get("/api/insights/today").json()
        assert today_ins["exercise_minutes"] > 0

        heatmap = client.get("/api/insights/heatmap", params={"days": 30}).json()["days"]
        today_cell = next(d for d in heatmap if d["date"] == today)
        assert today_cell["level"] > 0 and today_cell["minutes"] > 0

        streaks = client.get("/api/insights/streaks").json()
        assert streaks["workout_streak"] >= 1
        assert streaks["activity_streak"] >= 1  # workouts fold into activity
        assert streaks["any_streak"] >= 1

        # Minute/session-keyed badges include lifting even without activity_log.
        badges = {b["id"]: b for b in client.get("/api/insights/achievements").json()["badges"]}
        assert badges["first_workout"]["earned"] is True
        assert badges["consistent_lifter"]["current"] >= 1

        trends = client.get("/api/insights/trends", params={"days": 7}).json()["days"]
        today_trend = next(d for d in trends if d["date"] == today)
        assert today_trend["exercise_min"] > 0


# ---------------------------------------------------------------------------
# Bug 7 — prs_count consistent with /prs items when bodyweight sets exist
# ---------------------------------------------------------------------------
def test_prs_count_matches_prs_items_with_bodyweight_sets():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)
        bench = exercise_id(client, "Bench Press")
        plank = exercise_id(client, "Plank")  # bodyweight (weight=0) movement

        wid = client.post("/api/workouts", json={"name": "Mixed"}, headers=h).json()["id"]
        client.post(f"/api/workouts/{wid}/sets",
                    json={"exercise_id": bench, "weight": 100, "reps": 5, "rpe": 8},
                    headers=h)
        # Bodyweight sets (weight=0) must not create a phantom PR.
        client.post(f"/api/workouts/{wid}/sets",
                    json={"exercise_id": plank, "weight": 0, "reps": 60},
                    headers=h)

        summary = client.get("/api/performance/summary").json()
        prs = client.get("/api/performance/prs").json()["items"]
        assert summary["prs_count"] == len(prs)
        assert all(p["exercise_id"] != plank for p in prs)  # bodyweight excluded


# ---------------------------------------------------------------------------
# Bug 4 + Bug 5 — coach macros == plan, training answers grounded
# ---------------------------------------------------------------------------
def test_coach_macros_match_active_nutrition_plan():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, goal="gain", weight_kg=82)
        h = csrf_headers(client)
        plan = client.post("/api/nutrition/plan/generate", headers=h).json()

        pnm = client.get("/api/ai/predict-next-meal").json()["macro_targets"]
        assert pnm["protein_g"] == plan["protein_g"]
        assert pnm["carbs_g"] == plan["carbs_g"]
        assert pnm["fat_g"] == plan["fat_g"]

        rec = client.get("/api/ai/recommend-foods").json()["macro_targets"]
        assert rec["protein_g"] == plan["protein_g"]


def test_coach_answers_training_questions_grounded():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="hypertrophy", goal="gain", weight_kg=80)
        h = csrf_headers(client)
        bench = exercise_id(client, "Bench Press")

        # Bench across two distinct recent dates -> an e1RM trend the coach can read.
        for i, wt in ((10, 95), (3, 100)):
            d = (date.today() - timedelta(days=i)).isoformat()
            wid = client.post("/api/workouts", json={"date": d, "name": "Push"},
                              headers=h).json()["id"]
            for _ in range(3):
                client.post(f"/api/workouts/{wid}/sets",
                            json={"exercise_id": bench, "weight": wt, "reps": 8, "rpe": 8},
                            headers=h)

        strength = client.post("/api/ai/chat",
                               json={"message": "am I getting stronger on bench?"},
                               headers=h).json()
        assert strength["intent"] == "strength"
        assert "Bench Press" in strength["reply"]

        volume = client.post("/api/ai/chat",
                             json={"message": "is my chest volume enough?"},
                             headers=h).json()
        assert volume["intent"] == "volume"
        assert "chest" in volume["reply"].lower()

        streak = client.post("/api/ai/chat",
                             json={"message": "what's my workout streak?"},
                             headers=h).json()
        assert streak["intent"] == "streak"
        assert "workout streak" in streak["reply"].lower()

        surplus = client.post("/api/ai/chat",
                              json={"message": "am I eating enough to bulk?"},
                              headers=h).json()
        assert surplus["intent"] == "surplus_deficit"
        assert surplus["reply"]

        maintain = client.post("/api/ai/chat",
                               json={"message": "how do I maintain?"},
                               headers=h).json()
        assert maintain["intent"] == "maintenance" and maintain["reply"]


# ---------------------------------------------------------------------------
# Bug 6 — 2-day template cycles to fill the requested day count
# ---------------------------------------------------------------------------
def test_maingain_program_cycles_days():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="maingain", days_per_week=3,
                    equipment="full_gym")
        program = client.post("/api/programs/generate",
                              json={"days_per_week": 3}, headers=csrf_headers(client)).json()
        assert program["days_per_week"] == 3
        names = [d["name"] for d in program["days"]]
        assert len(names) == 3
        # A/B template -> A/B/A (day 3 repeats day 1).
        assert names[0] == names[2] and names[0] != names[1]


# ---------------------------------------------------------------------------
# Bug 8 — equipment-aware generation
# ---------------------------------------------------------------------------
def test_home_basic_program_avoids_barbell():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="maingain", days_per_week=3,
                    equipment="home_basic")
        program = client.post("/api/programs/generate", json={},
                              headers=csrf_headers(client)).json()
        catalog = {e["id"]: e for e in
                   client.get("/api/exercises", params={"limit": 500}).json()["items"]}
        equipments = {
            catalog[ex["exercise_id"]]["equipment"]
            for day in program["days"] for ex in day["exercises"]
        }
        assert "barbell" not in equipments
        assert equipments <= {"dumbbell", "bodyweight"}


# ---------------------------------------------------------------------------
# Bug 10 / Bug 11 — limit soft-clamp + removed predict route
# ---------------------------------------------------------------------------
def test_workouts_limit_soft_clamps():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        r = client.get("/api/workouts", params={"limit": 500})
        assert r.status_code == 200  # not 422
        assert r.json()["limit"] == 200  # clamped to the max


def test_insights_predict_route_removed():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        assert client.get("/api/insights/predict").status_code == 404
