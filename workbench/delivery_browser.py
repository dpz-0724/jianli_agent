# -*- coding: utf-8 -*-
"""Durable page streaming and self-healing browser controls for pilot delivery."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

from .browser_runtime import clear_browser_profiles
from .browser_worker import BrowserWorker, _NoopLegacyDB
from .database import default_data_dir
from .diagnostics import capture_failure
from .models import BrowserCommand
from .zhilian_browser import ProductCandidateSearcher, SearchCancelled


class PagePersistenceError(RuntimeError):
    pass


class DeliveryCandidateSearcher(ProductCandidateSearcher):
    def is_alive(self) -> bool:
        if self._context is None:
            return False
        try:
            pages = [page for page in self._context.pages if not page.is_closed()]
            browser = self._context.browser
            return bool(pages or browser is not None)
        except Exception:
            return False

    def _ensure_live_page(self):
        if not self.is_alive():
            try:
                self.close()
            except Exception:
                pass
            self.launch()
        pages = [page for page in self._context.pages if not page.is_closed()]
        if self.page is None or self.page.is_closed():
            self.page = pages[0] if pages else self._context.new_page()
        return self.page

    def launch(self):
        if self.is_alive():
            return self._ensure_live_page()
        return super().launch()

    def bring_to_front(self) -> None:
        self._ensure_live_page().bring_to_front()

    def go_search(self, timeout: int = 45000) -> bool:
        self._ensure_live_page()
        return super().go_search(timeout=timeout)

    def open_url(self, url: str) -> None:
        self._ensure_live_page()
        return super().open_url(url)

    def browser_info(self) -> dict[str, Any]:
        info = super().browser_info()
        info["running"] = self.is_alive()
        return info

    def search_and_scrape_controlled(
        self,
        keyword: str,
        *,
        max_pages: int = 5,
        max_count: int = 200,
        start_page: int = 1,
        on_progress: Callable[[int, int], None] | None = None,
        on_page_result: Callable[[int, list[dict[str, Any]], int], None] | None = None,
        control: Callable[[str, int, int], None] | None = None,
    ) -> int:
        from searcher import _candidate_dedup_key

        def check(stage: str, page_no: int, count: int) -> None:
            if control:
                control(stage, page_no, count)

        check("before_search", 0, 0)
        self._ensure_live_page()
        self.do_search(keyword)
        seen: set[str] = set()
        total_count = 0

        for skipped in range(1, max(1, start_page)):
            check("skip_to_checkpoint", skipped, total_count)
            if not self._goto_next_page():
                break

        for page_no in range(max(1, start_page), max_pages + 1):
            check("before_page", page_no, total_count)
            selector = self._wait_for_search_cards(timeout=15000)
            if not selector:
                if page_no == max(1, start_page):
                    raise RuntimeError(
                        "SEARCH_RESULTS_SELECTOR_MISSING: 未发现搜索结果卡片，可能是页面改版、账号限制或搜索未成功"
                    )
                break
            page_candidates: list[dict[str, Any]] = []
            cards = self.page.query_selector_all(selector)
            for card in cards:
                check("before_candidate", page_no, total_count)
                candidate = self._parse_search_card(card)
                if not candidate:
                    continue
                key = _candidate_dedup_key(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                page_candidates.append(candidate)
                total_count += 1
                if on_progress:
                    on_progress(total_count, page_no)
                if total_count >= max_count:
                    break
            if on_page_result:
                on_page_result(page_no, page_candidates, total_count)
            check("after_page", page_no, total_count)
            if total_count >= max_count or not self._goto_next_page():
                break
        return total_count


class DeliveryBrowserWorker(BrowserWorker):
    """Streams each page and waits until its durable database commit is acknowledged."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ack_lock = threading.Lock()
        self._page_ack_events: dict[str, threading.Event] = {}
        self._page_ack_results: dict[str, tuple[bool, str]] = {}

    def submit(self, command: str, payload: dict[str, Any] | None = None, request_id: str | None = None) -> str:
        name = command.upper().strip()
        rid = request_id or uuid.uuid4().hex
        if name == "ACK_PAGE":
            data = payload or {}
            token = str(data.get("ack_token") or "")
            with self._ack_lock:
                event = self._page_ack_events.get(token)
                if event is not None:
                    self._page_ack_results[token] = (
                        bool(data.get("ok")),
                        str(data.get("error") or ""),
                    )
                    event.set()
            return rid
        if name == "BRING_TO_FRONT" and self._active_request_id:
            self._bring_front_requested.set()
            self._emit("CONTROL_ACCEPTED", rid, action="BRING_TO_FRONT", message="正在显示受控浏览器")
            return rid
        return super().submit(name, payload, rid)

    def _register_page_ack(self) -> tuple[str, threading.Event]:
        token = uuid.uuid4().hex
        event = threading.Event()
        with self._ack_lock:
            self._page_ack_events[token] = event
        return token, event

    def _await_page_ack(self, token: str, event: threading.Event, timeout: float = 180.0) -> None:
        deadline = time.monotonic() + timeout
        try:
            while not event.wait(0.15):
                if self._cancel_requested.is_set() or self._shutdown.is_set():
                    raise SearchCancelled("任务在等待候选人安全保存时被停止")
                if time.monotonic() >= deadline:
                    raise PagePersistenceError("PAGE_PERSIST_TIMEOUT: 等待候选人保存确认超时")
            with self._ack_lock:
                ok, error = self._page_ack_results.get(token, (False, "未收到保存结果"))
            if not ok:
                raise PagePersistenceError(f"PAGE_PERSIST_FAILED: {error or '候选人保存失败'}")
        finally:
            with self._ack_lock:
                self._page_ack_events.pop(token, None)
                self._page_ack_results.pop(token, None)

    def _ensure_bot(self) -> DeliveryCandidateSearcher:
        if self._bot is not None and not self._bot.is_alive():
            self._reset_bot()
        if self._bot is None:
            self._bot = DeliveryCandidateSearcher(dict(self.browser_config), _NoopLegacyDB())
            self._bot.launch()
        return self._bot

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
                bot.bring_to_front()
                self._stop_trace(bot)
                self._emit(
                    "NEED_LOGIN",
                    command.request_id,
                    run_id=run_id,
                    message="请在受控浏览器完成智联登录，然后点击“验证登录并继续”。",
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
                    message=f"第 {page_no}/{max_pages} 页，已识别 {count} 名候选人",
                )

            def on_page_result(page_no: int, candidates: list[dict[str, Any]], total_count: int) -> None:
                ack_token, ack_event = self._register_page_ack()
                self._emit(
                    "PAGE_RESULT",
                    command.request_id,
                    run_id=run_id,
                    page_no=page_no,
                    candidates=candidates,
                    page_count=len(candidates),
                    segment_count=total_count,
                    ack_token=ack_token,
                    message=f"第 {page_no} 页已采集，正在持久化 {len(candidates)} 名候选人",
                )
                self._await_page_ack(ack_token, ack_event)

            count = bot.search_and_scrape_controlled(
                query,
                max_pages=max_pages,
                max_count=max_count,
                start_page=start_page,
                on_progress=on_progress,
                on_page_result=on_page_result,
                control=lambda stage, page_no, current_count: self._control(
                    bot, command.request_id, run_id, stage, page_no, current_count
                ),
            )
            self._stop_trace(bot)
            self._emit(
                "COMPLETED",
                command.request_id,
                run_id=run_id,
                count=count,
                page_persisted=True,
                message=f"搜索完成，本段共识别 {count} 名候选人",
            )
        except SearchCancelled as error:
            if bot is not None:
                self._stop_trace(bot)
            self._emit("CANCELLED", command.request_id, run_id=run_id, error=str(error), message="任务已安全停止")
        except Exception as error:
            text = str(error)
            error_code = (
                "PAGE_PERSIST_FAILED"
                if "PAGE_PERSIST_FAILED" in text
                else "PAGE_PERSIST_TIMEOUT"
                if "PAGE_PERSIST_TIMEOUT" in text
                else self._classify_error(error)
            )
            diagnostic_dir = capture_failure(
                run_id=run_id,
                request_id=command.request_id,
                error_code=error_code,
                error=error,
                bot=bot,
                extra={"query": query, "max_pages": max_pages, "max_count": max_count, "start_page": start_page},
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
            with self._ack_lock:
                for event in self._page_ack_events.values():
                    event.set()
                self._page_ack_events.clear()
                self._page_ack_results.clear()

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

        last_error: BaseException | None = None
        for attempt in range(2):
            try:
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
                    self._emit("FAILED", command.request_id, error_code="UNKNOWN_COMMAND", error=f"未知浏览器命令: {command.command}")
                return
            except Exception as error:
                last_error = error
                code = self._classify_error(error)
                if attempt == 0 and code in {"BROWSER_CLOSED", "BROWSER_THREAD_ERROR"}:
                    self._reset_bot()
                    continue
                raise
        if last_error:
            raise last_error


__all__ = ["DeliveryBrowserWorker", "DeliveryCandidateSearcher", "PagePersistenceError"]
