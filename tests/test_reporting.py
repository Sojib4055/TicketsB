from src.reports.reporting import build_initial_ui_state


def test_initial_ui_state_is_dashboard_ready():
    state = build_initial_ui_state("http://127.0.0.1:8765")

    assert state["dashboard_url"] == "http://127.0.0.1:8765"
    assert state["top_offers"] == []
    assert state["summary"]["offers_scanned"] == 0
