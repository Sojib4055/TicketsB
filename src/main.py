from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.analytics.price_changes import detect_price_changes
from src.analytics.audit_reader import load_audit_events
from src.browser.session import BrowserSession
from src.config import settings
from src.monitoring.availability_parser import parse_availability_text, parse_offer_text
from src.monitoring.extractors import RegexOfferExtractor, SemanticOfferExtractor
from src.monitoring.scheduler import AdaptiveScheduler
from src.monitoring.targets import load_monitor_targets
from src.models import AvailabilityStatus, HandoffBrief, MonitorTarget, Offer, ParsedOffer, PolicyDecision, TripRequest
from src.planner import choose_next_step
from src.policy import rank_offers
from src.reports.reporting import (
    build_initial_ui_state,
    load_latest_offer_report,
    write_offer_report,
    write_ui_state,
)
from src.state_machine import AgentState, StateMachine
from src.tools.human_handoff import request_human_handoff
from src.tools.notifier import notify
from src.trips import (
    advance_monitoring_message,
    apply_trip_to_settings,
    load_trip_request,
    monitor_target_for_trip,
    schedule_for_trip,
)
from src.ui import DashboardServer
from src.utils.audit import audit_event
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    dashboard = DashboardServer(settings.ui_host, settings.ui_port) if settings.ui_enabled else None
    dashboard_url = dashboard.start() if dashboard else ""
    if dashboard_url:
        print(f"Dashboard: {dashboard_url}")

    sm = StateMachine()
    browser = BrowserSession()
    ui_state = build_initial_ui_state(dashboard_url)
    ui_state["decision"] = {
        "kind": "STARTING",
        "message": "Monitor is starting",
    }
    _append_ui_event(ui_state, "Monitor is starting")
    write_ui_state(ui_state)

    trip = load_trip_request()
    if trip is None and _should_wait_for_trip_setup():
        trip = _wait_for_trip_setup(ui_state)

    if trip is not None:
        apply_trip_to_settings(trip)
        targets = [monitor_target_for_trip(trip)]
    else:
        targets = load_monitor_targets()
    scheduler = AdaptiveScheduler(targets, history_events=load_audit_events())
    regex_extractor = RegexOfferExtractor()
    semantic_extractor = SemanticOfferExtractor()
    current_url: str | None = None
    availability_confirmations: dict[str, int] = {}
    if trip is not None:
        ui_state["trip"] = asdict(trip)
        ui_state["trip_schedule"] = asdict(schedule_for_trip(trip))
    write_ui_state(ui_state)

    try:
        if trip is not None:
            trip = _wait_for_monitoring_window(ui_state, trip)
            apply_trip_to_settings(trip)
            targets = [monitor_target_for_trip(trip)]
            scheduler = AdaptiveScheduler(targets, history_events=load_audit_events())

        browser.connect()
        browser.resize()

        retries = 0
        while sm.state not in {AgentState.ABORTED, AgentState.CONFIRMATION}:
            try:
                target = scheduler.next_target()
                if current_url != target.url:
                    browser.navigate(target.url)
                    current_url = target.url

                snapshot_text = browser.snapshot_text()
                status = parse_availability_text(snapshot_text)
                if status.state == "available" and status.confidence >= settings.availability_confidence_threshold:
                    availability_confirmations[target.id] = availability_confirmations.get(target.id, 0) + 1
                else:
                    availability_confirmations[target.id] = 0

                confirmed_snapshots = availability_confirmations.get(target.id, 0)
                step = choose_next_step(status, sm.state, confirmed_snapshots=confirmed_snapshots)
                scheduler.record_status(target.id, status)
                _publish_poll_state(ui_state, target, status, sm.state, step.action, step.reason)

                audit_event(
                    event_type="planner_step",
                    payload={
                        "target_id": target.id,
                        "url": target.url,
                        "state": sm.state.value,
                        "status": status.state,
                        "confidence": status.confidence,
                        "signals": status.signals,
                        "warnings": status.warnings,
                        "confirmed_snapshots": confirmed_snapshots,
                        "action": step.action,
                        "reason": step.reason,
                    },
                )

                logger.info(
                    "Target=%s State=%s Status=%s Confidence=%.2f Action=%s",
                    target.id,
                    sm.state.value,
                    status.state,
                    status.confidence,
                    step.action,
                )

                if step.action == "wait_and_recheck":
                    time.sleep(scheduler.recommended_delay(target, status))
                    continue

                if step.action == "stay_in_queue":
                    notify("Queue detected. Monitoring continues.")
                    time.sleep(scheduler.recommended_delay(target, status))
                    continue

                if step.action == "observe":
                    time.sleep(scheduler.recommended_delay(target, status))
                    continue

                if step.action == "request_human_handoff":
                    handoff = HandoffBrief(
                        reason=f"Manual action required: {status.state}",
                        target=target.label or target.route_or_event or target.url,
                        found=f"Page state {status.state} with confidence {status.confidence:.2f}",
                        policy_result="No purchase action evaluated",
                        bot_action="Stopped before sensitive or blocked step",
                        suggested_next_action="Review the page manually and resume only if appropriate",
                        expiry_risk="unknown",
                        details={"signals": ", ".join(status.signals) or "none"},
                    )
                    request_human_handoff(handoff)
                    sm.transition(step.next_state)
                    _publish_final_report(
                        ui_state=ui_state,
                        target=target,
                        status=status,
                        final_state=sm.state,
                        decision={"kind": "HUMAN_HANDOFF", "message": handoff.reason},
                        ranked=[],
                        handoff=handoff,
                    )
                    break

                if step.action == "start_purchase_flow":
                    ranked = _extract_ranked_offers(snapshot_text, regex_extractor, semantic_extractor, target)
                    if not ranked:
                        notify("Availability detected, but offer details could not be parsed. Monitoring continues.")
                        _append_ui_event(ui_state, "Availability detected, but no parseable offers were found")
                        write_ui_state(ui_state)
                        time.sleep(scheduler.recommended_delay(target, status))
                        continue

                    sm.transition(step.next_state)

                    offer, decision = ranked[0]
                    seat_summary = (
                        f"{offer.available_seats} seats available"
                        if offer.available_seats is not None
                        else "seat count unavailable"
                    )
                    offer_summary = (
                        f"{offer.title} | {offer.section} | {seat_summary} | "
                        f"fare {offer.total_usd} {settings.normalized_price_currency}"
                    )
                    top_items = _ranked_items(ranked[:settings.top_offer_limit])
                    price_changes = detect_price_changes(load_latest_offer_report(), top_items)

                    audit_event(
                        event_type="offer_evaluated",
                        payload={
                            "target_id": target.id,
                            "url": target.url,
                            "allowed": decision.allowed,
                            "reason": decision.reason,
                            "score": decision.score,
                            "rank_reason": decision.rank_reason,
                            "hard_blocks": decision.hard_blocks,
                            "soft_penalties": decision.soft_penalties,
                            "offer": asdict(offer),
                        },
                    )

                    if not decision.allowed:
                        screenshot_path = browser.take_screenshot("blocked_offer", full_page=False).as_posix()
                        notify(_availability_notification(target, ranked, decision, blocked=True))
                        sm.transition(AgentState.ABORTED)
                        _publish_final_report(
                            ui_state=ui_state,
                            target=target,
                            status=status,
                            final_state=sm.state,
                            decision={
                                "kind": "BLOCKED_BY_POLICY",
                                "message": f"Best offer blocked: {decision.reason}",
                            },
                            ranked=ranked,
                            price_changes=price_changes,
                            screenshot_path=screenshot_path,
                        )
                        break

                    if settings.dry_run:
                        notify(_availability_notification(target, ranked, decision, blocked=False))
                        screenshot_path = browser.take_screenshot("dry_run_offer", full_page=False).as_posix()
                        sm.transition(AgentState.PAYMENT_REVIEW)
                        handoff = HandoffBrief(
                            reason="Dry run reached payment review",
                            target=target.label or target.route_or_event or target.url,
                            found=offer_summary,
                            policy_result=(
                                f"Allowed with score {decision.score}. {decision.rank_reason}"
                            ),
                            bot_action="No booking was placed",
                            suggested_next_action="Review the offer and complete checkout manually if desired",
                            expiry_risk=decision.expiry_risk,
                            details={
                                "top_offers": str(min(len(ranked), settings.top_offer_limit)),
                                "best_score": str(decision.score),
                            },
                        )
                        request_human_handoff(handoff)
                        _publish_final_report(
                            ui_state=ui_state,
                            target=target,
                            status=status,
                            final_state=sm.state,
                            decision={
                                "kind": "READY_FOR_HUMAN_REVIEW",
                                "message": f"Best offer allowed: {offer.title} at {offer.total_usd} {offer.currency}",
                            },
                            ranked=ranked,
                            handoff=handoff,
                            price_changes=price_changes,
                            screenshot_path=screenshot_path,
                        )
                        break

                    sm.transition(AgentState.CHECKOUT)
                    handoff = HandoffBrief(
                        reason="Checkout automation is not implemented",
                        target=target.label or target.route_or_event or target.url,
                        found=offer_summary,
                        policy_result=(
                            f"Allowed with score {decision.score}. {decision.rank_reason}"
                        ),
                        bot_action="Stopped before checkout/payment execution",
                        suggested_next_action="Complete checkout manually only if site terms allow it",
                        expiry_risk=decision.expiry_risk,
                    )
                    request_human_handoff(handoff)
                    _publish_final_report(
                        ui_state=ui_state,
                        target=target,
                        status=status,
                        final_state=sm.state,
                        decision={
                            "kind": "CHECKOUT_HANDOFF",
                            "message": "Checkout automation is not implemented",
                        },
                        ranked=ranked,
                        handoff=handoff,
                        price_changes=price_changes,
                    )
                    break

                retries = 0

            except KeyboardInterrupt:
                notify("Interrupted by user.")
                sm.transition(AgentState.ABORTED)
                ui_state["state"] = sm.state.value
                ui_state["decision"] = {"kind": "INTERRUPTED", "message": "Interrupted by user"}
                ui_state["final"] = True
                _append_ui_event(ui_state, "Interrupted by user")
                write_ui_state(ui_state)
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
                    ui_state["state"] = sm.state.value
                    ui_state["decision"] = {"kind": "ERROR", "message": f"Aborted after errors: {exc}"}
                    ui_state["final"] = True
                    _append_ui_event(ui_state, f"Aborted after {retries} errors")
                    write_ui_state(ui_state)
                    break
                time.sleep(3)
    except Exception as exc:
        logger.exception("Startup error: %s", exc)
        sm.transition(AgentState.ABORTED)
        ui_state["state"] = sm.state.value
        ui_state["decision"] = {"kind": "ERROR", "message": f"Startup error: {exc}"}
        ui_state["final"] = True
        _append_ui_event(ui_state, f"Startup error: {exc}")
        write_ui_state(ui_state)
    finally:
        browser.close()

    if dashboard is not None:
        _append_ui_event(ui_state, f"Final state: {sm.state.value}")
        write_ui_state(ui_state)
        _keep_dashboard_alive(dashboard)


def _extract_best_offer(
    snapshot_text: str,
    regex_extractor: RegexOfferExtractor,
    semantic_extractor: SemanticOfferExtractor,
) -> ParsedOffer | None:
    offers = regex_extractor.extract(snapshot_text)
    semantic_offers = []
    if not offers or max(offer.confidence for offer in offers) < settings.availability_confidence_threshold:
        semantic_offers = semantic_extractor.extract(snapshot_text)
    candidates = [*offers, *semantic_offers]
    if not candidates:
        return parse_offer_text(snapshot_text)

    parsed_by_key = {_offer_key(parsed): parsed for parsed in candidates}
    ranked = rank_offers([_parsed_to_offer(parsed, snapshot_text) for parsed in candidates])
    if not ranked:
        return max(candidates, key=lambda offer: offer.confidence)
    return parsed_by_key[_offer_key_from_offer(ranked[0][0])]


def _extract_ranked_offers(
    snapshot_text: str,
    regex_extractor: RegexOfferExtractor,
    semantic_extractor: SemanticOfferExtractor,
    target: MonitorTarget,
) -> list[tuple[Offer, PolicyDecision]]:
    parsed_offers = regex_extractor.extract(snapshot_text)
    semantic_offers = []
    if not parsed_offers or max(offer.confidence for offer in parsed_offers) < settings.availability_confidence_threshold:
        semantic_offers = semantic_extractor.extract(snapshot_text)
    candidates = [*parsed_offers, *semantic_offers]
    if not candidates:
        fallback = parse_offer_text(snapshot_text)
        candidates = [fallback] if fallback is not None else []
    offers = [_parsed_to_offer(parsed, snapshot_text, target) for parsed in candidates]
    return rank_offers(offers)


def _parsed_to_offer(
    parsed: ParsedOffer,
    snapshot_text: str,
    target: MonitorTarget | None = None,
) -> Offer:
    origin = _query_value(target.url, "fromcity") if target else settings.effective_target_origin
    destination = _query_value(target.url, "tocity") if target else settings.effective_target_destination
    return Offer(
        title=parsed.title,
        section=parsed.section,
        quantity=parsed.quantity,
        total_usd=parsed.total_usd,
        available_seats=parsed.available_seats,
        currency=parsed.currency or settings.normalized_price_currency,
        departure_time=parsed.departure_time,
        arrival_time=parsed.arrival_time,
        duration=parsed.duration,
        service_class=parsed.service_class,
        target_origin=origin or settings.effective_target_origin,
        target_destination=destination or settings.effective_target_destination,
        source_text=snapshot_text[:500],
        confidence=parsed.confidence,
    )


def _offer_key(parsed: ParsedOffer) -> tuple[str, str, int, float]:
    return (parsed.title, parsed.section, parsed.quantity, parsed.total_usd)


def _offer_key_from_offer(offer: Offer) -> tuple[str, str, int, float]:
    return (offer.title, offer.section, offer.quantity, offer.total_usd)


def _query_value(url: str, key: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(key)
    return values[0] if values else None


def _should_wait_for_trip_setup() -> bool:
    return settings.require_trip_setup or "example.com/events/sample" in settings.target_event_url


def _wait_for_trip_setup(ui_state: dict[str, Any]) -> TripRequest:
    announced = False
    while True:
        trip = load_trip_request()
        if trip is not None:
            ui_state["trip"] = asdict(trip)
            ui_state["trip_schedule"] = asdict(schedule_for_trip(trip))
            ui_state["decision"] = {
                "kind": "TRIP_SAVED",
                "message": f"Trip saved for {trip.from_city} -> {trip.to_city} on {trip.journey_date}",
            }
            _append_ui_event(ui_state, "Trip setup received")
            write_ui_state(ui_state)
            return trip

        ui_state["state"] = "WAITING_FOR_TRIP_SETUP"
        ui_state["decision"] = {
            "kind": "WAITING_FOR_TRIP_SETUP",
            "message": "Use the Trip Setup form to choose route, date, time frame, and price cap.",
        }
        ui_state["final"] = False
        if not announced:
            _append_ui_event(ui_state, "Waiting for trip setup from dashboard")
            announced = True
        write_ui_state(ui_state)
        time.sleep(2)


def _wait_for_monitoring_window(ui_state: dict[str, Any], trip: TripRequest) -> TripRequest:
    notified = False
    while True:
        latest_trip = load_trip_request() or trip
        schedule = schedule_for_trip(latest_trip)
        ui_state["trip"] = asdict(latest_trip)
        ui_state["trip_schedule"] = asdict(schedule)

        if schedule.should_monitor:
            if not notified:
                message = advance_monitoring_message(latest_trip, schedule)
                notify(message)
                _append_ui_event(ui_state, message)
                notified = True
            ui_state["decision"] = {
                "kind": "MONITORING_WINDOW_OPEN",
                "message": schedule.message,
            }
            _append_ui_event(ui_state, schedule.message)
            write_ui_state(ui_state)
            return latest_trip

        ui_state["state"] = "SCHEDULED"
        ui_state["decision"] = {
            "kind": "WAITING_FOR_MONITORING_WINDOW",
            "message": schedule.message,
        }
        ui_state["final"] = False
        if not notified:
            message = advance_monitoring_message(latest_trip, schedule)
            notify(message)
            _append_ui_event(ui_state, message)
            notified = True
        write_ui_state(ui_state)
        time.sleep(min(max(settings.poll_interval_seconds, 5), 300))


def _publish_poll_state(
    ui_state: dict[str, Any],
    target: MonitorTarget,
    status: AvailabilityStatus,
    state: AgentState,
    action: str,
    reason: str,
) -> None:
    ui_state["state"] = state.value
    ui_state["target"] = asdict(target)
    ui_state["status"] = _status_dict(status)
    ui_state["decision"] = {
        "kind": action.upper(),
        "message": reason,
    }
    ui_state["final"] = False
    _append_ui_event(ui_state, f"{target.id}: {status.state} -> {action}")
    write_ui_state(ui_state)


def _publish_final_report(
    ui_state: dict[str, Any],
    target: MonitorTarget,
    status: AvailabilityStatus,
    final_state: AgentState,
    decision: dict[str, Any],
    ranked: list[tuple[Offer, PolicyDecision]],
    handoff: HandoffBrief | None = None,
    price_changes: list[dict[str, Any]] | None = None,
    screenshot_path: str | None = None,
) -> None:
    top_items = _ranked_items(ranked[:settings.top_offer_limit])
    report = {
        **ui_state,
        "state": final_state.value,
        "target": asdict(target),
        "status": _status_dict(status),
        "decision": decision,
        "summary": _summary(ranked),
        "top_offers": top_items,
        "price_changes": price_changes or [],
        "handoff": _handoff_dict(handoff),
        "screenshot_path": screenshot_path,
        "final": True,
    }
    _append_ui_event(report, decision.get("message", final_state.value))
    write_offer_report(report)
    write_ui_state(report)
    ui_state.clear()
    ui_state.update(report)


def _ranked_items(ranked: list[tuple[Offer, PolicyDecision]]) -> list[dict[str, Any]]:
    return [
        {
            "offer": asdict(offer),
            "decision": asdict(decision),
        }
        for offer, decision in ranked
    ]


def _summary(ranked: list[tuple[Offer, PolicyDecision]]) -> dict[str, Any]:
    allowed = [(offer, decision) for offer, decision in ranked if decision.allowed]
    blocked = [(offer, decision) for offer, decision in ranked if not decision.allowed]
    lowest = min((offer.total_usd for offer, _ in ranked), default=None)
    return {
        "offers_scanned": len(ranked),
        "valid_offers": len(allowed),
        "blocked_offers": len(blocked),
        "best_allowed_fare": allowed[0][0].total_usd if allowed else None,
        "lowest_seen_fare": lowest,
        "max_total_price": settings.effective_max_total_price,
        "currency": ranked[0][0].currency if ranked else settings.normalized_price_currency,
    }


def _availability_notification(
    target: MonitorTarget,
    ranked: list[tuple[Offer, PolicyDecision]],
    decision: PolicyDecision,
    *,
    blocked: bool,
) -> str:
    best = ranked[0][0]
    route = target.label or target.route_or_event or target.url
    headline = "Tickets found but blocked by policy" if blocked else "Tickets available and policy-approved"
    lines = [
        headline,
        f"Target: {route}",
        f"Best offer: {best.title}",
        f"Route: {best.section}",
        f"Departure: {best.departure_time or 'unknown'}",
        f"Fare: {best.total_usd} {best.currency}",
        f"Seats: {best.available_seats if best.available_seats is not None else 'unknown'}",
        f"Score: {decision.score}/100",
        f"Policy: {decision.reason}",
        f"Expiry risk: {decision.expiry_risk}",
    ]
    alternatives = ranked[1:4]
    if alternatives:
        lines.append("Alternatives:")
        for index, (offer, alt_decision) in enumerate(alternatives, start=2):
            lines.append(
                f"{index}. {offer.title} | {offer.departure_time or 'unknown'} | "
                f"{offer.total_usd} {offer.currency} | score {alt_decision.score}"
            )
    if not blocked:
        lines.append("Action: Dry run/review mode. No payment was submitted.")
    return "\n".join(lines)


def _status_dict(status: AvailabilityStatus) -> dict[str, Any]:
    return {
        "state": status.state,
        "confidence": status.confidence,
        "signals": status.signals,
        "warnings": status.warnings,
    }


def _handoff_dict(handoff: HandoffBrief | None) -> dict[str, Any] | None:
    if handoff is None:
        return None
    data = asdict(handoff)
    data["message"] = handoff.to_message()
    return data


def _append_ui_event(ui_state: dict[str, Any], message: str) -> None:
    events = ui_state.setdefault("events", [])
    events.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "message": message})
    del events[:-100]


def _keep_dashboard_alive(dashboard: DashboardServer) -> None:
    if not settings.ui_enabled or not settings.ui_persist_after_run:
        dashboard.stop()
        return
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        dashboard.stop()


if __name__ == "__main__":
    main()
