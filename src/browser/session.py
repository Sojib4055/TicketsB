from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.browser.context import ensure_browser_profile_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BrowserSession:
    '''
    Thin wrapper around browser automation.

    Replace the internals of this class with the MCP client used by your host.
    For example, you may call tools like:
    - browser_navigate
    - browser_snapshot
    - browser_click
    - browser_type
    - browser_take_screenshot

    The rest of the app uses this wrapper instead of calling MCP tools directly.
    '''

    def __init__(self) -> None:
        self.connected = False
        self.current_url: str | None = None
        ensure_browser_profile_dir()

    def connect(self) -> None:
        self.connected = True
        logger.info("Connected to browser layer (stub).")

    def navigate(self, url: str) -> None:
        self.current_url = url
        logger.info("Navigate: %s", url)

    def snapshot(self) -> dict[str, Any]:
        # Stub output. Replace with real MCP snapshot response.
        return {
            "url": self.current_url,
            "text": "Sample Event | Tickets available now | 2 tickets from $75 each | Lower Bowl",
            "elements": [],
        }

    def snapshot_text(self) -> str:
        data = self.snapshot()
        return data.get("text", "")

    def click(self, semantic_target: str) -> None:
        logger.info("Click semantic target: %s", semantic_target)

    def type_text(self, semantic_target: str, value: str) -> None:
        logger.info("Type into %s value length=%s", semantic_target, len(value))

    def take_screenshot(self, name: str) -> Path:
        path = Path("logs/screenshots") / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"url": self.current_url, "name": name}, indent=2), encoding="utf-8")
        logger.info("Screenshot placeholder saved: %s", path)
        return path
