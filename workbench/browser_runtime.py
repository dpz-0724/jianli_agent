# -*- coding: utf-8 -*-
"""Managed Playwright browser runtime discovery and packaging helpers."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .database import default_data_dir


def configure_packaged_browser_path() -> Path | None:
    """Point Playwright at the Chromium folder shipped by an onedir build."""
    if not getattr(sys, "frozen", False):
        return None
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidates = [root / "runtime-browsers", Path(sys.executable).parent / "runtime-browsers"]
    for candidate in candidates:
        if candidate.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return candidate
    return None


def browser_profile_dir(mode: str = "managed") -> Path:
    safe_mode = "".join(ch for ch in (mode or "managed") if ch.isalnum() or ch in "-_" ) or "managed"
    return default_data_dir() / "browser_profiles" / safe_mode


def clear_browser_profiles() -> None:
    root = default_data_dir() / "browser_profiles"
    if root.exists():
        shutil.rmtree(root)


def runtime_summary(settings: Any) -> dict[str, Any]:
    packaged = configure_packaged_browser_path()
    custom = Path(str(getattr(settings, "custom_browser_path", "") or ""))
    return {
        "mode": str(getattr(settings, "browser_mode", "managed")),
        "packaged_browser_path": str(packaged or ""),
        "custom_browser_exists": bool(custom.is_file()) if str(custom) else False,
        "profile_root": str(default_data_dir() / "browser_profiles"),
        "playwright_browser_path": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
    }
