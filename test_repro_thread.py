# -*- coding: utf-8 -*-
"""根因复现：Playwright sync API 跨线程调用会怎样。
模拟 app.py 真实情况：线程A launch 浏览器 + 同线程访问正常；线程B 调 is_logged_in 失败。"""
import sys, os, threading, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "code")
from bot import BrowserBot

tmp = os.path.join(tempfile.gettempdir(), "zp_repro_test")
cfg = {"hide_browser": True, "chrome_path": None, "user_data_dir": tmp, "keywords": []}
bot = BrowserBot(cfg, None)

launched = threading.Event()
same_result = {}

def thread_a():
    try:
        bot.launch()
        bot.page.goto("about:blank", timeout=30000)
        # 同线程访问（Playwright 绑定的线程）
        try:
            same_result["url"] = bot.page.url
            same_result["logged"] = bot.is_logged_in()
        except Exception as e:
            same_result["err"] = repr(e)
    finally:
        launched.set()

t = threading.Thread(target=thread_a, daemon=True)
t.start()
launched.wait(90)
time.sleep(1)

print("=== 1. 同线程访问（浏览器所在线程A） ===")
print("结果:", same_result)

print("=== 2. 跨线程访问 page.url（模拟 app.py 登录轮询线程B） ===")
try:
    u = bot.page.url
    print("未抛异常, url =", u)
except Exception as e:
    print("✗ 跨线程异常:", repr(e)[:300])

print("=== 3. 跨线程调 is_logged_in ===")
r = bot.is_logged_in()
print("is_logged_in 返回:", r, "（内部 except 吞异常 → 永远 False → '登录没反应'）")

try:
    bot.close()
except Exception:
    pass
print("REPRO DONE")