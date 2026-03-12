from __future__ import annotations

import time

from rich import print

from src.browser.session import BrowserSession
from src.config import settings
from src.monitoring.availability_parser import parse_availability_text
from src.planner import choose_next_step
from src.policy import Offer, evaluate_offer
from src.state_machine import AgentState, StateMachine
from src.tools.human_handoff import request_human_handoff
from src.tools.notifier import notify
from src.utils.audit import audit_event
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    print(f"[bold green]Starting ticket-bot-mcp[/bold green] | dry_run={settings.dry_run}")
    sm = StateMachine()
    browser = BrowserSession()

    browser.connect()
    browser.navigate(settings.target_event_url)

    retries = 0
    while sm.state not in {AgentState.ABORTED, AgentState.CONFIRMATION}:
        try:
            snapshot_text = browser.snapshot_text()
            status = parse_availability_text(snapshot_text)
            step = choose_next_step(status, sm.state)

            audit_event(
                event_type="planner_step",
                payload={
                    "state": sm.state.value,
                    "status": status.state,
                    "action": step.action,
                    "reason": step.reason,
                },
            )

            logger.info("State=%s Status=%s Action=%s", sm.state.value, status.state, step.action)

            if step.action == "wait_and_recheck":
                time.sleep(settings.poll_interval_seconds)
                continue

            if step.action == "stay_in_queue":
                notify("Queue detected. Monitoring continues.")
                time.sleep(settings.fast_poll_interval_seconds)
                continue

            if step.action == "request_human_handoff":
                request_human_handoff(f"Manual action required: {status.state}")
                sm.transition(step.next_state)
                break

            if step.action == "start_purchase_flow":
                sm.transition(step.next_state)

                # Demo offer extraction. Replace with actual page parsing later.
                offer = Offer(
                    title="Sample Event",
                    section="Lower Bowl",
                    quantity=2,
                    total_usd=150.0,
                    source_text=snapshot_text[:500],
                )
                decision = evaluate_offer(offer)

                audit_event(
                    event_type="offer_evaluated",
                    payload={
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "offer": offer.__dict__,
                    },
                )

                if not decision.allowed:
                    notify(f"Offer blocked by policy: {decision.reason}")
                    sm.transition(AgentState.ABORTED)
                    break

                if settings.dry_run:
                    notify(f"DRY RUN: acceptable offer found. Would proceed with {offer.quantity} tickets for ${offer.total_usd}.")
                    browser.take_screenshot("dry_run_offer")
                    sm.transition(AgentState.PAYMENT_REVIEW)
                    request_human_handoff("Dry run reached payment review. No order was placed.")
                    break

                sm.transition(AgentState.CHECKOUT)
                # Real checkout steps would be implemented here through wrapped MCP tool calls.

            retries = 0

        except KeyboardInterrupt:
            notify("Interrupted by user.")
            sm.transition(AgentState.ABORTED)
            break
        except Exception as exc:
            retries += 1
            logger.exception("Unhandled error: %s", exc)
            audit_event(
                event_type="error",
                payload={"error": str(exc), "retries": retries},
            )
            if retries >= settings.max_retries:
                notify(f"Aborting after {retries} consecutive errors: {exc}")
                sm.transition(AgentState.ABORTED)
                break
            time.sleep(3)

    print(f"[bold yellow]Final state:[/bold yellow] {sm.state.value}")


if __name__ == "__main__":
    main()
