# -*- coding: utf-8 -*-
"""端到端验证：App 的登录检测链（open_site → watch → after 回调 → 界面变绿）
用 FakeBot 模拟：go_im 返回未登录，is_logged_in 在第 3 次调用时返回已登录。"""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod


class FakeBot:
    def __init__(self):
        self.calls = 0

    def go_im(self, timeout=40000):
        print("[fake] go_im called")
        return False  # 未登录 → 进 watch 循环

    def is_logged_in(self):
        self.calls += 1
        ok = self.calls >= 3
        print(f"[fake] is_logged_in #{self.calls} -> {ok}")
        return ok

    def close(self):
        pass


a = appmod.App()
fake = FakeBot()
a.bot = fake
a.get_bot = lambda: fake  # 绕过真实 bot

a.search.open_site()

# 驱动主循环，最多 20 秒
deadline = time.time() + 20
state = None
while time.time() < deadline:
    a.update()
    state = a.search.login_state.get()
    if "已登录" in state:
        break
    time.sleep(0.1)

print("最终登录状态:", state)
print("is_logged_in 被调用次数:", fake.calls)
ok = state is not None and "已登录" in state
a.destroy()
print("CHAIN TEST", "OK" if ok else "FAILED")