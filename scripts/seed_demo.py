r"""(Re)seed FitPath's three demo accounts with rich, backdated, persona-appropriate data.

Deterministic + idempotent: on each run it deletes the existing demo users (which
cascades away all their data) and recreates them from scratch with the same
credentials, then replays realistic history **through the live API** (FastAPI
``TestClient``) so every row passes the same validation and CSRF checks a real
client would. Because it goes through ``POST /api/workouts`` with a real ``date``
it also exercises the workout-backdating fix.

Personas (username / password):
  * alex_cut       / FitPathDemo!1  — cutting + powerlifting, 4-day Upper/Lower,
                                       ~3 weeks of SBD work on distinct dates
                                       (e1RM held on a deficit), high steps,
                                       bodyweight trending down.
  * sam_bulk       / FitPathDemo!2  — bulking + hypertrophy, 6-day PPL, ~3 weeks
                                       of high-volume double-progression, surplus
                                       meals, bodyweight up.
  * jordan_maingain/ FitPathDemo!3  — maingaining + inconsistent, home_basic
                                       (dumbbell/bodyweight program), ~4 weeks of
                                       sparse/gappy sessions & meals, weight stable.

Run against the real database::

    .\.venv\Scripts\python.exe scripts\seed_demo.py

Honours ``FITPATH_DB`` if set (otherwise the repo's ``fitpath.sqlite3``).
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Make ``import app`` work when run as a script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    MealLog,
    SetLog,
    StepLog,
    User,
    WeightLog,
    WorkoutSession,
)
from app.seed_exercises import seed_exercises  # noqa: E402


# ---------------------------------------------------------------------------
# Persona configuration
# ---------------------------------------------------------------------------
PERSONAS = [
    {
        "username": "alex_cut",
        "email": "alex.cut@fitpath.demo",
        "password": "FitPathDemo!1",
        "seed": 201,
        "weeks": 3,
        "train_weekdays": [0, 1, 3, 4],  # Mon/Tue/Thu/Fri = 4-day U/L
        "profile": {
            "name": "Alex", "sex": "male", "age": 30, "height_cm": 178,
            "weight_kg": 86, "activity_level": "active", "goal": "lose",
            "training_goal": "powerlifting", "experience_level": "advanced",
            "days_per_week": 4, "equipment": "full_gym", "units": "metric",
            "wake_time": "06:30", "step_goal": 12000,
        },
        "strength_factor": 1.35,
        "weekly_gain": 0.0,          # strength maintained on a deficit
        "rep_style": "low",
        "meal_prob": 0.97,
        "menu": [
            ("Egg-white oats & berries", "breakfast", 470, 38, 60, 10, 8),
            ("Chicken, rice & broccoli", "lunch", 620, 55, 72, 13, 13),
            ("Protein shake & banana", "snack", 300, 35, 35, 3, 16),
            ("Sirloin steak & potatoes", "dinner", 690, 60, 55, 22, 19),
            ("Low-fat Greek yogurt", "snack", 210, 24, 18, 2, 21),
        ],
        "steps": (10500, 14000),
        "weight_start": 87.2, "weight_end": 85.0, "weight_every": 2,
    },
    {
        "username": "sam_bulk",
        "email": "sam.bulk@fitpath.demo",
        "password": "FitPathDemo!2",
        "seed": 202,
        "weeks": 3,
        "train_weekdays": [0, 1, 2, 3, 4, 5],  # 6-day PPL
        "profile": {
            "name": "Sam", "sex": "male", "age": 24, "height_cm": 180,
            "weight_kg": 78, "activity_level": "moderate", "goal": "gain",
            "training_goal": "hypertrophy", "experience_level": "intermediate",
            "days_per_week": 6, "equipment": "full_gym", "units": "metric",
            "wake_time": "07:30", "step_goal": 9000,
        },
        "strength_factor": 1.0,
        "weekly_gain": 0.03,         # double-progression: loads creep up
        "rep_style": "double",
        "meal_prob": 1.0,
        "menu": [
            ("Oats, whey & peanut butter", "breakfast", 720, 40, 88, 24, 8),
            ("Rice bowl, chicken & avocado", "lunch", 820, 46, 90, 28, 13),
            ("Mass gainer shake", "snack", 560, 36, 80, 10, 16),
            ("Salmon, pasta & olive oil", "dinner", 780, 42, 82, 26, 19),
            ("Trail mix & whole milk", "snack", 300, 14, 32, 14, 21),
        ],
        "steps": (7000, 10500),
        "weight_start": 77.0, "weight_end": 79.2, "weight_every": 2,
    },
    {
        "username": "jordan_maingain",
        "email": "jordan.maingain@fitpath.demo",
        "password": "FitPathDemo!3",
        "seed": 203,
        "weeks": 4,
        # Sparse, gappy schedule (per-week weekday lists) — the inconsistent lifter.
        "weekly_schedule": [[1, 4], [2], [0, 3], [5]],
        "profile": {
            "name": "Jordan", "sex": "female", "age": 28, "height_cm": 166,
            "weight_kg": 64, "activity_level": "light", "goal": "maintain",
            "training_goal": "maingain", "experience_level": "beginner",
            "days_per_week": 3, "equipment": "home_basic", "units": "metric",
            "wake_time": "07:00", "step_goal": 8000,
        },
        "strength_factor": 0.62,
        "weekly_gain": 0.004,        # essentially flat — maintaining
        "rep_style": "moderate",
        "meal_prob": 0.5,            # gappy meal logging
        "menu": [
            ("Greek yogurt, granola & berries", "breakfast", 380, 22, 52, 9, 8),
            ("Turkey & hummus wrap", "lunch", 520, 30, 58, 16, 13),
            ("Apple & peanut butter", "snack", 220, 7, 26, 12, 16),
            ("Tofu veggie stir-fry & rice", "dinner", 600, 28, 78, 16, 19),
        ],
        "steps": (4800, 9000),
        "weight_start": 64.1, "weight_end": 63.9, "weight_every": 4,
    },
]

# Intermediate-male baseline top-set working weights (kg); other lifts fall back
# to an equipment/category estimate. Scaled per persona by ``strength_factor``.
NAME_BASE = {
    "Back Squat": 120, "Front Squat": 95, "Deadlift": 155, "Sumo Deadlift": 150,
    "Romanian Deadlift": 120, "Bench Press": 92, "Incline Bench Press": 74,
    "Close-Grip Bench Press": 78, "Overhead Press": 56, "Barbell Row": 82,
    "T-Bar Row": 70, "Hip Thrust": 140, "Good Morning": 70, "Leg Press": 200,
    "Hack Squat": 120, "Barbell Curl": 34, "Barbell Shrug": 90, "Upright Row": 42,
    "Weighted Pull-Up": 15,
}
EQUIP_CAT_BASE = {
    ("barbell", "compound"): 85, ("barbell", "isolation"): 32,
    ("dumbbell", "compound"): 26, ("dumbbell", "isolation"): 12,
    ("machine", "compound"): 105, ("machine", "isolation"): 45,
    ("cable", "compound"): 45, ("cable", "isolation"): 24,
    ("ez_bar", "compound"): 40, ("ez_bar", "isolation"): 26,
    ("bodyweight", "compound"): 0, ("bodyweight", "isolation"): 0,
}


def _round_2p5(x: float) -> float:
    return round(x / 2.5) * 2.5


def _base_weight(name: str, meta: dict) -> float:
    if name in NAME_BASE:
        return float(NAME_BASE[name])
    return float(EQUIP_CAT_BASE.get((meta.get("equipment"), meta.get("category")), 30))


def _rep_range(target_reps: str) -> tuple[int, int]:
    parts = [p for p in target_reps.replace(" ", "").split("-") if p.isdigit()]
    if not parts:
        return 8, 12
    low = int(parts[0])
    high = int(parts[1]) if len(parts) > 1 else low
    return low, max(low, high)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("fitpath_csrf")
    return {"X-CSRF-Token": token} if token else {}


def _iso_dt(d: date, hour: int, minute: int) -> str:
    return datetime.combine(d, time.min).replace(hour=hour, minute=minute).isoformat()


def _delete_existing_demo_users() -> list[str]:
    usernames = [p["username"] for p in PERSONAS]
    removed = []
    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.username.in_(usernames))).all()
        for u in users:
            removed.append(u.username)
            db.delete(u)  # ON DELETE CASCADE clears profile/logs/workouts/etc.
        db.commit()
    return removed


def _training_dates(persona: dict, today: date) -> list[date]:
    weeks = persona["weeks"]
    start_monday = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    dates: list[date] = []
    for w in range(weeks):
        if "weekly_schedule" in persona:
            offsets = persona["weekly_schedule"][w]
        else:
            offsets = persona["train_weekdays"]
        for off in offsets:
            d = start_monday + timedelta(days=7 * w + off)
            if d <= today:
                dates.append(d)
    return sorted(set(dates))


def _log_session(
    client: TestClient, headers: dict, d: date, day: dict, week: int,
    persona: dict, catalog: dict, rng: random.Random,
) -> int:
    """Create one backdated workout session and its sets. Returns working-set count."""
    resp = client.post(
        "/api/workouts",
        json={"date": d.isoformat(), "name": day["name"],
              "program_day_id": day["id"]},
        headers=headers,
    )
    resp.raise_for_status()
    wid = resp.json()["id"]

    factor = persona["strength_factor"]
    gain = persona["weekly_gain"]
    style = persona["rep_style"]
    working = 0
    warmed_up = False

    for ex in day["exercises"]:
        meta = catalog.get(ex["exercise_id"], {})
        base = _base_weight(ex["name"], meta)
        low, high = _rep_range(ex["target_reps"])
        if style == "low":
            reps = low
        elif style == "double":
            reps = min(high, low + (week % (high - low + 1))) if high > low else low
        else:  # moderate
            reps = min(high, low + rng.randint(0, max(0, high - low)))

        if base > 0:
            weight = _round_2p5(
                max(2.5, base * factor * (1 + gain * week) + rng.uniform(-2.0, 2.0))
            )
        else:
            weight = 0.0  # bodyweight movement — logged as reps only

        # One warm-up on the first loaded compound (excluded from volume/PRs).
        if not warmed_up and base > 0 and meta.get("category") == "compound":
            client.post(
                f"/api/workouts/{wid}/sets",
                json={"exercise_id": ex["exercise_id"],
                      "weight": _round_2p5(weight * 0.6), "reps": 5,
                      "is_warmup": True},
                headers=headers,
            )
            warmed_up = True

        for _ in range(max(1, ex["target_sets"])):
            client.post(
                f"/api/workouts/{wid}/sets",
                json={
                    "exercise_id": ex["exercise_id"],
                    "weight": weight,
                    "reps": reps,
                    "rpe": round(rng.uniform(7.0, 9.0), 1),
                },
                headers=headers,
            )
            working += 1
    return working


def _log_day_logs(
    client: TestClient, headers: dict, d: date, persona: dict, rng: random.Random,
) -> int:
    """Meals + steps + sleep + water for a single (backdated) day."""
    logged_meals = 0
    if rng.random() < persona["meal_prob"]:
        for (name, cat, kcal, p, c, f, hour) in persona["menu"]:
            # Inconsistent personas sometimes skip a meal entirely.
            if persona["meal_prob"] < 0.9 and rng.random() < 0.35:
                continue
            scale = rng.uniform(0.93, 1.07)
            client.post(
                "/api/logs/meals",
                json={
                    "name": name, "category": cat,
                    "kcal": round(kcal * scale),
                    "protein_g": round(p * scale, 1),
                    "carbs_g": round(c * scale, 1),
                    "fat_g": round(f * scale, 1),
                    "eaten_at": _iso_dt(d, hour, rng.randint(0, 55)),
                },
                headers=headers,
            )
            logged_meals += 1
        # A couple of water logs on days we ate.
        for hour in (10, 15, 20):
            if rng.random() < 0.7:
                client.post(
                    "/api/logs/water",
                    json={"ml": rng.choice([250, 300, 500]),
                          "logged_at": _iso_dt(d, hour, rng.randint(0, 55))},
                    headers=headers,
                )

    lo, hi = persona["steps"]
    client.post("/api/logs/steps",
                json={"steps": rng.randint(lo, hi), "logged_for": d.isoformat()},
                headers=headers)

    if rng.random() < (0.9 if persona["meal_prob"] > 0.9 else 0.55):
        client.post(
            "/api/logs/sleep",
            json={"hours": round(rng.uniform(6.3, 8.4), 1),
                  "wake_time": persona["profile"]["wake_time"],
                  "logged_for": d.isoformat()},
            headers=headers,
        )
    return logged_meals


def seed_persona(client: TestClient, persona: dict, today: date) -> dict:
    rng = random.Random(persona["seed"])

    # Register (sets cookies) — fall back to login if somehow present.
    reg = client.post("/api/auth/register", json={
        "email": persona["email"], "username": persona["username"],
        "password": persona["password"],
    })
    if reg.status_code == 409:
        client.post("/api/auth/login", json={
            "identifier": persona["username"], "password": persona["password"]})
    h = _csrf(client)

    # Profile + generated program + nutrition plan.
    client.put("/api/profile", json=persona["profile"], headers=h).raise_for_status()
    client.post("/api/programs/generate", json={}, headers=h).raise_for_status()
    client.post("/api/nutrition/plan/generate", headers=h).raise_for_status()

    program = client.get("/api/programs/active").json()
    days = program["days"]

    catalog = {
        e["id"]: e
        for e in client.get("/api/exercises", params={"limit": 500}).json()["items"]
    }

    train_dates = _training_dates(persona, today)
    start_day = min(train_dates) if train_dates else today - timedelta(days=7)
    total_days = (today - start_day).days + 1

    # Workouts on the persona's training dates (cycling the program days).
    sets_total = 0
    for i, d in enumerate(sorted(train_dates)):
        day = days[i % len(days)]
        week = (d - start_day).days // 7
        sets_total += _log_session(client, h, d, day, week, persona, catalog, rng)

    # Daily logs (meals/steps/sleep/water) + periodic weight.
    meals_total = 0
    for offset in range(total_days):
        d = start_day + timedelta(days=offset)
        frac = offset / max(1, total_days - 1)
        meals_total += _log_day_logs(client, h, d, persona, rng)
        if offset % persona["weight_every"] == 0 or d == today:
            w = persona["weight_start"] + (persona["weight_end"] - persona["weight_start"]) * frac
            client.post(
                "/api/logs/weight",
                json={"weight_kg": round(w + rng.uniform(-0.2, 0.2), 1),
                      "logged_for": d.isoformat()},
                headers=h,
            )

    # Log out so the next persona starts with a clean cookie jar.
    client.post("/api/auth/logout", headers=_csrf(client))
    return {"sessions": len(train_dates), "sets": sets_total, "meals": meals_total}


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify_persona(client: TestClient, persona: dict) -> dict:
    r = client.post("/api/auth/login", json={
        "identifier": persona["username"], "password": persona["password"]})
    login_ok = r.status_code == 200

    prs = client.get("/api/performance/prs").json()["items"]
    summary = client.get("/api/performance/summary").json()
    trend_points = 0
    trend_lift = None
    if prs:
        top = prs[0]
        perf = client.get(f"/api/performance/exercise/{top['exercise_id']}").json()
        trend_points = len(perf["e1rm_trend"])
        trend_lift = top["exercise_name"]

    heatmap = client.get("/api/insights/heatmap", params={"days": 84}).json()["days"]
    active_days = sum(1 for d in heatmap if d["level"] > 0)
    streaks = client.get("/api/insights/streaks").json()

    client.post("/api/auth/logout", headers=_csrf(client))
    return {
        "login_ok": login_ok,
        "prs_count": summary.get("prs_count"),
        "prs_items": len(prs),
        "sessions_count": summary.get("sessions_count"),
        "trend_lift": trend_lift,
        "trend_points": trend_points,
        "heatmap_active_days": active_days,
        "workout_streak": streaks.get("workout_streak"),
        "any_streak": streaks.get("any_streak"),
    }


def _db_counts(username: str) -> dict:
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.username == username))
        if uid is None:
            return {}
        workouts = db.scalar(
            select(func.count(WorkoutSession.id)).where(WorkoutSession.user_id == uid))
        sets = db.scalar(
            select(func.count(SetLog.id))
            .join(WorkoutSession, SetLog.workout_session_id == WorkoutSession.id)
            .where(WorkoutSession.user_id == uid))
        meals = db.scalar(select(func.count(MealLog.id)).where(MealLog.user_id == uid))
        steps = db.scalar(select(func.count(StepLog.id)).where(StepLog.user_id == uid))
        weights = db.scalar(select(func.count(WeightLog.id)).where(WeightLog.user_id == uid))
        return {"workouts": workouts, "sets": sets, "meals": meals,
                "steps_days": steps, "weight_logs": weights}


def main() -> None:
    today = date.today()
    print("Seeding FitPath demo accounts (via live API)...\n")

    with TestClient(app) as client:
        with SessionLocal() as db:  # ensure catalog present (startup also seeds)
            seed_exercises(db)

        removed = _delete_existing_demo_users()
        if removed:
            print(f"Removed existing demo users: {', '.join(removed)}\n")

        results = {p["username"]: seed_persona(client, p, today) for p in PERSONAS}

        print("Per-account results:\n" + "=" * 68)
        all_ok = True
        for p in PERSONAS:
            name = p["username"]
            counts = _db_counts(name)
            v = verify_persona(client, p)
            ok = (
                v["login_ok"]
                and v["trend_points"] >= 2
                and v["heatmap_active_days"] >= 1
                and v["prs_count"] == v["prs_items"]
            )
            all_ok = all_ok and ok
            print(f"\n{name}  ({'OK' if ok else 'CHECK'})")
            print(f"  seeded : {results[name]['sessions']} sessions, "
                  f"{results[name]['sets']} working sets, {results[name]['meals']} meals")
            print(f"  db     : {counts}")
            print(f"  login  : {v['login_ok']}")
            print(f"  perf   : sessions={v['sessions_count']} prs_count={v['prs_count']} "
                  f"(== /prs items {v['prs_items']}: {v['prs_count'] == v['prs_items']})")
            print(f"  e1RM   : {v['trend_lift']} has {v['trend_points']} dated points")
            print(f"  heatmap: {v['heatmap_active_days']} active days")
            print(f"  streaks: workout={v['workout_streak']} any={v['any_streak']}")

        print("\n" + "=" * 68)
        print("ALL ACCOUNTS OK" if all_ok else "SOME ACCOUNTS NEED ATTENTION")
        if not all_ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
