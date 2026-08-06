"""AI Coach routes — predictive meal recommendations + chat (contract §9).

These endpoints expose the pure, offline ``app/ml`` helpers to the frontend.
Every reply is grounded in the *authenticated user's own* logged data: the
route layer sources per-user rows via SQLAlchemy and passes plain dicts to the
ml functions (which remain I/O-free and reusable).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..ml import coach, parser
from ..ml.circadian import eating_window
from ..models import (
    ActivityLog,
    Exercise,
    MealLog,
    Profile,
    SetLog,
    SleepLog,
    StepLog,
    User,
    WaterLog,
    WorkoutSession,
)
from ..services import performance
from ..services.mapping import training_goal_to_params
from ..services.nutrition import active_macro_targets, goal_target_kcal
from ..services.streaks import streaks_summary

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Data-access helpers (all user-scoped)
# ---------------------------------------------------------------------------
def _load_profile(db: Session, user_id: int) -> Profile:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(
            status_code=400, detail="set your profile first via PUT /api/profile"
        )
    return profile


def _goal_kcal(p: Profile) -> float:
    return goal_target_kcal(p)


def _meal_dict(m: MealLog) -> dict:
    return {
        "name": m.name,
        "category": m.category,
        "kcal": m.kcal,
        "eaten_at": m.eaten_at.isoformat(timespec="minutes"),
        "protein_g": m.protein_g,
        "carbs_g": m.carbs_g,
        "fat_g": m.fat_g,
    }


def _fetch_meals(
    db: Session, user_id: int, history_days: int = 14, exclude_today: bool = True
) -> list[dict]:
    today_d = datetime.now().date()
    cutoff = datetime.combine(today_d - timedelta(days=history_days), time.min)
    stmt = select(MealLog).where(
        MealLog.user_id == user_id, MealLog.eaten_at >= cutoff
    )
    if exclude_today:
        stmt = stmt.where(MealLog.eaten_at < datetime.combine(today_d, time.min))
    rows = db.scalars(stmt.order_by(MealLog.eaten_at)).all()
    return [_meal_dict(m) for m in rows]


def _fetch_today_meals(db: Session, user_id: int) -> list[dict]:
    today_d = datetime.now().date()
    start = datetime.combine(today_d, time.min)
    end = start + timedelta(days=1)
    rows = db.scalars(
        select(MealLog)
        .where(
            MealLog.user_id == user_id,
            MealLog.eaten_at >= start,
            MealLog.eaten_at < end,
        )
        .order_by(MealLog.eaten_at)
    ).all()
    return [_meal_dict(m) for m in rows]


def _today_macros(db: Session, user_id: int) -> dict:
    today = _fetch_today_meals(db, user_id)
    return {
        "protein_g": sum(m["protein_g"] or 0 for m in today),
        "carbs_g": sum(m["carbs_g"] or 0 for m in today),
        "fat_g": sum(m["fat_g"] or 0 for m in today),
    }


def _today_context(db: Session, user_id: int, profile: Profile) -> dict:
    today_d = datetime.now().date()
    start = datetime.combine(today_d, time.min)
    end = start + timedelta(days=1)

    goal_kcal = _goal_kcal(profile)

    meals = db.scalars(
        select(MealLog).where(
            MealLog.user_id == user_id,
            MealLog.eaten_at >= start,
            MealLog.eaten_at < end,
        )
    ).all()
    activities = db.scalars(
        select(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.done_at >= start,
            ActivityLog.done_at < end,
        )
    ).all()
    steps_row = db.scalar(
        select(StepLog).where(
            StepLog.user_id == user_id, StepLog.logged_for == today_d
        )
    )
    water_rows = db.scalars(
        select(WaterLog).where(
            WaterLog.user_id == user_id,
            WaterLog.logged_at >= start,
            WaterLog.logged_at < end,
        )
    ).all()
    sleep_row = db.scalar(
        select(SleepLog)
        .where(SleepLog.user_id == user_id, SleepLog.logged_for == today_d)
        .order_by(SleepLog.id.desc())
    )

    kcal_in = sum(m.kcal for m in meals)
    return {
        "kcal_in": round(kcal_in),
        "target_kcal": round(goal_kcal),
        "remaining_to_target": round(goal_kcal - kcal_in),
        "macros": {
            "protein_g": round(sum(m.protein_g or 0 for m in meals), 1),
            "carbs_g": round(sum(m.carbs_g or 0 for m in meals), 1),
            "fat_g": round(sum(m.fat_g or 0 for m in meals), 1),
        },
        "steps": steps_row.steps if steps_row else 0,
        "water_ml": sum(w.ml for w in water_rows),
        "exercise_minutes": sum(a.minutes for a in activities),
        "sleep_hours": sleep_row.hours if sleep_row else None,
        "goals": {
            "water_goal_ml": profile.water_goal_ml,
            "step_goal": profile.step_goal,
            "exercise_goal_min": profile.exercise_goal_min,
        },
    }


def _profile_dict(p: Profile) -> dict:
    return {
        "name": p.name,
        "sex": p.sex,
        "age": p.age,
        "height_cm": p.height_cm,
        "weight_kg": p.weight_kg,
        "activity_level": p.activity_level,
        "goal": p.goal,
        "wake_time": p.wake_time,
    }


# ---------------------------------------------------------------------------
# Training-domain context (grounded in real workout/performance data)
# ---------------------------------------------------------------------------
_MAIN_LIFT_NAMES = ("Back Squat", "Bench Press", "Deadlift", "Overhead Press")


def _trend_for_exercise(db: Session, user_id: int, ex: Exercise) -> Optional[dict]:
    perf = performance.exercise_performance(db, user_id, ex.id, ex.name)
    trend = perf.get("e1rm_trend") or []
    if not trend:
        return None
    first = trend[0]["value"]
    last = trend[-1]["value"]
    change = round(last - first, 1)
    pct = round(100 * change / first, 1) if first else 0.0
    direction = "up" if change > 0.5 else "down" if change < -0.5 else "flat"
    return {
        "name": ex.name,
        "first_e1rm": first,
        "last_e1rm": last,
        "change": change,
        "pct": pct,
        "direction": direction,
        "points": len(trend),
        "best_e1rm": (perf.get("best") or {}).get("best_e1rm", last),
    }


def _lift_trends(db: Session, user_id: int) -> list[dict]:
    """Per-lift estimated-1RM trend (first vs latest) to gauge strength.

    Prefers the classic barbell mains; if the user trains none of them (e.g. a
    home_basic/bodyweight lifter on dumbbell variants), falls back to their
    most-logged weighted exercises so the coach still has real data to report.
    """
    mains = db.scalars(
        select(Exercise).where(Exercise.name.in_(_MAIN_LIFT_NAMES))
    ).all()
    out = [t for ex in mains if (t := _trend_for_exercise(db, user_id, ex))]
    if out:
        return out

    rows = db.execute(
        select(SetLog.exercise_id, func.count(SetLog.id))
        .join(WorkoutSession, SetLog.workout_session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user_id,
            SetLog.is_warmup.is_(False),
            SetLog.weight > 0,
        )
        .group_by(SetLog.exercise_id)
        .order_by(func.count(SetLog.id).desc())
        .limit(4)
    ).all()
    for exercise_id, _n in rows:
        ex = db.get(Exercise, exercise_id)
        if ex is not None:
            trend = _trend_for_exercise(db, user_id, ex)
            if trend and trend["points"] >= 2:
                out.append(trend)
    return out


def _recent_volume(db: Session, user_id: int, profile: Profile) -> list[dict]:
    """Most recent training week's per-muscle sets/volume vs MEV/MAV targets."""
    goal = training_goal_to_params(profile.training_goal)
    today_d = datetime.now().date()
    report = performance.volume_report(
        db, user_id, goal, from_=today_d - timedelta(days=13), to=today_d
    )
    weeks = report.get("weeks") or []
    return weeks[-1]["muscles"] if weeks else []


def _intake_vs_target(db: Session, user_id: int, profile: Profile) -> dict:
    """Average daily intake over the last 7 (completed) days vs the kcal target."""
    target = round(goal_target_kcal(profile))
    today_d = datetime.now().date()
    start = datetime.combine(today_d - timedelta(days=7), time.min)
    end = datetime.combine(today_d, time.min)
    meals = db.scalars(
        select(MealLog).where(
            MealLog.user_id == user_id,
            MealLog.eaten_at >= start,
            MealLog.eaten_at < end,
        )
    ).all()
    by_day: dict[date, float] = {}
    for m in meals:
        by_day[m.eaten_at.date()] = by_day.get(m.eaten_at.date(), 0.0) + m.kcal
    avg = round(sum(by_day.values()) / len(by_day)) if by_day else 0
    return {
        "avg_daily_kcal": avg,
        "target_kcal": target,
        "delta": (avg - target) if by_day else 0,
        "days_counted": len(by_day),
        "goal": profile.goal,
    }


def _training_context(
    db: Session, user_id: int, profile: Profile, streaks: dict
) -> dict:
    today_d = datetime.now().date()
    sessions_14 = (
        db.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.date >= today_d - timedelta(days=14),
            )
        )
        or 0
    )
    return {
        "training_goal": profile.training_goal,
        "goal": profile.goal,
        "workout_streak": streaks.get("workout_streak", 0),
        "sessions_last_14d": int(sessions_14),
        "lifts": _lift_trends(db, user_id),
        "volume": _recent_volume(db, user_id, profile),
        "intake": _intake_vs_target(db, user_id, profile),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/predict-next-meal")
def predict_next_meal(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Rich next-meal prediction with food recommendations."""
    profile = _load_profile(db, user.id)
    return coach.predict_next_meal_detailed(
        history_meals=_fetch_meals(db, user.id, history_days=14, exclude_today=True),
        todays_meals=_fetch_today_meals(db, user.id),
        daily_kcal_target=_goal_kcal(profile),
        todays_macros_consumed=_today_macros(db, user.id),
        target_macros=active_macro_targets(db, user.id, profile),
    )


@router.get("/recommend-foods")
def recommend_foods(
    category: Optional[str] = Query(default=None, description="filter by meal category"),
    top_n: int = Query(default=5, ge=1, le=20),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Foods from your history ranked by how well they close the macro gap."""
    profile = _load_profile(db, user.id)
    history = _fetch_meals(db, user.id, history_days=30, exclude_today=False)
    macros_today = _today_macros(db, user.id)
    # Use the user's real plan macro targets (single source of truth) so the gap
    # here matches the Nutrition screen and the rest of the coach.
    targets = active_macro_targets(db, user.id, profile)
    gap = {
        "protein": targets["protein"] - macros_today["protein_g"],
        "carbs": targets["carbs"] - macros_today["carbs_g"],
        "fat": targets["fat"] - macros_today["fat_g"],
    }
    return {
        "macro_gap": {
            "protein_g": round(gap["protein"], 1),
            "carbs_g": round(gap["carbs"], 1),
            "fat_g": round(gap["fat"], 1),
        },
        "macro_targets": {f"{k}_g": round(v, 1) for k, v in targets.items()},
        "recommendations": coach.recommend_foods_for_macros(
            history, gap, category=category, top_n=top_n
        ),
    }


@router.get("/insights")
def ai_insights(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Pattern analysis: typical times, top foods per meal, kcal/macros averages."""
    history = _fetch_meals(db, user.id, history_days=30, exclude_today=False)
    return coach.analyze_patterns(history)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ParseLogRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/parse-log")
def parse_log(
    req: ParseLogRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Parse a natural-language meal description into a structured payload."""
    history = _fetch_meals(db, user.id, history_days=30, exclude_today=False)
    return parser.parse_meal(req.text, history=history)


@router.post("/chat")
def chat(
    req: ChatRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Ask the coach anything — replies are grounded in your real data."""
    profile = _load_profile(db, user.id)
    goal_kcal = _goal_kcal(profile)

    today_ctx = _today_context(db, user.id, profile)
    history = _fetch_meals(db, user.id, history_days=14, exclude_today=True)
    todays = _fetch_today_meals(db, user.id)
    prediction = coach.predict_next_meal_detailed(
        history_meals=history,
        todays_meals=todays,
        daily_kcal_target=goal_kcal,
        todays_macros_consumed=_today_macros(db, user.id),
        target_macros=active_macro_targets(db, user.id, profile),
    )
    patterns = coach.analyze_patterns(history + todays)
    streaks = streaks_summary(db, user.id)
    training = _training_context(db, user.id, profile, streaks)
    try:
        circadian = eating_window(profile.wake_time)
    except Exception:
        circadian = {}

    return coach.chat(
        req.message,
        {
            "profile": _profile_dict(profile),
            "today": today_ctx,
            "prediction": prediction,
            "patterns": patterns,
            "streaks": streaks,
            "training": training,
            "circadian": circadian,
        },
    )
