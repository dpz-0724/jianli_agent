# -*- coding: utf-8 -*-
"""真实端到端测试：用已保存的登录态，自动打开智联 IM → 滚动 → 抓候选人。
回答用户的问题：自动化筛选到底能不能跑通。"""
import sys, os
sys.path.insert(0, "code")
from searcher import CandidateSearcher

# 用真实的持久化 profile（含用户登录态），headless 避免弹窗
cfg = {"hide_browser": True, "chrome_path": None, "keywords": []}
bot = CandidateSearcher(cfg, None)
try:
    bot.launch()
    print("浏览器已启动（复用已保存登录态）")
    logged = bot.go_im()
    print("go_im 返回(已登录?):", logged)
    print("当前URL:", bot.page.url)
    print("页面标题:", bot.page.title())

    if logged:
        print("\n=== 已登录，开始自动滚动抓取 ===")
        cands = bot.scrape_candidates(max_count=50, auto_scroll=True, scroll_rounds=8)
        print(f"\n抓到候选人: {len(cands)} 个")
        for i, c in enumerate(cands[:8], 1):
            print(f"  {i}. {c['name']} | {c['title']} | {c['location']} | "
                  f"{c['education']} | {c['experience']} | {c['activity']}")
        if not cands:
            # 抓不到 → dump 页面结构帮助定位选择器
            html = bot.page.content()
            with open("page_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("未抓到，页面已存 page_dump.html，长度:", len(html))
            print("页面文本前800字:", bot.page.inner_text("body")[:800].replace("\n", " | "))
    else:
        print("未登录（登录态可能未复用），当前在登录页")
        print("页面文本前300字:", bot.page.inner_text("body")[:300].replace("\n", " | "))
except Exception as e:
    import traceback; traceback.print_exc()
    print("出错:", repr(e))
finally:
    try:
        bot.close()
    except Exception:
        pass
print("REAL SCRAPE TEST DONE")