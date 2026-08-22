# -*- coding: utf-8 -*-
"""连通性 + API 端点探测：检查服务器是否存活，并用探测获取真实字段名。"""
import urllib.request
import urllib.parse
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.status, r.read(400)

def post(url, data, timeout=15):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return r.status, r.read(800)
    except urllib.error.HTTPError as e:
        return e.code, e.read(800)
    except Exception as e:
        return None, repr(e).encode()

print("=== 连通性 ===")
for name, url in [
    ("服务器", "http://175.24.227.191:8088/api/login"),
    ("智联招聘首页", "https://www.zhaopin.com/"),
    ("智联招聘IM", "https://rd6.zhaopin.com/app/im"),
    ("智联招聘搜索", "https://sou.zhaopin.com/"),
]:
    try:
        s, b = get(url)
        print(f"[OK] {name} -> HTTP {s}, {len(b)} bytes")
    except Exception as e:
        print(f"[FAIL] {name} -> {e}")

print("\n=== API 端点探测（POST 空/错误字段，看返回）===")
probes = [
    ("login", "/api/login", [("username", "probe"), ("password", "probe")]),
    ("login-empty", "/api/login", []),
    ("reg", "/api/reg", [("username", "probe")]),
    ("kamiSave", "/api/kamiSave", [("kami", "probe")]),
    ("getzhilianka", "/api/getzhilianka", []),
]
for name, path, params in probes:
    url = "http://175.24.227.191:8088" + path
    s, b = post(url, params)
    print(f"[{name}] {path} -> HTTP {s}")
    if b and isinstance(b, bytes):
        print("    " + b.decode("utf-8", "replace")[:300])
    elif isinstance(b, str):
        print("    " + b[:300])