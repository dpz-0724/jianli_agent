# -*- coding: utf-8 -*-
"""提取智联顶部导航的路由 + 候选人相关可点击入口。"""
import re
html = open("page_dump.html", encoding="utf-8").read()

# 导航链接 href + 文字
print("=== 所有 href 路由 ===")
hrefs = re.findall(r'href="([^"]+)"[^>]*>\s*<span[^>]*>\s*([^<]{1,12})\s*<', html)
seen = set()
for h, t in hrefs:
    t = t.strip()
    if t and (h, t) not in seen and ("rd6" in h or h.startswith("/") or "zhaopin" in h):
        seen.add((h, t)); print(f"  [{t}] -> {h}")

print("\n=== 顶部导航文字(职位/推荐/搜索/聊天/人才管理) ===")
for kw in ["职位", "推荐", "搜索", "聊天", "互动", "人才管理", "人才"]:
    # 找带该文字的 a/span 及其 class/href
    for m in re.finditer(r'<a[^>]*?(?:href="([^"]*)")?[^>]*class="([^"]*)"[^>]*>\s*<span[^>]*>\s*' + kw + r'\s*<', html):
        print(f"  [{kw}] href={m.group(1)} class={m.group(2)}")
        break

print("\n=== 新招呼/推荐人才 相关 class ===")
for pat in ["recommend", "greeting", "new-greet", "招呼", "talent", "resume-card", "card"]:
    hits = set(re.findall(r'class="([^"]*' + pat + r'[^"]*)"', html))
    for h in list(hits)[:8]:
        print(f"  ({pat}) {h}")