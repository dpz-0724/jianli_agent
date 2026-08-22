# -*- coding: utf-8 -*-
"""隔离：off-screen 窗口位置是否导致虚拟列表只渲染首卡。"""
import sys
sys.path.insert(0, "code")
from searcher import CandidateSearcher

class _Noop:
    def __getattr__(self, n):
        return lambda *a, **k: None

for hide in (True, False):
    bot = CandidateSearcher({"hide_browser": hide, "chrome_path": None}, _Noop())
    try:
        bot.launch()
        if bot.go_search():
            bot.do_search("Java")
            bot.page.wait_for_timeout(6000)
            n = bot.page.content().count("search-resume-item-wrap")
            print(f"hide_browser={hide}: 卡片数={n}")
    except Exception as e:
        print(f"hide_browser={hide}: 出错 {e}")
    finally:
        try: bot.close()
        except Exception: pass
print("ISOLATION DONE")