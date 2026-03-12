from __future__ import annotations

from dataclasses import dataclass

from src.state_machine import AgentState
from src.monitoring.availability_parser import AvailabilityStatus


@dataclass(slots=True)
class PlanStep:
    action: str
    reason: str
    next_state: AgentState


def choose_next_step(status: AvailabilityStatus, current_state: AgentState) -> PlanStep:
    if status.state == "sold_out":
        return PlanStep(
            action="wait_and_recheck",
            reason="Tickets are still sold out",
            next_state=AgentState.MONITORING,
        )

    if status.state == "available" and current_state == AgentState.MONITORING:
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
