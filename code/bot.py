# -*- coding: utf-8 -*-
"""智联浏览器适配器。

生产主链路只使用公开页面交互能力：启动本地浏览器、复用招聘人员本人登录态、
进入搜索页和检测登录。所有 Playwright 调用由 workbench.browser_worker 专用线程执行。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# 保留搜索器仍使用的少量 IM 选择器；业务代码不再依赖逆向转储文件。
SELECTORS = {
    "nav_item": "a.app-nav__item",
    "candidate_row": "div.im-candidate__row.has-separator>span.im-candidate__item",
    "cand_name": "span.im-candidate__item.im-candidate__name",
    "cand_job": "span.im-candidate__item > span.im-candidate__job",
    "cand_location": "span.im-candidate__item.im-candidate__location",
    "cand_b2b_name": "span.im-candidate__b2b-name",
}

URLS = {
    "home": "https://www.zhaopin.com/",
    "im": "https://rd6.zhaopin.com/app/im",
    "search": "https://rd6.zhaopin.com/app/search",
}


def _browser_candidates() -> list[Path]:
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return [
        program_files / "Google/Chrome/Application/chrome.exe",
        program_files_x86 / "Google/Chrome/Application/chrome.exe",
        local_app_data / "Google/Chrome/Application/chrome.exe",
        program_files / "Microsoft/Edge/Application/msedge.exe",
        program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
    ]


def find_system_browser() -> str | None:
    for path in _browser_candidates():
        if path.is_file():
            return str(path)
    return None


class BrowserBot:
    def __init__(self, config: dict | None = None, db=None):
        self.cfg = config or {}
        self.db = db
        self.page = None
        self._pw = None
        self._context = None

    def launch(self):
        """启动持久化浏览器上下文。

        优先使用招聘人员已安装的 Chrome/Edge；没有系统浏览器时回退到 Playwright
        Chromium（需预先执行 ``python -m playwright install chromium``）。
        """
        from playwright.sync_api import sync_playwright

        if self._context is not None:
            pages = self._context.pages
            self.page = pages[0] if pages else self._context.new_page()
            return self.page

        self._pw = sync_playwright().start()
        browser_path = self.cfg.get("chrome_path") or find_system_browser()
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "RecruitmentWorkbench"
        user_data_dir = Path(self.cfg.get("user_data_dir") or base / "browser_profile")
        user_data_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs = {
            # 智联风控对真 headless 返回降级结果（实测仅 1 条），必须 headed；
            # “隐藏浏览器”改为把窗口移出屏幕，兼顾后台运行与登录扫码。
            "headless": False,
            "viewport": {"width": 1440, "height": 900},
            "locale": "zh-CN",
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        }
        if self.cfg.get("hide_browser", False):
            launch_kwargs["args"].append("--window-position=-2400,-2400")
        launch_kwargs["user_agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        if browser_path:
            launch_kwargs["executable_path"] = browser_path

        try:
            self._context = self._pw.chromium.launch_persistent_context(str(user_data_dir), **launch_kwargs)
        except Exception as error:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
            hint = (
                "浏览器启动失败。请安装 Chrome/Edge，或在当前 Python 环境执行 "
                "`python -m playwright install chromium`。"
            )
            raise RuntimeError(f"{hint}\n原始错误：{error}") from error

        self._context.set_default_timeout(int(self.cfg.get("default_timeout_ms", 20000)))
        self._context.set_default_navigation_timeout(int(self.cfg.get("navigation_timeout_ms", 45000)))
        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self.page

    def is_logged_in(self) -> bool:
        if self.page is None:
            return False
        try:
            url = (self.page.url or "").lower()
            if any(token in url for token in ("passport", "/login", "login.zhaopin")):
                return False
            if "rd6.zhaopin.com/app" in url:
                return True
            for selector in (
                "a.app-nav__item",
                "[class*='app-nav']",
                "[class*='search-resume']",
                "[class*='talent-basic-info']",
            ):
                if self.page.query_selector(selector):
                    return True
        except Exception:
            return False
        return False

    def go_search(self, timeout: int = 45000) -> bool:
        if self.page is None:
            self.launch()
        self.page.goto(URLS["search"], timeout=timeout, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1800)
        return self.is_logged_in()

    def go_im(self, timeout: int = 45000) -> bool:
        if self.page is None:
            self.launch()
        self.page.goto(URLS["im"], timeout=timeout, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1800)
        return self.is_logged_in()

    def mark_window(self) -> None:
        if self.page is None:
            return
        try:
            self.page.bring_to_front()
        except Exception:
            pass
        try:
            self.page.evaluate("document.title = '【招聘自动化工作台】请在本窗口完成智联登录'")
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        finally:
            self._context = None
            self.page = None
            try:
                if self._pw is not None:
                    self._pw.stop()
            finally:
                self._pw = None

    @staticmethod
    def _extract_wechat(text: str):
        match = re.search(r"(?:微信|VX|vx|weixin)[:\s：]*([A-Za-z][A-Za-z0-9_-]{5,19})", text or "")
        return match.group(1) if match else None

    @staticmethod
    def _extract_phone(text: str):
        match = re.search(r"1[3-9]\d{9}", text or "")
        return match.group(0) if match else None
