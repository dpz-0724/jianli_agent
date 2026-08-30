# -*- coding: utf-8 -*-
"""简历智能体 · 网页版 exe 启动器：启动本地服务并自动打开浏览器。"""
from __future__ import annotations

import sys
import threading
import time
import webbrowser

# 打包(onedir)后，先定位内置 Chromium，再启动服务
try:
    from workbench.browser_runtime import configure_packaged_browser_path
    configure_packaged_browser_path()
except Exception:
    pass

PORT = 8899


def _open_browser() -> None:
    time.sleep(1.8)
    try:
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    except Exception:
        pass


def main() -> None:
    from webapp.server import app
    import uvicorn

    threading.Thread(target=_open_browser, daemon=True).start()
    print("=" * 44)
    print("  简历智能体 · 已启动")
    print(f"  请在浏览器访问:  http://127.0.0.1:{PORT}")
    print("  (关闭本窗口即停止服务)")
    print("=" * 44)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
