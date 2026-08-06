"""Natural-language meal parser.

Turns a casual sentence like "had 2 eggs and a coffee for breakfast" into a
structured meal payload (category + kcal + macros) that can be one-tap logged.

Strategy (no external LLM — fully local + private):

  1. Tokenize the sentence and pull a category from keyword/time-of-day cues.
  2. Pull numeric quantities (digits, written numbers, fractions, "a/an").
  3. Match food terms against:
        a) the user's own meal history (rich, personalized vocabulary)
        b) a small builtin food table for the long tail
  4. Estimate kcal/macros = portion_count * per_unit_values.
  5. Return a structured payload + a confidence note so the UI can show
     "tweak before you log" affordances.

This is intentionally heuristic. The user always confirms before it persists,
so a fuzzy guess is fine — way better than typing the form from scratch.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Builtin nutrition table
# ---------------------------------------------------------------------------
# Values are per "natural unit" the user is likely to say
# ("an egg", "a slice of bread", "a cup of coffee"). Approximate — fine for
# a first pass since the user confirms before logging.
#
# Each entry: aliases -> { unit, kcal, p, c, f }
_FOODS: list[dict] = [
    {"aliases": ["egg", "eggs"],                              "unit": "egg",       "kcal":  78, "p":  6,  "c":  1,  "f":  5},
    {"aliases": ["bacon"],                                    "unit": "strip",     "kcal":  43, "p":  3,  "c":  0,  "f":  3},
    {"aliases": ["sausage"],                                  "unit": "sausage",   "kcal": 170, "p":  9,  "c":  1,  "f": 14},
    {"aliases": ["toast", "bread", "slice of bread"],         "unit": "slice",     "kcal":  80, "p":  3,  "c": 14,  "f":  1},
    {"aliases": ["bagel"],                                    "unit": "bagel",     "kcal": 277, "p": 11,  "c": 55,  "f":  2},
    {"aliases": ["croissant"],                                "unit": "croissant", "kcal": 230, "p":  5,  "c": 26,  "f": 12},
    {"aliases": ["pancake", "pancakes"],                      "unit": "pancake",   "kcal":  90, "p":  3,  "c": 15,  "f":  2},
    {"aliases": ["waffle", "waffles"],                        "unit": "waffle",    "kcal": 220, "p":  6,  "c": 25,  "f": 11},
    {"aliases": ["oatmeal", "oats", "porridge"],              "unit": "cup",       "kcal": 150, "p":  5,  "c": 27,  "f":  3},
    {"aliases": ["yogurt", "greek yogurt"],                   "unit": "cup",       "kcal": 150, "p": 15,  "c": 11,  "f":  4},
    {"aliases": ["banana"],                                   "unit": "banana",    "kcal": 105, "p":  1,  "c": 27,  "f":  0},
    {"aliases": ["apple"],                                    "unit": "apple",     "kcal":  95, "p":  0,  "c": 25,  "f":  0},
    {"aliases": ["orange"],                                   "unit": "orange",    "kcal":  62, "p":  1,  "c": 15,  "f":  0},
    {"aliases": ["berries", "blueberries", "strawberries"],   "unit": "cup",       "kcal":  85, "p":  1,  "c": 21,  "f":  0},
    {"aliases": ["coffee", "black coffee", "espresso"],       "unit": "cup",       "kcal":   5, "p":  0,  "c":  0,  "f":  0},
    {"aliases": ["latte"],                                    "unit": "cup",       "kcal": 190, "p":  9,  "c": 19,  "f":  7},
    {"aliases": ["tea"],                                      "unit": "cup",       "kcal":   2, "p":  0,  "c":  0,  "f":  0},
    {"aliases": ["smoothie", "protein shake"],                "unit": "shake",     "kcal": 250, "p": 25,  "c": 25,  "f":  6},
    {"aliases": ["sandwich"],                                 "unit": "sandwich",  "kcal": 350, "p": 18,  "c": 36,  "f": 14},
    {"aliases": ["burger", "cheeseburger", "hamburger"],      "unit": "burger",    "kcal": 540, "p": 25,  "c": 40,  "f": 30},
    {"aliases": ["pizza", "slice of pizza", "pizza slice"],   "unit": "slice",     "kcal": 285, "p": 12,  "c": 36,  "f": 10},
    {"aliases": ["salad"],                                    "unit": "bowl",      "kcal": 220, "p":  8,  "c": 18,  "f": 12},
    {"aliases": ["chicken", "grilled chicken", "chicken breast"], "unit": "serving","kcal": 230, "p": 35,  "c":  0,  "f":  9},
    {"aliases": ["steak", "beef"],                            "unit": "serving",   "kcal": 380, "p": 36,  "c":  0,  "f": 25},
    {"aliases": ["salmon"],                                   "unit": "fillet",    "kcal": 280, "p": 30,  "c":  0,  "f": 18},
    {"aliases": ["fish", "tilapia", "cod"],                   "unit": "fillet",    "kcal": 180, "p": 28,  "c":  0,  "f":  6},
    {"aliases": ["rice", "white rice", "brown rice"],         "unit": "cup",       "kcal": 215, "p":  5,  "c": 45,  "f":  2},
    {"aliases": ["pasta", "spaghetti", "noodles"],            "unit": "cup",       "kcal": 220, "p":  8,  "c": 43,  "f":  1},
    {"aliases": ["potato", "potatoes"],                       "unit": "potato",    "kcal": 160, "p":  4,  "c": 37,  "f":  0},
    {"aliases": ["fries", "french fries"],                    "unit": "serving",   "kcal": 365, "p":  4,  "c": 48,  "f": 17},
    {"aliases": ["broccoli", "vegetables", "veggies"],        "unit": "cup",       "kcal":  55, "p":  4,  "c": 11,  "f":  1},
    {"aliases": ["avocado"],                                  "unit": "avocado",   "kcal": 240, "p":  3,  "c": 13,  "f": 22},
    {"aliases": ["nuts", "almonds", "cashews", "peanuts"],    "unit": "handful",   "kcal": 170, "p":  6,  "c":  6,  "f": 14},
    {"aliases": ["chocolate", "candy", "snickers"],           "unit": "bar",       "kcal": 250, "p":  4,  "c": 33,  "f": 12},
    {"aliases": ["cookie", "cookies"],                        "unit": "cookie",    "kcal":  78, "p":  1,  "c": 10,  "f":  4},
    {"aliases": ["ice cream"],                                "unit": "scoop",     "kcal": 137, "p":  2,  "c": 16,  "f":  7},
    {"aliases": ["beer"],                                     "unit": "bottle",    "kcal": 153, "p":  2,  "c": 13,  "f":  0},
    {"aliases": ["wine"],                                     "unit": "glass",     "kcal": 125, "p":  0,  "c":  4,  "f":  0},
    {"aliases": ["soda", "coke", "pepsi", "sprite"],          "unit": "can",       "kcal": 140, "p":  0,  "c": 39,  "f":  0},
    {"aliases": ["juice", "orange juice"],                    "unit": "cup",       "kcal": 110, "p":  2,  "c": 26,  "f":  0},
    {"aliases": ["water"],                                    "unit": "cup",       "kcal":   0, "p":  0,  "c":  0,  "f":  0},
    {"aliases": ["protein bar"],                              "unit": "bar",       "kcal": 200, "p": 20,  "c": 22,  "f":  6},
    {"aliases": ["soup"],                                     "unit": "bowl",      "kcal": 180, "p":  8,  "c": 22,  "f":  6},
    {"aliases": ["burrito"],                                  "unit": "burrito",   "kcal": 600, "p": 26,  "c": 70,  "f": 23},
    {"aliases": ["taco", "tacos"],                            "unit": "taco",      "kcal": 170, "p":  8,  "c": 14,  "f":  9},
    {"aliases": ["sushi", "sushi roll"],                      "unit": "roll",      "kcal": 350, "p": 15,  "c": 55,  "f":  8},
    {"aliases": ["donut", "doughnut"],                        "unit": "donut",     "kcal": 260, "p":  4,  "c": 31,  "f": 14},
    {"aliases": ["muffin"],                                   "unit": "muffin",    "kcal": 340, "p":  6,  "c": 51,  "f": 14},
    {"aliases": ["cheese", "cheddar"],                        "unit": "slice",     "kcal": 113, "p":  7,  "c":  0,  "f":  9},
    {"aliases": ["butter"],                                   "unit": "tbsp",      "kcal": 102, "p":  0,  "c":  0,  "f": 12},
    {"aliases": ["peanut butter", "pb"],                      "unit": "tbsp",      "kcal":  94, "p":  4,  "c":  3,  "f":  8},
]


# ---------------------------------------------------------------------------
# Quantity parsing
# ---------------------------------------------------------------------------
_WORD_NUMS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "dozen": 12,
    "half": 0.5, "couple": 2, "few": 3, "several": 4,
}
_FRACTION = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\b")


def _split_clauses(text: str) -> list[str]:
    """Split on commas, ' and ', ' plus ', ' & ', ' with '."""
    parts = re.split(r"\s*(?:,| and | plus | with | & )\s*", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _extract_qty(clause: str) -> tuple[float, str]:
    """Return (qty, remaining_text)."""
    s = clause.strip().lower()
    # Strip filler verbs that sometimes survive splitting ("had 2 eggs")
    s = re.sub(r"^(?:i\s+)?(?:had|ate|just\s+ate|just\s+had|grabbed|made|got|drank)\s+", "", s)
    s = s.strip()

    # Fraction first: "1/2 bagel"
    m = _FRACTION.match(s)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        qty = num / max(den, 1)
        return qty, s[m.end():].strip()

    # Digit number
    m = _NUMBER.match(s)
    if m:
        qty = float(m.group(1))
        return qty, s[m.end():].strip()

    # Word number
    first, _, rest = s.partition(" ")
    if first in _WORD_NUMS:
        return float(_WORD_NUMS[first]), rest.strip()

    # Default 1
    return 1.0, s


def _match_food(text: str, user_vocab: list[dict]) -> Optional[dict]:
    """Find best matching food. Prefer longer matches.

    user_vocab: list of {name, kcal, p, c, f, count} from the user's history.
    """
    s = text.lower().strip()
    if not s:
        return None

    # Try user vocab first (personalized).
    best_user = None
    best_user_len = 0
    for food in user_vocab:
        name = food["name"].lower()
        if not name:
            continue
        if name in s or s in name:
            if len(name) > best_user_len:
                best_user = food
                best_user_len = len(name)
    if best_user:
        return {
            "name": best_user["name"],
            "kcal": best_user["kcal"],
            "p": best_user["p"],
            "c": best_user["c"],
            "f": best_user["f"],
            "unit": "serving",
            "source": "history",
        }

    # Fall back to builtin DB — longest-alias-wins to avoid "egg" matching "eggplant".
    best = None
    best_len = 0
    for food in _FOODS:
        for alias in food["aliases"]:
            if re.search(rf"\b{re.escape(alias)}\b", s):
                if len(alias) > best_len:
                    best_len = len(alias)
                    best = {
                        "name": alias,
                        "kcal": food["kcal"],
                        "p": food["p"],
                        "c": food["c"],
                        "f": food["f"],
                        "unit": food["unit"],
                        "source": "builtin",
                    }
    return best


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------
_CATEGORY_KEYWORDS = {
    "breakfast": ["breakfast", "brekkie", "morning meal"],
    "lunch":     ["lunch", "midday", "noon meal"],
    "dinner":    ["dinner", "supper", "evening meal"],
    "snack":     ["snack", "treat", "munchie", "munchies"],
}


def _detect_category(text: str, now: Optional[datetime] = None) -> str:
    s = text.lower()
    for cat, words in _CATEGORY_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", s) for w in words):
            return cat
    # Time-of-day fallback
    now = now or datetime.now()
    h = now.hour
    if   5 <= h < 11: return "breakfast"
    elif 11 <= h < 15: return "lunch"
    elif 15 <= h < 17: return "snack"
    elif 17 <= h < 22: return "dinner"
    return "snack"


# ---------------------------------------------------------------------------
# Build user vocab from meal history
# ---------------------------------------------------------------------------
def _build_user_vocab(history: Iterable[dict]) -> list[dict]:
    """Aggregate the user's logged meals into a per-name nutrition vocab.

    For each distinct meal name (lowercased), take the median-ish values from
    history. This becomes a personalized food DB the parser can match against.
    """
    by_name: dict[str, list[dict]] = {}
    for m in history:
        nm = (m.get("name") or "").strip()
        if not nm:
            continue
        by_name.setdefault(nm.lower(), []).append(m)

    vocab = []
    for nm_lower, rows in by_name.items():
        if len(rows) < 1:
            continue
        # Use first non-null name with original capitalization
        display_name = next((r["name"] for r in rows if r.get("name")), nm_lower)
        kcal = sum(r.get("kcal", 0) or 0 for r in rows) / len(rows)
        p = sum((r.get("protein_g") or 0) for r in rows) / len(rows)
        c = sum((r.get("carbs_g")   or 0) for r in rows) / len(rows)
        f = sum((r.get("fat_g")     or 0) for r in rows) / len(rows)
        vocab.append({
            "name": display_name,
            "kcal": round(kcal),
            "p": round(p, 1),
            "c": round(c, 1),
            "f": round(f, 1),
            "count": len(rows),
        })
    # Frequent first, so prefer "chicken bowl" you've logged 12 times over
    # "chicken bowl" you logged once.
    vocab.sort(key=lambda v: -v["count"])
    return vocab


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_meal(text: str, history: Iterable[dict] = (), now: Optional[datetime] = None) -> dict:
    """Parse a natural-language description into a structured meal payload.

    Returns:
        {
          "name": "2 eggs + toast",
          "category": "breakfast",
          "kcal": 236,
          "protein_g": 15,
          "carbs_g": 16,
          "fat_g": 11,
          "items": [{name, qty, unit, kcal, p, c, f, source}, ...],
          "unmatched": ["random thing"],
          "confidence": "high" | "medium" | "low",
          "note": "matched 2 of 3 items — tweak before logging if needed",
        }
    """
    raw = (text or "").strip()
    if not raw:
        return {
            "name": "", "category": _detect_category("", now),
            "kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0,
            "items": [], "unmatched": [], "confidence": "low",
            "note": "Type what you ate — e.g. '2 eggs and coffee for breakfast'.",
        }

    user_vocab = _build_user_vocab(history)
    category = _detect_category(raw, now)

    # Strip the category word so it doesn't fight food matching ("had pizza for dinner")
    cleaned = raw
    for words in _CATEGORY_KEYWORDS.values():
        for w in words:
            cleaned = re.sub(rf"\b(?:for|at)?\s*{re.escape(w)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:i\s+(?:had|ate|just\s+ate|just\s+had|grabbed|made)|log|track)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .,!?")

    clauses = _split_clauses(cleaned)
    items = []
    unmatched = []
    for clause in clauses:
        qty, remaining = _extract_qty(clause)
        food = _match_food(remaining or clause, user_vocab)
        if not food:
            unmatched.append(clause)
            continue
        items.append({
            "name": food["name"],
            "qty": qty,
            "unit": food.get("unit", "serving"),
            "kcal": round(food["kcal"] * qty),
            "p":    round(food["p"]    * qty, 1),
            "c":    round(food["c"]    * qty, 1),
            "f":    round(food["f"]    * qty, 1),
            "source": food.get("source", "history"),
        })

    total_kcal = sum(i["kcal"] for i in items)
    total_p = round(sum(i["p"] for i in items), 1)
    total_c = round(sum(i["c"] for i in items), 1)
    total_f = round(sum(i["f"] for i in items), 1)

    # Display name = brief summary
    if items:
        parts = []
        for i in items:
            qty = i["qty"]
            qty_str = ("½" if qty == 0.5 else
                       str(int(qty)) if qty == int(qty) else
                       f"{qty:g}")
            parts.append(f"{qty_str} {i['name']}")
        display = " + ".join(parts)
    else:
        display = raw[:80]

    matched = len(items)
    total = matched + len(unmatched)
    if matched == 0:
        conf = "low"
        note = "Couldn't recognize any foods — type the meal name + kcal manually."
    elif unmatched or any(i["source"] == "builtin" for i in items):
        conf = "medium"
        note = f"Matched {matched} of {total} item{'s' if total != 1 else ''} — tweak before logging if needed."
    else:
        conf = "high"
        note = f"Recognized from your meal history."

    return {
        "name": display,
        "category": category,
        "kcal": total_kcal,
        "protein_g": total_p,
        "carbs_g": total_c,
        "fat_g": total_f,
        "items": items,
        "unmatched": unmatched,
        "confidence": conf,
        "note": note,
    }
