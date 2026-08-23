# -*- coding: utf-8 -*-
"""Compatibility export for the productized Qt desktop client."""
from __future__ import annotations

from .qt_workspace import ProductRecruitmentWorkbenchWindow

RecruitmentWorkbenchWindow = ProductRecruitmentWorkbenchWindow
WorkbenchApp = ProductRecruitmentWorkbenchWindow

__all__ = ["WorkbenchApp", "RecruitmentWorkbenchWindow", "ProductRecruitmentWorkbenchWindow"]
