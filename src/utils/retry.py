from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_fixed


def default_retry():
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
