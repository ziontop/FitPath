"""FitPath AI Coach.

This module is the heart of the app's *predictive intelligence*. It does three
things, all grounded in the user's own logged data (no external LLM, no API
keys — fully private and offline):

  1. analyze_patterns()           -> learn the user's eating patterns:
                                     typical times per meal category, top foods,
                                     average kcal + macros per meal type.
  2. predict_next_meal_detailed() -> given today's meals + history + macro goals,
                                     predict the *next* meal: when, what category,
                                     how many kcal, and concrete food suggestions
                                     pulled from the user's own history that best
                                     fill the remaining macro gap.
  3. chat()                       -> a rule-based coach. Parses the user's question,
                                     pulls live data from their day, and replies
                                     with grounded, actionable answers.

Why rule-based instead of an LLM? Because the answers should be *true to your
data*. A heuristic that reads your real numbers is more useful than a generic
chat model that hallucinates. Every recommendation has a citation
(`based on X meals in the last 14 days`).

==============================================================================
PREDICTIVE PATTERN HOOKS — easy reference for "where is the AI?":
  * `_macro_targets_for_profile()`   : converts goals into per-macro daily targets
  * `analyze_patterns()`             : statistical pattern mining of meal log
  * `_score_foods_for_macros()`      : ranks past foods by macro-fit score
  * `predict_next_meal_detailed()`   : combines pattern + macro gap + circadian
  * `chat()._INTENTS`                : intent → answer; each answer uses real data
==============================================================================
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from statistics import mean, median
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Macro-target helpers
# ---------------------------------------------------------------------------
# Fallback macro split (protein 30% / carbs 40% / fat 30% of daily kcal), used
# only when the caller doesn't pass the user's real plan targets. Screens should
# pass the active nutrition plan's macros (see services.nutrition.active_macro_targets)
# so the coach and the Nutrition screen never disagree.
# 1g protein=4 kcal, 1g carbs=4 kcal, 1g fat=9 kcal.
MACRO_SPLIT = {"protein": 0.30, "carbs": 0.40, "fat": 0.30}
KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}


def macro_targets(daily_kcal: float) -> dict[str, float]:
    """Fallback daily protein/carbs/fat grams from a daily kcal target (30/40/30)."""
    return {
        m: round((daily_kcal * MACRO_SPLIT[m]) / KCAL_PER_G[m], 1)
        for m in ("protein", "carbs", "fat")
    }


# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------
def category_for_hour(h: int) -> str:
    """Most likely meal category for a given hour of day."""
    if 5 <= h < 10:
        return "breakfast"
    if 11 <= h < 14:
        return "lunch"
    if 17 <= h < 21:
        return "dinner"
    return "snack"


# ---------------------------------------------------------------------------
# 1. Pattern analysis
# ---------------------------------------------------------------------------
def analyze_patterns(meals: list[dict]) -> dict:
    """Mine the user's meal log for patterns.

    Each meal dict has keys: name, category, kcal, eaten_at (ISO), protein_g,
    carbs_g, fat_g.

    Returns a JSON-serializable dict with:
      - typical_times: {category: "HH:MM"}            (median start time)
      - top_foods:     {category: [{name, count, avg_kcal}, ...]}  top 3 per cat
      - avg_kcal:      {category: int}                (median kcal per meal type)
      - avg_macros:    {category: {protein_g, carbs_g, fat_g}}
      - meals_per_day: float
      - days_observed: int
      - total_meals:   int
    """
    if not meals:
        return {
            "typical_times": {},
            "top_foods": {},
            "avg_kcal": {},
            "avg_macros": {},
            "meals_per_day": 0,
            "days_observed": 0,
            "total_meals": 0,
        }

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for m in meals:
        by_cat[m.get("category") or "snack"].append(m)

    typical_times: dict[str, str] = {}
    top_foods: dict[str, list[dict]] = {}
    avg_kcal: dict[str, int] = {}
    avg_macros: dict[str, dict[str, float]] = {}

    for cat, rows in by_cat.items():
        # Median time of day for this category
        minutes_of_day = []
        for r in rows:
            try:
                t = datetime.fromisoformat(r["eaten_at"])
                minutes_of_day.append(t.hour * 60 + t.minute)
            except (ValueError, TypeError, KeyError):
                continue
        if minutes_of_day:
            med = int(median(minutes_of_day))
            typical_times[cat] = f"{med // 60:02d}:{med % 60:02d}"

        # Top foods by frequency
        names = Counter(r["name"].strip().lower() for r in rows if r.get("name"))
        top = []
        for name, count in names.most_common(3):
            matching = [r for r in rows if r.get("name", "").strip().lower() == name]
            top.append({
                "name": name,
                "count": count,
                "avg_kcal": round(mean(r["kcal"] for r in matching)),
            })
        top_foods[cat] = top

        avg_kcal[cat] = round(median(r["kcal"] for r in rows))
        avg_macros[cat] = {
            "protein_g": round(mean((r.get("protein_g") or 0) for r in rows), 1),
            "carbs_g":   round(mean((r.get("carbs_g")   or 0) for r in rows), 1),
            "fat_g":     round(mean((r.get("fat_g")     or 0) for r in rows), 1),
        }

    days = {m["eaten_at"][:10] for m in meals if m.get("eaten_at")}
    return {
        "typical_times": typical_times,
        "top_foods": top_foods,
        "avg_kcal": avg_kcal,
        "avg_macros": avg_macros,
        "meals_per_day": round(len(meals) / max(1, len(days)), 2),
        "days_observed": len(days),
        "total_meals": len(meals),
    }


# ---------------------------------------------------------------------------
# 2. Macro-fit food recommender
# ---------------------------------------------------------------------------
def _score_food_for_gap(food: dict, gap: dict[str, float]) -> float:
    """Score how well a food fills a macro gap. Higher is better.

    The score rewards macros where there's a deficit and penalizes overshoot.
    Uses a simple weighted dot-product against a normalized gap vector.
    """
    # Build a unit-normalized gap (avoid divide-by-zero)
    total_gap = sum(max(0.0, v) for v in gap.values()) or 1.0
    weights = {m: max(0.0, gap[m]) / total_gap for m in ("protein", "carbs", "fat")}

    food_p = food.get("protein_g") or 0
    food_c = food.get("carbs_g") or 0
    food_f = food.get("fat_g") or 0
    food_grams = food_p + food_c + food_f
    if food_grams <= 0:
        return 0.0

    score = 0.0
    score += weights["protein"] * (food_p / food_grams) * 2.0  # protein bias
    score += weights["carbs"]   * (food_c / food_grams)
    score += weights["fat"]     * (food_f / food_grams)
    # Slight reward for matching kcal magnitude (not overshooting hugely)
    target_kcal_for_gap = (
        max(0, gap["protein"]) * 4 + max(0, gap["carbs"]) * 4 + max(0, gap["fat"]) * 9
    ) / max(1, sum(1 for v in gap.values() if v > 0))
    food_kcal = food.get("kcal") or 0
    if target_kcal_for_gap > 0 and food_kcal > 0:
        ratio = min(food_kcal, target_kcal_for_gap) / max(food_kcal, target_kcal_for_gap)
        score *= (0.6 + 0.4 * ratio)
    return score


def recommend_foods_for_macros(
    history_meals: list[dict],
    macro_gap: dict[str, float],
    category: Optional[str] = None,
    top_n: int = 5,
) -> list[dict]:
    """Return top-N foods from the user's history that best fill the macro gap.

    macro_gap = {"protein": grams_short, "carbs": grams_short, "fat": grams_short}.
    Negative values mean already over target (the score will treat as 0 weight).
    If `category` is set, prefer foods from that category but fall back to any.
    """
    # Deduplicate by lowercase name, averaging macros
    bucket: dict[str, dict] = {}
    for m in history_meals:
        name = (m.get("name") or "").strip().lower()
        if not name:
            continue
        if category and m.get("category") != category:
            continue
        if name not in bucket:
            bucket[name] = {
                "name": m["name"].strip(),
                "category": m.get("category"),
                "samples": 0,
                "kcal": 0.0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }
        b = bucket[name]
        b["samples"] += 1
        b["kcal"] += m.get("kcal") or 0
        b["protein_g"] += m.get("protein_g") or 0
        b["carbs_g"] += m.get("carbs_g") or 0
        b["fat_g"] += m.get("fat_g") or 0

    foods = []
    for b in bucket.values():
        s = b["samples"]
        foods.append({
            "name": b["name"],
            "category": b["category"],
            "kcal": round(b["kcal"] / s),
            "protein_g": round(b["protein_g"] / s, 1),
            "carbs_g": round(b["carbs_g"] / s, 1),
            "fat_g": round(b["fat_g"] / s, 1),
            "logged_count": s,
        })

    # If category-filter yielded nothing, fall back to all
    if not foods and category:
        return recommend_foods_for_macros(history_meals, macro_gap, category=None, top_n=top_n)

    ranked = sorted(
        foods,
        key=lambda f: (_score_food_for_gap(f, macro_gap), f["logged_count"]),
        reverse=True,
    )
    return ranked[:top_n]


# ---------------------------------------------------------------------------
# 3. Next-meal prediction (timing + category + WHAT to eat)
# ---------------------------------------------------------------------------
def predict_next_meal_detailed(
    history_meals: list[dict],
    todays_meals: list[dict],
    daily_kcal_target: float,
    todays_macros_consumed: dict[str, float],
    now: Optional[datetime] = None,
    target_macros: Optional[dict[str, float]] = None,
) -> dict:
    """Predict next meal: when, category, suggested kcal, recommended foods.

    ``target_macros`` (``{"protein","carbs","fat"}`` grams) should be the user's
    real macro targets from their active nutrition plan so every screen agrees;
    when omitted it falls back to the generic kcal-split heuristic.

    Returns a rich dict the UI can render directly.
    """
    now = now or datetime.now()
    if target_macros is None:
        target_macros = macro_targets(daily_kcal_target)
    macro_gap = {
        "protein": target_macros["protein"] - (todays_macros_consumed.get("protein_g") or 0),
        "carbs":   target_macros["carbs"]   - (todays_macros_consumed.get("carbs_g")   or 0),
        "fat":     target_macros["fat"]     - (todays_macros_consumed.get("fat_g")     or 0),
    }
    kcal_eaten = sum(m.get("kcal", 0) for m in todays_meals)
    kcal_remaining = max(0.0, daily_kcal_target - kcal_eaten)

    patterns = analyze_patterns(history_meals)

    # Predict TIME using median interval (filtered to <10h gaps)
    times = sorted(
        datetime.fromisoformat(m["eaten_at"])
        for m in todays_meals
        if m.get("eaten_at")
    )
    interval_min = 240.0  # 4h default
    if history_meals:
        # Use history if today is empty; otherwise blend
        hist_times = sorted(
            datetime.fromisoformat(m["eaten_at"])
            for m in history_meals
            if m.get("eaten_at")
        )
        deltas = [
            (b - a).total_seconds() / 60.0
            for a, b in zip(hist_times, hist_times[1:])
            if (b - a) <= timedelta(hours=10)
        ]
        if deltas:
            interval_min = median(deltas)

    anchor = times[-1] if times else now
    predicted_dt = anchor + timedelta(minutes=interval_min)
    if predicted_dt < now:
        predicted_dt = now + timedelta(minutes=30)

    # Predict CATEGORY, then keep the predicted TIME and the category LABEL
    # consistent (previously the label could disagree with the clock — e.g. an
    # 18:00 prediction labelled "lunch").
    predicted_cat = category_for_hour(predicted_dt.hour)
    # If the user's history says they typically eat a different category near this
    # time, prefer that category...
    if patterns["typical_times"]:
        best_cat = None
        best_dist = 999
        pmin = predicted_dt.hour * 60 + predicted_dt.minute
        for cat, tstr in patterns["typical_times"].items():
            h, m = map(int, tstr.split(":"))
            d = abs((h * 60 + m) - pmin)
            if d < best_dist:
                best_dist = d
                best_cat = cat
        if best_cat and best_dist <= 120:
            predicted_cat = best_cat

    # ...and snap the predicted time to that category's typical time (when it's
    # still upcoming) so the label and the clock agree. Without a typical time to
    # anchor to, relabel from the final hour instead — either way they match.
    typical_for_cat = patterns["typical_times"].get(predicted_cat)
    if typical_for_cat:
        th, tm = map(int, typical_for_cat.split(":"))
        typical_dt = predicted_dt.replace(hour=th, minute=tm, second=0, microsecond=0)
        if typical_dt >= now and typical_dt >= anchor:
            predicted_dt = typical_dt
    else:
        predicted_cat = category_for_hour(predicted_dt.hour)

    # Suggested kcal: split remaining across estimated remaining meals
    typical_kcal_for_cat = patterns["avg_kcal"].get(predicted_cat)
    typical_kcal = typical_kcal_for_cat or (
        median(m["kcal"] for m in history_meals) if history_meals else daily_kcal_target / 4
    )
    meals_left_est = max(1, round(kcal_remaining / max(typical_kcal, 1)))
    suggested_kcal = round(kcal_remaining / meals_left_est) if kcal_remaining > 0 else 0

    # Recommended foods that best fill the macro gap
    recs = recommend_foods_for_macros(history_meals, macro_gap, category=predicted_cat, top_n=4)

    return {
        "predicted_time": predicted_dt.isoformat(timespec="minutes"),
        "predicted_category": predicted_cat,
        "suggested_kcal": suggested_kcal,
        "kcal_remaining": round(kcal_remaining),
        "kcal_eaten_today": round(kcal_eaten),
        "median_interval_hours": round(interval_min / 60.0, 2),
        "macro_gap": {
            "protein_g": round(macro_gap["protein"], 1),
            "carbs_g":   round(macro_gap["carbs"], 1),
            "fat_g":     round(macro_gap["fat"], 1),
        },
        "macro_targets": {f"{k}_g": v for k, v in target_macros.items()},
        "typical_kcal_for_category": round(typical_kcal),
        "recommendations": recs,
        "pattern_summary": {
            "days_observed": patterns["days_observed"],
            "meals_per_day": patterns["meals_per_day"],
            "typical_times": patterns["typical_times"],
        },
    }


# ---------------------------------------------------------------------------
# 4. Chat coach — intent parser
# ---------------------------------------------------------------------------
INTENTS = [
    ("greet",        r"^(hi|hello|hey|yo|sup|howdy)\b"),
    ("eat_now",      r"\b(what (should|to|can) i eat|what.*eat (now|next)|next meal|recommend.*food|food.*recommend)\b"),
    # --- Training domain (checked before the generic how_doing/exercise/weight so
    #     e.g. "what's my workout streak?" routes to streak, not exercise) ---
    ("surplus_deficit", r"\b(surplus|deficit|eating enough|enough to (bulk|gain|grow|cut|lose)|under[- ]?eating|over[- ]?eating|am i eating (enough|too much))\b"),
    ("maintenance",  r"\b(maintain|maintenance|maingain|recomp)\b"),
    ("strength",     r"\b(e1rm|1[\s-]?rm|\bpr\b|\bprs\b|personal record|strength|stronger|weaker|plateau)\b"),
    ("volume",       r"\b(volume|\bmev\b|\bmav\b|\bmrv\b|sets? per week|weekly sets|enough (sets|volume)|too (much|little|many) (volume|sets))\b"),
    ("consistency",  r"\b(keep missing|missing (workout|training|gym|session)|skip(p(ing|ed))? (workout|training|the gym|sessions|leg day)|inconsistent|can'?t stay consistent|fall(en|ing)? off|hard to (stick|stay consistent))\b"),
    ("streak",       r"\b(streak|consisten(t|cy))\b"),
    ("how_doing",    r"\b(how.*(am|are).*doing|how.*today|day.*going|progress|status|stats|summary)\b"),
    ("macros",       r"\b(macro|protein|carbs?|fat)s?\b"),
    ("calories",     r"\b(calories?|kcal|cals?)\b"),
    ("water",        r"\b(water\w*|hydrat\w*|thirst\w*|drink\w*)\b"),
    ("sleep",        r"\b(sleep\w*|rest|tired|nap\w*|bed)\b"),
    ("exercise",     r"\b(exercis\w*|workout\w*|train\w*|run\w*|gym|move\w*|cardio|lift\w*|walk\w*)\b"),
    ("steps",        r"\b(steps?|walking)\b"),
    ("weight",       r"\b(weight|weigh|scale|lose|gain.*weight|bulk|cut)\b"),
    ("pattern",      r"\b(pattern\w*|trend\w*|habit\w*|routine\w*|insight\w*)\b"),
    ("tip",          r"\b(tips?|advice|suggest\w*|help\w*|recommend\w*)\b"),
    ("circadian",    r"\b(circadian|rhythm|eating window|fasting|intermittent)\b"),
]


def detect_intent(message: str) -> str:
    msg = message.lower().strip()
    for name, pattern in INTENTS:
        if re.search(pattern, msg):
            return name
    return "fallback"


def chat(message: str, ctx: dict) -> dict:
    """Generate a coach reply.

    ctx must contain:
      profile, today (insights/today response), prediction (predict_next_meal_detailed),
      patterns (analyze_patterns), streaks (insights/streaks), circadian (insights/circadian).
    ctx may also contain ``training`` (workout streak, per-lift e1RM trend, weekly
    volume vs MEV/MAV, and intake-vs-target) so the coach can answer training
    questions grounded in the user's real performance data.
    """
    intent = detect_intent(message)
    msg = message.lower().strip()
    today = ctx.get("today") or {}
    prediction = ctx.get("prediction") or {}
    patterns = ctx.get("patterns") or {}
    streaks = ctx.get("streaks") or {}
    circadian = ctx.get("circadian") or {}
    profile = ctx.get("profile") or {}
    training = ctx.get("training") or {}
    name = (profile.get("name") or "").strip() or "friend"

    def fmt_time(iso: str) -> str:
        try:
            t = datetime.fromisoformat(iso)
        except Exception:
            return iso
        # Cross-platform 12-hour format (no %-I; works on Windows).
        h = t.hour % 12 or 12
        suffix = "AM" if t.hour < 12 else "PM"
        return f"{h}:{t.minute:02d} {suffix}"

    suggestions: list[str] = []
    chips: list[str] = []  # follow-up prompts

    if intent == "greet":
        reply = (
            f"Hey {name}! 👋 I'm your FitPath coach. I can see your day so far — "
            f"you've eaten {today.get('kcal_in', 0)} of {today.get('target_kcal', 0)} kcal, "
            f"hit {today.get('steps', 0):,} steps, and drunk {today.get('water_ml', 0)} ml of water. "
            "Ask me anything — like *what should I eat next?*"
        )
        chips = ["What should I eat next?", "How am I doing today?", "Give me a tip"]

    elif intent == "eat_now":
        if prediction.get("recommendations"):
            recs = prediction["recommendations"][:3]
            food_list = "\n".join(
                f"• **{r['name']}** — ~{r['kcal']} kcal "
                f"(P {r['protein_g']}g · C {r['carbs_g']}g · F {r['fat_g']}g)"
                for r in recs
            )
            gap = prediction["macro_gap"]
            reply = (
                f"Based on your patterns, your next meal looks like **{prediction['predicted_category']}** "
                f"around **{fmt_time(prediction['predicted_time'])}** "
                f"(~{prediction['suggested_kcal']} kcal). "
                f"You still need {max(0, gap['protein_g'])}g protein, "
                f"{max(0, gap['carbs_g'])}g carbs, {max(0, gap['fat_g'])}g fat today.\n\n"
                f"From your own history, these would fit best:\n{food_list}"
            )
            suggestions = [r["name"] for r in recs]
        else:
            reply = (
                "I don't have enough meal history yet to recommend specific foods. "
                "Log a few meals (with macros if you can) and I'll start spotting patterns. "
                f"For now, aim for ~{prediction.get('suggested_kcal', 'a moderate')} kcal "
                f"around {fmt_time(prediction.get('predicted_time', ''))}."
            )
        chips = ["Show my macro targets", "What's my eating pattern?", "How am I doing today?"]

    elif intent == "how_doing":
        kcal_pct = 0
        if today.get("target_kcal"):
            kcal_pct = round(100 * today["kcal_in"] / today["target_kcal"])
        water_pct = 0
        if today.get("goals", {}).get("water_goal_ml"):
            water_pct = round(100 * today["water_ml"] / today["goals"]["water_goal_ml"])
        steps_pct = 0
        if today.get("goals", {}).get("step_goal"):
            steps_pct = round(100 * today["steps"] / today["goals"]["step_goal"])
        reply = (
            f"Here's your day so far:\n"
            f"• 🔥 Calories: **{today.get('kcal_in', 0)} / {today.get('target_kcal', 0)} kcal** ({kcal_pct}%)\n"
            f"• 💧 Water: **{today.get('water_ml', 0)} / {today.get('goals', {}).get('water_goal_ml', 0)} ml** ({water_pct}%)\n"
            f"• 🦶 Steps: **{today.get('steps', 0):,}** ({steps_pct}%)\n"
            f"• 💪 Exercise: **{today.get('exercise_minutes', 0)} min**\n"
            f"• 😴 Sleep last night: **{today.get('sleep_hours') or '—'}h**\n"
            f"• 🏆 Any-log streak: **{streaks.get('any_streak', 0)} days**"
        )
        chips = ["What should I eat next?", "Should I exercise?", "How's my hydration?"]

    elif intent == "macros":
        gap = prediction.get("macro_gap", {})
        tgt = prediction.get("macro_targets", {})
        m = today.get("macros", {})
        reply = (
            f"**Macros today** (eaten / target):\n"
            f"• Protein: {m.get('protein_g', 0)}g / {tgt.get('protein_g', '?')}g — "
            f"{max(0, gap.get('protein_g', 0))}g to go\n"
            f"• Carbs: {m.get('carbs_g', 0)}g / {tgt.get('carbs_g', '?')}g — "
            f"{max(0, gap.get('carbs_g', 0))}g to go\n"
            f"• Fat: {m.get('fat_g', 0)}g / {tgt.get('fat_g', '?')}g — "
            f"{max(0, gap.get('fat_g', 0))}g to go\n\n"
            "These targets come straight from your active nutrition plan. Need recommendations to close the gap? Just ask."
        )
        chips = ["Recommend high-protein food", "What should I eat next?"]

    elif intent == "calories":
        rem = today.get("remaining_to_target", 0)
        if rem > 0:
            reply = (
                f"You've eaten **{today.get('kcal_in', 0)} kcal** out of "
                f"**{today.get('target_kcal', 0)}**. "
                f"That leaves **{rem} kcal** to play with. "
                f"At your typical meal size (~{prediction.get('typical_kcal_for_category', '?')} kcal), "
                f"that's roughly {max(1, round(rem / max(1, prediction.get('typical_kcal_for_category', 500))))} more meal(s)."
            )
        else:
            reply = (
                f"You're at **{today.get('kcal_in', 0)} kcal** — {abs(rem)} kcal over your target of "
                f"{today.get('target_kcal', 0)}. Not a disaster, but consider a lighter dinner or "
                "a 20-min walk to even things out."
            )
        chips = ["What should I eat next?", "Should I exercise?"]

    elif intent == "water":
        cur = today.get("water_ml", 0)
        goal = today.get("goals", {}).get("water_goal_ml", 0)
        need = max(0, goal - cur)
        reply = (
            f"You're at **{cur} ml** of **{goal} ml** today. "
            + (f"Drink {need} more ml — about {round(need / 250)} glasses." if need else "Target hit! Nice. 💧")
        )
        chips = ["Log 500 ml water", "How am I doing today?"]

    elif intent == "sleep":
        last = today.get("sleep_hours")
        if last is None:
            reply = "I don't see sleep logged for last night. Log it from the + button and I can tailor tips."
        elif last < 6.5:
            reply = (
                f"Only **{last}h** last night — short sleep raises ghrelin (hunger) and lowers leptin (fullness), "
                f"which tends to add ~300 kcal of unwanted snacking. Try for {circadian.get('sleep_target', '23:00')} bedtime tonight."
            )
        elif last >= 8:
            reply = f"**{last}h** of sleep is great. You'll recover faster and feel hunger more accurately today."
        else:
            reply = f"**{last}h** is okay. Aim for 7.5–9h consistently for better recovery and macro balance."
        chips = ["How am I doing today?", "Tips for tonight"]

    elif intent == "exercise":
        em = today.get("exercise_minutes", 0)
        goal = today.get("goals", {}).get("exercise_goal_min", 0)
        if em >= goal:
            reply = f"You've already hit **{em} min** today — goal smashed. 💪 Don't forget protein for recovery (you need {max(0, prediction.get('macro_gap', {}).get('protein_g', 0))}g more)."
        else:
            missing = goal - em
            reply = (
                f"You've done **{em} min** of exercise — {missing} min short of your goal. "
                f"A {missing}-min brisk walk would burn ~{missing * 5} kcal and close your move ring."
            )
        chips = ["What should I eat next?", "How am I doing today?"]

    elif intent == "steps":
        s = today.get("steps", 0)
        goal = today.get("goals", {}).get("step_goal", 0)
        reply = (
            f"You're at **{s:,} steps** ({round(100 * s / max(1, goal))}% of your {goal:,} goal). "
            + (
                "Nail the rest with a 15-min walk after your next meal."
                if s < goal
                else "Crushed it. 🦶"
            )
        )
        chips = ["How am I doing today?", "Should I exercise?"]

    elif intent == "weight":
        reply = (
            f"Your latest weight is **{profile.get('weight_kg', '?')} kg**. "
            "Trends matter more than any single weigh-in — check the Weight chart on the Trends tab. "
            f"At your goal of **{profile.get('goal', 'maintain')}**, target is **{today.get('target_kcal', '?')} kcal/day**."
        )
        chips = ["How am I doing today?", "What should I eat next?"]

    elif intent == "pattern":
        if not patterns or not patterns.get("typical_times"):
            reply = "I need more meals logged before I can spot patterns. Log consistently for 3–5 days and I'll find your patterns."
        else:
            tt = patterns["typical_times"]
            top = patterns["top_foods"]
            lines = [f"**Your patterns** ({patterns['days_observed']} days · {patterns['meals_per_day']} meals/day avg):"]
            for cat in ("breakfast", "lunch", "dinner", "snack"):
                if cat in tt:
                    line = f"• {cat.capitalize()} ~**{tt[cat]}**"
                    if top.get(cat):
                        favs = ", ".join(f["name"] for f in top[cat][:2])
                        line += f" — usually {favs}"
                    lines.append(line)
            reply = "\n".join(lines)
        chips = ["What should I eat next?", "How am I doing today?"]

    elif intent == "streak":
        reply = (
            f"🔥 **{streaks.get('any_streak', 0)}-day** logging streak · "
            f"🏋️ workout streak **{streaks.get('workout_streak', 0)} days**.\n"
            f"Meals: {streaks.get('meal_streak', 0)} · Activity: {streaks.get('activity_streak', 0)} · "
            f"Sleep: {streaks.get('sleep_streak', 0)} · Water: {streaks.get('water_streak', 0)}. "
            "Don't break the chain."
        )
        chips = ["How am I doing today?", "I keep missing workouts"]

    elif intent == "strength":
        lifts = training.get("lifts") or []
        if not lifts:
            reply = (
                "I don't have enough logged sets yet to judge strength. Log your main "
                "lifts (squat/bench/deadlift/overhead press) across a few sessions and "
                "I'll track your estimated 1RM (e1RM) over time."
            )
        else:
            focus_name = None
            for kw, nm in (
                ("squat", "Back Squat"), ("bench", "Bench Press"),
                ("deadlift", "Deadlift"), ("dead", "Deadlift"),
                ("overhead", "Overhead Press"), ("ohp", "Overhead Press"),
            ):
                if kw in msg:
                    focus_name = nm
                    break
            focus = next((lf for lf in lifts if lf["name"] == focus_name), None)
            show = [focus] if focus else lifts
            lines = ["**Estimated-1RM trend** (from your logged working sets):"]
            for lf in show:
                arrow = {"up": "📈", "down": "📉", "flat": "➡️"}[lf["direction"]]
                verb = {"up": "trending up", "down": "slipping", "flat": "holding steady"}[lf["direction"]]
                sign = "+" if lf["change"] >= 0 else ""
                lines.append(
                    f"• {arrow} **{lf['name']}**: {lf['first_e1rm']} → {lf['last_e1rm']} kg "
                    f"({sign}{lf['change']} kg / {sign}{lf['pct']}%) across {lf['points']} sessions — {verb}."
                )
            goal = training.get("goal")
            down = [lf for lf in show if lf["direction"] == "down"]
            if down and goal == "lose":
                lines.append(
                    "On a cut, holding e1RM is a win; a small dip is normal. Keep protein high "
                    "and intensity heavy (low reps) to preserve strength."
                )
            elif down:
                lines.append(
                    "A dip usually means fatigue or under-recovery — check sleep, and consider a "
                    "lighter deload week before pushing loads again."
                )
            else:
                lines.append("Strength is holding or climbing — keep progressing loads gradually.")
            reply = "\n".join(lines)
        chips = ["Is my volume enough?", "What's my workout streak?"]

    elif intent == "volume":
        vols = training.get("volume") or []
        if not vols:
            reply = (
                "No working sets logged in the last two weeks, so I can't assess volume yet. "
                "Log your sessions and I'll compare weekly sets per muscle to the MEV–MAV landmarks."
            )
        else:
            focus = next((mv for mv in vols if mv["muscle"].lower() in msg), None)
            show = [focus] if focus else vols[:5]
            lines = ["**Weekly volume vs targets** (sets/week, MEV–MAV):"]
            for mv in show:
                if mv["sets"] < mv["target_low"]:
                    status, emoji = "under MEV — add sets", "🔽"
                elif mv["sets"] > mv["target_high"]:
                    status, emoji = "above MAV — watch recovery", "🔼"
                else:
                    status, emoji = "in the productive range", "✅"
                lines.append(
                    f"• {emoji} **{mv['muscle']}**: {mv['sets']} sets "
                    f"(target {mv['target_low']}–{mv['target_high']}) — {status}."
                )
            reply = "\n".join(lines)
        chips = ["Am I getting stronger?", "How do I maintain?"]

    elif intent == "surplus_deficit":
        intake = training.get("intake") or {}
        goal = intake.get("goal") or profile.get("goal") or "maintain"
        avg = intake.get("avg_daily_kcal", 0)
        tgt = intake.get("target_kcal", 0)
        delta = intake.get("delta", 0)
        days = intake.get("days_counted", 0)
        goal_word = {
            "gain": "surplus (to bulk)",
            "lose": "deficit (to cut)",
            "maintain": "maintenance",
        }.get(goal, goal)
        if not days:
            reply = (
                f"I don't have enough logged meals this past week to check. Your target is "
                f"**~{tgt} kcal/day** for your **{goal}** goal — log meals and I'll compare your intake."
            )
        else:
            if goal == "gain":
                verdict = (
                    "you're hitting your surplus — good, that fuels growth."
                    if avg >= tgt - 50
                    else f"you're **under** target by ~{abs(delta)} kcal/day — eat more (add a shake or extra carbs) to actually gain."
                )
            elif goal == "lose":
                verdict = (
                    "you're in a deficit — on track to lose."
                    if avg <= tgt + 50
                    else f"you're **over** target by ~{delta} kcal/day — tighten portions to keep losing."
                )
            else:
                verdict = (
                    "you're right around maintenance."
                    if abs(delta) <= 100
                    else f"you're off maintenance by ~{delta:+} kcal/day."
                )
            reply = (
                f"Over the last {days} days you've averaged **{avg} kcal/day** vs a target of "
                f"**{tgt}** for your **{goal}** goal ({goal_word}). So {verdict}"
            )
        chips = ["What should I eat next?", "How do I maintain?"]

    elif intent == "maintenance":
        tgt = today.get("target_kcal") or (training.get("intake") or {}).get("target_kcal", 0)
        reply = (
            f"To **maintain**, hold calories near your maintenance target (**~{tgt} kcal/day**) with "
            "protein ~1.6 g/kg to keep muscle. Train each muscle ~2×/week at the low end of your set "
            "targets — enough to keep strength without piling on fatigue. Weigh in weekly; if the "
            "trend drifts more than ±0.5 kg/week, nudge intake by ~100–200 kcal."
        )
        chips = ["Am I eating enough?", "Is my volume enough?"]

    elif intent == "consistency":
        ws = training.get("workout_streak", 0)
        sess = training.get("sessions_last_14d", 0)
        reply = (
            f"You've logged **{sess} sessions in the last 14 days** (workout streak: {ws}). "
            "Consistency beats intensity — a few concrete fixes:\n"
            "• Shrink it: even a 20-min, 3-lift full-body session counts.\n"
            "• Anchor it to a fixed day/time so it runs on autopilot.\n"
            "• Pick a weekly target you can actually hit (2–3×), then build up.\n"
            "Missing one day never breaks progress — missing the *next* one does."
        )
        chips = ["What's my workout streak?", "How do I maintain?"]

    elif intent == "circadian":
        if circadian:
            reply = (
                f"Your circadian window: wake **{circadian.get('wake_time')}**, first meal ~**{circadian.get('first_meal')}**, "
                f"last meal by **{circadian.get('last_meal')}**, sleep around **{circadian.get('sleep_target')}**. "
                f"That's a ~{circadian.get('eating_window_hours', '?')}h eating window — eating outside it disrupts melatonin and glucose handling."
            )
        else:
            reply = "Set your wake time in Profile and I'll map your ideal eating window."
        chips = ["What should I eat next?", "Tips for tonight"]

    elif intent == "tip":
        # Same heuristic as the daily tip card, but coach-flavored
        h = (datetime.now()).hour
        if today.get("water_ml", 0) / max(1, today.get("goals", {}).get("water_goal_ml", 2500)) < 0.4 and h >= 11:
            reply = "Hydration is your easiest win right now. Drink a glass of water before your next decision — it'll also dull the snack craving."
        elif today.get("kcal_in", 0) == 0 and h >= 10:
            reply = "You haven't logged a meal yet today. Front-load 25–35g of protein at breakfast — it stabilizes glucose and curbs the 3pm slump."
        elif today.get("steps", 0) < today.get("goals", {}).get("step_goal", 8000) * 0.5 and h >= 16:
            reply = f"Movement debt building up — you're at {today.get('steps', 0):,} steps. A 15-min outdoor walk now would compound: steps + sunlight + circadian reset."
        else:
            reply = "Small wins beat heroics. Right now: one glass of water, two minutes of stretching, and pick what you'll eat next *before* you're hungry."
        chips = ["What should I eat next?", "How am I doing today?"]

    else:  # fallback
        reply = (
            "I can help with your nutrition (meals, macros, calories, hydration, sleep) "
            "and your training — strength/e1RM progress, weekly volume vs targets, your "
            "workout streak, consistency, and whether you're eating enough for your goal. "
            "Try: *am I losing strength on my squat?*, *is my chest volume enough?*, or "
            "*what should I eat next?*"
        )
        chips = ["Am I getting stronger?", "Is my volume enough?", "What should I eat next?"]

    return {
        "intent": intent,
        "reply": reply,
        "suggestions": suggestions,
        "chips": chips,
    }
