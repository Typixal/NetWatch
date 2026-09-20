"""Every filesystem path NetWatch uses.

Nothing else in the codebase constructs a path. Keeping it in one module is
what keeps the C-drive discipline enforceable: all runtime data lives under
``%LOCALAPPDATA%\\NetWatch\\`` and nowhere else.

Set ``NETWATCH_DATA_DIR`` to override the base directory (used by tests).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

APP_NAME = "NetWatch"


def _base() -> Path:
    override = os.environ.get("NETWATCH_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return root / APP_NAME


def app_dir() -> Path:
    d = _base()
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_dir() / "config.json"


def blocklist_path() -> Path:
    return app_dir() / "blocklist.json"


def log_dir() -> Path:
    d = app_dir() / "logs"
    d.mkdir(exist_ok=True)
    return d


def log_path_for(day: date) -> Path:
    return log_dir() / f"{day.isoformat()}.jsonl"


def today_log_path() -> Path:
    return log_path_for(date.today())


def cache_dir() -> Path:
    d = app_dir() / "cache"
    d.mkdir(exist_ok=True)
    return d


def dns_cache_path() -> Path:
    return cache_dir() / "dns_cache.json"


def asset_path(*parts: str) -> Path:
    """Path to a bundled asset, working both frozen and from source.

    PyInstaller unpacks ``--add-data`` payloads into ``sys._MEIPASS``; in a
    source checkout the assets sit next to the project root instead.
    """
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    root = Path(meipass) if meipass else Path(__file__).resolve().parents[3]
    return root.joinpath("assets", *parts)
