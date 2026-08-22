import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as appmod

class FakeBot:
    def go_im(self, timeout=40000):
        return False
    def is_logged_in(self):
        return False
    def close(self): pass

a = appmod.App()
fake = FakeBot()
a.bot = fake
a.get_bot = lambda: fake
a.search.open_site()

deadline = time.time() + 8
while time.time() < deadline:
    a.update()
    time.sleep(0.1)

logs = a.search.log_area.get("1.0", "end").strip()
print("===== 运行日志内容 =====")
print(logs)
a.destroy()
