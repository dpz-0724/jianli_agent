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

    def go_search(self):
        self.thread_id = threading.get_ident()
        return True

    def search_and_scrape(self, query, max_pages, max_count, on_progress):
        self.thread_id = threading.get_ident()
        on_progress(1, 1)
        return [{"platform": "demo", "platform_uid": "1", "name": "A", "title": query}]

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
    def test_search_runs_on_dedicated_worker_thread(self):
        events = queue.Queue()
        worker = FakeWorker(events)
        main_thread_id = threading.get_ident()
        request_id = worker.submit("SEARCH", {"run_id": 1, "query": "Java", "max_pages": 1, "max_count": 10})
        completed = None
        deadline = time.time() + 3
        while time.time() < deadline:
            event = events.get(timeout=1)
            if event.request_id == request_id and event.event == "COMPLETED":
                completed = event
                break
        worker.shutdown()
        self.assertIsNotNone(completed)
        self.assertIsNotNone(worker.fake_bot.thread_id)
        self.assertNotEqual(worker.fake_bot.thread_id, main_thread_id)


if __name__ == "__main__":
    unittest.main()
