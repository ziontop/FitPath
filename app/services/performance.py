"""Performance analytics (contract §6) — e1RM, PRs, per-exercise history, volume.

All computation is user-scoped and ignores warm-up sets (matching
``app/routes/workouts.py::_volume``). Estimated 1RM uses the researched
:func:`~app.training.params.estimated_1rm` (Epley/Brzycki mean); because those
diverge past ~10 reps, the rep count fed to the formula is capped at
``TRUSTWORTHY_MAX_REPS`` so a high-rep back-off set never inflates a PR.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Exercise, SetLog, WorkoutSession
from ..training.params import (
    Goal,
    estimated_1rm,
    load_for_reps,
    rpe_to_rir,
    weekly_set_target,
)
from .mapping import muscle_group_for

TRUSTWORTHY_MAX_REPS = 10
_DEFAULT_WEIGHT_STEP_KG = 2.5


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def _e1rm(weight: float, reps: int) -> float:
    """Estimated 1RM with reps capped for trustworthiness."""
    return estimated_1rm(weight, min(max(reps, 1), TRUSTWORTHY_MAX_REPS))


def round_to_increment(value: float, step: float = _DEFAULT_WEIGHT_STEP_KG) -> float:
    """Round a load to the nearest plate increment (2.5 kg by default)."""
    if step <= 0:
        return round(value, 1)
    return round(round(value / step) * step, 2)


def suggested_weight(
    e1rm: Optional[float],
    target_reps: int,
    target_rpe: Optional[float],
    step: float = _DEFAULT_WEIGHT_STEP_KG,
) -> Optional[float]:
    """Working load for ``target_reps`` @ ``target_rpe`` given an estimated 1RM.

    A set stopped at ``RPE`` leaves ``RIR = 10 - RPE`` reps in reserve, i.e. the
    lifter could have done ``target_reps + RIR`` reps to failure at that load.
    We therefore pick the load whose *failure* rep count is ``target_reps + RIR``
    (inverse-Epley via :func:`load_for_reps`/:func:`epley_percent_1rm`), so doing
    ``target_reps`` at it stops at the intended RPE. Returns ``None`` without an
    e1RM so the UI can show a starting-weight prompt instead.
    """
    if not e1rm or e1rm <= 0:
        return None
    rir = rpe_to_rir(target_rpe if target_rpe is not None else 8.0)
    effective_reps = max(1, round(target_reps + rir))
    load = load_for_reps(e1rm, effective_reps)
    return round_to_increment(load, step)


def _working_sets_stmt(user_id: int):
    """Base SELECT of the user's working (non-warmup) sets + date + exercise."""
    return (
        select(SetLog, WorkoutSession.date, Exercise)
        .join(WorkoutSession, SetLog.workout_session_id == WorkoutSession.id)
        .join(Exercise, SetLog.exercise_id == Exercise.id)
        .where(
            WorkoutSession.user_id == user_id,
            SetLog.is_warmup.is_(False),
        )
    )


def _pr_from_entries(
    exercise_id: int,
    exercise_name: str,
    entries: Iterable[tuple[float, int, Optional[float], date]],
) -> Optional[dict]:
    """Build a PR record from ``(weight, reps, rpe, date)`` tuples.

    ``best_e1rm`` is the max estimated 1RM (preferring trustworthy <=10-rep
    sets); ``best_weight``/``best_reps`` describe the single heaviest set;
    ``achieved_at`` is the date of the e1RM PR set.
    """
    rows = [(w, r, rpe, d) for (w, r, rpe, d) in entries if w > 0 and r >= 1]
    if not rows:
        return None

    trustworthy = [row for row in rows if row[1] <= TRUSTWORTHY_MAX_REPS]
    e1rm_pool = trustworthy or rows
    best_e1rm_row = max(e1rm_pool, key=lambda row: _e1rm(row[0], row[1]))
    top_weight_row = max(rows, key=lambda row: (row[0], row[1]))

    return {
        "exercise_id": exercise_id,
        "exercise_name": exercise_name,
        "best_e1rm": round(_e1rm(best_e1rm_row[0], best_e1rm_row[1]), 1),
        "best_weight": round(top_weight_row[0], 1),
        "best_reps": top_weight_row[1],
        "achieved_at": best_e1rm_row[3].isoformat() if best_e1rm_row[3] else None,
    }


# ---------------------------------------------------------------------------
# Endpoints' business logic
# ---------------------------------------------------------------------------
def performance_summary(db: Session, user_id: int) -> dict:
    rows = db.execute(_working_sets_stmt(user_id)).all()
    total_volume = round(sum(s.weight * s.reps for s, _d, _e in rows), 1)

    sessions_count = (
        db.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user_id
            )
        )
        or 0
    )

    best: dict[int, tuple[float, str]] = {}
    for s, _d, e in rows:
        # Match personal_records(): only weight-loaded working sets establish a PR,
        # so prs_count == len(/prs items) (bodyweight-only exercises are excluded).
        if s.weight <= 0 or s.reps < 1:
            continue
        value = _e1rm(s.weight, s.reps)
        if e.id not in best or value > best[e.id][0]:
            best[e.id] = (value, e.name)

    highlights = sorted(
        (
            {"exercise_id": eid, "exercise_name": name, "e1rm": round(value, 1)}
            for eid, (value, name) in best.items()
        ),
        key=lambda h: h["e1rm"],
        reverse=True,
    )[:3]

    return {
        "total_volume": total_volume,
        "sessions_count": int(sessions_count),
        "prs_count": len(best),
        "e1rm_highlights": highlights,
    }


def personal_records(db: Session, user_id: int) -> dict:
    rows = db.execute(_working_sets_stmt(user_id)).all()
    grouped: dict[int, dict] = {}
    for s, d, e in rows:
        g = grouped.setdefault(e.id, {"name": e.name, "entries": []})
        g["entries"].append((s.weight, s.reps, s.rpe, d))

    items = []
    for exercise_id, g in grouped.items():
        pr = _pr_from_entries(exercise_id, g["name"], g["entries"])
        if pr is not None:
            items.append(pr)
    items.sort(key=lambda p: p["best_e1rm"], reverse=True)
    return {"items": items}


def exercise_performance(
    db: Session, user_id: int, exercise_id: int, exercise_name: str
) -> dict:
    rows = db.execute(
        _working_sets_stmt(user_id)
        .where(SetLog.exercise_id == exercise_id)
        .order_by(WorkoutSession.date, SetLog.set_index)
    ).all()

    history: list[dict] = []
    entries: list[tuple[float, int, Optional[float], date]] = []
    e1rm_by_date: dict[str, float] = {}
    volume_by_date: dict[str, float] = {}

    for s, d, _e in rows:
        d_iso = d.isoformat()
        value = _e1rm(s.weight, s.reps)
        history.append(
            {
                "date": d_iso,
                "weight": s.weight,
                "reps": s.reps,
                "rpe": s.rpe,
                "e1rm": round(value, 1),
            }
        )
        entries.append((s.weight, s.reps, s.rpe, d))
        e1rm_by_date[d_iso] = max(e1rm_by_date.get(d_iso, 0.0), value)
        volume_by_date[d_iso] = volume_by_date.get(d_iso, 0.0) + s.weight * s.reps

    e1rm_trend = [
        {"date": d, "value": round(v, 1)} for d, v in sorted(e1rm_by_date.items())
    ]
    volume_trend = [
        {"date": d, "value": round(v, 1)} for d, v in sorted(volume_by_date.items())
    ]

    best = _pr_from_entries(exercise_id, exercise_name, entries) or {
        "exercise_id": exercise_id,
        "exercise_name": exercise_name,
        "best_e1rm": 0,
        "best_weight": 0,
        "best_reps": 0,
        "achieved_at": None,
    }

    return {
        "exercise_id": exercise_id,
        "exercise_name": exercise_name,
        "history": history,
        "e1rm_trend": e1rm_trend,
        "volume_trend": volume_trend,
        "best": best,
    }


def volume_report(
    db: Session,
    user_id: int,
    goal: Goal,
    from_: Optional[date] = None,
    to: Optional[date] = None,
) -> dict:
    stmt = _working_sets_stmt(user_id)
    if from_ is not None:
        stmt = stmt.where(WorkoutSession.date >= from_)
    if to is not None:
        stmt = stmt.where(WorkoutSession.date <= to)
    rows = db.execute(stmt.order_by(WorkoutSession.date)).all()

    weeks: dict[date, dict] = {}
    for s, d, e in rows:
        week_start = d - timedelta(days=d.weekday())  # Monday
        bucket = weeks.setdefault(week_start, {"muscles": {}, "total_volume": 0.0})
        volume = s.weight * s.reps
        bucket["total_volume"] += volume
        group = muscle_group_for(e.primary_muscle)
        if group is not None:
            mm = bucket["muscles"].setdefault(group, {"sets": 0, "volume": 0.0})
            mm["sets"] += 1
            mm["volume"] += volume

    out = []
    for week_start in sorted(weeks):
        bucket = weeks[week_start]
        muscles = []
        for group, mm in bucket["muscles"].items():
            low, high = weekly_set_target(goal, group)
            muscles.append(
                {
                    "muscle": group.value,
                    "sets": mm["sets"],
                    "volume": round(mm["volume"], 1),
                    "target_low": low,
                    "target_high": high,
                }
            )
        muscles.sort(key=lambda m: m["volume"], reverse=True)
        out.append(
            {
                "week_start": week_start.isoformat(),
                "muscles": muscles,
                "total_volume": round(bucket["total_volume"], 1),
            }
        )
    return {"weeks": out}


def best_recent_e1rm(
    db: Session, user_id: int, exercise_id: int, since_days: int = 120
) -> Optional[float]:
    """Best estimated 1RM for an exercise over recent working sets (or ``None``)."""
    cutoff = date.today() - timedelta(days=since_days)
    rows = db.execute(
        _working_sets_stmt(user_id).where(
            SetLog.exercise_id == exercise_id,
            WorkoutSession.date >= cutoff,
        )
    ).all()
    values = [_e1rm(s.weight, s.reps) for s, _d, _e in rows if s.weight > 0 and s.reps >= 1]
    return max(values) if values else None


__all__ = [
    "TRUSTWORTHY_MAX_REPS",
    "round_to_increment",
    "suggested_weight",
    "performance_summary",
    "personal_records",
    "exercise_performance",
    "volume_report",
    "best_recent_e1rm",
]
