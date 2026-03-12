from __future__ import annotations

from pathlib import Path

BROWSER_DATA_DIR = Path("browser_data/user_profile")


def ensure_browser_profile_dir() -> Path:
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return BROWSER_DATA_DIR
