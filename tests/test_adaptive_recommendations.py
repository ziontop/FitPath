"""Tests for the history-adaptive recommendation engine (ADAPTIVE-RECOMMENDATIONS.md).

Covers the additive, deterministic ``/api/recommendations/{adaptive,meals,workout}``
surface end-to-end plus the pure engine in :mod:`app.ml.adaptive`:

* meals — cold start, sparse blend, macro-fit / recency / frequency / adherence
  ranking, portion scaling, MMR diversity, already-eaten-today exclusion,
  category filter, determinism, confidence & history-basis shapes;
* workouts — cold start, increase, hold, reduce, deload (stall), layoff resume,
  warm-ups excluded, RPE-None handling, zero-weight/bodyweight, program-day
  override + 404, no-active-program and rest-day states;
* unified envelope shape/version/tip and per-user isolation.

The DB is pointed at a temp file BEFORE importing the app (mirrors the other
suites) so the shared ``fitpath.sqlite3`` is never touched.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ.setdefault("FITPATH_DB", _tmp.name)

import app.db as db_module  # noqa: E402

if os.environ["FITPATH_DB"] == _tmp.name:
    db_module.DB_PATH = Path(_tmp.name)

import datetime as _dt  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.services.adaptive as adaptive_service  # noqa: E402
from app.main import app  # noqa: E402
from app.ml import adaptive as ml  # noqa: E402


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
        "name": "Test", "sex": "male", "age": 28, "height_cm": 178,
        "weight_kg": 75, "activity_level": "moderate", "goal": "maintain",
        "training_goal": "hypertrophy", "experience_level": "intermediate",
        "days_per_week": 4, "equipment": "full_gym", "units": "metric",
        "wake_time": "07:00",
    }
    payload.update(overrides)
    r = client.put("/api/profile", json=payload, headers=csrf_headers(client))
    assert r.status_code == 200, r.text


@contextmanager
def new_client_with_profile(**profile):
    """Yield a TestClient whose lifespan has run (tables created) + a set profile."""
    with TestClient(app) as client:
        make_user(client)
        put_profile(client, **profile)
        yield client


def log_meal(
    client, h, name, kcal, category="dinner", p=0, c=0, f=0,
    days_ago=1, hour=12, favorite=False,
):
    eaten = (datetime.now() - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    r = client.post(
        "/api/logs/meals",
        json={
            "name": name, "kcal": kcal, "category": category,
            "protein_g": p, "carbs_g": c, "fat_g": f, "eaten_at": eaten.isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    if favorite:
        client.post(f"/api/logs/meals/{mid}/favorite", headers=h)
    return mid


def log_session(client, h, exercise_id, days_ago, sets, program_day_id=None):
    """``sets`` = list of (weight, reps, rpe|None, is_warmup)."""
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    body = {"name": "S", "date": d}
    if program_day_id is not None:
        body["program_day_id"] = program_day_id
    wid = client.post("/api/workouts", json=body, headers=h).json()["id"]
    for (w, reps, rpe, warm) in sets:
        payload = {"exercise_id": exercise_id, "weight": w, "reps": reps, "is_warmup": warm}
        if rpe is not None:
            payload["rpe"] = rpe
        r = client.post(f"/api/workouts/{wid}/sets", json=payload, headers=h)
        assert r.status_code == 201, r.text
    return wid


def generate_program(client, h, **body) -> dict:
    r = client.post("/api/programs/generate", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def day0_first_exercise(client):
    """Return (day_id, exercise dict, rep_low, rep_high) for the active program's first day."""
    prog = client.get("/api/programs/active").json()
    day = sorted(prog["days"], key=lambda d: d["day_index"])[0]
    ex = day["exercises"][0]
    low, high = _rep_bounds(ex["target_reps"])
    return day["id"], ex, low, high


def _rep_bounds(s: str) -> tuple[int, int]:
    parts = str(s).replace("–", "-").split("-")
    low = int("".join(ch for ch in parts[0] if ch.isdigit()))
    high = low
    if len(parts) > 1:
        digits = "".join(ch for ch in parts[1] if ch.isdigit())
        if digits:
            high = int(digits)
    return low, high


def find_meal(suggestions, name_contains):
    lowered = name_contains.lower()
    return [s for s in suggestions if lowered in s["name"].lower()]


def find_exercise(block, exercise_id):
    return next(e for e in block["exercises"] if e["exercise_id"] == exercise_id)


# ===========================================================================
# Pure engine (fast, no DB) — decide_progression state machine + helpers
# ===========================================================================
def _presc(low=6, high=8, sets=4, rpe=8.0, inc=1.25):
    return ml.Prescription(low, high, sets, rpe, inc, inc)


def _sess(days_ago, w, reps, rpe, sets=4, e1rm=None):
    d = date.today() - timedelta(days=days_ago)
    return ml.SessionSummary(d, w, reps, rpe, sets, e1rm if e1rm is not None else w * (1 + reps / 30))


def test_pure_decide_cold_start():
    dec = ml.decide_progression(_presc(), [], best_e1rm=None, layoff_days=None, cold_start_weight=None)
    assert dec.action == "start" and dec.weight is None and dec.reason_kind == "start"


def test_pure_decide_increase_hold_reduce():
    # Increase: top of range at target RPE, sets complete, and it beat the prior session.
    sessions = [_sess(6, 100, 6, 8.0), _sess(2, 100, 8, 7.5)]
    inc = ml.decide_progression(_presc(), sessions, 104.0, 2, None)
    assert inc.action == "increase" and inc.weight > 100 and inc.reps == 6

    # Hold (progress reps): inside the range, single session.
    hold = ml.decide_progression(_presc(), [_sess(2, 100, 6, 8.0)], 100.0, 2, None)
    assert hold.action == "hold" and hold.weight == 100 and hold.reps == 7

    # Reduce: two consecutive misses below rep_low.
    misses = [_sess(4, 100, 4, 8.0), _sess(2, 100, 4, 8.0)]
    red = ml.decide_progression(_presc(), misses, 100.0, 2, None)
    assert red.action == "reduce" and red.weight < 100


def test_pure_decide_deload_and_layoff_and_bodyweight():
    # Deload after 3 stalls (four identical sessions never beat their predecessor).
    stalled = [_sess(8, 100, 6, 8.0), _sess(6, 100, 6, 8.0), _sess(4, 100, 6, 8.0), _sess(2, 100, 6, 8.0)]
    deload = ml.decide_progression(_presc(), stalled, 100.0, 2, None)
    assert deload.action == "deload" and deload.deload is True
    assert 89 <= deload.weight <= 91  # ~90%

    # Layoff: a single session 20 days ago resumes lighter, not punished.
    lay = ml.decide_progression(_presc(), [_sess(20, 100, 6, 8.0)], 100.0, 20, None)
    assert lay.action == "hold" and lay.reason_kind == "layoff"
    assert 92 <= lay.weight <= 94  # ~93%

    # Bodyweight (zero load): never adds load, just progresses reps.
    bw = ml.decide_progression(_presc(), [_sess(2, 0, 8, None)], None, 2, None)
    assert bw.action == "hold" and bw.weight == 0 and bw.reason_kind == "hold_bodyweight"


def test_pure_decide_e1rm_regression_deload():
    # Last session's e1RM slipped ≥5% under the recent best → deload.
    sessions = [_sess(6, 100, 8, 8.0, e1rm=120.0), _sess(2, 90, 6, 8.0, e1rm=105.0)]
    dec = ml.decide_progression(_presc(), sessions, best_e1rm=120.0, layoff_days=2, cold_start_weight=None)
    assert dec.action == "deload" and dec.reason_kind in ("deload_e1rm", "deload_stall")


def test_pure_helpers_math():
    assert round(ml.cosine((52, 60, 14), (45, 150, 30)), 3) == 0.915
    assert ml.portion_factor(300, 600) == 2.0  # clamp upper
    assert ml.portion_factor(1200, 600) == 0.5  # clamp lower
    assert ml.portion_factor(600, 600) == 1.0
    assert ml.jaccard(ml.tokens("Chicken and rice"), ml.tokens("Chicken rice bowl")) >= 0.6
    assert ml.confidence_meal(21, 9) == "high"
    assert ml.confidence_meal(6, 4) == "medium"
    assert ml.confidence_meal(2, 1) == "low"
    assert ml.confidence_workout(5) == "high" and ml.confidence_workout(2) == "medium"
    assert ml.min_confidence(["high", "low", "medium"]) == "low"
    # Deterministic, process-independent hash + rotation.
    assert ml.stable_hash("x") == ml.stable_hash("x")


# ===========================================================================
# Meals — cold start & sparse
# ===========================================================================
def test_meals_cold_start_fallback():
    with new_client_with_profile() as client:
        block = client.get("/api/recommendations/meals").json()
        assert block["version"] == "adaptive-v1"
        assert block["confidence"] == "low"
        assert block["history_basis"]["distinct_foods"] == 0
        assert block["suggestions"], "cold start must still return starter picks"
        for s in block["suggestions"]:
            assert s["logged_count"] == 0
            assert s["last_eaten_at"] is None
            assert "starter" in s["history_basis"].lower()


def test_meals_sparse_blends_history_with_fallback():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        # Two distinct foods over two days -> sparse state.
        log_meal(client, h, "Turkey wrap", 500, "lunch", 35, 45, 15, days_ago=2)
        log_meal(client, h, "Oatmeal", 400, "breakfast", 15, 60, 8, days_ago=3)

        block = client.get("/api/recommendations/meals", params={"limit": 3}).json()
        assert len(block["suggestions"]) == 3
        counts = [s["logged_count"] for s in block["suggestions"]]
        assert any(c > 0 for c in counts), "history foods should appear"
        assert any(c == 0 for c in counts), "fallbacks should fill the slate"
        assert block["confidence"] in ("low", "medium")


# ===========================================================================
# Meals — signal ranking (each isolated)
# ===========================================================================
def test_meals_recency_ranking():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        for d in (1, 2, 3):
            log_meal(client, h, "Recent yogurt", 240, "snack", 20, 30, 5, days_ago=d)
        for d in (20, 21, 22):
            log_meal(client, h, "Old yogurt", 240, "snack", 20, 30, 5, days_ago=d)

        sugg = client.get("/api/recommendations/meals", params={"limit": 10}).json()["suggestions"]
        recent = find_meal(sugg, "Recent yogurt")[0]
        old = find_meal(sugg, "Old yogurt")[0]
        assert recent["components"]["recency"] > old["components"]["recency"]
        assert recent["score"] > old["score"]


def test_meals_frequency_ranking():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        for d in (1, 2, 3, 4, 5, 6):
            log_meal(client, h, "Frequent bar", 210, "snack", 20, 22, 7, days_ago=d)
        log_meal(client, h, "Rare bar", 210, "snack", 20, 22, 7, days_ago=1)

        sugg = client.get("/api/recommendations/meals", params={"limit": 10}).json()["suggestions"]
        freq = find_meal(sugg, "Frequent bar")[0]
        rare = find_meal(sugg, "Rare bar")[0]
        assert freq["components"]["frequency"] > rare["components"]["frequency"]
        assert freq["score"] > rare["score"]


def test_meals_macro_fit_ranking():
    with new_client_with_profile(goal="gain") as client:
        h = csrf_headers(client)
        plan = client.post("/api/nutrition/plan/generate", headers=h).json()
        # Fill today's carbs + fat so the remaining gap is protein-dominant.
        log_meal(
            client, h, "Big carb dinner", plan["carbs_g"] * 4 + plan["fat_g"] * 9 + 40,
            "dinner", 10, plan["carbs_g"], plan["fat_g"], days_ago=0, hour=13,
        )
        for d in (2, 4, 6):
            log_meal(client, h, "Chicken breast", 220, "lunch", 40, 2, 5, days_ago=d)
            log_meal(client, h, "White rice", 230, "lunch", 4, 50, 1, days_ago=d)

        sugg = client.get("/api/recommendations/meals", params={"limit": 10}).json()["suggestions"]
        chicken = find_meal(sugg, "Chicken breast")[0]
        rice = find_meal(sugg, "White rice")[0]
        assert chicken["components"]["macro_fit"] > rice["components"]["macro_fit"]


def test_meals_adherence_signal():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        plan = client.post("/api/nutrition/plan/generate", headers=h).json()
        target, protein = plan["target_kcal"], plan["protein_g"]
        # "Good bowl" only on on-target days; "Cheat pizza" only on blow-out days.
        for i, d in enumerate((2, 4, 6, 8, 10)):
            log_meal(client, h, "Good bowl", target, "dinner", protein, 100, 50, days_ago=d)
        for d in (3, 5, 7):
            log_meal(client, h, "Cheat pizza", round(target * 1.5), "dinner",
                     round(protein * 0.3), 100, 50, days_ago=d)
        # A third food to stay out of the sparse-blend branch.
        for d in (4, 6):
            log_meal(client, h, "Side salad", 150, "dinner", 5, 12, 9, days_ago=d)

        block = client.get("/api/recommendations/meals", params={"limit": 10}).json()
        assert block["history_basis"]["adherent_days"] >= 5
        good = find_meal(block["suggestions"], "Good bowl")[0]
        cheat = find_meal(block["suggestions"], "Cheat pizza")[0]
        assert good["components"]["adherence"] > cheat["components"]["adherence"]
        assert good["components"]["adherence"] >= 0.99
        assert cheat["components"]["adherence"] == 0.0


# ===========================================================================
# Meals — portion / diversity / exclusion / filter / determinism
# ===========================================================================
def test_meals_portion_scaling_and_payload_consistency():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        for d in (1, 2, 3, 4, 5):
            log_meal(client, h, "Protein plate", 300, "lunch", 30, 30, 6, days_ago=d)

        sugg = client.get("/api/recommendations/meals", params={"limit": 5}).json()["suggestions"]
        assert sugg
        for s in sugg:
            assert ml.PORTION_MIN <= s["portion"] <= ml.PORTION_MAX
            # meal_payload mirrors the (scaled) headline numbers.
            assert s["meal_payload"]["kcal"] == s["kcal"]
            assert s["meal_payload"]["protein_g"] == s["protein_g"]
            # Scaled macros stay internally consistent with the scaled kcal.
            macro_kcal = s["protein_g"] * 4 + s["carbs_g"] * 4 + s["fat_g"] * 9
            assert abs(macro_kcal - s["kcal"]) <= max(25, 0.1 * s["kcal"])


def test_meals_mmr_diversity_drops_near_duplicates():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        # Three near-identical chicken-rice variants + two distinct foods.
        for d in (1, 2, 3):
            log_meal(client, h, "Chicken and rice", 600, "lunch", 45, 60, 14, days_ago=d)
            log_meal(client, h, "Chicken rice bowl", 610, "lunch", 46, 61, 14, days_ago=d)
            log_meal(client, h, "Chicken rice plate", 605, "lunch", 45, 60, 15, days_ago=d)
        for d in (1, 2, 3):
            log_meal(client, h, "Greek yogurt", 240, "snack", 24, 28, 4, days_ago=d)
            log_meal(client, h, "Mixed nuts", 200, "snack", 6, 6, 16, days_ago=d)

        sugg = client.get("/api/recommendations/meals", params={"limit": 3}).json()["suggestions"]
        chicken = find_meal(sugg, "chicken rice") + find_meal(sugg, "chicken and rice")
        assert len(chicken) <= 1, "near-duplicate chicken-rice rows must be de-duped"
        assert len(sugg) == 3


def test_meals_excludes_already_eaten_today():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        for d in (1, 2, 3):
            log_meal(client, h, "Repeat meal", 500, "lunch", 40, 45, 15, days_ago=d)
        # Also eaten TODAY -> must be excluded from the candidate pool.
        log_meal(client, h, "Repeat meal", 500, "lunch", 40, 45, 15, days_ago=0, hour=9)

        sugg = client.get("/api/recommendations/meals", params={"limit": 10}).json()["suggestions"]
        assert not find_meal(sugg, "Repeat meal")


def test_meals_category_filter():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        for d in (1, 2, 3):
            log_meal(client, h, "Egg scramble", 350, "breakfast", 25, 10, 20, days_ago=d)
            log_meal(client, h, "Steak dinner", 700, "dinner", 55, 20, 40, days_ago=d)

        block = client.get("/api/recommendations/meals", params={"category": "dinner", "limit": 5}).json()
        assert block["suggestions"]
        assert all(s["category"] == "dinner" for s in block["suggestions"])


def test_meals_deterministic_output():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        for d in (1, 2, 3, 4, 5, 6):
            log_meal(client, h, f"Food {d % 3}", 400 + d, "lunch", 30, 40, 10, days_ago=d)

        first = client.get("/api/recommendations/meals", params={"limit": 3}).json()["suggestions"]
        second = client.get("/api/recommendations/meals", params={"limit": 3}).json()["suggestions"]
        assert [(s["name"], s["score"], s["portion"]) for s in first] == \
               [(s["name"], s["score"], s["portion"]) for s in second]


def test_meals_confidence_and_history_basis_high():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        # ≥14 days and ≥8 distinct foods -> high confidence.
        for d in range(1, 16):
            log_meal(client, h, f"Food {d % 9}", 300 + d, "lunch", 25, 30, 8, days_ago=d)

        block = client.get("/api/recommendations/meals", params={"limit": 3}).json()
        hb = block["history_basis"]
        assert hb["window_days"] == 30
        assert hb["days_observed"] >= 14 and hb["distinct_foods"] >= 8
        assert block["confidence"] == "high"
        for s in block["suggestions"]:
            assert set(s["components"]) == {
                "macro_fit", "recency", "frequency", "adherence", "category_fit", "favorite"
            }
            assert s["reason"] and s["history_basis"]


# ===========================================================================
# Workouts — progression states (program-day override to fix the session)
# ===========================================================================
def test_workout_cold_start():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)

        block = client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json()
        rec = find_exercise(block, ex["exercise_id"])
        assert rec["action"] == "start"
        assert rec["suggested_weight"] is None
        assert rec["last_performance"] is None
        assert rec["confidence"] == "low"
        assert rec["e1rm_trend"] is None


def test_workout_increase():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid, rpe, sets = ex["exercise_id"], ex["target_rpe"] or 8.0, ex["target_sets"]

        # Prior session at the low end, latest hits the top of range at/under target RPE.
        log_session(client, h, eid, days_ago=6,
                    sets=[(100, low, rpe, False)] * sets, program_day_id=day_id)
        log_session(client, h, eid, days_ago=2,
                    sets=[(100, high, rpe, False)] * sets, program_day_id=day_id)

        block = client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json()
        rec = find_exercise(block, eid)
        assert rec["action"] == "increase"
        assert rec["suggested_weight"] > 100
        assert rec["change"]["direction"] == "up"
        assert rec["last_performance"]["weight"] == 100
        assert rec["e1rm_trend"] is not None


def test_workout_hold_progress():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid, rpe, sets = ex["exercise_id"], ex["target_rpe"] or 8.0, ex["target_sets"]

        log_session(client, h, eid, days_ago=2,
                    sets=[(100, low, rpe, False)] * sets, program_day_id=day_id)

        rec = find_exercise(
            client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json(), eid
        )
        assert rec["action"] == "hold"
        assert rec["suggested_weight"] == 100
        assert rec["change"]["weight_delta_kg"] == 0.0


def test_workout_reduce_after_two_misses():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid, rpe, sets = ex["exercise_id"], ex["target_rpe"] or 8.0, ex["target_sets"]
        miss_reps = max(1, low - 1)

        log_session(client, h, eid, days_ago=4,
                    sets=[(100, miss_reps, rpe, False)] * sets, program_day_id=day_id)
        log_session(client, h, eid, days_ago=2,
                    sets=[(100, miss_reps, rpe, False)] * sets, program_day_id=day_id)

        rec = find_exercise(
            client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json(), eid
        )
        assert rec["action"] == "reduce"
        assert rec["suggested_weight"] < 100
        assert rec["change"]["direction"] == "down"


def test_workout_deload_after_stalls():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid, rpe, sets = ex["exercise_id"], ex["target_rpe"] or 8.0, ex["target_sets"]

        # Four identical sessions -> three consecutive stalls -> deload.
        for d in (8, 6, 4, 2):
            log_session(client, h, eid, days_ago=d,
                        sets=[(100, low, rpe, False)] * sets, program_day_id=day_id)

        rec = find_exercise(
            client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json(), eid
        )
        assert rec["action"] == "deload" and rec["deload"] is True
        assert 88 <= rec["suggested_weight"] <= 92  # ~90%


def test_workout_layoff_resume_lighter():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid, rpe, sets = ex["exercise_id"], ex["target_rpe"] or 8.0, ex["target_sets"]

        log_session(client, h, eid, days_ago=20,
                    sets=[(100, low, rpe, False)] * sets, program_day_id=day_id)

        rec = find_exercise(
            client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json(), eid
        )
        assert rec["action"] == "hold"
        assert rec["suggested_weight"] < 100  # ~93%
        assert "esuming" in rec["reason"]  # "Resuming after N days off ..."


def test_workout_warmups_excluded_and_rpe_none():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid, sets = ex["exercise_id"], ex["target_sets"]

        # RPE omitted (None) throughout; a heavier warm-up must not become the top set.
        log_session(client, h, eid, days_ago=6,
                    sets=[(100, low, None, False)] * sets, program_day_id=day_id)
        working = [(100, high, None, False)] * sets
        working.append((130, 2, None, True))  # heavy warm-up
        log_session(client, h, eid, days_ago=2, sets=working, program_day_id=day_id)

        rec = find_exercise(
            client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json(), eid
        )
        assert rec["last_performance"]["weight"] == 100  # warm-up (130) excluded
        assert rec["last_performance"]["rpe"] is None
        assert rec["action"] == "increase"  # progresses even without RPE logged


def test_workout_zero_weight_bodyweight_no_crash():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)
        eid = ex["exercise_id"]

        for d in (4, 2):
            log_session(client, h, eid, days_ago=d,
                        sets=[(0, 20, None, False)], program_day_id=day_id)

        rec = find_exercise(
            client.get("/api/recommendations/workout", params={"program_day_id": day_id}).json(), eid
        )
        assert rec["action"] == "hold"
        assert rec["suggested_weight"] == 0
        assert rec["last_performance"]["weight"] == 0


def test_workout_program_day_override_and_404():
    with new_client_with_profile() as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        day_id, ex, low, high = day0_first_exercise(client)

        ok = client.get("/api/recommendations/workout", params={"program_day_id": day_id})
        assert ok.status_code == 200
        assert ok.json()["program_day_id"] == day_id

        bad = client.get("/api/recommendations/workout", params={"program_day_id": 99999999})
        assert bad.status_code == 404


def test_workout_no_active_program_state():
    with new_client_with_profile() as client:
        block = client.get("/api/recommendations/workout").json()
        assert block["rest_day"] is False
        assert block["exercises"] == []
        assert "program" in block["reason"].lower()
        assert block["adherence"]["scheduled_days_per_week"] == 0


def test_workout_rest_day_state(monkeypatch):
    class _FrozenDateTime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 7, 12, 0, 0)  # a Tuesday

    with new_client_with_profile(training_goal="maingain", days_per_week=1) as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=1)  # schedules weekday 0 (Monday) only
        # Freeze "today" to a Tuesday so a 1-day program yields a rest day.
        monkeypatch.setattr(adaptive_service, "datetime", _FrozenDateTime)
        block = client.get("/api/recommendations/workout").json()
        assert block["rest_day"] is True
        assert block["exercises"] == []
        assert block["name"] is None


# ===========================================================================
# Unified envelope + isolation
# ===========================================================================
def test_adaptive_envelope_shape():
    with new_client_with_profile(goal="gain") as client:
        h = csrf_headers(client)
        generate_program(client, h, days_per_week=4)
        client.post("/api/nutrition/plan/generate", headers=h)
        client.post("/api/admin/seed-demo", params={"days": 21}, headers=h)

        env = client.get("/api/recommendations/adaptive").json()
        assert set(env) == {"version", "algorithm", "generated_at", "meals", "workout", "tip"}
        assert env["version"] == "adaptive-v1"
        assert env["algorithm"] == "history-adaptive-deterministic"
        assert env["tip"] and isinstance(env["tip"], str)

        meals = env["meals"]
        assert set(meals) >= {
            "version", "algorithm", "targets", "consumed", "remaining",
            "next_meal", "history_basis", "confidence", "suggestions",
        }
        for block_name in ("targets", "consumed", "remaining"):
            assert set(meals[block_name]) == {"kcal", "protein_g", "carbs_g", "fat_g"}
        assert meals["confidence"] in ("low", "medium", "high")

        workout = env["workout"]
        assert set(workout) >= {
            "version", "rest_day", "deload", "confidence", "adherence", "reason", "exercises"
        }
        assert workout["adherence"]["consistency"] in ("on_track", "inconsistent", "returning")
        if workout["exercises"]:
            rec = workout["exercises"][0]
            assert rec["action"] in ("start", "increase", "hold", "reduce", "deload")
            assert rec["confidence"] in ("low", "medium", "high")
            assert rec["reason"] and rec["history_basis"]
            assert set(rec["change"]) == {"weight_delta_kg", "reps_delta", "direction"}


def test_adaptive_requires_profile():
    with TestClient(app) as client:
        make_user(client)  # no profile set
        assert client.get("/api/recommendations/adaptive").status_code == 400
        assert client.get("/api/recommendations/meals").status_code == 400
        # The workout block does not depend on a profile (mirrors programs/today).
        assert client.get("/api/recommendations/workout").status_code == 200


def test_adaptive_per_user_isolation():
    with new_client_with_profile() as alice, new_client_with_profile() as bob:
        ha = csrf_headers(alice)
        generate_program(alice, ha, days_per_week=4)
        alice.post("/api/nutrition/plan/generate", headers=ha)
        for d in (1, 2, 3, 4, 5):
            log_meal(alice, ha, "Alice special", 500, "dinner", 40, 40, 15, days_ago=d)
        day_id, ex, low, high = day0_first_exercise(alice)
        log_session(alice, ha, ex["exercise_id"], days_ago=2,
                    sets=[(100, high, 8.0, False)] * ex["target_sets"], program_day_id=day_id)

        # Bob sees none of Alice's foods and has no program.
        bob_meals = bob.get("/api/recommendations/meals", params={"limit": 5}).json()
        assert not find_meal(bob_meals["suggestions"], "Alice special")
        assert all(s["logged_count"] == 0 for s in bob_meals["suggestions"])
        assert bob_meals["history_basis"]["total_meals"] == 0

        bob_workout = bob.get("/api/recommendations/workout").json()
        assert bob_workout["exercises"] == []

        # Alice still sees her own history.
        alice_meals = alice.get("/api/recommendations/meals", params={"limit": 5}).json()
        assert find_meal(alice_meals["suggestions"], "Alice special")
