from __future__ import annotations

from datetime import datetime

from src.analytics.drop_patterns import active_hour_score
from src.models import AvailabilityStatus, MonitorTarget


def estimate_drop_probability(
    target: MonitorTarget,
    status: AvailabilityStatus | None = None,
    history_events: list[dict] | None = None,
    now: datetime | None = None,
) -> float:
    score = min(max(target.priority, 0.1), 5.0) * 0.08

    if status is not None:
        if status.state == "available":
            score += 0.75 * status.confidence
        elif status.state == "queue":
            score += 0.35
        elif status.state == "unknown":
            score += 0.12
        elif status.state == "sold_out":
            score -= min(target.consecutive_sold_out * 0.03, 0.25)
        elif status.state in {"captcha_blocked", "mfa_required"}:
            score += 0.2

    if history_events:
        current_hour = (now or datetime.now()).hour
        score += min(active_hour_score(history_events, current_hour), 0.25)

    return max(0.02, min(score, 0.98))
