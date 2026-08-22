# -*- coding: utf-8 -*-
import os
base = r"E:\终身学习\云只智联_reverse\resources"
out = os.path.join(base, "version_report.txt")
lines = []
for f in ["res_3F5C73C.bin", "res_3F5C7D0.bin", "res_3F5CA00.bin"]:
    p = os.path.join(base, f)
    d = open(p, "rb").read()
    lines.append("===== " + f + " (" + str(len(d)) + " bytes) =====")
    if f == "res_3F5C73C.bin":
        lines.append(d.decode("utf-8", "replace"))
    else:
        txt = d.decode("utf-16le", "ignore")
        lines.append(repr(txt))
        lines.append("--- visible ---")
        lines.append(txt.replace("\x00", ""))
    lines.append("")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print("written", out)