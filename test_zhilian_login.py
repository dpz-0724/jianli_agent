# -*- coding: utf-8 -*-
"""诊断：访问智联招聘 IM，查看登录页实际状态并截图。"""
from playwright.sync_api import sync_playwright

OUT = r"E:\终身学习\云只智联_reverse\zhilian_im.png"
try:
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1366, "height": 900},
                               user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36").new_page()
    page.goto("https://rd6.zhaopin.com/app/im", timeout=40000)
    page.wait_for_timeout(8000)
    print("最终URL:", page.url)
    print("页面标题:", page.title())
    txt = page.inner_text("body") or ""
    print("页面文本前500字:", txt[:500].replace("\n", " | "))
    page.screenshot(path=OUT, full_page=False)
    print("截图已保存:", OUT)
    # 检查关键元素
    for sel in ["iframe", ".qrcode", ".login", "input[type=password]", "input[type=tel]",
                "a.app-nav__item", "img"]:
        try:
            n = page.query_selector_all(sel)
            if n:
                print(f"  元素 {sel}: {len(n)} 个")
        except Exception:
            pass
    browser.close()
    p.stop()
    print("DIAG DONE")
except Exception as e:
    print("访问出错:", repr(e))