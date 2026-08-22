# -*- coding: utf-8 -*-
"""实测：搜索人才 → 翻页抓取 → 字段解析 全链路。"""
import sys
sys.path.insert(0, "code")
from searcher import CandidateSearcher

cfg = {"hide_browser": True, "chrome_path": None, "keywords": []}
bot = CandidateSearcher(cfg, None)
try:
    bot.launch()
    logged = bot.go_search()
    print("已登录:", logged)
    if logged:
        cands = bot.search_and_scrape("Java", max_pages=2, max_count=60,
                                      on_progress=lambda n, p: print(f"  ...第{p}页 已发现 {n} 人"))
        print(f"\n共抓到 {len(cands)} 个候选人")
        for i, c in enumerate(cands[:10], 1):
            print(f"{i}. {c['name']} | {c['title']} | {c['location']} | {c['education']} | "
                  f"{c['experience']} | {c['age']}岁 | {c['activity']}")
            print(f"   技能: {c['skills'][:80]}")
except Exception as e:
    import traceback; traceback.print_exc()
    print("出错:", repr(e))
finally:
    try: bot.close()
    except Exception: pass
print("SEARCH SCRAPE TEST DONE")