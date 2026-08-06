"""Concrete, code-ready strength & physique training parameters for FitPath.

This module encodes modern, evidence-based training and nutrition parameters as
typed constants, dataclasses and pure functions so the **algorithmic (non-LLM)**
recommendation engine can derive every recommendation deterministically. There
are NO side effects, NO I/O and NO third-party dependencies here (stdlib only:
``dataclasses``, ``enum``) so it is always import-safe.

Every number carries a citation tag in its docstring/comment; the full source
list with URLs lives in ``docs/TRAINING-SCIENCE.md``. Key tags:

* [RP-VOL]   Renaissance Periodization volume landmarks (MV/MEV/MAV/MRV).
             https://rpstrength.com/blogs/articles/training-volume-landmarks-muscle-growth
* [RP-MUSCLE] RP / Israetel per-muscle volume guides.
* [SBS-RIR]  Stronger By Science, RPE/RIR autoregulation.
             https://www.strongerbyscience.com/reps-in-reserve/
* [SCH-FREQ] Schoenfeld/Ogborn/Krieger 2016, frequency meta-analysis.
             https://pubmed.ncbi.nlm.nih.gov/27102172/
* [SCH-REST] Schoenfeld et al. 2016, longer rest > short rest.
             https://pubmed.ncbi.nlm.nih.gov/26605807/
* [MORTON]   Morton et al. 2018, protein ~1.6 g/kg. https://pubmed.ncbi.nlm.nih.gov/28698222/
* [ISSN]     Jager et al. 2017 ISSN protein stand, 1.4-2.0 g/kg.
* [HELMS]    Helms et al. 2014, cut protein 2.3-3.1 g/kg LBM, fat floor ~0.5-0.6 g/kg.
* [531]      Wendler 5/3/1 (Training Max = 90% 1RM). https://thefitness.wiki/5-3-1-primer/
* [RFIT-BBR] r/Fitness Basic Beginner Routine (linear progression rules).
* [EPLEY]/[BRZYCKI] e1RM formulas.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ===========================================================================
# Enums
# ===========================================================================


class Goal(str, Enum):
    """The three FitPath personas / training + nutrition goals."""

    CUT_POWERLIFTING = "cut_powerlifting"          # lose fat, preserve SBD strength
    BULK_HYPERTROPHY = "bulk_hypertrophy"          # gain muscle in a surplus
    MAINGAIN_INCONSISTENT = "maingain_inconsistent"  # maintenance, minimalist, resilient


class ExperienceLevel(str, Enum):
    """Training age. Governs progression scheme and how much volume/periodization matters."""

    BEGINNER = "beginner"          # <~1 yr consistent lifting; linear progression works
    INTERMEDIATE = "intermediate"  # ~1-3 yr; volume landmarks + weekly progression matter
    ADVANCED = "advanced"          # 3+ yr; block periodization + autoregulation


class Muscle(str, Enum):
    """Major trainable muscle groups for weekly volume accounting."""

    CHEST = "chest"
    BACK = "back"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    CALVES = "calves"
    ABS = "abs"


class ProgressionScheme(str, Enum):
    """Load/volume progression strategies, matched to experience level."""

    LINEAR = "linear"              # add fixed load each session [RFIT-BBR]
    DOUBLE = "double"              # add reps to top of range, then add load
    RPE_AUTOREG = "rpe_autoreg"    # pick load for target reps @ target RPE [SBS-RIR]
    PERIODIZED_531 = "periodized_531"  # Wendler waves off a Training Max [531]
    BLOCK = "block"                # accumulation -> intensification -> peak


# Nutrition energy density (1 g -> kcal). Matches app/ml/coach.py convention.
KCAL_PER_G: dict[str, int] = {"protein": 4, "carbs": 4, "fat": 9}


# ===========================================================================
# Estimated 1RM (e1RM) — pure functions
# ===========================================================================
# Given a set of `weight` for `reps`, estimate a one-rep max, and invert to get
# target loads. Estimates diverge past ~10 reps, so callers should prefer sets
# of <=10 reps. [EPLEY][BRZYCKI]

_EPLEY_K = 0.0333  # Epley coefficient: 1RM = w * (1 + 0.0333 * reps)


def epley_1rm(weight: float, reps: int) -> float:
    """Epley estimated 1RM: ``w * (1 + 0.0333 * r)`` (== ``w * (1 + r/30)``). [EPLEY]"""
    if reps <= 1:
        return float(weight)
    return weight * (1.0 + _EPLEY_K * reps)


def brzycki_1rm(weight: float, reps: int) -> float:
    """Brzycki estimated 1RM: ``w * 36 / (37 - r)``. Valid for r < 37. [BRZYCKI]"""
    if reps <= 1:
        return float(weight)
    reps = min(reps, 36)  # guard the 37 - r denominator
    return weight * 36.0 / (37.0 - reps)


def estimated_1rm(weight: float, reps: int) -> float:
    """Best-estimate 1RM = mean(Epley, Brzycki). Use only for reps <= ~10."""
    if reps <= 1:
        return float(weight)
    return (epley_1rm(weight, reps) + brzycki_1rm(weight, reps)) / 2.0


def epley_percent_1rm(reps: int) -> float:
    """Fraction of 1RM expected to allow ``reps`` (inverse Epley). e.g. 5 -> ~0.857."""
    if reps <= 1:
        return 1.0
    return 1.0 / (1.0 + _EPLEY_K * reps)


def load_for_reps(one_rm: float, reps: int) -> float:
    """Target working load to hit ``reps`` given a known/estimated 1RM (inverse Epley)."""
    return one_rm * epley_percent_1rm(reps)


def rpe_to_rir(rpe: float) -> float:
    """Reps in reserve implied by an RPE value: ``RIR = 10 - RPE``. [SBS-RIR]"""
    return max(0.0, 10.0 - rpe)


def rir_to_rpe(rir: float) -> float:
    """RPE implied by reps in reserve: ``RPE = 10 - RIR``. [SBS-RIR]"""
    return max(0.0, 10.0 - rir)


# ===========================================================================
# Weekly volume landmarks per muscle (sets / muscle / week) [RP-VOL][RP-MUSCLE]
# ===========================================================================
# A "working set" = 30-85% 1RM, 5-30 reps, 0-4 RIR. Only direct/prime-mover sets
# are counted (indirect volume is already factored in). Landmarks are starting
# points; beginners sit near MEV, intermediates progress MEV -> MRV per block. [RP-VOL]


@dataclass(frozen=True)
class VolumeLandmark:
    """MV/MEV/MAV/MRV weekly set landmarks for one muscle group. [RP-VOL]"""

    mv: int        # Maintenance Volume (holds size; ~deload target)
    mev: int       # Minimum Effective Volume (start of a growth block)
    mav_low: int   # Maximum Adaptive Volume, low end of the productive range
    mav_high: int  # Maximum Adaptive Volume, high end
    mrv: int       # Maximum Recoverable Volume (upper cap)


# Consolidated from RP / Israetel muscle-specific guides. [RP-MUSCLE]
VOLUME_LANDMARKS: dict[Muscle, VolumeLandmark] = {
    Muscle.CHEST:      VolumeLandmark(mv=6, mev=8,  mav_low=12, mav_high=20, mrv=22),
    Muscle.BACK:       VolumeLandmark(mv=6, mev=10, mav_low=14, mav_high=22, mrv=25),
    Muscle.QUADS:      VolumeLandmark(mv=6, mev=8,  mav_low=12, mav_high=18, mrv=20),
    Muscle.HAMSTRINGS: VolumeLandmark(mv=4, mev=6,  mav_low=10, mav_high=16, mrv=20),
    Muscle.GLUTES:     VolumeLandmark(mv=0, mev=4,  mav_low=8,  mav_high=12, mrv=16),
    Muscle.SHOULDERS:  VolumeLandmark(mv=6, mev=8,  mav_low=16, mav_high=22, mrv=26),
    Muscle.BICEPS:     VolumeLandmark(mv=5, mev=8,  mav_low=14, mav_high=20, mrv=26),
    Muscle.TRICEPS:    VolumeLandmark(mv=4, mev=6,  mav_low=10, mav_high=14, mrv=18),
    Muscle.CALVES:     VolumeLandmark(mv=6, mev=8,  mav_low=12, mav_high=16, mrv=20),
    Muscle.ABS:        VolumeLandmark(mv=0, mev=0,  mav_low=16, mav_high=20, mrv=25),
}


# ===========================================================================
# Per-goal training prescription (rep range, intensity, rest, frequency) [SBS-RIR][SCH-*]
# ===========================================================================


class VolumeBias(str, Enum):
    """How the goal maps onto the volume landmarks."""

    HOLD_MV_MEV = "hold_mv_mev"      # cut: enough to maintain, not grow (MV..MEV)
    PROGRESS_MEV_MRV = "progress_mev_mrv"  # bulk: start MEV, climb to MRV
    MAINTAIN_MV = "maintain_mv"      # maingain: minimalist, ~MV


@dataclass(frozen=True)
class GoalPrescription:
    """Rep/intensity/rest/frequency prescription for a goal. [SBS-RIR][SCH-FREQ][SCH-REST]"""

    # Primary compound (SBD) work
    main_rep_min: int
    main_rep_max: int
    main_pct_1rm_low: float   # fraction of 1RM
    main_pct_1rm_high: float
    main_rpe_low: float
    main_rpe_high: float
    # Accessory / isolation work
    accessory_rep_min: int
    accessory_rep_max: int
    accessory_rpe_low: float
    accessory_rpe_high: float
    # Rest (seconds) — longer rest favors strength & hypertrophy on compounds [SCH-REST]
    compound_rest_s: int
    isolation_rest_s: int
    # Frequency [SCH-FREQ]
    sessions_per_week_low: int
    sessions_per_week_high: int
    muscle_freq_per_week: int
    # Volume handling against the landmarks
    volume_bias: VolumeBias


GOAL_TRAINING: dict[Goal, GoalPrescription] = {
    # Cutting powerlifter: keep SBD intensity high, low reps, minimal accessory
    # volume so fatigue stays recoverable in a deficit. [SBS-RIR][SCH-REST][RP-VOL]
    Goal.CUT_POWERLIFTING: GoalPrescription(
        main_rep_min=1, main_rep_max=5,
        main_pct_1rm_low=0.80, main_pct_1rm_high=0.92,
        main_rpe_low=7.0, main_rpe_high=9.0,
        accessory_rep_min=6, accessory_rep_max=12,
        accessory_rpe_low=7.0, accessory_rpe_high=9.0,
        compound_rest_s=240, isolation_rest_s=90,
        sessions_per_week_low=3, sessions_per_week_high=4,
        muscle_freq_per_week=2,
        volume_bias=VolumeBias.HOLD_MV_MEV,
    ),
    # Hypertrophy bulk: moderate reps near failure, accumulate volume toward MRV,
    # SBD as the strength anchor, 2x/muscle frequency. [SBS-RIR][SCH-FREQ][RP-VOL]
    Goal.BULK_HYPERTROPHY: GoalPrescription(
        main_rep_min=6, main_rep_max=10,
        main_pct_1rm_low=0.65, main_pct_1rm_high=0.80,
        main_rpe_low=7.0, main_rpe_high=9.0,
        accessory_rep_min=10, accessory_rep_max=15,
        accessory_rpe_low=8.0, accessory_rpe_high=10.0,
        compound_rest_s=180, isolation_rest_s=75,
        sessions_per_week_low=4, sessions_per_week_high=6,
        muscle_freq_per_week=2,
        volume_bias=VolumeBias.PROGRESS_MEV_MRV,
    ),
    # Maingaining + inconsistent: minimalist full-body, autoregulated, resilient
    # to missed sessions; volume ~MV to preserve without heavy fatigue. [RP-VOL]
    Goal.MAINGAIN_INCONSISTENT: GoalPrescription(
        main_rep_min=4, main_rep_max=6,
        main_pct_1rm_low=0.75, main_pct_1rm_high=0.85,
        main_rpe_low=7.0, main_rpe_high=8.0,
        accessory_rep_min=8, accessory_rep_max=12,
        accessory_rpe_low=8.0, accessory_rpe_high=9.0,
        compound_rest_s=180, isolation_rest_s=75,
        sessions_per_week_low=2, sessions_per_week_high=3,
        muscle_freq_per_week=2,
        volume_bias=VolumeBias.MAINTAIN_MV,
    ),
}


def weekly_set_target(goal: Goal, muscle: Muscle) -> tuple[int, int]:
    """Recommended weekly (low, high) working-set band for a muscle under a goal.

    Clamped to the muscle's landmarks per the goal's volume bias:
    cut -> [MV, MEV], bulk -> [MEV, MRV], maingain -> [MV, MEV]. [RP-VOL]
    """
    lm = VOLUME_LANDMARKS[muscle]
    bias = GOAL_TRAINING[goal].volume_bias
    if bias is VolumeBias.PROGRESS_MEV_MRV:
        return (lm.mev, lm.mrv)
    if bias is VolumeBias.MAINTAIN_MV:
        return (lm.mv, lm.mev)
    return (lm.mv, lm.mev)  # HOLD_MV_MEV (cut)


# ===========================================================================
# Progression schemes & deload rules [RFIT-BBR][SBS-RIR][531][RP-VOL]
# ===========================================================================

# Beginners run linear progression; intermediates autoregulate/double-progress;
# advanced lifters use block periodization. [RFIT-BBR][SBS-RIR]
EXPERIENCE_PROGRESSION: dict[ExperienceLevel, ProgressionScheme] = {
    ExperienceLevel.BEGINNER: ProgressionScheme.LINEAR,
    ExperienceLevel.INTERMEDIATE: ProgressionScheme.RPE_AUTOREG,
    ExperienceLevel.ADVANCED: ProgressionScheme.BLOCK,
}

# Linear progression per-session load increments. [RFIT-BBR]
LINEAR_INCREMENT_KG: dict[str, float] = {
    "upper": 1.25,  # +2.5 lb on upper-body lifts (bench, OHP, row)
    "lower": 2.5,   # +5 lb on lower-body lifts (squat, deadlift)
}
# Fail the rep target -> repeat; fail repeatedly -> deload to this fraction. [RFIT-BBR]
LINEAR_DELOAD_FRACTION = 0.90  # -10%
LINEAR_STALL_SESSIONS = 3      # consecutive failed sessions that trigger a deload

# Weekly mesocycle volume progression (intermediate+): add sets/muscle/week from
# MEV toward MRV, then deload. [RP-VOL]
WEEKLY_SET_INCREMENT = (1, 3)          # add 1-3 sets/muscle/week based on recovery
MESOCYCLE_WEEKS_BEFORE_DELOAD = (4, 6)  # accumulate ~4-6 weeks, then deload

# Deload prescription: drop to ~MV and/or cut load. [RP-VOL]
DELOAD_LOAD_FRACTION = 0.90     # ~-10% load
DELOAD_VOLUME_FRACTION = 0.50   # ~-50% sets (toward MV)


@dataclass(frozen=True)
class DeloadTriggers:
    """Signals that should trigger a deload week. [RP-VOL]"""

    failed_sessions_in_a_row: int = 2       # can't complete prescribed work twice
    cannot_match_prior_week: bool = True    # RP MRV signal: performance regressed
    planned_every_n_weeks: tuple[int, int] = (4, 8)  # scheduled cadence
    persistent_joint_pain_or_soreness: bool = True


DELOAD_TRIGGERS = DeloadTriggers()

# 5/3/1 (Wendler) constants for periodized powerlifting blocks. [531]
FIVE_THREE_ONE = {
    "training_max_fraction": 0.90,  # TM = 90% of true 1RM; all % are off the TM
    # week -> list of (percent_of_TM, target_reps, is_amrap)
    "weeks": {
        1: [(0.65, 5, False), (0.75, 5, False), (0.85, 5, True)],
        2: [(0.70, 3, False), (0.80, 3, False), (0.90, 3, True)],
        3: [(0.75, 5, False), (0.85, 3, False), (0.95, 1, True)],
        4: [(0.40, 5, False), (0.50, 5, False), (0.60, 5, False)],  # deload
    },
    "tm_increment_kg": {"upper": 2.5, "lower": 5.0},  # +5 lb upper / +10 lb lower per cycle
}


# ===========================================================================
# Nutrition targets per goal [MORTON][ISSN][HELMS][RATE]
# ===========================================================================


@dataclass(frozen=True)
class NutritionTargets:
    """Per-goal energy and macro targets. Grams are per kg of BODYWEIGHT. [MORTON][HELMS]"""

    kcal_delta_per_day: float          # applied on top of TDEE
    bodyweight_pct_per_week_low: float  # target rate of weight change (%BW/wk)
    bodyweight_pct_per_week_high: float
    protein_g_per_kg: float            # protein target
    fat_g_per_kg_floor: float          # do not go below this fat intake [HELMS]
    fat_g_per_kg_target: float         # default fat target
    carb_note: str                     # carbs fill remaining kcal


NUTRITION: dict[Goal, NutritionTargets] = {
    # Cut: ~-500 kcal/day, 0.5-1.0 %BW/wk loss. Protein high to spare muscle
    # (~2.4 g/kg BW, from Helms 2.3-3.1 g/kg LBM). Fat floor 0.6 g/kg. [HELMS][RATE]
    Goal.CUT_POWERLIFTING: NutritionTargets(
        kcal_delta_per_day=-500.0,
        bodyweight_pct_per_week_low=-1.0, bodyweight_pct_per_week_high=-0.5,
        protein_g_per_kg=2.4,
        fat_g_per_kg_floor=0.6, fat_g_per_kg_target=0.8,
        carb_note="Fill remaining kcal with carbs; prioritize peri-workout for SBD output.",
    ),
    # Lean bulk: +250-500 kcal/day, +0.25-0.5 %BW/wk. Protein ~2.0 g/kg. [MORTON][ISSN][RATE]
    Goal.BULK_HYPERTROPHY: NutritionTargets(
        kcal_delta_per_day=350.0,
        bodyweight_pct_per_week_low=0.25, bodyweight_pct_per_week_high=0.5,
        protein_g_per_kg=2.0,
        fat_g_per_kg_floor=0.6, fat_g_per_kg_target=1.0,
        carb_note="Fill remaining (large) kcal with carbs to fuel high training volume.",
    ),
    # Maintain: ~0 delta, protein ~1.6 g/kg (Morton optimum). [MORTON]
    Goal.MAINGAIN_INCONSISTENT: NutritionTargets(
        kcal_delta_per_day=0.0,
        bodyweight_pct_per_week_low=-0.1, bodyweight_pct_per_week_high=0.1,
        protein_g_per_kg=1.6,
        fat_g_per_kg_floor=0.6, fat_g_per_kg_target=1.0,
        carb_note="Fill remaining kcal with carbs; adjust ±100-200 kcal to hold weight.",
    ),
}

# Refeeds / diet breaks apply to the cut only. [RATE][RP-DIET]
REFEED_DAYS_PER_WEEK = (1, 2)              # carb-driven days back at ~maintenance
DIET_BREAK_WEEKS = (1, 2)                  # at maintenance
DIET_BREAK_AFTER_WEEKS_DIETING = (8, 12)   # scheduled cadence, or sooner if fatigued


def macro_targets(
    daily_kcal: float,
    bodyweight_kg: float,
    goal: Goal,
) -> dict[str, float]:
    """Derive protein/fat/carb grams for a daily kcal target and bodyweight.

    Protein and fat are set from per-kg constants (fat clamped at its floor),
    then carbohydrate fills the remaining calories. [MORTON][HELMS]
    Returns a dict of grams; carbs are floored at 0 for very low kcal targets.
    """
    t = NUTRITION[goal]
    protein_g = t.protein_g_per_kg * bodyweight_kg
    fat_g = max(t.fat_g_per_kg_floor, t.fat_g_per_kg_target) * bodyweight_kg
    kcal_from_pf = protein_g * KCAL_PER_G["protein"] + fat_g * KCAL_PER_G["fat"]
    carb_g = max(0.0, (daily_kcal - kcal_from_pf) / KCAL_PER_G["carbs"])
    return {
        "protein_g": round(protein_g, 1),
        "fat_g": round(fat_g, 1),
        "carbs_g": round(carb_g, 1),
    }


# ===========================================================================
# Weekly program templates (SBD-based) for the 3 personas
# ===========================================================================
# day -> ordered list of SetPrescription. Loads are picked at runtime via
# RPE + e1RM; here we fix sets/target-reps/RPE/rest. See docs/TRAINING-SCIENCE.md §9.


@dataclass(frozen=True)
class SetPrescription:
    """One exercise slot in a training day: sets x reps @ RPE, with rest seconds."""

    exercise: str
    sets: int
    reps: int
    rpe: float
    rest_s: int
    compound: bool = False


PROGRAM_TEMPLATES: dict[Goal, dict[str, tuple[SetPrescription, ...]]] = {
    # -- CUTTING + POWERLIFTING: 4-day Upper/Lower, heavy SBD, minimal accessories --
    Goal.CUT_POWERLIFTING: {
        "Lower (Squat focus)": (
            SetPrescription("Back Squat", 4, 4, 8.0, 240, compound=True),
            SetPrescription("Romanian Deadlift", 3, 6, 7.0, 180, compound=True),
            SetPrescription("Leg Press", 2, 10, 8.0, 120, compound=True),
            SetPrescription("Hanging Leg Raise", 3, 12, 9.0, 90),
        ),
        "Upper (Bench focus)": (
            SetPrescription("Bench Press", 4, 4, 8.0, 240, compound=True),
            SetPrescription("Overhead Press", 3, 6, 7.0, 180, compound=True),
            SetPrescription("Barbell Row", 3, 6, 8.0, 150, compound=True),
            SetPrescription("Lat Pulldown", 2, 12, 8.0, 90, compound=True),
            SetPrescription("Triceps Pushdown", 2, 12, 9.0, 75),
        ),
        "Lower (Deadlift focus)": (
            SetPrescription("Deadlift", 3, 3, 8.0, 300, compound=True),
            SetPrescription("Front Squat", 3, 5, 7.0, 180, compound=True),
            SetPrescription("Lying Leg Curl", 3, 10, 9.0, 90),
            SetPrescription("Standing Calf Raise", 3, 12, 9.0, 75),
        ),
        "Upper (Bench volume / back)": (
            SetPrescription("Close-Grip Bench Press", 4, 5, 8.0, 180, compound=True),
            SetPrescription("Weighted Pull-Up", 3, 6, 8.0, 150, compound=True),
            SetPrescription("Incline DB Press", 3, 10, 8.0, 120, compound=True),
            SetPrescription("Lateral Raise", 3, 15, 9.0, 60),
            SetPrescription("Barbell Curl", 2, 12, 9.0, 75),
        ),
    },
    # -- BULKING + HYPERTROPHY: 6-day Push/Pull/Legs, SBD anchors, MAV volume --
    Goal.BULK_HYPERTROPHY: {
        "Push A": (
            SetPrescription("Bench Press", 4, 6, 8.0, 180, compound=True),
            SetPrescription("Overhead Press", 3, 8, 8.0, 150, compound=True),
            SetPrescription("Incline DB Press", 3, 10, 9.0, 120, compound=True),
            SetPrescription("Lateral Raise", 4, 15, 9.0, 60),
            SetPrescription("Triceps Pushdown", 3, 12, 9.0, 75),
        ),
        "Pull A": (
            SetPrescription("Deadlift", 3, 5, 8.0, 240, compound=True),
            SetPrescription("Barbell Row", 4, 8, 8.0, 150, compound=True),
            SetPrescription("Lat Pulldown", 3, 12, 9.0, 90, compound=True),
            SetPrescription("Face Pull", 3, 15, 9.0, 60),
            SetPrescription("Barbell Curl", 3, 10, 9.0, 75),
        ),
        "Legs A": (
            SetPrescription("Back Squat", 4, 6, 8.0, 240, compound=True),
            SetPrescription("Romanian Deadlift", 3, 8, 8.0, 180, compound=True),
            SetPrescription("Leg Press", 3, 12, 9.0, 120, compound=True),
            SetPrescription("Lying Leg Curl", 3, 12, 9.0, 90),
            SetPrescription("Standing Calf Raise", 4, 12, 9.0, 75),
        ),
        "Push B": (
            SetPrescription("Incline Bench Press", 4, 8, 8.0, 180, compound=True),
            SetPrescription("Seated DB Press", 3, 10, 9.0, 120, compound=True),
            SetPrescription("Cable Fly", 3, 15, 9.0, 75),
            SetPrescription("Lateral Raise", 4, 15, 9.0, 60),
            SetPrescription("Overhead Triceps Extension", 3, 12, 9.0, 75),
        ),
        "Pull B": (
            SetPrescription("Pull-Up", 4, 8, 9.0, 150, compound=True),
            SetPrescription("Chest-Supported Row", 4, 10, 9.0, 120, compound=True),
            SetPrescription("Rear-Delt Fly", 3, 15, 9.0, 60),
            SetPrescription("Barbell Shrug", 3, 12, 9.0, 90),
            SetPrescription("Incline DB Curl", 3, 12, 9.0, 75),
        ),
        "Legs B": (
            SetPrescription("Front Squat", 4, 8, 8.0, 210, compound=True),
            SetPrescription("Hip Thrust", 3, 10, 9.0, 150, compound=True),
            SetPrescription("Leg Extension", 3, 15, 9.0, 90),
            SetPrescription("Seated Leg Curl", 3, 12, 9.0, 90),
            SetPrescription("Seated Calf Raise", 4, 15, 9.0, 60),
        ),
    },
    # -- MAINGAINING + INCONSISTENT: 2-3 day Full-Body A/B, minimalist, resilient --
    Goal.MAINGAIN_INCONSISTENT: {
        "Full-Body A": (
            SetPrescription("Back Squat", 3, 5, 8.0, 180, compound=True),
            SetPrescription("Bench Press", 3, 5, 8.0, 180, compound=True),
            SetPrescription("Barbell Row", 3, 8, 8.0, 120, compound=True),
            SetPrescription("Barbell Curl", 2, 12, 9.0, 75),  # optional accessory
        ),
        "Full-Body B": (
            SetPrescription("Deadlift", 2, 5, 8.0, 240, compound=True),
            SetPrescription("Overhead Press", 3, 5, 8.0, 150, compound=True),
            SetPrescription("Lat Pulldown", 3, 10, 9.0, 90, compound=True),
            SetPrescription("Triceps Pushdown", 2, 12, 9.0, 75),  # optional accessory
        ),
    },
}


__all__ = [
    "Goal",
    "ExperienceLevel",
    "Muscle",
    "ProgressionScheme",
    "VolumeBias",
    "KCAL_PER_G",
    "epley_1rm",
    "brzycki_1rm",
    "estimated_1rm",
    "epley_percent_1rm",
    "load_for_reps",
    "rpe_to_rir",
    "rir_to_rpe",
    "VolumeLandmark",
    "VOLUME_LANDMARKS",
    "GoalPrescription",
    "GOAL_TRAINING",
    "weekly_set_target",
    "EXPERIENCE_PROGRESSION",
    "LINEAR_INCREMENT_KG",
    "LINEAR_DELOAD_FRACTION",
    "LINEAR_STALL_SESSIONS",
    "WEEKLY_SET_INCREMENT",
    "MESOCYCLE_WEEKS_BEFORE_DELOAD",
    "DELOAD_LOAD_FRACTION",
    "DELOAD_VOLUME_FRACTION",
    "DeloadTriggers",
    "DELOAD_TRIGGERS",
    "FIVE_THREE_ONE",
    "NutritionTargets",
    "NUTRITION",
    "REFEED_DAYS_PER_WEEK",
    "DIET_BREAK_WEEKS",
    "DIET_BREAK_AFTER_WEEKS_DIETING",
    "macro_targets",
    "SetPrescription",
    "PROGRAM_TEMPLATES",
]
