"""Insights routes — now user-scoped (contract §10).

Same shapes as the original single-user app, scoped to the authenticated user
and extended with workout streaks + a "Consistent Lifter" achievement.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..ml.calories import bmr_mifflin_st_jeor, tdee
from ..ml.circadian import eating_window
from ..models import (
    ActivityLog,
    MealLog,
    Profile,
    SleepLog,
    StepLog,
    User,
    WaterLog,
    WeightLog,
    WorkoutSession,
)
from ..services.nutrition import goal_target_kcal
from ..services.streaks import (
    streaks_summary,
    workout_days,
    workout_minutes_by_day,
)

router = APIRouter(prefix="/api/insights", tags=["insights"])

# Rough kcal burn per minute by intensity (light activity baseline ~3 kcal/min).
INTENSITY_KCAL_PER_MIN = {"light": 3.5, "moderate": 6.0, "vigorous": 9.0}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _load_profile_or_400(db: Session, user_id: int) -> Profile:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(
            status_code=400, detail="set your profile first via PUT /api/profile"
        )
    return profile


def _goal_kcal(p: Profile) -> float:
    return goal_target_kcal(p)


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min)
    return start, start + timedelta(days=1)


def _activity_kcal(minutes: float, intensity: str) -> float:
    return minutes * INTENSITY_KCAL_PER_MIN.get(intensity, 6.0)


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------
@router.get("/today")
def today(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    profile = _load_profile_or_400(db, user.id)
    today_d = datetime.now().date()
    start, end = _day_bounds(today_d)

    bmr = bmr_mifflin_st_jeor(
        profile.sex, profile.weight_kg, profile.height_cm, profile.age
    )
    tdee_kcal = tdee(bmr, profile.activity_level)
    goal_kcal = goal_target_kcal(profile)

    meals = db.scalars(
        select(MealLog).where(
            MealLog.user_id == user.id,
            MealLog.eaten_at >= start,
            MealLog.eaten_at < end,
        )
    ).all()
    activities = db.scalars(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.done_at >= start,
            ActivityLog.done_at < end,
        )
    ).all()
    sleep = db.scalar(
        select(SleepLog)
        .where(SleepLog.user_id == user.id, SleepLog.logged_for == today_d)
        .order_by(SleepLog.id.desc())
    )
    steps_row = db.scalar(
        select(StepLog).where(
            StepLog.user_id == user.id, StepLog.logged_for == today_d
        )
    )
    water_rows = db.scalars(
        select(WaterLog).where(
            WaterLog.user_id == user.id,
            WaterLog.logged_at >= start,
            WaterLog.logged_at < end,
        )
    ).all()

    kcal_in = sum(m.kcal for m in meals)
    protein = sum(m.protein_g or 0 for m in meals)
    carbs = sum(m.carbs_g or 0 for m in meals)
    fat = sum(m.fat_g or 0 for m in meals)
    # Exercise minutes include logged cardio/activities AND an estimate from any
    # strength workout logged today (so lifting counts as exercise).
    activity_minutes = sum(a.minutes for a in activities)
    workout_minutes = workout_minutes_by_day(db, user.id, today_d).get(today_d, 0.0)
    exercise_minutes = activity_minutes + workout_minutes
    kcal_out_activity = sum(_activity_kcal(a.minutes, a.intensity) for a in activities)
    steps = steps_row.steps if steps_row else 0
    kcal_out_steps = steps * 0.04
    water_ml = sum(w.ml for w in water_rows)

    return {
        "bmr": round(bmr),
        "tdee": round(tdee_kcal),
        "target_kcal": round(goal_kcal),
        "kcal_in": round(kcal_in),
        "kcal_out_activity": round(kcal_out_activity),
        "kcal_out_steps": round(kcal_out_steps),
        "net_kcal": round(kcal_in - (kcal_out_activity + kcal_out_steps)),
        "remaining_to_target": round(goal_kcal - kcal_in),
        "sleep_hours": sleep.hours if sleep else None,
        "steps": steps,
        "exercise_minutes": round(exercise_minutes),
        "water_ml": water_ml,
        "macros": {
            "protein_g": round(protein, 1),
            "carbs_g": round(carbs, 1),
            "fat_g": round(fat, 1),
        },
        "goals": {
            "water_goal_ml": profile.water_goal_ml,
            "step_goal": profile.step_goal,
            "exercise_goal_min": profile.exercise_goal_min,
        },
    }


# ---------------------------------------------------------------------------
# Circadian
# ---------------------------------------------------------------------------
@router.get("/circadian")
def circadian(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    profile = _load_profile_or_400(db, user.id)
    return eating_window(profile.wake_time)


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
@router.get("/trends")
def trends(
    days: int = Query(default=14, ge=2, le=90),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    today_d = datetime.now().date()
    start_d = today_d - timedelta(days=days - 1)
    start_dt = datetime.combine(start_d, time.min)

    meals = db.scalars(
        select(MealLog).where(
            MealLog.user_id == user.id, MealLog.eaten_at >= start_dt
        )
    ).all()
    activities = db.scalars(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id, ActivityLog.done_at >= start_dt
        )
    ).all()
    sleeps = db.scalars(
        select(SleepLog).where(
            SleepLog.user_id == user.id, SleepLog.logged_for >= start_d
        ).order_by(SleepLog.id)
    ).all()
    steps = db.scalars(
        select(StepLog).where(
            StepLog.user_id == user.id, StepLog.logged_for >= start_d
        )
    ).all()
    weights = db.scalars(
        select(WeightLog).where(
            WeightLog.user_id == user.id, WeightLog.logged_for >= start_d
        )
    ).all()
    waters = db.scalars(
        select(WaterLog).where(
            WaterLog.user_id == user.id, WaterLog.logged_at >= start_dt
        )
    ).all()

    by_meal: dict[date, dict] = {}
    for m in meals:
        d = m.eaten_at.date()
        agg = by_meal.setdefault(d, {"kcal": 0.0, "p": 0.0, "c": 0.0, "f": 0.0})
        agg["kcal"] += m.kcal
        agg["p"] += m.protein_g or 0
        agg["c"] += m.carbs_g or 0
        agg["f"] += m.fat_g or 0

    by_act: dict[date, dict] = {}
    for a in activities:
        d = a.done_at.date()
        agg = by_act.setdefault(d, {"mins": 0.0, "kcal": 0.0})
        agg["mins"] += a.minutes
        agg["kcal"] += _activity_kcal(a.minutes, a.intensity)

    by_sleep = {s.logged_for: s.hours for s in sleeps}
    by_steps = {s.logged_for: s.steps for s in steps}
    by_weight = {w.logged_for: w.weight_kg for w in weights}
    by_water: dict[date, float] = {}
    for w in waters:
        by_water[w.logged_at.date()] = by_water.get(w.logged_at.date(), 0) + w.ml

    # Strength workouts contribute estimated exercise minutes too.
    by_workout_min = workout_minutes_by_day(db, user.id, start_d)

    days_list = []
    for i in range(days):
        d = start_d + timedelta(days=i)
        meal = by_meal.get(d)
        act = by_act.get(d)
        exercise_min = (act["mins"] if act else 0.0) + by_workout_min.get(d, 0.0)
        days_list.append(
            {
                "date": d.isoformat(),
                "kcal_in": round(meal["kcal"]) if meal else 0,
                "protein_g": round(meal["p"], 1) if meal else 0,
                "carbs_g": round(meal["c"], 1) if meal else 0,
                "fat_g": round(meal["f"], 1) if meal else 0,
                "exercise_min": round(exercise_min),
                "kcal_out_activity": round(act["kcal"]) if act else 0,
                "sleep_hours": by_sleep.get(d),
                "steps": by_steps.get(d, 0),
                "weight_kg": by_weight.get(d),
                "water_ml": by_water.get(d, 0),
            }
        )
    return {"days": days_list}


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------
@router.get("/streaks")
def streaks(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    # Shared with the AI coach so on-screen streaks and chat always agree.
    # Workout days fold into the activity + any-log streaks.
    return streaks_summary(db, user.id)


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------
def _badge(id_, label, icon, color, current, target) -> dict:
    return {
        "id": id_,
        "label": label,
        "icon": icon,
        "color": color,
        "earned": current >= target,
        "current": int(current),
        "target": int(target),
        "progress": min(1.0, current / target if target else 1),
    }


@router.get("/achievements")
def achievements(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    profile = _load_profile_or_400(db, user.id)
    goal_kcal = _goal_kcal(profile)
    today_d = datetime.now().date()

    meals = db.scalars(select(MealLog).where(MealLog.user_id == user.id)).all()
    total_meals = len(meals)
    total_activities = db.scalar(
        select(func.count(ActivityLog.id)).where(ActivityLog.user_id == user.id)
    )
    total_workout_sessions = db.scalar(
        select(func.count(WorkoutSession.id)).where(
            WorkoutSession.user_id == user.id
        )
    ) or 0
    # "Exercise" for the Move It / Athlete badges = logged activities PLUS logged
    # strength workouts, so lifting counts toward them.
    total_exercise_sessions = (total_activities or 0) + total_workout_sessions
    total_water_ml = sum(
        w.ml
        for w in db.scalars(
            select(WaterLog).where(WaterLog.user_id == user.id)
        ).all()
    )
    max_steps = db.scalar(
        select(func.max(StepLog.steps)).where(StepLog.user_id == user.id)
    ) or 0
    sleep_8_count = db.scalar(
        select(func.count(SleepLog.id)).where(
            SleepLog.user_id == user.id, SleepLog.hours >= 8
        )
    )
    days_logged = len({m.eaten_at.date() for m in meals})
    workout_day_count = len(
        set(
            db.scalars(
                select(WorkoutSession.date).where(
                    WorkoutSession.user_id == user.id
                )
            ).all()
        )
    )

    # On-target kcal days within the last 30 days.
    cutoff_dt = datetime.combine(today_d - timedelta(days=30), time.min)
    kcal_by_day: dict[date, float] = {}
    for m in meals:
        if m.eaten_at >= cutoff_dt:
            kcal_by_day[m.eaten_at.date()] = (
                kcal_by_day.get(m.eaten_at.date(), 0) + m.kcal
            )
    on_target_days = sum(1 for k in kcal_by_day.values() if abs(k - goal_kcal) <= 200)

    return {
        "badges": [
            _badge("first_meal", "First Bite", "🍽️", "#FF6B6B", total_meals, 1),
            _badge("ten_meals", "Getting Started", "🥗", "#4ECDC4", total_meals, 10),
            _badge("hundred_meals", "Centurion", "💯", "#FFD93D", total_meals, 100),
            _badge("first_workout", "Move It", "💪", "#FF9F1C", total_exercise_sessions, 1),
            _badge("ten_workouts", "Athlete", "🏋️", "#A06CD5", total_exercise_sessions, 10),
            _badge(
                "hydration_master",
                "Hydration Hero",
                "💧",
                "#4DA8DA",
                total_water_ml,
                50_000,
            ),
            _badge("step_legend", "Step Legend", "🦶", "#7CF0A3", max_steps, 10_000),
            _badge("well_rested", "Well Rested", "😴", "#6CB1FF", sleep_8_count, 5),
            _badge("week_streak", "Consistent", "🔥", "#FC4C02", days_logged, 7),
            _badge(
                "on_target_week", "Calorie Sniper", "🎯", "#22D3A2", on_target_days, 7
            ),
            _badge(
                "consistent_lifter",
                "Consistent Lifter",
                "🏆",
                "#F4A259",
                workout_day_count,
                7,
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------
@router.get("/heatmap")
def heatmap(
    days: int = Query(default=84, ge=14, le=365),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    today_d = datetime.now().date()
    start_d = today_d - timedelta(days=days - 1)
    start_dt = datetime.combine(start_d, time.min)

    activities = db.scalars(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id, ActivityLog.done_at >= start_dt
        )
    ).all()
    mins_by_day: dict[date, float] = {}
    for a in activities:
        mins_by_day[a.done_at.date()] = mins_by_day.get(a.done_at.date(), 0) + a.minutes

    # Fold in strength workouts: a day with a logged session is "active" even if
    # its estimated minutes are small (and workout minutes add to the heat level).
    workout_min = workout_minutes_by_day(db, user.id, start_d)
    for d, mins in workout_min.items():
        mins_by_day[d] = mins_by_day.get(d, 0) + mins
    workout_only_days = workout_days(db, user.id, start_d)

    result = []
    for i in range(days):
        d = start_d + timedelta(days=i)
        m = mins_by_day.get(d, 0)
        level = 0 if m == 0 else 1 if m < 15 else 2 if m < 30 else 3 if m < 60 else 4
        # Guarantee a workout day always registers as active on the heatmap.
        if level == 0 and d in workout_only_days:
            level = 1
        result.append({"date": d.isoformat(), "minutes": round(m), "level": level})
    return {"days": result}
