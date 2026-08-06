"""Nutrition / health log routes (contract §4).

Every resource is plural, user-scoped, and supports full CRUD. Ownership is
enforced on mutations: a row that isn't the current user's yields ``404``.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import (
    ActivityLog,
    MealLog,
    SleepLog,
    StepLog,
    User,
    WaterLog,
    WeightLog,
)
from ..schemas import ActivityIn, MealIn, SleepIn, StepsIn, WaterIn, WeightIn

router = APIRouter(prefix="/api/logs", tags=["logs"])


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def meal_public(m: MealLog) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "kcal": m.kcal,
        "category": m.category,
        "protein_g": m.protein_g,
        "carbs_g": m.carbs_g,
        "fat_g": m.fat_g,
        "eaten_at": m.eaten_at.isoformat(timespec="minutes"),
        "favorite": m.favorite,
    }


def activity_public(a: ActivityLog) -> dict:
    return {
        "id": a.id,
        "activity": a.activity,
        "minutes": a.minutes,
        "intensity": a.intensity,
        "done_at": a.done_at.isoformat(timespec="minutes"),
    }


def sleep_public(s: SleepLog) -> dict:
    return {
        "id": s.id,
        "hours": s.hours,
        "wake_time": s.wake_time,
        "logged_for": s.logged_for.isoformat(),
    }


def steps_public(s: StepLog) -> dict:
    return {"id": s.id, "steps": s.steps, "logged_for": s.logged_for.isoformat()}


def water_public(w: WaterLog) -> dict:
    return {"id": w.id, "ml": w.ml, "logged_at": w.logged_at.isoformat(timespec="minutes")}


def weight_public(w: WeightLog) -> dict:
    return {"id": w.id, "weight_kg": w.weight_kg, "logged_for": w.logged_for.isoformat()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min)
    return start, start + timedelta(days=1)


def _owned_or_404(db: Session, model, obj_id: int, user_id: int):
    obj = db.get(model, obj_id)
    if obj is None or obj.user_id != user_id:
        raise HTTPException(status_code=404, detail="not found")
    return obj


# ---------------------------------------------------------------------------
# Meals
# ---------------------------------------------------------------------------
@router.post("/meals")
def create_meal(
    m: MealIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    meal = MealLog(
        user_id=user.id,
        name=m.name,
        kcal=m.kcal,
        category=m.category,
        protein_g=m.protein_g,
        carbs_g=m.carbs_g,
        fat_g=m.fat_g,
        eaten_at=m.eaten_at or datetime.now(),
    )
    db.add(meal)
    db.flush()
    return meal_public(meal)


@router.get("/meals")
def list_meals(
    date: Optional[date] = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    day = date or datetime.now().date()
    start, end = _day_bounds(day)
    rows = db.scalars(
        select(MealLog)
        .where(
            MealLog.user_id == user.id,
            MealLog.eaten_at >= start,
            MealLog.eaten_at < end,
        )
        .order_by(MealLog.eaten_at)
    ).all()
    return {"items": [meal_public(m) for m in rows]}


@router.get("/meals/recent")
def recent_meals(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Recent + favorite + frequent meals for the quick re-log picker."""
    rows = db.scalars(
        select(MealLog)
        .where(MealLog.user_id == user.id)
        .order_by(MealLog.eaten_at.desc())
    ).all()

    groups: dict[tuple[str, str], dict] = {}
    for m in rows:  # newest-first, so first hit for a key is the most recent
        key = (m.name.lower(), m.category)
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "name": m.name,
                "category": m.category,
                "kcal": m.kcal,
                "protein_g": m.protein_g,
                "carbs_g": m.carbs_g,
                "fat_g": m.fat_g,
                "last_at": m.eaten_at,
                "times": 1,
                "favorite": bool(m.favorite),
            }
        else:
            g["times"] += 1
            g["favorite"] = g["favorite"] or bool(m.favorite)

    def serialize(g: dict) -> dict:
        return {**g, "last_at": g["last_at"].isoformat(timespec="minutes")}

    all_groups = list(groups.values())
    recent = sorted(all_groups, key=lambda g: g["last_at"], reverse=True)[:limit]
    favorites = sorted(
        (g for g in all_groups if g["favorite"]),
        key=lambda g: g["last_at"],
        reverse=True,
    )[:limit]
    frequent = sorted(
        (g for g in all_groups if g["times"] >= 2),
        key=lambda g: (g["times"], g["last_at"]),
        reverse=True,
    )[:limit]
    return {
        "recent": [serialize(g) for g in recent],
        "favorites": [serialize(g) for g in favorites],
        "frequent": [serialize(g) for g in frequent],
    }


@router.put("/meals/{meal_id}")
def update_meal(
    meal_id: int,
    m: MealIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    meal = _owned_or_404(db, MealLog, meal_id, user.id)
    meal.name = m.name
    meal.kcal = m.kcal
    meal.category = m.category
    meal.protein_g = m.protein_g
    meal.carbs_g = m.carbs_g
    meal.fat_g = m.fat_g
    if m.eaten_at is not None:
        meal.eaten_at = m.eaten_at
    db.flush()
    return meal_public(meal)


@router.delete("/meals/{meal_id}")
def delete_meal(
    meal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    meal = _owned_or_404(db, MealLog, meal_id, user.id)
    db.delete(meal)
    return {"ok": True}


@router.post("/meals/{meal_id}/favorite")
def toggle_meal_favorite(
    meal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    meal = _owned_or_404(db, MealLog, meal_id, user.id)
    new_fav = not meal.favorite
    # Toggle every same-named meal for this user so the pick stays consistent.
    same = db.scalars(
        select(MealLog).where(
            MealLog.user_id == user.id, MealLog.name.ilike(meal.name)
        )
    ).all()
    for row in same:
        row.favorite = new_fav
    db.flush()
    return {"ok": True, "name": meal.name, "favorite": new_fav}


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------
@router.post("/activities")
def create_activity(
    a: ActivityIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    act = ActivityLog(
        user_id=user.id,
        activity=a.activity,
        minutes=a.minutes,
        intensity=a.intensity,
        done_at=a.done_at or datetime.now(),
    )
    db.add(act)
    db.flush()
    return activity_public(act)


@router.get("/activities")
def list_activities(
    date: Optional[date] = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    day = date or datetime.now().date()
    start, end = _day_bounds(day)
    rows = db.scalars(
        select(ActivityLog)
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.done_at >= start,
            ActivityLog.done_at < end,
        )
        .order_by(ActivityLog.done_at)
    ).all()
    return {"items": [activity_public(a) for a in rows]}


@router.put("/activities/{activity_id}")
def update_activity(
    activity_id: int,
    a: ActivityIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    act = _owned_or_404(db, ActivityLog, activity_id, user.id)
    act.activity = a.activity
    act.minutes = a.minutes
    act.intensity = a.intensity
    if a.done_at is not None:
        act.done_at = a.done_at
    db.flush()
    return activity_public(act)


@router.delete("/activities/{activity_id}")
def delete_activity(
    activity_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    act = _owned_or_404(db, ActivityLog, activity_id, user.id)
    db.delete(act)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------
@router.post("/sleep")
def create_sleep(
    s: SleepIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    row = SleepLog(
        user_id=user.id,
        hours=s.hours,
        wake_time=s.wake_time,
        logged_for=s.logged_for or date.today(),
    )
    db.add(row)
    db.flush()
    return sleep_public(row)


@router.get("/sleep")
def list_sleep(
    date: Optional[date] = Query(default=None),
    limit: int = Query(default=90, ge=1, le=365),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(SleepLog).where(SleepLog.user_id == user.id)
    if date is not None:
        stmt = stmt.where(SleepLog.logged_for == date)
    rows = db.scalars(
        stmt.order_by(SleepLog.logged_for.desc(), SleepLog.id.desc()).limit(limit)
    ).all()
    return {"items": [sleep_public(s) for s in rows]}


@router.put("/sleep/{sleep_id}")
def update_sleep(
    sleep_id: int,
    s: SleepIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = _owned_or_404(db, SleepLog, sleep_id, user.id)
    row.hours = s.hours
    row.wake_time = s.wake_time
    if s.logged_for is not None:
        row.logged_for = s.logged_for
    db.flush()
    return sleep_public(row)


@router.delete("/sleep/{sleep_id}")
def delete_sleep(
    sleep_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    row = _owned_or_404(db, SleepLog, sleep_id, user.id)
    db.delete(row)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Steps (one row per day — upsert)
# ---------------------------------------------------------------------------
@router.post("/steps")
def upsert_steps(
    s: StepsIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    day = s.logged_for or date.today()
    row = db.scalar(
        select(StepLog).where(
            StepLog.user_id == user.id, StepLog.logged_for == day
        )
    )
    if row is None:
        row = StepLog(user_id=user.id, steps=s.steps, logged_for=day)
        db.add(row)
    else:
        row.steps = s.steps
    db.flush()
    return steps_public(row)


@router.get("/steps")
def list_steps(
    date: Optional[date] = Query(default=None),
    limit: int = Query(default=90, ge=1, le=365),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(StepLog).where(StepLog.user_id == user.id)
    if date is not None:
        stmt = stmt.where(StepLog.logged_for == date)
    rows = db.scalars(stmt.order_by(StepLog.logged_for.desc()).limit(limit)).all()
    return {"items": [steps_public(s) for s in rows]}


@router.delete("/steps/{step_id}")
def delete_steps(
    step_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    row = _owned_or_404(db, StepLog, step_id, user.id)
    db.delete(row)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------
@router.post("/water")
def create_water(
    w: WaterIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    row = WaterLog(user_id=user.id, ml=w.ml, logged_at=w.logged_at or datetime.now())
    db.add(row)
    db.flush()
    return water_public(row)


@router.get("/water")
def list_water(
    date: Optional[date] = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    day = date or datetime.now().date()
    start, end = _day_bounds(day)
    rows = db.scalars(
        select(WaterLog)
        .where(
            WaterLog.user_id == user.id,
            WaterLog.logged_at >= start,
            WaterLog.logged_at < end,
        )
        .order_by(WaterLog.logged_at)
    ).all()
    return {"items": [water_public(w) for w in rows], "total_ml": sum(w.ml for w in rows)}


@router.delete("/water/{water_id}")
def delete_water(
    water_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    row = _owned_or_404(db, WaterLog, water_id, user.id)
    db.delete(row)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Weight (one row per day — upsert)
# ---------------------------------------------------------------------------
@router.post("/weight")
def upsert_weight(
    w: WeightIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    day = w.logged_for or date.today()
    row = db.scalar(
        select(WeightLog).where(
            WeightLog.user_id == user.id, WeightLog.logged_for == day
        )
    )
    if row is None:
        row = WeightLog(user_id=user.id, weight_kg=w.weight_kg, logged_for=day)
        db.add(row)
    else:
        row.weight_kg = w.weight_kg
    db.flush()
    return weight_public(row)


@router.get("/weight")
def list_weight(
    date: Optional[date] = Query(default=None),
    limit: int = Query(default=365, ge=1, le=365),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(WeightLog).where(WeightLog.user_id == user.id)
    if date is not None:
        stmt = stmt.where(WeightLog.logged_for == date)
    rows = db.scalars(stmt.order_by(WeightLog.logged_for.desc()).limit(limit)).all()
    return {"items": [weight_public(w) for w in rows]}


@router.put("/weight/{weight_id}")
def update_weight(
    weight_id: int,
    w: WeightIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = _owned_or_404(db, WeightLog, weight_id, user.id)
    row.weight_kg = w.weight_kg
    if w.logged_for is not None:
        row.logged_for = w.logged_for
    db.flush()
    return weight_public(row)


@router.delete("/weight/{weight_id}")
def delete_weight(
    weight_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    row = _owned_or_404(db, WeightLog, weight_id, user.id)
    db.delete(row)
    return {"ok": True}
