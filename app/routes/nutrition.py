"""Nutrition plan routes (contract §8, ``/api/nutrition``).

Thin router over :mod:`app.services.nutrition`. ``POST /plan/generate`` takes no
body — targets are derived from the user's profile.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..services import nutrition

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


@router.post("/plan/generate", status_code=201)
def generate_plan(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    plan = nutrition.generate_plan(db, user)
    return nutrition.plan_public(plan)


@router.get("/plan/active")
def get_active_plan(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    plan = nutrition.active_plan(db, user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="no active nutrition plan")
    return nutrition.plan_public(plan)


@router.get("/today")
def get_today(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    return nutrition.nutrition_today(db, user)
