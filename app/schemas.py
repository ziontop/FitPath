"""Pydantic v2 request/response schemas for the multi-user FitPath API.

Field names match ``docs/API-CONTRACT.md`` exactly so the frontend integrates
without translation. Enums are ``Literal`` aliases (kept in sync with the
contract's Enums section) so invalid values fail with a 422 automatically.
"""
from __future__ import annotations

import datetime as _dt
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums (contract §2)
# ---------------------------------------------------------------------------
Sex = Literal["male", "female"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
Goal = Literal["lose", "maintain", "gain"]
TrainingGoal = Literal["powerlifting", "hypertrophy", "maingain"]
ExperienceLevel = Literal["beginner", "intermediate", "advanced"]
Equipment = Literal["full_gym", "home_basic", "bodyweight"]
Units = Literal["metric", "imperial"]
Intensity = Literal["light", "moderate", "vigorous"]
MealCategory = Literal["breakfast", "lunch", "dinner", "snack"]
ExerciseCategory = Literal["compound", "isolation"]
AppleHealthType = Literal["steps", "weight", "sleep", "water", "workouts"]


# ---------------------------------------------------------------------------
# Auth (contract §1)
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=256)


class LoginIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


# ---------------------------------------------------------------------------
# Profile (contract §3)
# ---------------------------------------------------------------------------
class Profile(BaseModel):
    name: Optional[str] = None
    sex: Sex
    age: int = Field(ge=10, le=120)
    height_cm: float = Field(gt=50, lt=260)
    weight_kg: float = Field(gt=20, lt=400)
    activity_level: ActivityLevel = "moderate"
    goal: Goal = "maintain"
    training_goal: TrainingGoal = "hypertrophy"
    experience_level: ExperienceLevel = "beginner"
    days_per_week: int = Field(default=3, ge=1, le=7)
    equipment: Equipment = "full_gym"
    units: Units = "metric"
    wake_time: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    water_goal_ml: int = Field(default=2500, ge=500, le=10000)
    step_goal: int = Field(default=8000, ge=1000, le=50000)
    exercise_goal_min: int = Field(default=30, ge=5, le=600)


# ---------------------------------------------------------------------------
# Nutrition / health logs (contract §4)
# ---------------------------------------------------------------------------
class MealIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kcal: float = Field(ge=0, le=10000)
    category: MealCategory = "snack"
    protein_g: Optional[float] = Field(default=None, ge=0, le=500)
    carbs_g: Optional[float] = Field(default=None, ge=0, le=1000)
    fat_g: Optional[float] = Field(default=None, ge=0, le=500)
    eaten_at: Optional[datetime] = None


class ActivityIn(BaseModel):
    activity: str = Field(min_length=1, max_length=120)
    minutes: float = Field(gt=0, le=24 * 60)
    intensity: Intensity = "moderate"
    done_at: Optional[datetime] = None


class SleepIn(BaseModel):
    hours: float = Field(ge=0, le=24)
    wake_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    logged_for: Optional[date] = None


class StepsIn(BaseModel):
    steps: int = Field(ge=0, le=200_000)
    logged_for: Optional[date] = None


class WaterIn(BaseModel):
    ml: int = Field(ge=1, le=5000)
    logged_at: Optional[datetime] = None


class WeightIn(BaseModel):
    weight_kg: float = Field(gt=20, lt=400)
    logged_for: Optional[date] = None


# ---------------------------------------------------------------------------
# Apple Health integration
# ---------------------------------------------------------------------------
class AppleHealthDeleteIn(BaseModel):
    types: Optional[list[AppleHealthType]] = None
    from_: Optional[date] = Field(default=None, alias="from")
    to: Optional[date] = None


class AppleHealthTokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)


class ShortcutStepsIn(BaseModel):
    date: date
    count: int = Field(ge=0, le=200_000)


class ShortcutWeightIn(BaseModel):
    date: date
    kg: float = Field(gt=20, lt=400)


class ShortcutSleepIn(BaseModel):
    date: date
    hours: float = Field(ge=0, le=24)
    wake_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class ShortcutWaterIn(BaseModel):
    date: date
    ml: int = Field(ge=1, le=5000)


class ShortcutWorkoutIn(BaseModel):
    activity: str = Field(min_length=1, max_length=120)
    start: datetime
    end: Optional[datetime] = None
    source: str = Field(default="Shortcut", min_length=1, max_length=64)
    minutes: float = Field(gt=0, le=24 * 60)
    intensity: Intensity = "moderate"
    kcal: Optional[float] = Field(default=None, ge=0, le=10000)


class ShortcutSyncIn(BaseModel):
    steps: list[ShortcutStepsIn] = Field(default_factory=list)
    weight: list[ShortcutWeightIn] = Field(default_factory=list)
    sleep: list[ShortcutSleepIn] = Field(default_factory=list)
    water: list[ShortcutWaterIn] = Field(default_factory=list)
    workouts: list[ShortcutWorkoutIn] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Exercises (contract §5)
# ---------------------------------------------------------------------------
class ExerciseIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: ExerciseCategory = "compound"
    primary_muscle: str = Field(min_length=1, max_length=40)
    secondary_muscles: list[str] = Field(default_factory=list)
    equipment: str = Field(min_length=1, max_length=32)
    is_main_lift: bool = False


# ---------------------------------------------------------------------------
# Workouts & sets (contract §6)
# ---------------------------------------------------------------------------
class WorkoutIn(BaseModel):
    # NOTE: the field is named ``date`` per the API contract, but the annotation
    # must reference ``_dt.date`` (not the bare ``date`` import): with
    # ``from __future__ import annotations`` the ``date = None`` default binds the
    # name ``date`` in the class namespace, so a bare ``Optional[date]`` would
    # resolve the forward-ref to ``Optional[None]`` == ``NoneType`` and reject any
    # real date with 422 "Input should be None".
    date: Optional[_dt.date] = None
    name: Optional[str] = Field(default=None, max_length=120)
    program_day_id: Optional[int] = None
    notes: Optional[str] = None


class WorkoutUpdate(BaseModel):
    date: Optional[_dt.date] = None
    name: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class SetIn(BaseModel):
    exercise_id: int
    weight: float = Field(ge=0, le=1000)
    reps: int = Field(ge=0, le=1000)
    rpe: Optional[float] = Field(default=None, ge=0, le=10)
    is_warmup: bool = False
    set_index: Optional[int] = Field(default=None, ge=0)


class SetUpdate(BaseModel):
    exercise_id: Optional[int] = None
    weight: Optional[float] = Field(default=None, ge=0, le=1000)
    reps: Optional[int] = Field(default=None, ge=0, le=1000)
    rpe: Optional[float] = Field(default=None, ge=0, le=10)
    is_warmup: Optional[bool] = None
    set_index: Optional[int] = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Programs (contract §7)
# ---------------------------------------------------------------------------
class ProgramGenerateIn(BaseModel):
    training_goal: Optional[TrainingGoal] = None
    days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    experience: Optional[ExperienceLevel] = None
    equipment: Optional[Equipment] = None


class ProgramUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Adaptive recommendations (docs/ADAPTIVE-RECOMMENDATIONS.md §6.3)
# ---------------------------------------------------------------------------
# Additive, deterministic history-based engine under /api/recommendations/*.
# Field names match the design doc's JSON 1:1; routes construct plain dicts and
# use these purely as ``response_model=`` for validation + OpenAPI.
Confidence = Literal["low", "medium", "high"]
WorkoutAction = Literal["start", "increase", "hold", "reduce", "deload"]
Direction = Literal["up", "down", "flat"]
Consistency = Literal["on_track", "inconsistent", "returning"]

RECOMMENDATION_VERSION = "adaptive-v1"
RECOMMENDATION_ALGORITHM = "history-adaptive-deterministic"


# ---- shared ----
class MacroSet(BaseModel):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class MealPayload(BaseModel):
    """Ready to POST to /api/logs/meals (mirrors schemas.MealIn)."""

    name: str
    kcal: float
    category: MealCategory
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None


# ---- meals ----
class MealScoreComponents(BaseModel):
    macro_fit: float
    recency: float
    frequency: float
    adherence: float
    category_fit: float
    favorite: float


class AdaptiveMealSuggestion(BaseModel):
    name: str
    category: MealCategory
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    portion: float = 1.0
    score: float
    components: MealScoreComponents
    reason: str
    history_basis: str
    confidence: Confidence
    logged_count: int
    last_eaten_at: Optional[str] = None
    meal_payload: MealPayload


class NextMealHint(BaseModel):
    predicted_category: MealCategory
    predicted_time: str
    suggested_kcal: int


class MealHistoryBasis(BaseModel):
    window_days: int
    days_observed: int
    total_meals: int
    distinct_foods: int
    adherent_days: int


class AdaptiveMealsBlock(BaseModel):
    version: str = RECOMMENDATION_VERSION
    algorithm: str = RECOMMENDATION_ALGORITHM
    targets: MacroSet
    consumed: MacroSet
    remaining: MacroSet
    next_meal: NextMealHint
    history_basis: MealHistoryBasis
    confidence: Confidence
    suggestions: list[AdaptiveMealSuggestion]


# ---- workout ----
class LastPerformance(BaseModel):
    date: str
    weight: float
    reps: int
    rpe: Optional[float] = None
    sets: int
    e1rm: float


class WeightChange(BaseModel):
    weight_delta_kg: float
    reps_delta: int
    direction: Direction


class E1rmTrendMini(BaseModel):
    first: float
    last: float
    direction: Direction


class AdaptiveExerciseRec(BaseModel):
    exercise_id: int
    name: str
    action: WorkoutAction
    suggested_weight: Optional[float] = None
    target_sets: int
    target_reps: str
    target_rpe: Optional[float] = None
    deload: bool = False
    last_performance: Optional[LastPerformance] = None
    change: WeightChange
    e1rm_trend: Optional[E1rmTrendMini] = None
    confidence: Confidence
    reason: str
    history_basis: str


class WorkoutAdherence(BaseModel):
    sessions_last_14d: int
    scheduled_days_per_week: int
    consistency: Consistency


class AdaptiveWorkoutBlock(BaseModel):
    version: str = RECOMMENDATION_VERSION
    algorithm: str = RECOMMENDATION_ALGORITHM
    rest_day: bool = False
    program_day_id: Optional[int] = None
    name: Optional[str] = None
    deload: bool = False
    confidence: Confidence = "low"
    adherence: Optional[WorkoutAdherence] = None
    reason: str = ""
    exercises: list[AdaptiveExerciseRec] = Field(default_factory=list)


# ---- envelope ----
class AdaptiveRecommendation(BaseModel):
    version: str = RECOMMENDATION_VERSION
    algorithm: str = RECOMMENDATION_ALGORITHM
    generated_at: str
    meals: AdaptiveMealsBlock
    workout: AdaptiveWorkoutBlock
    tip: str
