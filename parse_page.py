# -*- coding: utf-8 -*-
"""解析智联 IM 页 dump，找出候选人真实入口（推荐/搜索 tab）与选择器结构。"""
import re

html = open("page_dump.html", encoding="utf-8").read()
print("HTML 长度:", len(html))

# 1. 找顶部导航/Tab（职位|推荐|搜索|聊天...）
tabs = re.findall(r'class="([^"]*app-nav[^"]*)"[^>]*>([^<]{1,12})<', html)
print("\n=== app-nav 导航项 ===")
for cls, txt in tabs[:20]:
    print(f"  [{txt.strip()}] class={cls}")

# 2. 找所有 im- 开头的主要 class（去重统计）
classes = re.findall(r'class="([^"]*im-[a-z_-]+[^"]*)"', html)
from collections import Counter
cnt = Counter()
for c in classes:
    for part in c.split():
        if part.startswith("im-"):
            cnt[part] += 1
print("\n=== im-* class 出现统计(前30) ===")
for cls, n in cnt.most_common(30):
    print(f"  {cls}: {n}")

# 3. 候选人相关选择器
for pat in ["im-candidate", "candidate", "recommend", "人才", "暂无", "没有符合", "发布职位", "空状态", "empty"]:
    hits = re.findall(r'class="([^"]*' + pat + r'[^"]*)"', html)
    if hits:
        print(f"\n=== 含 '{pat}' 的 class ===")
        for h in set(hits[:12]):
            print("  ", h)

# 4. 关键提示文案附近
for kw in ["暂无在线职位", "没有符合条件的人才", "快去发布职位", "可帮您预读简历"]:
    idx = html.find(kw)
    if idx >= 0:
        seg = html[max(0, idx-200):idx+60]
        seg = re.sub(r'\s+', ' ', seg)
        print(f"\n=== 文案『{kw}』上下文 ===")
        print("  ", seg[-220:])