"""Deterministic, privacy-preserving adaptive-recommendation engine (pure core).

This module is the **I/O-free** heart of the history-adaptive recommender
described in ``docs/ADAPTIVE-RECOMMENDATIONS.md``. Like :mod:`app.ml.coach` it
holds no database or network access — the :mod:`app.services.adaptive`
orchestration layer reads the authenticated user's own rows, hands plain
values/dataclasses in, and serializes the results out.

Everything here is a published, testable formula: same inputs ⇒ same output.
There is no randomness; every tie-break or cross-day rotation is seeded by a
stable key (``user_id`` + ISO date + normalized name) so it is reproducible.

Two engines live here:

* **Meals** — :func:`score_food` ranks a user's own logged foods by a transparent
  weighted score (macro-fit, adherent-day usefulness, recency, frequency,
  category/time fit, favorite), :func:`portion_factor` scales the serving to the
  remaining budget, and :func:`diversify` (Maximal Marginal Relevance) keeps the
  returned set varied.
* **Workouts** — :func:`decide_progression` applies double progression gated by
  RPE (increase / hold / reduce / deload) with layoff-safe resumption, reusing
  the researched constants in :mod:`app.training.params`.

Constants (§8 of the design doc) are collected in one block with citations.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Optional

from ..training.params import (
    DELOAD_LOAD_FRACTION,
    LINEAR_INCREMENT_KG,
)

# ===========================================================================
# §8 — Constants & tunables (single source, with citations)
# ===========================================================================
#: Audit ids stamped on every response so behavior is attributable to a rule set.
RECOMMENDATION_VERSION = "adaptive-v1"
RECOMMENDATION_ALGORITHM = "history-adaptive-deterministic"

# --- meal engine ---------------------------------------------------------
MEAL_WINDOW_DAYS = 30          # food history window (matches nutrition._fetch_history_meals)
RECENCY_HALF_LIFE_DAYS = 14    # recency decay half-life
FREQ_SMOOTHING = 3             # frequency smoothing K: n/(n+K)
KCAL_FIT_FLOOR = 0.6           # min macro-fit multiplier for serving-size mismatch
TIME_FIT_WINDOW_MIN = 90       # ± minutes for the "right slot" time-fit bonus

# Composite meal weights (W_M + W_A + W_R + W_F + W_T == 1.00; favorite additive).
W_M = 0.35   # macro-fit to today's remaining gap
W_A = 0.20   # adherent-day contribution (foods from on-target days)
W_R = 0.15   # recency
W_F = 0.15   # frequency
W_T = 0.15   # category / time fit
W_FAV = 0.05  # favorite bump (additive, outside the normalized budget)

KCAL_LOW = 0.90            # adherent-day kcal band (lower)
KCAL_HIGH = 1.10           # adherent-day kcal band (upper)
PROTEIN_MIN = 0.90         # adherent-day protein floor [MORTON]
MIN_DAYS_FOR_ADHERENCE = 5  # observed days before adherence is trusted

PORTION_MIN = 0.5          # serving-scaling clamp (lower)
PORTION_MAX = 2.0          # serving-scaling clamp (upper)
PORTION_STEP = 0.25        # serving-scaling granularity

MMR_LAMBDA = 0.5           # diversity penalty [Carbonell & Goldstein MMR]
TIE_EPSILON = 0.02         # score-tie band for deterministic rotation
NEAR_DUPLICATE_JACCARD = 0.6  # drop names this similar to an already-picked food
CATEGORY_CAP = 2           # ≤ 2 per category among returned picks (when ≥3 categories)

MEAL_HIGH_CONF_DAYS = 14   # high-confidence thresholds
MEAL_HIGH_CONF_FOODS = 8
MEAL_MED_CONF_DAYS = 5     # medium-confidence thresholds
MEAL_MED_CONF_FOODS = 3

# --- workout engine ------------------------------------------------------
WORKOUT_LOOKBACK_SESSIONS = 5    # recent sessions read per exercise
STALL_SESSIONS_FOR_DELOAD = 3    # consecutive stalls → deload [RFIT-BBR]
E1RM_REGRESS_PCT = 0.05          # e1RM drop that signals regression → deload [RP-VOL]
HIGH_RPE_MARGIN = 1.5            # RPE this far over target = fatigue [SBS-RIR]
EASY_RPE_MARGIN = 2.0            # ≥2 RIR beyond target → double jump [SBS-RIR]
LAYOFF_DAYS = 14                 # gap beyond this → resume-safe (lighter)
LAYOFF_LOAD_FRACTION = 0.93      # return-from-layoff load cut (≈ −7%)
WORKOUT_HIGH_CONF_SESSIONS = 4   # high-confidence session count
WORKOUT_MED_CONF_SESSIONS = 2    # medium-confidence session count

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
_LOWER_MUSCLE_GROUPS = {"quads", "hamstrings", "glutes", "calves"}
_TOKEN_STOPWORDS = {"and", "with", "the", "a", "of", "in", "&"}


# ===========================================================================
# Small pure helpers
# ===========================================================================
def norm(name: str) -> str:
    """Normalize a food name: lowercase, trim, collapse internal whitespace."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def tokens(name: str) -> frozenset[str]:
    """Content tokens of a name (lowercased words, punctuation & stopwords dropped)."""
    words = re.split(r"[^a-z0-9]+", (name or "").lower())
    return frozenset(w for w in words if w and w not in _TOKEN_STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two token sets (0 when both empty)."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cosine(u: tuple[float, ...], v: tuple[float, ...]) -> float:
    """Cosine similarity of two equal-length vectors; 0 if either has zero norm.

    For non-negative inputs (macros/gaps) the result is in ``[0, 1]``.
    """
    dot = sum(a * b for a, b in zip(u, v))
    nu = math.sqrt(sum(a * a for a in u))
    nv = math.sqrt(sum(b * b for b in v))
    if nu <= 0.0 or nv <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (nu * nv)))


def stable_hash(key: str) -> int:
    """Deterministic, process-independent hash of ``key`` (SHA-256 → int).

    Python's builtin ``hash`` is salted per process; this is reproducible across
    runs so cross-day rotation (§4.6) is testable by freezing the date.
    """
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)


def rotation_rank(user_id: int, today: date, norm_name: str) -> int:
    """Stable per-day rotation key for breaking score ties among equal foods."""
    return stable_hash(f"{user_id}:{today.isoformat()}:{norm_name}")


def round_to(value: float, step: float) -> float:
    """Round ``value`` to the nearest multiple of ``step`` (``step<=0`` → unchanged)."""
    if step <= 0:
        return value
    return round(value / step) * step


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def portion_factor(base_kcal: float, budget: float) -> float:
    """Serving multiplier sizing a food to the per-meal kcal ``budget`` (§4.4).

    ``clamp(round_to(budget / base_kcal, 0.25), PORTION_MIN, PORTION_MAX)``;
    defaults to ``1.0`` when either input is non-positive.
    """
    if base_kcal <= 0 or budget <= 0:
        return 1.0
    return clamp(round_to(budget / base_kcal, PORTION_STEP), PORTION_MIN, PORTION_MAX)


# ===========================================================================
# Meal scoring (§4.2)
# ===========================================================================
@dataclass(frozen=True)
class MealCandidate:
    """An aggregated food from the user's history (median macros over its rows)."""

    name: str
    category: str
    base_kcal: float
    base_protein: float
    base_carbs: float
    base_fat: float
    logged_count: int
    last_eaten_date: date
    favorite: bool
    eaten_days: frozenset[date] = field(default_factory=frozenset)
    eaten_hours: tuple[int, ...] = ()


@dataclass(frozen=True)
class MealContext:
    """Per-request scoring context shared by every candidate."""

    gap_protein: float
    gap_carbs: float
    gap_fat: float
    budget_kcal: float
    predicted_category: str
    now_minutes: int
    today: date
    adherent_days: frozenset[date] = field(default_factory=frozenset)
    adherence_reliable: bool = False


def macro_fit(cand: MealCandidate, ctx: MealContext) -> float:
    """Component (1): cosine similarity to the remaining gap, kcal-tempered (§4.2)."""
    f = (cand.base_protein, cand.base_carbs, cand.base_fat)
    g = (ctx.gap_protein, ctx.gap_carbs, ctx.gap_fat)
    cos_fg = cosine(f, g)
    serving = cand.base_kcal
    if serving > 0 and ctx.budget_kcal > 0:
        kcal_fit = min(serving, ctx.budget_kcal) / max(serving, ctx.budget_kcal)
    else:
        kcal_fit = 0.0
    return cos_fg * (KCAL_FIT_FLOOR + (1.0 - KCAL_FIT_FLOOR) * kcal_fit)


def recency(cand: MealCandidate, ctx: MealContext) -> float:
    """Component (2): exponential decay, 1.0 today / 0.5 at 14 d (§4.2)."""
    days_since = max(0, (ctx.today - cand.last_eaten_date).days)
    return 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)


def frequency(cand: MealCandidate) -> float:
    """Component (3): saturating ratio ``n / (n + K)`` (§4.2)."""
    n = max(0, cand.logged_count)
    return n / (n + FREQ_SMOOTHING) if (n + FREQ_SMOOTHING) > 0 else 0.0


def adherence(cand: MealCandidate, ctx: MealContext) -> float:
    """Component (4): fraction of the food's days that were on-target (§4.3).

    Neutral ``0.5`` until adherence is trustworthy (documented fallback).
    """
    if not ctx.adherence_reliable or not cand.eaten_days:
        return 0.5
    hits = len(cand.eaten_days & ctx.adherent_days)
    return hits / len(cand.eaten_days)


def category_fit(cand: MealCandidate, ctx: MealContext) -> float:
    """Component (5): 1.0 same category / 0.6 near typical time / 0.3 otherwise."""
    if cand.category == ctx.predicted_category:
        return 1.0
    if cand.eaten_hours:
        median_min = int(median(cand.eaten_hours)) * 60
        if abs(median_min - ctx.now_minutes) <= TIME_FIT_WINDOW_MIN:
            return 0.6
    return 0.3


def score_food(cand: MealCandidate, ctx: MealContext) -> tuple[float, dict[str, float]]:
    """Composite meal score + per-component sub-scores for audit (§4.2.1).

    ``score = W_M·M + W_A·A + W_R·R + W_F·F + W_T·T + W_FAV·Fav``.
    """
    m = macro_fit(cand, ctx)
    a = adherence(cand, ctx)
    r = recency(cand, ctx)
    f = frequency(cand)
    t = category_fit(cand, ctx)
    fav = 1.0 if cand.favorite else 0.0
    score = W_M * m + W_A * a + W_R * r + W_F * f + W_T * t + W_FAV * fav
    components = {
        "macro_fit": round(m, 4),
        "adherence": round(a, 4),
        "recency": round(r, 4),
        "frequency": round(f, 4),
        "category_fit": round(t, 4),
        "favorite": round(fav, 4),
    }
    return score, components


# ===========================================================================
# Diversification — Maximal Marginal Relevance (§4.5)
# ===========================================================================
def _pick_similarity(a: dict, b: dict) -> float:
    cat = 1.0 if a["category"] == b["category"] else 0.0
    macro = cosine(
        (a["protein_g"], a["carbs_g"], a["fat_g"]),
        (b["protein_g"], b["carbs_g"], b["fat_g"]),
    )
    jac = jaccard(tokens(a["name"]), tokens(b["name"]))
    return 0.5 * cat + 0.3 * macro + 0.2 * jac


def _selection_key(adj: float, rank: int) -> tuple[int, int]:
    """Deterministic argmax key: higher adjusted-score bucket first, then rotate.

    Scores within ``TIE_EPSILON`` share a bucket (statistically equivalent) and
    are ordered by ``rotation_rank`` so the daily pick rotates reproducibly.
    """
    return (int(round(adj / TIE_EPSILON)), -rank)


def diversify(items: list[dict], top_n: int) -> list[dict]:
    """Greedy MMR selection with category-cap and near-duplicate rules (§4.5).

    Each ``item`` must carry ``name``/``category``/``protein_g``/``carbs_g``/
    ``fat_g``/``score``/``rotation_rank``. Returns the chosen items (same dict
    refs) in presentation order.
    """
    pool = list(items)
    if top_n <= 0 or not pool:
        return []
    n_categories = len({i["category"] for i in pool})
    cat_cap = CATEGORY_CAP if n_categories >= 3 else top_n

    selected: list[dict] = []
    cat_counts: dict[str, int] = {}
    while pool and len(selected) < top_n:
        best: Optional[dict] = None
        best_key: Optional[tuple[int, int]] = None
        for c in pool:
            if cat_counts.get(c["category"], 0) >= cat_cap:
                continue
            if any(
                jaccard(tokens(c["name"]), tokens(s["name"])) >= NEAR_DUPLICATE_JACCARD
                for s in selected
            ):
                continue
            penalty = max((_pick_similarity(c, s) for s in selected), default=0.0)
            adj = c["score"] - MMR_LAMBDA * penalty
            key = _selection_key(adj, c["rotation_rank"])
            if best_key is None or key > best_key:
                best_key, best = key, c
        if best is None:
            # Every remaining item is blocked by a hard rule; relax to still fill
            # the slate, choosing the highest raw score deterministically.
            best = max(
                pool, key=lambda c: _selection_key(c["score"], c["rotation_rank"])
            )
        selected.append(best)
        pool.remove(best)
        cat_counts[best["category"]] = cat_counts.get(best["category"], 0) + 1
    return selected


# ===========================================================================
# Confidence (§4.8, §5.5)
# ===========================================================================
def confidence_meal(days_observed: int, distinct_foods: int) -> str:
    if days_observed >= MEAL_HIGH_CONF_DAYS and distinct_foods >= MEAL_HIGH_CONF_FOODS:
        return "high"
    if days_observed >= MEAL_MED_CONF_DAYS and distinct_foods >= MEAL_MED_CONF_FOODS:
        return "medium"
    return "low"


def confidence_workout(n_sessions: int) -> str:
    if n_sessions >= WORKOUT_HIGH_CONF_SESSIONS:
        return "high"
    if n_sessions >= WORKOUT_MED_CONF_SESSIONS:
        return "medium"
    return "low"


def min_confidence(levels: list[str]) -> str:
    """Lowest confidence in a list ("a day is only as trustworthy as its least-known lift")."""
    if not levels:
        return "low"
    return min(levels, key=lambda level: _CONFIDENCE_ORDER.get(level, 0))


# ===========================================================================
# Workout progression (§5.2)
# ===========================================================================
@dataclass(frozen=True)
class SessionSummary:
    """One logged session's top working set + volume + estimated 1RM."""

    date: date
    top_weight: float
    top_reps: int
    top_rpe: Optional[float]
    sets_completed: int
    session_e1rm: float


@dataclass(frozen=True)
class Prescription:
    """The program prescription for one exercise, plus its plate increment."""

    rep_low: int
    rep_high: int
    target_sets: int
    target_rpe: Optional[float]
    increment: float
    round_step: float


@dataclass(frozen=True)
class ExerciseDecision:
    """The engine's raw decision for an exercise (weights un-snapped)."""

    action: str          # start | increase | hold | reduce | deload
    weight: Optional[float]
    reps: int            # single next-rep target (drives change.reps_delta)
    target_sets: int
    deload: bool
    reason_kind: str


def increment_for_muscle_group(group: Optional[str]) -> float:
    """Plate increment for a lift's coarse muscle group (upper 1.25 / lower 2.5)."""
    key = "lower" if (group or "").strip().lower() in _LOWER_MUSCLE_GROUPS else "upper"
    return LINEAR_INCREMENT_KG[key]


def _beats(cur: SessionSummary, prev: SessionSummary) -> bool:
    """Did ``cur`` beat ``prev`` at the top set on either load or reps?"""
    if cur.top_weight > prev.top_weight:
        return True
    if cur.top_weight == prev.top_weight and cur.top_reps > prev.top_reps:
        return True
    return False


def _trailing_stalls(sessions: list[SessionSummary]) -> int:
    """Consecutive logged sessions (from newest) that did not beat their predecessor."""
    count = 0
    for i in range(len(sessions) - 1, 0, -1):
        if _beats(sessions[i], sessions[i - 1]):
            break
        count += 1
    return count


def _trailing_misses(sessions: list[SessionSummary], rep_low: int) -> int:
    """Consecutive logged sessions (from newest) whose top reps fell below ``rep_low``."""
    count = 0
    for s in reversed(sessions):
        if s.top_reps < rep_low:
            count += 1
        else:
            break
    return count


def decide_progression(
    prescription: Prescription,
    sessions: list[SessionSummary],
    best_e1rm: Optional[float],
    layoff_days: Optional[int],
    cold_start_weight: Optional[float],
) -> ExerciseDecision:
    """Double progression gated by RPE, evaluated in priority order (§5.2).

    ``sessions`` are the exercise's recent logged sessions, **oldest → newest**.
    Returns raw (un-snapped) weights; the caller snaps them to a loadable plate
    increment via :func:`app.services.performance.round_to_increment`.
    """
    rl, rh = prescription.rep_low, prescription.rep_high
    tsets = prescription.target_sets
    trpe = prescription.target_rpe
    inc = prescription.increment

    # Rule 0 — cold start: no prior working sets for this exercise.
    if not sessions:
        return ExerciseDecision(
            action="start",
            weight=cold_start_weight,
            reps=rl,
            target_sets=tsets,
            deload=False,
            reason_kind="start",
        )

    last = sessions[-1]
    lw, lr, lrpe = last.top_weight, last.top_reps, last.top_rpe
    bodyweight = lw <= 0  # plank / bodyweight movement — progress reps, never load

    # §5.3 — long layoff: resume lighter, do NOT treat the gap as a stall/miss.
    if layoff_days is not None and layoff_days > LAYOFF_DAYS:
        weight = lw if bodyweight else lw * LAYOFF_LOAD_FRACTION
        return ExerciseDecision(
            action="hold",
            weight=weight,
            reps=rl,
            target_sets=tsets,
            deload=False,
            reason_kind="layoff",
        )

    stall_count = _trailing_stalls(sessions)
    miss_count = _trailing_misses(sessions, rl)

    # Rule 1 — deload: repeated stalls, a falling e1RM, or persistent high-RPE misses.
    e1rm_regress = (
        best_e1rm is not None
        and best_e1rm > 0
        and last.session_e1rm <= best_e1rm * (1.0 - E1RM_REGRESS_PCT)
    )
    last_two = sessions[-2:]
    high_rpe_deload = (
        len(last_two) == 2
        and trpe is not None
        and all(
            s.top_rpe is not None
            and s.top_rpe >= trpe + HIGH_RPE_MARGIN
            and s.top_reps < rl
            for s in last_two
        )
    )
    if not bodyweight and (
        stall_count >= STALL_SESSIONS_FOR_DELOAD or e1rm_regress or high_rpe_deload
    ):
        kind = (
            "deload_stall"
            if stall_count >= STALL_SESSIONS_FOR_DELOAD
            else "deload_e1rm"
            if e1rm_regress
            else "deload_rpe"
        )
        return ExerciseDecision(
            action="deload",
            weight=lw * DELOAD_LOAD_FRACTION,
            reps=rl,
            target_sets=tsets,
            deload=True,
            reason_kind=kind,
        )

    # Rule 2 — reduce: a 2nd consecutive real miss (top reps below the range).
    if miss_count >= 2 and not bodyweight:
        return ExerciseDecision(
            action="reduce",
            weight=lw - inc,
            reps=rl,
            target_sets=tsets,
            deload=False,
            reason_kind="reduce",
        )

    # Rule 3 — hold after a single miss: repeat the load, chase one more rep.
    if miss_count == 1:
        return ExerciseDecision(
            action="hold",
            weight=lw,
            reps=min(rh, lr + 1),
            target_sets=tsets,
            deload=False,
            reason_kind="hold_miss",
        )

    # Rule 4 — increase: top of range at ≤ target RPE with all sets completed.
    rpe_allows_increase = trpe is None or lrpe is None or lrpe <= trpe
    if (
        not bodyweight
        and lr >= rh
        and rpe_allows_increase
        and last.sets_completed >= tsets
    ):
        easy = trpe is not None and lrpe is not None and lrpe <= trpe - EASY_RPE_MARGIN
        added = inc * (2 if easy else 1)
        return ExerciseDecision(
            action="increase",
            weight=lw + added,
            reps=rl,
            target_sets=tsets,
            deload=False,
            reason_kind="increase_double" if easy else "increase",
        )

    # Rule 5 — hold (progress reps): inside the range, or top of range but not yet
    # cleared for a load jump (fatigue / missing set), or a bodyweight movement.
    return ExerciseDecision(
        action="hold",
        weight=lw,
        reps=min(rh, lr + 1),
        target_sets=tsets,
        deload=False,
        reason_kind="hold_bodyweight" if bodyweight else "hold_progress",
    )


def direction_of(delta: float, *, epsilon: float = 1e-6) -> str:
    if delta > epsilon:
        return "up"
    if delta < -epsilon:
        return "down"
    return "flat"


__all__ = [
    "RECOMMENDATION_VERSION",
    "RECOMMENDATION_ALGORITHM",
    "MEAL_WINDOW_DAYS",
    "norm",
    "tokens",
    "jaccard",
    "cosine",
    "stable_hash",
    "rotation_rank",
    "round_to",
    "clamp",
    "portion_factor",
    "MealCandidate",
    "MealContext",
    "macro_fit",
    "recency",
    "frequency",
    "adherence",
    "category_fit",
    "score_food",
    "diversify",
    "confidence_meal",
    "confidence_workout",
    "min_confidence",
    "SessionSummary",
    "Prescription",
    "ExerciseDecision",
    "increment_for_muscle_group",
    "decide_progression",
    "direction_of",
]
