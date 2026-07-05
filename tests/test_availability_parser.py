from src.monitoring.availability_parser import parse_availability_text, parse_offer_text, parse_offer_texts


def test_parse_available():
    status = parse_availability_text("Tickets available now")
    assert status.state == "available"
    assert status.confidence >= 0.75
    assert "tickets available" in status.signals


def test_parse_sold_out():
    status = parse_availability_text("Sold Out")
    assert status.state == "sold_out"


def test_no_tickets_available_is_sold_out_not_available():
    status = parse_availability_text("No tickets available")
    assert status.state == "sold_out"
    assert status.confidence >= 0.75


def test_parse_offer_from_snapshot_text():
    parsed = parse_offer_text("Sample Event | Tickets available now | 2 tickets from $75 each | Lower Bowl")

    assert parsed is not None
    assert parsed.title == "Sample Event"
    assert parsed.section == "Lower Bowl"
    assert parsed.quantity == 2
    assert parsed.total_usd == 150.0
    assert parsed.confidence >= 0.75


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
    assert parsed.currency == "BDT"
    assert parsed.departure_time == "08:30 AM"
    assert parsed.arrival_time == "05:00 PM"
    assert parsed.service_class == "1, Hino, Non AC"
    assert "available_seats" in parsed.signals


def test_parse_shohoz_snapshot_wrapper_does_not_accept_page_header_or_zero_fare():
    parsed = parse_offer_text(
        """
        ### Page
        - Page URL: https://www.shohoz.com/bus-tickets/booking/bus/search?fromcity=Dhaka&tocity=Bogura
        - Console: 0 errors, 1 warnings
        ### Snapshot
        ```yaml
        - generic [ref=e238]: Shalki Classic
        - generic [ref=e239]: 1, Hino, Non AC
        - generic [ref=e240]: "Route: Dhaka - Bogura"
        - generic [ref=e259]: \u09f31,000
        - generic [ref=e260]: \u09f3750
        - button "Book Ticket" [ref=e262] [cursor=pointer]
        - generic [ref=e263]: 29 Seat(s) Available
        - generic [ref=e269]: Get 250 TK Discount
        ```
        """
    )

    assert parsed is not None
    assert parsed.title == "Shalki Classic"
    assert parsed.total_usd == 750.0
    assert parsed.total_usd > 0
    assert parsed.booking_ref == "e262"


def test_parse_shohoz_snapshot_extracts_multiple_positive_offers():
    offers = parse_offer_texts(
        """
        - generic [ref=e238]: Shalki Classic
        - generic [ref=e239]: 1, Hino, Non AC
        - generic [ref=e240]: "Route: Dhaka - Bogura"
        - generic [ref=e259]: \u09f31,000
        - generic [ref=e260]: \u09f3750
        - button "Book Ticket" [ref=e262] [cursor=pointer]
        - generic [ref=e263]: 29 Seat(s) Available
        - generic [ref=e286]: Burimari Express
        - generic [ref=e287]: 12, Sleeper Premium AC, AC
        - generic [ref=e288]: "Route: Dhaka - Rangpur"
        - generic [ref=e307]: \u09f31,500
        - generic [ref=e308]: \u09f31300
        - button "Book Ticket" [ref=e313] [cursor=pointer]
        - generic [ref=e314]: 0 Seat(s) Available
        - generic [ref=e385]: Manik Express
        - generic [ref=e386]: 32, Business Class , AC Bullet
        - generic [ref=e387]: "Route: Dhaka - Bogura"
        - generic [ref=e406]: \u09f3900
        - generic [ref=e407]: \u09f3800
        - button "Book Ticket" [ref=e409] [cursor=pointer]
        - generic [ref=e410]: 16 Seat(s) Available
        """
    )

    assert len(offers) == 2
    assert all(offer.title != "### Page" for offer in offers)
    assert all(offer.total_usd > 0 for offer in offers)
    assert all((offer.available_seats or 0) > 0 for offer in offers)
    assert {offer.title: offer.booking_ref for offer in offers} == {"Shalki Classic": "e262", "Manik Express": "e409"}
