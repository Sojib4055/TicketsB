from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AvailabilityStatus:
    state: str
    raw_text: str


def parse_availability_text(text: str) -> AvailabilityStatus:
    lower = text.lower()

    if "captcha" in lower:
        return AvailabilityStatus("captcha_blocked", text)
    if "mfa" in lower or "verify your identity" in lower:
        return AvailabilityStatus("mfa_required", text)
    if "queue" in lower or "you are in line" in lower:
        return AvailabilityStatus("queue", text)
    if "sold out" in lower or "no tickets available" in lower:
        return AvailabilityStatus("sold_out", text)
    if "available" in lower or "find tickets" in lower or "tickets available" in lower:
        return AvailabilityStatus("available", text)

    return AvailabilityStatus("unknown", text)
