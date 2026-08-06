"""Workout session + set-log routes (contract §6).

A workout session belongs to a user and owns many set logs (weight × reps ×
RPE) — the core performance data. Set ownership is enforced via the parent
session's ``user_id``. Performance *analytics* (``/api/performance/*``) are
intentionally NOT implemented here; they belong to the recommendation engine.
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import current_user
from ..models import Exercise, SetLog, User, WorkoutSession
from ..schemas import SetIn, SetUpdate, WorkoutIn, WorkoutUpdate

router = APIRouter(prefix="/api/workouts", tags=["workouts"])

# Largest page size we'll actually run; larger ``limit`` values are soft-clamped.
_MAX_WORKOUTS_LIMIT = 200


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def set_public(s: SetLog) -> dict:
    return {
        "id": s.id,
        "exercise_id": s.exercise_id,
        "exercise_name": s.exercise.name if s.exercise else None,
        "set_index": s.set_index,
        "weight": s.weight,
        "reps": s.reps,
        "rpe": s.rpe,
        "is_warmup": s.is_warmup,
    }


def _volume(sets) -> float:
    return round(sum(s.weight * s.reps for s in sets if not s.is_warmup), 1)


def workout_summary(w: WorkoutSession) -> dict:
    return {
        "id": w.id,
        "date": w.date.isoformat(),
        "name": w.name,
        "notes": w.notes,
        "program_day_id": w.program_day_id,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "set_count": len(w.sets),
        "total_volume": _volume(w.sets),
    }


def workout_detail(w: WorkoutSession) -> dict:
    ordered = sorted(w.sets, key=lambda s: s.set_index)
    return {
        **workout_summary(w),
        "sets": [set_public(s) for s in ordered],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _workout_or_404(db: Session, workout_id: int, user_id: int) -> WorkoutSession:
    w = db.get(WorkoutSession, workout_id)
    if w is None or w.user_id != user_id:
        raise HTTPException(status_code=404, detail="workout not found")
    return w


def _set_or_404(db: Session, workout: WorkoutSession, set_id: int) -> SetLog:
    s = db.get(SetLog, set_id)
    if s is None or s.workout_session_id != workout.id:
        raise HTTPException(status_code=404, detail="set not found")
    return s


def _require_exercise(db: Session, exercise_id: int, user_id: int) -> None:
    e = db.get(Exercise, exercise_id)
    if e is None or (e.owner_user_id is not None and e.owner_user_id != user_id):
        raise HTTPException(status_code=400, detail="unknown exercise_id")


# ---------------------------------------------------------------------------
# Workout sessions
# ---------------------------------------------------------------------------
@router.post("", status_code=201)
def create_workout(
    body: WorkoutIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = WorkoutSession(
        user_id=user.id,
        date=body.date or date_cls.today(),
        name=body.name,
        notes=body.notes,
        program_day_id=body.program_day_id,
    )
    db.add(w)
    db.flush()
    db.refresh(w)  # populate server-generated created_at
    return workout_detail(w)


@router.get("")
def list_workouts(
    from_: Optional[date_cls] = Query(default=None, alias="from"),
    to: Optional[date_cls] = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Soft-clamp the page size instead of 422-ing on large ``limit`` values.
    limit = min(limit, _MAX_WORKOUTS_LIMIT)
    stmt = select(WorkoutSession).where(WorkoutSession.user_id == user.id)
    if from_ is not None:
        stmt = stmt.where(WorkoutSession.date >= from_)
    if to is not None:
        stmt = stmt.where(WorkoutSession.date <= to)
    stmt = (
        stmt.options(selectinload(WorkoutSession.sets))
        .order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.scalars(stmt).all()
    return {"items": [workout_summary(w) for w in rows], "limit": limit, "offset": offset}


@router.get("/{workout_id}")
def get_workout(
    workout_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = _workout_or_404(db, workout_id, user.id)
    return workout_detail(w)


@router.put("/{workout_id}")
def update_workout(
    workout_id: int,
    body: WorkoutUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = _workout_or_404(db, workout_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if "date" in data and data["date"] is not None:
        w.date = data["date"]
    if "name" in data:
        w.name = data["name"]
    if "notes" in data:
        w.notes = data["notes"]
    db.flush()
    return workout_detail(w)


@router.delete("/{workout_id}")
def delete_workout(
    workout_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = _workout_or_404(db, workout_id, user.id)
    db.delete(w)  # cascades to set logs
    return {"ok": True}


# ---------------------------------------------------------------------------
# Set logs (nested under a workout)
# ---------------------------------------------------------------------------
@router.post("/{workout_id}/sets", status_code=201)
def add_set(
    workout_id: int,
    body: SetIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = _workout_or_404(db, workout_id, user.id)
    _require_exercise(db, body.exercise_id, user.id)

    if body.set_index is not None:
        set_index = body.set_index
    else:
        current_max = db.scalar(
            select(func.max(SetLog.set_index)).where(
                SetLog.workout_session_id == w.id
            )
        )
        set_index = 0 if current_max is None else current_max + 1

    s = SetLog(
        workout_session_id=w.id,
        exercise_id=body.exercise_id,
        set_index=set_index,
        weight=body.weight,
        reps=body.reps,
        rpe=body.rpe,
        is_warmup=body.is_warmup,
    )
    db.add(s)
    db.flush()
    return set_public(s)


@router.put("/{workout_id}/sets/{set_id}")
def update_set(
    workout_id: int,
    set_id: int,
    body: SetUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = _workout_or_404(db, workout_id, user.id)
    s = _set_or_404(db, w, set_id)
    data = body.model_dump(exclude_unset=True)
    if "exercise_id" in data and data["exercise_id"] is not None:
        _require_exercise(db, data["exercise_id"], user.id)
        s.exercise_id = data["exercise_id"]
    for field in ("weight", "reps", "rpe", "is_warmup", "set_index"):
        if field in data and data[field] is not None:
            setattr(s, field, data[field])
    db.flush()
    return set_public(s)


@router.delete("/{workout_id}/sets/{set_id}")
def delete_set(
    workout_id: int,
    set_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    w = _workout_or_404(db, workout_id, user.id)
    s = _set_or_404(db, w, set_id)
    db.delete(s)
    return {"ok": True}
