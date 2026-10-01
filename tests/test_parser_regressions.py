from unittest.mock import Mock

from src.browser.session import BrowserSession, BrowserToolError
from src.monitoring.availability_parser import parse_availability_text, parse_offer_texts

import pytest


def cards(second_fare='900', second_operator='Operator Two'):
    return f'''Operator One
1, Hino, Non AC
Route: Dhaka - Bogura
08:00 AM
02:00 PM
BDT 500
BOOK TICKET
10 Seats Available
{second_operator}
1, Hino, Non AC
Route: Dhaka - Bogura
10:00 AM
04:00 PM
BDT {second_fare}
BOOK TICKET
10 Seats Available'''


def test_bus_cards_keep_their_own_fares():
    offers = parse_offer_texts(cards())
    assert {o.title:o.total_usd for o in offers} == {'Operator One':500, 'Operator Two':900}


def test_same_operator_different_departures_are_preserved():
    offers = parse_offer_texts(cards('500', 'Operator One'))
    assert len(offers) == 2
    assert {o.departure_time for o in offers} == {'08:00 AM', '10:00 AM'}


@pytest.mark.parametrize('text', ['Tickets unavailable', '0 Seats Available | BDT 500', 'No seats available'])
def test_unavailable_is_not_available(text):
    assert parse_availability_text(text).state != 'available'


def test_zero_seat_bus_page_does_not_fall_back_to_generic_offer():
    assert parse_offer_texts(cards().replace('10 Seats Available', '0 Seats Available')) == []


def test_mcp_error_result_is_raised_without_replaying_click():
    browser = BrowserSession.__new__(BrowserSession)
    browser.connected = True
    browser._loop = None
    browser._call_tool_async = Mock(return_value=None)
    browser._run_async = Mock(return_value={'isError':True, 'content':[]})
    with pytest.raises(BrowserToolError):
        browser._call_tool('browser_click', {'ref':'e1'})
    assert browser._run_async.call_count == 1
