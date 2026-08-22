# -*- coding: utf-8 -*-
"""Tkinter desktop UI for Recruitment Workbench V1."""
from __future__ import annotations

import queue
import tkinter as tk

from .browser_worker import BrowserWorker
from .database import WorkbenchDB
from .models import BrowserEvent
from .service import RecruitmentService
from .ui_actions import UIActionsMixin
from .ui_layout import UILayoutMixin


class WorkbenchApp(UIActionsMixin, UILayoutMixin, tk.Tk):
    def __init__(self, db_path: str | None = None):
        super().__init__()
        self.title("招聘自动化工作台 V1")
        self.geometry("1400x860")
        self.minsize(1120, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.db = WorkbenchDB(db_path)
        self.service = RecruitmentService(self.db)
        self.browser_events: "queue.Queue[BrowserEvent]" = queue.Queue()
        self.worker = BrowserWorker(self.browser_events)
        self.current_job_id: int | None = None
        self.pending: dict[str, dict] = {}
        self.waiting_login: dict | None = None
        self._style()
        self._build()
        self.refresh_jobs()
        self.after(150, self._poll_events)
