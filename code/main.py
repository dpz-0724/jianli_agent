# -*- coding: utf-8 -*-
"""云只智联 复现工程入口（CLI）。

用法示例：
    python main.py login          # 登录（账号1 / 密码）
    python main.py activate 卡密   # 卡密激活
    python main.py greet          # 启动浏览器，自动打招呼一轮
    python main.py collect        # 采集微信/手机号
    python main.py sync           # 云端同步
    python main.py export out.csv # 导出简历 CSV
"""
import sys
import configparser
from db import DB
from auth import AccountManager, License, machine_id
from api_client import CloudAPI

CFG = configparser.ConfigParser()
CFG.read("config.ini", encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    db = DB()
    acct = AccountManager()
    api = CloudAPI(app_key=CFG.get("global", "api.app_key", fallback=None))
    lic = License(api)

    if cmd == "login":
        slot = sys.argv[2] if len(sys.argv) > 2 else "账号1"
        u = acct.get(slot, "username")
        p = acct.get(slot, "password")
        dev = acct.get(slot, "device_id") or machine_id()
        print("登录结果:", api.login(u, p, dev))

    elif cmd == "activate":
        kami = sys.argv[2]
        dev = machine_id()
        print("激活结果:", lic.activate(kami, dev))

    elif cmd == "sync":
        data = api.sync_all()
        print("云端数据:", str(data)[:300])

    elif cmd == "export":
        path = sys.argv[2] if len(sys.argv) > 2 else "resumes.csv"
        print("已导出到:", db.export_csv(path))

    elif cmd == "greet":
        from bot import BrowserBot
        bot = BrowserBot({
            "hide_browser": CFG.getboolean("global", "hide_browser", fallback=False),
            "round_count": CFG.get("greet", "round_count", fallback="50"),
            "keywords": [k for k in CFG.get("filter", "keywords", fallback="").split("|") if k],
            "chrome_path": CFG.get("global", "chrome_path", fallback=None),
        }, db)
        bot.launch()
        bot.ensure_login()
        bot.search()
        bot.greet_round()
        bot.collect_contacts()
        bot.close()

    elif cmd == "collect":
        from bot import BrowserBot
        bot = BrowserBot({"hide_browser": False, "keywords": []}, db)
        bot.launch()
        bot.ensure_login()
        bot.collect_contacts()
        bot.close()

    else:
        print(f"未知命令: {cmd}\n" + __doc__)


if __name__ == "__main__":
    main()