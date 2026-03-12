from __future__ import annotations

from dataclasses import dataclass

from src.config import settings


@dataclass(slots=True)
class Offer:
    title: str
    section: str
    quantity: int
    total_usd: float
    source_text: str = ""


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate_offer(offer: Offer) -> PolicyDecision:
    if offer.quantity > settings.max_tickets:
        return PolicyDecision(False, f"Ticket quantity exceeds max_tickets={settings.max_tickets}")

    if offer.total_usd > settings.max_total_usd:
        return PolicyDecision(False, f"Total cost exceeds max_total_usd={settings.max_total_usd}")

    text = f"{offer.title} {offer.section} {offer.source_text}".lower()
    for banned in settings.avoid_keywords_list:
        if banned in text:
            return PolicyDecision(False, f"Offer contains blocked keyword: {banned}")

    return PolicyDecision(True, "Offer satisfies policy")
