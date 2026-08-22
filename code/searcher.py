# -*- coding: utf-8 -*-
"""智联候选人搜索适配器。

本文件仍基于页面自动化，但提供了比旧版更稳定的搜索输入、候选人身份提取、
多字段去重和可诊断错误。业务评估由 workbench.evaluation 负责。
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bot import BrowserBot, SELECTORS
from matcher import SKILL_DICT, _has_word

EDU_PAT = re.compile(r"本科|硕士|博士|大专|中专/中技|中专|中技|高中|初中及以下|初中|全日制")
EXP_PAT = re.compile(r"在校/应届|应届|一年以内|1-3年|3-5年|5-10年|10年以上|(\d{1,2})年")
ACT_PAT = re.compile(r"刚刚活跃|在线|今日活跃|本周活跃|本月活跃|30天活跃")

SEARCH_CARD_SELECTORS = (
    ".search-resume-item-wrap",
    "[class*='search-resume-item']",
    "[class*='talent-card']",
)


def _first(pattern, text):
    match = pattern.search(text or "")
    return match.group(0) if match else ""


def _extract_skills(text):
    low = (text or "").lower()
    hits = []
    for word in SKILL_DICT:
        if _has_word(low, word) and word not in hits:
            hits.append(word)
    return "|".join(hits)


def _candidate_dedup_key(candidate):
    if candidate.get("platform_uid"):
        return "uid:" + str(candidate["platform_uid"])
    # 注意：不能用 source_url 兜底——同页候选人共享搜索页 URL，会把整页去重成 1 人。
    fields = (
        candidate.get("name", ""),
        candidate.get("title", ""),
        candidate.get("location", ""),
        candidate.get("education", ""),
        candidate.get("experience", ""),
        (candidate.get("text", "") or "")[:160],
    )
    return "fallback:" + "|".join(str(value).strip().lower() for value in fields)


class CandidateSearcher(BrowserBot):
    """BrowserBot 上的候选人搜索能力。"""

    def do_search(self, keyword):
        """清空旧条件后输入关键词，避免连续任务把关键词叠加。"""
        keyword = (keyword or "").strip()
        if not keyword:
            raise ValueError("搜索关键词不能为空")

        for selector in (".keyword-input-tags__placeholder", ".keyword-input-tags"):
            try:
                element = self.page.query_selector(selector)
                if element:
                    element.click()
                    self.page.wait_for_timeout(300)
                    break
            except Exception:
                continue

        input_element = None
        for selector in (
            "input.keyword-input-tag-item-input__input",
            "input[placeholder*='关键词']",
            "input[placeholder*='搜索']",
            "input[type='text']",
        ):
            try:
                input_element = self.page.query_selector(selector)
                if input_element:
                    break
            except Exception:
                continue
        if input_element is None:
            raise RuntimeError("SEARCH_INPUT_NOT_FOUND: 未找到智联搜索输入框")

        try:
            input_element.fill("")
        except Exception:
            try:
                input_element.click()
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
            except Exception as error:
                raise RuntimeError("SEARCH_INPUT_CLEAR_FAILED: 无法清空搜索输入框") from error

        try:
            input_element.fill(keyword)
        except Exception:
            input_element.click()
            self.page.keyboard.type(keyword, delay=50)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(2500)

    def scrape_candidates(self, max_count=500, auto_scroll=True, scroll_rounds=50, on_progress=None):
        """抓取 IM 候选人流。该入口保留给兼容场景。"""
        candidates, seen = [], set()

        def emit():
            if on_progress:
                try:
                    on_progress(len(candidates))
                except Exception:
                    pass

        def parse_visible():
            cards = self.page.query_selector_all("div.im-candidate__row") or self.page.query_selector_all(
                "div.im-candidate__row.has-separator"
            )
            for card in cards:
                if len(candidates) >= max_count:
                    return
                try:
                    text = (card.inner_text() or "").strip()
                except Exception:
                    continue
                name = self._sel_text(card, SELECTORS.get("cand_name")) or self._sel_text(
                    card, SELECTORS.get("cand_b2b_name")
                )
                title = self._sel_text(card, SELECTORS.get("cand_job"))
                location = self._sel_text(card, SELECTORS.get("cand_location"))
                full = text.replace(name or "", "", 1)
                uid, source_url = self._extract_identity(card)
                candidate = {
                    "platform": "zhilian",
                    "platform_uid": uid,
                    "name": name or "",
                    "title": title or "",
                    "location": location or "",
                    "education": _first(EDU_PAT, full),
                    "experience": _first(EXP_PAT, full),
                    "activity": _first(ACT_PAT, full) or _guess_activity(full),
                    "skills": _extract_skills(full),
                    "text": full,
                    "source": source_url or self.page.url,
                    "source_url": source_url or self.page.url,
                }
                key = _candidate_dedup_key(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                emit()

        parse_visible()
        if auto_scroll:
            stagnant = 0
            for _ in range(scroll_rounds):
                if len(candidates) >= max_count:
                    break
                before = len(candidates)
                try:
                    self.page.mouse.wheel(0, 2600)
                except Exception:
                    self.page.evaluate("window.scrollBy(0, 2600)")
                self.page.wait_for_timeout(1200)
                parse_visible()
                stagnant = stagnant + 1 if len(candidates) == before else 0
                if stagnant >= 3:
                    break
        return candidates

    def search_and_scrape(self, keyword, max_pages=5, max_count=200, on_progress=None):
        """搜索人才并分页抓取候选人。

        首屏若未发现结果容器，会抛出可诊断错误，而不是静默返回空列表。
        """
        self.do_search(keyword)
        candidates, seen = [], set()
        for page_no in range(1, max_pages + 1):
            selector = self._wait_for_search_cards(timeout=15000)
            if not selector:
                if page_no == 1:
                    raise RuntimeError(
                        "SEARCH_RESULTS_SELECTOR_MISSING: 未发现搜索结果卡片，可能是页面改版、账号限制或搜索未成功"
                    )
                break
            cards = self.page.query_selector_all(selector)
            for card in cards:
                candidate = self._parse_search_card(card)
                if not candidate:
                    continue
                key = _candidate_dedup_key(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                if on_progress:
                    try:
                        on_progress(len(candidates), page_no)
                    except Exception:
                        pass
                if len(candidates) >= max_count:
                    break
            if len(candidates) >= max_count or not self._goto_next_page():
                break
        return candidates

    def _wait_for_search_cards(self, timeout=15000):
        slice_timeout = max(1000, int(timeout / len(SEARCH_CARD_SELECTORS)))
        for selector in SEARCH_CARD_SELECTORS:
            try:
                self.page.wait_for_selector(selector, timeout=slice_timeout)
                if self.page.query_selector(selector):
                    return selector
            except Exception:
                continue
        return None

    def _goto_next_page(self):
        for selector in (
            ".km-pagination__next:not([disabled])",
            "button[aria-label*='下一页']:not([disabled])",
            "button:has-text('下一页'):not([disabled])",
        ):
            try:
                next_button = self.page.query_selector(selector)
                if next_button:
                    next_button.click()
                    self.page.wait_for_timeout(2200)
                    return True
            except Exception:
                continue
        try:
            current = self.page.query_selector(".km-pagination__pager--current")
            if current:
                next_element = current.evaluate_handle("el => el.nextElementSibling").as_element()
                if next_element and "km-pagination__pager" in (next_element.get_attribute("class") or ""):
                    next_element.click()
                    self.page.wait_for_timeout(2200)
                    return True
        except Exception:
            pass
        return False

    def _parse_search_card(self, card):
        def sel_text(selectors):
            if isinstance(selectors, str):
                selectors = (selectors,)
            for selector in selectors:
                try:
                    element = card.query_selector(selector)
                    if element:
                        value = (element.inner_text() or "").strip()
                        if value:
                            return value
                except Exception:
                    continue
            return ""

        try:
            text = (card.inner_text() or "").strip()
        except Exception:
            return None
        if not text:
            return None

        name = sel_text((".talent-basic-info__name--inner", ".talent-basic-info__name", "[class*='name']"))
        exp_text = sel_text((".work-years-label", "[class*='work-years']"))
        education = sel_text((".education-label", "[class*='education-label']"))
        career = sel_text((".career-status-label", "[class*='career-status']"))
        extra = sel_text((".talent-basic-info__extra", "[class*='basic-info__extra']"))
        title = sel_text((".talent-experience__title", "[class*='experience__title']"))

        try:
            tags = card.query_selector_all(".global-active-tag")
            activity_text = " ".join((tag.inner_text() or "").strip() for tag in tags)
        except Exception:
            activity_text = ""

        uid, source_url = self._extract_identity(card)
        return {
            "platform": "zhilian",
            "platform_uid": uid,
            "name": name,
            "title": title,
            "location": _extract_city(extra or text),
            "education": education or _first(EDU_PAT, text),
            "experience": _years_to_segment(exp_text or _first(EXP_PAT, text)),
            "activity": _map_search_activity(activity_text, career),
            "skills": _extract_skills(text),
            "text": text,
            "source": source_url or self.page.url,
            "source_url": source_url or self.page.url,
        }

    def _extract_identity(self, card):
        for attribute in (
            "data-resume-id",
            "data-resumeid",
            "data-enc-resume-id",
            "data-user-id",
            "data-candidate-id",
            "data-id",
        ):
            try:
                value = card.get_attribute(attribute)
                if value:
                    return value.strip(), self.page.url
            except Exception:
                continue

        href = ""
        for selector in (
            "a[href*='resume']",
            "a[href*='talent']",
            "a[href*='candidate']",
            "a[href]",
        ):
            try:
                link = card.query_selector(selector)
                if link:
                    href = (link.get_attribute("href") or "").strip()
                    if href:
                        break
            except Exception:
                continue
        if not href:
            return "", ""

        absolute_url = urljoin(self.page.url, href)
        parsed = urlparse(absolute_url)
        query = parse_qs(parsed.query)
        for key in (
            "resumeId",
            "resumeid",
            "encResumeId",
            "resumeNumber",
            "userId",
            "candidateId",
            "id",
        ):
            values = query.get(key)
            if values and values[0]:
                return values[0], absolute_url

        path_match = re.search(r"/(?:resume|talent|candidate)/([^/?#]+)", parsed.path, re.I)
        if path_match:
            return path_match.group(1), absolute_url
        return "", absolute_url

    def _sel_text(self, node, selector):
        if not selector:
            return ""
        try:
            element = node.query_selector(selector)
            return (element.inner_text() or "").strip() if element else ""
        except Exception:
            return ""


def _guess_activity(text):
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
    text = (exp_text or "").strip()
    if not text:
        return ""
    if re.search(r"\d{1,2}\s*[-—~至到]\s*\d{1,2}\s*年", text):
        return text
    if "10年以上" in text:
        return text
    match = re.search(r"(\d{1,2})", text)
    if not match:
        if any(token in text for token in ("应届", "在校")):
            return "在校/应届"
        if "无经验" in text:
            return "一年以内"
        return text
    years = int(match.group(1))
    if years <= 0:
        segment = "在校/应届"
    elif years <= 1:
        segment = "一年以内"
    elif years <= 3:
        segment = "1-3年"
    elif years <= 5:
        segment = "3-5年"
    elif years <= 10:
        segment = "5-10年"
    else:
        segment = "10年以上"
    return f"{segment}（{text}）" if segment not in text else text


SEARCH_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安",
    "重庆", "天津", "长沙", "郑州", "青岛", "东莞", "佛山", "合肥", "厦门", "福州",
    "大连", "济南", "昆明", "宁波", "无锡", "南昌", "南宁", "贵阳", "海口", "兰州",
    "哈尔滨", "长春", "沈阳", "石家庄", "太原", "珠海",
]


def _extract_city(text):
    match = re.search(r"期望[：:]\s*([^\s,，、]+)", text or "")
    if match:
        return match.group(1)
    for city in SEARCH_CITIES:
        if city in (text or ""):
            return city
    return ""


def _map_search_activity(tag_text, career_text=""):
    text = tag_text or ""
    if "在线" in text:
        return "在线"
    if any(token in text for token in ("刚刚", "分钟前", "半小时")):
        return "刚刚活跃"
    if any(token in text for token in ("小时前", "今天", "今日", "新注册")):
        return "今日活跃"
    if any(token in text for token in ("昨天", "天前")):
        return "本周活跃"
    if text:
        return "本月活跃"
    if "离职" in (career_text or ""):
        return "本周活跃"
    return ""
