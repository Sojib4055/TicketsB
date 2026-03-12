from __future__ import annotations

import time
from collections.abc import Iterator

from src.browser.session import BrowserSession
from src.monitoring.availability_parser import AvailabilityStatus, parse_availability_text


def watch(browser: BrowserSession, interval_seconds: int = 30) -> Iterator[AvailabilityStatus]:
    while True:
        text = browser.snapshot_text()
        yield parse_availability_text(text)
        time.sleep(interval_seconds)
