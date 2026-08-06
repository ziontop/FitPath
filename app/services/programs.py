"""Workout program generation + serialization + "today" logic (contract §7).

Programs are built from the researched :data:`~app.training.params.PROGRAM_TEMPLATES`
for the persona derived from the user's ``training_goal``. Each template
``SetPrescription`` becomes a :class:`~app.models.ProgramExercise` (its exercise
name resolved to a catalog row via :class:`~app.services.mapping.ExerciseResolver`),
with the progression scheme taken from the user's experience level.

``today_workout`` rotates the active program's days across the week (spreading
rest days) and derives a suggested working weight per exercise from the user's
recent estimated 1RM.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Profile, Program, ProgramDay, ProgramExercise, User
from ..training.params import PROGRAM_TEMPLATES, Goal
from . import performance
from .mapping import (
    DEFAULT_DAYS_PER_WEEK,
    SPLIT_TYPE,
    ExerciseResolver,
    allowed_equipment_for,
    contract_training_goal,
    progression_for,
    resolve_experience,
    training_goal_to_params,
)

_PROGRAM_BASE_NAME: dict[Goal, str] = {
    Goal.CUT_POWERLIFTING: "Powerlifting Cut - Upper/Lower",
    Goal.BULK_HYPERTROPHY: "Hypertrophy - Push/Pull/Legs",
    Goal.MAINGAIN_INCONSISTENT: "Maingain - Full Body",
}


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------
def rep_range(reps: int, compound: bool) -> str:
    """Display rep-range string (e.g. ``"6-9"``) anchored at the prescribed reps.

    The prescription's target reps is the low end; the spread widens for
    higher-rep work and is a touch larger for accessories than compounds.
    """
    if reps <= 1:
        return "1"
    spread = 2 if reps <= 5 else 3 if reps <= 8 else 4 if reps <= 12 else 5
    if not compound:
        spread += 1
    return f"{reps}-{reps + spread}"


def low_rep(target_reps: str) -> int:
    """Parse the leading integer of a rep-range string (``"6-10"`` -> ``6``)."""
    digits = ""
    for ch in target_reps.strip():
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else 5


def requested_day_count(days_per_week: Optional[int]) -> int:
    """Clamp the requested training days/week to the valid 1-7 range.

    Unlike the old behaviour, this does NOT clamp down to the template's day
    count — templates are *cycled* (see :func:`cycle_days`) to fill the request,
    so e.g. a 2-day Full-Body A/B template can honour a 3-day/week request (A/B/A).
    """
    requested = days_per_week or DEFAULT_DAYS_PER_WEEK
    return max(1, min(requested, 7))


def cycle_days(day_names: list[str], n_days: int) -> list[str]:
    """Fill ``n_days`` by cycling a template's days (e.g. ``[A, B]`` -> ``A/B/A``)."""
    if not day_names:
        return []
    return [day_names[i % len(day_names)] for i in range(n_days)]


def weekly_schedule(n_days: int) -> dict[int, int]:
    """Map weekday (Mon=0..Sun=6) -> program-day index, spreading rest days."""
    n = max(1, min(n_days, 7))
    return {(i * 7) // n: i for i in range(n)}


def _program_name(goal: Goal, n_days: int) -> str:
    return f"{_PROGRAM_BASE_NAME[goal]} ({n_days}-day)"


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def program_summary(p: Program) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "training_goal": p.training_goal,
        "split_type": p.split_type,
        "days_per_week": p.days_per_week,
        "active": p.active,
    }


def program_exercise_public(pe: ProgramExercise) -> dict:
    return {
        "exercise_id": pe.exercise_id,
        "name": pe.exercise.name if pe.exercise else None,
        "target_sets": pe.target_sets,
        "target_reps": pe.target_reps,
        "target_rpe": pe.target_rpe,
        "rest_seconds": pe.rest_seconds,
        "progression": pe.progression,
    }


def program_day_public(d: ProgramDay) -> dict:
    exercises = sorted(d.exercises, key=lambda pe: pe.order_index)
    return {
        "id": d.id,
        "day_index": d.day_index,
        "name": d.name,
        "exercises": [program_exercise_public(pe) for pe in exercises],
    }


def program_detail(p: Program) -> dict:
    days = sorted(p.days, key=lambda d: d.day_index)
    return {**program_summary(p), "days": [program_day_public(d) for d in days]}


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def _load_full(db: Session, program_id: int, user_id: int) -> Optional[Program]:
    return db.scalar(
        select(Program)
        .where(Program.id == program_id, Program.user_id == user_id)
        .options(
            selectinload(Program.days)
            .selectinload(ProgramDay.exercises)
            .selectinload(ProgramExercise.exercise)
        )
    )


def get_program(db: Session, program_id: int, user_id: int) -> Optional[Program]:
    return _load_full(db, program_id, user_id)


def list_programs(db: Session, user_id: int) -> list[Program]:
    return list(
        db.scalars(
            select(Program)
            .where(Program.user_id == user_id)
            .order_by(Program.active.desc(), Program.id.desc())
        ).all()
    )


def active_program(db: Session, user_id: int) -> Optional[Program]:
    return db.scalar(
        select(Program)
        .where(Program.user_id == user_id, Program.active.is_(True))
        .order_by(Program.id.desc())
        .options(
            selectinload(Program.days)
            .selectinload(ProgramDay.exercises)
            .selectinload(ProgramExercise.exercise)
        )
    )


def _deactivate_all(db: Session, user_id: int) -> None:
    for p in db.scalars(
        select(Program).where(Program.user_id == user_id, Program.active.is_(True))
    ).all():
        p.active = False
    db.flush()


def activate(db: Session, program: Program) -> None:
    _deactivate_all(db, program.user_id)
    program.active = True
    db.flush()


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate_program(
    db: Session,
    user: User,
    *,
    training_goal: Optional[str] = None,
    days_per_week: Optional[int] = None,
    experience: Optional[str] = None,
    equipment: Optional[str] = None,  # accepted for contract parity; templates fixed
) -> Program:
    """Create (and activate) a program for the user from the persona template."""
    profile = db.get(Profile, user.id)

    training_goal = training_goal or (profile.training_goal if profile else None)
    goal = training_goal_to_params(training_goal)
    experience_level = resolve_experience(
        experience or (profile.experience_level if profile else None)
    )
    requested_days = days_per_week or (profile.days_per_week if profile else None)

    template = PROGRAM_TEMPLATES[goal]
    day_names = list(template.keys())
    n_days = requested_day_count(requested_days)
    selected = cycle_days(day_names, n_days)
    progression = progression_for(experience_level)
    # Substitute template lifts the user's equipment can't do (e.g. a home_basic
    # lifter gets dumbbell/bodyweight variants instead of an all-barbell program).
    equipment_level = equipment or (profile.equipment if profile else None)
    resolver = ExerciseResolver(
        db, user.id, allowed_equipment=allowed_equipment_for(equipment_level)
    )

    _deactivate_all(db, user.id)

    program = Program(
        user_id=user.id,
        name=_program_name(goal, n_days),
        training_goal=contract_training_goal(training_goal, goal),
        split_type=SPLIT_TYPE[goal],
        days_per_week=n_days,
        active=True,
    )
    db.add(program)
    db.flush()

    for day_index, day_name in enumerate(selected):
        program_day = ProgramDay(
            program_id=program.id, day_index=day_index, name=day_name
        )
        db.add(program_day)
        db.flush()
        for order_index, sp in enumerate(template[day_name]):
            exercise = resolver.resolve(sp.exercise)
            db.add(
                ProgramExercise(
                    program_day_id=program_day.id,
                    exercise_id=exercise.id,
                    order_index=order_index,
                    target_sets=sp.sets,
                    target_reps=rep_range(sp.reps, sp.compound),
                    target_rpe=sp.rpe,
                    rest_seconds=sp.rest_s,
                    progression=progression,
                )
            )

    db.flush()
    return _load_full(db, program.id, user.id)


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------
def today_workout(db: Session, user: User) -> dict:
    """Today's session for the active program, or ``{"rest_day": True}``."""
    program = active_program(db, user.id)
    if program is None or not program.days:
        return {"rest_day": True}

    days = sorted(program.days, key=lambda d: d.day_index)
    schedule = weekly_schedule(len(days))
    weekday = date.today().weekday()
    if weekday not in schedule:
        return {"rest_day": True}

    day = days[schedule[weekday]]
    exercises = []
    for pe in sorted(day.exercises, key=lambda x: x.order_index):
        public = program_exercise_public(pe)
        e1rm = performance.best_recent_e1rm(db, user.id, pe.exercise_id)
        public["suggested_weight"] = performance.suggested_weight(
            e1rm, low_rep(pe.target_reps), pe.target_rpe
        )
        exercises.append(public)

    return {
        "program_day_id": day.id,
        "name": day.name,
        "exercises": exercises,
    }


__all__ = [
    "rep_range",
    "low_rep",
    "weekly_schedule",
    "program_summary",
    "program_detail",
    "program_day_public",
    "program_exercise_public",
    "get_program",
    "list_programs",
    "active_program",
    "activate",
    "generate_program",
    "today_workout",
]
