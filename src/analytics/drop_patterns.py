from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def summarize_drop_windows(events: list[dict[str, Any]]) -> dict[str, dict[int, int]]:
    hours: Counter[int] = Counter()
    weekdays: Counter[int] = Counter()

    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if payload.get("status") != "available":
            continue

        ts = _parse_ts(event.get("ts"))
        if ts is None:
            continue
        hours[ts.hour] += 1
        weekdays[ts.weekday()] += 1

    return {
        "hour_of_day": dict(sorted(hours.items())),
        "weekday": dict(sorted(weekdays.items())),
    }


def active_hour_score(events: list[dict[str, Any]], hour: int) -> float:
    summary = summarize_drop_windows(events)
    hour_counts = summary["hour_of_day"]
    total = sum(hour_counts.values())
    if total == 0:
        return 0.0
    return hour_counts.get(hour, 0) / total


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
