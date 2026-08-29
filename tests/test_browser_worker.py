# -*- coding: utf-8 -*-
from __future__ import annotations

import queue
import threading
import time
import unittest

from workbench.browser_worker import BrowserWorker


class FakeBot:
    def __init__(self):
        self.thread_id = None
        self.page = None
        self._context = None

    def go_search(self):
        self.thread_id = threading.get_ident()
        return True

    def browser_info(self):
        return {"running": True, "mode": "managed", "version": "test", "profile_dir": "test", "current_url": ""}

    def search_and_scrape_controlled(
        self,
        query,
        max_pages,
        max_count,
        start_page,
        on_progress,
        on_checkpoint,
        control,
        on_page=None,
        filters=None,
        fetch_detail=False,
        max_detail=25,
    ):
        self.thread_id = threading.get_ident()
        result = []
        for page_no in range(start_page, max_pages + 1):
            control("before_page", page_no, len(result))
            time.sleep(0.03)
            result.append({"platform": "demo", "platform_uid": str(page_no), "name": "A", "title": query})
            on_progress(len(result), page_no)
            if on_page:
                on_page(page_no, [result[-1]])
            on_checkpoint(page_no, len(result))
            if len(result) >= max_count:
                break
        return result

    def bring_to_front(self):
        return None

    def close(self):
        return None


class FakeWorker(BrowserWorker):
    def __init__(self, events):
        super().__init__(events)
        self.fake_bot = FakeBot()

    def _ensure_bot(self):
        self._bot = self.fake_bot
        return self.fake_bot


class BrowserWorkerTests(unittest.TestCase):
    def _wait_for(self, events, request_id, expected, timeout=4):
        deadline = time.time() + timeout
        while time.time() < deadline:
            event = events.get(timeout=1)
            if event.request_id == request_id and event.event == expected:
                return event
        return None

    def test_search_runs_on_dedicated_worker_thread(self):
        events = queue.Queue()
        worker = FakeWorker(events)
        main_thread_id = threading.get_ident()
        request_id = worker.submit(
            "SEARCH",
            {"run_id": 1, "query": "Java", "max_pages": 1, "max_count": 10},
        )
        completed = self._wait_for(events, request_id, "COMPLETED")
        worker.shutdown()
        self.assertIsNotNone(completed)
        self.assertIsNotNone(worker.fake_bot.thread_id)
        self.assertNotEqual(worker.fake_bot.thread_id, main_thread_id)

    def test_pause_and_resume_are_cooperative(self):
        events = queue.Queue()
        worker = FakeWorker(events)
        request_id = worker.submit(
            "SEARCH",
            {"run_id": 2, "query": "Python", "max_pages": 8, "max_count": 8},
        )
        first_progress = self._wait_for(events, request_id, "PROGRESS")
        self.assertIsNotNone(first_progress)
        worker.submit("PAUSE")
        paused = self._wait_for(events, request_id, "PAUSED")
        self.assertIsNotNone(paused)
        worker.submit("RESUME")
        completed = self._wait_for(events, request_id, "COMPLETED")
        worker.shutdown()
        self.assertIsNotNone(completed)

    def test_cancel_finishes_as_cancelled(self):
        events = queue.Queue()
        worker = FakeWorker(events)
        request_id = worker.submit(
            "SEARCH",
            {"run_id": 3, "query": "Go", "max_pages": 20, "max_count": 20},
        )
        self.assertIsNotNone(self._wait_for(events, request_id, "PROGRESS"))
        worker.submit("CANCEL")
        cancelled = self._wait_for(events, request_id, "CANCELLED")
        worker.shutdown()
        self.assertIsNotNone(cancelled)


if __name__ == "__main__":
    unittest.main()
