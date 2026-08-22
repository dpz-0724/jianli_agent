# -*- coding: utf-8 -*-
"""Compatibility export for the productized Qt desktop client."""
from __future__ import annotations

from .qt_ui import RecruitmentWorkbenchWindow

# Older entrypoints imported WorkbenchApp from this module. Keep the symbol while the
# application lifecycle is now owned by QApplication in workbench_app.py.
WorkbenchApp = RecruitmentWorkbenchWindow

__all__ = ["WorkbenchApp", "RecruitmentWorkbenchWindow"]
