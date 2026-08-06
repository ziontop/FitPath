"""Profile routes — 1:1 with the authenticated user (contract §3)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Profile, User, WeightLog
from ..schemas import Profile as ProfileIn

router = APIRouter(prefix="/api/profile", tags=["profile"])

_FIELDS = (
    "name",
    "sex",
    "age",
    "height_cm",
    "weight_kg",
    "activity_level",
    "goal",
    "training_goal",
    "experience_level",
    "days_per_week",
    "equipment",
    "units",
    "wake_time",
    "water_goal_ml",
    "step_goal",
    "exercise_goal_min",
)


def profile_public(p: Profile) -> dict:
    return {"user_id": p.user_id, **{f: getattr(p, f) for f in _FIELDS}}


@router.get("")
def get_profile(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    profile = db.get(Profile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not set")
    return profile_public(profile)


@router.put("")
def upsert_profile(
    body: ProfileIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    data = body.model_dump()
    profile = db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id, **data)
        db.add(profile)
    else:
        for field, value in data.items():
            setattr(profile, field, value)

    # Seed today's weight so the Trends chart starts populated (idempotent).
    today = date.today()
    existing = db.scalar(
        select(WeightLog).where(
            WeightLog.user_id == user.id, WeightLog.logged_for == today
        )
    )
    if existing is None:
        db.add(WeightLog(user_id=user.id, weight_kg=body.weight_kg, logged_for=today))

    db.flush()
    return profile_public(profile)
