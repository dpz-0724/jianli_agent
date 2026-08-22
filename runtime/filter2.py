# -*- coding: utf-8 -*-
"""Re-filter CJK dump using GB2312 coverage as a strong common-hanzi signal."""
src = r"E:\终身学习\云只智联_reverse\runtime\pid99568_cjk.txt"

def gb2312_ok(c):
    try:
        c.encode("gb2312")
        return True
    except Exception:
        return False

def score(s):
    L = len(s)
    if not (2 <= L <= 40):
        return None
    cjk = [c for c in s if "\u4e00" <= c <= "\u9fff"]
    if not cjk:
        return None
    good = sum(1 for c in cjk if gb2312_ok(c))
    ratio = good / L
    if ratio < 0.8:
        return None
    return ratio

kept = {}
for line in open(src, encoding="utf-8", errors="ignore"):
    s = line.strip()
    r = score(s)
    if r is not None:
        kept[s] = r

items = sorted(kept.items(), key=lambda kv: (-len(kv[0]), -kv[1]))
out = r"E:\终身学习\云只智联_reverse\runtime\real_cjk.txt"
with open(out, "w", encoding="utf-8") as f:
    for s, r in items:
        f.write(f"{s}\t{r:.2f}\n")
print("kept:", len(items), "->", out)