# -*- coding: utf-8 -*-
"""UID 探测：搜索结果卡片是否携带平台 UID（data-* / 链接 / 全局变量）。"""
import sys, json, re
sys.path.insert(0, "code")
from searcher import CandidateSearcher

class _Noop:
    def __getattr__(self, n):
        return lambda *a, **k: None

bot = CandidateSearcher({"hide_browser": True, "chrome_path": None}, _Noop())
try:
    bot.launch()
    if bot.go_search():
        bot.do_search("销售")
        bot.page.wait_for_timeout(5000)
        info = bot.page.evaluate("""
          () => {
            const cards = Array.from(document.querySelectorAll('.search-resume-item-wrap')).slice(0, 3);
            const out = [];
            for (const card of cards) {
              // 卡片及内部前 3 层元素的所有 data-* 属性
              const dataAttrs = [];
              const walk = (el, depth) => {
                if (depth > 3) return;
                for (const a of el.attributes || []) {
                  if (a.name.startsWith('data-') || a.name === 'href' || a.name === 'id') {
                    dataAttrs.push({tag: el.tagName, attr: a.name, val: a.value.slice(0, 80)});
                  }
                }
                for (const ch of el.children) walk(ch, depth + 1);
              };
              walk(card, 0);
              // 卡片内所有 a 链接
              const links = Array.from(card.querySelectorAll('a[href]')).map(a => a.href).slice(0, 5);
              out.push({dataAttrs, links});
            }
            // 页面全局变量里是否有简历 id 映射
            const winKeys = Object.keys(window).filter(k => /resume|talent|candidate/i.test(k)).slice(0, 10);
            return {cards: out, winKeys};
          }
        """)
        print(json.dumps(info, ensure_ascii=False, indent=1)[:3500])
        # 页面 HTML 里搜 resume id 类字段
        html = bot.page.content()
        pats = ["resumeId", "encResumeId", "resume_id", "data-resume", "userId", "talentId"]
        for p in pats:
            hits = re.findall(r'.{40}' + p + r'.{60}', html)
            if hits:
                print(f"\n[HTML 命中 {p}] {hits[0][:120]}")
            else:
                print(f"[HTML 无 {p}]")
    else:
        print("未登录")
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    try: bot.close()
    except Exception: pass
print("UID PROBE DONE")