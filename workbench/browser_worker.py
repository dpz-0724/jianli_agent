# -*- coding: utf-8 -*-
"""Single-owner browser worker.

Every Playwright object is created and used on this dedicated worker thread. The UI
communicates through commands/events and never touches Page/Context directly.
"""
from __future__ import annotations

import queue
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from .diagnostics import capture_failure
from .models import BrowserCommand, BrowserEvent

ROOT_DIR = Path(__file__).resolve().parents[1]
LEGACY_CODE_DIR = ROOT_DIR / "code"


class _NoopLegacyDB:
    """CandidateSearcher only needs DB for legacy greeting/contact features not used here."""

    def __getattr__(self, name: str):
        def noop(*_args, **_kwargs):
            return None
        return noop


class BrowserWorker:
    def __init__(
        self,
        events: "queue.Queue[BrowserEvent]",
        *,
        chrome_path: str | None = None,
        hide_browser: bool = False,
    ):
        self.events = events
        self.chrome_path = chrome_path
        self.hide_browser = hide_browser
        self.commands: "queue.Queue[BrowserCommand]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="browser-worker", daemon=True)
        self._started = False
        self._bot: Any | None = None
        self._shutdown = threading.Event()

    def start(self) -> None:
        if not self._started:
            self._thread.start()
            self._started = True

    def submit(self, command: str, payload: dict[str, Any] | None = None, request_id: str | None = None) -> str:
        self.start()
        rid = request_id or uuid.uuid4().hex
        self.commands.put(BrowserCommand(command=command, request_id=rid, payload=payload or {}))
        return rid

    def shutdown(self, timeout: float = 8.0) -> None:
        if not self._started:
            return
        self.submit("SHUTDOWN")
        self._thread.join(timeout=timeout)

    def _emit(self, event: str, request_id: str, **payload: Any) -> None:
        self.events.put(BrowserEvent(event=event, request_id=request_id, payload=payload))

    def _ensure_bot(self) -> Any:
        if self._bot is not None:
            return self._bot
        if str(LEGACY_CODE_DIR) not in sys.path:
            sys.path.insert(0, str(LEGACY_CODE_DIR))
        from searcher import CandidateSearcher  # imported only in worker thread

        config = {
            "hide_browser": self.hide_browser,
            "chrome_path": self.chrome_path or None,
        }
        self._bot = CandidateSearcher(config, _NoopLegacyDB())
        self._bot.launch()
        return self._bot

    def _start_trace(self, bot: Any) -> None:
        context = getattr(bot, "_context", None)
        if context is None:
            return
        try:
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
        except Exception:
            # A previous interrupted trace may still be active; diagnostics remains best-effort.
            pass

    def _stop_trace(self, bot: Any) -> None:
        context = getattr(bot, "_context", None)
        if context is None:
            return
        try:
            context.tracing.stop()
        except Exception:
            pass

    @staticmethod
    def _classify_error(error: BaseException) -> str:
        text = str(error).lower()
        if "timeout" in text:
            return "BROWSER_TIMEOUT"
        if "target page" in text or "browser has been closed" in text or "closed" in text:
            return "BROWSER_CLOSED"
        if "net::" in text or "network" in text or "connection" in text:
            return "NETWORK_ERROR"
        if "greenlet" in text or "thread" in text:
            return "BROWSER_THREAD_ERROR"
        return "BROWSER_AUTOMATION_ERROR"

    def _reset_bot(self) -> None:
        if self._bot is not None:
            try:
                self._bot.close()
            except Exception:
                pass
        self._bot = None

    def _handle_search(self, command: BrowserCommand) -> None:
        payload = command.payload
        run_id = payload.get("run_id", "unknown")
        query = str(payload.get("query") or "").strip()
        max_pages = max(1, min(int(payload.get("max_pages", 5)), 20))
        max_count = max(1, min(int(payload.get("max_count", 200)), 2000))
        if not query:
            self._emit("FAILED", command.request_id, run_id=run_id, error_code="EMPTY_QUERY", error="搜索关键词为空")
            return

        bot = None
        try:
            self._emit("STATUS", command.request_id, run_id=run_id, message="正在启动并检查浏览器…", progress=5)
            bot = self._ensure_bot()
            self._start_trace(bot)
            logged_in = bot.go_search()
            if not logged_in:
                try:
                    bot.mark_window()
                except Exception:
                    pass
                self._stop_trace(bot)
                self._emit(
                    "NEED_LOGIN",
                    command.request_id,
                    run_id=run_id,
                    message="请在已打开的智联窗口完成登录，然后点击“登录完成，继续搜索”。",
                )
                return

            self._emit("STATUS", command.request_id, run_id=run_id, message=f"正在搜索：{query}", progress=20)

            def on_progress(count: int, page_no: int) -> None:
                progress = min(85, 20 + page_no * 10)
                self._emit(
                    "PROGRESS",
                    command.request_id,
                    run_id=run_id,
                    count=count,
                    page_no=page_no,
                    progress=progress,
                    message=f"第 {page_no} 页，已发现 {count} 名候选人",
                )

            candidates = bot.search_and_scrape(
                query,
                max_pages=max_pages,
                max_count=max_count,
                on_progress=on_progress,
            )
            self._stop_trace(bot)
            self._emit(
                "COMPLETED",
                command.request_id,
                run_id=run_id,
                candidates=candidates,
                count=len(candidates),
                message=f"搜索完成，共发现 {len(candidates)} 名候选人",
            )
        except Exception as error:
            error_code = self._classify_error(error)
            diagnostic_dir = capture_failure(
                run_id=run_id,
                request_id=command.request_id,
                error_code=error_code,
                error=error,
                bot=bot,
                extra={"query": query, "max_pages": max_pages, "max_count": max_count},
            )
            if error_code in {"BROWSER_CLOSED", "BROWSER_THREAD_ERROR"}:
                self._reset_bot()
            self._emit(
                "FAILED",
                command.request_id,
                run_id=run_id,
                error_code=error_code,
                error=str(error),
                diagnostic_dir=diagnostic_dir,
                message="自动化任务失败，已生成诊断包。",
            )

    def _handle_check_login(self, command: BrowserCommand) -> None:
        run_id = command.payload.get("run_id", "unknown")
        try:
            bot = self._ensure_bot()
            logged_in = bot.go_search()
            self._emit(
                "LOGIN_CHECKED",
                command.request_id,
                run_id=run_id,
                logged_in=bool(logged_in),
                message="登录状态有效" if logged_in else "尚未检测到有效登录",
            )
        except Exception as error:
            diagnostic_dir = capture_failure(
                run_id=run_id,
                request_id=command.request_id,
                error_code=self._classify_error(error),
                error=error,
                bot=self._bot,
            )
            self._emit(
                "FAILED",
                command.request_id,
                run_id=run_id,
                error_code=self._classify_error(error),
                error=str(error),
                diagnostic_dir=diagnostic_dir,
            )

    def _run(self) -> None:
        while not self._shutdown.is_set():
            command = self.commands.get()
            if command.command == "SHUTDOWN":
                self._shutdown.set()
                self._reset_bot()
                self._emit("SHUTDOWN", command.request_id, message="浏览器工作线程已关闭")
                break
            if command.command == "RESET_BROWSER":
                self._reset_bot()
                self._emit("BROWSER_RESET", command.request_id, message="浏览器已重置")
                continue
            if command.command == "CHECK_LOGIN":
                self._handle_check_login(command)
                continue
            if command.command == "SEARCH":
                self._handle_search(command)
                continue
            self._emit(
                "FAILED",
                command.request_id,
                error_code="UNKNOWN_COMMAND",
                error=f"未知浏览器命令: {command.command}",
            )
