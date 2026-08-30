# -*- coding: utf-8 -*-
"""授权码：签发/验签/机器绑定/期限。"""
import time

from workbench import license_mgr
from workbench.license_mgr import make_license, verify_license, machine_fingerprint

_PRIV = "00" * 32  # 测试用私钥（与嵌入公钥不对应，故单独构造一对）


def _gen_pair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    return priv.private_bytes_raw().hex(), priv.public_key().public_bytes_raw().hex()


def test_roundtrip_with_matching_pubkey(monkeypatch):
    priv, pub = _gen_pair()
    monkeypatch.setattr(license_mgr, "PUBLIC_KEY_HEX", pub)
    monkeypatch.setattr(license_mgr, "machine_fingerprint", lambda: "AAAA-BBBB-CCCC-DDDD")
    code = make_license(priv, "测试公司", "AAAA-BBBB-CCCC-DDDD", days=30)
    ok, info = verify_license(code)
    assert ok, info
    assert info["c"] == "测试公司"
    assert info["_expires_text"]


def test_wrong_machine_rejected(monkeypatch):
    priv, pub = _gen_pair()
    monkeypatch.setattr(license_mgr, "PUBLIC_KEY_HEX", pub)
    monkeypatch.setattr(license_mgr, "machine_fingerprint", lambda: "ZZZZ-YYYY-XXXX-WWWW")
    code = make_license(priv, "测试公司", "AAAA-BBBB-CCCC-DDDD", days=30)
    ok, reason = verify_license(code)
    assert not ok
    assert "不匹配" in reason


def test_tampered_code_rejected(monkeypatch):
    priv, pub = _gen_pair()
    monkeypatch.setattr(license_mgr, "PUBLIC_KEY_HEX", pub)
    monkeypatch.setattr(license_mgr, "machine_fingerprint", lambda: "AAAA-BBBB-CCCC-DDDD")
    code = make_license(priv, "测试公司", "AAAA-BBBB-CCCC-DDDD", days=30)
    bad = code[:-4] + ("AAAA" if not code.endswith("AAAA") else "BBBB")
    ok, reason = verify_license(bad)
    assert not ok


def test_expired_rejected(monkeypatch):
    priv, pub = _gen_pair()
    monkeypatch.setattr(license_mgr, "PUBLIC_KEY_HEX", pub)
    monkeypatch.setattr(license_mgr, "machine_fingerprint", lambda: "AAAA-BBBB-CCCC-DDDD")
    code = make_license(priv, "测试公司", "*", days=1)
    # 手动把到期时间改成过去
    import base64, json
    p = code.split(".")
    payload = json.loads(base64.urlsafe_b64decode(p[1] + "=" * (-len(p[1]) % 4)).decode())
    payload["e"] = int(time.time()) - 100
    # 重新签名(用测试私钥)使验签通过但已过期
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv_obj = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv))
    body = p[0] + "." + base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(priv_obj.sign(body.encode())).decode().rstrip("=")
    expired_code = body + "." + sig
    ok, reason = verify_license(expired_code)
    assert not ok
    assert "到期" in reason


def test_wildcard_machine_ok(monkeypatch):
    priv, pub = _gen_pair()
    monkeypatch.setattr(license_mgr, "PUBLIC_KEY_HEX", pub)
    monkeypatch.setattr(license_mgr, "machine_fingerprint", lambda: "ANY-MACHINE-0000-0000")
    code = make_license(priv, "测试公司", "*", days=0)  # 永久 + 不绑定机器
    ok, info = verify_license(code)
    assert ok, info


def test_machine_fingerprint_format():
    fp = machine_fingerprint()
    parts = fp.split("-")
    assert len(parts) == 4 and all(len(p) == 4 for p in parts)
