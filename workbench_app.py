# -*- coding: utf-8 -*-
"""Production entrypoint for Recruitment Workbench V0.9."""
from __future__ import annotations

import logging
import os
import sys

from workbench.browser_runtime import configure_packaged_browser_path
from workbench.database import default_data_dir


def configure_logging() -> None:
    log_dir = default_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "workbench.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main() -> int:
    configure_logging()
    configure_packaged_browser_path()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from workbench.qt_ui import RecruitmentWorkbenchWindow

        application = QApplication.instance() or QApplication(sys.argv)
        application.setApplicationName("招聘自动化工作台")
        application.setOrganizationName("RecruitmentWorkbench")
        application.setStyle("Fusion")
        window = RecruitmentWorkbenchWindow()
        window.show()
        return int(application.exec())
    except Exception as error:
        logging.exception("应用启动失败")
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "启动失败",
                "招聘自动化工作台启动失败。\n\n"
                f"{error}\n\n详细信息已写入：{default_data_dir() / 'logs' / 'workbench.log'}",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
