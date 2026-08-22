# -*- coding: utf-8 -*-
"""UI labels and operating-system helpers."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox

ASSESSMENT_LABELS = {"PASS": "通过", "REVIEW": "待复核", "CONFLICT": "明确冲突", None: "未评估"}
STAGE_LABELS = {
    "NEW": "新入池", "TO_REVIEW": "待复核", "TO_CONTACT": "待联系", "CONTACTED": "已联系",
    "INTERVIEW": "面试中", "OFFER": "已发 Offer", "HIRED": "已入职", "REJECTED": "不合适",
    "TALENT_POOL": "人才库",
}
RUN_LABELS = {
    "PENDING": "等待中", "RUNNING": "运行中", "NEED_LOGIN": "等待登录",
    "SUCCEEDED": "成功", "FAILED": "失败", "CANCELLED": "已取消",
}


def open_folder(path: str) -> None:
    folder = Path(path or "")
    if not folder.exists():
        messagebox.showwarning("目录不存在", f"目录不存在：\n{folder}")
        return
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as error:
        messagebox.showerror("打开失败", str(error))
