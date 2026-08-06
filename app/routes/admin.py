"""Admin / demo helpers, scoped to the current user (contract §11)."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import (
    ActivityLog,
    Exercise,
    HealthImportBatch,
    ImportedHealthRecord,
    MealLog,
    Profile,
    SetLog,
    SleepLog,
    StepLog,
    User,
    WaterLog,
    WeightLog,
    WorkoutSession,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_LOG_MODELS = (MealLog, ActivityLog, SleepLog, StepLog, WaterLog, WeightLog)


def _clear_user_logs(db: Session, user_id: int) -> None:
    db.execute(delete(ImportedHealthRecord).where(ImportedHealthRecord.user_id == user_id))
    db.execute(delete(HealthImportBatch).where(HealthImportBatch.user_id == user_id))
    for model in _LOG_MODELS:
        db.execute(delete(model).where(model.user_id == user_id))
    # Workout sessions cascade to their set logs at the DB level.
    db.execute(delete(WorkoutSession).where(WorkoutSession.user_id == user_id))


@router.post("/seed-demo")
def seed_demo(
    days: int = Query(default=14, ge=2, le=90),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Populate the past N days with realistic logs for the current user."""
    rng = random.Random(42)
    today = date.today()
    start = today - timedelta(days=days - 1)

    _clear_user_logs(db, user.id)

    meals_catalog = [
        ("breakfast", [("Oats & berries", 420, 14, 70, 9),
                       ("Avocado toast", 380, 12, 42, 18),
                       ("Greek yogurt parfait", 320, 22, 38, 8),
                       ("Protein smoothie", 350, 30, 35, 7)]),
        ("lunch", [("Chicken bowl", 620, 45, 60, 18),
                   ("Turkey wrap", 540, 32, 55, 20),
                   ("Salmon salad", 580, 38, 28, 32),
                   ("Veggie burrito", 660, 22, 88, 22)]),
        ("dinner", [("Stir-fry tofu", 680, 35, 70, 25),
                    ("Steak & potatoes", 820, 55, 55, 35),
                    ("Pasta bolognese", 760, 38, 90, 22),
                    ("Sushi platter", 640, 30, 80, 16)]),
        ("snack", [("Apple & PB", 220, 6, 28, 10),
                   ("Almonds", 180, 6, 6, 16),
                   ("Protein bar", 210, 20, 22, 7),
                   ("Greek yogurt", 120, 15, 12, 0)]),
    ]
    activities = [
        ("walk", (20, 50), "moderate"),
        ("run", (20, 45), "vigorous"),
        ("yoga", (25, 60), "light"),
        ("strength", (30, 60), "vigorous"),
        ("cycling", (30, 75), "moderate"),
    ]

    profile = db.get(Profile, user.id)
    base_weight = float(profile.weight_kg) if profile else None

    # Main lifts for demo workouts (only if the catalog is seeded).
    main_lifts = db.scalars(
        select(Exercise).where(
            Exercise.name.in_(["Back Squat", "Bench Press", "Deadlift", "Overhead Press"])
        )
    ).all()
    lift_base = {"Back Squat": 100.0, "Bench Press": 70.0, "Deadlift": 130.0, "Overhead Press": 45.0}

    for offset in range(days):
        d = start + timedelta(days=offset)
        is_today = d == today

        for slot_idx, (cat, options) in enumerate(meals_catalog):
            if cat == "snack" and rng.random() < 0.45:
                continue
            if is_today and slot_idx >= 2:
                continue
            name, kcal, p, c, f = rng.choice(options)
            kcal_var = int(kcal * rng.uniform(0.85, 1.1))
            hour = {"breakfast": 8, "lunch": 13, "dinner": 19, "snack": 16}[cat] + rng.randint(-1, 1)
            eaten_at = datetime.combine(d, datetime.min.time()).replace(
                hour=hour, minute=rng.randint(0, 59)
            )
            db.add(MealLog(
                user_id=user.id, name=name, kcal=kcal_var, eaten_at=eaten_at,
                category=cat, protein_g=p, carbs_g=c, fat_g=f,
            ))

        if rng.random() < 0.75:
            act, (lo, hi), intensity = rng.choice(activities)
            done_at = datetime.combine(d, datetime.min.time()).replace(
                hour=rng.randint(6, 20), minute=rng.randint(0, 59)
            )
            db.add(ActivityLog(
                user_id=user.id, activity=act, minutes=rng.randint(lo, hi),
                intensity=intensity, done_at=done_at,
            ))

        db.add(SleepLog(
            user_id=user.id, hours=round(rng.uniform(6.0, 8.5), 1),
            wake_time=f"{rng.randint(6, 8):02d}:{rng.choice([0, 15, 30, 45]):02d}",
            logged_for=d,
        ))

        steps = rng.randint(4000, 12000)
        if is_today:
            steps = int(steps * 0.45)
        db.add(StepLog(user_id=user.id, steps=steps, logged_for=d))

        sips = rng.randint(4, 8) if not is_today else rng.randint(2, 4)
        for s in range(sips):
            hour = min(7 + s * 2 + rng.randint(0, 1), 22)
            logged_at = datetime.combine(d, datetime.min.time()).replace(
                hour=hour, minute=rng.randint(0, 59)
            )
            db.add(WaterLog(user_id=user.id, ml=rng.choice([200, 250, 300, 500]), logged_at=logged_at))

        if base_weight is not None and (offset % 2 == 0 or is_today):
            drift = (offset - days / 2) * 0.03 + rng.uniform(-0.15, 0.15)
            db.add(WeightLog(user_id=user.id, weight_kg=round(base_weight + drift, 1), logged_for=d))

        # ~3x/week strength sessions with progressing main lifts.
        if main_lifts and offset % 2 == 0 and not is_today:
            session = WorkoutSession(user_id=user.id, date=d, name="Full Body")
            db.add(session)
            db.flush()
            week = offset // 7
            set_index = 0
            for ex in main_lifts[:2 + (offset // 7) % 2]:
                base = lift_base.get(ex.name, 60.0) + week * 2.5
                for _ in range(3):
                    db.add(SetLog(
                        workout_session_id=session.id, exercise_id=ex.id,
                        set_index=set_index, weight=round(base, 1), reps=5,
                        rpe=round(rng.uniform(7.0, 8.5), 1), is_warmup=False,
                    ))
                    set_index += 1

    db.flush()
    return {"ok": True, "days_seeded": days}


@router.post("/reset")
def reset(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Delete the current user's logs + workouts (keeps the profile)."""
    _clear_user_logs(db, user.id)
    return {"ok": True, "message": "all logs cleared"}
