"""Unified daily recommendation (contract §9).

Composes the programs "today" payload and the nutrition "today" payload (reusing
the same service functions the dedicated routers use — no HTTP self-calls) and
adds a short, data-grounded coaching tip.
"""
from __future__ import annotations

from ..models import User
from sqlalchemy.orm import Session

from . import nutrition, programs


def _build_tip(workout: dict, nutrition_today: dict) -> str:
    remaining = nutrition_today.get("remaining", {})
    kcal_left = max(0, round(remaining.get("kcal", 0)))
    protein_left = max(0, round(remaining.get("protein_g", 0)))

    if workout.get("rest_day"):
        return (
            f"Rest day — prioritise sleep and hydration, and still aim for "
            f"~{protein_left}g more protein to support recovery."
        )

    name = workout.get("name") or "your session"
    exercises = workout.get("exercises") or []
    lead = exercises[0]["name"] if exercises else "your main lift"
    return (
        f"Today is {name}. Warm up, then work up to {lead} at the prescribed RPE. "
        f"You have {kcal_left} kcal and {protein_left}g protein left to hit today's target."
    )


def recommendations_today(db: Session, user: User) -> dict:
    workout = programs.today_workout(db, user)
    nutrition_payload = nutrition.nutrition_today(db, user)
    return {
        "workout": workout,
        "nutrition": nutrition_payload,
        "tip": _build_tip(workout, nutrition_payload),
    }


__all__ = ["recommendations_today"]
