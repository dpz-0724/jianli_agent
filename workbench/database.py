# -*- coding: utf-8 -*-
"""Public SQLite repository facade."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .db_base import DatabaseBase
from .db_candidates import CandidateMixin
from .db_jobs import JobRunMixin
from .db_reporting import ReportingMixin
from .db_schema import default_data_dir


class WorkbenchDB(JobRunMixin, CandidateMixin, ReportingMixin, DatabaseBase):
    """Thread-safe, job-scoped repository composed from focused mixins."""

    def __init__(self, path=None):
        # SQLite ':memory:' creates a different database for every short-lived connection.
        # Map it to a temporary file so repository methods still share one database in UI
        # smoke tests and embedded evaluation environments.
        self._temporary_directory = None
        if str(path) == ":memory:":
            self._temporary_directory = tempfile.TemporaryDirectory()
            path = Path(self._temporary_directory.name) / "workbench.db"
        super().__init__(path)

    def __del__(self):
        temporary = getattr(self, "_temporary_directory", None)
        if temporary is not None:
            try:
                temporary.cleanup()
            except Exception:
                pass


__all__ = ["WorkbenchDB", "default_data_dir"]
