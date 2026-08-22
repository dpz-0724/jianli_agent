# -*- coding: utf-8 -*-
"""Focused Qt dialogs used by the productized desktop workbench."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .models import CandidateStage

STAGE_LABELS = {
    CandidateStage.NEW.value: "新入池",
    CandidateStage.TO_REVIEW.value: "待复核",
    CandidateStage.TO_CONTACT.value: "待联系",
    CandidateStage.CONTACTED.value: "已联系",
    CandidateStage.INTERVIEW.value: "面试中",
    CandidateStage.OFFER.value: "Offer",
    CandidateStage.HIRED.value: "已录用",
    CandidateStage.REJECTED.value: "不合适",
    CandidateStage.TALENT_POOL.value: "人才库",
}


class NewJobDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建招聘岗位")
        self.resize(680, 520)
        layout = QVBoxLayout(self)
        title = QLabel("创建招聘岗位")
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        hint = QLabel("先录入基础信息。系统会生成岗位画像草稿，确认后才能开始搜索。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(12)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例如：高级 Java 后端工程师")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("例如：Java Spring 微服务")
        self.jd_edit = QTextEdit()
        self.jd_edit.setPlaceholderText("粘贴完整岗位职责、任职要求和加分项")
        form.addRow("岗位名称", self.title_edit)
        form.addRow("搜索关键词", self.keyword_edit)
        form.addRow("岗位 JD", self.jd_edit)
        layout.addLayout(form, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("创建并解析")
        buttons.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.title_edit.text().strip():
            self.title_edit.setFocus()
            return
        self.accept()

    def values(self) -> dict[str, str]:
        return {
            "title": self.title_edit.text().strip(),
            "keyword": self.keyword_edit.text().strip(),
            "jd": self.jd_edit.toPlainText().strip(),
        }


class CandidateReviewDialog(QDialog):
    def __init__(self, candidate: dict[str, Any], parent=None):
        super().__init__(parent)
        self.candidate = candidate
        self.open_source_requested = False
        self.setWindowTitle(f"候选人复核 · {candidate.get('name') or '未命名'}")
        self.resize(880, 720)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        heading = QLabel(
            f"{candidate.get('name','')}  ·  {candidate.get('title','')}\n"
            f"{candidate.get('location','') or '地点未知'} / "
            f"{candidate.get('education','') or '学历未知'} / "
            f"{candidate.get('experience','') or '经验未知'}"
        )
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)

        assessment = candidate.get("assessment_status") or "REVIEW"
        score = candidate.get("fit_score")
        assessment_label = {"PASS": "建议优先查看", "REVIEW": "信息待核验", "CONFLICT": "存在明确冲突"}.get(
            assessment, assessment
        )
        badge = QLabel(f"评估：{assessment_label}    匹配度：{'-' if score is None else f'{float(score):.1f}'}")
        badge.setObjectName("StatusChip")
        layout.addWidget(badge, alignment=badge.alignment())

        reasons = candidate.get("reasons") or ["暂无评估依据"]
        reason_text = "\n".join(f"• {item}" for item in reasons)
        reason_label = QLabel(reason_text)
        reason_label.setWordWrap(True)
        reason_label.setObjectName("Muted")
        layout.addWidget(reason_label)

        form = QFormLayout()
        self.stage_combo = QComboBox()
        for value, label in STAGE_LABELS.items():
            self.stage_combo.addItem(label, value)
        current_stage = str(candidate.get("stage") or CandidateStage.TO_REVIEW.value)
        index = self.stage_combo.findData(current_stage)
        self.stage_combo.setCurrentIndex(max(0, index))

        self.owner_edit = QLineEdit(str(candidate.get("owner") or ""))
        self.note_edit = QTextEdit()
        self.note_edit.setPlainText(str(candidate.get("note") or ""))
        self.note_edit.setMinimumHeight(130)
        self.follow_up_edit = QDateTimeEdit()
        self.follow_up_edit.setCalendarPopup(True)
        self.follow_up_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.follow_up_edit.setSpecialValueText("未设置")
        self.follow_up_edit.setMinimumDateTime(QDateTime.fromSecsSinceEpoch(0))
        existing_follow_up = str(candidate.get("next_follow_up_at") or "")
        if existing_follow_up:
            parsed = QDateTime.fromString(existing_follow_up[:16], "yyyy-MM-ddTHH:mm")
            if parsed.isValid():
                self.follow_up_edit.setDateTime(parsed)
            else:
                self.follow_up_edit.setDateTime(QDateTime.fromSecsSinceEpoch(0))
        else:
            self.follow_up_edit.setDateTime(QDateTime.fromSecsSinceEpoch(0))

        self.decision_combo = QComboBox()
        self.decision_combo.addItem("不新增复核结论", "")
        self.decision_combo.addItem("确认进入下一步", "ADVANCE")
        self.decision_combo.addItem("保留待复核", "KEEP_REVIEW")
        self.decision_combo.addItem("确认不合适", "REJECT")
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("有复核结论时建议填写理由")

        form.addRow("招聘阶段", self.stage_combo)
        form.addRow("负责人", self.owner_edit)
        form.addRow("下次跟进", self.follow_up_edit)
        form.addRow("备注", self.note_edit)
        form.addRow("人工复核结论", self.decision_combo)
        form.addRow("复核理由", self.reason_edit)
        layout.addLayout(form, 1)

        action_row = QHBoxLayout()
        self.source_button = QPushButton("在受控浏览器打开来源")
        self.source_button.setEnabled(bool(candidate.get("source_url")) and not str(candidate.get("source_url")).startswith("demo://"))
        self.source_button.clicked.connect(self._request_source)
        action_row.addWidget(self.source_button)
        action_row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.button(QDialogButtonBox.Save).setText("保存复核")
        buttons.button(QDialogButtonBox.Save).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        action_row.addWidget(buttons)
        layout.addLayout(action_row)

    def _request_source(self) -> None:
        self.open_source_requested = True
        self.accept()

    def values(self) -> dict[str, Any]:
        follow_up = ""
        if self.follow_up_edit.dateTime().toSecsSinceEpoch() > 0:
            follow_up = self.follow_up_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
        return {
            "stage": self.stage_combo.currentData(),
            "owner": self.owner_edit.text().strip(),
            "note": self.note_edit.toPlainText().strip(),
            "next_follow_up_at": follow_up,
            "decision": self.decision_combo.currentData(),
            "decision_reason": self.reason_edit.text().strip(),
        }
