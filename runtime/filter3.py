# -*- coding: utf-8 -*-
"""Strong filter on correctly-aligned CJK runs: GB2312 coverage + length + CJK density."""
src = r"E:\终身学习\云只智联_reverse\runtime\pid90364_cjk.txt"

def gb2312_ok(c):
    try:
        c.encode("gb2312"); return True
    except Exception:
        return False

kept = []
seen = set()
for line in open(src, encoding="utf-8", errors="ignore"):
    s = line.strip()
    L = len(s)
    if not (2 <= L <= 40):
        continue
    cjk = [c for c in s if "\u4e00" <= c <= "\u9fff"]
    if len(cjk) < 2:
        continue
    if cjk and (len(cjk) / L) < 0.65:
        continue
    g = sum(1 for c in cjk if gb2312_ok(c))
    if g / len(cjk) < 0.9:
        continue
    if s not in seen:
        seen.add(s)
        kept.append(s)

kept.sort(key=lambda x: -len(x))
out = r"E:\终身学习\云只智联_reverse\runtime\real_cjk2.txt"
open(out, "w", encoding="utf-8").write("\n".join(kept))
print("kept:", len(kept), "->", out)