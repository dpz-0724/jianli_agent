# -*- coding: utf-8 -*-
"""浏览器自动化核心：智联招聘打招呼 / 沟通 / 采集微信与手机号。

选择器由逆向后 .rdata 明文还原（真实 DOM，前缀 im-/app-/km-）。
原程序（易语言）通过注入 CSS 选择器驱动谷歌浏览器；本实现用 Playwright 等价驱动 Chrome。
"""
import time
import os
from db import DB
from scripts import ScriptEngine, KeywordFilter


def _find_system_chrome():
    """探测系统已安装的谷歌浏览器（对标原软件「粘贴谷歌浏览器路径」）。
    优先用真实系统 Chrome：登录态/指纹更真实，规避自带 Chromium 的反爬特征。"""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Public\AppData\Local"),
                     "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

# ---- 智联招聘真实 CSS 选择器（从 .rdata 明文 dump 还原）----
SELECTORS = {
    # 导航
    "nav_item":        "a.app-nav__item",
    "nav_item_span":   "a.app-nav__item>span",
    "im_unread":       "div > div.app-im-unread",
    # 候选人卡片（打招呼对象）
    "candidate_row":   "div.im-candidate__row.has-separator>span.im-candidate__item",
    "cand_name":       "span.im-candidate__item.im-candidate__name",
    "cand_job":        "span.im-candidate__item > span.im-candidate__job",
    "cand_job_type":   "span.im-candidate__item.im-candidate__job-type",
    "cand_location":   "span.im-candidate__item.im-candidate__location",
    "cand_b2b_name":   "span.im-candidate__b2b-name",
    # 会话 / 消息
    "session_item":    "div.im-session-item.km-list__item",
    "session_person":  "div.im-session-panel__person",
    "session_name":    "span.im-session-item__name-title",
    "message":         "div.km-list__item.im-message",
    "bubble":          "div.km-list__item.im-message>div>div.im-message__bubble",
    "bubble_inner":    "div.km-list__item.im-message>div>div.im-message__bubble>div>div.im-message__bubble-inner-wrap",
    "bubble_me":       "div.im-message__bubble.im-message__bubble--me",
    "read_state":      "div.im-message__read-state.is-read",
    # 微信采集（核心）
    "wx_button":       "button.im-attachment-card__button--wx > div",
    "ask_contact_btn": "div.im-ask-for-contact__newwrap >button",
    "ask_wx_btn":      "div.im-ask-for-wx.im-action-button > a",
    "wx_number":       "div.im-ask-for-wx__number--text > div",   # 微信号文本
    "wx_card":         "div.im-wx-card__",
    "wx_card_name":    "div.im-wx-card__name",
    "wx_request_msg":  "div.im-message__bubble-inner.imc-wx-request",
    # 手机 / 虚拟号码
    "phone":           "div.im-new-info__phone.is-flex",
    "virtual_phone":   "span.virtual-number__text--phone.im-resume-basic__phone--black",
    "sensitive_phone": "div.km-popover.im-new-info__capply>div.km-popover__inner>div.sensitive-phone",
    # 交换联系方式
    "send_address_btn":"div.im-send-address__button>button",
    "send_address_mod":"button.im-module-send-address>div>span",
    # 三列表（职位切换）
    "three_change_btn":"div.im-three-list__change--button--new",
    "three_job_title": "div.im-three-list__panel--job--title.is-ellipsis",
    "three_panel_name":"div.im-three-list__panel--name",
    # 输入/发送
    "sender_input":    "div.im-sender__input-tip",                # 聊天输入区
    "sender_send":     "div.im-sender__input-tip--active>button", # 发送
}

URLS = {
    "home": "https://www.zhaopin.com/",
    "im":   "https://rd6.zhaopin.com/app/im",
    "search": "https://rd6.zhaopin.com/app/search",   # 搜索人才（不依赖职位）
    "recommend": "https://rd6.zhaopin.com/app/recommend",
    "sou":  "https://sou.zhaopin.com/",
}


class BrowserBot:
    def __init__(self, config: dict, db: DB):
        self.cfg = config
        self.db = db
        self.scripts = ScriptEngine()
        self.kw = KeywordFilter(config.get("keywords"))
        self.page = None

    def launch(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        headless = bool(self.cfg.get("hide_browser", False))
        chrome_path = self.cfg.get("chrome_path") or _find_system_chrome()
        self.user_data_dir = self.cfg.get("user_data_dir") or os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "云只智联", "chrome_profile")
        os.makedirs(self.user_data_dir, exist_ok=True)
        # 持久化 context：登录态保存在本地 chrome_profile，下次启动免登录
        self._context = self._pw.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=headless,
            executable_path=chrome_path,
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self.page

    def is_logged_in(self):
        """检测当前页面是否已登录智联招聘（多特征判定）。
        关键规则：未登录访问 rd6.zhaopin.com 必然被踢回 passport 登录页，
        所以只要停在 rd6 域且不在 login/passport，即视为已登录。"""
        try:
            url = self.page.url or ""
            if "passport" in url or "login" in url:
                return False
            if "rd6.zhaopin.com" in url or "zhaopin.com/app" in url:
                return True
            for sel in ("a.app-nav__item", "div.im-session-list", "div.im-candidate__row",
                        "div.im-widget-trigger", "div.im-three-list__panel", "div.im-session-item"):
                if self.page.query_selector(sel):
                    return True
            return False
        except Exception:
            return False

    def go_im(self, timeout=40000):
        """前往智联 IM；未登录会自动跳转登录页。返回是否已登录。"""
        self.page.goto(URLS["im"], timeout=timeout)
        self.page.wait_for_timeout(2500)
        return self.is_logged_in()

    def go_search(self, timeout=40000):
        """前往智联「搜索人才」页（不依赖在招职位的找人入口）。返回是否已登录。"""
        self.page.goto(URLS["search"], timeout=timeout)
        self.page.wait_for_timeout(2500)
        return self.is_logged_in()

    def do_search(self, keyword):
        """在搜索人才页输入关键词并触发搜索。"""
        ph = self.page.query_selector(".keyword-input-tags__placeholder") or \
             self.page.query_selector(".keyword-input-tags")
        if ph:
            try:
                ph.click()
                self.page.wait_for_timeout(500)
            except Exception:
                pass
        inp = self.page.query_selector("input.keyword-input-tag-item-input__input") or \
              self.page.query_selector("input[type=text]")
        if inp:
            try:
                inp.evaluate("el => el.focus()")
            except Exception:
                pass
        self.page.keyboard.type(keyword, delay=60)
        self.page.wait_for_timeout(400)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(3000)

    def mark_window(self):
        """把浏览器标签标题改成醒目提示并置顶，避免用户在别的窗口登录。"""
        try:
            self.page.bring_to_front()
        except Exception:
            pass
        try:
            self.page.evaluate("document.title = '【云只智联】请在本窗口登录'")
        except Exception:
            pass

    def greet_round(self, round_count=None):
        """一轮打招呼：遍历候选人卡片，命中过滤关键词则标记不沟通。"""
        round_count = round_count or int(self.cfg.get("round_count", 50))
        done = skip = 0
        cards = self.page.query_selector_all(SELECTORS["candidate_row"]) or \
                self.page.query_selector_all("div.im-candidate__row")
        for card in cards[:round_count]:
            nickname = self._text(card, SELECTORS["cand_name"])
            title = self._text(card, SELECTORS["cand_job"])
            if self.kw.should_skip(f"{nickname} {title}"):
                self.db.conn.execute(
                    "INSERT OR REPLACE INTO talks(nickname,title,status) VALUES(?,?,'不沟通')", (nickname, title))
                self.db.conn.commit()
                skip += 1
                continue
            try:
                card.click()
                time.sleep(0.5)
                # 交换联系方式（求简历/微信/手机）
                for sel in (SELECTORS["ask_contact_btn"], SELECTORS["ask_wx_btn"]):
                    el = self.page.query_selector(sel)
                    if el:
                        el.click()
                        break
                done += 1
                self.db.conn.execute(
                    "INSERT OR REPLACE INTO talks(nickname,title,status) VALUES(?,?,'已沟通')", (nickname, title))
                self.db.conn.commit()
                time.sleep(float(self.cfg.get("greet_interval", 2)))
            except Exception:
                pass
        print(f"打招呼完成：成功 {done}，跳过 {skip}")
        return done, skip

    def collect_contacts(self):
        """采集微信/手机号（含虚拟号码）：从消息气泡与微信名片读取。"""
        found = 0
        for sel in (SELECTORS["wx_number"], SELECTORS["wx_card_name"],
                    SELECTORS["virtual_phone"], SELECTORS["phone"]):
            for el in self.page.query_selector_all(sel):
                txt = (el.inner_text() or "").strip()
                wechat = self._extract_wechat(txt)
                phone = self._extract_phone(txt) or (txt if sel == SELECTORS["virtual_phone"] else None)
                if wechat or phone:
                    self.db.upsert_resume({"wechat": wechat, "phone": phone, "source": self.page.url})
                    found += 1
        # 从消息气泡里补抓
        for b in self.page.query_selector_all(SELECTORS["bubble_inner"]):
            txt = b.inner_text() or ""
            wechat = self._extract_wechat(txt)
            phone = self._extract_phone(txt)
            if wechat or phone:
                self.db.upsert_resume({"wechat": wechat, "phone": phone, "source": "im"})
                found += 1
        print(f"采集到 {found} 条联系方式")
        return found

    def _text(self, node, sel):
        try:
            el = node.query_selector(sel) if sel else node
            return (el.inner_text() or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_wechat(text):
        import re
        m = re.search(r"(?:微信|VX|vx|weixin)[:\s：]*([A-Za-z][A-Za-z0-9_-]{5,19})", text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_phone(text):
        import re
        m = re.search(r"1[3-9]\d{9}", text)
        return m.group(0) if m else None

    def close(self):
        try:
            if getattr(self, "_context", None):
                self._context.close()
            if getattr(self, "_pw", None):
                self._pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    print("BrowserBot 已就绪（智联招聘真实 DOM 选择器）")
    print("选择器来源: 逆向 .rdata 明文 dump")