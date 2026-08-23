# -*- coding: utf-8 -*-
"""Delivery hardening for the unified recruitment workspace.

Adds durable page persistence, browser self-healing, recruiter-authoritative profile
semantics, explicit platform-filter disclosure and manual duplicate merge support.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QAbstractItemView, QLabel, QMessageBox, QPushButton

from .delivery_browser import DeliveryBrowserWorker
from .models import BrowserEvent, RunStatus
from .product_profile import build_recruiter_confirmed_profile
from .qt_workspace import ProductRecruitmentWorkbenchWindow as _BaseWorkspace


class RecruitmentWorkspaceWindow(_BaseWorkspace):
    def __init__(self, db_path: str | None = None):
        super().__init__(db_path)

        previous_worker = self.worker
        self.worker = DeliveryBrowserWorker(self.browser_events, browser_config=self._browser_config())
        previous_worker.shutdown()

        self._install_delivery_ui()
        QTimer.singleShot(850, self._automatic_login_check)

    def _install_delivery_ui(self) -> None:
        self._update_login_ui(self.login_verified, "尚未验证智联登录" if not self.login_verified else "智联登录有效")

        notice = QLabel(
            "当前智联召回阶段仅使用“智联搜索词”。学历、经验、地点、必须能力和加分能力"
            "用于入池后的本地评估，不会自动改变智联网页筛选条件。"
        )
        notice.setObjectName("Muted")
        notice.setWordWrap(True)
        self.search_card.layout().insertWidget(1, notice)

        if hasattr(self, "runtime_detail"):
            self.runtime_detail.setText("浏览器运行时和数据目录已配置。详细路径会随诊断包保存。")

        self.candidate_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.merge_candidates_button = QPushButton("合并所选重复候选人")
        self.merge_candidates_button.setToolTip("选择两行候选人；当前行作为保留主记录，合并前会自动备份数据库")
        self.merge_candidates_button.clicked.connect(self.merge_selected_candidates)
        candidate_page = self.stack.widget(1)
        if candidate_page is not None and candidate_page.layout() is not None:
            candidate_page.layout().addWidget(self.merge_candidates_button)

    def _update_login_ui(self, logged_in: bool, message: str) -> None:
        super()._update_login_ui(logged_in, message)
        if hasattr(self, "new_job_button"):
            self.new_job_button.setEnabled(True)
            self.new_job_button.setToolTip("创建招聘岗位" if logged_in else "点击后先完成智联登录，再创建岗位")
        if hasattr(self, "empty_job_button"):
            self.empty_job_button.setEnabled(True)
            self.empty_job_button.setText("创建招聘岗位" if logged_in else "先登录智联，再创建岗位")
            self.empty_job_button.setToolTip("创建招聘岗位" if logged_in else "点击后打开受控浏览器完成智联登录")

    def _automatic_login_check(self) -> None:
        if self.active_run_id:
            return
        self._login_check_action = "startup"
        if hasattr(self, "workspace_login_hint"):
            self.workspace_login_hint.setText("正在检查已保存的智联登录状态…")
        self.worker.submit("CHECK_LOGIN")

    def _build_profile(self, values):
        return build_recruiter_confirmed_profile(
            keyword=str(values.get("keyword") or ""),
            jd=str(values.get("jd") or ""),
            min_education=str(values.get("min_education") or "不限"),
            min_experience_years=values.get("min_experience_years") or 0,
            locations=values.get("locations") or "",
            required_skills=values.get("required_skills"),
            preferred_skills=values.get("preferred_skills"),
        )

    def _ack_page(self, payload: dict, ok: bool, error: str = "") -> None:
        token = str(payload.get("ack_token") or "")
        if token:
            self.worker.submit(
                "ACK_PAGE",
                {"ack_token": token, "ok": bool(ok), "error": error},
            )

    def _handle_browser_event(self, event: BrowserEvent) -> None:
        payload = event.payload
        context = self.pending.get(event.request_id, {})
        run_id = int(payload.get("run_id") or context.get("run_id") or 0)

        if event.event == "PAGE_RESULT":
            if not run_id or not context:
                self._ack_page(payload, False, "找不到对应的招聘任务上下文")
                return
            page_no = int(payload.get("page_no") or 0)
            run = self.db.get_sourcing_run(run_id)
            if not run:
                self._ack_page(payload, False, "招聘任务不存在")
                return
            if page_no <= int(run.get("last_page") or 0):
                self._ack_page(payload, True)
                return
            try:
                summary = self.service.ingest_candidates(
                    job_id=int(context["job_id"]),
                    run_id=run_id,
                    candidates=payload.get("candidates") or [],
                )
                found_total = int(run.get("found_count") or 0) + summary.found
                new_total = int(run.get("new_count") or 0) + summary.new_job_links
                checkpoint = {
                    "last_completed_page": page_no,
                    "persisted_candidate_count": found_total,
                    "new_job_links": new_total,
                    "query": str(run.get("query") or ""),
                }
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.RUNNING,
                    found_count=found_total,
                    new_count=new_total,
                    last_page=page_no,
                    checkpoint=checkpoint,
                )
            except Exception as error:
                context["persist_failed"] = True
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.FAILED,
                    error_code="PAGE_PERSIST_FAILED",
                    error_message=str(error),
                )
                self._ack_page(payload, False, str(error))
                QMessageBox.critical(
                    self,
                    "候选人保存失败",
                    "本页候选人未能安全保存。系统不会进入下一页，可修复后从最近已提交页恢复。\n\n"
                    f"{error}",
                )
                return

            self._ack_page(payload, True)
            self.task_status.setText(
                f"第 {page_no} 页已安全保存：累计发现 {found_total} 人，新入池 {new_total} 人"
            )
            self.refresh_runs()
            self.refresh_candidates()
            self.refresh_stats()
            return

        if event.event == "CANCELLED" and context.get("persist_failed"):
            self.task_status.setText("任务因候选人保存失败而停止，可从最近已提交页恢复")
            self.progress.setValue(0)
            self.global_status.setText("候选人保存失败")
            self._finish_active_request(event.request_id)
            self.refresh_runs()
            return

        if event.event == "COMPLETED" and payload.get("page_persisted"):
            run = self.db.get_sourcing_run(run_id) if run_id else None
            if run:
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.SUCCEEDED,
                    found_count=int(run.get("found_count") or 0),
                    new_count=int(run.get("new_count") or 0),
                )
                self.task_status.setText(
                    f"搜索完成：累计发现 {run.get('found_count') or 0} 人，新入池 {run.get('new_count') or 0} 人"
                )
            self.progress.setValue(100)
            self.global_status.setText("搜索完成")
            self._finish_active_request(event.request_id)
            self.refresh_jobs(context.get("job_id"))
            self._select_page(1)
            return

        super()._handle_browser_event(event)

    def restore_database(self) -> None:
        if self.active_run_id:
            QMessageBox.warning(self, "任务运行中", "请先停止当前招聘任务，再恢复数据库。")
            return
        super().restore_database()

    def merge_selected_candidates(self) -> None:
        selection = self.candidate_table.selectionModel().selectedRows()
        rows = sorted({index.row() for index in selection})
        if len(rows) != 2:
            QMessageBox.information(self, "选择两名候选人", "请在候选人表格中选择恰好两行。当前行将作为保留记录。")
            return
        current_row = self.candidate_table.currentRow()
        primary_row = current_row if current_row in rows else rows[0]
        duplicate_row = rows[0] if rows[1] == primary_row else rows[1]

        def candidate_for_row(row: int):
            item = self.candidate_table.item(row, 0)
            if item is None:
                return None
            return self.db.get_job_candidate(int(item.data(0x0100)))

        primary = candidate_for_row(primary_row)
        duplicate = candidate_for_row(duplicate_row)
        if not primary or not duplicate:
            QMessageBox.warning(self, "无法合并", "未能读取所选候选人。")
            return
        if int(primary["candidate_id"]) == int(duplicate["candidate_id"]):
            QMessageBox.information(self, "无需合并", "两行已经指向同一候选人身份。")
            return
        answer = QMessageBox.question(
            self,
            "确认合并候选人",
            f"保留：{primary.get('name') or '未命名'} · {primary.get('title') or ''}\n"
            f"合并：{duplicate.get('name') or '未命名'} · {duplicate.get('title') or ''}\n\n"
            "岗位关联、快照、评估和跟进记录将归并到保留记录。系统会先自动备份数据库。是否继续？",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.db.merge_candidates(int(primary["candidate_id"]), int(duplicate["candidate_id"]))
        except Exception as error:
            QMessageBox.critical(self, "合并失败", str(error))
            return
        self.refresh_jobs(self.current_job_id)
        self.refresh_candidates()
        QMessageBox.information(self, "合并完成", "重复候选人已合并；合并前备份和审计记录已保存。")


__all__ = ["RecruitmentWorkspaceWindow"]
