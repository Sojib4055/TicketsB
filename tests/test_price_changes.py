from src.analytics.price_changes import detect_price_changes


def test_detect_price_drop_and_seat_change():
    previous = {
        "top_offers": [
            {
                "offer": {
                    "title": "Operator A",
                    "section": "Route: Dhaka - Bogura",
                    "total_usd": 600,
                    "available_seats": 10,
                    "currency": "BDT",
                }
            }
        ]
    }
    current = [
        {
            "offer": {
                "title": "Operator A",
                "section": "Route: Dhaka - Bogura",
                "total_usd": 520,
                "available_seats": 8,
                "currency": "BDT",
            }
        }
    ]

    changes = detect_price_changes(previous, current)

    assert any(change["type"] == "price_dropped" for change in changes)
    assert any(change["type"] == "seat_count_changed" for change in changes)
