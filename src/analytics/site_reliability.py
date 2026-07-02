from __future__ import annotations

from collections import defaultdict
from typing import Any


def summarize_site_reliability(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: {"polls": 0, "available": 0, "errors": 0})

    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        target = str(payload.get("target_id") or payload.get("url") or "default")
        event_type = event.get("event_type")

        if event_type == "planner_step":
            summary[target]["polls"] += 1
            if payload.get("status") == "available":
                summary[target]["available"] += 1
        elif event_type == "error":
            summary[target]["errors"] += 1

    return dict(summary)
