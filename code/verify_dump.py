# -*- coding: utf-8 -*-
"""验证 dump 的节是否包含解密后的明文（API 路径 / URL / 中文字符串 / 导入表）。"""
import re, os

D = r"E:\终身学习\云只智联_reverse\dumped"
sections = [".rdata", ".text", ".data"]
checks = {
    "服务器IP": rb"175\.24\.227\.191",
    "api路径": rb"/api/(login|reg|getAllData|kamiSave|getzhilianka)",
    "字段zhanghao": rb"zhanghao",
    "字段mima": rb"mima",
    "字段laiyuan": rb"laiyuan",
    "智联招聘域名": rb"zhaopin\.com",
    "HTTPS": rb"https?://",
}

for sec in sections:
    p = os.path.join(D, f"云只_智联 4.3.8.exe_{sec}.section.bin")
    if not os.path.exists(p):
        continue
    data = open(p, "rb").read()
    print(f"\n=== {sec} ({len(data)/1024:.1f} KB) ===")
    for label, pattern in checks.items():
        m = re.search(pattern, data)
        if m:
            # 打印上下文
            i = m.start()
            ctx = data[max(0, i-20): i+60]
            print(f"  [HIT] {label}: ...{ctx!r}")
        else:
            print(f"  [miss] {label}")

    # UTF-16LE 中文
    cn = re.findall(rb"(?:[\x00-\xff][\x4e-\x9f]){4,}", data)
    print(f"  UTF16-CJK runs (>=4字): {len(cn)}")
    if cn:
        for c in cn[:3]:
            try:
                print("    ", c.decode("utf-16le", "ignore"))
            except Exception:
                pass

    # ASCII 字符串数量
    ascii_count = len(re.findall(rb"[\x20-\x7e]{8,}", data))
    print(f"  ASCII strings (>=8): {ascii_count}")