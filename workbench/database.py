# -*- coding: utf-8 -*-
"""Public SQLite repository facade."""
from __future__ import annotations

from .db_base import DatabaseBase
from .db_candidates import CandidateMixin
from .db_jobs import JobRunMixin
from .db_reporting import ReportingMixin
from .db_schema import default_data_dir


class WorkbenchDB(JobRunMixin, CandidateMixin, ReportingMixin, DatabaseBase):
    """Thread-safe, job-scoped repository composed from focused mixins."""


__all__ = ["WorkbenchDB", "default_data_dir"]
