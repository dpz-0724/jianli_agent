# -*- coding: utf-8 -*-
"""Unified product workspace layered on top of the engineering Qt shell.

This module fixes the silent job-creation path and reorganizes the primary user flow to:
login -> create job -> confirm structured requirements -> start recruiting -> review.
The detailed automation and system pages remain available for diagnostics, but the daily
workflow no longer requires users to jump between them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .evaluation import build_requirement_profile, requirement_summary
from .models import BrowserEvent, CandidateStage, ProfileStatus
from .qt_dialogs import CandidateReviewDialog, STAGE_LABELS
from .qt_job_dialog import JobCreateDialog
from .qt_ui import (
    ASSESSMENT_LABELS,
    BROWSER_MODE_LABELS,
    MetricCard,
    RecruitmentWorkbenchWindow,
    _card,
)

LOGGER = logging.getLogger(__name__)


def _split_terms(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,，、;；/|]+", value)
    else:
        parts = [str(item) for item in value]
    return list(dict.fromkeys(part.strip() for part in parts if part and part.strip()))


class ProductRecruitmentWorkbenchWindow(RecruitmentWorkbenchWindow):
    """Daily-use workspace with visible login and structured job creation."""

    def __init__(self, db_path: str | None = None):
        self.login_verified = False
        self._login_check_action = ""
        super().__init__(db_path)
        self._update_login_ui(False, "尚未验证智联登录")
        self._sync_stepper()

    # ------------------------------------------------------------------
    # Main workspace layout
    # ------------------------------------------------------------------
    def _build_stepper(self) -> QFrame:
        frame, layout = _card("开始招聘", "登录、建岗、确认标准，然后一键启动搜索。")
        row = QHBoxLayout()
        self.step_widgets: list[tuple[QLabel, QLabel]] = []
        steps = ("登录智联", "创建岗位", "确认岗位标准", "开始招聘")
        for index, text in enumerate(steps, 1):
            number = QLabel(str(index))
            number.setAlignment(Qt.AlignCenter)
            label = QLabel(text)
            row.addWidget(number)
            row.addWidget(label)
            if index < len(steps):
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setStyleSheet("color:#D0D5DD; min-width:36px;")
                row.addWidget(line, 1)
            self.step_widgets.append((number, label))
        layout.addLayout(row)
        self._update_stepper(0)
        return frame

    def _build_job_page(self) -> QWidget:
        scroll, _container, content = self._page_scroll()
        content.addWidget(self._build_stepper())

        login_card, login_layout = _card(
            "智联登录与受控浏览器",
            "先登录智联。工作台会复用同一登录状态，后续搜索、候选人来源和人工接管都在这个受控浏览器中完成。",
        )
        login_status = QHBoxLayout()
        self.workspace_login_chip = QLabel("智联：未验证")
        self.workspace_login_chip.setObjectName("StatusChip")
        self.workspace_browser_label = QLabel("浏览器：尚未启动")
        self.workspace_browser_label.setObjectName("Muted")
        self.workspace_browser_label.setWordWrap(True)
        login_status.addWidget(self.workspace_login_chip)
        login_status.addWidget(self.workspace_browser_label, 1)
        login_layout.addLayout(login_status)

        login_actions = QHBoxLayout()
        self.open_login_button = QPushButton("打开智联并登录")
        self.open_login_button.setObjectName("PrimaryButton")
        self.open_login_button.clicked.connect(self.open_login)
        self.verify_login_button = QPushButton("我已完成登录，重新验证")
        self.verify_login_button.clicked.connect(self.verify_login)
        show_browser_button = QPushButton("显示浏览器")
        show_browser_button.clicked.connect(self.show_browser)
        login_actions.addWidget(self.open_login_button)
        login_actions.addWidget(self.verify_login_button)
        login_actions.addWidget(show_browser_button)
        login_actions.addStretch(1)
        login_layout.addLayout(login_actions)
        self.workspace_login_hint = QLabel("完成登录后即可创建岗位。")
        self.workspace_login_hint.setObjectName("Muted")
        self.workspace_login_hint.setWordWrap(True)
        login_layout.addWidget(self.workspace_login_hint)
        content.addWidget(login_card)

        self.empty_card, empty_layout = _card(
            "创建第一个招聘岗位",
            "支持结构化学历、经验、地点、必须能力和加分能力，也可以粘贴完整岗位 JD。",
        )
        self.empty_job_button = QPushButton("创建招聘岗位")
        self.empty_job_button.setObjectName("PrimaryButton")
        self.empty_job_button.clicked.connect(self.new_job)
        empty_layout.addWidget(self.empty_job_button, alignment=Qt.AlignLeft)
        content.addWidget(self.empty_card)

        self.profile_card, profile_layout = _card(
            "岗位标准",
            "学历与经验按硬性条件处理；必须能力缺失会进入人工核验，不会仅因摘要未出现就自动淘汰。",
        )
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.title_edit = QLineEdit()
        self.keyword_edit = QLineEdit()
        self.education_combo = QComboBox()
        self.education_combo.addItems(("不限", "高中", "大专", "本科", "硕士", "博士"))
        self.experience_spin = QSpinBox()
        self.experience_spin.setRange(0, 30)
        self.experience_spin.setSuffix(" 年")
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText("多个地点用顿号或逗号分隔")
        self.required_skills_edit = QLineEdit()
        self.required_skills_edit.setPlaceholderText("例如：Java、Spring Boot、MySQL")
        self.preferred_skills_edit = QLineEdit()
        self.preferred_skills_edit.setPlaceholderText("例如：微服务、Kubernetes、金融行业")
        self.jd_edit = QTextEdit()
        self.jd_edit.setMinimumHeight(180)
        self.jd_edit.setPlaceholderText("粘贴完整岗位职责、任职要求和优先项")

        form.addWidget(QLabel("岗位名称"), 0, 0)
        form.addWidget(self.title_edit, 0, 1)
        form.addWidget(QLabel("智联搜索词"), 0, 2)
        form.addWidget(self.keyword_edit, 0, 3)
        form.addWidget(QLabel("硬性：最低学历"), 1, 0)
        form.addWidget(self.education_combo, 1, 1)
        form.addWidget(QLabel("硬性：最低经验"), 1, 2)
        form.addWidget(self.experience_spin, 1, 3)
        form.addWidget(QLabel("工作地点"), 2, 0)
        form.addWidget(self.location_edit, 2, 1, 1, 3)
        form.addWidget(QLabel("必须能力"), 3, 0)
        form.addWidget(self.required_skills_edit, 3, 1, 1, 3)
        form.addWidget(QLabel("加分能力"), 4, 0)
        form.addWidget(self.preferred_skills_edit, 4, 1, 1, 3)
        form.addWidget(QLabel("岗位 JD"), 5, 0, Qt.AlignTop)
        form.addWidget(self.jd_edit, 5, 1, 1, 3)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        profile_layout.addLayout(form)

        self.profile_summary = QLabel("请先创建岗位。")
        self.profile_summary.setWordWrap(True)
        self.profile_summary.setObjectName("Muted")
        profile_layout.addWidget(self.profile_summary)
        profile_actions = QHBoxLayout()
        self.profile_state_chip = QLabel("岗位标准：未建立")
        self.profile_state_chip.setObjectName("StatusChip")
        self.parse_button = QPushButton("解析并保存草稿")
        self.parse_button.clicked.connect(self.parse_profile)
        self.confirm_button = QPushButton("确认岗位标准")
        self.confirm_button.setObjectName("SuccessButton")
        self.confirm_button.clicked.connect(self.confirm_profile)
        self.reassess_button = QPushButton("重新评估候选人")
        self.reassess_button.clicked.connect(self.reassess)
        self.archive_button = QPushButton("归档岗位")
        self.archive_button.clicked.connect(self.archive_job)
        profile_actions.addWidget(self.profile_state_chip)
        profile_actions.addStretch(1)
        profile_actions.addWidget(self.archive_button)
        profile_actions.addWidget(self.reassess_button)
        profile_actions.addWidget(self.parse_button)
        profile_actions.addWidget(self.confirm_button)
        profile_layout.addLayout(profile_actions)
        content.addWidget(self.profile_card)

        self.search_card, search_layout = _card(
            "开始招聘",
            "系统按平台 UID 优先去重；同岗位已出现的人不会重复入池，跨岗位已见的人会在候选人列表标记。",
        )
        plan = QGridLayout()
        self.max_pages_spin = QSpinBox()
        self.max_pages_spin.setRange(1, 20)
        self.max_count_spin = QSpinBox()
        self.max_count_spin.setRange(1, 2000)
        self.max_count_spin.setSingleStep(50)
        self.browser_mode_combo = QComboBox()
        for value in ("managed", "edge", "chrome", "auto", "custom"):
            self.browser_mode_combo.addItem(BROWSER_MODE_LABELS[value], value)
        self.visible_check = QCheckBox("显示自动化浏览器")
        self.sidecar_check = QCheckBox("工作台与浏览器左右分屏")
        plan.addWidget(QLabel("搜索页数"), 0, 0)
        plan.addWidget(self.max_pages_spin, 0, 1)
        plan.addWidget(QLabel("人数上限"), 0, 2)
        plan.addWidget(self.max_count_spin, 0, 3)
        plan.addWidget(QLabel("浏览器"), 1, 0)
        plan.addWidget(self.browser_mode_combo, 1, 1, 1, 2)
        plan.addWidget(self.visible_check, 1, 3)
        plan.addWidget(self.sidecar_check, 1, 4)
        plan.setColumnStretch(2, 1)
        search_layout.addLayout(plan)

        search_actions = QHBoxLayout()
        self.start_button = QPushButton("开始招聘")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start_search)
        self.login_button = QPushButton("验证登录并继续")
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self.continue_after_login)
        self.demo_button = QPushButton("导入演示数据")
        self.demo_button.clicked.connect(self.import_demo)
        show_button = QPushButton("显示浏览器")
        show_button.clicked.connect(self.show_browser)
        pause_button = QPushButton("暂停")
        pause_button.clicked.connect(self.pause_task)
        takeover_button = QPushButton("人工接管")
        takeover_button.clicked.connect(self.take_over)
        resume_button = QPushButton("继续")
        resume_button.setObjectName("SuccessButton")
        resume_button.clicked.connect(self.resume_task)
        stop_button = QPushButton("停止")
        stop_button.setObjectName("DangerButton")
        stop_button.clicked.connect(self.cancel_task)
        for button in (
            self.start_button,
            self.login_button,
            show_button,
            pause_button,
            takeover_button,
            resume_button,
            stop_button,
        ):
            search_actions.addWidget(button)
        search_actions.addStretch(1)
        search_actions.addWidget(self.demo_button)
        search_layout.addLayout(search_actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.task_status = QLabel("当前没有运行任务")
        self.task_status.setObjectName("Muted")
        search_layout.addWidget(self.progress)
        search_layout.addWidget(self.task_status)
        content.addWidget(self.search_card)

        metrics = QHBoxLayout()
        self.job_total_metric = MetricCard("本岗位候选人")
        self.job_pass_metric = MetricCard("建议优先查看")
        self.job_review_metric = MetricCard("信息待核验")
        self.job_conflict_metric = MetricCard("明确冲突")
        for metric in (
            self.job_total_metric,
            self.job_pass_metric,
            self.job_review_metric,
            self.job_conflict_metric,
        ):
            metrics.addWidget(metric)
        content.addLayout(metrics)
        content.addStretch(1)

        self._job_controls = [
            self.title_edit,
            self.keyword_edit,
            self.education_combo,
            self.experience_spin,
            self.location_edit,
            self.required_skills_edit,
            self.preferred_skills_edit,
            self.jd_edit,
            self.parse_button,
            self.confirm_button,
            self.reassess_button,
            self.archive_button,
            self.start_button,
            self.demo_button,
        ]
        for widget in (
            self.title_edit,
            self.keyword_edit,
            self.location_edit,
            self.required_skills_edit,
            self.preferred_skills_edit,
        ):
            widget.textEdited.connect(self._mark_profile_dirty)
        self.jd_edit.textChanged.connect(self._profile_text_changed)
        self.education_combo.currentTextChanged.connect(lambda _text: self._mark_profile_dirty())
        self.experience_spin.valueChanged.connect(lambda _value: self._mark_profile_dirty())
        return scroll

    def _build_candidate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(14)

        metrics = QHBoxLayout()
        self.candidate_metrics = {
            "total": MetricCard("全部候选人"),
            "PASS": MetricCard("建议优先查看"),
            "REVIEW": MetricCard("信息待核验"),
            "CONFLICT": MetricCard("明确冲突"),
        }
        for metric in self.candidate_metrics.values():
            metrics.addWidget(metric)
        layout.addLayout(metrics)

        card, card_layout = _card(
            "候选人收件箱",
            "“首次入池 / 本岗位已更新 / 跨岗位已见”用于说明去重历史；招聘阶段用于说明是否已经处理过。",
        )
        filters = QHBoxLayout()
        self.assessment_filter = QComboBox()
        self.assessment_filter.addItem("全部评估", "ALL")
        self.assessment_filter.addItem("建议优先查看", "PASS")
        self.assessment_filter.addItem("信息待核验", "REVIEW")
        self.assessment_filter.addItem("明确冲突", "CONFLICT")
        self.stage_filter = QComboBox()
        self.stage_filter.addItem("全部处理状态", "ALL")
        for value, label in STAGE_LABELS.items():
            self.stage_filter.addItem(label, value)
        self.history_filter = QComboBox()
        self.history_filter.addItem("全部去重状态", "ALL")
        self.history_filter.addItem("首次入池", "NEW")
        self.history_filter.addItem("本岗位已更新", "UPDATED")
        self.history_filter.addItem("跨岗位已见", "CROSS_JOB")
        self.candidate_search = QLineEdit()
        self.candidate_search.setPlaceholderText("搜索姓名、职位、技能或简历文本")
        refresh = QPushButton("筛选")
        refresh.clicked.connect(self.refresh_candidates)
        export = QPushButton("导出本岗位")
        export.clicked.connect(self.export_job)
        filters.addWidget(self.assessment_filter)
        filters.addWidget(self.stage_filter)
        filters.addWidget(self.history_filter)
        filters.addWidget(self.candidate_search, 1)
        filters.addWidget(refresh)
        filters.addWidget(export)
        card_layout.addLayout(filters)

        self.candidate_table = QTableWidget(0, 10)
        self.candidate_table.setHorizontalHeaderLabels(
            ("评估", "匹配度", "姓名", "当前/期望职位", "地点", "学历", "经验", "去重/历史", "处理状态", "负责人")
        )
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.candidate_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.candidate_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.candidate_table.setAlternatingRowColors(True)
        self.candidate_table.verticalHeader().setVisible(False)
        header = self.candidate_table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for index in (0, 1, 2, 4, 5, 6, 7, 8, 9):
            header.setSectionResizeMode(index, QHeaderView.ResizeToContents)
        self.candidate_table.doubleClicked.connect(self.review_candidate)
        card_layout.addWidget(self.candidate_table, 1)

        actions = QHBoxLayout()
        review = QPushButton("查看并复核")
        review.setObjectName("PrimaryButton")
        review.clicked.connect(self.review_candidate)
        to_contact = QPushButton("标记待联系")
        to_contact.clicked.connect(lambda: self.quick_stage(CandidateStage.TO_CONTACT))
        contacted = QPushButton("标记已联系")
        contacted.clicked.connect(lambda: self.quick_stage(CandidateStage.CONTACTED))
        talent = QPushButton("转入人才库")
        talent.clicked.connect(lambda: self.quick_stage(CandidateStage.TALENT_POOL))
        actions.addWidget(review)
        actions.addWidget(to_contact)
        actions.addWidget(contacted)
        actions.addWidget(talent)
        actions.addStretch(1)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        self.assessment_filter.currentIndexChanged.connect(self.refresh_candidates)
        self.stage_filter.currentIndexChanged.connect(self.refresh_candidates)
        self.history_filter.currentIndexChanged.connect(self.refresh_candidates)
        self.candidate_search.returnPressed.connect(self.refresh_candidates)
        return page

    # ------------------------------------------------------------------
    # Login-first flow
    # ------------------------------------------------------------------
    def _update_login_ui(self, logged_in: bool, message: str) -> None:
        self.login_verified = bool(logged_in)
        if hasattr(self, "workspace_login_chip"):
            self.workspace_login_chip.setText("智联：已登录" if logged_in else "智联：未登录")
            self.workspace_login_hint.setText(message)
        if hasattr(self, "new_job_button"):
            self.new_job_button.setEnabled(logged_in)
        if hasattr(self, "empty_job_button"):
            self.empty_job_button.setEnabled(logged_in)
        self._sync_stepper()

    def _sync_stepper(self) -> None:
        if not hasattr(self, "step_widgets"):
            return
        if not self.login_verified:
            self._update_stepper(0)
            return
        if not self.current_job_id:
            self._update_stepper(1)
            return
        job = self.db.get_job(self.current_job_id)
        confirmed = bool(job and job.get("profile_status") == ProfileStatus.CONFIRMED.value)
        self._update_stepper(3 if confirmed and not self._profile_dirty else 2)

    def open_login(self) -> None:
        self._login_check_action = "preflight"
        config = self._browser_config()
        config["browser_visible"] = True
        self.worker.submit("CONFIGURE_BROWSER", config)
        self.worker.submit("CHECK_LOGIN")
        self.worker.submit("BRING_TO_FRONT")
        self.workspace_login_hint.setText("请在受控浏览器中完成智联登录，然后点击“重新验证”。")
        self.global_status.setText("等待智联登录")

    def verify_login(self) -> None:
        self._login_check_action = "preflight"
        self.worker.submit("CHECK_LOGIN")
        self.worker.submit("BRING_TO_FRONT")
        self.workspace_login_hint.setText("正在验证智联登录状态…")

    def continue_after_login(self) -> None:
        if not self.waiting_login:
            return
        self._login_check_action = "resume_search"
        self.worker.submit("CHECK_LOGIN")
        self.worker.submit("BRING_TO_FRONT")
        self.task_status.setText("正在验证登录状态…")

    def start_search(self) -> None:
        if not self.login_verified:
            QMessageBox.information(self, "请先登录智联", "完成智联登录并验证后，才能开始招聘。")
            self.open_login()
            return
        super().start_search()

    # ------------------------------------------------------------------
    # Reliable job creation and structured profile
    # ------------------------------------------------------------------
    def _build_profile(self, values: dict[str, Any]):
        profile = build_requirement_profile(
            keyword=str(values.get("keyword") or ""),
            jd=str(values.get("jd") or ""),
            min_education=str(values.get("min_education") or ""),
            min_experience_years=values.get("min_experience_years") or 0,
            locations=values.get("locations") or "",
        )
        explicit_required = _split_terms(values.get("required_skills"))
        explicit_preferred = _split_terms(values.get("preferred_skills"))
        required = tuple(explicit_required) if explicit_required else profile.required_skills
        preferred = tuple(skill for skill in (explicit_preferred or list(profile.preferred_skills)) if skill not in required)
        evidence = dict(profile.source_evidence)
        for skill in explicit_required:
            evidence.setdefault(f"skill:{skill}", []).append("招聘人员结构化填写：必须能力")
        for skill in explicit_preferred:
            evidence.setdefault(f"skill:{skill}", []).append("招聘人员结构化填写：加分能力")
        return replace(
            profile,
            required_skills=required,
            preferred_skills=preferred,
            source_evidence=evidence,
        )

    def new_job(self) -> None:
        if not self.login_verified:
            QMessageBox.information(self, "先登录智联", "请先完成智联登录。登录成功后即可创建岗位。")
            self.open_login()
            return
        try:
            dialog = JobCreateDialog(self)
            result = dialog.exec()
        except Exception as error:
            LOGGER.exception("创建岗位对话框打开失败")
            QMessageBox.critical(self, "无法打开创建岗位", f"创建岗位窗口未能打开：\n{error}")
            return
        if result != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        job_id: int | None = None
        try:
            job_id = self.db.create_job(values["title"], values["keyword"], values["jd"])
            profile = self._build_profile(values)
            self.db.update_job(
                job_id,
                title=values["title"],
                keyword=values["keyword"],
                jd=values["jd"],
                profile=profile,
                profile_status=ProfileStatus.DRAFT,
            )
        except Exception as error:
            LOGGER.exception("创建岗位失败")
            if job_id is not None:
                try:
                    self.db.delete_job(job_id)
                except Exception:
                    LOGGER.exception("回滚未完成岗位失败")
            QMessageBox.critical(self, "创建失败", f"岗位未创建：\n{error}")
            return
        self.refresh_jobs(job_id)
        self._select_page(0)
        self.global_status.setText(f"岗位已创建：{values['title']}")
        self._sync_stepper()

    def refresh_jobs(self, select_id: int | None = None) -> None:
        super().refresh_jobs(select_id)
        self._sync_stepper()

    def load_job(self, job_id: int) -> None:
        super().load_job(job_id)
        self._loading_job = True
        try:
            profile = self.service.load_profile(job_id)
            self.required_skills_edit.setText("、".join(profile.required_skills))
            self.preferred_skills_edit.setText("、".join(profile.preferred_skills))
        finally:
            self._loading_job = False
        self._sync_stepper()

    def parse_profile(self) -> bool:
        if not self.current_job_id:
            QMessageBox.information(self, "提示", "请先创建岗位。")
            return False
        values = {
            "title": self.title_edit.text().strip(),
            "keyword": self.keyword_edit.text().strip() or self.title_edit.text().strip(),
            "jd": self.jd_edit.toPlainText().strip(),
            "min_education": self.education_combo.currentText(),
            "min_experience_years": self.experience_spin.value(),
            "locations": self.location_edit.text(),
            "required_skills": self.required_skills_edit.text(),
            "preferred_skills": self.preferred_skills_edit.text(),
        }
        if not values["title"]:
            QMessageBox.warning(self, "岗位名称缺失", "请填写岗位名称。")
            self.title_edit.setFocus()
            return False
        try:
            profile = self._build_profile(values)
            self.db.update_job(
                self.current_job_id,
                title=values["title"],
                keyword=values["keyword"],
                jd=values["jd"],
                profile=profile,
                profile_status=ProfileStatus.DRAFT,
            )
        except Exception as error:
            LOGGER.exception("保存岗位标准草稿失败")
            QMessageBox.critical(self, "保存失败", str(error))
            return False
        self.profile_summary.setText(requirement_summary(profile))
        self.profile_state_chip.setText("岗位标准：草稿，等待确认")
        self._profile_dirty = False
        self.confirm_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.refresh_jobs(self.current_job_id)
        self._sync_stepper()
        return True

    def _mark_profile_dirty(self) -> None:
        super()._mark_profile_dirty()
        self._sync_stepper()

    def confirm_profile(self) -> None:
        super().confirm_profile()
        self._sync_stepper()

    # ------------------------------------------------------------------
    # Browser events and login state
    # ------------------------------------------------------------------
    def _handle_browser_event(self, event: BrowserEvent) -> None:
        payload = event.payload
        if event.event == "LOGIN_CHECKED":
            logged_in = bool(payload.get("logged_in"))
            action = self._login_check_action
            self._login_check_action = ""
            if logged_in:
                self._update_login_ui(True, "智联登录有效。现在可以创建岗位或开始招聘。")
                self.global_status.setText("智联已登录")
                if action == "resume_search" and self.waiting_login:
                    super().continue_after_login()
            else:
                self._update_login_ui(False, "尚未检测到有效登录，请在受控浏览器完成登录后重新验证。")
                self.global_status.setText("等待智联登录")
            self._log(str(payload.get("message") or "登录状态已检查"))
            return
        if event.event == "NEED_LOGIN":
            self._update_login_ui(False, "搜索需要登录。请在受控浏览器完成登录，再点击“验证登录并继续”。")
        elif event.event == "BROWSER_PROFILE_CLEARED":
            self._update_login_ui(False, "智联登录状态已清除。")
        elif event.event == "BROWSER_STATUS":
            mode = str(payload.get("mode") or "-")
            version = str(payload.get("version") or "")
            running = bool(payload.get("running"))
            if hasattr(self, "workspace_browser_label"):
                self.workspace_browser_label.setText(
                    f"浏览器：{BROWSER_MODE_LABELS.get(mode, mode)} {version} · {'运行中' if running else '未启动'}".strip()
                )
        super()._handle_browser_event(event)

    # ------------------------------------------------------------------
    # Candidate history and review
    # ------------------------------------------------------------------
    def _candidate_history_map(self, candidate_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not candidate_ids:
            return {}
        placeholders = ",".join("?" for _ in candidate_ids)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT c.id AS candidate_id,
                    (SELECT COUNT(DISTINCT jc2.job_id) FROM job_candidates jc2 WHERE jc2.candidate_id=c.id) AS job_count,
                    (SELECT COUNT(*) FROM candidate_snapshots cs WHERE cs.candidate_id=c.id) AS snapshot_count,
                    (SELECT GROUP_CONCAT(j2.title, '、')
                       FROM job_candidates jc3 JOIN jobs j2 ON j2.id=jc3.job_id
                      WHERE jc3.candidate_id=c.id AND jc3.job_id<>?) AS other_jobs
                FROM candidates c WHERE c.id IN ({placeholders})
                """,
                [self.current_job_id, *candidate_ids],
            ).fetchall()
        return {int(row["candidate_id"]): dict(row) for row in rows}

    @staticmethod
    def _history_status(item: dict[str, Any]) -> tuple[str, str]:
        if int(item.get("job_count") or 0) > 1:
            other = str(item.get("other_jobs") or "")
            return "CROSS_JOB", f"跨岗位已见{(' · ' + other) if other else ''}"
        if int(item.get("snapshot_count") or 0) > 1:
            return "UPDATED", "本岗位已更新"
        return "NEW", "首次入池"

    def refresh_candidates(self) -> None:
        self.candidate_table.setRowCount(0)
        if not self.current_job_id:
            for metric in self.candidate_metrics.values():
                metric.set_value(0)
            return
        rows = self.db.list_job_candidates(
            self.current_job_id,
            assessment_status=str(self.assessment_filter.currentData() or "ALL"),
            stage=str(self.stage_filter.currentData() or "ALL"),
            search=self.candidate_search.text(),
        )
        history = self._candidate_history_map([int(row["candidate_id"]) for row in rows])
        selected_history = str(self.history_filter.currentData() or "ALL")
        for row_data in rows:
            history_code, history_label = self._history_status(history.get(int(row_data["candidate_id"]), {}))
            if selected_history != "ALL" and history_code != selected_history:
                continue
            row = self.candidate_table.rowCount()
            self.candidate_table.insertRow(row)
            score = "" if row_data.get("fit_score") is None else f"{float(row_data['fit_score']):.1f}"
            values = (
                ASSESSMENT_LABELS.get(row_data.get("assessment_status"), "尚未评估"),
                score,
                row_data.get("name", ""),
                row_data.get("title", ""),
                row_data.get("location", ""),
                row_data.get("education", ""),
                row_data.get("experience", ""),
                history_label,
                STAGE_LABELS.get(row_data.get("stage"), row_data.get("stage", "")),
                row_data.get("owner", ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if column == 0:
                    item.setData(Qt.UserRole, int(row_data["job_candidate_id"]))
                self.candidate_table.setItem(row, column, item)
        self.refresh_stats()

    def review_candidate(self) -> None:
        candidate_id = self._selected_candidate_id()
        candidate = self.db.get_job_candidate(candidate_id) if candidate_id else None
        if not candidate:
            QMessageBox.information(self, "提示", "请先选择候选人。")
            return
        dialog = CandidateReviewDialog(candidate, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.open_source_requested:
            self.worker.submit("OPEN_URL", {"url": candidate.get("source_url") or ""})
            return
        values = dialog.values()
        self.db.update_job_candidate(
            candidate_id,
            stage=values["stage"],
            owner=values["owner"],
            note=values["note"],
            next_follow_up_at=values["next_follow_up_at"],
        )
        if values["decision"]:
            self.db.add_review_decision(candidate_id, values["decision"], values["decision_reason"])
        self.db.add_follow_up(candidate_id, "REVIEW_SAVED", values["decision_reason"])
        self.refresh_candidates()
