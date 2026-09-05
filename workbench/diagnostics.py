# -*- coding: utf-8 -*-
"""Best-effort failure diagnostics for browser automation runs."""
from __future__ import annotations

import json
import os
import platform
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import default_data_dir


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:80]


def diagnostics_root() -> Path:
    root = default_data_dir() / "diagnostics"
    root.mkdir(parents=True, exist_ok=True)
    return root


def capture_failure(
    *,
    run_id: int | str,
    request_id: str,
    error_code: str,
    error: BaseException,
    bot: Any | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = diagnostics_root() / f"run-{_safe_name(str(run_id))}-{stamp}"
    folder.mkdir(parents=True, exist_ok=True)

    page = getattr(bot, "page", None) if bot is not None else None
    context = getattr(bot, "_context", None) if bot is not None else None
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "request_id": request_id,
        "error_code": error_code,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": traceback.format_exc(),
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pid": os.getpid(),
        "extra": extra or {},
    }

    if page is not None:
        try:
            metadata["url"] = page.url
        except Exception:
            pass
        try:
            metadata["title"] = page.title()
        except Exception:
            pass
        try:
            page.screenshot(path=str(folder / "screenshot.png"), full_page=True)
        except Exception as screenshot_error:
            metadata["screenshot_error"] = str(screenshot_error)
        try:
            (folder / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception as content_error:
            metadata["content_error"] = str(content_error)

    if context is not None:
        try:
            context.tracing.stop(path=str(folder / "trace.zip"))
            metadata["trace_saved"] = True
        except Exception as trace_error:
            metadata["trace_error"] = str(trace_error)

    (folder / "error.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(folder)
