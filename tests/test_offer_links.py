from src.main import _offer_notification, _parsed_to_offer
from src.policy import evaluate_offer
from src.models import MonitorTarget, ParsedOffer


def test_offer_booking_url_falls_back_to_target_url():
    target = MonitorTarget(
        id="shohoz-dhk-bog",
        url="https://www.shohoz.com/bus-tickets/booking/bus/search?fromcity=Dhaka&tocity=Bogura",
    )
    parsed = ParsedOffer(
        title="SHYAMOLI PARIBAHAN",
        section="Route: Dhaka - Bogura",
        quantity=1,
        total_usd=460.0,
        currency="BDT",
        booking_ref="e262",
    )

    offer = _parsed_to_offer(parsed, "snapshot", target)

    assert offer.booking_url == target.url
    assert offer.payment_url == ""
    assert offer.booking_ref == "e262"


def test_offer_preserves_provider_payment_url_when_available():
    target = MonitorTarget(id="shohoz-dhk-bog", url="https://www.shohoz.com/search")
    parsed = ParsedOffer(
        title="SHYAMOLI PARIBAHAN",
        section="Route: Dhaka - Bogura",
        quantity=1,
        total_usd=460.0,
        currency="BDT",
        booking_url="https://www.shohoz.com/bus-tickets/booking/bus/search?fromcity=Dhaka&tocity=Bogura",
        payment_url="https://www.shohoz.com/payment/review/example",
    )

    offer = _parsed_to_offer(parsed, "snapshot", target)

    assert offer.booking_url == parsed.booking_url
    assert offer.payment_url == parsed.payment_url


def test_offer_notification_contains_best_and_nearby_links():
    target = MonitorTarget(id="shohoz-dhk-bog", url="https://www.shohoz.com/search?fromcity=Dhaka&tocity=Bogura")
    parsed_items = [
        ParsedOffer(title="SHYAMOLI PARIBAHAN", section="Route: Dhaka - Bogura", quantity=1, total_usd=460.0, currency="BDT"),
        ParsedOffer(title="Hanif Enterprise", section="Route: Dhaka - Bogura", quantity=1, total_usd=480.0, currency="BDT"),
        ParsedOffer(title="Blue Line Express", section="Route: Dhaka - Bogura", quantity=1, total_usd=500.0, currency="BDT"),
    ]
    offers = [_parsed_to_offer(parsed, "snapshot", target) for parsed in parsed_items]
    ranked = [(offer, evaluate_offer(offer)) for offer in offers]

    notification = _offer_notification(ranked)

    assert notification is not None
    assert notification["title"] == "Best offer allowed: SHYAMOLI PARIBAHAN at 460.0 BDT"
    assert notification["best_offer"]["link_url"] == target.url
    assert notification["best_offer"]["link_label"] == "Open booking/search page"
    assert notification["best_offer"]["open_action_label"] == "Open seat selection"
    assert notification["best_offer"]["can_open_in_browser"] is True
    assert len(notification["nearby_offers"]) == 2
    assert all(item["link_url"] == target.url for item in notification["nearby_offers"])
