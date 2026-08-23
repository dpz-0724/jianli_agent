# -*- coding: utf-8 -*-
"""Product-facing job creation dialog.

The first productized dialog silently ignored an empty title and gave users no visible
feedback. This version keeps the create action disabled until the minimum information is
present, shows validation errors inline, and captures structured recruitment conditions
before the JD parser runs.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)


class JobCreateDialog(QDialog):
    """Create a job draft with both free-form JD and structured conditions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建招聘岗位")
        self.setWindowModality(Qt.WindowModal)
        self.setModal(True)
        self.setMinimumSize(760, 680)
        self.resize(820, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        heading = QLabel("创建招聘岗位")
        heading.setObjectName("CardTitle")
        root.addWidget(heading)
        hint = QLabel(
            "先填写岗位和硬性条件，再粘贴完整 JD。系统会生成岗位画像草稿，"
            "由招聘人员确认后才允许开始招聘。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        root.addWidget(hint)

        basic_group = QGroupBox("基础信息")
        basic_form = QFormLayout(basic_group)
        basic_form.setContentsMargins(16, 18, 16, 16)
        basic_form.setSpacing(12)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("必填，例如：高级 Java 后端工程师")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("例如：Java Spring 微服务；用于智联搜索")
        basic_form.addRow("岗位名称 *", self.title_edit)
        basic_form.addRow("搜索关键词", self.keyword_edit)
        root.addWidget(basic_group)

        hard_group = QGroupBox("结构化招聘条件")
        hard_grid = QGridLayout(hard_group)
        hard_grid.setContentsMargins(16, 18, 16, 16)
        hard_grid.setHorizontalSpacing(14)
        hard_grid.setVerticalSpacing(12)

        self.education_combo = QComboBox()
        self.education_combo.addItems(("不限", "高中", "大专", "本科", "硕士", "博士"))
        self.experience_spin = QSpinBox()
        self.experience_spin.setRange(0, 30)
        self.experience_spin.setSuffix(" 年")
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText("多个地点用顿号或逗号分隔")
        self.required_skills_edit = QLineEdit()
        self.required_skills_edit.setPlaceholderText("必须能力，例如：Java、Spring Boot、MySQL")
        self.preferred_skills_edit = QLineEdit()
        self.preferred_skills_edit.setPlaceholderText("加分能力，例如：微服务、Kubernetes、金融行业")

        hard_grid.addWidget(QLabel("硬性：最低学历"), 0, 0)
        hard_grid.addWidget(self.education_combo, 0, 1)
        hard_grid.addWidget(QLabel("硬性：最低经验"), 0, 2)
        hard_grid.addWidget(self.experience_spin, 0, 3)
        hard_grid.addWidget(QLabel("工作地点"), 1, 0)
        hard_grid.addWidget(self.location_edit, 1, 1, 1, 3)
        hard_grid.addWidget(QLabel("必须能力"), 2, 0)
        hard_grid.addWidget(self.required_skills_edit, 2, 1, 1, 3)
        hard_grid.addWidget(QLabel("加分能力"), 3, 0)
        hard_grid.addWidget(self.preferred_skills_edit, 3, 1, 1, 3)
        hard_grid.setColumnStretch(1, 1)
        hard_grid.setColumnStretch(3, 1)
        root.addWidget(hard_group)

        jd_group = QGroupBox("岗位 JD")
        jd_layout = QVBoxLayout(jd_group)
        jd_layout.setContentsMargins(16, 18, 16, 16)
        self.jd_edit = QTextEdit()
        self.jd_edit.setMinimumHeight(180)
        self.jd_edit.setPlaceholderText("粘贴岗位职责、任职要求、优先项和其他说明")
        jd_layout.addWidget(self.jd_edit)
        root.addWidget(jd_group, 1)

        self.validation_label = QLabel("请先填写岗位名称")
        self.validation_label.setObjectName("ErrorText")
        self.validation_label.setStyleSheet("color:#D92D20; font-weight:600;")
        root.addWidget(self.validation_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.create_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.create_button.setText("创建岗位草稿")
        self.create_button.setObjectName("PrimaryButton")
        self.cancel_button.setText("取消")
        self.create_button.setEnabled(False)
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        button_row.addWidget(self.buttons)
        root.addLayout(button_row)

        self.title_edit.textChanged.connect(self._sync_validation)
        self.keyword_edit.textChanged.connect(self._sync_validation)
        QTimer.singleShot(0, self._prepare_window)

    def _prepare_window(self) -> None:
        self.raise_()
        self.activateWindow()
        self.title_edit.setFocus(Qt.OtherFocusReason)

    def _sync_validation(self) -> None:
        has_title = bool(self.title_edit.text().strip())
        self.create_button.setEnabled(has_title)
        self.validation_label.setText("" if has_title else "请先填写岗位名称")
        self.validation_label.setVisible(not has_title)

    def _validate_and_accept(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            self.validation_label.setText("岗位名称不能为空")
            self.validation_label.setVisible(True)
            self.title_edit.setFocus(Qt.OtherFocusReason)
            return
        if not self.keyword_edit.text().strip():
            self.keyword_edit.setText(title)
        self.accept()

    def values(self) -> dict[str, Any]:
        return {
            "title": self.title_edit.text().strip(),
            "keyword": self.keyword_edit.text().strip() or self.title_edit.text().strip(),
            "jd": self.jd_edit.toPlainText().strip(),
            "min_education": self.education_combo.currentText(),
            "min_experience_years": int(self.experience_spin.value()),
            "locations": self.location_edit.text().strip(),
            "required_skills": self.required_skills_edit.text().strip(),
            "preferred_skills": self.preferred_skills_edit.text().strip(),
        }
