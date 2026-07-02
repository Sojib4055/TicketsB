from __future__ import annotations

import json
from typing import Any

from src.config import settings
from src.models import MonitorTarget


def load_monitor_targets() -> list[MonitorTarget]:
    if not settings.monitor_targets_json:
        return [
            MonitorTarget(
                id="default",
                url=settings.target_event_url,
                label="Default target",
                route_or_event=settings.target_event_url,
                poll_min_seconds=settings.fast_poll_interval_seconds,
                poll_max_seconds=settings.poll_interval_seconds,
            )
        ]

    try:
        raw_targets = json.loads(settings.monitor_targets_json)
    except json.JSONDecodeError as exc:
        raise ValueError("MONITOR_TARGETS_JSON must be a JSON list of target objects") from exc

    if not isinstance(raw_targets, list):
        raise ValueError("MONITOR_TARGETS_JSON must be a JSON list of target objects")

    targets: list[MonitorTarget] = []
    for index, raw in enumerate(raw_targets):
        if not isinstance(raw, dict):
            raise ValueError("Each monitor target must be a JSON object")
        targets.append(_coerce_target(raw, index))

    if not targets:
        raise ValueError("MONITOR_TARGETS_JSON did not contain any targets")
    return targets


def _coerce_target(raw: dict[str, Any], index: int) -> MonitorTarget:
    url = str(raw.get("url") or "").strip()
    if not url:
        raise ValueError(f"Monitor target at index {index} is missing url")

    target_id = str(raw.get("id") or f"target-{index + 1}").strip()
    return MonitorTarget(
        id=target_id,
        url=url,
        label=str(raw.get("label") or target_id),
        site_type=str(raw.get("site_type") or "generic"),
        route_or_event=str(raw.get("route_or_event") or raw.get("label") or url),
        priority=float(raw.get("priority") or 1.0),
        poll_min_seconds=int(raw.get("poll_min_seconds") or settings.fast_poll_interval_seconds),
        poll_max_seconds=int(raw.get("poll_max_seconds") or settings.poll_interval_seconds),
    )
