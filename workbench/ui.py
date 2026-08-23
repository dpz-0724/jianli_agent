# -*- coding: utf-8 -*-
"""Compatibility export for the productized Qt desktop client."""
from __future__ import annotations

from .qt_workspace_runtime import RecruitmentWorkspaceWindow

RecruitmentWorkbenchWindow = RecruitmentWorkspaceWindow
WorkbenchApp = RecruitmentWorkspaceWindow
ProductRecruitmentWorkbenchWindow = RecruitmentWorkspaceWindow

__all__ = ["WorkbenchApp", "RecruitmentWorkbenchWindow", "ProductRecruitmentWorkbenchWindow"]
