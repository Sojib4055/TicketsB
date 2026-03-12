from src.monitoring.availability_parser import parse_availability_text


def test_parse_available():
    status = parse_availability_text("Tickets available now")
    assert status.state == "available"


def test_parse_sold_out():
    status = parse_availability_text("Sold Out")
    assert status.state == "sold_out"
