from __future__ import annotations

import httpx

from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def notify(message: str) -> None:
    logger.info("NOTIFY: %s", message)

    if settings.discord_webhook_url:
        try:
            httpx.post(settings.discord_webhook_url, json={"content": message}, timeout=10.0)
        except Exception as exc:
            logger.warning("Discord notification failed: %s", exc)

    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            httpx.post(
                url,
                json={"chat_id": settings.telegram_chat_id, "text": message},
                timeout=10.0,
            )
        except Exception as exc:
            logger.warning("Telegram notification failed: %s", exc)
