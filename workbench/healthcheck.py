# -*- coding: utf-8 -*-
"""Preflight checks for deployment, support and Pilot acceptance."""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import sqlite3
import sys
import tempfile
from pathlib import Path

from .browser_runtime import configure_packaged_browser_path
from .database import WorkbenchDB, default_data_dir
from .db_schema import SCHEMA_VERSION


def _find_system_browser() -> str | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    return str(next((path for path in candidates if path.is_file()), "")) or None


def _managed_browser_path() -> str | None:
    if importlib.util.find_spec("playwright") is None:
        return None
    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            path = Path(playwright.chromium.executable_path)
            return str(path) if path.is_file() else None
        finally:
            playwright.stop()
    except Exception:
        return None


def run_healthcheck() -> dict:
    data_dir = default_data_dir()
    packaged = configure_packaged_browser_path()
    result = {
        "ok": True,
        "python": sys.version,
        "platform": platform.platform(),
        "playwright_installed": importlib.util.find_spec("playwright") is not None,
        "pyside6_installed": importlib.util.find_spec("PySide6") is not None,
        "managed_browser_path": _managed_browser_path(),
        "packaged_browser_path": str(packaged or ""),
        "system_browser_path": _find_system_browser(),
        "data_dir": str(data_dir),
        "data_dir_writable": False,
        "sqlite_ok": False,
        "schema_version": None,
        "backup_restore_ok": False,
        "checks": [],
    }

    def fail(name: str, error: Exception | str) -> None:
        result["checks"].append({"name": name, "ok": False, "error": str(error)})
        result["ok"] = False

    def warn(name: str, message: str) -> None:
        result["checks"].append({"name": name, "ok": True, "warning": message})

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, delete=True):
            pass
        result["data_dir_writable"] = True
    except Exception as error:
        fail("data_dir", error)

    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT 1").fetchone()
        conn.close()
        result["sqlite_ok"] = True
    except Exception as error:
        fail("sqlite", error)

    if not result["playwright_installed"]:
        fail("playwright", "未安装 Playwright")
    if not result["pyside6_installed"]:
        fail("pyside6", "未安装 PySide6")

    if not result["managed_browser_path"] and not result["system_browser_path"]:
        warn(
            "browser",
            "当前环境未发现可执行浏览器。源码环境请执行 playwright install chromium；发布包应携带 runtime-browsers。",
        )

    try:
        with tempfile.TemporaryDirectory(dir=data_dir) as temp_dir:
            root = Path(temp_dir)
            db = WorkbenchDB(root / "healthcheck.db")
            db.create_job("健康检查岗位", "healthcheck", "")
            backup = db.backup_to(root / "healthcheck-backup.db")
            db.create_job("待回滚岗位", "temporary", "")
            db.restore_from(backup)
            jobs = db.list_jobs()
            if [job["title"] for job in jobs] != ["健康检查岗位"]:
                raise RuntimeError("备份恢复后的岗位数据不一致")
            with db.connect() as conn:
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0]).lower()
            if integrity != "ok":
                raise RuntimeError(f"数据库完整性检查失败：{integrity}")
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"数据库版本不一致：{version} != {SCHEMA_VERSION}")
            result["schema_version"] = version
            result["backup_restore_ok"] = True
    except Exception as error:
        fail("database_delivery", error)

    return result


def main() -> int:
    result = run_healthcheck()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
