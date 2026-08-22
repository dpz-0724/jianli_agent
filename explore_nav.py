# -*- coding: utf-8 -*-
"""探查智联候选人真实入口：加载 IM 页 → 提取顶部导航 → 逐个访问找候选人源。"""
import sys, os, time
sys.path.insert(0, "code")
from bot import BrowserBot

cfg = {"hide_browser": True, "chrome_path": None, "keywords": []}
bot = BrowserBot(cfg, None)

def dump_page(tag):
    try:
        url = bot.page.url
        title = bot.page.title()
        body = bot.page.inner_text("body")[:600].replace("\n", " | ")
        print(f"\n===== [{tag}] =====")
        print("URL:", url)
        print("标题:", title)
        print("文本:", body)
        return url
    except Exception as e:
        print(f"[{tag}] dump 出错: {e}")
        return ""

try:
    bot.launch()
    bot.go_im()
    dump_page("IM 页")
    bot.page.wait_for_timeout(2500)

    # 1. 提取顶部导航（a 标签 + 文字）
    print("\n===== 顶部导航项（DOM 实时提取）=====")
    navs = bot.page.evaluate("""
      () => {
        const out = [];
        document.querySelectorAll('a, [role="menuitem"], .app-nav__item, [class*="nav"]').forEach(el => {
          const t = (el.innerText || '').trim();
          if (t && t.length <= 8 && !t.includes('\\n')) {
            out.push({text: t, href: el.href || '', cls: (el.className||'').toString().slice(0,50)});
          }
        });
        return out.slice(0, 40);
      }
    """)
    seen = set()
    for n in navs:
        key = n["text"]
        if key in seen: continue
        seen.add(key)
        print(f"  [{n['text']}] href={n['href']}  class={n['cls']}")

    # 2. 提取所有可见的 href 路由
    print("\n===== 页面所有 href =====")
    hrefs = bot.page.evaluate("""
      () => Array.from(document.querySelectorAll('a[href]'))
        .map(a => ({href: a.href, text: (a.innerText||'').trim().slice(0,12)}))
        .filter(x => x.href.includes('zhaopin.com'))
    """)
    hs = set()
    for h in hrefs:
        if h["href"] not in hs:
            hs.add(h["href"])
            print(f"  [{h['text']}] {h['href']}")

except Exception as e:
    import traceback; traceback.print_exc()
    print("出错:", repr(e))
finally:
    try: bot.close()
    except Exception: pass
print("\nNAV EXPLORE DONE")