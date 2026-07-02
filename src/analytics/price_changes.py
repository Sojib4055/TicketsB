from __future__ import annotations

from typing import Any


def detect_price_changes(
    previous_report: dict[str, Any] | None,
    current_top_offers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not previous_report:
        return []

    previous_by_key = {
        _offer_key(item.get("offer", {})): item.get("offer", {})
        for item in previous_report.get("top_offers", [])
        if isinstance(item, dict)
    }

    changes: list[dict[str, Any]] = []
    for item in current_top_offers:
        offer = item.get("offer", {})
        key = _offer_key(offer)
        previous = previous_by_key.get(key)
        if not previous:
            changes.append(
                {
                    "type": "new_offer",
                    "message": f"New offer appeared: {offer.get('title')} at {offer.get('total_usd')} {offer.get('currency')}",
                    "offer": offer,
                }
            )
            continue

        old_price = _as_float(previous.get("total_usd"))
        new_price = _as_float(offer.get("total_usd"))
        if old_price is not None and new_price is not None and old_price != new_price:
            direction = "dropped" if new_price < old_price else "increased"
            changes.append(
                {
                    "type": f"price_{direction}",
                    "message": (
                        f"Price {direction}: {offer.get('title')} "
                        f"{old_price} -> {new_price} {offer.get('currency')}"
                    ),
                    "old_price": old_price,
                    "new_price": new_price,
                    "offer": offer,
                }
            )

        old_seats = _as_int(previous.get("available_seats"))
        new_seats = _as_int(offer.get("available_seats"))
        if old_seats is not None and new_seats is not None and old_seats != new_seats:
            changes.append(
                {
                    "type": "seat_count_changed",
                    "message": f"Seat count changed: {offer.get('title')} {old_seats} -> {new_seats}",
                    "old_seats": old_seats,
                    "new_seats": new_seats,
                    "offer": offer,
                }
            )

    return changes


def _offer_key(offer: dict[str, Any]) -> tuple[str, str]:
    return (str(offer.get("title") or ""), str(offer.get("section") or ""))


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
