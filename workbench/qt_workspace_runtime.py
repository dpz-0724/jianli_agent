# -*- coding: utf-8 -*-
"""Runtime refinements for the unified recruitment workspace.

The create action must never look dead. Before login it remains clickable and routes the
user into the login flow; after login it opens the structured job dialog. A saved login
is also checked automatically on startup so returning recruiters do not have to repeat a
manual verification step.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer

from .qt_workspace import ProductRecruitmentWorkbenchWindow as _BaseWorkspace


class RecruitmentWorkspaceWindow(_BaseWorkspace):
    def __init__(self, db_path: str | None = None):
        super().__init__(db_path)
        QTimer.singleShot(850, self._automatic_login_check)

    def _update_login_ui(self, logged_in: bool, message: str) -> None:
        super()._update_login_ui(logged_in, message)
        # Do not disable the create action. Disabled-looking buttons are interpreted as
        # broken by users; new_job() already provides the correct login-first guidance.
        if hasattr(self, "new_job_button"):
            self.new_job_button.setEnabled(True)
            self.new_job_button.setToolTip(
                "创建招聘岗位" if logged_in else "点击后先完成智联登录，再创建岗位"
            )
        if hasattr(self, "empty_job_button"):
            self.empty_job_button.setEnabled(True)
            self.empty_job_button.setText("创建招聘岗位" if logged_in else "先登录智联，再创建岗位")
            self.empty_job_button.setToolTip(
                "创建招聘岗位" if logged_in else "点击后打开受控浏览器完成智联登录"
            )

    def _automatic_login_check(self) -> None:
        if self.active_run_id:
            return
        self._login_check_action = "startup"
        if hasattr(self, "workspace_login_hint"):
            self.workspace_login_hint.setText("正在检查已保存的智联登录状态…")
        self.worker.submit("CHECK_LOGIN")


__all__ = ["RecruitmentWorkspaceWindow"]
