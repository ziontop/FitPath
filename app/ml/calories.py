"""BMR (Mifflin-St Jeor) + TDEE calculation.

Goal-based calorie *deltas* deliberately live in :mod:`app.training.params`
(``NUTRITION[...].kcal_delta_per_day``) so the persona nutrition targets have a
single source of truth. Callers that need a goal-adjusted daily target should
use :func:`app.services.nutrition.goal_target_kcal`.
"""
from __future__ import annotations

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def bmr_mifflin_st_jeor(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Return Basal Metabolic Rate in kcal/day."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex == "male" else -161)


def tdee(bmr: float, activity_level: str) -> float:
    """Total Daily Energy Expenditure in kcal/day."""
    return bmr * ACTIVITY_MULTIPLIERS.get(activity_level, 1.55)
