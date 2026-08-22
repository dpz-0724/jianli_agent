# -*- coding: utf-8 -*-
"""隔离2：主线程直接跑分支的 search_and_scrape，验证抓取/去重逻辑。"""
import sys
sys.path.insert(0, "code")
from searcher import CandidateSearcher

class _Noop:
    def __getattr__(self, n):
        return lambda *a, **k: None

bot = CandidateSearcher({"hide_browser": True, "chrome_path": None}, _Noop())
try:
    bot.launch()
    if bot.go_search():
        cands = bot.search_and_scrape("Java", max_pages=2, max_count=60,
                                      on_progress=lambda n, p: print(f"  第{p}页 累计 {n}"))
        print("search_and_scrape 结果:", len(cands))
        for c in cands[:3]:
            print("  ", c.get("name"), c.get("education"), c.get("experience"))
    else:
        print("未登录")
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    try: bot.close()
    except Exception: pass
print("DONE")