# -*- coding: utf-8 -*-
"""鉴别：搜索配额/风控 —— headed 模式搜一次，数卡片、看提示文案。"""
import sys, re
sys.path.insert(0, "code")
from searcher import CandidateSearcher

class _Noop:
    def __getattr__(self, n):
        return lambda *a, **k: None

bot = CandidateSearcher({"hide_browser": False, "chrome_path": None}, _Noop())
try:
    bot.launch()
    logged = bot.go_search()
    print("已登录:", logged)
    if logged:
        bot.do_search("Java")
        bot.page.wait_for_timeout(6000)
        html = bot.page.content()
        n_cards = html.count("search-resume-item-wrap")
        print("headed 模式卡片数:", n_cards)
        print("有分页组件:", "km-pagination" in html)
        txt = bot.page.inner_text("body")
        for kw in ["剩", "限制", "验证", "频繁", "异常", "次数用完", "安全", "滑块"]:
            i = txt.find(kw)
            if i >= 0:
                print(f"  文案命中[{kw}]: ...{txt[max(0,i-30):i+30]}...".replace("\n", " "))
        open("debug_headed_search.html", "w", encoding="utf-8").write(html)
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    try: bot.close()
    except Exception: pass
print("DEBUG DONE")