# -*- coding: utf-8 -*-
"""简历智能体 · 桌面版启动器。

把本地网页工作台套进一个原生桌面窗口（pywebview）：有任务栏图标、没有浏览器
地址栏，体验和独立软件一致；底层仍是本地服务，双击即用。窗口关闭即退出。
"""
from __future__ import annotations

import threading
import time

try:
    from workbench.browser_runtime import configure_packaged_browser_path
    configure_packaged_browser_path()
except Exception:
    pass

PORT = 8899


def _run_server() -> None:
    from webapp.server import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def main() -> None:
    import webview

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    # 等服务就绪
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    webview.create_window(
        "简历智能体",
        f"http://127.0.0.1:{PORT}",
        width=1460,
        height=920,
        min_size=(1100, 700),
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
