# -*- coding: utf-8 -*-
"""Persistent product settings stored outside the source tree."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .database import default_data_dir


@dataclass
class AppSettings:
    browser_mode: str = "managed"
    custom_browser_path: str = ""
    browser_visible: bool = True
    sidecar_enabled: bool = True
    slow_mo_ms: int = 40
    default_max_pages: int = 5
    default_max_count: int = 200
    data_retention_days: int = 180

    def normalized(self) -> "AppSettings":
        allowed = {"managed", "edge", "chrome", "custom", "auto"}
        mode = self.browser_mode.lower().strip()
        return AppSettings(
            browser_mode=mode if mode in allowed else "managed",
            custom_browser_path=self.custom_browser_path.strip(),
            browser_visible=bool(self.browser_visible),
            sidecar_enabled=bool(self.sidecar_enabled),
            slow_mo_ms=max(0, min(int(self.slow_mo_ms), 2000)),
            default_max_pages=max(1, min(int(self.default_max_pages), 20)),
            default_max_count=max(1, min(int(self.default_max_count), 2000)),
            data_retention_days=max(1, min(int(self.data_retention_days), 3650)),
        )


SETTINGS_PATH = default_data_dir() / "settings.json"


def load_settings(path: str | Path | None = None) -> AppSettings:
    target = Path(path) if path else SETTINGS_PATH
    if not target.exists():
        return AppSettings()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return AppSettings(**{key: payload[key] for key in AppSettings.__dataclass_fields__ if key in payload}).normalized()
    except Exception:
        return AppSettings()


def save_settings(settings: AppSettings, path: str | Path | None = None) -> Path:
    target = Path(path) if path else SETTINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = settings.normalized()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(normalized), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target
