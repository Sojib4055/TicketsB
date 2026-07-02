from __future__ import annotations

import time
from collections.abc import Sequence

from src.models import AvailabilityStatus, MonitorTarget
from src.monitoring.belief import estimate_drop_probability


class AdaptiveScheduler:
    def __init__(self, targets: Sequence[MonitorTarget], history_events: list[dict] | None = None) -> None:
        if not targets:
            raise ValueError("At least one monitor target is required")
        self.targets = list(targets)
        self.history_events = history_events or []
        self._last_polled: dict[str, float] = {}

    def next_target(self) -> MonitorTarget:
        now = time.monotonic()
        return min(self.targets, key=lambda target: self._next_due_at(target, now))

    def record_status(self, target_id: str, status: AvailabilityStatus) -> None:
        target = self._target_by_id(target_id)
        target.last_seen_status = status.state
        if status.state == "sold_out":
            target.consecutive_sold_out += 1
        else:
            target.consecutive_sold_out = 0
        target.belief_score = estimate_drop_probability(target, status, self.history_events)
        self._last_polled[target.id] = time.monotonic()

    def recommended_delay(self, target: MonitorTarget, status: AvailabilityStatus | None = None) -> int:
        if status is not None and status.state in {"queue", "available"}:
            return target.poll_min_seconds

        belief = target.belief_score
        span = max(target.poll_max_seconds - target.poll_min_seconds, 0)
        delay = round(target.poll_max_seconds - (span * belief))
        return max(target.poll_min_seconds, min(delay, target.poll_max_seconds))

    def _next_due_at(self, target: MonitorTarget, now: float) -> float:
        last_polled = self._last_polled.get(target.id)
        if last_polled is None:
            return now
        return last_polled + self.recommended_delay(target)

    def _target_by_id(self, target_id: str) -> MonitorTarget:
        for target in self.targets:
            if target.id == target_id:
                return target
        raise KeyError(f"Unknown monitor target: {target_id}")
