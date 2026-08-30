# -*- coding: utf-8 -*-
"""一次性生成卖方 Ed25519 密钥对。私钥仅存 _vendor_private.key（绝不分发）。"""
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pathlib, sys

out = pathlib.Path(__file__).parent / "_vendor_private.key"
priv = Ed25519PrivateKey.generate()
priv_hex = priv.private_bytes_raw().hex()
pub_hex = priv.public_key().public_bytes_raw().hex()
out.write_text(priv_hex, encoding="utf-8")
print("私钥已保存到:", out, "（绝不分发！）")
print("公钥HEX（嵌入 license_mgr.py 的 PUBLIC_KEY_HEX）:")
print(pub_hex)
