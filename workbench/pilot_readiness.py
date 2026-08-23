# -*- coding: utf-8 -*-
"""Offline readiness checks for a packaged pilot release.

The checks intentionally avoid logging in to, scraping, or mutating the recruitment
platform. They verify that the distributed executable contains the required runtime,
can write its local data, can migrate/backup/restore SQLite, and can load product
settings. Real account and page-compatibility checks remain part of field acceptance.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .browser_runtime import configure_packaged_browser_path
from .database import WorkbenchDB, default_data_dir
from .db_schema import SCHEMA_VERSION
from .evaluation import build_requirement_profile
from .models import ProfileStatus
from .settings import AppSettings, load_settings, save_settings

APP_VERSION = "0.9.1"


def _result(name: str, passed: bool, detail: str, *, required: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "required": bool(required),
        "detail": str(detail),
    }


def _run_check(
    results: list[dict[str, Any]],
    name: str,
    callback: Callable[[], str],
    *,
    required: bool = True,
) -> None:
    try:
        detail = callback()
    except Exception as error:  # readiness output must contain the failure, not crash
        results.append(_result(name, False, f"{type(error).__name__}: {error}", required=required))
    else:
        results.append(_result(name, True, detail, required=required))


def _check_data_directory(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".readiness-write-test"
    marker.write_text("ok", encoding="utf-8")
    if marker.read_text(encoding="utf-8") != "ok":
        raise RuntimeError("written marker could not be read back")
    marker.unlink(missing_ok=True)
    return f"writable: {root}"


def _check_database_roundtrip(root: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="rw-readiness-", dir=str(root)) as temp:
        temp_path = Path(temp)
        database_path = temp_path / "pilot.db"
        backup_path = temp_path / "pilot-backup.db"
        db = WorkbenchDB(database_path)
        job_id = db.create_job("交付自检岗位", "Java", "本科及以上，至少3年经验。")
        profile = build_requirement_profile(
            keyword="Java",
            jd="本科及以上，至少3年经验。",
            min_education="本科",
            min_experience_years=3,
        )
        db.update_job(
            job_id,
            profile=profile,
            profile_status=ProfileStatus.DRAFT,
        )
        db.confirm_job_profile(job_id, confirmed_by="pilot-self-test")
        db.backup_to(backup_path)
        if not backup_path.is_file() or backup_path.stat().st_size == 0:
            raise RuntimeError("database backup was not created")
        db.delete_job(job_id)
        if db.get_job(job_id) is not None:
            raise RuntimeError("database mutation did not take effect")
        db.restore_from(backup_path)
        restored = db.get_job(job_id)
        if not restored:
            raise RuntimeError("database restore did not recover the job")
        if restored.get("profile_status") != ProfileStatus.CONFIRMED.value:
            raise RuntimeError("restored profile confirmation state is invalid")
        with db.connect() as conn:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError(f"integrity_check={integrity}")
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"schema version {version}, expected {SCHEMA_VERSION}")
        return f"SQLite backup/restore OK; schema={version}"


def _check_settings_roundtrip(root: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="rw-settings-", dir=str(root)) as temp:
        path = Path(temp) / "settings.json"
        expected = AppSettings(
            browser_mode="managed",
            browser_visible=True,
            sidecar_enabled=True,
            slow_mo_ms=40,
            default_max_pages=5,
            default_max_count=200,
            data_retention_days=180,
        ).normalized()
        save_settings(expected, path)
        actual = load_settings(path)
        if actual != expected:
            raise RuntimeError("settings round-trip mismatch")
        return "settings read/write OK"


def _check_browser_runtime() -> str:
    packaged = configure_packaged_browser_path()
    configured = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")) if os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH"
    ) else None
    root = packaged or configured
    if root is None:
        # Source mode is allowed to rely on Playwright's standard cache. Importing the
        # package still proves the Python runtime is present; actual browser launch is a
        # field or packaging gate.
        import playwright  # noqa: F401

        return "source mode: Playwright import OK"
    if not root.is_dir():
        raise RuntimeError(f"configured browser directory does not exist: {root}")
    chromium_dirs = [
        item for item in root.iterdir()
        if item.is_dir() and item.name.lower().startswith(("chromium-", "chromium_headless_shell-"))
    ]
    if not chromium_dirs:
        raise RuntimeError(f"no packaged Chromium revision found in {root}")
    return f"packaged Chromium found: {chromium_dirs[0].name}"


def run_readiness_checks(data_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    root = Path(data_root) if data_root else default_data_dir()
    results: list[dict[str, Any]] = []
    _run_check(results, "local_data_directory", lambda: _check_data_directory(root))
    _run_check(results, "sqlite_backup_restore", lambda: _check_database_roundtrip(root))
    _run_check(results, "settings_roundtrip", lambda: _check_settings_roundtrip(root))
    _run_check(results, "browser_runtime", _check_browser_runtime)

    required_failures = [item for item in results if item["required"] and not item["passed"]]
    return {
        "product": "Recruitment Workbench",
        "version": APP_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall": "PASS" if not required_failures else "FAIL",
        "field_validation_required": True,
        "environment": {
            "frozen": bool(getattr(sys, "frozen", False)),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executable": sys.executable,
            "data_root": str(root),
            "schema_version": SCHEMA_VERSION,
        },
        "checks": results,
        "remaining_field_gates": [
            "authorized Zhilian login",
            "real search repeated runs",
            "candidate UID and selector stability",
            "enterprise proxy/certificate/security software",
            "manual takeover and browser recovery",
            "signed installer and upgrade/rollback",
            "data authorization, retention and platform-rule review",
        ],
    }


def write_readiness_report(
    path: str | os.PathLike[str],
    *,
    data_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    report = run_readiness_checks(data_root=data_root)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)
    return report


__all__ = ["APP_VERSION", "run_readiness_checks", "write_readiness_report"]
