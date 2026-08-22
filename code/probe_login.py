# -*- coding: utf-8 -*-
"""第二轮：探测 login/reg/getzhilianka 的字段链，还原完整请求参数。"""
import urllib.request, urllib.parse, re, json, time

BASE = "http://175.24.227.191:8088"

def post(path, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, method="POST",
                                 headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        t = r.read(1500).decode("utf-8", "replace")
        return r.status, t
    except urllib.error.HTTPError as e:
        return e.code, e.read(1500).decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)

def show(name, path, data):
    s, t = post(path, data)
    keys = re.findall(r'Undefined array key "([^"]+)"', t)
    msg = ""
    try:
        msg = json.loads(t).get("msg", "")
    except Exception:
        pass
    print(f"[{name}] {data}")
    print(f"    HTTP={s} msg={msg!r} keys={keys}")
    if not msg and not keys:
        print("    raw:", t[:260].replace("\n", " "))
    time.sleep(0.4)

print("=== 登录字段链 ===")
show("login-zhanghao", "/api/login", {"zhanghao": "test999999"})
show("login-zhanghao+mima", "/api/login", {"zhanghao": "test999999", "mima": "testpass"})
show("login-account+password", "/api/login", {"account": "test999999", "password": "testpass"})
show("login-zhanghao+password", "/api/login", {"zhanghao": "test999999", "password": "testpass"})
show("login-username+password", "/api/login", {"username": "test999999", "password": "testpass"})

print("\n=== 注册字段 ===")
show("reg-zhanghao", "/api/reg", {"zhanghao": "test999999"})

print("\n=== 修改密码字段链 ===")
show("mima-zhanghao", "/api/update_mima", {"zhanghao": "test999999"})

print("\n=== 智联卡 ===")
show("zk-leixing+pingtai", "/api/getzhilianka", {"leixing": "1", "pingtai": "zhaopin"})
show("zk-leixing+pingtai+zhanghao", "/api/getzhilianka", {"leixing": "1", "pingtai": "zhaopin", "zhanghao": "test"})

print("\n=== 校验接口完整字段 ===")
show("judgeWeichat-full", "/api/judgeWeichat", {"zhanghao": "t", "name": "张三", "weichat": "wx", "laiyuan": "智联"})
show("judgePhone-full", "/api/judgePhone", {"zhanghao": "t", "name": "张三", "phone": "13800138000", "laiyuan": "智联"})