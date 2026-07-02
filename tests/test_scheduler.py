from src.models import AvailabilityStatus, MonitorTarget
from src.monitoring.scheduler import AdaptiveScheduler


def test_scheduler_prioritizes_unpolled_targets():
    targets = [
        MonitorTarget(id="a", url="https://example.com/a"),
        MonitorTarget(id="b", url="https://example.com/b"),
    ]
    scheduler = AdaptiveScheduler(targets)

    first = scheduler.next_target()
    scheduler.record_status(first.id, AvailabilityStatus("sold_out", "Sold Out", 0.9))
    second = scheduler.next_target()

    assert second.id != first.id


def test_scheduler_uses_min_delay_for_available_status():
    target = MonitorTarget(id="a", url="https://example.com/a", poll_min_seconds=5, poll_max_seconds=60)
    scheduler = AdaptiveScheduler([target])
    status = AvailabilityStatus("available", "Tickets available", 0.9)

    assert scheduler.recommended_delay(target, status) == 5
