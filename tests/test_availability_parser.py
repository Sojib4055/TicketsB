from src.monitoring.availability_parser import parse_availability_text, parse_offer_text


def test_parse_available():
    status = parse_availability_text("Tickets available now")
    assert status.state == "available"


def test_parse_sold_out():
    status = parse_availability_text("Sold Out")
    assert status.state == "sold_out"


def test_parse_offer_from_snapshot_text():
    parsed = parse_offer_text("Sample Event | Tickets available now | 2 tickets from $75 each | Lower Bowl")

    assert parsed is not None
    assert parsed.title == "Sample Event"
    assert parsed.section == "Lower Bowl"
    assert parsed.quantity == 2
    assert parsed.total_usd == 150.0


def test_parse_shohoz_bus_offer_from_snapshot_text():
    parsed = parse_offer_text(
        """
        Bus Tickets from Dhaka
        Filters
        Shalki Classic
        1, Hino, Non AC
        Route: Dhaka - Bogura
        08:30 AM
        Dhaka
        05:00 PM
        Bogura
        \u09f31,000
        \u09f3750
        BOOK TICKET
        36 Seat(s) Available
        Get 250 TK Discount
        """
    )

    assert parsed is not None
    assert parsed.title == "Shalki Classic"
    assert parsed.section == "Route: Dhaka - Bogura"
    assert parsed.quantity == 1
    assert parsed.total_usd == 750.0
    assert parsed.available_seats == 36
