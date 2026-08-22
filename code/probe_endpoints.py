# -*- coding: utf-8 -*-
"""系统探测全部端点：POST 空参数，收集 PHP 'Undefined array key' 泄露的字段名与中文提示。"""
import urllib.request, urllib.parse, re, time, json

BASE = "http://175.24.227.191:8088"

ENDPOINTS = {
    "login": "/api/login", "reg": "/api/reg", "kamiSave": "/api/kamiSave",
    "getzhilianka": "/api/getzhilianka", "updatazhiliankanew": "/api/updatazhiliankanew",
    "update_mima": "/api/update_mima", "getAllData": "/api/getAllData",
    "getMoHuData": "/api/getMoHuData", "getNunbers": "/api/getNunbers",
    "daochuAllData": "/api/daochuAllData", "insertDataNewUp": "/api/insertDataNewUp",
    "updateWeichatNew": "/api/updateWeichatNew", "updatePhoneNew": "/api/updatePhoneNew",
    "judgeWeichat": "/api/judgeWeichat", "judgePhone": "/api/judgePhone",
    "judgeDatas": "/api/judgeDatas", "messageNotifySend2": "/api/messageNotify/send2",
    "messageNotifySend3": "/api/messageNotify/send3",
}

def post(path, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, method="POST",
                                 headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, r.read(1200).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(1200).decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)

all_keys = {}
for name, path in ENDPOINTS.items():
    s, text = post(path, {})
    keys = re.findall(r'Undefined array key "([^"]+)"', text)
    msg = ""
    try:
        j = json.loads(text)
        msg = j.get("msg", "")
    except Exception:
        pass
    if keys:
        all_keys[name] = sorted(set(keys))
    print(f"[{name}] {path}")
    print(f"    HTTP={s} keys={sorted(set(keys))} msg={msg!r}")
    if not msg and not keys:
        print("    raw:", text[:200].replace("\n", " "))
    time.sleep(0.3)

print("\n=== 汇总：各端点泄露字段名 ===")
for name, keys in all_keys.items():
    print(f"{name}: {keys}")