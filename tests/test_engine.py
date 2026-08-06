"""Tests for the recommendation + plan-generation engine (contract §6-9).

Covers program generation per persona, nutrition-plan derivation (cut <
maintenance < bulk, protein ~ goal g/kg x bodyweight), performance analytics
(e1RM PRs with warm-ups excluded, weekly volume) and the unified
recommendations payload. Runs alongside — and must keep green — the existing
smoke suite.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# Point the DB at a temp file BEFORE importing the app (mirrors test_smoke).
_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ.setdefault("FITPATH_DB", _tmp.name)

import app.db as db_module  # noqa: E402

if os.environ["FITPATH_DB"] == _tmp.name:
    db_module.DB_PATH = Path(_tmp.name)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import performance, programs  # noqa: E402


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


def _program_exercise_names(program: dict) -> set[str]:
    return {ex["name"] for day in program["days"] for ex in day["exercises"]}


# ---------------------------------------------------------------------------
# Program generation
# ---------------------------------------------------------------------------
def test_generate_program_per_persona():
    cases = {
        "powerlifting": ("upper_lower", 4),   # CUT template has 4 days
        "hypertrophy": ("push_pull_legs", 4),  # BULK has 6, first 4 used for 4 days/week
        "maingain": ("full_body", 4),          # MAINGAIN's 2-day A/B template cycles (A/B/A/B) to fill 4
    }
    for training_goal, (split_type, expected_days) in cases.items():
        with TestClient(app) as client:
            make_user(client)
            put_profile(client, training_goal=training_goal, days_per_week=4)

            r = client.post("/api/programs/generate", json={}, headers=csrf_headers(client))
            assert r.status_code == 201, r.text
            program = r.json()

            assert program["training_goal"] == training_goal
            assert program["split_type"] == split_type
            assert program["active"] is True
            assert program["days_per_week"] == expected_days
            assert len(program["days"]) == expected_days
            # Every day has ordered exercises with the contract fields.
            for day in program["days"]:
                assert day["exercises"], "day has no exercises"
                for ex in day["exercises"]:
                    assert set(ex) >= {
                        "exercise_id", "name", "target_sets", "target_reps",
                        "target_rpe", "rest_seconds", "progression",
                    }
                    assert isinstance(ex["target_reps"], str) and "-" in ex["target_reps"]
                    assert ex["target_sets"] >= 1

            # Active endpoint returns the same program with days -> exercises.
            active = client.get("/api/programs/active").json()
            assert active["id"] == program["id"]
            assert len(active["days"]) == expected_days

            # Listed in summaries.
            listed = client.get("/api/programs").json()["items"]
            assert any(p["id"] == program["id"] and p["active"] for p in listed)


def test_generate_resolves_template_exercise_aliases():
    """Hypertrophy template uses abbreviated names that must map to catalog rows."""
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="hypertrophy", days_per_week=6)

        program = client.post(
            "/api/programs/generate", json={"days_per_week": 6}, headers=csrf_headers(client)
        ).json()
        assert len(program["days"]) == 6

        names = _program_exercise_names(program)
        # Aliased template names ("Incline DB Press", "Cable Fly", "Seated DB Press",
        # "Rear-Delt Fly", "Pull-Up", "Incline DB Curl") resolve to catalog rows.
        for canonical in [
            "Incline Dumbbell Press",
            "Cable Crossover",
            "Dumbbell Shoulder Press",
            "Rear Delt Fly",
            "Pull-up",
        ]:
            assert canonical in names, f"{canonical} not resolved; got {sorted(names)}"

        # No exercise kept a raw abbreviated template name.
        assert not any("DB " in n or n.endswith(" DB") for n in names)

        # Generating must not duplicate the catalog with alias spellings.
        catalog = client.get("/api/exercises", params={"limit": 500}).json()["items"]
        catalog_names = [e["name"] for e in catalog]
        assert catalog_names.count("Incline Dumbbell Press") == 1
        assert "Incline DB Press" not in catalog_names


def test_program_days_per_week_override():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="hypertrophy", days_per_week=4)
        program = client.post(
            "/api/programs/generate", json={"days_per_week": 3}, headers=csrf_headers(client)
        ).json()
        assert program["days_per_week"] == 3
        assert len(program["days"]) == 3


def test_program_today_shape():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="hypertrophy")
        client.post("/api/programs/generate", json={}, headers=csrf_headers(client))

        today = client.get("/api/programs/today").json()
        if today.get("rest_day"):
            assert today == {"rest_day": True}
        else:
            assert "program_day_id" in today and "name" in today
            assert isinstance(today["exercises"], list) and today["exercises"]
            for ex in today["exercises"]:
                assert "suggested_weight" in ex  # None without history
                assert ex["suggested_weight"] is None


def test_program_activation_rename_delete():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        h = csrf_headers(client)

        first = client.post("/api/programs/generate", json={}, headers=h).json()
        second = client.post("/api/programs/generate", json={}, headers=h).json()
        # Newest is active; the first was deactivated.
        assert client.get("/api/programs/active").json()["id"] == second["id"]

        # Re-activate the first via PUT {active: true}.
        client.put(f"/api/programs/{first['id']}", json={"active": True}, headers=h)
        assert client.get("/api/programs/active").json()["id"] == first["id"]

        # Rename.
        renamed = client.put(
            f"/api/programs/{first['id']}", json={"name": "My Split"}, headers=h
        ).json()
        assert renamed["name"] == "My Split"

        # Delete cascades days/exercises.
        assert client.delete(f"/api/programs/{second['id']}", headers=h).json() == {"ok": True}
        assert client.get(f"/api/programs/{second['id']}").status_code == 404


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------
def _generate_plan_for_goal(client: TestClient, goal: str) -> dict:
    make_user(client)
    put_profile(client, goal=goal, weight_kg=75)
    r = client.post("/api/nutrition/plan/generate", headers=csrf_headers(client))
    assert r.status_code == 201, r.text
    return r.json()


def test_nutrition_plan_kcal_ordering_and_protein():
    with TestClient(app) as cut, TestClient(app) as maintain, TestClient(app) as bulk:
        cut_plan = _generate_plan_for_goal(cut, "lose")
        maintain_plan = _generate_plan_for_goal(maintain, "maintain")
        bulk_plan = _generate_plan_for_goal(bulk, "gain")

        # cut < maintenance < bulk
        assert cut_plan["target_kcal"] < maintain_plan["target_kcal"] < bulk_plan["target_kcal"]

        # protein ~ goal g/kg x bodyweight (2.4 cut, 1.6 maintain, 2.0 bulk; 75 kg)
        assert abs(cut_plan["protein_g"] - 2.4 * 75) <= 2
        assert abs(maintain_plan["protein_g"] - 1.6 * 75) <= 2
        assert abs(bulk_plan["protein_g"] - 2.0 * 75) <= 2

        # Macros are sane and sum roughly to the kcal target.
        for plan in (cut_plan, maintain_plan, bulk_plan):
            assert plan["active"] is True
            assert plan["target_kcal"] >= 1200
            kcal_from_macros = (
                plan["protein_g"] * 4 + plan["carbs_g"] * 4 + plan["fat_g"] * 9
            )
            assert abs(kcal_from_macros - plan["target_kcal"]) <= 60


def test_nutrition_plan_active_and_today():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, goal="maintain", weight_kg=70)
        h = csrf_headers(client)

        client.post("/api/nutrition/plan/generate", headers=h)
        plan = client.get("/api/nutrition/plan/active").json()
        assert plan["active"] is True

        # Log a meal, then today's remaining should reflect it.
        client.post(
            "/api/logs/meals",
            json={"name": "eggs", "kcal": 300, "category": "breakfast",
                  "protein_g": 20, "carbs_g": 5, "fat_g": 22},
            headers=h,
        )
        today = client.get("/api/nutrition/today").json()
        assert set(today) == {"targets", "consumed", "remaining", "meal_suggestions"}
        for block in ("targets", "consumed", "remaining"):
            assert set(today[block]) == {"kcal", "protein_g", "carbs_g", "fat_g"}
        assert today["consumed"]["kcal"] == 300
        assert today["consumed"]["protein_g"] == 20
        assert today["remaining"]["kcal"] == today["targets"]["kcal"] - 300
        assert isinstance(today["meal_suggestions"], list) and today["meal_suggestions"]
        for s in today["meal_suggestions"]:
            assert "name" in s and "kcal" in s


def test_nutrition_requires_profile():
    with TestClient(app) as client:
        make_user(client)
        assert client.post("/api/nutrition/plan/generate", headers=csrf_headers(client)).status_code == 400
        assert client.get("/api/nutrition/today").status_code == 400


# ---------------------------------------------------------------------------
# Performance analytics
# ---------------------------------------------------------------------------
def _log_bench_session(client: TestClient, h: dict, weight: float = 100, reps: int = 5) -> int:
    bench = exercise_id(client, "Bench Press")
    wid = client.post("/api/workouts", json={"name": "Push"}, headers=h).json()["id"]
    client.post(
        f"/api/workouts/{wid}/sets",
        json={"exercise_id": bench, "weight": weight, "reps": reps, "rpe": 8},
        headers=h,
    )
    # A warm-up set that must be excluded from volume + PRs.
    client.post(
        f"/api/workouts/{wid}/sets",
        json={"exercise_id": bench, "weight": 40, "reps": 5, "is_warmup": True},
        headers=h,
    )
    return bench


def test_performance_prs_summary_and_volume():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="powerlifting")
        h = csrf_headers(client)
        bench = _log_bench_session(client, h, weight=100, reps=5)

        prs = client.get("/api/performance/prs").json()["items"]
        bench_pr = next(p for p in prs if p["exercise_id"] == bench)
        assert bench_pr["best_weight"] == 100  # warm-up (40) excluded
        assert bench_pr["best_reps"] == 5
        assert bench_pr["best_e1rm"] > 110  # estimated_1rm(100, 5) ~= 114.6
        assert bench_pr["exercise_name"] == "Bench Press"
        assert bench_pr["achieved_at"]

        summary = client.get("/api/performance/summary").json()
        assert summary["total_volume"] == 500.0  # 100 x 5, warm-up excluded
        assert summary["sessions_count"] >= 1
        assert summary["prs_count"] >= 1
        assert summary["e1rm_highlights"][0]["exercise_id"] == bench

        detail = client.get(f"/api/performance/exercise/{bench}").json()
        assert len(detail["history"]) == 1  # warm-up excluded
        assert detail["history"][0]["weight"] == 100
        assert len(detail["e1rm_trend"]) == 1
        assert len(detail["volume_trend"]) == 1
        assert detail["best"]["best_weight"] == 100

        volume = client.get("/api/performance/volume").json()
        assert volume["weeks"], "no weekly volume"
        chest = None
        for wk in volume["weeks"]:
            for m in wk["muscles"]:
                if m["muscle"] == "chest":
                    chest = m
        assert chest is not None
        assert chest["sets"] == 1  # only the working set
        assert chest["volume"] == 500.0
        assert "target_low" in chest and "target_high" in chest


def test_performance_empty_state():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client)
        summary = client.get("/api/performance/summary").json()
        assert summary == {
            "total_volume": 0,
            "sessions_count": 0,
            "prs_count": 0,
            "e1rm_highlights": [],
        }
        assert client.get("/api/performance/prs").json() == {"items": []}
        assert client.get("/api/performance/volume").json() == {"weeks": []}


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
def test_recommendations_today():
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, training_goal="hypertrophy", goal="gain")
        h = csrf_headers(client)
        client.post("/api/programs/generate", json={}, headers=h)
        client.post("/api/nutrition/plan/generate", headers=h)

        rec = client.get("/api/recommendations/today").json()
        assert set(rec) == {"workout", "nutrition", "tip"}
        assert isinstance(rec["tip"], str) and rec["tip"]
        assert set(rec["nutrition"]) == {
            "targets", "consumed", "remaining", "meal_suggestions"
        }
        workout = rec["workout"]
        assert workout.get("rest_day") is True or "exercises" in workout


# ---------------------------------------------------------------------------
# Pure engine helpers (unit)
# ---------------------------------------------------------------------------
def test_suggested_weight_math():
    # No history -> None (UI shows a starting-weight prompt).
    assert performance.suggested_weight(None, 5, 8) is None
    # 100 kg e1RM, 5 reps @ RPE 8 (2 RIR) -> load for a 7-rep max, rounded to 2.5.
    w = performance.suggested_weight(100.0, 5, 8.0)
    assert w is not None
    assert 75.0 <= w <= 85.0
    assert (w * 10) % 25 == 0  # multiple of 2.5
    # Higher RPE (closer to failure) -> heavier suggestion.
    assert performance.suggested_weight(100.0, 5, 9.0) >= w


def test_program_helpers():
    assert programs.rep_range(4, True) == "4-6"
    assert programs.rep_range(1, True) == "1"
    assert programs.rep_range(10, True) == "10-14"
    assert programs.low_rep("6-10") == 6
    assert programs.low_rep("5") == 5
    sched = programs.weekly_schedule(4)
    assert len(sched) == 4
    assert sorted(sched.values()) == [0, 1, 2, 3]
    assert len(programs.weekly_schedule(2)) == 2
    assert len(programs.weekly_schedule(6)) == 6
