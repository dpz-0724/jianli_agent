# -*- coding: utf-8 -*-
from __future__ import annotations

import queue
import unittest

from workbench.delivery_browser import DeliveryBrowserWorker
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


if __name__ == "__main__":
    unittest.main()
