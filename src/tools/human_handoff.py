from __future__ import annotations

from src.models import HandoffBrief
from src.tools.notifier import notify
from src.utils.logger import get_logger

logger = get_logger(__name__)


def request_human_handoff(reason: str | HandoffBrief) -> None:
    if isinstance(reason, HandoffBrief):
        message = reason.to_message()
        logger.warning("HUMAN HANDOFF: %s", reason.reason)
        notify(message)
        return

    logger.warning("HUMAN HANDOFF: %s", reason)
    notify(f"HUMAN HANDOFF REQUIRED: {reason}")
