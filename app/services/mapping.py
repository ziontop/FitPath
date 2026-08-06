"""Mapping helpers that bridge API-contract vocabulary onto ``app.training.params``.

The contract (docs/API-CONTRACT.md §2) speaks in terms of ``training_goal``
(``powerlifting|hypertrophy|maingain``), nutrition ``goal``
(``lose|maintain|gain``), ``experience_level`` and granular catalog
``primary_muscle`` strings. The research spec speaks in :class:`~app.training.params.Goal`
personas, :class:`~app.training.params.ExperienceLevel` and the coarser
:class:`~app.training.params.Muscle` groups used for the volume landmarks.

This module also resolves the SBD-based program templates' free-text exercise
NAMES onto concrete catalog :class:`~app.models.Exercise` rows (case-insensitive,
then a small curated alias table, then normalized/fuzzy matching, and finally —
only as a last resort — by creating a global exercise).
"""
from __future__ import annotations

import difflib
import json
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Exercise
from ..training.params import (
    EXPERIENCE_PROGRESSION,
    ExperienceLevel,
    Goal,
    Muscle,
)

# ---------------------------------------------------------------------------
# Goal + experience mapping
# ---------------------------------------------------------------------------
#: ``profile.training_goal`` -> training persona in the research spec.
TRAINING_GOAL_TO_PARAMS: dict[str, Goal] = {
    "powerlifting": Goal.CUT_POWERLIFTING,
    "hypertrophy": Goal.BULK_HYPERTROPHY,
    "maingain": Goal.MAINGAIN_INCONSISTENT,
}
#: nutrition ``goal`` (lose/maintain/gain) -> persona for NUTRITION deltas/macros.
NUTRITION_GOAL_TO_PARAMS: dict[str, Goal] = {
    "lose": Goal.CUT_POWERLIFTING,
    "maintain": Goal.MAINGAIN_INCONSISTENT,
    "gain": Goal.BULK_HYPERTROPHY,
}

DEFAULT_TRAINING_GOAL = "hypertrophy"
DEFAULT_NUTRITION_GOAL = "maintain"
DEFAULT_DAYS_PER_WEEK = 4

#: How each persona's weekly template is described to the frontend.
SPLIT_TYPE: dict[Goal, str] = {
    Goal.CUT_POWERLIFTING: "upper_lower",
    Goal.BULK_HYPERTROPHY: "push_pull_legs",
    Goal.MAINGAIN_INCONSISTENT: "full_body",
}

_CONTRACT_TRAINING_GOALS = set(TRAINING_GOAL_TO_PARAMS)


def training_goal_to_params(training_goal: Optional[str]) -> Goal:
    """Map a contract ``training_goal`` onto a :class:`Goal` (defaults hypertrophy)."""
    return TRAINING_GOAL_TO_PARAMS.get(
        (training_goal or "").strip().lower(),
        TRAINING_GOAL_TO_PARAMS[DEFAULT_TRAINING_GOAL],
    )


def nutrition_goal_to_params(goal: Optional[str]) -> Goal:
    """Map a contract nutrition ``goal`` onto a :class:`Goal` (defaults maintain)."""
    return NUTRITION_GOAL_TO_PARAMS.get(
        (goal or "").strip().lower(),
        NUTRITION_GOAL_TO_PARAMS[DEFAULT_NUTRITION_GOAL],
    )


def contract_training_goal(training_goal: Optional[str], goal: Goal) -> str:
    """Return the contract ``training_goal`` string to persist on a Program."""
    tg = (training_goal or "").strip().lower()
    if tg in _CONTRACT_TRAINING_GOALS:
        return tg
    for contract_value, persona in TRAINING_GOAL_TO_PARAMS.items():
        if persona is goal:
            return contract_value
    return DEFAULT_TRAINING_GOAL


def resolve_experience(experience: Optional[str]) -> ExperienceLevel:
    """Map a contract ``experience_level`` onto :class:`ExperienceLevel`."""
    try:
        return ExperienceLevel((experience or "").strip().lower())
    except ValueError:
        return ExperienceLevel.INTERMEDIATE


def progression_for(experience: ExperienceLevel) -> str:
    """Progression-scheme label for an experience level (from EXPERIENCE_PROGRESSION)."""
    return EXPERIENCE_PROGRESSION[experience].value


# ---------------------------------------------------------------------------
# Muscle-group mapping (catalog primary_muscle -> volume-landmark Muscle)
# ---------------------------------------------------------------------------
_PRIMARY_MUSCLE_TO_GROUP: dict[str, Muscle] = {
    "chest": Muscle.CHEST,
    "upper_chest": Muscle.CHEST,
    "back": Muscle.BACK,
    "lats": Muscle.BACK,
    "upper_back": Muscle.BACK,
    "traps": Muscle.BACK,
    "lower_back": Muscle.BACK,
    "quads": Muscle.QUADS,
    "hamstrings": Muscle.HAMSTRINGS,
    "glutes": Muscle.GLUTES,
    "shoulders": Muscle.SHOULDERS,
    "front_delts": Muscle.SHOULDERS,
    "side_delts": Muscle.SHOULDERS,
    "rear_delts": Muscle.SHOULDERS,
    "biceps": Muscle.BICEPS,
    "triceps": Muscle.TRICEPS,
    "calves": Muscle.CALVES,
    "core": Muscle.ABS,
    "abs": Muscle.ABS,
    "obliques": Muscle.ABS,
}


def muscle_group_for(primary_muscle: Optional[str]) -> Optional[Muscle]:
    """Coarse volume-landmark :class:`Muscle` for a catalog ``primary_muscle``.

    Returns ``None`` for muscles without a weekly landmark (e.g. forearms), so
    their working sets still count toward *total* volume but not a muscle band.
    """
    if not primary_muscle:
        return None
    return _PRIMARY_MUSCLE_TO_GROUP.get(primary_muscle.strip().lower())


# ---------------------------------------------------------------------------
# Exercise-name resolution (template name -> catalog Exercise row)
# ---------------------------------------------------------------------------
# Template names that don't match the seeded catalog verbatim. Keys are
# lowercased template names; values are exact catalog names.
_ALIASES: dict[str, str] = {
    "weighted pull-up": "Pull-up",
    "incline db press": "Incline Dumbbell Press",
    "seated db press": "Dumbbell Shoulder Press",
    "cable fly": "Cable Crossover",
    "rear-delt fly": "Rear Delt Fly",
    "incline db curl": "Dumbbell Curl",
}

_ABBREVIATIONS = {"db": "dumbbell", "bb": "barbell", "ohp": "overhead press"}

#: Equipment tags each contract ``equipment`` level can actually use.
#: ``None`` means "everything" (full gym). A basic home setup is dumbbells +
#: bodyweight; a bodyweight level is exactly that. Used to substitute template
#: lifts a user can't perform (e.g. a home_basic lifter shouldn't get an
#: all-barbell SBD program).
EQUIPMENT_ALLOWED: dict[str, Optional[set[str]]] = {
    "full_gym": None,
    "home_basic": {"dumbbell", "bodyweight"},
    "bodyweight": {"bodyweight"},
}


def allowed_equipment_for(equipment: Optional[str]) -> Optional[set[str]]:
    """Allowed catalog equipment tags for a contract ``equipment`` level.

    Returns ``None`` (no restriction) for ``full_gym`` or any unknown value.
    """
    return EQUIPMENT_ALLOWED.get((equipment or "").strip().lower())


def _normalize(name: str) -> str:
    """Lowercase, expand common abbreviations and drop punctuation for matching."""
    lowered = name.strip().lower().replace("-", " ").replace("/", " ")
    tokens = [_ABBREVIATIONS.get(tok, tok) for tok in lowered.split() if tok]
    return " ".join(tokens)


# Keyword -> (category, primary_muscle, equipment) for the create fallback.
_INFER_RULES: tuple[tuple[tuple[str, ...], tuple[str, str, str]], ...] = (
    (("squat",), ("compound", "quads", "barbell")),
    (("deadlift", "rdl"), ("compound", "hamstrings", "barbell")),
    (("hip thrust", "glute"), ("compound", "glutes", "barbell")),
    (("leg curl", "hamstring"), ("isolation", "hamstrings", "machine")),
    (("leg extension",), ("isolation", "quads", "machine")),
    (("calf",), ("isolation", "calves", "machine")),
    (("bench", "chest", "fly", "press up", "push"), ("compound", "chest", "barbell")),
    (("overhead press", "shoulder press", "ohp"), ("compound", "shoulders", "barbell")),
    (("lateral", "delt", "raise"), ("isolation", "shoulders", "dumbbell")),
    (("row", "pulldown", "pull up", "pull-up", "chin"), ("compound", "back", "barbell")),
    (("shrug",), ("isolation", "traps", "barbell")),
    (("curl",), ("isolation", "biceps", "dumbbell")),
    (("pushdown", "triceps", "extension", "skull"), ("isolation", "triceps", "cable")),
    (("crunch", "leg raise", "plank", "ab ", "core"), ("isolation", "core", "bodyweight")),
)


def _infer_exercise(name: str) -> tuple[str, str, str]:
    """Best-effort ``(category, primary_muscle, equipment)`` for an unknown name."""
    normalized = _normalize(name)
    for keywords, spec in _INFER_RULES:
        if any(kw.strip() in normalized for kw in keywords):
            return spec
    return ("compound", "core", "barbell")


class ExerciseResolver:
    """Resolves template exercise names to catalog rows, caching per generation.

    Loads the user's visible catalog (global rows + their own custom rows) once,
    then resolves names via: curated alias -> exact case-insensitive -> normalized
    -> fuzzy -> create a new global exercise. Newly created rows are cached so a
    repeated name within one program build reuses the same row.

    When ``allowed_equipment`` is given (a set of equipment tags), a resolved
    exercise the user can't perform is substituted for a same-muscle exercise
    using allowed equipment (e.g. Back Squat -> Goblet Squat for a home_basic
    lifter). If no allowed alternative exists, the original is kept so the
    program is never left with a hole.
    """

    def __init__(
        self,
        db: Session,
        user_id: int,
        allowed_equipment: Optional[set[str]] = None,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._allowed = allowed_equipment
        rows = db.scalars(
            select(Exercise).where(
                or_(
                    Exercise.owner_user_id.is_(None),
                    Exercise.owner_user_id == user_id,
                )
            )
        ).all()
        self._by_ci: dict[str, Exercise] = {}
        self._by_norm: dict[str, Exercise] = {}
        # Allowed-equipment substitution pools, indexed by primary muscle and by
        # the coarser volume-landmark muscle group (deterministic name order).
        self._sub_by_muscle: dict[str, list[Exercise]] = {}
        self._sub_by_group: dict[Muscle, list[Exercise]] = {}
        for e in rows:
            self._by_ci.setdefault(e.name.strip().lower(), e)
            self._by_norm.setdefault(_normalize(e.name), e)
            if allowed_equipment is not None and e.equipment in allowed_equipment:
                self._sub_by_muscle.setdefault(
                    e.primary_muscle.strip().lower(), []
                ).append(e)
                group = muscle_group_for(e.primary_muscle)
                if group is not None:
                    self._sub_by_group.setdefault(group, []).append(e)
        for pool in (*self._sub_by_muscle.values(), *self._sub_by_group.values()):
            pool.sort(key=lambda ex: ex.name)

    def resolve(self, name: str) -> Exercise:
        return self._substitute(self._resolve_raw(name))

    def _resolve_raw(self, name: str) -> Exercise:
        key = name.strip().lower()

        alias = _ALIASES.get(key)
        if alias:
            hit = self._by_ci.get(alias.strip().lower()) or self._by_norm.get(
                _normalize(alias)
            )
            if hit is not None:
                return hit

        hit = self._by_ci.get(key)
        if hit is not None:
            return hit

        normalized = _normalize(name)
        hit = self._by_norm.get(normalized)
        if hit is not None:
            return hit

        close = difflib.get_close_matches(
            normalized, list(self._by_norm.keys()), n=1, cutoff=0.82
        )
        if close:
            return self._by_norm[close[0]]

        return self._create(name)

    def _substitute(self, exercise: Exercise) -> Exercise:
        """Swap in an allowed-equipment alternative if the user can't do this one."""
        if self._allowed is None or exercise.equipment in self._allowed:
            return exercise
        muscle = exercise.primary_muscle.strip().lower()
        pool = self._sub_by_muscle.get(muscle, [])
        same_category = [e for e in pool if e.category == exercise.category]
        candidates = same_category or pool
        if not candidates:
            group = muscle_group_for(exercise.primary_muscle)
            candidates = self._sub_by_group.get(group, []) if group else []
        for candidate in candidates:
            if candidate.id != exercise.id:
                return candidate
        return exercise  # no allowed alternative — keep the original

    def _create(self, name: str) -> Exercise:
        category, primary_muscle, equipment = _infer_exercise(name)
        exercise = Exercise(
            name=name.strip(),
            category=category,
            primary_muscle=primary_muscle,
            secondary_muscles=json.dumps([]),
            equipment=equipment,
            is_main_lift=False,
            is_custom=False,
            owner_user_id=None,
        )
        self._db.add(exercise)
        self._db.flush()
        self._by_ci[exercise.name.strip().lower()] = exercise
        self._by_norm[_normalize(exercise.name)] = exercise
        return exercise


__all__ = [
    "TRAINING_GOAL_TO_PARAMS",
    "NUTRITION_GOAL_TO_PARAMS",
    "DEFAULT_TRAINING_GOAL",
    "DEFAULT_NUTRITION_GOAL",
    "DEFAULT_DAYS_PER_WEEK",
    "SPLIT_TYPE",
    "training_goal_to_params",
    "nutrition_goal_to_params",
    "contract_training_goal",
    "resolve_experience",
    "progression_for",
    "muscle_group_for",
    "EQUIPMENT_ALLOWED",
    "allowed_equipment_for",
    "ExerciseResolver",
]
