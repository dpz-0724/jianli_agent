# -*- coding: utf-8 -*-
"""端到端冒烟测试：验证复现工程所有模块可 import 且核心逻辑可用。"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db, scripts, auth, api_client, bot, main  # noqa: F401  (import 即验证无语法/依赖错误)

# 1) API 端点表完整
assert len(api_client.ENDPOINTS) == 18, f"endpoints={len(api_client.ENDPOINTS)}"
assert len(api_client.EXTERNAL) >= 6

# 2) 话术 + 关键词过滤
kf = scripts.KeywordFilter()
assert kf.should_skip("太远了") is True
assert kf.should_skip("你好，我想了解一下这个岗位") is False
se = scripts.ScriptEngine()
assert len(se.next_greeting("张三", "销售")) > 0
assert len(se.reject_message()) > 0

# 3) 账号 / 设备绑定 / 卡密（临时 config，不污染交付文件）
tmpcfg = os.path.join(tempfile.gettempdir(), "yunzhi_smoke.ini")
tmpdb = os.path.join(tempfile.gettempdir(), "yunzhi_smoke.db")
for f in (tmpcfg, tmpdb):
    if os.path.exists(f):
        os.remove(f)

am = auth.AccountManager(tmpcfg)
assert am.bind_device("账号1", "DEV123") == "DEV123"
am.set_expire("账号1", "2099-12-31")
assert am.get("账号1", "expire_at") == "2099-12-31"
assert auth.machine_id() != ""

lic = auth.License()  # 无云端 -> 本地模拟激活
assert lic.activate("KAMI001", "DEV123")["status"] == "ok"

# 4) 数据库去重 + 导出
d = db.DB(tmpdb)
d.upsert_resume({"name": "A", "phone": "13800000001", "wechat": "wx_a"})
d.upsert_resume({"name": "B", "phone": "13800000001"})  # 手机号重复 -> 去重
assert d.query("SELECT count(*) FROM resumes")[0][0] == 1
d.upsert_resume({"name": "C", "wechat": "wx_c"})
assert d.query("SELECT count(*) FROM resumes")[0][0] == 2
csv_path = os.path.join(tempfile.gettempdir(), "yunzhi_smoke.csv")
d.export_csv(csv_path)
assert os.path.exists(csv_path)
d.close()

# 5) bot 选择器与静态方法
assert bot.BrowserBot._extract_phone("加我微信 13812345678 详聊") == "13812345678"
assert bot.BrowserBot._extract_wechat("微信 VX: abcde_123") == "abcde_123"

for f in (tmpcfg, tmpdb, csv_path):
    if os.path.exists(f):
        os.remove(f)
print("ALL SMOKE TESTS PASSED")