from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AvailabilityStatus:
    state: str
    raw_text: str
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedOffer:
    title: str
    section: str
    quantity: int
    total_usd: float
    unit_price_usd: float | None = None
    available_seats: int | None = None
    currency: str = "PRICE"
    departure_time: str | None = None
    arrival_time: str | None = None
    duration: str | None = None
    service_class: str | None = None
    booking_url: str = ""
    payment_url: str = ""
    booking_ref: str = ""
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    source_text: str = ""


@dataclass(slots=True)
class Offer:
    title: str
    section: str
    quantity: int
    total_usd: float
    available_seats: int | None = None
    currency: str = "PRICE"
    departure_time: str | None = None
    arrival_time: str | None = None
    duration: str | None = None
    service_class: str | None = None
    booking_url: str = ""
    payment_url: str = ""
    booking_ref: str = ""
    target_origin: str = ""
    target_destination: str = ""
    source_text: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    score: int = 0
    rank_reason: str = ""
    hard_blocks: list[str] = field(default_factory=list)
    soft_penalties: list[str] = field(default_factory=list)
    preference_matches: list[str] = field(default_factory=list)
    expiry_risk: str = "unknown"


@dataclass(slots=True)
class MonitorTarget:
    id: str
    url: str
    label: str = ""
    site_type: str = "generic"
    route_or_event: str = ""
    priority: float = 1.0
    poll_min_seconds: int = 10
    poll_max_seconds: int = 300
    last_seen_status: str = "unknown"
    belief_score: float = 0.1
    consecutive_sold_out: int = 0


@dataclass(slots=True)
class TripRequest:
    from_city: str
    to_city: str
    journey_date: str
    preferred_departure_start: str = ""
    preferred_departure_end: str = ""
    max_total_price: float = 2000.0
    currency: str = "BDT"
    seat_count: int = 1
    preferred_operators: list[str] = field(default_factory=list)
    avoid_operators: list[str] = field(default_factory=list)
    avoid_night_buses: bool = False
    monitor_days_before: int = 10
    seat_preference: str = ""
    auto_purchase_requested: bool = False
    created_at: str = ""


@dataclass(slots=True)
class TripSchedule:
    journey_date: str
    monitoring_start_date: str
    today: str
    days_until_journey: int
    days_until_monitoring_start: int
    should_monitor: bool
    message: str


@dataclass(slots=True)
class HandoffBrief:
    reason: str
    target: str
    found: str
    policy_result: str
    bot_action: str
    suggested_next_action: str
    expiry_risk: str = "unknown"
    details: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> str:
        lines = [
            "HUMAN HANDOFF REQUIRED",
            f"Reason: {self.reason}",
            f"Target: {self.target}",
            f"Found: {self.found}",
            f"Policy result: {self.policy_result}",
            f"Bot action: {self.bot_action}",
            f"Suggested next action: {self.suggested_next_action}",
            f"Expiry risk: {self.expiry_risk}",
        ]
        for key, value in self.details.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
