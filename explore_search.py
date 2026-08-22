# -*- coding: utf-8 -*-
"""探查人才搜索页 /app/search：能否输入关键词搜出候选人（不依赖职位）。"""
import sys, os
sys.path.insert(0, "code")
from bot import BrowserBot

cfg = {"hide_browser": True, "chrome_path": None, "keywords": []}
bot = BrowserBot(cfg, None)

try:
    bot.launch()
    bot.page.goto("https://rd6.zhaopin.com/app/search", timeout=40000)
    bot.page.wait_for_timeout(5000)
    print("URL:", bot.page.url)
    print("标题:", bot.page.title())
    txt = bot.page.inner_text("body")
    print("页面文本(前1200字):")
    print(txt[:1200].replace("\n", " | "))

    # 找输入框
    inputs = bot.page.evaluate("""
      () => Array.from(document.querySelectorAll('input,textarea'))
        .map(i => ({tag:i.tagName, type:i.type||'', ph:i.placeholder||'', cls:(i.className||'').slice(0,60),
                     vis: i.offsetParent !== null}))
    """)
    print("\n=== 输入框 ===")
    for i in inputs:
        print("  ", i)

    # 找按钮
    btns = bot.page.evaluate("""
      () => Array.from(document.querySelectorAll('button,[role="button"],.km-button'))
        .map(b => ({text:(b.innerText||'').trim().slice(0,12), cls:(b.className||'').slice(0,60),
                    vis: b.offsetParent !== null}))
        .filter(b => b.text)
    """)
    print("\n=== 按钮 ===")
    for b in btns[:20]:
        print("  ", b)

    html = bot.page.content()
    open("search_dump.html", "w", encoding="utf-8").write(html)
    print("\nsearch_dump.html 已保存, 长度:", len(html))
except Exception as e:
    import traceback; traceback.print_exc()
    print("出错:", repr(e))
finally:
    try: bot.close()
    except Exception: pass
print("SEARCH PAGE EXPLORE DONE")