# -*- coding: utf-8 -*-
"""Product browser adapter for visible, controllable Zhilian automation.

The adapter keeps the existing page parser isolated behind a managed browser strategy:
Playwright Chromium by default, then Microsoft Edge / Google Chrome channels as explicit
fallbacks. It deliberately avoids fixed user-agent strings and anti-detection switches.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from .browser_runtime import browser_profile_dir, configure_packaged_browser_path

ROOT_DIR = Path(__file__).resolve().parents[1]
LEGACY_CODE_DIR = ROOT_DIR / "code"
if str(LEGACY_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_CODE_DIR))

from searcher import CandidateSearcher, _candidate_dedup_key  # noqa: E402


class SearchCancelled(RuntimeError):
    pass


class ProductCandidateSearcher(CandidateSearcher):
    def __init__(self, config: dict[str, Any] | None = None, db=None):
        super().__init__(config or {}, db)
        self.active_browser_mode = ""
        self._last_launch_error = ""

    @staticmethod
    def _attempts(mode: str, custom_path: str = "") -> list[tuple[str, dict[str, Any]]]:
        managed = ("managed", {})
        edge = ("edge", {"channel": "msedge"})
        chrome = ("chrome", {"channel": "chrome"})
        custom = ("custom", {"executable_path": custom_path})
        mode = (mode or "managed").lower()
        if mode == "edge":
            return [edge, managed, chrome]
        if mode == "chrome":
            return [chrome, managed, edge]
        if mode == "custom" and custom_path:
            return [custom, managed, edge, chrome]
        if mode == "auto":
            return [managed, edge, chrome]
        return [managed, edge, chrome]

    def launch(self):
        if self._context is not None:
            self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
            return self.page

        configure_packaged_browser_path()
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        requested = str(self.cfg.get("browser_mode") or "managed")
        custom_path = str(self.cfg.get("custom_browser_path") or self.cfg.get("chrome_path") or "")
        visible = bool(self.cfg.get("browser_visible", True))
        slow_mo = max(0, min(int(self.cfg.get("slow_mo_ms", 0) or 0), 2000))
        bounds = self.cfg.get("window_bounds") or {}

        common: dict[str, Any] = {
            "headless": False,
            "locale": "zh-CN",
            "no_viewport": True,
            "slow_mo": slow_mo,
            "args": [],
        }
        if bounds:
            x, y = int(bounds.get("x", 0)), int(bounds.get("y", 0))
            width, height = int(bounds.get("width", 1200)), int(bounds.get("height", 850))
            common["args"].extend([f"--window-position={x},{y}", f"--window-size={width},{height}"])
        else:
            common["args"].append("--start-maximized")
        if not visible:
            common["args"].append("--window-position=-2400,-2400")

        errors: list[str] = []
        for mode, override in self._attempts(requested, custom_path):
            if mode == "custom" and not Path(custom_path).is_file():
                errors.append(f"custom: 文件不存在 {custom_path}")
                continue
            profile = browser_profile_dir(mode)
            profile.mkdir(parents=True, exist_ok=True)
            kwargs = dict(common)
            kwargs["args"] = list(common["args"])
            kwargs.update(override)
            try:
                self._context = self._pw.chromium.launch_persistent_context(str(profile), **kwargs)
                self.active_browser_mode = mode
                break
            except Exception as error:
                errors.append(f"{mode}: {error}")
                self._context = None

        if self._context is None:
            try:
                self._pw.stop()
            finally:
                self._pw = None
            self._last_launch_error = "\n".join(errors)
            raise RuntimeError(
                "无法启动受控浏览器。请运行 setup.bat 安装工作台 Chromium，或在设置中选择 Edge/Chrome。\n"
                + self._last_launch_error
            )

        self._context.set_default_timeout(int(self.cfg.get("default_timeout_ms", 20000)))
        self._context.set_default_navigation_timeout(int(self.cfg.get("navigation_timeout_ms", 45000)))
        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self.page

    def browser_info(self) -> dict[str, Any]:
        version = ""
        try:
            browser = self._context.browser if self._context is not None else None
            version = browser.version if browser is not None else ""
        except Exception:
            pass
        return {
            "running": self._context is not None,
            "mode": self.active_browser_mode or str(self.cfg.get("browser_mode") or "managed"),
            "version": version,
            "profile_dir": str(browser_profile_dir(self.active_browser_mode or "managed")),
            "current_url": str(getattr(self.page, "url", "") or ""),
            "visible": bool(self.cfg.get("browser_visible", True)),
        }

    def bring_to_front(self) -> None:
        if self.page is None:
            self.launch()
        self.page.bring_to_front()

    def open_url(self, url: str) -> None:
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ValueError("只能在受控浏览器中打开 HTTP/HTTPS 地址")
        if self.page is None:
            self.launch()
        page = self._context.new_page() if self._context is not None else self.page
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.bring_to_front()
        self.page = page

    def capture_preview(self, path: str | os.PathLike[str]) -> str:
        if self.page is None:
            raise RuntimeError("浏览器尚未启动")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(target), full_page=False)
        return str(target)

    def search_and_scrape_controlled(
        self,
        keyword: str,
        *,
        max_pages: int = 5,
        max_count: int = 200,
        start_page: int = 1,
        on_progress: Callable[[int, int], None] | None = None,
        on_checkpoint: Callable[[int, int], None] | None = None,
        control: Callable[[str, int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        def check(stage: str, page_no: int, count: int) -> None:
            if control:
                control(stage, page_no, count)

        check("before_search", 0, 0)
        self.do_search(keyword)
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for skipped in range(1, max(1, start_page)):
            check("skip_to_checkpoint", skipped, 0)
            if not self._goto_next_page():
                break

        for page_no in range(max(1, start_page), max_pages + 1):
            check("before_page", page_no, len(candidates))
            selector = self._wait_for_search_cards(timeout=15000)
            if not selector:
                if page_no == max(1, start_page):
                    raise RuntimeError(
                        "SEARCH_RESULTS_SELECTOR_MISSING: 未发现搜索结果卡片，可能是页面改版、账号限制或搜索未成功"
                    )
                break
            cards = self.page.query_selector_all(selector)
            for card in cards:
                check("before_candidate", page_no, len(candidates))
                candidate = self._parse_search_card(card)
                if not candidate:
                    continue
                key = _candidate_dedup_key(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                if on_progress:
                    on_progress(len(candidates), page_no)
                if len(candidates) >= max_count:
                    break
            if on_checkpoint:
                on_checkpoint(page_no, len(candidates))
            check("after_page", page_no, len(candidates))
            if len(candidates) >= max_count or not self._goto_next_page():
                break
        return candidates
