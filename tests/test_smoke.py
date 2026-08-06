"""Smoke tests for the multi-user FitPath API.

Covers the full happy path (register -> login -> profile -> exercises -> meals
-> workouts + sets), plus the security guarantees: per-user data isolation,
auth-required 401s, and CSRF 403s on unprotected mutations.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# Point the DB at a temp file BEFORE importing the app.
_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ["FITPATH_DB"] = _tmp.name

import app.db as db_module  # noqa: E402

db_module.DB_PATH = Path(_tmp.name)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def csrf_headers(client: TestClient) -> dict:
    """CSRF header echoing the JS-readable cookie (double-submit)."""
    token = client.cookies.get("fitpath_csrf")
    return {"X-CSRF-Token": token} if token else {}


def make_user(client: TestClient) -> dict:
    """Register a fresh unique user; cookies land in the client's jar."""
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


def bench_press_id(client: TestClient) -> int:
    items = client.get("/api/exercises", params={"q": "Bench Press"}).json()["items"]
    assert items, "seeded catalog missing Bench Press"
    return items[0]["id"]


# ---------------------------------------------------------------------------
# Public / SPA
# ---------------------------------------------------------------------------
def test_health_is_public():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_spa_index_and_client_route_fallback():
    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "fitpath" in root.text.lower()
        assert '<div id="root">' in root.text  # React mount point
        assert "no-store" in root.headers["cache-control"]

        # A client-side route must fall back to the SPA shell so a hard refresh
        # (e.g. on /login or /insights) still boots the app.
        login = client.get("/login")
        assert login.status_code == 200
        assert '<div id="root">' in login.text
        assert "no-store" in login.headers["cache-control"]

        # Unknown API paths stay JSON 404s, never the HTML shell.
        missing = client.get("/api/definitely-not-a-route")
        assert missing.status_code == 404
        assert '<div id="root">' not in missing.text


def test_retired_service_worker_clears_legacy_pwa_cache():
    with TestClient(app) as client:
        response = client.get("/sw.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert "no-store" in response.headers["cache-control"]
        assert response.headers["service-worker-allowed"] == "/"
        assert "caches.delete" in response.text
        assert "registration.unregister" in response.text


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_auth_required_without_session():
    with TestClient(app) as client:
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/profile").status_code == 401
        assert client.get("/api/logs/meals").status_code == 401
        assert client.get("/api/workouts").status_code == 401


def test_register_login_logout_me():
    with TestClient(app) as client:
        user = make_user(client)
        assert set(user) == {"id", "email", "username", "created_at"}

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["id"] == user["id"]

        # Logout requires CSRF, then invalidates the session.
        assert client.post("/api/auth/logout", headers=csrf_headers(client)).status_code == 204
        assert client.get("/api/auth/me").status_code == 401

        # Log back in by username.
        r = client.post(
            "/api/auth/login",
            json={"identifier": user["username"], "password": "password123"},
        )
        assert r.status_code == 200
        assert client.get("/api/auth/me").status_code == 200


def test_login_bad_password_401():
    with TestClient(app) as client:
        user = make_user(client)
        r = client.post(
            "/api/auth/login",
            json={"identifier": user["email"], "password": "wrong-password"},
        )
        assert r.status_code == 401


def test_duplicate_registration_409():
    with TestClient(app) as client:
        user = make_user(client)
        r = client.post(
            "/api/auth/register",
            json={"email": user["email"], "username": user["username"] + "x", "password": "password123"},
        )
        assert r.status_code == 409


def test_short_password_rejected():
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/register",
            json={"email": "shorty@ex.com", "username": "shorty", "password": "short"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
def test_csrf_required_on_mutations():
    with TestClient(app) as client:
        make_user(client)
        # Valid session but no X-CSRF-Token header -> 403.
        r = client.post("/api/logs/meals", json={"name": "x", "kcal": 100})
        assert r.status_code == 403
        # With the header it succeeds.
        r = client.post(
            "/api/logs/meals",
            json={"name": "x", "kcal": 100, "category": "snack"},
            headers=csrf_headers(client),
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def test_profile_upsert_and_new_fields():
    with TestClient(app) as client:
        make_user(client)
        assert client.get("/api/profile").status_code == 404  # not set yet

        put_profile(client, training_goal="powerlifting", equipment="home_basic")
        prof = client.get("/api/profile").json()
        assert prof["training_goal"] == "powerlifting"
        assert prof["experience_level"] == "intermediate"
        assert prof["days_per_week"] == 4
        assert prof["equipment"] == "home_basic"
        assert prof["units"] == "metric"


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------
def test_exercises_seeded_filter_and_custom():
    with TestClient(app) as client:
        make_user(client)

        # Seeded main lift present + flagged.
        bench = client.get("/api/exercises", params={"q": "Bench Press"}).json()["items"]
        assert bench and bench[0]["is_main_lift"] is True
        assert bench[0]["is_custom"] is False

        # Filter by muscle.
        chest = client.get("/api/exercises", params={"muscle": "chest"}).json()["items"]
        assert all(e["primary_muscle"] == "chest" for e in chest)

        # Create a custom exercise (owner-scoped).
        r = client.post(
            "/api/exercises",
            json={
                "name": "Zottman Curl",
                "category": "isolation",
                "primary_muscle": "biceps",
                "secondary_muscles": ["forearms"],
                "equipment": "dumbbell",
            },
            headers=csrf_headers(client),
        )
        assert r.status_code == 201
        created = r.json()
        assert created["is_custom"] is True
        assert created["secondary_muscles"] == ["forearms"]


# ---------------------------------------------------------------------------
# Logs + insights
# ---------------------------------------------------------------------------
def test_meal_crud_recent_favorite_and_insights():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)

        meal = client.post(
            "/api/logs/meals",
            json={"name": "oats", "kcal": 450, "category": "breakfast",
                  "protein_g": 15, "carbs_g": 70, "fat_g": 8},
            headers=h,
        ).json()
        assert meal["id"] and meal["favorite"] is False

        today = client.get("/api/insights/today").json()
        assert today["kcal_in"] == 450
        assert today["macros"]["protein_g"] == 15
        assert today["goals"]["water_goal_ml"] > 0

        # Favorite toggle.
        fav = client.post(f"/api/logs/meals/{meal['id']}/favorite", headers=h).json()
        assert fav["ok"] and fav["favorite"] is True

        recent = client.get("/api/logs/meals/recent").json()
        assert any(m["name"] == "oats" for m in recent["favorites"])

        # Update + delete.
        upd = client.put(
            f"/api/logs/meals/{meal['id']}",
            json={"name": "oats", "kcal": 500, "category": "breakfast"},
            headers=h,
        ).json()
        assert upd["kcal"] == 500
        assert client.delete(f"/api/logs/meals/{meal['id']}", headers=h).json() == {"ok": True}
        assert client.get("/api/logs/meals").json()["items"] == []


def test_water_weight_steps_and_trends():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, weight_kg=60)
        h = csrf_headers(client)

        assert client.post("/api/logs/water", json={"ml": 500}, headers=h).status_code == 200
        assert client.post("/api/logs/water", json={"ml": 750}, headers=h).status_code == 200
        # Weight upsert (one row per day).
        client.post("/api/logs/weight", json={"weight_kg": 60.5}, headers=h)
        client.post("/api/logs/weight", json={"weight_kg": 61.0}, headers=h)
        assert len(client.get("/api/logs/weight").json()["items"]) == 1
        # Steps upsert.
        client.post("/api/logs/steps", json={"steps": 5000}, headers=h)
        client.post("/api/logs/steps", json={"steps": 8000}, headers=h)
        steps_items = client.get("/api/logs/steps").json()["items"]
        assert len(steps_items) == 1 and steps_items[0]["steps"] == 8000

        client.post("/api/logs/activities",
                    json={"activity": "walk", "minutes": 20, "intensity": "moderate"}, headers=h)
        # A logged meal exercises the streaks meal-day aggregation (regression:
        # it previously crashed on non-empty meal history).
        client.post("/api/logs/meals",
                    json={"name": "oats", "kcal": 400, "category": "breakfast"}, headers=h)

        today = client.get("/api/insights/today").json()
        assert today["water_ml"] == 1250
        assert today["exercise_minutes"] == 20

        assert len(client.get("/api/insights/trends", params={"days": 7}).json()["days"]) == 7
        streaks = client.get("/api/insights/streaks").json()
        assert streaks["water_streak"] >= 1
        assert streaks["meal_streak"] >= 1
        assert "workout_streak" in streaks
        assert len(client.get("/api/insights/heatmap", params={"days": 30}).json()["days"]) == 30

        ach = client.get("/api/insights/achievements").json()
        assert any(b["id"] == "consistent_lifter" for b in ach["badges"])


# ---------------------------------------------------------------------------
# Workouts + sets
# ---------------------------------------------------------------------------
def test_workout_and_set_lifecycle():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)
        ex_id = bench_press_id(client)

        wid = client.post("/api/workouts", json={"name": "Push Day"}, headers=h).json()["id"]

        working = client.post(
            f"/api/workouts/{wid}/sets",
            json={"exercise_id": ex_id, "weight": 100, "reps": 5, "rpe": 8},
            headers=h,
        ).json()
        client.post(
            f"/api/workouts/{wid}/sets",
            json={"exercise_id": ex_id, "weight": 40, "reps": 5, "is_warmup": True},
            headers=h,
        )

        detail = client.get(f"/api/workouts/{wid}").json()
        assert len(detail["sets"]) == 2
        assert detail["sets"][0]["exercise_name"] == "Bench Press"
        assert detail["total_volume"] == 500.0  # warmup excluded

        # Edit + delete a set.
        client.put(f"/api/workouts/{wid}/sets/{working['id']}", json={"weight": 105}, headers=h)
        assert client.get(f"/api/workouts/{wid}").json()["sets"][0]["weight"] == 105
        assert client.delete(f"/api/workouts/{wid}/sets/{working['id']}", headers=h).json() == {"ok": True}
        assert len(client.get(f"/api/workouts/{wid}").json()["sets"]) == 1

        # A set referencing a bogus exercise is rejected.
        assert client.post(
            f"/api/workouts/{wid}/sets",
            json={"exercise_id": 999999, "weight": 50, "reps": 5},
            headers=h,
        ).status_code == 400

        # Delete workout cascades its sets.
        assert client.delete(f"/api/workouts/{wid}", headers=h).json() == {"ok": True}
        assert client.get(f"/api/workouts/{wid}").status_code == 404


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------
def test_user_data_isolation():
    with TestClient(app) as alice, TestClient(app) as bob:
        make_user(alice)
        make_user(bob)
        put_profile(alice)
        ha = csrf_headers(alice)

        # Alice logs a meal and a workout.
        alice.post("/api/logs/meals", json={"name": "steak", "kcal": 700}, headers=ha)
        wid = alice.post("/api/workouts", json={"name": "Leg Day"}, headers=ha).json()["id"]

        # Bob cannot see Alice's data.
        assert bob.get("/api/profile").status_code == 404
        assert bob.get("/api/logs/meals").json()["items"] == []
        assert bob.get("/api/workouts").json()["items"] == []
        assert bob.get(f"/api/workouts/{wid}").status_code == 404
        assert bob.delete(f"/api/workouts/{wid}", headers=csrf_headers(bob)).status_code == 404

        # Alice still sees her own.
        assert len(alice.get("/api/workouts").json()["items"]) == 1
        assert len(alice.get("/api/logs/meals").json()["items"]) == 1


# ---------------------------------------------------------------------------
# AI coach
# ---------------------------------------------------------------------------
def test_ai_endpoints_and_parse_log():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)

        for _ in range(3):
            client.post(
                "/api/logs/meals",
                json={"name": "chicken bowl", "kcal": 600, "category": "lunch",
                      "protein_g": 45, "carbs_g": 50, "fat_g": 18},
                headers=h,
            )

        p = client.get("/api/ai/predict-next-meal").json()
        assert "predicted_time" in p and "macro_gap" in p and "recommendations" in p

        rec = client.get("/api/ai/recommend-foods").json()
        assert "recommendations" in rec and "macro_gap" in rec

        pat = client.get("/api/ai/insights").json()
        assert pat["total_meals"] >= 3 and "typical_times" in pat

        for q in ["hi", "what should I eat?", "how am I doing?", "show my macros",
                  "tip", "how's my hydration?", "patterns please", "calories left?"]:
            r = client.post("/api/ai/chat", json={"message": q}, headers=h).json()
            assert r["reply"] and "intent" in r and isinstance(r["chips"], list)

        parsed = client.post(
            "/api/ai/parse-log",
            json={"text": "had 2 eggs and a coffee for breakfast"},
            headers=h,
        ).json()
        assert parsed["category"] == "breakfast"
        assert parsed["kcal"] > 100
        assert any(i["name"] == "eggs" for i in parsed["items"])


# ---------------------------------------------------------------------------
# Admin seed/reset
# ---------------------------------------------------------------------------
def test_admin_seed_and_reset():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)

        seeded = client.post("/api/admin/seed-demo", params={"days": 14}, headers=h).json()
        assert seeded["ok"] and seeded["days_seeded"] == 14
        assert len(client.get("/api/workouts").json()["items"]) >= 1
        assert client.get("/api/insights/trends", params={"days": 14}).json()["days"]

        assert client.post("/api/admin/reset", headers=h).json()["ok"] is True
        assert client.get("/api/workouts").json()["items"] == []
        # Profile survives a reset.
        assert client.get("/api/profile").status_code == 200
