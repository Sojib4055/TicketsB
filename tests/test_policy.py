from src.config import settings
from src.policy import Offer, evaluate_offer


def test_policy_allows_reasonable_offer():
    offer = Offer(title="Concert", section="Lower Bowl", quantity=2, total_usd=100.0)
    decision = evaluate_offer(offer)
    assert decision.allowed is True
    assert decision.score > 0
    assert decision.hard_blocks == []


def test_policy_blocks_expensive_offer():
    offer = Offer(title="Concert", section="Lower Bowl", quantity=2, total_usd=10_000.0)
    decision = evaluate_offer(offer)
    assert decision.allowed is False
    assert decision.score == 0
    assert decision.hard_blocks


def test_policy_blocks_zero_price_offer():
    offer = Offer(title="Bus", section="Route: Dhaka - Bogura", quantity=1, total_usd=0.0)
    decision = evaluate_offer(offer)
    assert decision.allowed is False
    assert "greater than zero" in decision.reason


def test_policy_uses_currency_neutral_price_cap():
    original_max_total_price = settings.max_total_price
    original_price_currency = settings.price_currency
    settings.max_total_price = 500.0
    settings.price_currency = "BDT"
    try:
        decision = evaluate_offer(
            Offer(title="Bus", section="Route: Dhaka - Bogura", quantity=1, total_usd=520.0)
        )
    finally:
        settings.max_total_price = original_max_total_price
        settings.price_currency = original_price_currency

    assert decision.allowed is False
    assert "MAX_TOTAL_PRICE=500.0 BDT" in decision.reason


def test_policy_scores_route_operator_and_departure_preferences():
    original_values = {
        "max_total_price": settings.max_total_price,
        "preferred_operators": settings.preferred_operators,
        "preferred_departure_start": settings.preferred_departure_start,
        "preferred_departure_end": settings.preferred_departure_end,
        "target_origin": settings.target_origin,
        "target_destination": settings.target_destination,
        "avoid_night_buses": settings.avoid_night_buses,
    }
    settings.max_total_price = 1000.0
    settings.preferred_operators = "Shyamoli"
    settings.preferred_departure_start = "06:00 AM"
    settings.preferred_departure_end = "10:00 AM"
    settings.target_origin = "Dhaka"
    settings.target_destination = "Bogura"
    settings.avoid_night_buses = True
    try:
        decision = evaluate_offer(
            Offer(
                title="SHYAMOLI PARIBAHAN",
                section="Route: Dhaka - Bogura",
                quantity=1,
                total_usd=520.0,
                available_seats=40,
                departure_time="08:30 AM",
                confidence=0.96,
            )
        )
    finally:
        for key, value in original_values.items():
            setattr(settings, key, value)

    assert decision.allowed is True
    assert decision.score >= 90
    assert "direct route match" in decision.preference_matches
    assert "preferred operator match" in decision.preference_matches
    assert "preferred departure window" in decision.preference_matches
