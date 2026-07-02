from __future__ import annotations

import re

from src.models import AvailabilityStatus, ParsedOffer


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


def parse_availability_text(text: str) -> AvailabilityStatus:
    lower = text.lower()

    if "captcha" in lower:
        return AvailabilityStatus("captcha_blocked", text, 0.99, ["captcha"])
    if "mfa" in lower or "verify your identity" in lower:
        return AvailabilityStatus("mfa_required", text, 0.96, ["mfa_or_identity_check"])

    queue_signals = _matching_signals(lower, ("queue", "you are in line"))
    sold_out_signals = _matching_signals(lower, ("sold out", "no tickets available"))
    available_signals = _matching_signals(
        lower,
        (
            "available",
            "find tickets",
            "tickets available",
            "book ticket",
            "seat(s) available",
            "seats available",
        ),
    )
    if "no tickets available" in sold_out_signals:
        available_signals = [
            signal
            for signal in available_signals
            if signal not in {"available", "tickets available"}
        ]

    if queue_signals:
        return AvailabilityStatus("queue", text, 0.88, queue_signals)

    if sold_out_signals and available_signals:
        return AvailabilityStatus(
            "unknown",
            text,
            0.42,
            [*sold_out_signals, *available_signals],
            ["mixed sold-out and availability signals"],
        )

    if sold_out_signals:
        return AvailabilityStatus("sold_out", text, 0.9, sold_out_signals)

    if available_signals:
        confidence = 0.76
        if _parse_available_seats(text) is not None:
            confidence += 0.1
        if _parse_pricing(text, 1)[0] is not None:
            confidence += 0.07
        return AvailabilityStatus("available", text, min(confidence, 0.94), available_signals)

    return AvailabilityStatus("unknown", text, 0.2, [], ["no known availability signals"])


def parse_offer_text(text: str) -> ParsedOffer | None:
    offers = parse_offer_texts(text)
    return offers[0] if offers else None


def parse_offer_texts(text: str) -> list[ParsedOffer]:
    segments = _extract_segments(text)
    bus_offers = _parse_bus_offer_blocks(segments)
    if bus_offers:
        return sorted(
            bus_offers,
            key=lambda offer: (offer.total_usd, -(offer.available_seats or 0)),
        )

    generic_offer = _parse_generic_offer_text(text, segments)
    return [generic_offer] if generic_offer is not None else []


def _parse_generic_offer_text(text: str, segments: list[str]) -> ParsedOffer | None:
    title = _parse_title(segments)
    section = _parse_section(text, segments) or "Unknown"
    quantity = _parse_quantity(text) or 1
    total_usd, unit_price_usd = _parse_pricing(text, quantity)
    available_seats = _parse_available_seats(text)

    if not title or total_usd is None or total_usd <= 0:
        return None

    signals = _offer_signals(title, section, quantity, total_usd, available_seats)
    return ParsedOffer(
        title=title,
        section=section,
        quantity=quantity,
        total_usd=total_usd,
        unit_price_usd=unit_price_usd,
        available_seats=available_seats,
        currency=_parse_currency(text),
        confidence=_offer_confidence(signals),
        signals=signals,
        source_text=text[:1000],
    )


def _parse_bus_offer_blocks(segments: list[str]) -> list[ParsedOffer]:
    offers: list[ParsedOffer] = []
    for index, segment in enumerate(segments):
        if segment.lower() != "book ticket":
            continue

        before = segments[max(0, index - 30):index]
        after = segments[index:index + 8]
        seats = _parse_available_seats("\n".join(after))
        if seats is None:
            seats = _parse_available_seats("\n".join(before[-8:]))
        if seats is None or seats <= 0:
            continue

        prices = [price for price in _parse_bdt_prices("\n".join(before[-14:])) if price > 0]
        if not prices:
            continue

        route = _nearest_route(before) or "Unknown"
        title = _nearest_operator_title(before)
        if not title:
            continue

        departure_time, arrival_time = _parse_bus_times(before)
        duration = _parse_duration(before)
        service_class = _parse_service_class(before)
        total = min(prices)
        signals = ["bus_card", "book_ticket", "title", "price", "positive_price", "available_seats"]
        if route != "Unknown":
            signals.append("section")
        if departure_time:
            signals.append("departure_time")

        offers.append(
            ParsedOffer(
                title=title,
                section=route,
                quantity=1,
                total_usd=total,
                unit_price_usd=total,
                available_seats=seats,
                currency="BDT",
                departure_time=departure_time,
                arrival_time=arrival_time,
                duration=duration,
                service_class=service_class,
                confidence=0.96,
                signals=signals,
                source_text="\n".join([*before[-18:], *after])[:1000],
            )
        )

    return _dedupe_offers(offers)


def _dedupe_offers(offers: list[ParsedOffer]) -> list[ParsedOffer]:
    deduped: dict[tuple[str, str, float, int | None], ParsedOffer] = {}
    for offer in offers:
        key = (offer.title, offer.section, offer.total_usd, offer.available_seats)
        deduped.setdefault(key, offer)
    return list(deduped.values())


def _nearest_route(segments: list[str]) -> str | None:
    for segment in reversed(segments):
        if segment.lower().startswith("route:"):
            return segment[:100]
    return None


def _nearest_operator_title(segments: list[str]) -> str | None:
    route_index = None
    for index, segment in enumerate(segments):
        if segment.lower().startswith("route:"):
            route_index = index

    candidates = segments[max(0, (route_index or len(segments)) - 8):route_index]
    for segment in reversed(candidates):
        if _is_operator_title_candidate(segment):
            return segment[:200]
    return None


def _parse_bus_times(segments: list[str]) -> tuple[str | None, str | None]:
    times = [segment for segment in segments if _looks_like_clock_time(segment)]
    if len(times) >= 2:
        return times[-2], times[-1]
    if len(times) == 1:
        return times[0], None
    return None, None


def _parse_duration(segments: list[str]) -> str | None:
    for segment in reversed(segments):
        if re.fullmatch(r"(?i)\d+h(?:\s+\d+m)?|\d+\s*h\s+\d+\s*m", segment):
            return segment
    return None


def _parse_service_class(segments: list[str]) -> str | None:
    for segment in segments:
        lower = segment.lower()
        if re.match(r"^\d+\s*,", segment) or any(
            token in lower
            for token in (" ac", "non ac", "sleeper", "hino", "volvo", "business class")
        ):
            return segment[:100]
    return None


def _is_operator_title_candidate(segment: str) -> bool:
    lower = segment.lower()
    if not segment or len(segment) < 3:
        return False
    if lower in {"logo", "img", "info", "filters"}:
        return False
    if lower.startswith(("route:", "page ", "console:", "/url:", "/placeholder:")):
        return False
    if re.match(r"^\d+\s*,", segment):
        return False
    if any(token in lower for token in (" ac", "non ac", "sleeper", "hino", "volvo", "business class")):
        return False
    if _looks_like_price(segment) or _looks_like_time_or_date(segment):
        return False
    return True


def _matching_signals(lower_text: str, candidates: tuple[str, ...]) -> list[str]:
    return [candidate for candidate in candidates if candidate in lower_text]


def _offer_signals(
    title: str,
    section: str,
    quantity: int,
    total_usd: float,
    available_seats: int | None,
) -> list[str]:
    signals = ["title", "price"]
    if section != "Unknown":
        signals.append("section")
    if quantity > 0:
        signals.append("quantity")
    if available_seats is not None:
        signals.append("available_seats")
    if total_usd > 0:
        signals.append("positive_price")
    return signals


def _offer_confidence(signals: list[str]) -> float:
    confidence = 0.35
    weights = {
        "title": 0.15,
        "price": 0.2,
        "section": 0.12,
        "quantity": 0.08,
        "available_seats": 0.12,
        "positive_price": 0.05,
    }
    for signal in signals:
        confidence += weights.get(signal, 0.0)
    return min(confidence, 0.95)


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
    lower = segment.lower()

    if not segment or segment.startswith("```") or segment.startswith("###"):
        return ""
    if lower.startswith(("page url:", "page title:", "console:", "/url:", "/placeholder:")):
        return ""

    quoted_match = re.search(r'"([^"]+)"', segment)
    if quoted_match:
        return quoted_match.group(1).strip()

    label_match = re.match(r"(?i)(?:text|heading|paragraph)\s*:\s*(.+)", segment)
    if label_match:
        return label_match.group(1).strip()

    role_label_match = re.match(
        r"(?i)(?:generic|button|link|img|textbox|paragraph)\s*:?\s*(.+)?$",
        segment,
    )
    if role_label_match:
        return (role_label_match.group(1) or "").strip()

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


def _parse_currency(text: str) -> str:
    if re.search(r"(?i)(\u09f3|\btk\b|\bbdt\b)", text):
        return "BDT"
    if "$" in text:
        return "USD"
    return "PRICE"


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
                price = float(match.group(1).replace(",", ""))
                if price > 0:
                    prices.append(price)

    return prices


def _looks_like_price(segment: str) -> bool:
    return bool(re.search(r"(?i)(\$|\u09f3|\btk\b|\bbdt\b)\s*[\d,]+|[\d,]+\s*(?:tk|bdt)\b", segment))


def _looks_like_time_or_date(segment: str) -> bool:
    return bool(
        _looks_like_clock_time(segment)
        or re.fullmatch(r"(?i)(?:mon|tue|wed|thu|fri|sat|sun),?\s+\d{1,2}\s+\w+", segment)
    )


def _looks_like_clock_time(segment: str) -> bool:
    return bool(re.fullmatch(r"(?i)\d{1,2}:\d{2}\s*(?:am|pm)", segment.strip()))
