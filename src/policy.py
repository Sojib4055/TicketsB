from __future__ import annotations

import re

from src.config import settings
from src.models import Offer, PolicyDecision


def evaluate_offer(offer: Offer) -> PolicyDecision:
    hard_blocks: list[str] = []
    if offer.total_usd <= 0:
        hard_blocks.append("Total cost must be greater than zero")

    if offer.quantity > settings.max_tickets:
        hard_blocks.append(f"Ticket quantity exceeds max_tickets={settings.max_tickets}")

    max_total_price = settings.effective_max_total_price
    currency = settings.normalized_price_currency
    if offer.total_usd > max_total_price:
        hard_blocks.append(f"Total cost exceeds MAX_TOTAL_PRICE={max_total_price} {currency}")

    text = f"{offer.title} {offer.section} {offer.source_text}".lower()
    for banned in settings.avoid_keywords_list:
        if banned in text:
            hard_blocks.append(f"Offer contains blocked keyword: {banned}")

    operator_lower = offer.title.lower()
    for avoided in settings.avoid_operators_list:
        if avoided in operator_lower:
            hard_blocks.append(f"Offer uses avoided operator: {avoided}")

    if hard_blocks:
        return PolicyDecision(
            allowed=False,
            reason="; ".join(hard_blocks),
            score=0,
            rank_reason="Blocked by hard policy constraints",
            hard_blocks=hard_blocks,
            expiry_risk=_expiry_risk(offer),
        )

    score, rank_reason, soft_penalties, preference_matches = _score_offer(offer)
    return PolicyDecision(
        allowed=True,
        reason="Offer satisfies policy",
        score=score,
        rank_reason=rank_reason,
        soft_penalties=soft_penalties,
        preference_matches=preference_matches,
        expiry_risk=_expiry_risk(offer),
    )


def rank_offers(offers: list[Offer]) -> list[tuple[Offer, PolicyDecision]]:
    decisions = [(offer, evaluate_offer(offer)) for offer in offers]
    return sorted(decisions, key=lambda item: (item[1].allowed, item[1].score), reverse=True)


def _score_offer(offer: Offer) -> tuple[int, str, list[str], list[str]]:
    score = 45
    reasons: list[str] = []
    soft_penalties: list[str] = []
    preference_matches: list[str] = []

    max_total_price = settings.effective_max_total_price
    if max_total_price > 0:
        price_headroom = max(max_total_price - offer.total_usd, 0) / max_total_price
        price_points = round(price_headroom * 25)
        score += price_points
        reasons.append(f"{price_points} price-headroom points")
        if price_points >= 15:
            preference_matches.append("strong price headroom")

    preferred_sections = [section.lower() for section in settings.preferred_sections_list]
    section_lower = offer.section.lower()
    if preferred_sections and any(section in section_lower for section in preferred_sections):
        score += 18
        reasons.append("preferred section match")
        preference_matches.append("preferred section")
    elif preferred_sections:
        score -= 8
        soft_penalties.append("Section is outside configured preferences")

    route_score, route_reason, route_penalty = _route_score(offer)
    score += route_score
    reasons.append(route_reason)
    if route_score >= 18:
        preference_matches.append("direct route match")
    if route_penalty:
        soft_penalties.append(route_penalty)

    operator_score, operator_reason, operator_penalty = _operator_score(offer)
    score += operator_score
    if operator_reason:
        reasons.append(operator_reason)
        preference_matches.append(operator_reason)
    if operator_penalty:
        soft_penalties.append(operator_penalty)

    time_score, time_reason, time_penalty = _departure_time_score(offer)
    score += time_score
    if time_reason:
        reasons.append(time_reason)
        preference_matches.append(time_reason)
    if time_penalty:
        soft_penalties.append(time_penalty)

    if offer.available_seats is not None:
        seat_points = _seat_quality_points(offer.available_seats)
        score += seat_points
        reasons.append(f"{seat_points} seat-quality points")
        if offer.quantity > 1 and offer.available_seats < offer.quantity:
            score -= 15
            soft_penalties.append("Available seat count is lower than requested quantity")
        if offer.available_seats <= 3:
            soft_penalties.append("Very low remaining seat count")
        elif offer.available_seats >= 10:
            preference_matches.append("comfortable seat availability")

    if offer.quantity == settings.max_tickets:
        score += 5
        reasons.append("matches configured ticket quantity cap")

    if offer.confidence:
        confidence_points = round(min(offer.confidence, 1.0) * 10)
        score += confidence_points
        reasons.append(f"{confidence_points} parser-confidence points")

    score = max(0, min(score, 100))
    rank_reason = "; ".join(reasons) if reasons else "No ranking preferences matched"
    return score, rank_reason, soft_penalties, preference_matches


def _route_score(offer: Offer) -> tuple[int, str, str | None]:
    origin = (offer.target_origin or settings.effective_target_origin).strip().lower()
    destination = (offer.target_destination or settings.effective_target_destination).strip().lower()
    route = offer.section.lower()
    if not origin or not destination:
        return 0, "route target unavailable", None

    if origin not in route or destination not in route:
        return -10, "route misses configured origin/destination", "Route does not clearly match target"

    stops = _route_stops(offer.section)
    if stops <= 2:
        return 22, "direct route match", None
    if stops <= 5:
        return 12, "near-direct route match", None
    return 3, "long route still reaches destination", "Long route has many intermediate stops"


def _route_stops(route: str) -> int:
    route_text = re.sub(r"(?i)^route:\s*", "", route)
    return len([part.strip() for part in route_text.split("-") if part.strip()])


def _operator_score(offer: Offer) -> tuple[int, str | None, str | None]:
    operator = offer.title.lower()
    preferred = settings.preferred_operators_list
    if not preferred:
        return 0, None, None
    if any(item in operator for item in preferred):
        return 14, "preferred operator match", None
    return -4, None, "Operator is outside configured preferences"


def _departure_time_score(offer: Offer) -> tuple[int, str | None, str | None]:
    minutes = _time_to_minutes(offer.departure_time)
    if minutes is None:
        return 0, None, "Departure time unavailable"

    if settings.avoid_night_buses and (minutes < 6 * 60 or minutes >= 22 * 60):
        return -10, None, "Night departure avoided by preference"

    start = _time_to_minutes(settings.preferred_departure_start)
    end = _time_to_minutes(settings.preferred_departure_end)
    if start is None or end is None:
        return 0, None, None

    in_window = start <= minutes <= end if start <= end else minutes >= start or minutes <= end
    if in_window:
        return 12, "preferred departure window", None
    return -6, None, "Departure outside preferred time window"


def _time_to_minutes(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"(?i)\s*(\d{1,2}):(\d{2})\s*(am|pm)?\s*", value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    period = match.group(3).lower() if match.group(3) else None
    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _seat_quality_points(seats: int) -> int:
    if seats <= 2:
        return 3
    if seats <= 5:
        return 6
    if seats <= 10:
        return 8
    return 10


def _expiry_risk(offer: Offer) -> str:
    if offer.available_seats is None:
        return "unknown"
    if offer.available_seats <= 2:
        return "high"
    if offer.available_seats <= 8:
        return "medium"
    return "low"
