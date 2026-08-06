"""Unified recommendations route (contract §9, ``/api/recommendations``).

Ships the legacy ``/today`` shape (unchanged, backward-compatible) plus the
additive, deterministic history-adaptive endpoints from
``docs/ADAPTIVE-RECOMMENDATIONS.md``:

* ``GET /adaptive`` — full envelope (meals + workout + tip) for the Today screen.
* ``GET /meals``    — detailed adaptive meal picks (Nutrition screen).
* ``GET /workout``  — detailed adaptive workout recommendation (Workout screen).

All three are auth-required and user-scoped; a missing profile raises ``400``
(mirroring ``/nutrition/today``). Responses are validated against the typed
models in :mod:`app.schemas` for OpenAPI + contract enforcement.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import (
    AdaptiveMealsBlock,
    AdaptiveRecommendation,
    AdaptiveWorkoutBlock,
    MealCategory,
)
from ..services import adaptive, recommendations

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/today")
def get_today(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Legacy unified payload — ``{workout, nutrition, tip}`` (unchanged)."""
    return recommendations.recommendations_today(db, user)


@router.get("/adaptive", response_model=AdaptiveRecommendation)
def get_adaptive(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Full adaptive envelope: meal picks + workout + a data-grounded tip."""
    return adaptive.adaptive_today(db, user)


@router.get("/meals", response_model=AdaptiveMealsBlock)
def get_adaptive_meals(
    category: Optional[MealCategory] = Query(
        default=None, description="restrict picks to a meal category"
    ),
    limit: int = Query(default=3, ge=1, le=10),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """History-ranked, portion-scaled, diversified meal suggestions."""
    return adaptive.adaptive_meals(db, user, category=category, limit=limit)


@router.get("/workout", response_model=AdaptiveWorkoutBlock)
def get_adaptive_workout(
    program_day_id: Optional[int] = Query(
        default=None,
        description="force a specific program day instead of next-in-rotation",
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Per-exercise double-progression recommendation for today's session."""
    return adaptive.adaptive_workout(db, user, program_day_id=program_day_id)
