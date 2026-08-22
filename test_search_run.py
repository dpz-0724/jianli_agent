# -*- coding: utf-8 -*-
"""关键测试 v2：人才搜索（修正输入框被 placeholder 遮挡）。"""
import sys, os
sys.path.insert(0, "code")
from bot import BrowserBot

cfg = {"hide_browser": True, "chrome_path": None, "keywords": []}
bot = BrowserBot(cfg, None)

try:
    bot.launch()
    bot.page.goto("https://rd6.zhaopin.com/app/search", timeout=40000)
    bot.page.wait_for_timeout(4000)

    # 点 placeholder 激活输入区
    ph = bot.page.query_selector(".keyword-input-tags__placeholder") or \
         bot.page.query_selector(".keyword-input-tags")
    if ph:
        ph.click()
        bot.page.wait_for_timeout(600)

    inp = bot.page.query_selector("input.keyword-input-tag-item-input__input") or \
          bot.page.query_selector("input[type=text]")
    if inp:
        inp.evaluate("el => el.focus()")
    bot.page.keyboard.type("Java", delay=80)
    bot.page.wait_for_timeout(500)
    bot.page.keyboard.press("Enter")
    print("已输入 Java 并回车搜索，等待结果 ...")
    bot.page.wait_for_timeout(9000)

    print("URL:", bot.page.url)
    txt = bot.page.inner_text("body")
    print("\n页面文本(搜索后 1800 字):")
    print(txt[:1800].replace("\n", " | "))

    import re
    html = bot.page.content()
    open("search_result_dump.html", "w", encoding="utf-8").write(html)
    from collections import Counter
    cnt = Counter()
    for c in re.findall(r'class="([^"]+)"', html):
        for part in c.split():
            if any(k in part for k in ("result", "card", "resume", "talent", "candidate", "item")):
                cnt[part] += 1
    print("\n=== 结果相关 class 统计(前30) ===")
    for cls, n in cnt.most_common(30):
        print(f"  {cls}: {n}")
except Exception as e:
    import traceback; traceback.print_exc()
    print("出错:", repr(e))
finally:
    try: bot.close()
    except Exception: pass
print("SEARCH TEST V2 DONE")