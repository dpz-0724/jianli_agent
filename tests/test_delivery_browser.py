# -*- coding: utf-8 -*-
from __future__ import annotations

import queue
import unittest

from workbench.delivery_browser import DeliveryBrowserWorker, PagePersistenceError
from workbench.models import BrowserCommand


class _ClosedBot:
    def is_alive(self):
        return True

    def bring_to_front(self):
        raise RuntimeError("Target page, context or browser has been closed")

    def close(self):
        return None


class _HealthyBot:
    def is_alive(self):
        return True

    def bring_to_front(self):
        return None

    def close(self):
        return None


class _RecoveryWorker(DeliveryBrowserWorker):
    def __init__(self, events):
        super().__init__(events)
        self.created = 0

    def _ensure_bot(self):
        if self._bot is None:
            self.created += 1
            self._bot = _ClosedBot() if self.created == 1 else _HealthyBot()
        return self._bot


class DeliveryBrowserTests(unittest.TestCase):
    def test_simple_control_recovers_after_browser_closed(self):
        events = queue.Queue()
        worker = _RecoveryWorker(events)
        worker._handle_simple(BrowserCommand(command="BRING_TO_FRONT", request_id="x", payload={}))
        event = events.get_nowait()
        self.assertEqual(event.event, "BROWSER_SHOWN")
        self.assertEqual(worker.created, 2)

    def test_page_ack_allows_browser_to_advance_only_after_commit(self):
        worker = DeliveryBrowserWorker(queue.Queue())
        token, event = worker._register_page_ack()
        self.assertFalse(event.is_set())
        worker.submit("ACK_PAGE", {"ack_token": token, "ok": True})
        worker._await_page_ack(token, event, timeout=0.2)
        self.assertNotIn(token, worker._page_ack_events)

    def test_failed_page_ack_stops_page_advance(self):
        worker = DeliveryBrowserWorker(queue.Queue())
        token, event = worker._register_page_ack()
        worker.submit("ACK_PAGE", {"ack_token": token, "ok": False, "error": "disk full"})
        with self.assertRaises(PagePersistenceError) as context:
            worker._await_page_ack(token, event, timeout=0.2)
        self.assertIn("disk full", str(context.exception))


if __name__ == "__main__":
    unittest.main()
