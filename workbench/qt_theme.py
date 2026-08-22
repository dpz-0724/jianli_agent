# -*- coding: utf-8 -*-
"""Quiet enterprise visual system for the Qt desktop client."""
from __future__ import annotations

APP_STYLE = r"""
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #172033;
}
QMainWindow, QWidget#Root {
    background: #F4F6F9;
}
QWidget#Sidebar {
    background: #0F172A;
    border: none;
}
QLabel#BrandMark {
    background: #2F6BFF;
    color: white;
    border-radius: 10px;
    font-size: 20px;
    font-weight: 700;
}
QLabel#BrandTitle {
    color: white;
    font-size: 17px;
    font-weight: 700;
}
QLabel#BrandSubtitle, QLabel#SidebarHint {
    color: #94A3B8;
    font-size: 11px;
}
QPushButton#SidebarButton {
    color: #CBD5E1;
    background: transparent;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 10px 12px;
    font-weight: 600;
}
QPushButton#SidebarButton:hover {
    background: #1E293B;
    color: white;
}
QPushButton#SidebarButton:checked {
    background: #1E3A8A;
    color: white;
}
QListWidget#JobList {
    background: transparent;
    border: none;
    outline: none;
    color: #CBD5E1;
}
QListWidget#JobList::item {
    padding: 10px 10px;
    margin: 2px 0;
    border-radius: 7px;
}
QListWidget#JobList::item:hover {
    background: #1E293B;
}
QListWidget#JobList::item:selected {
    background: #243B69;
    color: white;
}
QFrame#TopBar {
    background: white;
    border-bottom: 1px solid #E5E7EB;
}
QLabel#PageTitle {
    font-size: 22px;
    font-weight: 700;
    color: #101828;
}
QLabel#PageSubtitle {
    color: #667085;
}
QLabel#StatusChip {
    background: #EEF4FF;
    color: #175CD3;
    border: 1px solid #C7D7FE;
    border-radius: 11px;
    padding: 4px 10px;
    font-weight: 600;
}
QFrame#Card {
    background: white;
    border: 1px solid #E4E7EC;
    border-radius: 12px;
}
QFrame#MetricCard {
    background: white;
    border: 1px solid #E4E7EC;
    border-radius: 10px;
}
QLabel#CardTitle {
    font-size: 16px;
    font-weight: 700;
    color: #101828;
}
QLabel#CardHint, QLabel#Muted {
    color: #667085;
}
QLabel#MetricValue {
    font-size: 26px;
    font-weight: 700;
    color: #101828;
}
QLabel#MetricLabel {
    color: #667085;
    font-size: 12px;
}
QLabel#StepActive {
    background: #2F6BFF;
    color: white;
    border-radius: 13px;
    min-width: 26px;
    min-height: 26px;
    max-width: 26px;
    max-height: 26px;
    font-weight: 700;
}
QLabel#StepDone {
    background: #E7F8F0;
    color: #087A55;
    border-radius: 13px;
    min-width: 26px;
    min-height: 26px;
    max-width: 26px;
    max-height: 26px;
    font-weight: 700;
}
QLabel#StepIdle {
    background: #EAECF0;
    color: #667085;
    border-radius: 13px;
    min-width: 26px;
    min-height: 26px;
    max-width: 26px;
    max-height: 26px;
    font-weight: 700;
}
QLabel#StepTextActive {
    color: #101828;
    font-weight: 700;
}
QLabel#StepTextIdle {
    color: #667085;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateTimeEdit {
    background: white;
    border: 1px solid #D0D5DD;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #2F6BFF;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {
    border: 1px solid #2F6BFF;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QPushButton {
    background: white;
    color: #344054;
    border: 1px solid #D0D5DD;
    border-radius: 7px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #F9FAFB;
    border-color: #98A2B3;
}
QPushButton:disabled {
    background: #F2F4F7;
    color: #98A2B3;
    border-color: #E4E7EC;
}
QPushButton#PrimaryButton {
    background: #2F6BFF;
    color: white;
    border: 1px solid #2F6BFF;
}
QPushButton#PrimaryButton:hover {
    background: #2459D6;
}
QPushButton#DangerButton {
    color: #B42318;
    border-color: #FDA29B;
    background: #FFF5F4;
}
QPushButton#SuccessButton {
    color: #067647;
    border-color: #ABEFC6;
    background: #ECFDF3;
}
QTableWidget, QTableView {
    background: white;
    alternate-background-color: #F9FAFB;
    border: 1px solid #E4E7EC;
    border-radius: 8px;
    gridline-color: #EAECF0;
    selection-background-color: #EAF0FF;
    selection-color: #101828;
}
QHeaderView::section {
    background: #F8FAFC;
    color: #475467;
    border: none;
    border-bottom: 1px solid #E4E7EC;
    padding: 9px 8px;
    font-weight: 700;
}
QTableWidget::item {
    padding: 7px;
}
QTabWidget::pane {
    border: none;
}
QProgressBar {
    border: none;
    background: #EAECF0;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #2F6BFF;
    border-radius: 4px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #C5CAD3;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QCheckBox {
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QToolTip {
    background: #101828;
    color: white;
    border: none;
    padding: 6px;
}
"""
