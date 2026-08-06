"""Nutrition plan generation + daily targets (contract §8).

Targets are derived deterministically: BMR (Mifflin-St Jeor) -> TDEE
(:mod:`app.ml.calories`) -> apply the persona kcal delta from
:data:`~app.training.params.NUTRITION` -> split into protein/fat/carbs via
:func:`~app.training.params.macro_targets` (grams keyed off bodyweight). Daily
meal suggestions reuse the offline coach food recommender
(:func:`app.ml.coach.recommend_foods_for_macros`).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ml import coach
from ..ml.calories import bmr_mifflin_st_jeor, tdee
from ..models import MealLog, NutritionPlan, Profile, User
from ..training.params import NUTRITION, Goal, macro_targets
from .mapping import nutrition_goal_to_params

_MIN_KCAL = 1200.0
_MEALS_PER_DAY: dict[Goal, int] = {
    Goal.CUT_POWERLIFTING: 4,
    Goal.BULK_HYPERTROPHY: 5,
    Goal.MAINGAIN_INCONSISTENT: 3,
}

# Sensible defaults if the user has no logged foods yet to draw suggestions from.
_FALLBACK_SUGGESTIONS: list[dict] = [
    {"name": "Grilled chicken & rice", "kcal": 520, "protein_g": 45, "carbs_g": 55, "fat_g": 12},
    {"name": "Greek yogurt & berries", "kcal": 240, "protein_g": 24, "carbs_g": 28, "fat_g": 4},
    {"name": "Salmon & sweet potato", "kcal": 480, "protein_g": 38, "carbs_g": 40, "fat_g": 18},
]


def _require_profile(db: Session, user_id: int) -> Profile:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(
            status_code=400, detail="set your profile first via PUT /api/profile"
        )
    return profile


def _derive_targets(profile: Profile) -> tuple[Goal, int, dict]:
    """Return ``(persona, target_kcal, macro grams)`` for a profile."""
    persona = nutrition_goal_to_params(profile.goal)
    bmr = bmr_mifflin_st_jeor(
        profile.sex, profile.weight_kg, profile.height_cm, profile.age
    )
    maintenance = tdee(bmr, profile.activity_level)
    target = max(_MIN_KCAL, maintenance + NUTRITION[persona].kcal_delta_per_day)
    macros = macro_targets(target, profile.weight_kg, persona)
    return persona, round(target), macros


def goal_target_kcal(profile: Profile) -> int:
    """Daily kcal target for a profile: maintenance TDEE + the persona goal delta.

    Single source of truth for the calorie target, shared by the nutrition plan
    generator, the insights dashboard and the AI coach so the number a user sees
    is always consistent (rather than each surface re-deriving its own delta with
    a slightly different value).
    """
    _persona, target_kcal, _macros = _derive_targets(profile)
    return target_kcal


def active_macro_targets(
    db: Session, user_id: int, profile: Optional[Profile] = None
) -> dict[str, float]:
    """Protein/carbs/fat *gram* targets, keyed ``protein``/``carbs``/``fat``.

    Single source of truth for macro targets shared with the AI coach so every
    screen agrees. Prefers the user's **active nutrition plan** (the numbers the
    Nutrition screen shows); otherwise falls back to the per-kg params-derived
    macros for the profile. This replaces the coach's old fixed 30/40/30 split
    (which disagreed with the plan — e.g. telling a bulker 231 g AND 156 g
    protein).
    """
    plan = active_plan(db, user_id)
    if plan is not None:
        return {
            "protein": float(plan.protein_g),
            "carbs": float(plan.carbs_g),
            "fat": float(plan.fat_g),
        }
    if profile is None:
        profile = db.get(Profile, user_id)
    if profile is None:
        return {"protein": 0.0, "carbs": 0.0, "fat": 0.0}
    _persona, _target, macros = _derive_targets(profile)
    return {
        "protein": macros["protein_g"],
        "carbs": macros["carbs_g"],
        "fat": macros["fat_g"],
    }


def plan_public(plan: NutritionPlan) -> dict:
    return {
        "id": plan.id,
        "goal": plan.goal,
        "target_kcal": plan.target_kcal,
        "protein_g": plan.protein_g,
        "carbs_g": plan.carbs_g,
        "fat_g": plan.fat_g,
        "meals_per_day": plan.meals_per_day,
        "active": plan.active,
    }


def active_plan(db: Session, user_id: int) -> Optional[NutritionPlan]:
    return db.scalar(
        select(NutritionPlan)
        .where(NutritionPlan.user_id == user_id, NutritionPlan.active.is_(True))
        .order_by(NutritionPlan.id.desc())
    )


def _deactivate_all(db: Session, user_id: int) -> None:
    for plan in db.scalars(
        select(NutritionPlan).where(
            NutritionPlan.user_id == user_id, NutritionPlan.active.is_(True)
        )
    ).all():
        plan.active = False
    db.flush()


def generate_plan(db: Session, user: User) -> NutritionPlan:
    """Create (and activate) a nutrition plan derived from the user's profile."""
    profile = _require_profile(db, user.id)
    persona, target_kcal, macros = _derive_targets(profile)

    _deactivate_all(db, user.id)
    plan = NutritionPlan(
        user_id=user.id,
        goal=profile.goal,
        target_kcal=target_kcal,
        protein_g=round(macros["protein_g"]),
        carbs_g=round(macros["carbs_g"]),
        fat_g=round(macros["fat_g"]),
        meals_per_day=_MEALS_PER_DAY[persona],
        active=True,
    )
    db.add(plan)
    db.flush()
    db.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------
def _fetch_today_meals(db: Session, user_id: int) -> list[MealLog]:
    today = datetime.now().date()
    start = datetime.combine(today, time.min)
    end = start + timedelta(days=1)
    return list(
        db.scalars(
            select(MealLog).where(
                MealLog.user_id == user_id,
                MealLog.eaten_at >= start,
                MealLog.eaten_at < end,
            )
        ).all()
    )


def _fetch_history_meals(db: Session, user_id: int, days: int = 30) -> list[dict]:
    cutoff = datetime.combine(
        datetime.now().date() - timedelta(days=days), time.min
    )
    rows = db.scalars(
        select(MealLog)
        .where(MealLog.user_id == user_id, MealLog.eaten_at >= cutoff)
        .order_by(MealLog.eaten_at)
    ).all()
    return [
        {
            "name": m.name,
            "category": m.category,
            "kcal": m.kcal,
            "protein_g": m.protein_g,
            "carbs_g": m.carbs_g,
            "fat_g": m.fat_g,
        }
        for m in rows
    ]


def _meal_suggestions(db: Session, user_id: int, gap: dict) -> list[dict]:
    history = _fetch_history_meals(db, user_id, days=30)
    recommended = coach.recommend_foods_for_macros(history, gap, top_n=3)
    suggestions = [
        {
            "name": r["name"],
            "kcal": r["kcal"],
            "protein_g": r["protein_g"],
            "carbs_g": r["carbs_g"],
            "fat_g": r["fat_g"],
        }
        for r in recommended
    ]
    return suggestions or _FALLBACK_SUGGESTIONS


def nutrition_today(db: Session, user: User) -> dict:
    """Targets vs consumed vs remaining for today, plus meal suggestions."""
    profile = _require_profile(db, user.id)

    plan = active_plan(db, user.id)
    if plan is not None:
        targets = {
            "kcal": plan.target_kcal,
            "protein_g": plan.protein_g,
            "carbs_g": plan.carbs_g,
            "fat_g": plan.fat_g,
        }
    else:
        _persona, target_kcal, macros = _derive_targets(profile)
        targets = {
            "kcal": target_kcal,
            "protein_g": round(macros["protein_g"]),
            "carbs_g": round(macros["carbs_g"]),
            "fat_g": round(macros["fat_g"]),
        }

    meals = _fetch_today_meals(db, user.id)
    consumed = {
        "kcal": round(sum(m.kcal for m in meals)),
        "protein_g": round(sum(m.protein_g or 0 for m in meals), 1),
        "carbs_g": round(sum(m.carbs_g or 0 for m in meals), 1),
        "fat_g": round(sum(m.fat_g or 0 for m in meals), 1),
    }
    remaining = {key: round(targets[key] - consumed[key], 1) for key in targets}

    gap = {
        "protein": targets["protein_g"] - consumed["protein_g"],
        "carbs": targets["carbs_g"] - consumed["carbs_g"],
        "fat": targets["fat_g"] - consumed["fat_g"],
    }

    return {
        "targets": targets,
        "consumed": consumed,
        "remaining": remaining,
        "meal_suggestions": _meal_suggestions(db, user.id, gap),
    }


__all__ = [
    "plan_public",
    "active_plan",
    "generate_plan",
    "goal_target_kcal",
    "active_macro_targets",
    "nutrition_today",
]
