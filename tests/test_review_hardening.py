"""Hardening tests added by the testing-and-review pass.

These complement ``test_smoke``/``test_engine`` and lock in the guarantees that
matter most for a multi-user app:

* **Per-user data isolation** on *every* resource (user B can neither read nor
  mutate user A's meals/activities/sleep/steps/water/weight/exercises/workouts/
  sets/programs/nutrition plan).
* **Auth edge cases**: duplicate username, absent/garbage/expired session -> 401,
  missing CSRF on PUT/DELETE -> 403.
* **Recommendation correctness**: ``/programs/today`` rest-day vs training-day
  scheduling, e1RM PR math vs the researched formula, warm-ups excluded.
* **Empty-state**: a brand-new profile with no logs returns sensible 200s /
  documented 404s across the whole surface — never a 500.
* **Calorie-target consistency**: the daily target is now a single source of
  truth, so insights/today == the nutrition plan == nutrition/today.

The DB is pointed at a temp file BEFORE importing the app (mirrors the other
suites) so the shared ``fitpath.sqlite3`` is never touched.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ.setdefault("FITPATH_DB", _tmp.name)

import app.db as db_module  # noqa: E402

if os.environ["FITPATH_DB"] == _tmp.name:
    db_module.DB_PATH = Path(_tmp.name)

from datetime import date as date_cls  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.services.programs as programs_service  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.deps import SESSION_COOKIE, utcnow  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuthSession  # noqa: E402
from app.training.params import estimated_1rm  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("fitpath_csrf")
    return {"X-CSRF-Token": token} if token else {}


def make_user(client: TestClient) -> dict:
    uid = uuid.uuid4().hex[:10]
    r = client.post(
        "/api/auth/register",
        json={"email": f"{uid}@ex.com", "username": f"u{uid}", "password": "password123"},
    )
    assert r.status_code == 201, r.text
    return r.json()["user"]


def put_profile(client: TestClient, **overrides) -> None:
    payload = {
        "name": "Test",
        "sex": "male",
        "age": 28,
        "height_cm": 178,
        "weight_kg": 75,
        "activity_level": "moderate",
        "goal": "maintain",
        "training_goal": "hypertrophy",
        "experience_level": "intermediate",
        "days_per_week": 4,
        "equipment": "full_gym",
        "units": "metric",
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
# Per-user data isolation — every resource
# ---------------------------------------------------------------------------
def test_isolation_all_log_resources():
    """Bob can neither list, read, mutate nor delete any of Alice's log rows."""
    with TestClient(app) as alice, TestClient(app) as bob:
        make_user(alice)
        make_user(bob)
        put_profile(alice)
        ha, hb = csrf_headers(alice), csrf_headers(bob)

        meal = alice.post(
            "/api/logs/meals",
            json={"name": "steak", "kcal": 700, "category": "dinner"},
            headers=ha,
        ).json()
        activity = alice.post(
            "/api/logs/activities",
            json={"activity": "run", "minutes": 30, "intensity": "vigorous"},
            headers=ha,
        ).json()
        sleep = alice.post(
            "/api/logs/sleep", json={"hours": 7.5, "wake_time": "07:00"}, headers=ha
        ).json()
        steps = alice.post("/api/logs/steps", json={"steps": 9000}, headers=ha).json()
        water = alice.post("/api/logs/water", json={"ml": 500}, headers=ha).json()
        weight = alice.post("/api/logs/weight", json={"weight_kg": 74.0}, headers=ha).json()

        # Bob's lists are empty (scoped to his own user_id).
        for path in (
            "/api/logs/meals",
            "/api/logs/activities",
            "/api/logs/sleep",
            "/api/logs/steps",
            "/api/logs/water",
            "/api/logs/weight",
        ):
            assert bob.get(path).json()["items"] == [], path

        # Bob cannot mutate/delete Alice's rows by id -> 404 (not 403/200).
        assert bob.put(f"/api/logs/meals/{meal['id']}",
                       json={"name": "x", "kcal": 1, "category": "snack"},
                       headers=hb).status_code == 404
        assert bob.post(f"/api/logs/meals/{meal['id']}/favorite", headers=hb).status_code == 404
        assert bob.delete(f"/api/logs/meals/{meal['id']}", headers=hb).status_code == 404
        assert bob.put(f"/api/logs/activities/{activity['id']}",
                       json={"activity": "x", "minutes": 1, "intensity": "light"},
                       headers=hb).status_code == 404
        assert bob.delete(f"/api/logs/activities/{activity['id']}", headers=hb).status_code == 404
        assert bob.put(f"/api/logs/sleep/{sleep['id']}",
                       json={"hours": 1, "wake_time": "07:00"}, headers=hb).status_code == 404
        assert bob.delete(f"/api/logs/sleep/{sleep['id']}", headers=hb).status_code == 404
        assert bob.delete(f"/api/logs/steps/{steps['id']}", headers=hb).status_code == 404
        assert bob.delete(f"/api/logs/water/{water['id']}", headers=hb).status_code == 404
        assert bob.put(f"/api/logs/weight/{weight['id']}",
                       json={"weight_kg": 60.0}, headers=hb).status_code == 404
        assert bob.delete(f"/api/logs/weight/{weight['id']}", headers=hb).status_code == 404

        # Alice still owns everything.
        assert len(alice.get("/api/logs/meals").json()["items"]) == 1
        assert len(alice.get("/api/logs/activities").json()["items"]) == 1


def test_isolation_exercises_workouts_programs_plans():
    with TestClient(app) as alice, TestClient(app) as bob:
        make_user(alice)
        make_user(bob)
        put_profile(alice, training_goal="hypertrophy")
        put_profile(bob)
        ha, hb = csrf_headers(alice), csrf_headers(bob)

        # Alice's custom exercise is invisible to Bob.
        custom = alice.post(
            "/api/exercises",
            json={"name": "Zottman Curl", "category": "isolation",
                  "primary_muscle": "biceps", "equipment": "dumbbell"},
            headers=ha,
        ).json()
        assert bob.get(f"/api/exercises/{custom['id']}").status_code == 404
        bob_names = [e["name"] for e in bob.get("/api/exercises", params={"limit": 500}).json()["items"]]
        assert "Zottman Curl" not in bob_names
        # ...and Bob cannot read its performance history either.
        assert bob.get(f"/api/performance/exercise/{custom['id']}").status_code == 404

        # Alice's workout + set are invisible / immutable to Bob.
        bench = exercise_id(alice, "Bench Press")
        wid = alice.post("/api/workouts", json={"name": "Push"}, headers=ha).json()["id"]
        sid = alice.post(f"/api/workouts/{wid}/sets",
                         json={"exercise_id": bench, "weight": 100, "reps": 5},
                         headers=ha).json()["id"]
        assert bob.get(f"/api/workouts/{wid}").status_code == 404
        assert bob.put(f"/api/workouts/{wid}", json={"name": "hax"}, headers=hb).status_code == 404
        assert bob.delete(f"/api/workouts/{wid}", headers=hb).status_code == 404
        assert bob.post(f"/api/workouts/{wid}/sets",
                        json={"exercise_id": bench, "weight": 50, "reps": 5},
                        headers=hb).status_code == 404
        assert bob.put(f"/api/workouts/{wid}/sets/{sid}",
                       json={"weight": 1}, headers=hb).status_code == 404
        assert bob.delete(f"/api/workouts/{wid}/sets/{sid}", headers=hb).status_code == 404

        # Alice's program is invisible / immutable to Bob.
        pid = alice.post("/api/programs/generate", json={}, headers=ha).json()["id"]
        assert bob.get(f"/api/programs/{pid}").status_code == 404
        assert bob.put(f"/api/programs/{pid}", json={"name": "hax"}, headers=hb).status_code == 404
        assert bob.delete(f"/api/programs/{pid}", headers=hb).status_code == 404

        # Alice's nutrition plan is not exposed to Bob (he has none of his own).
        alice.post("/api/nutrition/plan/generate", headers=ha)
        assert alice.get("/api/nutrition/plan/active").json()["active"] is True
        assert bob.get("/api/nutrition/plan/active").status_code == 404


# ---------------------------------------------------------------------------
# Auth edge cases
# ---------------------------------------------------------------------------
def test_duplicate_username_conflicts():
    with TestClient(app) as client:
        user = make_user(client)
        r = client.post(
            "/api/auth/register",
            json={"email": "fresh-" + user["email"], "username": user["username"],
                  "password": "password123"},
        )
        assert r.status_code == 409
        assert "username" in r.json()["detail"].lower()


def test_absent_and_garbage_session_are_401():
    with TestClient(app) as client:
        assert client.get("/api/auth/me").status_code == 401
        r = client.get("/api/auth/me", headers={"Cookie": f"{SESSION_COOKIE}=not-a-real-token"})
        assert r.status_code == 401


def test_expired_session_is_401():
    with TestClient(app) as client:
        user = make_user(client)
        token = "expired-" + uuid.uuid4().hex
        with SessionLocal() as db:
            db.add(AuthSession(
                token=token,
                csrf_token="x",
                user_id=user["id"],
                expires_at=utcnow() - timedelta(days=1),
            ))
            db.commit()
        r = client.get("/api/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"})
        assert r.status_code == 401


def test_missing_csrf_on_put_and_delete_is_403():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)
        meal = client.post(
            "/api/logs/meals",
            json={"name": "oats", "kcal": 300, "category": "breakfast"},
            headers=h,
        ).json()
        # Valid session but no X-CSRF-Token header -> 403 on every mutation verb.
        assert client.put(f"/api/logs/meals/{meal['id']}",
                          json={"name": "oats", "kcal": 1, "category": "snack"}).status_code == 403
        assert client.delete(f"/api/logs/meals/{meal['id']}").status_code == 403
        # The row survived the rejected mutations.
        assert len(client.get("/api/logs/meals").json()["items"]) == 1


# ---------------------------------------------------------------------------
# Recommendation correctness — today rest-day scheduling + e1RM math
# ---------------------------------------------------------------------------
class _FrozenDate:
    """Stand-in for ``datetime.date`` whose ``today()`` is fixed to a weekday."""

    _value = date_cls.today()

    @classmethod
    def today(cls):
        return cls._value


def test_programs_today_rest_vs_training_day(monkeypatch):
    # 2026-07-06 is a Monday (weekday 0), 2026-07-07 a Tuesday (weekday 1).
    monday = date_cls(2026, 7, 6)
    tuesday = date_cls(2026, 7, 7)
    assert monday.weekday() == 0 and tuesday.weekday() == 1

    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="maingain", days_per_week=1)
        client.post("/api/programs/generate", json={"days_per_week": 1},
                    headers=csrf_headers(client))

        # A 1-day program schedules only weekday 0 -> Monday trains, Tuesday rests.
        _FrozenDate._value = tuesday
        monkeypatch.setattr(programs_service, "date", _FrozenDate)
        assert client.get("/api/programs/today").json() == {"rest_day": True}

        _FrozenDate._value = monday
        today = client.get("/api/programs/today").json()
        assert today.get("rest_day") is not True
        assert "program_day_id" in today and today["exercises"]
        # No training history yet -> suggested weight is a prompt (None).
        assert all(ex["suggested_weight"] is None for ex in today["exercises"])


def test_e1rm_pr_matches_formula_and_excludes_warmups():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="powerlifting")
        h = csrf_headers(client)
        bench = exercise_id(client, "Bench Press")

        wid = client.post("/api/workouts", json={"name": "Bench"}, headers=h).json()["id"]
        client.post(f"/api/workouts/{wid}/sets",
                    json={"exercise_id": bench, "weight": 100, "reps": 5, "rpe": 8}, headers=h)
        # A heavier warm-up must NOT set a PR or add volume.
        client.post(f"/api/workouts/{wid}/sets",
                    json={"exercise_id": bench, "weight": 120, "reps": 3, "is_warmup": True}, headers=h)

        prs = client.get("/api/performance/prs").json()["items"]
        bench_pr = next(p for p in prs if p["exercise_id"] == bench)
        expected = round(estimated_1rm(100, 5), 1)
        assert bench_pr["best_e1rm"] == expected
        assert bench_pr["best_weight"] == 100  # 120 warm-up excluded
        assert bench_pr["best_reps"] == 5

        summary = client.get("/api/performance/summary").json()
        assert summary["total_volume"] == 500.0  # only the 100x5 working set


# ---------------------------------------------------------------------------
# Empty-state — a fresh profile never 500s
# ---------------------------------------------------------------------------
def test_empty_state_endpoints_never_500():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)  # profile set, but zero logs / programs / plans
        bench = exercise_id(client, "Bench Press")

        ok_200 = [
            "/api/insights/today",
            "/api/insights/circadian",
            "/api/insights/trends",
            "/api/insights/streaks",
            "/api/insights/achievements",
            "/api/insights/heatmap",
            "/api/performance/summary",
            "/api/performance/prs",
            "/api/performance/volume",
            f"/api/performance/exercise/{bench}",
            "/api/programs",
            "/api/programs/today",
            "/api/nutrition/today",
            "/api/recommendations/today",
            "/api/ai/insights",
            "/api/ai/predict-next-meal",
            "/api/ai/recommend-foods",
        ]
        for path in ok_200:
            r = client.get(path)
            assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text}"

        # Documented 404s when nothing has been generated yet.
        assert client.get("/api/programs/active").status_code == 404
        assert client.get("/api/nutrition/plan/active").status_code == 404

        # Empty analytics are explicitly zeroed, not missing.
        assert client.get("/api/performance/summary").json() == {
            "total_volume": 0, "sessions_count": 0, "prs_count": 0, "e1rm_highlights": []
        }
        assert client.get("/api/programs/today").json() == {"rest_day": True}


# ---------------------------------------------------------------------------
# Calorie-target consistency (single source of truth)
# ---------------------------------------------------------------------------
def test_calorie_target_is_consistent_across_surfaces():
    with TestClient(app) as client:
        make_user(client)
        # "gain" is the goal whose delta used to diverge (insights +300 vs plan +350).
        put_profile(client, goal="gain", weight_kg=80)
        h = csrf_headers(client)

        plan = client.post("/api/nutrition/plan/generate", headers=h).json()
        insights_target = client.get("/api/insights/today").json()["target_kcal"]
        nutrition_target = client.get("/api/nutrition/today").json()["targets"]["kcal"]

        assert insights_target == plan["target_kcal"] == nutrition_target
