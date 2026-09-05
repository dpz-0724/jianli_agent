# -*- coding: utf-8 -*-
"""离线授权码（Ed25519 签名 + 机器绑定 + 期限）。

设计：卖方持有私钥（仅授权码生成器使用，绝不随软件分发），公钥嵌入软件。
授权码 = 私钥签名的字符串，内含 客户名 / 绑定机器码 / 到期时间。
软件用公钥验签 + 校验机器码与期限，全部通过才放行。
纯离线、无需授权服务器；公钥只能验不能造，客户拿到公钥也无法伪造新码。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

# ===== 卖方公钥（嵌入软件，可验不可造）。私钥只在授权码生成器里。=====
# 由 tools/_gen_vendor_keys.py 生成；更换密钥对后需同步更新这里与生成器。
PUBLIC_KEY_HEX = "57f786f32c3b1690aebfe783de601ea28086a4bcdcb618937be2739ea741ece8"

_PREFIX = "ZL1"
_SALT = "zhaopin-agent::machine::v1"


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def machine_fingerprint() -> str:
    """本机机器码：Windows MachineGuid 加盐哈希，格式 XXXX-XXXX-XXXX-XXXX。
    换电脑/重装系统会变；无法读取时退回基于机器名的弱指纹。"""
    raw = ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        raw = winreg.QueryValueEx(key, "MachineGuid")[0]
    except Exception:
        try:
            raw = os.environ.get("COMPUTERNAME", "") + "|" + os.environ.get("USERNAME", "")
        except Exception:
            raw = "unknown"
    digest = hashlib.sha256((_SALT + raw).encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i:i + 4] for i in range(0, 16, 4))


def _license_dir() -> Path:
    from .database import default_data_dir
    d = default_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def license_file() -> Path:
    return _license_dir() / "license.key"


# ---------- 签发（仅授权码生成器调用，私钥不入软件） ----------
def make_license(private_key_hex: str, customer: str, machine: str = "*", days: int = 0) -> str:
    """生成授权码。machine='*' 表示不绑定机器；days=0 表示永久。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    payload = {
        "c": customer.strip(),
        "m": (machine or "*").strip().upper(),
        "e": 0 if days <= 0 else int(time.time()) + days * 86400,
        "i": int(time.time()),
        "n": hashlib.sha256(os.urandom(8)).hexdigest()[:8],
    }
    body = _PREFIX + "." + _b64e(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    sig = priv.sign(body.encode("utf-8"))
    return body + "." + _b64e(sig)


# ---------- 校验（软件内） ----------
def verify_license(code: str) -> tuple[bool, dict | str]:
    """校验授权码。返回 (是否有效, 载荷dict 或 失败原因str)。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        parts = (code or "").strip().split(".")
        if len(parts) != 3 or parts[0] != _PREFIX:
            return False, "授权码格式不正确"
        body = parts[0] + "." + parts[1]
        payload = json.loads(_b64d(parts[1]).decode("utf-8"))
        sig = _b64d(parts[2])
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        pub.verify(sig, body.encode("utf-8"))  # 验签失败会抛异常
    except Exception:
        return False, "授权码无效或已被篡改"
    # 期限
    exp = int(payload.get("e") or 0)
    if exp and time.time() > exp:
        return False, "授权已到期（到期日 %s）" % time.strftime("%Y-%m-%d", time.localtime(exp))
    # 机器绑定
    bound = (payload.get("m") or "*").upper()
    if bound != "*" and bound != machine_fingerprint().upper():
        return False, "授权码与本机不匹配（不能复制到其他电脑使用）"
    payload["_expires_text"] = "永久" if not exp else time.strftime("%Y-%m-%d", time.localtime(exp))
    return True, payload


def is_activated() -> bool:
    f = license_file()
    if not f.exists():
        return False
    try:
        ok, _ = verify_license(f.read_text(encoding="utf-8"))
        return ok
    except Exception:
        return False


def activate(code: str) -> tuple[bool, str]:
    """写入并校验授权码。成功返回 (True, 提示)，失败返回 (False, 原因)。"""
    ok, info = verify_license(code)
    if not ok:
        return False, str(info)
    license_file().write_text(code.strip(), encoding="utf-8")
    exp = info.get("_expires_text", "")
    return True, f"激活成功！授权给【{info.get('c','')}】，有效期：{exp}"


def current_activation() -> dict:
    """返回当前激活信息（供界面显示）。"""
    f = license_file()
    if not f.exists():
        return {"activated": False}
    ok, info = verify_license(f.read_text(encoding="utf-8"))
    if not ok:
        return {"activated": False, "error": str(info)}
    return {"activated": True, "customer": info.get("c", ""), "expires": info.get("_expires_text", "")}
