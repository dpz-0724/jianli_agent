# -*- coding: utf-8 -*-
"""候选人抓取器：从智联招聘 IM 候选人流抓取卡片，解析姓名/职位/地点/学历/经验/年龄/活跃度。

选择器沿用逆向 .rdata 明文还原的真实 DOM（前缀 im-/app-）。
抓取后交给 matcher 打分排序。
"""
import re
from bot import BrowserBot, SELECTORS
from matcher import SKILL_DICT, _has_word

EDU_PAT = re.compile(r"本科|硕士|博士|大专|中专/中技|中专|中技|高中|初中及以下|初中|全日制")
AGE_PAT = re.compile(r"(\d{1,2})\s*岁")
EXP_PAT = re.compile(r"在校/应届|应届|一年以内|1-3年|3-5年|5-10年|10年以上|(\d{1,2})年")
ACT_PAT = re.compile(r"刚刚活跃|在线|今日活跃|本周活跃|本月活跃|30天活跃")


def _first(pat, text):
    m = pat.search(text or "")
    return m.group(0) if m else ""


def _int(pat, text):
    m = pat.search(text or "")
    return int(m.group(1)) if m and m.group(1) else (0 if m else 0)


def _extract_skills(text):
    low = (text or "").lower()
    hits = []
    for w in SKILL_DICT:
        if _has_word(low, w) and w not in hits:
            hits.append(w)
    return "|".join(hits)


class CandidateSearcher(BrowserBot):
    """在 BrowserBot 基础上增加候选人抓取能力。"""

    def scrape_candidates(self, max_count=500, auto_scroll=True, scroll_rounds=50, on_progress=None):
        """抓取候选人；auto_scroll=True 时自动滚动页面触发懒加载，翻到列表底部抓全。

        on_progress(n) 每发现一个新候选人时回调，用于界面实时显示「已发现 N 人」。
        """
        cands, seen = [], set()

        def _emit():
            if on_progress:
                try:
                    on_progress(len(cands))
                except Exception:
                    pass

        def parse_visible():
            cards = self.page.query_selector_all("div.im-candidate__row") or \
                    self.page.query_selector_all("div.im-candidate__row.has-separator")
            for card in cards:
                if len(cands) >= max_count:
                    return
                try:
                    text = (card.inner_text() or "").strip()
                except Exception:
                    continue
                name = self._sel_text(card, SELECTORS.get("cand_name")) or \
                       self._sel_text(card, SELECTORS.get("cand_b2b_name"))
                title = self._sel_text(card, SELECTORS.get("cand_job"))
                location = self._sel_text(card, SELECTORS.get("cand_location"))
                full = text.replace(name or "", "", 1)
                education = _first(EDU_PAT, full)
                age = _int(AGE_PAT, full)
                experience = _first(EXP_PAT, full)
                activity = _first(ACT_PAT, full) or _guess_activity(full)
                skills = _extract_skills(full)
                key = (name or title or text[:30]).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                cands.append({
                    "name": name or "", "title": title or "", "location": location or "",
                    "education": education, "age": age, "experience": experience,
                    "activity": activity, "skills": skills, "text": full,
                    "source": self.page.url,
                })
                _emit()

        parse_visible()
        if auto_scroll:
            stagnant = 0
            for _ in range(scroll_rounds):
                if len(cands) >= max_count:
                    break
                before = len(cands)
                try:
                    self.page.mouse.wheel(0, 2600)
                except Exception:
                    try:
                        self.page.evaluate("window.scrollBy(0, 2600)")
                    except Exception:
                        pass
                self.page.wait_for_timeout(1200)
                parse_visible()
                if len(cands) == before:
                    stagnant += 1
                    if stagnant >= 3:  # 连续 3 轮无新卡片 → 已到底
                        break
                else:
                    stagnant = 0
        return cands

    # ================= 搜索人才（不依赖职位的核心找人入口） =================

    def search_and_scrape(self, keyword, max_pages=5, max_count=200, on_progress=None):
        """智联「搜索人才」：输入关键词搜索 → 逐页抓取候选人卡片。

        on_progress(count, page_no)：进度回调。返回候选人字典列表。
        """
        self.do_search(keyword)
        cands, seen = [], set()
        for page_no in range(1, max_pages + 1):
            try:
                self.page.wait_for_selector(".search-resume-item-wrap", timeout=15000)
            except Exception:
                break
            cards = self.page.query_selector_all(".search-resume-item-wrap")
            for card in cards:
                c = self._parse_search_card(card)
                if not c:
                    continue
                key = (c["name"] or c["title"] or c["text"][:30]).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                cands.append(c)
                if on_progress:
                    try:
                        on_progress(len(cands), page_no)
                    except Exception:
                        pass
            if len(cands) >= max_count:
                break
            if not self._goto_next_page():
                break
        return cands

    def _goto_next_page(self):
        """点击搜索结果下一页；没有下一页返回 False。"""
        try:
            nxt = self.page.query_selector(".km-pagination__next:not([disabled])")
            if nxt:
                nxt.click()
                self.page.wait_for_timeout(2500)
                return True
            cur = self.page.query_selector(".km-pagination__pager--current")
            if cur:
                nxt2 = cur.evaluate_handle(
                    "el => el.nextElementSibling").as_element()
                if nxt2 and "km-pagination__pager" in (nxt2.get_attribute("class") or ""):
                    nxt2.click()
                    self.page.wait_for_timeout(2500)
                    return True
            return False
        except Exception:
            return False

    def _parse_search_card(self, card):
        """解析搜索人才结果卡片 → 候选人字典（字段对齐 matcher 打分模型）。"""
        def sel_text(sel):
            try:
                el = card.query_selector(sel)
                return (el.inner_text() or "").strip() if el else ""
            except Exception:
                return ""
        try:
            text = (card.inner_text() or "").strip()
        except Exception:
            return None
        if not text:
            return None
        name = sel_text(".talent-basic-info__name--inner") or sel_text(".talent-basic-info__name")
        age_t = sel_text(".age-label")
        exp_t = sel_text(".work-years-label")
        edu = sel_text(".education-label")
        career = sel_text(".career-status-label")
        extra = sel_text(".talent-basic-info__extra")
        title = sel_text(".talent-experience__title")
        # 活跃标签（半小时前有投递 / X小时前有回复 / 新注册 ...）
        try:
            tags = card.query_selector_all(".global-active-tag")
            act_text = " ".join((t.inner_text() or "").strip() for t in tags)
        except Exception:
            act_text = ""
        m = re.search(r"(\d{1,2})", age_t or "")
        age = int(m.group(1)) if m else 0
        experience = _years_to_segment(exp_t)
        location = _extract_city(extra or text)
        activity = _map_search_activity(act_text, career)
        skills = _extract_skills(text)
        return {
            "name": name, "title": title, "location": location,
            "education": edu, "age": age, "experience": experience,
            "activity": activity, "skills": skills, "text": text,
            "source": self.page.url,
        }

    def _sel_text(self, node, sel):
        try:
            el = node.query_selector(sel)
            return (el.inner_text() or "").strip() if el else ""
        except Exception:
            return ""


def _guess_activity(text):
    # 页面常见活跃度标签顺序猜测（无明确标签时降级）
    if "刚刚" in text:
        return "刚刚活跃"
    if "今日" in text:
        return "今日活跃"
    if "本周" in text:
        return "本周活跃"
    if "本月" in text:
        return "本月活跃"
    return ""


def _years_to_segment(exp_text):
    """把「8年/应届生/1-3年」之类统一成 matcher 经验段（带原文，便于筛选子串命中）。"""
    t = (exp_text or "").strip()
    if not t:
        return ""
    m = re.search(r"(\d{1,2})", t)
    if not m:
        if any(k in t for k in ("应届", "在校")):
            return "在校/应届"
        if "无经验" in t:
            return "一年以内"
        return t
    n = int(m.group(1))
    if n <= 0:
        seg = "在校/应届"
    elif n < 1:
        seg = "一年以内"
    elif n <= 3:
        seg = "1-3年"
    elif n <= 5:
        seg = "3-5年"
    elif n <= 10:
        seg = "5-10年"
    else:
        seg = "10年以上"
    return f"{seg}（{t}）" if seg not in t else t


SEARCH_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安",
                 "重庆", "天津", "长沙", "郑州", "青岛", "东莞", "佛山", "合肥", "厦门", "福州",
                 "大连", "济南", "昆明", "宁波", "无锡", "南昌", "南宁", "贵阳", "海口", "兰州",
                 "哈尔滨", "长春", "沈阳", "石家庄", "太原", "珠海"]


def _extract_city(text):
    """从期望信息/卡片文本中提取工作城市。"""
    m = re.search(r"期望[：:]\s*([^\s,，、]+)", text or "")
    if m:
        return m.group(1)
    for c in SEARCH_CITIES:
        if c in (text or ""):
            return c
    return ""


def _map_search_activity(tag_text, career_text=""):
    """把搜索结果页的活跃标签映射到打分模型的活跃度档位。"""
    t = tag_text or ""
    if "在线" in t:
        return "在线"
    if any(k in t for k in ("刚刚", "分钟前", "半小时")):
        return "刚刚活跃"
    if any(k in t for k in ("小时前", "今天", "今日", "新注册")):
        return "今日活跃"
    if any(k in t for k in ("昨天", "天前")):
        return "本周活跃"
    if t:
        return "本月活跃"
    # 无活跃标签时用求职状态兜底（离职找工作=近期活跃）
    if "离职" in (career_text or ""):
        return "本周活跃"
    return ""


if __name__ == "__main__":
    print("CandidateSearcher 已就绪（复用 BrowserBot 的 Playwright 驱动与真实选择器）")