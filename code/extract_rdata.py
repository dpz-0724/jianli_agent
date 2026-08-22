# -*- coding: utf-8 -*-
"""从 .rdata 明文 dump 提取完整 URL、API 参数、CSS 选择器，分类落盘。"""
import re, os

D = r"E:\终身学习\云只智联_reverse\dumped"
p = os.path.join(D, "云只_智联 4.3.8.exe_.rdata.section.bin")
data = open(p, "rb").read()

# null-separated ASCII strings
strings = [s.decode("utf-8", "replace") for s in re.findall(rb"[\x20-\x7e]{5,}", data)]
strings = list(dict.fromkeys(strings))

urls = [s for s in strings if re.search(r"https?://", s)]
params = [s for s in strings if re.search(r"(zhanghao|mima|token|sign|laiyuan|number|begin|end_time|start_time|leixing|pingtai|kami|shouji|weichat|phone|name|key)=", s)]
selectors = [s for s in strings if re.search(r"(app-|\.app|#|>|div\b|span\b|input\b|button\b|img\b|li\b|a\b)", s) and not re.search(r"https?://", s)]
api_paths = [s for s in strings if re.search(r"/api/|/v1/|/app/", s)]

def dump(name, items):
    items = sorted(set(items))
    fp = os.path.join(D, f"rdata_{name}.txt")
    open(fp, "w", encoding="utf-8").write("\n".join(items))
    print(f"{name}: {len(items)} -> {os.path.basename(fp)}")

dump("urls", urls)
dump("params", params)
dump("selectors", selectors)
dump("api_paths", api_paths)
print("total strings:", len(strings))