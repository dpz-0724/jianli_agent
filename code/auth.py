# -*- coding: utf-8 -*-
"""账号 / 授权 / 设备绑定模块。

复现原程序的：
- 多账号槽位（账号1 ~ 账号9 + 一个「言账号」）
- 设备绑定（device_id 生成与校验，对应「设备已被使用 / 设备仍在使用 / 没有该设备」）
- 卡密/授权码激活（对应 /api/kamiSave、/api/getzhilianka）
"""
import os
import uuid
import hashlib
import configparser
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")


def machine_id():
    """生成设备指纹（原程序「设备绑定」依据，此处用稳定的机器标识近似）。"""
    raw = os.environ.get("COMPUTERNAME", "node") + "|" + \
        (os.environ.get("PROCESSOR_IDENTIFIER", "") or "cpu")
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


class AccountManager:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.cfg = configparser.ConfigParser()
        if os.path.exists(path):
            self.cfg.read(path, encoding="utf-8")

    def _slot(self, slot):
        if not self.cfg.has_section(slot):
            self.cfg.add_section(slot)
        return self.cfg[slot]

    def list_accounts(self):
        """列出所有账号槽位（账号1~账号9 + 言账号）"""
        slots = ["言账号"] + [f"账号{i}" for i in range(1, 10)]
        out = []
        for s in slots:
            if self.cfg.has_section(s):
                out.append((s, dict(self.cfg[s])))
        return out

    def get(self, slot, key, default=""):
        if self.cfg.has_section(slot):
            return self.cfg.get(slot, key, fallback=default)
        return default

    def set(self, slot, key, value):
        self._slot(slot)[key] = value
        self.save()

    def bind_device(self, slot, device_id=None):
        """绑定设备到账号"""
        device_id = device_id or machine_id()
        self.set(slot, "device_id", device_id)
        return device_id

    def set_expire(self, slot, expire_str):
        self.set(slot, "expire_at", expire_str)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            self.cfg.write(f)


class License:
    """授权与用量（对应 /api/kamiSave 卡密、/api/getzhilianka 智联卡）"""

    def __init__(self, api=None):
        self.api = api

    def activate(self, kami_code, device_id):
        if self.api:
            return self.api.activate_kami(kami_code, device_id)
        # 无云端时本地模拟：卡密 = 授权码
        return {"kami": kami_code, "device_id": device_id, "status": "ok"}

    def query(self):
        if self.api:
            return self.api.get_zhilianka()
        return {"zhilianka": "demo", "expire": "2099-12-31"}


if __name__ == "__main__":
    am = AccountManager()
    am.bind_device("账号1")
    am.set_expire("账号1", "2099-12-31")
    print("accounts:", am.list_accounts())
    print("machine_id:", machine_id())