from src.config import settings
from src.models import AvailabilityStatus
from src.planner import choose_next_step
from src.state_machine import AgentState


def test_planner_waits_for_confirming_available_snapshot():
    original_confirmation_snapshots = settings.availability_confirmation_snapshots
    original_confidence_threshold = settings.availability_confidence_threshold
    settings.availability_confirmation_snapshots = 2
    settings.availability_confidence_threshold = 0.75
    status = AvailabilityStatus("available", "Tickets available", 0.9)
    try:
        step = choose_next_step(status, AgentState.MONITORING, confirmed_snapshots=1)
    finally:
        settings.availability_confirmation_snapshots = original_confirmation_snapshots
        settings.availability_confidence_threshold = original_confidence_threshold

    assert step.action == "observe"
    assert "confirming" in step.reason


def test_planner_starts_purchase_after_confirmed_available_snapshots():
    original_confirmation_snapshots = settings.availability_confirmation_snapshots
    original_confidence_threshold = settings.availability_confidence_threshold
    settings.availability_confirmation_snapshots = 2
    settings.availability_confidence_threshold = 0.75
    status = AvailabilityStatus("available", "Tickets available", 0.9)
    try:
        step = choose_next_step(status, AgentState.MONITORING, confirmed_snapshots=2)
    finally:
        settings.availability_confirmation_snapshots = original_confirmation_snapshots
        settings.availability_confidence_threshold = original_confidence_threshold

    assert step.action == "start_purchase_flow"
