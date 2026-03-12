from __future__ import annotations

from enum import Enum


class AgentState(str, Enum):
    MONITORING = "MONITORING"
    AVAILABILITY_DETECTED = "AVAILABILITY_DETECTED"
    LOGIN_READY = "LOGIN_READY"
    SEAT_SELECTION = "SEAT_SELECTION"
    CHECKOUT = "CHECKOUT"
    PAYMENT_REVIEW = "PAYMENT_REVIEW"
    CONFIRMATION = "CONFIRMATION"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    ABORTED = "ABORTED"


class StateMachine:
    def __init__(self) -> None:
        self.state = AgentState.MONITORING

    def transition(self, next_state: AgentState) -> AgentState:
        self.state = next_state
        return self.state
