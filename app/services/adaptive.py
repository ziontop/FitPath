"""History-adaptive recommendations — orchestration + per-user data access.

This service layer wires the pure engine in :mod:`app.ml.adaptive` to the
authenticated user's own rows (``meal_log``, ``set_log`` ⨝ ``workout_session``,
``program_exercise``, ``nutrition_plan``, ``profile``) and serializes the results
into the additive ``/api/recommendations/*`` envelope described in
``docs/ADAPTIVE-RECOMMENDATIONS.md``.

Design guarantees upheld here:

* **Deterministic** — same date + same rows ⇒ same output (ties rotate via a
  stable per-day key, never randomness).
* **Privacy-preserving** — every query is scoped by ``user_id``; no cross-user
  aggregation, no third-party calls, no LLM.
* **Reuse the science** — targets come from :mod:`app.services.nutrition`
  (single source of truth), progression/e1RM from
  :mod:`app.services.performance` and :mod:`app.training.params`, timing/patterns
  from :mod:`app.ml.coach`. Nothing is re-derived with a different constant.
* **No silent failure** — a missing profile raises ``400`` (mirroring
  ``nutrition.nutrition_today``); cold-start / sparse history use the documented,
  explicit fallbacks in §4.7.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from statistics import median
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ml import adaptive, coach
from ..ml.adaptive import (
    MealCandidate,
    MealContext,
    Prescription,
    RECOMMENDATION_ALGORITHM,
    RECOMMENDATION_VERSION,
)
from ..models import MealLog, SetLog, User, WorkoutSession
from . import nutrition, performance, programs
from .mapping import muscle_group_for

_MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g")


# ===========================================================================
# Data access (all user-scoped)
# ===========================================================================
def _history_rows(
    db: Session, user_id: int, days: int, exclude_today: bool = True
) -> list[MealLog]:
    """The user's ``meal_log`` rows over the trailing ``days`` window."""
    today = datetime.now().date()
    cutoff = datetime.combine(today - timedelta(days=days), time.min)
    stmt = select(MealLog).where(
        MealLog.user_id == user_id, MealLog.eaten_at >= cutoff
    )
    if exclude_today:
        stmt = stmt.where(MealLog.eaten_at < datetime.combine(today, time.min))
    return list(db.scalars(stmt.order_by(MealLog.eaten_at)).all())


def _today_rows(db: Session, user_id: int) -> list[MealLog]:
    today = datetime.now().date()
    start = datetime.combine(today, time.min)
    end = start + timedelta(days=1)
    return list(
        db.scalars(
            select(MealLog)
            .where(
                MealLog.user_id == user_id,
                MealLog.eaten_at >= start,
                MealLog.eaten_at < end,
            )
            .order_by(MealLog.eaten_at)
        ).all()
    )


def _meal_dict(m: MealLog) -> dict:
    """Plain dict shape the offline :mod:`app.ml.coach` helpers consume."""
    return {
        "name": m.name,
        "category": m.category,
        "kcal": m.kcal,
        "eaten_at": m.eaten_at.isoformat(timespec="minutes"),
        "protein_g": m.protein_g,
        "carbs_g": m.carbs_g,
        "fat_g": m.fat_g,
    }


def _exercise_sessions(
    db: Session, user_id: int, exercise_id: int, limit: int
) -> list[adaptive.SessionSummary]:
    """Recent logged sessions for one exercise (oldest → newest, ≤ ``limit``).

    Reuses :func:`app.services.performance._working_sets_stmt` (warm-ups already
    excluded) and groups the working sets per ``workout_session`` to derive the
    top set, sets completed and session e1RM.
    """
    rows = db.execute(
        performance._working_sets_stmt(user_id)
        .where(SetLog.exercise_id == exercise_id)
        .order_by(WorkoutSession.date, SetLog.set_index)
    ).all()

    by_session: dict[int, dict] = {}
    for s, d, _e in rows:
        group = by_session.setdefault(s.workout_session_id, {"date": d, "sets": []})
        group["sets"].append(s)

    summaries: list[tuple[date, int, adaptive.SessionSummary]] = []
    for sid, group in by_session.items():
        sets = group["sets"]
        if not sets:
            continue
        top = max(sets, key=lambda x: (x.weight, x.reps))
        e1rm = max(performance._e1rm(x.weight, x.reps) for x in sets)
        summaries.append(
            (
                group["date"],
                sid,
                adaptive.SessionSummary(
                    date=group["date"],
                    top_weight=top.weight,
                    top_reps=top.reps,
                    top_rpe=top.rpe,
                    sets_completed=len(sets),
                    session_e1rm=e1rm,
                ),
            )
        )
    summaries.sort(key=lambda t: (t[0], t[1]))
    return [summary for (_d, _sid, summary) in summaries][-limit:]


# ===========================================================================
# Meal engine (§4)
# ===========================================================================
def _macro_set(kcal: float, protein: float, carbs: float, fat: float) -> dict:
    return {
        "kcal": round(kcal),
        "protein_g": round(protein, 1),
        "carbs_g": round(carbs, 1),
        "fat_g": round(fat, 1),
    }


def _last_eaten_phrase(days_since: int) -> str:
    if days_since <= 0:
        return "today"
    if days_since == 1:
        return "1 day ago"
    return f"{days_since} days ago"


def _meal_reason(
    *,
    category: str,
    components: dict[str, float],
    gap: tuple[float, float, float],
    logged_count: int,
    adherence_reliable: bool,
    favorite: bool,
) -> str:
    """Plain-English reason built from the dominant weighted components (§4.9)."""
    gap_named = sorted(
        (("protein", gap[0]), ("carbs", gap[1]), ("fat", gap[2])),
        key=lambda kv: kv[1],
        reverse=True,
    )
    top_gaps = [(name, grams) for name, grams in gap_named if grams > 0][:2]
    parts: list[str] = []
    if top_gaps:
        macro_phrase = " / ".join(f"{round(grams)}g {name}" for name, grams in top_gaps)
        parts.append(f"fits your remaining {macro_phrase} gap")
    else:
        parts.append("rounds out an already on-target day")

    if components["frequency"] >= 0.5 or components["recency"] >= 0.7:
        parts.append(f"a go-to {category} you've logged {logged_count}×")
    elif components["category_fit"] >= 1.0:
        parts.append(f"a typical {category} choice for now")

    if adherence_reliable and components["adherence"] >= 0.6:
        parts.append("and it shows up on your on-target days")
    if favorite:
        parts.append("and it's a favorite")

    sentence = ", ".join(parts)
    return sentence[0].upper() + sentence[1:] + "."


def _meal_history_basis(
    *,
    total_meals: int,
    days_observed: int,
    logged_count: int,
    days_since: int,
    eaten_days: int,
    adherent_hits: int,
) -> str:
    return (
        f"From {total_meals} meals over {days_observed} days · "
        f"eaten {logged_count}× (last {_last_eaten_phrase(days_since)}) · "
        f"on {adherent_hits} of {eaten_days} logged day(s) on-target."
    )


def _scaled_suggestion(item: dict, ctx: MealContext, confidence: str) -> dict:
    """Portion-scale a scored history candidate into an AdaptiveMealSuggestion."""
    portion = adaptive.portion_factor(item["base_kcal"], ctx.budget_kcal)
    kcal = round(item["base_kcal"] * portion)
    protein = round(item["protein_g"] * portion, 1)
    carbs = round(item["carbs_g"] * portion, 1)
    fat = round(item["fat_g"] * portion, 1)
    days_since = max(0, (ctx.today - item["last_eaten"].date()).days)
    reason = _meal_reason(
        category=item["category"],
        components=item["components"],
        gap=(ctx.gap_protein, ctx.gap_carbs, ctx.gap_fat),
        logged_count=item["logged_count"],
        adherence_reliable=ctx.adherence_reliable,
        favorite=item["favorite"],
    )
    history_basis = _meal_history_basis(
        total_meals=item["total_meals"],
        days_observed=item["days_observed"],
        logged_count=item["logged_count"],
        days_since=days_since,
        eaten_days=item["eaten_days_count"],
        adherent_hits=item["adherent_hits"],
    )
    return {
        "name": item["name"],
        "category": item["category"],
        "kcal": kcal,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "portion": round(portion, 2),
        "score": round(item["score"], 3),
        "components": item["components"],
        "reason": reason,
        "history_basis": history_basis,
        "confidence": confidence,
        "logged_count": item["logged_count"],
        "last_eaten_at": item["last_eaten"].isoformat(timespec="minutes"),
        "meal_payload": {
            "name": item["name"],
            "kcal": kcal,
            "category": item["category"],
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
        },
    }


def _fallback_suggestions(
    ctx: MealContext,
    limit: int,
    exclude_names: Optional[set[str]] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Curated starter foods re-ranked by macro-fit + portion-scaled (§4.7).

    When a ``category`` filter is active the starters are labelled with it so a
    category-scoped request never leaks a food from another slot.
    """
    exclude = {adaptive.norm(n) for n in (exclude_names or set())}
    label = category or ctx.predicted_category
    scored: list[tuple[float, dict]] = []
    for food in nutrition._FALLBACK_SUGGESTIONS:
        if adaptive.norm(food["name"]) in exclude:
            continue
        cand = MealCandidate(
            name=food["name"],
            category=label,
            base_kcal=float(food["kcal"]),
            base_protein=float(food["protein_g"]),
            base_carbs=float(food["carbs_g"]),
            base_fat=float(food["fat_g"]),
            logged_count=0,
            last_eaten_date=ctx.today,
            favorite=False,
        )
        fit = adaptive.macro_fit(cand, ctx)
        scored.append((fit, cand))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    out: list[dict] = []
    for fit, cand in scored[:limit]:
        portion = adaptive.portion_factor(cand.base_kcal, ctx.budget_kcal)
        kcal = round(cand.base_kcal * portion)
        protein = round(cand.base_protein * portion, 1)
        carbs = round(cand.base_carbs * portion, 1)
        fat = round(cand.base_fat * portion, 1)
        components = {
            "macro_fit": round(fit, 4),
            "adherence": 0.0,
            "recency": 0.0,
            "frequency": 0.0,
            "category_fit": 0.0,
            "favorite": 0.0,
        }
        out.append(
            {
                "name": cand.name,
                "category": cand.category,
                "kcal": kcal,
                "protein_g": protein,
                "carbs_g": carbs,
                "fat_g": fat,
                "portion": round(portion, 2),
                "score": round(fit, 3),
                "components": components,
                "reason": "Starter suggestion picked to match your remaining macros.",
                "history_basis": "No logged meals yet — starter suggestions.",
                "confidence": "low",
                "logged_count": 0,
                "last_eaten_at": None,
                "meal_payload": {
                    "name": cand.name,
                    "kcal": kcal,
                    "category": cand.category,
                    "protein_g": protein,
                    "carbs_g": carbs,
                    "fat_g": fat,
                },
            }
        )
    return out


def adaptive_meals(
    db: Session,
    user: User,
    *,
    category: Optional[str] = None,
    limit: int = 3,
) -> dict:
    """Detailed adaptive meal recommendations (AdaptiveMealsBlock, §4/§6.3)."""
    profile = nutrition._require_profile(db, user.id)  # 400 if missing (§4.7)
    limit = max(1, min(limit, 10))
    now = datetime.now()
    today = now.date()

    # --- targets (single source of truth: active plan → else profile-derived) ---
    plan = nutrition.active_plan(db, user.id)
    macros = nutrition.active_macro_targets(db, user.id, profile)
    kcal_target = float(plan.target_kcal) if plan else float(
        nutrition.goal_target_kcal(profile)
    )
    targets = _macro_set(kcal_target, macros["protein"], macros["carbs"], macros["fat"])

    today_rows = _today_rows(db, user.id)
    consumed = _macro_set(
        sum(m.kcal for m in today_rows),
        sum(m.protein_g or 0 for m in today_rows),
        sum(m.carbs_g or 0 for m in today_rows),
        sum(m.fat_g or 0 for m in today_rows),
    )
    remaining = {key: round(targets[key] - consumed[key], 1) for key in _MACRO_KEYS}

    gap_protein = max(0.0, targets["protein_g"] - consumed["protein_g"])
    gap_carbs = max(0.0, targets["carbs_g"] - consumed["carbs_g"])
    gap_fat = max(0.0, targets["fat_g"] - consumed["fat_g"])
    remaining_kcal = max(0.0, targets["kcal"] - consumed["kcal"])

    # --- next-meal prediction (reuse coach pattern mining) ---
    history_rows = _history_rows(db, user.id, adaptive.MEAL_WINDOW_DAYS, exclude_today=True)
    prediction = coach.predict_next_meal_detailed(
        history_meals=[_meal_dict(m) for m in history_rows],
        todays_meals=[_meal_dict(m) for m in today_rows],
        daily_kcal_target=kcal_target,
        todays_macros_consumed={
            "protein_g": consumed["protein_g"],
            "carbs_g": consumed["carbs_g"],
            "fat_g": consumed["fat_g"],
        },
        now=now,
        target_macros=macros,
    )
    predicted_category = prediction["predicted_category"]
    typical_meal_kcal = prediction.get("typical_kcal_for_category") or (
        kcal_target / 4 if kcal_target else 1.0
    )
    meals_left_est = (
        max(1, round(remaining_kcal / typical_meal_kcal))
        if remaining_kcal > 0 and typical_meal_kcal > 0
        else 1
    )
    budget = remaining_kcal / meals_left_est if meals_left_est else remaining_kcal

    # --- aggregate candidates (§4.1) + adherent days (§4.3) ---
    groups: dict[tuple[str, str], dict] = {}
    for m in history_rows:
        key = (adaptive.norm(m.name), m.category)
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "name": m.name.strip(),
                "category": m.category,
                "kcal": [],
                "protein": [],
                "carbs": [],
                "fat": [],
                "count": 0,
                "last_eaten": m.eaten_at,
                "favorite": False,
                "days": set(),
                "hours": [],
            }
        group["count"] += 1
        group["kcal"].append(m.kcal)
        group["protein"].append(m.protein_g or 0)
        group["carbs"].append(m.carbs_g or 0)
        group["fat"].append(m.fat_g or 0)
        group["favorite"] = group["favorite"] or bool(m.favorite)
        group["last_eaten"] = max(group["last_eaten"], m.eaten_at)
        group["days"].add(m.eaten_at.date())
        group["hours"].append(m.eaten_at.hour)

    distinct_foods = len(groups)
    days_observed = len({m.eaten_at.date() for m in history_rows})
    total_meals = len(history_rows)

    by_day_kcal: dict[date, float] = {}
    by_day_protein: dict[date, float] = {}
    for m in history_rows:
        d = m.eaten_at.date()
        by_day_kcal[d] = by_day_kcal.get(d, 0.0) + m.kcal
        by_day_protein[d] = by_day_protein.get(d, 0.0) + (m.protein_g or 0)
    adherent_days = frozenset(
        d
        for d in by_day_kcal
        if adaptive.KCAL_LOW * kcal_target <= by_day_kcal[d] <= adaptive.KCAL_HIGH * kcal_target
        and by_day_protein[d] >= adaptive.PROTEIN_MIN * targets["protein_g"]
    )
    adherence_reliable = bool(adherent_days) and days_observed >= adaptive.MIN_DAYS_FOR_ADHERENCE

    ctx = MealContext(
        gap_protein=gap_protein,
        gap_carbs=gap_carbs,
        gap_fat=gap_fat,
        budget_kcal=budget,
        predicted_category=predicted_category,
        now_minutes=now.hour * 60 + now.minute,
        today=today,
        adherent_days=adherent_days,
        adherence_reliable=adherence_reliable,
    )

    today_keys = {(adaptive.norm(m.name), m.category) for m in today_rows}
    block_confidence = adaptive.confidence_meal(days_observed, distinct_foods)

    scored_items: list[dict] = []
    for (nkey, cat), group in groups.items():
        if (nkey, cat) in today_keys:  # §4.1 exclude already-eaten-today
            continue
        if category and cat != category:
            continue
        cand = MealCandidate(
            name=group["name"],
            category=cat,
            base_kcal=float(median(group["kcal"])),
            base_protein=float(median(group["protein"])),
            base_carbs=float(median(group["carbs"])),
            base_fat=float(median(group["fat"])),
            logged_count=group["count"],
            last_eaten_date=group["last_eaten"].date(),
            favorite=group["favorite"],
            eaten_days=frozenset(group["days"]),
            eaten_hours=tuple(group["hours"]),
        )
        score, components = adaptive.score_food(cand, ctx)
        scored_items.append(
            {
                "name": cand.name,
                "category": cand.category,
                "protein_g": cand.base_protein,
                "carbs_g": cand.base_carbs,
                "fat_g": cand.base_fat,
                "base_kcal": cand.base_kcal,
                "score": score,
                "components": components,
                "rotation_rank": adaptive.rotation_rank(user.id, today, nkey),
                "logged_count": cand.logged_count,
                "last_eaten": group["last_eaten"],
                "favorite": cand.favorite,
                "eaten_days_count": len(cand.eaten_days),
                "adherent_hits": len(cand.eaten_days & adherent_days),
                "total_meals": total_meals,
                "days_observed": days_observed,
            }
        )

    # --- assemble suggestions per cold-start / sparse / normal state (§4.7) ---
    if distinct_foods == 0 or not scored_items:
        suggestions = _fallback_suggestions(ctx, limit, category=category)
    elif distinct_foods <= 2 or days_observed < adaptive.MIN_DAYS_FOR_ADHERENCE:
        picked = adaptive.diversify(scored_items, limit)
        suggestions = [_scaled_suggestion(item, ctx, block_confidence) for item in picked]
        if len(suggestions) < limit:
            existing = {adaptive.norm(s["name"]) for s in suggestions}
            suggestions += _fallback_suggestions(
                ctx, limit - len(suggestions), exclude_names=existing, category=category
            )
    else:
        picked = adaptive.diversify(scored_items, limit)
        suggestions = [_scaled_suggestion(item, ctx, block_confidence) for item in picked]

    return {
        "version": RECOMMENDATION_VERSION,
        "algorithm": RECOMMENDATION_ALGORITHM,
        "targets": targets,
        "consumed": consumed,
        "remaining": remaining,
        "next_meal": {
            "predicted_category": prediction["predicted_category"],
            "predicted_time": prediction["predicted_time"],
            "suggested_kcal": prediction["suggested_kcal"],
        },
        "history_basis": {
            "window_days": adaptive.MEAL_WINDOW_DAYS,
            "days_observed": days_observed,
            "total_meals": total_meals,
            "distinct_foods": distinct_foods,
            "adherent_days": len(adherent_days),
        },
        "confidence": block_confidence,
        "suggestions": suggestions,
    }


# ===========================================================================
# Workout engine (§5)
# ===========================================================================
def _rep_bounds(target_reps: str) -> tuple[int, int]:
    """Parse ``"6-9"`` → ``(6, 9)`` (reusing programs.low_rep for the low end)."""
    low = programs.low_rep(target_reps)
    high = low
    parts = (target_reps or "").replace("–", "-").split("-")
    if len(parts) >= 2:
        digits = "".join(ch for ch in parts[1] if ch.isdigit())
        if digits:
            high = int(digits)
    return low, max(low, high)


def _consistency(sessions_14d: int, scheduled: int) -> str:
    if sessions_14d == 0:
        return "returning"
    expected = max(1, scheduled) * 2  # ≈ two weeks of the scheduled cadence
    if sessions_14d >= math.ceil(expected * 0.7):
        return "on_track"
    return "inconsistent"


def _workout_adherence(db: Session, user_id: int, scheduled: int) -> dict:
    today = datetime.now().date()
    sessions_14d = (
        db.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.date >= today - timedelta(days=14),
            )
        )
        or 0
    )
    return {
        "sessions_last_14d": int(sessions_14d),
        "scheduled_days_per_week": scheduled,
        "consistency": _consistency(int(sessions_14d), scheduled),
    }


def _select_day(db, user_id, days, program_day_id, today):
    """Adaptive next-in-rotation day selection (§5.4). ``None`` ⇒ rest day."""
    if program_day_id is not None:
        day = next((d for d in days if d.id == program_day_id), None)
        if day is None:
            raise HTTPException(
                status_code=404, detail="program_day_id not in active program"
            )
        return day

    day_ids = [d.id for d in days]
    last = db.scalar(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.program_day_id.in_(day_ids),
        )
        .order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
    )
    if last is not None and last.program_day_id is not None:
        last_day = next((d for d in days if d.id == last.program_day_id), None)
        if last_day is not None:
            next_index = (last_day.day_index + 1) % len(days)
            return next(d for d in days if d.day_index == next_index)

    # No completed program session yet — fall back to the weekday rotation.
    schedule = programs.weekly_schedule(len(days))
    weekday = today.weekday()
    if weekday in schedule:
        return days[schedule[weekday]]
    return None


def _exercise_reason(
    *,
    kind: str,
    name: str,
    last: Optional[adaptive.SessionSummary],
    rep_low: int,
    rep_high: int,
    target_rpe: Optional[float],
    weight: Optional[float],
    weight_delta: float,
    layoff_days: Optional[int],
) -> str:
    weight_txt = f"{weight} kg" if weight is not None else "a starting weight"
    delta_txt = f"{abs(round(weight_delta, 2))} kg"
    if kind == "start":
        if weight is not None:
            return (
                f"First {name} session on this program — start around {weight_txt} "
                f"for {rep_low}-{rep_high} reps and we'll adapt from your logs."
            )
        return (
            f"No {name} history yet — pick a comfortable weight for {rep_low}-{rep_high} "
            "reps; the engine adapts once you log a set."
        )
    if kind == "layoff":
        return (
            f"Resuming after {layoff_days} days off — starting a touch lighter at "
            f"{weight_txt} for {rep_low} reps. Not a stall, just easing back in."
        )
    if kind == "deload_stall":
        return (
            f"Progress stalled for a few sessions — deloading to {weight_txt} (~90%) "
            "to shed fatigue and resupercompensate."
        )
    if kind == "deload_e1rm":
        return (
            f"Your estimated 1RM slipped ≥5% — deloading to {weight_txt} to recover "
            "before pushing again."
        )
    if kind == "deload_rpe":
        return (
            f"Two hard sessions short of the range at high RPE — deloading to "
            f"{weight_txt} to manage fatigue."
        )
    if kind == "reduce":
        return (
            f"Second miss in a row below {rep_low} reps — backing off {delta_txt} to "
            f"{weight_txt} to rebuild with clean reps."
        )
    if kind == "hold_miss":
        return (
            f"Just short of {rep_low} reps last time — repeat {weight_txt} and chase "
            "one more rep before adding load."
        )
    if kind in ("increase", "increase_double"):
        rpe_txt = f" @ RPE {last.top_rpe}" if last and last.top_rpe is not None else ""
        jump = "a double jump" if kind == "increase_double" else f"{delta_txt}"
        reps_txt = f"{last.top_reps} reps" if last else "the top of your range"
        return (
            f"You hit {reps_txt}{rpe_txt} last time (top of range with reps to spare) "
            f"— adding {jump} to {weight_txt} and resetting to {rep_low} reps."
        )
    if kind == "hold_bodyweight":
        return (
            f"Bodyweight movement — hold and build reps toward {rep_high} before "
            "adding external load."
        )
    return (
        f"Inside your {rep_low}-{rep_high} range — hold {weight_txt} and add a rep "
        "toward the top before the next load bump."
    )


def _exercise_history_basis(
    name: str, sessions: list[adaptive.SessionSummary], e1rm_trend: Optional[dict]
) -> str:
    if not sessions:
        return f"No logged {name} sessions yet — using the program prescription."
    n = len(sessions)
    if e1rm_trend is not None:
        return (
            f"Based on your last {n} {name} session(s); "
            f"e1RM {e1rm_trend['first']} → {e1rm_trend['last']} kg."
        )
    return f"Based on your last {n} {name} session(s)."


def _exercise_rec(db: Session, user_id: int, pe, today: date) -> dict:
    ex = pe.exercise
    name = ex.name if ex is not None else "Exercise"
    rep_low, rep_high = _rep_bounds(pe.target_reps)
    group = muscle_group_for(ex.primary_muscle) if ex is not None else None
    increment = adaptive.increment_for_muscle_group(group.value if group else None)

    prescription = Prescription(
        rep_low=rep_low,
        rep_high=rep_high,
        target_sets=pe.target_sets,
        target_rpe=pe.target_rpe,
        increment=increment,
        round_step=increment,
    )
    sessions = _exercise_sessions(
        db, user_id, pe.exercise_id, adaptive.WORKOUT_LOOKBACK_SESSIONS
    )
    best_e1rm = performance.best_recent_e1rm(db, user_id, pe.exercise_id)
    layoff_days = (today - sessions[-1].date).days if sessions else None
    cold_start_weight = performance.suggested_weight(
        best_e1rm, rep_low, pe.target_rpe, step=increment
    )

    decision = adaptive.decide_progression(
        prescription, sessions, best_e1rm, layoff_days, cold_start_weight
    )
    weight = (
        performance.round_to_increment(decision.weight, step=increment)
        if decision.weight is not None
        else None
    )

    last = sessions[-1] if sessions else None
    last_performance = None
    if last is not None:
        last_performance = {
            "date": last.date.isoformat(),
            "weight": last.top_weight,
            "reps": last.top_reps,
            "rpe": last.top_rpe,
            "sets": last.sets_completed,
            "e1rm": round(last.session_e1rm, 1),
        }

    if last is not None:
        weight_delta = round((weight - last.top_weight), 2) if weight is not None else 0.0
        reps_delta = decision.reps - last.top_reps
        direction = (
            adaptive.direction_of(weight_delta)
            if abs(weight_delta) > 1e-6
            else adaptive.direction_of(reps_delta)
        )
    else:
        weight_delta, reps_delta, direction = 0.0, 0, "flat"
    change = {
        "weight_delta_kg": weight_delta,
        "reps_delta": reps_delta,
        "direction": direction,
    }

    e1rm_trend = None
    if sessions:
        first = round(sessions[0].session_e1rm, 1)
        last_e1rm = round(sessions[-1].session_e1rm, 1)
        e1rm_trend = {
            "first": first,
            "last": last_e1rm,
            "direction": adaptive.direction_of(last_e1rm - first),
        }

    return {
        "exercise_id": pe.exercise_id,
        "name": name,
        "action": decision.action,
        "suggested_weight": weight,
        "target_sets": decision.target_sets,
        "target_reps": pe.target_reps,
        "target_rpe": pe.target_rpe,
        "deload": decision.deload,
        "last_performance": last_performance,
        "change": change,
        "e1rm_trend": e1rm_trend,
        "confidence": adaptive.confidence_workout(len(sessions)),
        "reason": _exercise_reason(
            kind=decision.reason_kind,
            name=name,
            last=last,
            rep_low=rep_low,
            rep_high=rep_high,
            target_rpe=pe.target_rpe,
            weight=weight,
            weight_delta=weight_delta,
            layoff_days=layoff_days,
        ),
        "history_basis": _exercise_history_basis(name, sessions, e1rm_trend),
    }


def _workout_block(
    *,
    rest_day: bool,
    program_day_id: Optional[int],
    name: Optional[str],
    deload: bool,
    confidence: str,
    adherence: dict,
    reason: str,
    exercises: list[dict],
) -> dict:
    return {
        "version": RECOMMENDATION_VERSION,
        "algorithm": RECOMMENDATION_ALGORITHM,
        "rest_day": rest_day,
        "program_day_id": program_day_id,
        "name": name,
        "deload": deload,
        "confidence": confidence,
        "adherence": adherence,
        "reason": reason,
        "exercises": exercises,
    }


def adaptive_workout(
    db: Session, user: User, program_day_id: Optional[int] = None
) -> dict:
    """Detailed adaptive workout recommendation (AdaptiveWorkoutBlock, §5/§6.3)."""
    now = datetime.now()
    today = now.date()
    program = programs.active_program(db, user.id)
    scheduled = program.days_per_week if program is not None else 0
    adherence = _workout_adherence(db, user.id, scheduled)
    empty_confidence = adaptive.confidence_workout(adherence["sessions_last_14d"])

    if program is None or not program.days:
        return _workout_block(
            rest_day=False,
            program_day_id=None,
            name=None,
            deload=False,
            confidence="low",
            adherence=adherence,
            reason="No active program yet — generate one to get adaptive workout guidance.",
            exercises=[],
        )

    days = sorted(program.days, key=lambda d: d.day_index)
    day = _select_day(db, user.id, days, program_day_id, today)
    if day is None:
        return _workout_block(
            rest_day=True,
            program_day_id=None,
            name=None,
            deload=False,
            confidence=empty_confidence,
            adherence=adherence,
            reason="Scheduled rest day — prioritise sleep, hydration and protein to recover.",
            exercises=[],
        )

    exercises = [
        _exercise_rec(db, user.id, pe, today)
        for pe in sorted(day.exercises, key=lambda x: x.order_index)
    ]
    deload_count = sum(1 for e in exercises if e["deload"])
    session_deload = bool(exercises) and deload_count > len(exercises) / 2
    confidence = adaptive.min_confidence([e["confidence"] for e in exercises]) if exercises else "low"

    if session_deload:
        reason = f"{day.name}: most main lifts are deloading — an intentional lighter session to recover and rebuild."
    else:
        lead = exercises[0]["name"] if exercises else "your main lift"
        reason = f"{day.name}: work up to {lead} at the prescribed RPE; loads below are adapted from your recent logs."

    return _workout_block(
        rest_day=False,
        program_day_id=day.id,
        name=day.name,
        deload=session_deload,
        confidence=confidence,
        adherence=adherence,
        reason=reason,
        exercises=exercises,
    )


# ===========================================================================
# Unified envelope (§6.2)
# ===========================================================================
def _build_tip(meals: dict, workout: dict) -> str:
    """A single, data-grounded coaching line for the Today screen (§9)."""
    remaining = meals.get("remaining", {})
    kcal_left = max(0, round(remaining.get("kcal", 0)))
    protein_left = max(0, round(remaining.get("protein_g", 0)))
    suggestions = meals.get("suggestions") or []
    top_meal = suggestions[0]["name"] if suggestions else None

    if workout.get("rest_day"):
        base = "Rest day — prioritise sleep and hydration."
    elif not workout.get("exercises"):
        base = workout.get("reason") or "No active program yet."
    else:
        name = workout.get("name") or "your session"
        lead = workout["exercises"][0]
        piece = f"Today is {name} — work up to {lead['name']}"
        if lead.get("target_rpe") is not None:
            piece += f" at RPE {lead['target_rpe']}"
        if lead.get("suggested_weight") is not None:
            piece += f" (try {lead['suggested_weight']} kg)"
        base = piece + "."

    tail = f" You have {kcal_left} kcal and {protein_left} g protein left"
    if top_meal:
        tail += f"; a {top_meal.lower()} would close most of it."
    else:
        tail += " to hit today's target."
    return base + tail


def adaptive_today(db: Session, user: User) -> dict:
    """The full adaptive envelope powering the Today screen (§6.2)."""
    now = datetime.now()
    meals = adaptive_meals(db, user)  # raises 400 without a profile (checked first)
    workout = adaptive_workout(db, user)
    return {
        "version": RECOMMENDATION_VERSION,
        "algorithm": RECOMMENDATION_ALGORITHM,
        "generated_at": now.isoformat(timespec="seconds"),
        "meals": meals,
        "workout": workout,
        "tip": _build_tip(meals, workout),
    }


__all__ = ["adaptive_meals", "adaptive_workout", "adaptive_today"]
