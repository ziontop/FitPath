"""Performance analytics routes (contract §6, ``/api/performance``).

Thin router over :mod:`app.services.performance`; every query is scoped to the
authenticated user. The engine logic (e1RM, PRs, volume) lives in the service.
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Profile, User
from ..services import performance
from ..services.mapping import training_goal_to_params
from .exercises import visible_exercise

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("/summary")
def get_summary(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    return performance.performance_summary(db, user.id)


@router.get("/prs")
def get_prs(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    return performance.personal_records(db, user.id)


@router.get("/exercise/{exercise_id}")
def get_exercise(
    exercise_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    exercise = visible_exercise(db, exercise_id, user.id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return performance.exercise_performance(db, user.id, exercise_id, exercise.name)


@router.get("/volume")
def get_volume(
    from_: Optional[date_cls] = Query(default=None, alias="from"),
    to: Optional[date_cls] = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    profile = db.get(Profile, user.id)
    goal = training_goal_to_params(profile.training_goal if profile else None)
    return performance.volume_report(db, user.id, goal, from_, to)
