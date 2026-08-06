"""Circadian-aware eating window suggestions.

Heuristic: align eating window with wake time. Most people benefit from
finishing dinner ~3h before sleep and starting breakfast 1-2h after waking.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta


def _parse_hhmm(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def eating_window(wake_time_hhmm: str, window_hours: int = 10) -> dict:
    """Suggest first/last meal times and tips for a given wake time."""
    wake = _parse_hhmm(wake_time_hhmm)
    today = datetime.now().date()
    wake_dt = datetime.combine(today, wake)

    first_meal = wake_dt + timedelta(hours=1, minutes=30)
    last_meal = first_meal + timedelta(hours=window_hours)
    sleep_target = last_meal + timedelta(hours=3)

    tips = [
        "Get 10-20 minutes of morning sunlight to anchor your circadian rhythm.",
        f"Aim for your first meal around {first_meal.strftime('%H:%M')} "
        f"(~1.5h after waking) once cortisol naturally rises.",
        f"Try to finish your last meal by {last_meal.strftime('%H:%M')} so "
        f"digestion isn't competing with sleep.",
        f"Target lights-out around {sleep_target.strftime('%H:%M')} for ~"
        f"{(wake_dt + timedelta(hours=24) - sleep_target).seconds // 3600}h sleep.",
        "Caffeine half-life is ~5-6h. Cut it 8-10h before bed.",
    ]
    return {
        "wake_time": wake_time_hhmm,
        "first_meal": first_meal.strftime("%H:%M"),
        "last_meal": last_meal.strftime("%H:%M"),
        "sleep_target": sleep_target.strftime("%H:%M"),
        "eating_window_hours": window_hours,
        "tips": tips,
    }
