from __future__ import annotations

from src.tools.notifier import notify
from src.utils.logger import get_logger

logger = get_logger(__name__)


def request_human_handoff(reason: str) -> None:
    logger.warning("HUMAN HANDOFF: %s", reason)
    notify(f"HUMAN HANDOFF REQUIRED: {reason}")
