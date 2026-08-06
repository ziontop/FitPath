"""Curated exercise catalog + idempotent seeder.

``seed_exercises(session)`` inserts the reference catalog below, skipping any
exercise whose ``name`` already exists, so it is safe to run repeatedly (e.g.
on app startup or from a one-off script). Seeded rows are non-custom
(``is_custom=False``, ``owner_user_id=None``); the SBD "big three" plus the
overhead press are flagged ``is_main_lift=True``.

``secondary_muscles`` is stored as a JSON-encoded list of strings to match the
``exercise`` shape in the API contract (``secondary_muscles[]``).

Run directly for a quick local seed::

    python -m app.seed_exercises
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Exercise

# (name, category, primary_muscle, secondary_muscles, equipment, is_main_lift)
_CATALOG: list[tuple[str, str, str, list[str], str, bool]] = [
    # --- SBD main lifts + overhead press -----------------------------------
    ("Back Squat", "compound", "quads", ["glutes", "hamstrings", "core"], "barbell", True),
    ("Bench Press", "compound", "chest", ["triceps", "front_delts"], "barbell", True),
    ("Deadlift", "compound", "back", ["glutes", "hamstrings", "traps", "forearms"], "barbell", True),
    ("Overhead Press", "compound", "shoulders", ["triceps", "upper_chest", "core"], "barbell", True),

    # --- Squat / knee-dominant ---------------------------------------------
    ("Front Squat", "compound", "quads", ["glutes", "core"], "barbell", False),
    ("Hack Squat", "compound", "quads", ["glutes"], "machine", False),
    ("Leg Press", "compound", "quads", ["glutes", "hamstrings"], "machine", False),
    ("Goblet Squat", "compound", "quads", ["glutes", "core"], "dumbbell", False),
    ("Bulgarian Split Squat", "compound", "quads", ["glutes", "hamstrings"], "dumbbell", False),
    ("Walking Lunge", "compound", "quads", ["glutes", "hamstrings"], "dumbbell", False),
    ("Leg Extension", "isolation", "quads", [], "machine", False),

    # --- Hinge / posterior chain -------------------------------------------
    ("Romanian Deadlift", "compound", "hamstrings", ["glutes", "back"], "barbell", False),
    ("Sumo Deadlift", "compound", "glutes", ["hamstrings", "quads", "back"], "barbell", False),
    ("Hip Thrust", "compound", "glutes", ["hamstrings"], "barbell", False),
    ("Good Morning", "compound", "hamstrings", ["glutes", "lower_back"], "barbell", False),
    ("Glute Ham Raise", "compound", "hamstrings", ["glutes", "calves"], "bodyweight", False),
    ("Back Extension", "isolation", "lower_back", ["glutes", "hamstrings"], "bodyweight", False),
    ("Lying Leg Curl", "isolation", "hamstrings", [], "machine", False),
    ("Seated Leg Curl", "isolation", "hamstrings", [], "machine", False),

    # --- Horizontal push (chest) -------------------------------------------
    ("Incline Bench Press", "compound", "upper_chest", ["front_delts", "triceps"], "barbell", False),
    ("Dumbbell Bench Press", "compound", "chest", ["triceps", "front_delts"], "dumbbell", False),
    ("Incline Dumbbell Press", "compound", "upper_chest", ["front_delts", "triceps"], "dumbbell", False),
    ("Push-up", "compound", "chest", ["triceps", "front_delts", "core"], "bodyweight", False),
    ("Dip", "compound", "chest", ["triceps", "front_delts"], "bodyweight", False),
    ("Dumbbell Chest Fly", "isolation", "chest", ["front_delts"], "dumbbell", False),
    ("Cable Crossover", "isolation", "chest", ["front_delts"], "cable", False),

    # --- Vertical push (shoulders) -----------------------------------------
    ("Dumbbell Shoulder Press", "compound", "shoulders", ["triceps", "upper_chest"], "dumbbell", False),
    ("Arnold Press", "compound", "shoulders", ["triceps"], "dumbbell", False),
    ("Lateral Raise", "isolation", "side_delts", [], "dumbbell", False),
    ("Front Raise", "isolation", "front_delts", [], "dumbbell", False),
    ("Rear Delt Fly", "isolation", "rear_delts", [], "dumbbell", False),
    ("Face Pull", "isolation", "rear_delts", ["traps", "rotator_cuff"], "cable", False),
    ("Upright Row", "compound", "side_delts", ["traps", "biceps"], "barbell", False),

    # --- Vertical pull (lats) ----------------------------------------------
    ("Pull-up", "compound", "lats", ["biceps", "upper_back", "forearms"], "bodyweight", False),
    ("Chin-up", "compound", "lats", ["biceps", "upper_back"], "bodyweight", False),
    ("Lat Pulldown", "compound", "lats", ["biceps", "upper_back"], "cable", False),
    ("Straight-Arm Pulldown", "isolation", "lats", [], "cable", False),

    # --- Horizontal pull (rows) --------------------------------------------
    ("Barbell Row", "compound", "upper_back", ["lats", "biceps", "rear_delts"], "barbell", False),
    ("Dumbbell Row", "compound", "upper_back", ["lats", "biceps"], "dumbbell", False),
    ("Seated Cable Row", "compound", "upper_back", ["lats", "biceps"], "cable", False),
    ("T-Bar Row", "compound", "upper_back", ["lats", "biceps"], "barbell", False),
    ("Chest-Supported Row", "compound", "upper_back", ["lats", "rear_delts"], "machine", False),
    ("Barbell Shrug", "isolation", "traps", ["forearms"], "barbell", False),

    # --- Biceps -------------------------------------------------------------
    ("Barbell Curl", "isolation", "biceps", ["forearms"], "barbell", False),
    ("Dumbbell Curl", "isolation", "biceps", ["forearms"], "dumbbell", False),
    ("Hammer Curl", "isolation", "biceps", ["brachialis", "forearms"], "dumbbell", False),
    ("Preacher Curl", "isolation", "biceps", [], "ez_bar", False),
    ("Cable Curl", "isolation", "biceps", [], "cable", False),

    # --- Triceps ------------------------------------------------------------
    ("Close-Grip Bench Press", "compound", "triceps", ["chest", "front_delts"], "barbell", False),
    ("Triceps Pushdown", "isolation", "triceps", [], "cable", False),
    ("Overhead Triceps Extension", "isolation", "triceps", [], "dumbbell", False),
    ("Skull Crusher", "isolation", "triceps", [], "ez_bar", False),
    ("Bench Dip", "compound", "triceps", ["chest"], "bodyweight", False),

    # --- Calves -------------------------------------------------------------
    ("Standing Calf Raise", "isolation", "calves", [], "machine", False),
    ("Seated Calf Raise", "isolation", "calves", [], "machine", False),

    # --- Core ---------------------------------------------------------------
    ("Plank", "isolation", "core", [], "bodyweight", False),
    ("Hanging Leg Raise", "isolation", "core", ["hip_flexors"], "bodyweight", False),
    ("Cable Crunch", "isolation", "core", [], "cable", False),
    ("Ab Wheel Rollout", "compound", "core", ["lats"], "bodyweight", False),
    ("Russian Twist", "isolation", "obliques", ["core"], "bodyweight", False),
]


def seed_exercises(session: Session) -> int:
    """Insert catalog exercises that don't already exist. Returns count added.

    Idempotent: existing exercises (matched by ``name``) are skipped, so this
    can be run on every startup. Commits only when new rows were added.
    """
    existing = set(session.scalars(select(Exercise.name)).all())
    added = 0
    for name, category, primary_muscle, secondary, equipment, is_main_lift in _CATALOG:
        if name in existing:
            continue
        session.add(
            Exercise(
                name=name,
                category=category,
                primary_muscle=primary_muscle,
                secondary_muscles=json.dumps(secondary),
                equipment=equipment,
                is_main_lift=is_main_lift,
                is_custom=False,
                owner_user_id=None,
            )
        )
        added += 1
    if added:
        session.commit()
    return added


def main() -> None:
    """Convenience entrypoint: ensure tables exist (dev) then seed."""
    from .db import SessionLocal, init_db

    init_db()
    with SessionLocal() as session:
        added = seed_exercises(session)
    print(f"seeded {added} new exercises ({len(_CATALOG)} in catalog)")


if __name__ == "__main__":
    main()
