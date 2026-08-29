# -*- coding: utf-8 -*-
"""Single-owner browser worker with pause, takeover, cancellation and diagnostics.

Every Playwright object is created and used on this dedicated worker thread. UI code
communicates only through commands/events. Control requests are cooperative threading
events so they can interrupt a long-running search between page/candidate checkpoints.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .browser_runtime import clear_browser_profiles
from .database import default_data_dir
from .diagnostics import capture_failure
from .models import BrowserCommand, BrowserEvent
from .zhilian_browser import ProductCandidateSearcher, SearchCancelled


class _NoopLegacyDB:
    def __getattr__(self, _name: str):
        def noop(*_args, **_kwargs):
            return None
        return noop


class BrowserWorker:
    def __init__(
        self,
        events: "queue.Queue[BrowserEvent]",
        *,
        browser_config: dict[str, Any] | None = None,
        chrome_path: str | None = None,
        hide_browser: bool = False,
    ):
        self.events = events
        self.browser_config: dict[str, Any] = dict(browser_config or {})
        if chrome_path:
            self.browser_config.setdefault("custom_browser_path", chrome_path)
        if hide_browser:
            self.browser_config.setdefault("browser_visible", False)
        self.commands: "queue.Queue[BrowserCommand]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="browser-worker", daemon=True)
        self._started = False
        self._bot: Any | None = None
        self._shutdown = threading.Event()
        self._pause_requested = threading.Event()
        self._cancel_requested = threading.Event()
        self._takeover_requested = threading.Event()
        self._bring_front_requested = threading.Event()
        self._active_request_id = ""
        self._active_run_id: int | str = ""
        self._last_preview_ts = 0.0

    def start(self) -> None:
        if not self._started:
            self._thread.start()
            self._started = True

    def submit(self, command: str, payload: dict[str, Any] | None = None, request_id: str | None = None) -> str:
        self.start()
        rid = request_id or uuid.uuid4().hex
        name = command.upper().strip()
        if name == "PAUSE":
            self._pause_requested.set()
            self._emit("CONTROL_ACCEPTED", rid, action="PAUSE", message="已请求暂停")
            return rid
        if name == "RESUME":
            self._takeover_requested.clear()
            self._pause_requested.clear()
            self._emit("CONTROL_ACCEPTED", rid, action="RESUME", message="已请求继续")
            return rid
        if name == "CANCEL":
            self._cancel_requested.set()
            self._pause_requested.clear()
            self._emit("CONTROL_ACCEPTED", rid, action="CANCEL", message="正在安全停止任务")
            return rid
        if name == "TAKE_OVER":
            self._takeover_requested.set()
            self._bring_front_requested.set()
            self._pause_requested.set()
            self._emit("CONTROL_ACCEPTED", rid, action="TAKE_OVER", message="正在切换为人工接管")
            return rid
        self.commands.put(BrowserCommand(command=name, request_id=rid, payload=payload or {}))
        return rid

    def shutdown(self, timeout: float = 10.0) -> None:
        if not self._started:
            return
        self._cancel_requested.set()
        self._pause_requested.clear()
        self.commands.put(BrowserCommand(command="SHUTDOWN", request_id=uuid.uuid4().hex, payload={}))
        self._thread.join(timeout=timeout)

    def _emit(self, event: str, request_id: str, **payload: Any) -> None:
        self.events.put(BrowserEvent(event=event, request_id=request_id, payload=payload))

    def _ensure_bot(self) -> ProductCandidateSearcher:
        # 健壮性：若上一次的浏览器已崩溃/被关闭，自愈重建，避免本轮直接报 "page closed"
        if self._bot is not None:
            try:
                ctx = getattr(self._bot, "_context", None)
                page = getattr(self._bot, "page", None)
                dead = ctx is None or page is None or page.is_closed()
            except Exception:
                dead = True
            if dead:
                self._reset_bot()
        if self._bot is None:
            self._bot = ProductCandidateSearcher(dict(self.browser_config), _NoopLegacyDB())
            self._bot.launch()
        return self._bot

    def _start_trace(self, bot: Any) -> None:
        context = getattr(bot, "_context", None)
        if context is None:
            return
        try:
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
        except Exception:
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
        if "selector" in text:
            return "PAGE_CHANGED"
        return "BROWSER_AUTOMATION_ERROR"

    def _reset_bot(self) -> None:
        if self._bot is not None:
            try:
                self._bot.close()
            except Exception:
                pass
        self._bot = None

    def _control(self, bot: Any, request_id: str, run_id: Any, stage: str, page_no: int, count: int) -> None:
        # 实时画面：节流周期截图，供网页/桌面端展示招聘过程
        now = time.time()
        if now - self._last_preview_ts >= 1.2:
            self._last_preview_ts = now
            try:
                target = default_data_dir() / "preview" / "latest.png"
                bot.capture_preview(target)
            except Exception:
                pass
        if self._bring_front_requested.is_set():
            self._bring_front_requested.clear()
            try:
                bot.bring_to_front()
            except Exception:
                pass
        if self._takeover_requested.is_set():
            self._emit(
                "TAKEOVER_READY",
                request_id,
                run_id=run_id,
                message="自动化已暂停，浏览器已交给人工操作。处理完成后点击“继续”。",
                page_no=page_no,
                count=count,
            )
            self._takeover_requested.clear()

        paused_announced = False
        while self._pause_requested.is_set() and not self._cancel_requested.is_set():
            if not paused_announced:
                self._emit(
                    "PAUSED",
                    request_id,
                    run_id=run_id,
                    message="任务已暂停",
                    stage=stage,
                    page_no=page_no,
                    count=count,
                )
                paused_announced = True
            if self._bring_front_requested.is_set():
                self._bring_front_requested.clear()
                try:
                    bot.bring_to_front()
                except Exception:
                    pass
            time.sleep(0.15)
        if paused_announced and not self._cancel_requested.is_set():
            self._emit(
                "RESUMED",
                request_id,
                run_id=run_id,
                message="任务继续运行",
                page_no=page_no,
                count=count,
            )
        if self._cancel_requested.is_set():
            raise SearchCancelled("用户取消了搜索任务")

    def _handle_search(self, command: BrowserCommand) -> None:
        payload = command.payload
        run_id = payload.get("run_id", "unknown")
        query = str(payload.get("query") or "").strip()
        max_pages = max(1, min(int(payload.get("max_pages", 5)), 20))
        max_count = max(1, min(int(payload.get("max_count", 200)), 2000))
        start_page = max(1, min(int(payload.get("start_page", 1)), max_pages))
        if not query:
            self._emit("FAILED", command.request_id, run_id=run_id, error_code="EMPTY_QUERY", error="搜索关键词为空")
            return

        self._pause_requested.clear()
        self._cancel_requested.clear()
        self._takeover_requested.clear()
        self._active_request_id = command.request_id
        self._active_run_id = run_id
        bot = None
        try:
            self._emit("STATUS", command.request_id, run_id=run_id, message="正在启动受控浏览器…", progress=5)
            bot = self._ensure_bot()
            self._emit("BROWSER_STATUS", command.request_id, run_id=run_id, **bot.browser_info())
            self._start_trace(bot)
            logged_in = bot.go_search()
            if not logged_in:
                try:
                    bot.bring_to_front()
                except Exception:
                    pass
                self._stop_trace(bot)
                self._emit(
                    "NEED_LOGIN",
                    command.request_id,
                    run_id=run_id,
                    message="请在右侧受控浏览器完成智联登录，然后点击“已登录，继续搜索”。",
                )
                return

            self._emit("STATUS", command.request_id, run_id=run_id, message=f"正在搜索：{query}", progress=15)

            def on_progress(count: int, page_no: int) -> None:
                progress = min(88, 15 + int(70 * page_no / max_pages))
                self._emit(
                    "PROGRESS",
                    command.request_id,
                    run_id=run_id,
                    count=count,
                    page_no=page_no,
                    progress=progress,
                    message=f"第 {page_no}/{max_pages} 页，已发现 {count} 名候选人",
                )

            def on_checkpoint(page_no: int, count: int) -> None:
                self._emit(
                    "CHECKPOINT",
                    command.request_id,
                    run_id=run_id,
                    page_no=page_no,
                    count=count,
                    checkpoint={"last_completed_page": page_no, "found_count": count, "query": query},
                )

            def on_page(page_no: int, page_candidates: list) -> None:
                self._emit(
                    "PAGE_BATCH",
                    command.request_id,
                    run_id=run_id,
                    page_no=page_no,
                    count=len(page_candidates),
                    candidates=page_candidates,
                )

            candidates = bot.search_and_scrape_controlled(
                query,
                max_pages=max_pages,
                max_count=max_count,
                start_page=start_page,
                on_progress=on_progress,
                on_checkpoint=on_checkpoint,
                on_page=on_page,
                control=lambda stage, page_no, count: self._control(
                    bot, command.request_id, run_id, stage, page_no, count
                ),
                filters=payload.get("filters") or None,
                fetch_detail=bool(payload.get("fetch_detail", False)),
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
        except SearchCancelled as error:
            if bot is not None:
                self._stop_trace(bot)
            self._emit(
                "CANCELLED",
                command.request_id,
                run_id=run_id,
                error=str(error),
                message="任务已安全停止",
            )
        except Exception as error:
            error_code = self._classify_error(error)
            diagnostic_dir = capture_failure(
                run_id=run_id,
                request_id=command.request_id,
                error_code=error_code,
                error=error,
                bot=bot,
                extra={
                    "query": query,
                    "max_pages": max_pages,
                    "max_count": max_count,
                    "start_page": start_page,
                },
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
        finally:
            self._active_request_id = ""
            self._active_run_id = ""
            self._pause_requested.clear()
            self._cancel_requested.clear()
            self._takeover_requested.clear()

    def _handle_simple(self, command: BrowserCommand) -> None:
        if command.command == "CONFIGURE_BROWSER":
            self.browser_config.update(command.payload)
            self._reset_bot()
            self._emit("BROWSER_CONFIGURED", command.request_id, message="浏览器设置已保存，下次启动时生效")
            return
        if command.command == "RESET_BROWSER":
            self._reset_bot()
            self._emit("BROWSER_RESET", command.request_id, message="受控浏览器已重置")
            return
        if command.command == "CLEAR_BROWSER_PROFILE":
            self._reset_bot()
            clear_browser_profiles()
            self._emit("BROWSER_PROFILE_CLEARED", command.request_id, message="登录状态和浏览器缓存已清除")
            return

        bot = self._ensure_bot()
        if command.command == "GET_BROWSER_STATUS":
            self._emit("BROWSER_STATUS", command.request_id, **bot.browser_info())
        elif command.command == "BRING_TO_FRONT":
            bot.bring_to_front()
            self._emit("BROWSER_SHOWN", command.request_id, message="已显示受控浏览器")
        elif command.command == "OPEN_URL":
            bot.open_url(str(command.payload.get("url") or ""))
            self._emit("URL_OPENED", command.request_id, message="已在受控浏览器中打开候选人来源")
        elif command.command == "CAPTURE_PREVIEW":
            target = default_data_dir() / "preview" / "latest.png"
            path = bot.capture_preview(target)
            self._emit("PREVIEW_READY", command.request_id, path=path)
        elif command.command == "CHECK_LOGIN":
            logged_in = bot.go_search()
            self._emit(
                "LOGIN_CHECKED",
                command.request_id,
                logged_in=bool(logged_in),
                message="登录状态有效" if logged_in else "尚未检测到有效登录",
            )
        else:
            self._emit(
                "FAILED",
                command.request_id,
                error_code="UNKNOWN_COMMAND",
                error=f"未知浏览器命令: {command.command}",
            )

    def _run(self) -> None:
        while not self._shutdown.is_set():
            command = self.commands.get()
            if command.command == "SHUTDOWN":
                self._shutdown.set()
                self._reset_bot()
                self._emit("SHUTDOWN", command.request_id, message="浏览器工作线程已关闭")
                break
            if command.command == "SEARCH":
                self._handle_search(command)
                continue
            try:
                self._handle_simple(command)
            except Exception as error:
                diagnostic_dir = capture_failure(
                    run_id=command.payload.get("run_id", "control"),
                    request_id=command.request_id,
                    error_code=self._classify_error(error),
                    error=error,
                    bot=self._bot,
                    extra={"command": command.command},
                )
                self._emit(
                    "FAILED",
                    command.request_id,
                    run_id=command.payload.get("run_id", 0),
                    error_code=self._classify_error(error),
                    error=str(error),
                    diagnostic_dir=diagnostic_dir,
                )
