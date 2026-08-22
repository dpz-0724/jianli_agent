# -*- coding: utf-8 -*-
"""Preflight checks for support and deployment."""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import sqlite3
import sys
import tempfile
from pathlib import Path

from .database import default_data_dir


def _find_chrome() -> str | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    return str(next((path for path in candidates if path.is_file()), "")) or None


def run_healthcheck() -> dict:
    data_dir = default_data_dir()
    result = {
        "ok": True,
        "python": sys.version,
        "platform": platform.platform(),
        "playwright_installed": importlib.util.find_spec("playwright") is not None,
        "browser_path": _find_chrome(),
        "data_dir": str(data_dir),
        "data_dir_writable": False,
        "sqlite_ok": False,
        "checks": [],
    }
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, delete=True):
            pass
        result["data_dir_writable"] = True
    except Exception as error:
        result["checks"].append({"name": "data_dir", "ok": False, "error": str(error)})
        result["ok"] = False

    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT 1").fetchone()
        conn.close()
        result["sqlite_ok"] = True
    except Exception as error:
        result["checks"].append({"name": "sqlite", "ok": False, "error": str(error)})
        result["ok"] = False

    if not result["playwright_installed"]:
        result["checks"].append({"name": "playwright", "ok": False, "error": "未安装 Playwright"})
        result["ok"] = False
    if not result["browser_path"]:
        result["checks"].append(
            {
                "name": "browser",
                "ok": False,
                "error": "未发现系统 Chrome/Edge；可执行 playwright install chromium 安装后备浏览器",
            }
        )
    return result


def main() -> int:
    result = run_healthcheck()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
