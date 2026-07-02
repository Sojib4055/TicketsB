from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from src.config import settings
from src.models import MonitorTarget, TripRequest, TripSchedule


TRIP_CONFIG_DIR = Path("logs/config")
TRIP_REQUEST_PATH = TRIP_CONFIG_DIR / "trip_request.json"


def load_trip_request(path: Path = TRIP_REQUEST_PATH) -> TripRequest | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return trip_from_payload(payload)


def save_trip_request(trip: TripRequest, path: Path = TRIP_REQUEST_PATH) -> TripRequest:
    TRIP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not trip.created_at:
        trip.created_at = datetime.now(timezone.utc).isoformat()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(asdict(trip), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return trip


def trip_from_payload(payload: dict[str, Any]) -> TripRequest:
    from_city = str(payload.get("from_city") or payload.get("fromcity") or "").strip()
    to_city = str(payload.get("to_city") or payload.get("tocity") or "").strip()
    journey_date = _normalize_date(str(payload.get("journey_date") or payload.get("doj") or "").strip())
    if not from_city or not to_city or not journey_date:
        raise ValueError("from_city, to_city, and journey_date are required")

    return TripRequest(
        from_city=from_city,
        to_city=to_city,
        journey_date=journey_date,
        preferred_departure_start=str(payload.get("preferred_departure_start") or "").strip(),
        preferred_departure_end=str(payload.get("preferred_departure_end") or "").strip(),
        max_total_price=float(payload.get("max_total_price") or settings.effective_max_total_price),
        currency=str(payload.get("currency") or settings.normalized_price_currency).strip().upper(),
        seat_count=max(1, int(payload.get("seat_count") or settings.max_tickets or 1)),
        preferred_operators=_list_value(payload.get("preferred_operators")),
        avoid_operators=_list_value(payload.get("avoid_operators")),
        avoid_night_buses=bool(payload.get("avoid_night_buses", False)),
        monitor_days_before=max(0, int(payload.get("monitor_days_before") or 10)),
        seat_preference=str(payload.get("seat_preference") or "").strip(),
        auto_purchase_requested=bool(payload.get("auto_purchase_requested", False)),
        created_at=str(payload.get("created_at") or ""),
    )


def apply_trip_to_settings(trip: TripRequest) -> None:
    settings.target_event_url = build_shohoz_url(trip)
    settings.max_total_price = trip.max_total_price
    settings.price_currency = trip.currency
    settings.max_tickets = trip.seat_count
    settings.preferred_operators = ",".join(trip.preferred_operators)
    settings.avoid_operators = ",".join(trip.avoid_operators)
    settings.preferred_departure_start = trip.preferred_departure_start or None
    settings.preferred_departure_end = trip.preferred_departure_end or None
    settings.avoid_night_buses = trip.avoid_night_buses
    settings.target_origin = trip.from_city
    settings.target_destination = trip.to_city


def monitor_target_for_trip(trip: TripRequest) -> MonitorTarget:
    label = f"{trip.from_city} -> {trip.to_city} · {trip.journey_date}"
    return MonitorTarget(
        id="trip",
        url=build_shohoz_url(trip),
        label=label,
        site_type="shohoz_bus",
        route_or_event=label,
        priority=1.5,
        poll_min_seconds=settings.fast_poll_interval_seconds,
        poll_max_seconds=settings.poll_interval_seconds,
    )


def build_shohoz_url(trip: TripRequest) -> str:
    journey_date = parse_trip_date(trip.journey_date)
    query = urlencode(
        {
            "fromcity": trip.from_city,
            "tocity": trip.to_city,
            "doj": journey_date.strftime("%d-%b-%Y"),
            "dor": "",
        }
    )
    return f"https://www.shohoz.com/bus-tickets/booking/bus/search?{query}"


def schedule_for_trip(trip: TripRequest, today: date | None = None) -> TripSchedule:
    today = today or date.today()
    journey_date = parse_trip_date(trip.journey_date)
    monitoring_start = journey_date - timedelta(days=trip.monitor_days_before)
    days_until_journey = (journey_date - today).days
    days_until_start = (monitoring_start - today).days
    should_monitor = today >= monitoring_start
    if days_until_journey < 0:
        message = f"Journey date {journey_date.isoformat()} is in the past."
        should_monitor = False
    elif should_monitor:
        message = (
            f"Monitoring active for {trip.from_city} -> {trip.to_city}. "
            f"Journey is in {days_until_journey} day(s)."
        )
    else:
        message = (
            f"Monitoring scheduled for {monitoring_start.isoformat()}, "
            f"{days_until_start} day(s) from today."
        )
    return TripSchedule(
        journey_date=journey_date.isoformat(),
        monitoring_start_date=monitoring_start.isoformat(),
        today=today.isoformat(),
        days_until_journey=days_until_journey,
        days_until_monitoring_start=days_until_start,
        should_monitor=should_monitor,
        message=message,
    )


def advance_monitoring_message(trip: TripRequest, schedule: TripSchedule) -> str:
    return (
        f"Advance monitoring: {trip.from_city} -> {trip.to_city} on {trip.journey_date}. "
        f"Start date: {schedule.monitoring_start_date}. "
        f"Status: {schedule.message}"
    )


def parse_trip_date(value: str) -> date:
    return datetime.strptime(_normalize_date(value), "%Y-%m-%d").date()


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]
