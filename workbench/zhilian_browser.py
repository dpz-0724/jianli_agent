# -*- coding: utf-8 -*-
"""Product browser adapter for visible, controllable Zhilian automation.

The adapter keeps the existing page parser isolated behind a managed browser strategy:
Playwright Chromium by default, then Microsoft Edge / Google Chrome channels as explicit
fallbacks. It deliberately avoids fixed user-agent strings and anti-detection switches.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from typing import Any, Callable

from .browser_runtime import browser_profile_dir, configure_packaged_browser_path

ROOT_DIR = Path(__file__).resolve().parents[1]
LEGACY_CODE_DIR = ROOT_DIR / "code"
if str(LEGACY_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_CODE_DIR))

from searcher import CandidateSearcher, _candidate_dedup_key  # noqa: E402


class SearchCancelled(RuntimeError):
    pass


class ProductCandidateSearcher(CandidateSearcher):
    def __init__(self, config: dict[str, Any] | None = None, db=None):
        super().__init__(config or {}, db)
        self.active_browser_mode = ""
        self._last_launch_error = ""
        self._resume_quota_exhausted = False
        self._api_by_name: dict[str, list[str]] = {}
        self._api_ordered: list[str] = []
        self._api_certs: dict[str, list[list[str]]] = {}

    @staticmethod
    def _attempts(mode: str, custom_path: str = "") -> list[tuple[str, dict[str, Any]]]:
        managed = ("managed", {})
        edge = ("edge", {"channel": "msedge"})
        chrome = ("chrome", {"channel": "chrome"})
        custom = ("custom", {"executable_path": custom_path})
        mode = (mode or "managed").lower()
        if mode == "edge":
            return [edge, managed, chrome]
        if mode == "chrome":
            return [chrome, managed, edge]
        if mode == "custom" and custom_path:
            return [custom, managed, edge, chrome]
        if mode == "auto":
            return [managed, edge, chrome]
        return [managed, edge, chrome]

    def launch(self):
        if self._context is not None:
            self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
            return self.page

        configure_packaged_browser_path()
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        requested = str(self.cfg.get("browser_mode") or "managed")
        custom_path = str(self.cfg.get("custom_browser_path") or self.cfg.get("chrome_path") or "")
        visible = bool(self.cfg.get("browser_visible", True))
        slow_mo = max(0, min(int(self.cfg.get("slow_mo_ms", 0) or 0), 2000))
        bounds = self.cfg.get("window_bounds") or {}

        common: dict[str, Any] = {
            "headless": False,
            "locale": "zh-CN",
            "no_viewport": True,
            "slow_mo": slow_mo,
            "args": [],
        }
        if bounds:
            x, y = int(bounds.get("x", 0)), int(bounds.get("y", 0))
            width, height = int(bounds.get("width", 1200)), int(bounds.get("height", 850))
            common["args"].extend([f"--window-position={x},{y}", f"--window-size={width},{height}"])
        else:
            common["args"].append("--start-maximized")
        if not visible:
            common["args"].append("--window-position=-2400,-2400")

        errors: list[str] = []
        healed = False
        for mode, override in self._attempts(requested, custom_path):
            if mode == "custom" and not Path(custom_path).is_file():
                errors.append(f"custom: 文件不存在 {custom_path}")
                continue
            profile = browser_profile_dir(mode)
            profile.mkdir(parents=True, exist_ok=True)
            kwargs = dict(common)
            kwargs["args"] = list(common["args"])
            kwargs.update(override)
            try:
                self._context = self._pw.chromium.launch_persistent_context(str(profile), **kwargs)
                self.active_browser_mode = mode
                break
            except Exception as error:
                errors.append(f"{mode}: {error}")
                self._context = None
                # 自愈：managed 登录 profile 损坏（如进程被强杀）会导致启动即崩。
                # 备份坏 profile、重建空目录重试一次——用户只需重新登录，不会卡死。
                if mode == "managed" and not healed:
                    healed = True
                    try:
                        import shutil, time as _t
                        backup = profile.with_name(profile.name + "_broken_" + str(int(_t.time())))
                        shutil.move(str(profile), str(backup))
                        profile.mkdir(parents=True, exist_ok=True)
                        self._context = self._pw.chromium.launch_persistent_context(str(profile), **kwargs)
                        self.active_browser_mode = mode
                        break
                    except Exception as error2:
                        errors.append(f"{mode}(自愈重试): {error2}")
                        self._context = None

        if self._context is None:
            try:
                self._pw.stop()
            finally:
                self._pw = None
            self._last_launch_error = "\n".join(errors)
            raise RuntimeError(
                "无法启动受控浏览器。请运行 setup.bat 安装工作台 Chromium，或在设置中选择 Edge/Chrome。\n"
                + self._last_launch_error
            )

        self._context.set_default_timeout(int(self.cfg.get("default_timeout_ms", 20000)))
        self._context.set_default_navigation_timeout(int(self.cfg.get("navigation_timeout_ms", 45000)))
        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self.page

    def browser_info(self) -> dict[str, Any]:
        version = ""
        try:
            browser = self._context.browser if self._context is not None else None
            version = browser.version if browser is not None else ""
        except Exception:
            pass
        return {
            "running": self._context is not None,
            "mode": self.active_browser_mode or str(self.cfg.get("browser_mode") or "managed"),
            "version": version,
            "profile_dir": str(browser_profile_dir(self.active_browser_mode or "managed")),
            "current_url": str(getattr(self.page, "url", "") or ""),
            "visible": bool(self.cfg.get("browser_visible", True)),
        }

    def bring_to_front(self) -> None:
        if self.page is None:
            self.launch()
        self.page.bring_to_front()

    def open_url(self, url: str) -> None:
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ValueError("只能在受控浏览器中打开 HTTP/HTTPS 地址")
        if self.page is None:
            self.launch()
        page = self._context.new_page() if self._context is not None else self.page
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.bring_to_front()
        self.page = page

    def capture_preview(self, path: str | os.PathLike[str]) -> str:
        if self.page is None:
            raise RuntimeError("浏览器尚未启动")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(target), full_page=False)
        return str(target)

    # ---- 搜索源头筛选（城市/学历/经验），大幅提升筛选质量 ----

    def _click_filter_option(self, label: str, option: str) -> bool:
        """在筛选行(按 label 定位)里点击指定选项文本。"""
        try:
            return bool(self.page.evaluate(
                """([label, option]) => {
                  const labels = Array.from(document.querySelectorAll('.search-label-wrapper-new__label'));
                  const lbl = labels.find(e => (e.innerText||'').trim().startsWith(label));
                  if (!lbl) return false;
                  let container = lbl.parentElement;
                  for (let i = 0; i < 5 && container; i++) {
                    const opts = Array.from(container.querySelectorAll('span,div,a,li'))
                      .filter(e => e.offsetParent && (e.innerText||'').trim() === option && e.children.length === 0);
                    if (opts.length) { opts[0].click(); return true; }
                    container = container.parentElement;
                  }
                  return false;
                }""", [label, option]))
        except Exception:
            return False

    def set_city(self, city: str) -> bool:
        """把搜索的期望工作地切换到目标城市（取消默认城市，只保留目标）。"""
        city = (city or "").strip()
        if not city:
            return False
        try:
            btn = self.page.query_selector(".keyword-panel__city") or self.page.query_selector(".keyword-panel-city")
            if not btn:
                return False
            btn.click()
            self.page.wait_for_timeout(1300)
            if not self.page.query_selector("text=请选择人才期望城市"):
                return False
            self.page.evaluate(
                """(city) => {
                  const els = Array.from(document.querySelectorAll('div,span,li,a,p'))
                    .filter(e=>e.offsetParent && (e.textContent||'').trim()===city);
                  if(els.length){ els[els.length-1].click(); }
                }""", city)
            self.page.wait_for_timeout(700)
            # 取消已选里的其它城市标签
            self.page.evaluate(
                """(city) => {
                  const tags = Array.from(document.querySelectorAll('[class*=select],[class*=tag],[class*=chosen],[class*=check]'));
                  for(const t of tags){
                    const txt=(t.innerText||'').trim();
                    if(txt && txt!==city && txt.length<=6 && /[一-龥]/.test(txt)){
                      const x = t.querySelector('[class*=close],[class*=del],i,svg');
                      if(x){ x.click(); }
                    }
                  }
                }""", city)
            self.page.wait_for_timeout(400)
            self.page.evaluate(
                """() => {
                  const btns = Array.from(document.querySelectorAll('button,div,span,a'))
                    .filter(e=>e.offsetParent && /^确定/.test((e.innerText||'').trim()) && (e.innerText||'').trim().length<=8);
                  if(btns.length){ btns[btns.length-1].click(); }
                }""")
            self.page.wait_for_timeout(1500)
            return True
        except Exception:
            return False

    def apply_search_filters(self, *, city: str = "", min_education: str = "", min_experience_years: int = 0) -> dict:
        """按画像在搜索源头设置筛选条件。返回实际应用的项（供进度提示）。年龄走引擎精确判定，不在此粗筛。"""
        applied: dict[str, str] = {}
        if city:
            if self.set_city(city):
                applied["city"] = city
        edu_map = {"大专": "大专及以上", "专科": "大专及以上", "本科": "本科及以上",
                   "硕士": "硕士及以上", "研究生": "硕士及以上", "博士": "硕士及以上"}
        edu_opt = edu_map.get((min_education or "").strip())
        if edu_opt and self._click_filter_option("学历要求", edu_opt):
            applied["education"] = edu_opt
            self.page.wait_for_timeout(1500)
        if min_experience_years and min_experience_years > 0:
            exp_opt = "1-3年" if min_experience_years <= 3 else ("3-5年" if min_experience_years <= 5 else "5-10年")
            if self._click_filter_option("经验要求", exp_opt):
                applied["experience"] = exp_opt
                self.page.wait_for_timeout(1500)
        return applied

    # ---- 完整简历详情抓取（"会看简历"的核心）----

    def _extract_resume_text(self) -> str:
        """取当前简历弹窗正文（不等待）。"""
        try:
            return self.page.evaluate(
                """() => {
                  const el = document.querySelector('.resume-content-new')
                    || document.querySelector('.resume-detail')
                    || document.querySelector('.new-resume-detail')
                    || document.querySelector('.km-modal__body');
                  return el ? (el.innerText || '') : '';
                }""") or ""
        except Exception:
            return ""

    def _open_resume_modal(self, card, timeout: int = 9000) -> bool:
        """点击候选人卡片打开简历弹窗，并**轮询直到正文真正加载**（外壳先出现、内容异步填充）。
        返回是否成功拿到有内容的简历。"""
        import time as _time
        try:
            target = card.query_selector(".talent-basic-info__name") or card
            target.click()
        except Exception:
            return False
        # 先等外壳出现
        try:
            self.page.wait_for_selector(".resume-content-new, .resume-detail, .new-resume-detail",
                                        timeout=timeout)
        except Exception:
            pass
        # 再轮询正文加载（外壳出现≠内容就绪）
        deadline = _time.time() + timeout / 1000
        while _time.time() < deadline:
            if len(self._extract_resume_text()) > 120:
                return True
            try:
                self.page.wait_for_timeout(300)
            except Exception:
                break
        return len(self._extract_resume_text()) > 40

    def _scrape_open_resume(self) -> str:
        """抓取当前打开的简历弹窗全文（滚动触发懒加载后取全文）。"""
        try:
            self.page.evaluate(
                """() => {
                  const c = document.querySelector('.resume-detail, .new-resume-detail, .km-modal__body');
                  if (c) { c.scrollTop = c.scrollHeight; }
                }""")
            self.page.wait_for_timeout(500)
        except Exception:
            pass
        return self._extract_resume_text()

    def _close_resume_modal(self) -> None:
        """关闭简历弹窗（ESC 优先，兜底点关闭按钮），保证回到列表页。"""
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(600)
        except Exception:
            pass
        try:
            if self.page.query_selector(".km-modal--open"):
                x = (self.page.query_selector(".km-modal__close")
                     or self.page.query_selector(".km-modal--open [class*=close]")
                     or self.page.query_selector(".new-shortcut-resume [class*=close]"))
                if x:
                    x.click()
                    self.page.wait_for_timeout(500)
        except Exception:
            pass

    def scrape_candidate_detail(self, card) -> str:
        """对单张卡片：打开简历弹窗→抓全文→关闭。失败返回空串（不影响卡片数据）。
        检测到'查看简历次数已用完'时置额度耗尽标志并返回空（外层据此停止深读）。"""
        opened = self._open_resume_modal(card)
        if not opened:
            self._close_resume_modal()
            return ""
        try:
            text = self._scrape_open_resume()
        finally:
            self._close_resume_modal()
        # 检测简历查看额度耗尽：抓到的是提示语而非简历
        if text and ("次数已用完" in text or "开通权益" in text or "查看简历次数" in text):
            self._resume_quota_exhausted = True
            return ""
        try:
            self.page.wait_for_timeout(300)
        except Exception:
            pass
        return text or ""

    def _attach_resume_list_listener(self) -> None:
        """拦截搜索接口 /talent/search/list，拿到每个候选人的 resumeNumber 和证书。
        智联候选人卡片是纯 JS 按钮、DOM 里没有主页链接，唯一标识只在接口 JSON 里。
        存：_api_by_name（姓名→resumeNumber队列→联系本人）、_api_ordered（按顺序→定位卡片）、
        _api_certs（姓名→证书队列，卡片阶段就白拿证书，不用花额度深读）。"""
        def _on_response(resp) -> None:
            try:
                if "talent/search/list" in resp.url and "json" in resp.headers.get("content-type", ""):
                    data = json.loads(resp.body())
                    lst = (data.get("data") or {}).get("list") or []
                    byname: dict[str, list[str]] = {}
                    certs_byname: dict[str, list[list[str]]] = {}
                    ordered: list[str] = []
                    for item in lst:
                        name = (item.get("userName") or "").strip()
                        rn = (item.get("resumeNumber") or "").strip()
                        certs = [str(c).strip() for c in (item.get("certificateNames") or []) if str(c).strip()]
                        if rn:
                            ordered.append(rn)
                        if name and rn:
                            byname.setdefault(name, []).append(rn)
                            certs_byname.setdefault(name, []).append(certs)
                    if ordered:
                        self._api_by_name = byname
                        self._api_ordered = ordered
                        self._api_certs = certs_byname
            except Exception:
                pass
        self.page.on("response", _on_response)

    def _take_resume_number(self, name: str) -> str:
        """按姓名取一个 resumeNumber（同名按出现顺序消耗）。"""
        name = (name or "").strip()
        if not name:
            return ""
        queue = self._api_by_name.get(name)
        if queue:
            return queue.pop(0)
        return ""

    def _take_certs(self, name: str) -> list[str]:
        """按姓名取一份证书列表（与 resumeNumber 同一顺序消耗，保持对齐）。"""
        name = (name or "").strip()
        if not name:
            return []
        queue = self._api_certs.get(name)
        if queue:
            return queue.pop(0)
        return []

    def search_and_scrape_controlled(
        self,
        keyword: str,
        *,
        max_pages: int = 5,
        max_count: int = 200,
        start_page: int = 1,
        on_progress: Callable[[int, int], None] | None = None,
        on_checkpoint: Callable[[int, int], None] | None = None,
        on_page: Callable[[int, list], None] | None = None,
        control: Callable[[str, int, int], None] | None = None,
        filters: dict[str, Any] | None = None,
        fetch_detail: bool = False,
        max_detail: int = 25,
        score_fn: Callable[[dict], float] | None = None,
        detail_filter: Callable[[dict], bool] | None = None,
    ) -> list[dict[str, Any]]:
        def check(stage: str, page_no: int, count: int) -> None:
            if control:
                control(stage, page_no, count)

        check("before_search", 0, 0)
        self._resume_quota_exhausted = False  # 每轮重置（额度是按天的，但本轮内一旦耗尽即停）
        detail_count = 0
        # 拦搜索接口 /talent/search/list，拿到每个候选人的 resumeNumber（联系本人要靠它）
        self._api_by_name: dict[str, list[str]] = {}
        try:
            self._attach_resume_list_listener()
        except Exception:
            pass
        self.do_search(keyword)
        # 源头筛选：设置城市/学历/经验，让搜索结果本身就匹配画像
        if filters:
            try:
                self.apply_search_filters(
                    city=str(filters.get("city", "") or ""),
                    min_education=str(filters.get("min_education", "") or ""),
                    min_experience_years=int(filters.get("min_experience_years", 0) or 0),
                )
                self.page.wait_for_timeout(2000)
            except Exception:
                pass
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for skipped in range(1, max(1, start_page)):
            check("skip_to_checkpoint", skipped, 0)
            if not self._goto_next_page():
                break

        for page_no in range(max(1, start_page), max_pages + 1):
            check("before_page", page_no, len(candidates))
            selector = self._wait_for_search_cards(timeout=15000)
            if not selector:
                if page_no == max(1, start_page):
                    raise RuntimeError(
                        "SEARCH_RESULTS_SELECTOR_MISSING: 未发现搜索结果卡片，可能是页面改版、账号限制或搜索未成功"
                    )
                break
            cards = self.page.query_selector_all(selector)
            page_new: list[dict[str, Any]] = []
            page_idx: list[int] = []
            for idx, card in enumerate(cards):
                check("before_candidate", page_no, len(candidates))
                candidate = self._parse_search_card(card)
                if not candidate:
                    continue
                key = _candidate_dedup_key(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                # 挂上 resumeNumber（联系本人的唯一标识）
                rn = self._take_resume_number(candidate.get("name"))
                if rn:
                    candidate["resume_number"] = rn
                    candidate["platform_uid"] = rn
                # 合并接口里的证书（卡片不展示证书，接口 certificateNames 能白拿一部分）
                api_certs = self._take_certs(candidate.get("name"))
                if api_certs:
                    existing = [c for c in (candidate.get("certificates") or "").split("、") if c]
                    for c in api_certs:
                        if c not in existing:
                            existing.append(c)
                    candidate["certificates"] = "、".join(existing)
                candidates.append(candidate)
                page_new.append(candidate)
                page_idx.append(idx)
                if on_progress:
                    on_progress(len(candidates), page_no)
                if len(candidates) >= max_count:
                    break
            # 深度筛选：逐人打开简历弹窗抓全文（让智能体真正"看简历"）
            # 额度保护：查看完整简历消耗智联每日额度——一旦耗尽或达本轮上限即停，不浪费
            # 稀缺额度优先给高分者：有评分函数时按我方匹配分降序深读，而非智联默认顺序
            if fetch_detail and page_new and not self._resume_quota_exhausted and detail_count < max_detail:
                ordered = list(zip(page_new, page_idx))
                if score_fn:
                    try:
                        ordered.sort(key=lambda pair: -(score_fn(pair[0]) or 0))
                    except Exception:
                        pass
                for cand, cidx in ordered:
                    if self._resume_quota_exhausted or detail_count >= max_detail:
                        break
                    # 两段漏斗门禁：硬冲突（明确不达标）的人跳过，不浪费看简历额度
                    if detail_filter is not None:
                        try:
                            if not detail_filter(cand):
                                continue
                        except Exception:
                            pass
                    check("before_detail", page_no, len(candidates))
                    try:
                        fresh = self.page.query_selector_all(selector)
                        if cidx < len(fresh):
                            text = self.scrape_candidate_detail(fresh[cidx])
                            detail_count += 1
                            if text and len(text) > len(cand.get("text", "") or ""):
                                cand["full_text"] = text
                                # 从完整简历提取证书（卡片上没有"证书"栏，只有全文有）并合并
                                try:
                                    from searcher import _extract_certificates as _ec
                                    certs = _ec(text)
                                    if certs:
                                        existing = [c for c in (cand.get("certificates") or "").split("、") if c]
                                        for c in certs.split("、"):
                                            if c and c not in existing:
                                                existing.append(c)
                                        cand["certificates"] = "、".join(existing)
                                except Exception:
                                    pass
                            # 深读间隔抖动：查看完整简历是最耗额度、最易触发风控的动作，模拟真人节奏
                            import random as _rnd
                            self.page.wait_for_timeout(1200 + _rnd.randint(0, 1500))
                    except Exception:
                        pass
            if on_page and page_new:
                on_page(page_no, page_new)
            if on_checkpoint:
                on_checkpoint(page_no, len(candidates))
            check("after_page", page_no, len(candidates))
            if len(candidates) >= max_count or not self._goto_next_page():
                break
        return candidates


_SEARCH_URL = "https://rd6.zhaopin.com/app/search"


def _contact_log(msg: str) -> None:
    import os as _os, time as _t
    try:
        p = _os.path.join(_os.environ.get("TEMP", "."), "_contact_debug.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (_t.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def open_candidate_contact(resume_number: str, keyword: str, filters: dict | None = None, max_pages: int = 8) -> None:
    """在【可见、已登录】的智联窗口里打开指定候选人的简历卡（上面有"打招呼/打电话"按钮），
    供招聘人直接联系本人。智联没有干净的主页链接（详情要当次有效的加密串 resumeK/resumeT，
    不能存下来复用），所以做法是：用和当初筛选【相同】的关键词+筛选条件重搜 → 拦接口按
    resumeNumber 定位到第几张卡片（DOM 顺序与接口顺序一致，已验证）→ 点开简历弹窗 → 窗口保持打开。
    在独立线程里跑，不占用主浏览器/不自动发消息（避免封号）。
    """
    import threading
    _contact_log("open_candidate_contact 被调用，准备启动线程")

    def _run() -> None:
        import time as _t
        _contact_log("=== 联系流程 _run 开始执行 ===")  # 裸日志，不带格式化，排除格式化异常
        try:
            _contact_log("参数 resumeNumber=%s keyword=%s" % (str(resume_number)[:16], str(keyword)))
            bot = ProductCandidateSearcher({"browser_visible": True, "browser_mode": "managed"})
            bot.launch()
            _contact_log("浏览器启动成功 mode=%s" % bot.active_browser_mode)
            page = bot.page
            page.goto(_SEARCH_URL, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            _contact_log("已到搜索页 url=%s" % page.url[:50])
            try:
                bot._attach_resume_list_listener()
            except Exception as e:
                _contact_log("挂监听器失败: %s" % e)
            bot.do_search(keyword)
            _contact_log("搜索完成")
            # 关键：用和当初筛选【相同】的筛选条件重搜，才能把那个人重新搜到、序号才对得上
            # 注意：不能写 filters = filters or {} —— 会把闭包参数遮蔽成未赋值的局部变量
            flt = dict(filters or {})
            if flt.get("city") or flt.get("min_education") or flt.get("min_experience_years"):
                try:
                    bot.apply_search_filters(
                        city=flt.get("city") or "",
                        min_education=flt.get("min_education") or "",
                        min_experience_years=int(flt.get("min_experience_years") or 0),
                    )
                    page.wait_for_timeout(2500)  # 等筛选后的新搜索接口返回
                    _contact_log("筛选已应用")
                except Exception as e:
                    _contact_log("筛选失败: %s" % e)
            found = False
            for pno in range(max_pages):
                selector = bot._wait_for_search_cards(timeout=12000)
                if not selector:
                    _contact_log("第%d页: 没有卡片选择器，停" % (pno + 1))
                    break
                ordered = getattr(bot, "_api_ordered", []) or []
                _contact_log("第%d页: 接口捕获%d个resumeNumber, 目标%s 在里面=%s" % (
                    pno + 1, len(ordered), resume_number[:12], resume_number in ordered))
                if resume_number in ordered:
                    idx = ordered.index(resume_number)
                    cards = page.query_selector_all(selector)
                    _contact_log("目标在第%d页第%d张，页面卡片数=%d" % (pno + 1, idx, len(cards)))
                    if idx < len(cards):
                        try:
                            cards[idx].scroll_into_view_if_needed()
                        except Exception:
                            pass
                        try:
                            found = bool(bot._open_resume_modal(cards[idx]))
                            _contact_log("打开简历弹窗结果=%s" % found)
                        except Exception as e:
                            found = True
                            _contact_log("打开弹窗异常但已点击: %s" % e)
                        break
                if not bot._goto_next_page():
                    _contact_log("第%d页后无下一页" % (pno + 1))
                    break
            _contact_log("查找结束 found=%s" % found)
            # 打开后把窗口提到最前，确保用户看到本人简历卡（含打招呼/打电话按钮）
            try:
                page.bring_to_front()
            except Exception as e:
                _contact_log("置顶失败: %s" % e)
            if found:
                try:
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
            # 无论是否定位到，都保持窗口打开（用户可自行在智联里操作），直到用户关窗
            _contact_log("进入窗口保持")
            while bot._context is not None and bot._context.pages:
                _t.sleep(1)
        except Exception as e:
            import traceback
            _contact_log("!!! 联系流程异常: %s\n%s" % (e, traceback.format_exc()[-400:]))
        finally:
            _contact_log("联系流程结束")
            try:
                bot._pw.stop()
            except Exception:
                pass

    _t = threading.Thread(target=_run, daemon=True)
    _t.start()
    _contact_log("线程已 start，alive=%s" % _t.is_alive())
