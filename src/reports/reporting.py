from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_DIR = Path("logs/reports")
LATEST_UI_STATE_PATH = REPORT_DIR / "latest_ui_state.json"
LATEST_OFFER_REPORT_PATH = REPORT_DIR / "latest_offer_report.json"
LATEST_TEXT_REPORT_PATH = REPORT_DIR / "latest_offer_report.txt"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_initial_ui_state(dashboard_url: str) -> dict[str, Any]:
    return {
        "app": "ticket-bot-mcp",
        "dashboard_url": dashboard_url,
        "updated_at": utc_now_iso(),
        "state": "STARTING",
        "target": {},
        "trip": None,
        "trip_schedule": None,
        "status": {
            "state": "starting",
            "confidence": 0,
            "signals": [],
            "warnings": [],
        },
        "decision": {
            "kind": "STARTING",
            "message": "Starting monitor",
        },
        "summary": {
            "offers_scanned": 0,
            "valid_offers": 0,
            "blocked_offers": 0,
            "best_allowed_fare": None,
            "lowest_seen_fare": None,
            "max_total_price": None,
            "currency": "PRICE",
        },
        "top_offers": [],
        "offer_notification": None,
        "price_changes": [],
        "handoff": None,
        "screenshot_path": None,
        "ticket_path": None,
        "events": [],
        "final": False,
    }


def write_ui_state(state: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now_iso()
    _write_json_atomic(LATEST_UI_STATE_PATH, state)


def write_offer_report(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report["updated_at"] = utc_now_iso()
    _write_json_atomic(LATEST_OFFER_REPORT_PATH, report)
    LATEST_TEXT_REPORT_PATH.write_text(_format_text_report(report), encoding="utf-8")


def load_latest_offer_report() -> dict[str, Any] | None:
    if not LATEST_OFFER_REPORT_PATH.exists():
        return None
    try:
        data = json.loads(LATEST_OFFER_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _format_text_report(report: dict[str, Any]) -> str:
    decision = report.get("decision", {})
    summary = report.get("summary", {})
    trip = report.get("trip") or {}
    schedule = report.get("trip_schedule") or {}
    lines = [
        "Ticket Bot Offer Report",
        f"Updated: {report.get('updated_at')}",
        f"Decision: {decision.get('kind', 'UNKNOWN')}",
        f"Message: {decision.get('message', '')}",
    ]
    if trip:
        lines.extend(
            [
                "",
                "Trip",
                f"Route: {trip.get('from_city')} -> {trip.get('to_city')}",
                f"Journey date: {trip.get('journey_date')}",
                f"Preferred time: {trip.get('preferred_departure_start') or '-'} to {trip.get('preferred_departure_end') or '-'}",
                f"Monitoring start: {schedule.get('monitoring_start_date', '-')}",
                f"Seat preference: {trip.get('seat_preference') or 'Any'}",
            ]
        )
    lines.extend(
        [
            "",
            "Summary",
            f"Offers scanned: {summary.get('offers_scanned', 0)}",
            f"Valid offers: {summary.get('valid_offers', 0)}",
            f"Blocked offers: {summary.get('blocked_offers', 0)}",
            f"Best allowed fare: {summary.get('best_allowed_fare')} {summary.get('currency', '')}",
            f"Lowest seen fare: {summary.get('lowest_seen_fare')} {summary.get('currency', '')}",
            f"Price cap: {summary.get('max_total_price')} {summary.get('currency', '')}",
            "",
            "Top Offers",
        ]
    )
    for index, item in enumerate(report.get("top_offers", []), start=1):
        offer = item.get("offer", {})
        decision_item = item.get("decision", {})
        link = offer.get("payment_url") or offer.get("booking_url")
        line = (
            f"{index}. {offer.get('title')} | {offer.get('section')} | "
            f"{offer.get('total_usd')} {offer.get('currency')} | "
            f"{offer.get('available_seats')} seats | score {decision_item.get('score')}"
        )
        if link:
            line += f" | link {link}"
        lines.append(line)

    notification = report.get("offer_notification") or {}
    if notification:
        best = notification.get("best_offer") or {}
        lines.extend(["", "Website Notification", notification.get("title", "")])
        if best.get("link_url"):
            lines.append(f"Best offer link: {best.get('link_label', 'Open link')} - {best.get('link_url')}")
        nearby = notification.get("nearby_offers") or []
        if nearby:
            lines.append("Nearby best-priced links:")
            for item in nearby:
                lines.append(f"- {item.get('operator')} | {item.get('fare')} {item.get('currency')} | {item.get('link_url')}")

    changes = report.get("price_changes") or []
    if changes:
        lines.extend(["", "Price Changes"])
        for change in changes:
            lines.append(change.get("message", ""))

    handoff = report.get("handoff")
    if handoff:
        lines.extend(["", "Handoff", handoff.get("message", "")])
    return "\n".join(lines).strip() + "\n"
