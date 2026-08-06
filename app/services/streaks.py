"""Shared streak + workout-as-activity helpers (contract §10).

The daily-log streak logic and the "a workout counts as exercise" heuristic used
to live copy-pasted inside :mod:`app.routes.insights` and :mod:`app.routes.ai`.
They are consolidated here so the numbers a user sees on the Insights screen and
the ones the AI coach quotes in chat always agree.

Key rules:

* A logged **workout session** (``/api/workouts``) counts as an *active* day for
  the activity streak, the any-log streak and the activity heatmap — not just
  rows in ``activity_log``.
* Strength work contributes estimated **exercise minutes** (``~3.5`` min per
  working, non-warmup set, capped per session) so lifting shows up in
  insights/today, trends and the minute-keyed badges.

This module is user-scoped and I/O lives entirely in SQLAlchemy queries.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models import (
    ActivityLog,
    MealLog,
    SetLog,
    SleepLog,
    WaterLog,
    WorkoutSession,
)

#: Estimated training time per working (non-warmup) set — covers the set plus
#: its rest. ~3.5 min/set is a reasonable average across compounds/accessories.
WORKOUT_MIN_PER_SET = 3.5
#: Hard per-session cap so a marathon logging session can't dominate the day.
WORKOUT_SESSION_MIN_CAP = 90.0


# ---------------------------------------------------------------------------
# Streak counting
# ---------------------------------------------------------------------------
def count_streak(day_set: set[date], today_d: date) -> int:
    """Consecutive-day streak ending today.

    Today not being logged yet doesn't break the streak (it just isn't counted).
    """
    streak = 0
    for offset in range(0, 366):
        d = today_d - timedelta(days=offset)
        if d in day_set:
            streak += 1
        elif offset == 0:
            continue  # today not logged yet — don't break, don't count
        else:
            break
    return streak


# ---------------------------------------------------------------------------
# Workout-as-activity helpers
# ---------------------------------------------------------------------------
def workout_working_sets_by_session(
    db: Session, user_id: int, start_d: date
) -> list[tuple[date, int]]:
    """``(session_date, working_set_count)`` for each session since ``start_d``."""
    rows = db.execute(
        select(WorkoutSession.date, func.count(SetLog.id))
        .outerjoin(
            SetLog,
            and_(
                SetLog.workout_session_id == WorkoutSession.id,
                SetLog.is_warmup.is_(False),
            ),
        )
        .where(WorkoutSession.user_id == user_id, WorkoutSession.date >= start_d)
        .group_by(WorkoutSession.id, WorkoutSession.date)
    ).all()
    return [(d, int(n or 0)) for d, n in rows]


def workout_minutes_by_day(
    db: Session, user_id: int, start_d: date
) -> dict[date, float]:
    """Estimated training minutes per day from logged workout sessions.

    ``~3.5`` min per working set, capped per session, summed across sessions on
    the same day.
    """
    out: dict[date, float] = {}
    for d, n_sets in workout_working_sets_by_session(db, user_id, start_d):
        minutes = min(WORKOUT_SESSION_MIN_CAP, WORKOUT_MIN_PER_SET * n_sets)
        out[d] = out.get(d, 0.0) + minutes
    return out


def workout_days(db: Session, user_id: int, start_d: date) -> set[date]:
    """Distinct dates on which the user logged a workout session."""
    return set(
        db.scalars(
            select(WorkoutSession.date).where(
                WorkoutSession.user_id == user_id, WorkoutSession.date >= start_d
            )
        ).all()
    )


# ---------------------------------------------------------------------------
# Streaks summary (workouts fold into activity + any)
# ---------------------------------------------------------------------------
def _day_sets(db: Session, user_id: int, today_d: date) -> dict[str, set[date]]:
    cutoff_d = today_d - timedelta(days=365)
    cutoff_dt = datetime.combine(cutoff_d, time.min)

    meal_days = {
        m.date()
        for m in db.scalars(
            select(MealLog.eaten_at).where(
                MealLog.user_id == user_id, MealLog.eaten_at >= cutoff_dt
            )
        ).all()
    }
    activity_days = {
        a.date()
        for a in db.scalars(
            select(ActivityLog.done_at).where(
                ActivityLog.user_id == user_id, ActivityLog.done_at >= cutoff_dt
            )
        ).all()
    }
    sleep_days = set(
        db.scalars(
            select(SleepLog.logged_for).where(
                SleepLog.user_id == user_id, SleepLog.logged_for >= cutoff_d
            )
        ).all()
    )
    water_days = {
        w.date()
        for w in db.scalars(
            select(WaterLog.logged_at).where(
                WaterLog.user_id == user_id, WaterLog.logged_at >= cutoff_dt
            )
        ).all()
    }
    return {
        "meal": meal_days,
        "activity": activity_days,
        "sleep": sleep_days,
        "water": water_days,
        "workout": workout_days(db, user_id, cutoff_d),
    }


def streaks_summary(db: Session, user_id: int) -> dict:
    """All per-domain streaks. Workout days count toward activity + any."""
    today_d = datetime.now().date()
    ds = _day_sets(db, user_id, today_d)
    activity_incl_workouts = ds["activity"] | ds["workout"]
    any_days = ds["meal"] | activity_incl_workouts | ds["sleep"] | ds["water"]
    return {
        "meal_streak": count_streak(ds["meal"], today_d),
        "activity_streak": count_streak(activity_incl_workouts, today_d),
        "sleep_streak": count_streak(ds["sleep"], today_d),
        "water_streak": count_streak(ds["water"], today_d),
        "workout_streak": count_streak(ds["workout"], today_d),
        "any_streak": count_streak(any_days, today_d),
    }


__all__ = [
    "WORKOUT_MIN_PER_SET",
    "WORKOUT_SESSION_MIN_CAP",
    "count_streak",
    "workout_working_sets_by_session",
    "workout_minutes_by_day",
    "workout_days",
    "streaks_summary",
]
