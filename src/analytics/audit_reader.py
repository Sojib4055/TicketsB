from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.utils.audit import EVENT_PATH


def iter_audit_events(path: Path = EVENT_PATH) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                yield event


def load_audit_events(path: Path = EVENT_PATH) -> list[dict[str, Any]]:
    return list(iter_audit_events(path))
