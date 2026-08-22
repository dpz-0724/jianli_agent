# -*- coding: utf-8 -*-
"""Production entrypoint for Recruitment Workbench V1."""
from __future__ import annotations

import logging
import sys

from workbench.database import default_data_dir
from workbench.ui import WorkbenchApp


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
    try:
        app = WorkbenchApp()
        app.mainloop()
        return 0
    except Exception:
        logging.exception("应用启动失败")
        try:
            import tkinter.messagebox as messagebox

            messagebox.showerror(
                "启动失败",
                "招聘自动化工作台启动失败。详细信息已写入本地日志目录。",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
