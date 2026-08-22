# -*- coding: utf-8 -*-
"""Modern PySide6 desktop client for the recruitment automation workbench."""
from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .browser_runtime import browser_profile_dir, runtime_summary
from .browser_worker import BrowserWorker
from .database import WorkbenchDB, default_data_dir
from .demo import demo_candidates
from .evaluation import requirement_summary
from .models import BrowserEvent, CandidateStage, JobStatus, ProfileStatus, RunStatus, SearchPlan
from .qt_dialogs import CandidateReviewDialog, NewJobDialog, STAGE_LABELS
from .qt_theme import APP_STYLE
from .service import RecruitmentService
from .settings import AppSettings, load_settings, save_settings

ASSESSMENT_LABELS = {
    "PASS": "建议优先查看",
    "REVIEW": "信息待核验",
    "CONFLICT": "存在明确冲突",
    None: "尚未评估",
}
RUN_LABELS = {
    "PENDING": "等待运行",
    "RUNNING": "运行中",
    "NEED_LOGIN": "等待登录",
    "PAUSED": "已暂停",
    "TAKEOVER": "人工接管",
    "SUCCEEDED": "已完成",
    "FAILED": "未完成",
    "CANCELLED": "已停止",
}
BROWSER_MODE_LABELS = {
    "managed": "工作台 Chromium（推荐）",
    "edge": "Microsoft Edge",
    "chrome": "Google Chrome",
    "auto": "自动选择",
    "custom": "自定义 Chromium 路径",
}


def _card(title: str, hint: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("CardTitle")
    layout.addWidget(heading)
    if hint:
        helper = QLabel(hint)
        helper.setWordWrap(True)
        helper.setObjectName("CardHint")
        layout.addWidget(helper)
    return frame, layout


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "0"):
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        label_widget = QLabel(label)
        label_widget.setObjectName("MetricLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(label_widget)

    def set_value(self, value: Any) -> None:
        self.value_label.setText(str(value))


class RecruitmentWorkbenchWindow(QMainWindow):
    def __init__(self, db_path: str | None = None):
        super().__init__()
        self.setWindowTitle("招聘自动化工作台")
        self.setMinimumSize(1180, 760)
        self.resize(1480, 900)
        self.setStyleSheet(APP_STYLE)

        self.db = WorkbenchDB(db_path)
        self.service = RecruitmentService(self.db)
        self.settings: AppSettings = load_settings()
        self.browser_events: "queue.Queue[BrowserEvent]" = queue.Queue()
        self.worker = BrowserWorker(self.browser_events, browser_config=self._browser_config())
        self.current_job_id: int | None = None
        self.pending: dict[str, dict[str, Any]] = {}
        self.waiting_login: dict[str, Any] | None = None
        self.active_run_id: int | None = None
        self._loading_job = False
        self._profile_dirty = False

        self._build_ui()
        self.refresh_jobs()
        self._apply_settings_to_controls()
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self._poll_browser_events)
        self.event_timer.start(120)
        QTimer.singleShot(400, self.check_browser_status)
        QTimer.singleShot(650, self._show_recovery_notice)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        shell.addWidget(self._build_sidebar())
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_job_page())
        self.stack.addWidget(self._build_candidate_page())
        self.stack.addWidget(self._build_automation_page())
        self.stack.addWidget(self._build_settings_page())
        main_layout.addWidget(self.stack, 1)
        shell.addWidget(main, 1)
        self._select_page(0)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(272)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 20, 18, 16)
        layout.setSpacing(10)

        brand_row = QHBoxLayout()
        mark = QLabel("招")
        mark.setObjectName("BrandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(42, 42)
        brand_text = QVBoxLayout()
        title = QLabel("招聘自动化工作台")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("岗位中心 · 人工复核")
        subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_text, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(10)

        self.nav_buttons: list[QPushButton] = []
        for index, text in enumerate(("岗位工作台", "候选人收件箱", "自动化任务", "系统与数据")):
            button = QPushButton(text)
            button.setObjectName("SidebarButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, page=index: self._select_page(page))
            layout.addWidget(button)
            self.nav_buttons.append(button)

        layout.addSpacing(12)
        job_header = QHBoxLayout()
        job_label = QLabel("招聘岗位")
        job_label.setObjectName("SidebarHint")
        self.new_job_button = QPushButton("＋ 新建")
        self.new_job_button.setObjectName("SidebarButton")
        self.new_job_button.clicked.connect(self.new_job)
        job_header.addWidget(job_label)
        job_header.addStretch(1)
        job_header.addWidget(self.new_job_button)
        layout.addLayout(job_header)

        self.job_list = QListWidget()
        self.job_list.setObjectName("JobList")
        self.job_list.currentItemChanged.connect(self._job_item_changed)
        layout.addWidget(self.job_list, 1)

        self.sidebar_browser = QLabel("浏览器：未检查")
        self.sidebar_browser.setObjectName("SidebarHint")
        self.sidebar_browser.setWordWrap(True)
        layout.addWidget(self.sidebar_browser)
        version = QLabel("V0.9 Productization Alpha")
        version.setObjectName("SidebarHint")
        layout.addWidget(version)
        return sidebar

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(78)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 12, 24, 12)
        titles = QVBoxLayout()
        self.page_title = QLabel("岗位工作台")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("创建岗位、确认标准，再启动受控搜索")
        self.page_subtitle.setObjectName("PageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)
        self.global_status = QLabel("就绪")
        self.global_status.setObjectName("StatusChip")
        layout.addWidget(self.global_status)
        return bar

    def _page_scroll(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(24, 22, 24, 28)
        content.setSpacing(16)
        scroll.setWidget(container)
        return scroll, container, content

    def _build_stepper(self) -> QFrame:
        frame, layout = _card("招聘流程", "按顺序完成，系统会在关键节点保留人工确认。")
        row = QHBoxLayout()
        self.step_widgets: list[tuple[QLabel, QLabel]] = []
        steps = ("创建岗位", "确认岗位标准", "连接受控浏览器", "搜索并复核")
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

        self.empty_card, empty_layout = _card("从第一个岗位开始", "粘贴岗位 JD，系统会生成必须能力、加分能力、学历、经验和地点建议。")
        empty_button = QPushButton("创建招聘岗位")
        empty_button.setObjectName("PrimaryButton")
        empty_button.clicked.connect(self.new_job)
        empty_layout.addWidget(empty_button, alignment=Qt.AlignLeft)
        content.addWidget(self.empty_card)

        self.profile_card, profile_layout = _card(
            "岗位画像",
            "解析结果只是草稿。招聘人员确认后，才会作为候选人搜索和评估依据。",
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
        self.jd_edit = QTextEdit()
        self.jd_edit.setMinimumHeight(190)
        self.jd_edit.setPlaceholderText("粘贴完整岗位 JD")

        form.addWidget(QLabel("岗位名称"), 0, 0)
        form.addWidget(self.title_edit, 0, 1)
        form.addWidget(QLabel("搜索关键词"), 0, 2)
        form.addWidget(self.keyword_edit, 0, 3)
        form.addWidget(QLabel("最低学历"), 1, 0)
        form.addWidget(self.education_combo, 1, 1)
        form.addWidget(QLabel("最低经验"), 1, 2)
        form.addWidget(self.experience_spin, 1, 3)
        form.addWidget(QLabel("工作地点"), 2, 0)
        form.addWidget(self.location_edit, 2, 1, 1, 3)
        form.addWidget(QLabel("岗位 JD"), 3, 0, Qt.AlignTop)
        form.addWidget(self.jd_edit, 3, 1, 1, 3)
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
        self.reassess_button = QPushButton("重新评估现有候选人")
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
            "搜索计划",
            "默认使用工作台自带 Chromium。运行时会打开独立受控浏览器，方便观察、暂停和人工接管。",
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
        self.sidecar_check = QCheckBox("启动时左右分屏")
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
        self.start_button = QPushButton("开始智联搜索")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start_search)
        self.login_button = QPushButton("已登录，继续搜索")
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self.continue_after_login)
        self.demo_button = QPushButton("导入演示数据")
        self.demo_button.clicked.connect(self.import_demo)
        search_actions.addWidget(self.start_button)
        search_actions.addWidget(self.login_button)
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
        for metric in (self.job_total_metric, self.job_pass_metric, self.job_review_metric, self.job_conflict_metric):
            metrics.addWidget(metric)
        content.addLayout(metrics)
        content.addStretch(1)

        self._job_controls = [
            self.title_edit, self.keyword_edit, self.education_combo, self.experience_spin,
            self.location_edit, self.jd_edit, self.parse_button, self.confirm_button,
            self.reassess_button, self.archive_button, self.start_button, self.demo_button,
        ]
        for widget in (self.title_edit, self.keyword_edit, self.location_edit):
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

        filter_card, filter_layout = _card("候选人收件箱", "双击候选人查看证据、记录人工结论和下一次跟进。")
        filters = QHBoxLayout()
        self.assessment_filter = QComboBox()
        self.assessment_filter.addItem("全部评估", "ALL")
        self.assessment_filter.addItem("建议优先查看", "PASS")
        self.assessment_filter.addItem("信息待核验", "REVIEW")
        self.assessment_filter.addItem("明确冲突", "CONFLICT")
        self.stage_filter = QComboBox()
        self.stage_filter.addItem("全部阶段", "ALL")
        for value, label in STAGE_LABELS.items():
            self.stage_filter.addItem(label, value)
        self.candidate_search = QLineEdit()
        self.candidate_search.setPlaceholderText("搜索姓名、职位、技能或简历文本")
        refresh = QPushButton("筛选")
        refresh.clicked.connect(self.refresh_candidates)
        export = QPushButton("导出本岗位")
        export.clicked.connect(self.export_job)
        filters.addWidget(self.assessment_filter)
        filters.addWidget(self.stage_filter)
        filters.addWidget(self.candidate_search, 1)
        filters.addWidget(refresh)
        filters.addWidget(export)
        filter_layout.addLayout(filters)

        self.candidate_table = QTableWidget(0, 9)
        self.candidate_table.setHorizontalHeaderLabels(
            ("评估", "匹配度", "姓名", "当前/期望职位", "地点", "学历", "经验", "招聘阶段", "负责人")
        )
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.candidate_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.candidate_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.candidate_table.setAlternatingRowColors(True)
        self.candidate_table.verticalHeader().setVisible(False)
        header = self.candidate_table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for index in (0, 1, 2, 4, 5, 6, 7, 8):
            header.setSectionResizeMode(index, QHeaderView.ResizeToContents)
        self.candidate_table.doubleClicked.connect(self.review_candidate)
        filter_layout.addWidget(self.candidate_table, 1)
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
        filter_layout.addLayout(actions)
        layout.addWidget(filter_card, 1)
        self.assessment_filter.currentIndexChanged.connect(self.refresh_candidates)
        self.stage_filter.currentIndexChanged.connect(self.refresh_candidates)
        self.candidate_search.returnPressed.connect(self.refresh_candidates)
        return page

    def _build_automation_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(14)

        browser_card, browser_layout = _card(
            "受控浏览器中心",
            "浏览器与工作台使用独立窗口和同一登录 Profile。自动化过程中可随时暂停、人工接管或停止。",
        )
        status_grid = QGridLayout()
        self.browser_runtime_label = QLabel("运行状态：未检查")
        self.browser_mode_label = QLabel("浏览器：-")
        self.browser_profile_label = QLabel(f"登录数据：{browser_profile_dir()}")
        self.browser_url_label = QLabel("当前页面：-")
        for label in (self.browser_runtime_label, self.browser_mode_label, self.browser_profile_label, self.browser_url_label):
            label.setObjectName("Muted")
            label.setWordWrap(True)
        status_grid.addWidget(self.browser_runtime_label, 0, 0)
        status_grid.addWidget(self.browser_mode_label, 0, 1)
        status_grid.addWidget(self.browser_profile_label, 1, 0)
        status_grid.addWidget(self.browser_url_label, 1, 1)
        browser_layout.addLayout(status_grid)
        controls = QHBoxLayout()
        for text, handler, object_name in (
            ("显示浏览器", self.show_browser, ""),
            ("暂停", self.pause_task, ""),
            ("人工接管", self.take_over, ""),
            ("继续", self.resume_task, "SuccessButton"),
            ("停止任务", self.cancel_task, "DangerButton"),
            ("重置浏览器", self.reset_browser, ""),
        ):
            button = QPushButton(text)
            if object_name:
                button.setObjectName(object_name)
            button.clicked.connect(handler)
            controls.addWidget(button)
        controls.addStretch(1)
        status_button = QPushButton("重新检查")
        status_button.clicked.connect(self.check_browser_status)
        controls.addWidget(status_button)
        browser_layout.addLayout(controls)
        layout.addWidget(browser_card)

        run_card, run_layout = _card("搜索任务与异常", "失败任务会保留错误码、页面截图、HTML 和 Playwright Trace。")
        run_toolbar = QHBoxLayout()
        refresh = QPushButton("刷新任务")
        refresh.clicked.connect(self.refresh_runs)
        resume = QPushButton("从检查点恢复")
        resume.clicked.connect(self.resume_selected_run)
        diagnostics = QPushButton("打开诊断目录")
        diagnostics.clicked.connect(self.open_diagnostics)
        run_toolbar.addWidget(refresh)
        run_toolbar.addWidget(resume)
        run_toolbar.addWidget(diagnostics)
        run_toolbar.addStretch(1)
        run_layout.addLayout(run_toolbar)
        self.run_table = QTableWidget(0, 8)
        self.run_table.setHorizontalHeaderLabels(("任务", "状态", "搜索词", "发现", "新入池", "页码", "开始时间", "错误/诊断"))
        self.run_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.run_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.run_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.run_table.verticalHeader().setVisible(False)
        run_header = self.run_table.horizontalHeader()
        run_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        run_header.setSectionResizeMode(7, QHeaderView.Stretch)
        run_layout.addWidget(self.run_table, 1)
        self.run_log = QTextEdit()
        self.run_log.setReadOnly(True)
        self.run_log.setMaximumHeight(150)
        self.run_log.setPlaceholderText("任务日志将在这里显示")
        run_layout.addWidget(self.run_log)
        layout.addWidget(run_card, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        scroll, _container, content = self._page_scroll()
        browser_card, browser_layout = _card(
            "浏览器与自动化",
            "工作台 Chromium 是默认受支持运行时；Edge 和 Chrome 作为备用。其他浏览器不在 V0.9 支持范围内。",
        )
        form = QFormLayout()
        self.settings_browser_mode = QComboBox()
        for value in ("managed", "edge", "chrome", "auto", "custom"):
            self.settings_browser_mode.addItem(BROWSER_MODE_LABELS[value], value)
        self.custom_browser_path = QLineEdit()
        self.custom_browser_path.setPlaceholderText("仅高级场景使用，例如 C:\\Browser\\chrome.exe")
        browse = QPushButton("选择文件")
        browse.clicked.connect(self.choose_custom_browser)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.custom_browser_path, 1)
        custom_row.addWidget(browse)
        self.slow_mo_spin = QSpinBox()
        self.slow_mo_spin.setRange(0, 2000)
        self.slow_mo_spin.setSuffix(" ms")
        self.settings_visible = QCheckBox("默认显示浏览器")
        self.settings_sidecar = QCheckBox("默认左右分屏")
        form.addRow("默认浏览器", self.settings_browser_mode)
        form.addRow("自定义路径", custom_row)
        form.addRow("演示减速", self.slow_mo_spin)
        form.addRow("可视化", self.settings_visible)
        form.addRow("窗口布局", self.settings_sidecar)
        browser_layout.addLayout(form)
        settings_actions = QHBoxLayout()
        save = QPushButton("保存浏览器设置")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self.save_settings)
        clear_profile = QPushButton("清除智联登录状态")
        clear_profile.setObjectName("DangerButton")
        clear_profile.clicked.connect(self.clear_browser_profile)
        settings_actions.addWidget(save)
        settings_actions.addWidget(clear_profile)
        settings_actions.addStretch(1)
        browser_layout.addLayout(settings_actions)
        content.addWidget(browser_card)

        data_card, data_layout = _card(
            "本地数据与备份",
            "候选人数据、浏览器登录状态和诊断文件均保存在当前 Windows 用户目录，不随源码上传。",
        )
        self.data_path_label = QLabel(str(default_data_dir()))
        self.data_path_label.setObjectName("Muted")
        self.data_path_label.setWordWrap(True)
        data_layout.addWidget(self.data_path_label)
        data_actions = QHBoxLayout()
        open_data = QPushButton("打开数据目录")
        open_data.clicked.connect(self.open_data_dir)
        backup = QPushButton("备份数据库")
        backup.clicked.connect(self.backup_database)
        restore = QPushButton("恢复数据库")
        restore.clicked.connect(self.restore_database)
        open_diag = QPushButton("打开诊断目录")
        open_diag.clicked.connect(self.open_diagnostics)
        for button in (open_data, backup, restore, open_diag):
            data_actions.addWidget(button)
        data_actions.addStretch(1)
        data_layout.addLayout(data_actions)
        content.addWidget(data_card)

        support_card, support_layout = _card(
            "交付状态",
            "当前版本为产品化 Alpha。真实智联账号连续运行、平台规则、安装签名、升级回滚仍需现场验收。",
        )
        self.runtime_detail = QLabel(json.dumps(runtime_summary(self.settings), ensure_ascii=False, indent=2))
        self.runtime_detail.setObjectName("Muted")
        self.runtime_detail.setWordWrap(True)
        support_layout.addWidget(self.runtime_detail)
        content.addWidget(support_card)
        content.addStretch(1)
        return scroll

    # ------------------------------------------------------------------
    # Navigation and state
    # ------------------------------------------------------------------
    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for position, button in enumerate(self.nav_buttons):
            button.setChecked(position == index)
        titles = (
            ("岗位工作台", "创建岗位、确认标准，再启动受控搜索"),
            ("候选人收件箱", "按证据复核候选人并记录跟进动作"),
            ("自动化任务", "观察浏览器、暂停、接管、恢复和诊断"),
            ("系统与数据", "管理浏览器运行时、本地数据和备份"),
        )
        self.page_title.setText(titles[index][0])
        self.page_subtitle.setText(titles[index][1])
        if index == 1:
            self.refresh_candidates()
        elif index == 2:
            self.refresh_runs()

    def _browser_config(self) -> dict[str, Any]:
        bounds: dict[str, int] = {}
        if self.settings.sidecar_enabled:
            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                left_width = int(area.width() * 0.56)
                bounds = {
                    "x": area.x() + left_width,
                    "y": area.y(),
                    "width": area.width() - left_width,
                    "height": area.height(),
                }
        return {
            "browser_mode": self.settings.browser_mode,
            "custom_browser_path": self.settings.custom_browser_path,
            "browser_visible": self.settings.browser_visible,
            "slow_mo_ms": self.settings.slow_mo_ms,
            "window_bounds": bounds,
        }

    def _arrange_sidecar(self) -> None:
        if not self.sidecar_check.isChecked():
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = int(area.width() * 0.56)
        self.setGeometry(area.x(), area.y(), width, area.height())

    def _update_stepper(self, step: int) -> None:
        for index, (number, label) in enumerate(self.step_widgets):
            if index < step:
                number.setObjectName("StepDone")
                number.setText("✓")
                label.setObjectName("StepTextIdle")
            elif index == step:
                number.setObjectName("StepActive")
                number.setText(str(index + 1))
                label.setObjectName("StepTextActive")
            else:
                number.setObjectName("StepIdle")
                number.setText(str(index + 1))
                label.setObjectName("StepTextIdle")
            number.style().unpolish(number)
            number.style().polish(number)
            label.style().unpolish(label)
            label.style().polish(label)

    def _set_job_controls_enabled(self, enabled: bool) -> None:
        for widget in self._job_controls:
            widget.setEnabled(enabled)
        self.empty_card.setVisible(not enabled)
        self.profile_card.setVisible(enabled)
        self.search_card.setVisible(enabled)

    def _mark_profile_dirty(self) -> None:
        if self._loading_job or not self.current_job_id:
            return
        self._profile_dirty = True
        self.profile_state_chip.setText("岗位标准：有未保存修改")
        self.confirm_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self._update_stepper(1)

    def _profile_text_changed(self) -> None:
        self._mark_profile_dirty()

    # ------------------------------------------------------------------
    # Jobs and profiles
    # ------------------------------------------------------------------
    def new_job(self) -> None:
        dialog = NewJobDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        values = dialog.values()
        try:
            job_id = self.db.create_job(values["title"], values["keyword"], values["jd"])
            self.service.parse_and_save_job(job_id, **values)
        except Exception as error:
            QMessageBox.critical(self, "创建失败", str(error))
            return
        self.refresh_jobs(job_id)

    def refresh_jobs(self, select_id: int | None = None) -> None:
        selected = select_id or self.current_job_id
        self.job_list.blockSignals(True)
        self.job_list.clear()
        jobs = self.db.list_jobs()
        for job in jobs:
            suffix = f"  ·  {job['candidate_count']}人"
            item = QListWidgetItem(f"{job['title']}{suffix}")
            item.setData(Qt.UserRole, int(job["id"]))
            item.setToolTip(f"画像：{job.get('profile_status','DRAFT')} · 任务：{job.get('run_count',0)}")
            self.job_list.addItem(item)
            if selected and int(job["id"]) == int(selected):
                self.job_list.setCurrentItem(item)
        self.job_list.blockSignals(False)
        if self.job_list.count() == 0:
            self.current_job_id = None
            self._set_job_controls_enabled(False)
            self.global_status.setText("尚未创建岗位")
            self._update_stepper(0)
        elif self.job_list.currentItem() is None:
            self.job_list.setCurrentRow(0)
            self.load_job(int(self.job_list.currentItem().data(Qt.UserRole)))
        else:
            self.load_job(int(self.job_list.currentItem().data(Qt.UserRole)))

    def _job_item_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is not None:
            self.load_job(int(current.data(Qt.UserRole)))

    def load_job(self, job_id: int) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        self._loading_job = True
        try:
            self.current_job_id = job_id
            self.title_edit.setText(str(job.get("title") or ""))
            self.keyword_edit.setText(str(job.get("keyword") or ""))
            self.jd_edit.setPlainText(str(job.get("jd") or ""))
            profile = self.service.load_profile(job_id)
            index = self.education_combo.findText(profile.min_education or "不限")
            self.education_combo.setCurrentIndex(max(0, index))
            self.experience_spin.setValue(int(profile.min_experience_years or 0))
            self.location_edit.setText("、".join(profile.locations))
            self.profile_summary.setText(requirement_summary(profile))
            confirmed = job.get("profile_status") == ProfileStatus.CONFIRMED.value
            version = int(job.get("profile_version") or 0)
            self.profile_state_chip.setText(
                f"岗位标准：已确认 V{version}" if confirmed else "岗位标准：草稿，等待确认"
            )
            self.start_button.setEnabled(confirmed)
            self.confirm_button.setEnabled(not confirmed)
            self.global_status.setText(f"当前岗位：{job['title']}")
            self._profile_dirty = False
            self._set_job_controls_enabled(True)
            self._update_stepper(2 if confirmed else 1)
            self.refresh_candidates()
            self.refresh_runs()
            self.refresh_stats()
        finally:
            self._loading_job = False

    def parse_profile(self) -> bool:
        if not self.current_job_id:
            QMessageBox.information(self, "提示", "请先创建岗位。")
            return False
        try:
            profile = self.service.parse_and_save_job(
                self.current_job_id,
                title=self.title_edit.text(),
                keyword=self.keyword_edit.text(),
                jd=self.jd_edit.toPlainText(),
                min_education=self.education_combo.currentText(),
                min_experience_years=self.experience_spin.value(),
                locations=self.location_edit.text(),
            )
        except Exception as error:
            QMessageBox.critical(self, "解析失败", str(error))
            return False
        self.profile_summary.setText(requirement_summary(profile))
        self.profile_state_chip.setText("岗位标准：草稿，等待确认")
        self._profile_dirty = False
        self.confirm_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self._update_stepper(1)
        self.refresh_jobs(self.current_job_id)
        return True

    def confirm_profile(self) -> None:
        if not self.current_job_id:
            return
        if self._profile_dirty and not self.parse_profile():
            return
        answer = QMessageBox.question(
            self,
            "确认岗位标准",
            "确认后，当前岗位画像将用于候选人搜索与评估。后续修改会重新变为草稿。是否确认？",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            version = self.service.confirm_job_profile(self.current_job_id)
        except Exception as error:
            QMessageBox.critical(self, "确认失败", str(error))
            return
        self.profile_state_chip.setText(f"岗位标准：已确认 V{version}")
        self.confirm_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self._update_stepper(2)
        self.refresh_jobs(self.current_job_id)

    def archive_job(self) -> None:
        if not self.current_job_id:
            return
        if QMessageBox.question(self, "归档岗位", "确认归档当前岗位？候选人主数据不会删除。") != QMessageBox.Yes:
            return
        self.db.update_job(self.current_job_id, status=JobStatus.ARCHIVED)
        self.current_job_id = None
        self.refresh_jobs()

    def reassess(self) -> None:
        if not self.current_job_id:
            return
        try:
            summary = self.service.reassess_job(self.current_job_id)
        except Exception as error:
            QMessageBox.critical(self, "重新评估失败", str(error))
            return
        self._log(f"重新评估完成：优先 {summary.pass_count}，待核验 {summary.review_count}，冲突 {summary.conflict_count}")
        self.refresh_candidates()
        self.refresh_stats()

    # ------------------------------------------------------------------
    # Sourcing and browser controls
    # ------------------------------------------------------------------
    def _current_search_plan(self) -> SearchPlan:
        query = self.keyword_edit.text().strip() or self.title_edit.text().strip()
        return SearchPlan(
            query=query,
            max_pages=self.max_pages_spin.value(),
            max_count=self.max_count_spin.value(),
            browser_mode=str(self.browser_mode_combo.currentData() or "managed"),
            visible=self.visible_check.isChecked(),
            sidecar=self.sidecar_check.isChecked(),
        ).normalized()

    def start_search(self) -> None:
        if not self.current_job_id:
            return
        if self._profile_dirty:
            QMessageBox.warning(self, "岗位标准未确认", "岗位信息有未保存修改。请重新解析并确认岗位标准。")
            return
        plan = self._current_search_plan()
        try:
            run_id = self.service.create_sourcing_run(self.current_job_id, plan)
        except Exception as error:
            QMessageBox.warning(self, "不能开始搜索", str(error))
            return
        self._submit_search(self.current_job_id, run_id, plan)

    def _submit_search(self, job_id: int, run_id: int, plan: SearchPlan, start_page: int = 1) -> None:
        self._arrange_sidecar()
        config = self._browser_config()
        config.update({"browser_mode": plan.browser_mode, "browser_visible": plan.visible})
        self.worker.submit("CONFIGURE_BROWSER", config)
        request_id = self.worker.submit(
            "SEARCH",
            {
                "job_id": job_id,
                "run_id": run_id,
                "query": plan.query,
                "max_pages": plan.max_pages,
                "max_count": plan.max_count,
                "start_page": start_page,
            },
        )
        self.pending[request_id] = {
            "job_id": job_id,
            "run_id": run_id,
            "plan": plan,
            "start_page": start_page,
        }
        self.active_run_id = run_id
        self.start_button.setEnabled(False)
        self.login_button.setEnabled(False)
        self.progress.setValue(5)
        self.task_status.setText("正在启动受控浏览器…")
        self._select_page(2)
        self.refresh_runs()

    def continue_after_login(self) -> None:
        if not self.waiting_login:
            return
        context = self.waiting_login
        self.waiting_login = None
        self.login_button.setEnabled(False)
        self.db.update_sourcing_run(context["run_id"], status=RunStatus.RUNNING)
        self._submit_search(context["job_id"], context["run_id"], context["plan"], context.get("start_page", 1))

    def import_demo(self) -> None:
        if not self.current_job_id:
            return
        try:
            self.service.assert_job_ready(self.current_job_id)
            plan = SearchPlan(query="DEMO", max_pages=1, max_count=20, browser_mode="managed")
            run_id = self.service.create_sourcing_run(self.current_job_id, plan)
            summary = self.service.ingest_candidates(
                job_id=self.current_job_id,
                run_id=run_id,
                candidates=demo_candidates(),
            )
            self.db.update_sourcing_run(
                run_id,
                status=RunStatus.SUCCEEDED,
                found_count=summary.found,
                new_count=summary.new_job_links,
            )
        except Exception as error:
            QMessageBox.critical(self, "导入失败", str(error))
            return
        self._log(f"演示数据已导入：发现 {summary.found} 人，待核验 {summary.review_count} 人")
        self.refresh_jobs(self.current_job_id)
        self._select_page(1)

    def pause_task(self) -> None:
        if self.active_run_id:
            self.worker.submit("PAUSE")

    def resume_task(self) -> None:
        if self.active_run_id:
            self.worker.submit("RESUME")

    def take_over(self) -> None:
        if self.active_run_id:
            self.worker.submit("TAKE_OVER")
        else:
            self.show_browser()

    def cancel_task(self) -> None:
        if not self.active_run_id:
            return
        if QMessageBox.question(self, "停止任务", "系统将在当前安全检查点停止本次任务。是否继续？") == QMessageBox.Yes:
            self.worker.submit("CANCEL")

    def show_browser(self) -> None:
        self.worker.submit("BRING_TO_FRONT")

    def reset_browser(self) -> None:
        self.worker.submit("RESET_BROWSER")

    def check_browser_status(self) -> None:
        self.worker.submit("GET_BROWSER_STATUS")

    def resume_selected_run(self) -> None:
        row = self.run_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一条未完成任务。")
            return
        run_id = int(self.run_table.item(row, 0).data(Qt.UserRole))
        run = self.db.get_sourcing_run(run_id)
        if not run:
            return
        if run["status"] not in {
            RunStatus.RUNNING.value,
            RunStatus.NEED_LOGIN.value,
            RunStatus.PAUSED.value,
            RunStatus.TAKEOVER.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            QMessageBox.information(self, "无需恢复", "该任务已经成功完成。")
            return
        if self.active_run_id:
            QMessageBox.warning(self, "已有任务", "请先停止当前运行中的任务。")
            return
        plan = SearchPlan(
            query=str(run["query"]),
            max_pages=int(run.get("max_pages") or 5),
            max_count=int(run.get("max_count") or 200),
            browser_mode=str(run.get("browser_mode") or self.settings.browser_mode),
            visible=True,
            sidecar=self.settings.sidecar_enabled,
        )
        start_page = min(plan.max_pages, max(1, int(run.get("last_page") or 0) + 1))
        self.db.update_sourcing_run(run_id, status=RunStatus.RUNNING)
        self._submit_search(int(run["job_id"]), run_id, plan, start_page=start_page)

    # ------------------------------------------------------------------
    # Browser events
    # ------------------------------------------------------------------
    def _poll_browser_events(self) -> None:
        while True:
            try:
                self._handle_browser_event(self.browser_events.get_nowait())
            except queue.Empty:
                break

    def _handle_browser_event(self, event: BrowserEvent) -> None:
        payload = event.payload
        context = self.pending.get(event.request_id, {})
        run_id = int(payload.get("run_id") or context.get("run_id") or 0)

        if event.event in {"STATUS", "PROGRESS"}:
            self.task_status.setText(str(payload.get("message") or "任务运行中"))
            self.progress.setValue(int(payload.get("progress") or 0))
            self._log(str(payload.get("message") or event.event))
            return
        if event.event == "CHECKPOINT":
            if run_id:
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.RUNNING,
                    found_count=int(payload.get("count") or 0),
                    last_page=int(payload.get("page_no") or 0),
                    checkpoint=payload.get("checkpoint") or {},
                )
                self.refresh_runs()
            return
        if event.event == "BROWSER_STATUS":
            running = bool(payload.get("running"))
            mode = str(payload.get("mode") or "-")
            version = str(payload.get("version") or "")
            self.browser_runtime_label.setText("运行状态：已连接" if running else "运行状态：未启动")
            self.browser_mode_label.setText(f"浏览器：{BROWSER_MODE_LABELS.get(mode, mode)} {version}".strip())
            self.browser_profile_label.setText(f"登录数据：{payload.get('profile_dir') or '-'}")
            self.browser_url_label.setText(f"当前页面：{payload.get('current_url') or '-'}")
            self.sidebar_browser.setText(f"浏览器：{BROWSER_MODE_LABELS.get(mode, mode)} · {'运行中' if running else '未启动'}")
            return
        if event.event == "NEED_LOGIN":
            if run_id:
                self.db.update_sourcing_run(run_id, status=RunStatus.NEED_LOGIN)
            old = self.pending.pop(event.request_id, context)
            self.waiting_login = {
                "job_id": old.get("job_id", self.current_job_id),
                "run_id": run_id,
                "plan": old.get("plan", self._current_search_plan()),
                "start_page": old.get("start_page", 1),
            }
            self.login_button.setEnabled(True)
            self.start_button.setEnabled(True)
            self.task_status.setText(str(payload.get("message") or "等待登录"))
            self.global_status.setText("等待完成智联登录")
            self._select_page(0)
            self.refresh_runs()
            return
        if event.event in {"PAUSED", "TAKEOVER_READY"}:
            status = RunStatus.TAKEOVER if event.event == "TAKEOVER_READY" else RunStatus.PAUSED
            if run_id:
                self.db.update_sourcing_run(run_id, status=status)
            self.task_status.setText(str(payload.get("message") or "任务已暂停"))
            self.global_status.setText("人工接管" if status == RunStatus.TAKEOVER else "任务已暂停")
            self.refresh_runs()
            return
        if event.event == "RESUMED":
            if run_id:
                self.db.update_sourcing_run(run_id, status=RunStatus.RUNNING)
            self.global_status.setText("任务运行中")
            self.refresh_runs()
            return
        if event.event == "COMPLETED":
            try:
                summary = self.service.ingest_candidates(
                    job_id=int(context["job_id"]),
                    run_id=run_id,
                    candidates=payload.get("candidates") or [],
                )
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.SUCCEEDED,
                    found_count=summary.found,
                    new_count=summary.new_job_links,
                )
                self.task_status.setText(f"完成：发现 {summary.found} 人，新入池 {summary.new_job_links} 人")
                self.progress.setValue(100)
                self.global_status.setText("搜索完成")
            except Exception as error:
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.FAILED,
                    error_code="INGEST_FAILED",
                    error_message=str(error),
                )
                QMessageBox.critical(self, "入库失败", str(error))
            self._finish_active_request(event.request_id)
            self.refresh_jobs(context.get("job_id"))
            self._select_page(1)
            return
        if event.event == "CANCELLED":
            if run_id:
                self.db.update_sourcing_run(run_id, status=RunStatus.CANCELLED)
            self.task_status.setText("任务已停止，可从任务页重新开始或恢复")
            self.progress.setValue(0)
            self.global_status.setText("任务已停止")
            self._finish_active_request(event.request_id)
            self.refresh_runs()
            return
        if event.event == "FAILED":
            if run_id:
                self.db.update_sourcing_run(
                    run_id,
                    status=RunStatus.FAILED,
                    error_code=str(payload.get("error_code") or "UNKNOWN"),
                    error_message=str(payload.get("error") or "未知错误"),
                    diagnostic_dir=str(payload.get("diagnostic_dir") or ""),
                )
            self.task_status.setText(f"任务未完成：{payload.get('error_code') or 'UNKNOWN'}")
            self.progress.setValue(0)
            self.global_status.setText("任务未完成，已保存诊断")
            self._log(f"失败：{payload.get('error_code')} {payload.get('error')}")
            self._finish_active_request(event.request_id)
            self.refresh_runs()
            return
        if event.event in {
            "BROWSER_RESET", "BROWSER_SHOWN", "URL_OPENED", "BROWSER_CONFIGURED",
            "BROWSER_PROFILE_CLEARED", "LOGIN_CHECKED", "CONTROL_ACCEPTED",
        }:
            message = str(payload.get("message") or event.event)
            self._log(message)
            if event.event in {"BROWSER_RESET", "BROWSER_PROFILE_CLEARED"}:
                self.sidebar_browser.setText("浏览器：未启动")
            return

    def _finish_active_request(self, request_id: str) -> None:
        self.pending.pop(request_id, None)
        self.active_run_id = None
        job = self.db.get_job(self.current_job_id) if self.current_job_id else None
        self.start_button.setEnabled(bool(job and job.get("profile_status") == ProfileStatus.CONFIRMED.value))
        self.login_button.setEnabled(False)

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------
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
        for row_data in rows:
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
                STAGE_LABELS.get(row_data.get("stage"), row_data.get("stage", "")),
                row_data.get("owner", ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if column == 0:
                    item.setData(Qt.UserRole, int(row_data["job_candidate_id"]))
                self.candidate_table.setItem(row, column, item)
        self.refresh_stats()

    def _selected_candidate_id(self) -> int | None:
        row = self.candidate_table.currentRow()
        if row < 0 or self.candidate_table.item(row, 0) is None:
            return None
        return int(self.candidate_table.item(row, 0).data(Qt.UserRole))

    def quick_stage(self, stage: CandidateStage) -> None:
        candidate_id = self._selected_candidate_id()
        if not candidate_id:
            return
        self.db.update_job_candidate(candidate_id, stage=stage)
        self.db.add_follow_up(candidate_id, "STAGE_CHANGED", STAGE_LABELS[stage.value])
        self.refresh_candidates()

    def review_candidate(self) -> None:
        candidate_id = self._selected_candidate_id()
        candidate = self.db.get_job_candidate(candidate_id) if candidate_id else None
        if not candidate:
            QMessageBox.information(self, "提示", "请先选择候选人。")
            return
        dialog = CandidateReviewDialog(candidate, self)
        if dialog.exec() != dialog.Accepted:
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

    def export_job(self) -> None:
        if not self.current_job_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出本岗位", "", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            count = self.db.export_job_csv(self.current_job_id, path)
        except Exception as error:
            QMessageBox.critical(self, "导出失败", str(error))
            return
        QMessageBox.information(self, "导出完成", f"已导出 {count} 名候选人。")

    def refresh_stats(self) -> None:
        if not self.current_job_id:
            return
        stats = self.db.job_stats(self.current_job_id)
        assessments = stats.get("assessments") or {}
        self.job_total_metric.set_value(stats.get("total", 0))
        self.job_pass_metric.set_value(assessments.get("PASS", 0))
        self.job_review_metric.set_value(assessments.get("REVIEW", 0) + assessments.get("UNASSESSED", 0))
        self.job_conflict_metric.set_value(assessments.get("CONFLICT", 0))
        self.candidate_metrics["total"].set_value(stats.get("total", 0))
        self.candidate_metrics["PASS"].set_value(assessments.get("PASS", 0))
        self.candidate_metrics["REVIEW"].set_value(assessments.get("REVIEW", 0) + assessments.get("UNASSESSED", 0))
        self.candidate_metrics["CONFLICT"].set_value(assessments.get("CONFLICT", 0))

    # ------------------------------------------------------------------
    # Runs, settings and data
    # ------------------------------------------------------------------
    def refresh_runs(self) -> None:
        self.run_table.setRowCount(0)
        if not self.current_job_id:
            return
        for run in self.db.list_sourcing_runs(self.current_job_id):
            row = self.run_table.rowCount()
            self.run_table.insertRow(row)
            error = run.get("error_code") or ""
            if run.get("diagnostic_dir"):
                error = f"{error} · {run['diagnostic_dir']}".strip(" ·")
            values = (
                run["id"],
                RUN_LABELS.get(run["status"], run["status"]),
                run["query"],
                run["found_count"],
                run["new_count"],
                run.get("last_page") or 0,
                run.get("started_at") or run.get("created_at") or "",
                error,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, int(run["id"]))
                self.run_table.setItem(row, column, item)

    def _apply_settings_to_controls(self) -> None:
        self.max_pages_spin.setValue(self.settings.default_max_pages)
        self.max_count_spin.setValue(self.settings.default_max_count)
        self.visible_check.setChecked(self.settings.browser_visible)
        self.sidecar_check.setChecked(self.settings.sidecar_enabled)
        for combo in (self.browser_mode_combo, self.settings_browser_mode):
            index = combo.findData(self.settings.browser_mode)
            combo.setCurrentIndex(max(0, index))
        self.custom_browser_path.setText(self.settings.custom_browser_path)
        self.slow_mo_spin.setValue(self.settings.slow_mo_ms)
        self.settings_visible.setChecked(self.settings.browser_visible)
        self.settings_sidecar.setChecked(self.settings.sidecar_enabled)
        self.runtime_detail.setText(json.dumps(runtime_summary(self.settings), ensure_ascii=False, indent=2))

    def choose_custom_browser(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 Chromium 浏览器", "", "可执行文件 (*.exe);;所有文件 (*)")
        if path:
            self.custom_browser_path.setText(path)
            index = self.settings_browser_mode.findData("custom")
            self.settings_browser_mode.setCurrentIndex(index)

    def save_settings(self) -> None:
        self.settings = AppSettings(
            browser_mode=str(self.settings_browser_mode.currentData() or "managed"),
            custom_browser_path=self.custom_browser_path.text(),
            browser_visible=self.settings_visible.isChecked(),
            sidecar_enabled=self.settings_sidecar.isChecked(),
            slow_mo_ms=self.slow_mo_spin.value(),
            default_max_pages=self.max_pages_spin.value(),
            default_max_count=self.max_count_spin.value(),
            data_retention_days=self.settings.data_retention_days,
        ).normalized()
        save_settings(self.settings)
        self._apply_settings_to_controls()
        self.worker.submit("CONFIGURE_BROWSER", self._browser_config())
        QMessageBox.information(self, "设置已保存", "浏览器设置已保存。正在运行的任务不会被强制中断。")

    def clear_browser_profile(self) -> None:
        if QMessageBox.question(
            self,
            "清除登录状态",
            "这会关闭受控浏览器并删除智联 Cookie、本地缓存和登录状态。是否继续？",
        ) == QMessageBox.Yes:
            self.worker.submit("CLEAR_BROWSER_PROFILE")

    def backup_database(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "备份数据库", "RecruitmentWorkbench-backup.db", "数据库文件 (*.db)")
        if not path:
            return
        try:
            self.db.backup_to(path)
        except Exception as error:
            QMessageBox.critical(self, "备份失败", str(error))
            return
        QMessageBox.information(self, "备份完成", path)

    def restore_database(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "恢复数据库", "", "数据库文件 (*.db)")
        if not path:
            return
        if QMessageBox.question(self, "恢复数据库", "当前数据将被备份文件替换。是否继续？") != QMessageBox.Yes:
            return
        try:
            self.db.restore_from(path)
        except Exception as error:
            QMessageBox.critical(self, "恢复失败", str(error))
            return
        self.current_job_id = None
        self.refresh_jobs()
        QMessageBox.information(self, "恢复完成", "数据库已恢复并重新加载。")

    def open_data_dir(self) -> None:
        default_data_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(default_data_dir())))

    def open_diagnostics(self) -> None:
        selected_path = ""
        row = self.run_table.currentRow()
        if row >= 0 and self.run_table.item(row, 0):
            run_id = int(self.run_table.item(row, 0).data(Qt.UserRole))
            run = self.db.get_sourcing_run(run_id)
            selected_path = str(run.get("diagnostic_dir") or "") if run else ""
        path = Path(selected_path) if selected_path else default_data_dir() / "diagnostics"
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _show_recovery_notice(self) -> None:
        incomplete = self.db.list_incomplete_runs(limit=10)
        if not incomplete:
            return
        latest = incomplete[0]
        self.global_status.setText(f"发现未完成任务：{latest['job_title']}")
        self._log(
            f"上次任务 #{latest['id']} 未完成，已到第 {latest.get('last_page') or 0} 页。"
            "可在“自动化任务”中选择并从检查点恢复。"
        )

    def _log(self, message: str) -> None:
        if not message:
            return
        self.run_log.append(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.worker.shutdown()
        event.accept()
