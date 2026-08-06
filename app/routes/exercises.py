"""Exercise catalog routes (contract §5).

Users see the seeded global catalog (``owner_user_id IS NULL``) plus their own
custom exercises. Custom exercises are created owner-scoped.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Exercise, User
from ..schemas import ExerciseIn

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


def exercise_public(e: Exercise) -> dict:
    try:
        secondary = json.loads(e.secondary_muscles) if e.secondary_muscles else []
    except (ValueError, TypeError):
        secondary = []
    return {
        "id": e.id,
        "name": e.name,
        "category": e.category,
        "primary_muscle": e.primary_muscle,
        "secondary_muscles": secondary,
        "equipment": e.equipment,
        "is_main_lift": e.is_main_lift,
        "is_custom": e.is_custom,
    }


def _visible(user_id: int):
    """Filter: global catalog rows plus the user's own custom exercises."""
    return or_(Exercise.owner_user_id.is_(None), Exercise.owner_user_id == user_id)


def visible_exercise(db: Session, exercise_id: int, user_id: int) -> Optional[Exercise]:
    e = db.get(Exercise, exercise_id)
    if e is None or (e.owner_user_id is not None and e.owner_user_id != user_id):
        return None
    return e


@router.get("")
def list_exercises(
    muscle: Optional[str] = Query(default=None),
    equipment: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Exercise).where(_visible(user.id))
    if muscle:
        stmt = stmt.where(Exercise.primary_muscle == muscle)
    if equipment:
        stmt = stmt.where(Exercise.equipment == equipment)
    if q:
        stmt = stmt.where(Exercise.name.ilike(f"%{q}%"))
    rows = db.scalars(
        stmt.order_by(Exercise.name).limit(limit).offset(offset)
    ).all()
    return {"items": [exercise_public(e) for e in rows], "limit": limit, "offset": offset}


@router.get("/{exercise_id}")
def get_exercise(
    exercise_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    e = visible_exercise(db, exercise_id, user.id)
    if e is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return exercise_public(e)


@router.post("", status_code=201)
def create_exercise(
    body: ExerciseIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    e = Exercise(
        name=body.name,
        category=body.category,
        primary_muscle=body.primary_muscle,
        secondary_muscles=json.dumps(body.secondary_muscles),
        equipment=body.equipment,
        is_main_lift=body.is_main_lift,
        is_custom=True,
        owner_user_id=user.id,
    )
    db.add(e)
    db.flush()
    return exercise_public(e)
