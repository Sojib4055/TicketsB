from datetime import date

from src.models import TripRequest
from src.trips import build_shohoz_url, schedule_for_trip, trip_from_payload


def test_trip_payload_generates_shohoz_url():
    trip = trip_from_payload(
        {
            "from_city": "Dhaka",
            "to_city": "Bogura",
            "journey_date": "2026-07-20",
            "max_total_price": 2000,
            "preferred_operators": "SHYAMOLI PARIBAHAN, Hanif Enterprise",
        }
    )

    url = build_shohoz_url(trip)

    assert "fromcity=Dhaka" in url
    assert "tocity=Bogura" in url
    assert "doj=20-Jul-2026" in url
    assert trip.preferred_operators == ["SHYAMOLI PARIBAHAN", "Hanif Enterprise"]


def test_trip_schedule_waits_until_advance_window():
    trip = TripRequest(from_city="Dhaka", to_city="Bogura", journey_date="2026-07-20", monitor_days_before=10)

    schedule = schedule_for_trip(trip, today=date(2026, 7, 5))

    assert schedule.should_monitor is False
    assert schedule.monitoring_start_date == "2026-07-10"
    assert schedule.days_until_monitoring_start == 5


def test_trip_schedule_active_inside_advance_window():
    trip = TripRequest(from_city="Dhaka", to_city="Bogura", journey_date="2026-07-20", monitor_days_before=10)

    schedule = schedule_for_trip(trip, today=date(2026, 7, 10))

    assert schedule.should_monitor is True
    assert "Monitoring active" in schedule.message
