# -*- coding: utf-8 -*-
"""登录流程测试：持久化 context + go_im 跳转 + 登录态检测（未登录分支）。"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "code")

from bot import BrowserBot

tmpdir = os.path.join(tempfile.gettempdir(), "zp_login_test")
cfg = {"hide_browser": True, "chrome_path": None, "user_data_dir": tmpdir, "keywords": []}

bot = BrowserBot(cfg, None)
bot.launch()
print("user_data_dir 已创建:", os.path.isdir(tmpdir))

already = bot.go_im()
print("go_im 返回(是否已登录):", already)
print("is_logged_in:", bot.is_logged_in())
print("最终URL:", bot.page.url)

assert already is False, "未登录时应返回 False"
assert bot.is_logged_in() is False, "登录页应判定为未登录"
assert "passport" in bot.page.url or "login" in bot.page.url, "应跳转到登录页"

bot.close()
print("LOGIN FLOW TEST OK（未登录分支验证通过）")