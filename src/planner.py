from __future__ import annotations

from dataclasses import dataclass

from src.config import settings
from src.state_machine import AgentState
from src.monitoring.availability_parser import AvailabilityStatus


@dataclass(slots=True)
class PlanStep:
    action: str
    reason: str
    next_state: AgentState


def choose_next_step(
    status: AvailabilityStatus,
    current_state: AgentState,
    confirmed_snapshots: int = 1,
) -> PlanStep:
    if status.state == "sold_out":
        return PlanStep(
            action="wait_and_recheck",
            reason="Tickets are still sold out",
            next_state=AgentState.MONITORING,
        )

    if status.state == "available" and current_state == AgentState.MONITORING:
        if status.confidence < settings.availability_confidence_threshold:
            return PlanStep(
                action="observe",
                reason=(
                    "Availability signal below confidence threshold "
                    f"({status.confidence:.2f} < {settings.availability_confidence_threshold:.2f})"
                ),
                next_state=current_state,
            )

        if confirmed_snapshots < settings.availability_confirmation_snapshots:
            return PlanStep(
                action="observe",
                reason=(
                    "Waiting for confirming availability snapshot "
                    f"({confirmed_snapshots}/{settings.availability_confirmation_snapshots})"
                ),
                next_state=current_state,
            )

        return PlanStep(
            action="start_purchase_flow",
            reason="Availability detected",
            next_state=AgentState.AVAILABILITY_DETECTED,
        )

    if status.state in {"captcha_blocked", "mfa_required"}:
        return PlanStep(
            action="request_human_handoff",
            reason=f"Sensitive checkpoint encountered: {status.state}",
            next_state=AgentState.HUMAN_HANDOFF,
        )

    if status.state == "queue":
        return PlanStep(
            action="stay_in_queue",
            reason="Queue detected, remain patient and monitor",
            next_state=current_state,
        )

    return PlanStep(
        action="observe",
        reason="No stronger action available",
        next_state=current_state,
    )
