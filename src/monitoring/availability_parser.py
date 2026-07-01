from __future__ import annotations

from dataclasses import dataclass
import re


SECTION_HINTS = (
    "lower bowl",
    "upper bowl",
    "floor",
    "mezzanine",
    "balcony",
    "club",
    "general admission",
    "ga",
    "route:",
    "non ac",
)


@dataclass(slots=True)
class AvailabilityStatus:
    state: str
    raw_text: str


@dataclass(slots=True)
class ParsedOffer:
    title: str
    section: str
    quantity: int
    total_usd: float
    unit_price_usd: float | None = None
    available_seats: int | None = None


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


def parse_offer_text(text: str) -> ParsedOffer | None:
    segments = _extract_segments(text)
    title = _parse_title(segments)
    section = _parse_section(text, segments) or "Unknown"
    quantity = _parse_quantity(text) or 1
    total_usd, unit_price_usd = _parse_pricing(text, quantity)
    available_seats = _parse_available_seats(text)

    if not title or total_usd is None:
        return None

    return ParsedOffer(
        title=title,
        section=section,
        quantity=quantity,
        total_usd=total_usd,
        unit_price_usd=unit_price_usd,
        available_seats=available_seats,
    )


def _extract_segments(text: str) -> list[str]:
    segments: list[str] = []
    for line in text.splitlines():
        for segment in line.split("|"):
            cleaned = _clean_snapshot_segment(segment)
            if cleaned:
                segments.append(cleaned)
    return segments


def _clean_snapshot_segment(segment: str) -> str:
    segment = re.sub(r"\[ref=[^\]]+\]", "", segment).strip()
    segment = segment.lstrip("- ").strip()

    quoted_match = re.search(r'"([^"]+)"', segment)
    if quoted_match:
        return quoted_match.group(1).strip()

    label_match = re.match(r"(?i)(?:text|heading|paragraph)\s*:\s*(.+)", segment)
    if label_match:
        return label_match.group(1).strip()

    return segment


def _parse_title(segments: list[str]) -> str | None:
    ignored_tokens = (
        "ticket",
        "available",
        "from $",
        "section",
        "quantity",
        "price",
        "checkout",
        "book ticket",
        "search",
        "filter",
        "reset",
        "discount",
        "boarding point",
        "dropping point",
        "cancellation policy",
        "amenities",
        "seat(s)",
        "depart",
        "arrive",
        "route:",
    )
    for segment in segments:
        lower = segment.lower()
        if any(token in lower for token in ignored_tokens):
            continue
        if _looks_like_price(segment) or _looks_like_time_or_date(segment):
            continue
        return segment[:200]
    return None


def _parse_section(text: str, segments: list[str]) -> str | None:
    explicit_match = re.search(r"(?i)\bsection\s*[:|-]\s*([^\n|,]+)", text)
    if explicit_match:
        return explicit_match.group(1).strip()[:100]

    for segment in segments:
        if segment.lower().startswith("route:"):
            return segment[:100]

    for segment in segments:
        lower = segment.lower()
        if any(hint in lower for hint in SECTION_HINTS):
            return segment[:100]

    return None


def _parse_quantity(text: str) -> int | None:
    ticket_match = re.search(r"(?i)\b(\d+)\s+tickets?\b", text)
    if ticket_match:
        return int(ticket_match.group(1))

    quantity_match = re.search(r"(?i)\bquantity\s*[:|-]\s*(\d+)\b", text)
    if quantity_match:
        return int(quantity_match.group(1))

    return None


def _parse_available_seats(text: str) -> int | None:
    seat_match = re.search(r"(?i)\b(\d+)\s+seats?\(s\)\s+available\b", text)
    if seat_match:
        return int(seat_match.group(1))

    seat_match = re.search(r"(?i)\b(\d+)\s+seats?\s+available\b", text)
    if seat_match:
        return int(seat_match.group(1))

    return None


def _parse_pricing(text: str, quantity: int) -> tuple[float | None, float | None]:
    total_match = re.search(r"(?i)\btotal\s*[:|-]?\s*\$(\d+(?:\.\d{1,2})?)\b", text)
    if total_match:
        total = float(total_match.group(1))
        unit_price = round(total / quantity, 2) if quantity else None
        return total, unit_price

    each_match = re.search(r"(?i)\$(\d+(?:\.\d{1,2})?)\s*(?:each|ea)\b", text)
    if each_match:
        unit_price = float(each_match.group(1))
        return round(unit_price * quantity, 2), unit_price

    from_match = re.search(r"(?i)\bfrom\s+\$(\d+(?:\.\d{1,2})?)\b", text)
    if from_match:
        unit_price = float(from_match.group(1))
        return round(unit_price * quantity, 2), unit_price

    any_price_match = re.search(r"\$(\d+(?:\.\d{1,2})?)", text)
    if any_price_match:
        total = float(any_price_match.group(1))
        unit_price = round(total / quantity, 2) if quantity > 1 else total
        return total, unit_price

    bdt_prices = _parse_bdt_prices(text)
    if bdt_prices:
        total = min(bdt_prices)
        unit_price = round(total / quantity, 2) if quantity > 1 else total
        return total, unit_price

    return None, None


def _parse_bdt_prices(text: str) -> list[float]:
    prices: list[float] = []
    for line in text.splitlines():
        if "discount" in line.lower():
            continue

        for pattern in (
            r"\u09f3\s*([\d,]+(?:\.\d{1,2})?)",
            r"(?i)\b(?:tk|bdt)\s*([\d,]+(?:\.\d{1,2})?)\b",
            r"(?i)\b([\d,]+(?:\.\d{1,2})?)\s*(?:tk|bdt)\b",
        ):
            for match in re.finditer(pattern, line):
                prices.append(float(match.group(1).replace(",", "")))

    return prices


def _looks_like_price(segment: str) -> bool:
    return bool(re.search(r"(?i)(\$|\u09f3|\btk\b|\bbdt\b)\s*[\d,]+|[\d,]+\s*(?:tk|bdt)\b", segment))


def _looks_like_time_or_date(segment: str) -> bool:
    return bool(
        re.fullmatch(r"(?i)\d{1,2}:\d{2}\s*(?:am|pm)", segment)
        or re.fullmatch(r"(?i)(?:mon|tue|wed|thu|fri|sat|sun),?\s+\d{1,2}\s+\w+", segment)
    )
