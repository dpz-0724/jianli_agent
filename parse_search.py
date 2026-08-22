import re
html = open("search_result_dump.html", encoding="utf-8").read()
print("HTML 长度:", len(html))
# 分页/加载更多
for pat in ["下一页", "加载更多", "pagination", "pager", "load-more", "更多人才", "换一批", "共.*人", "共.*份", "发现.*人才", "为您找到"]:
    hits = re.findall(r'.{60}' + pat + r'.{60}', html)
    for h in hits[:3]:
        print(f"\n[{pat}] ...", re.sub(r"\s+"," ",h), "...")
# 候选人卡片容器
print("\nsearch-resume-item 数量:", html.count("search-resume-item-wrap"))
# 卡片的完整结构样例（取第一个卡片的 class 层级）
idx = html.find("search-resume-item-wrap")
if idx > 0:
    seg = html[idx-100:idx+3000]
    classes = re.findall(r'class="([^"]+)"', seg)
    print("\n第一个卡片的 class 序列:")
    for c in classes[:40]:
        print("  ", c)
