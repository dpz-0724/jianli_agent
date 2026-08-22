# -*- coding: utf-8 -*-
"""云只智联 · 候选人筛选排序工具（产品版 V3）。

产品定义（一句话）：HR 写下招聘要求，点「开始筛选」，软件自动从智联招聘
推荐人才流抓取候选人，按条件打分排序，产出可跟进的候选人名单。

两个主页面：
  ① 筛选：写条件（JD/关键词）+ 选条件（学历/经验/地点…）+ 开始筛选（进度全程可见）
  ② 候选人排序：按匹配度排序的结果 + 跟进标记 + 对比 + 导出
"""
import os
import sys
import json
import queue
import threading
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "code"))

from db import DB
from matcher import extract_keywords, rank_candidates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE_DIR, "config.ini")

PRIMARY = "#2C7BE5"
OK_GREEN = "#10A37F"
WARN_AMBER = "#F59E0B"
DANGER_RED = "#EF4444"
NEUTRAL = "#9CA3AF"

SCORE_LEVELS = [(70, OK_GREEN, "#E6F7EF"), (40, WARN_AMBER, "#FEF6E0"), (0, NEUTRAL, "#F3F4F6")]
STATUS_SET = ["待联系", "已联系", "已约面试", "不合适"]

EDU_ORDER = ["初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"]
EXP_ORDER = ["在校/应届", "一年以内", "1-3年", "3-5年", "5-10年", "10年以上"]


def load_config():
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG):
        cfg.read(CONFIG, encoding="utf-8")
    return cfg


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        cfg.write(f)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("云只智联 · 候选人筛选排序工具")
        self.geometry("1180x800")
        self.minsize(1000, 680)
        self._apply_style()

        self.db = DB()
        self.cfg = load_config()
        self.bot = None
        self.log_q = queue.Queue()
        self.ui_q = queue.Queue()

        self._build_stats_bar()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.filter_tab = FilterRunTab(self.nb, self)
        self.pool = PoolTab(self.nb, self)
        self.data = DataTab(self.nb, self)
        self.setting = SettingTab(self.nb, self)
        self.nb.add(self.filter_tab, text="  ① 筛选（填条件 → 开始）  ")
        self.nb.add(self.pool, text="  ② 候选人排序  ")
        self.nb.add(self.data, text="  采集数据  ")
        self.nb.add(self.setting, text="  设置  ")

        self.after(100, self._poll)
        self.refresh_stats()
        self.log("欢迎使用。三步走：1) 粘贴岗位JD或填关键词  2) 勾选筛选条件  3) 点「开始筛选」")
        self.log("没有智联账号？勾选「演示模式」可体验完整流程")

    # ---------- 样式 ----------
    def _apply_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", font=("Microsoft YaHei", 9))
        st.configure("Treeview", rowheight=26, font=("Microsoft YaHei", 9))
        st.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"), foreground="#374151")
        st.configure("TButton", padding=(8, 3))
        st.configure("Big.TButton", font=("Microsoft YaHei", 12, "bold"), padding=(24, 8))
        st.configure("TLabelframe.Label", foreground=PRIMARY, font=("Microsoft YaHei", 9, "bold"))

    def _build_stats_bar(self):
        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill="x")
        self.stat_total = tk.StringVar(value="候选人 0")
        self.stat_high = tk.StringVar(value="高匹配 0")
        self.stat_contacted = tk.StringVar(value="已跟进 0")
        self.stat_avg = tk.StringVar(value="平均分 0")
        for var in (self.stat_total, self.stat_high, self.stat_contacted, self.stat_avg):
            ttk.Label(bar, textvariable=var, font=("Microsoft YaHei", 10, "bold")).pack(side="left", padx=12)
        ttk.Separator(self, orient="horizontal").pack(fill="x")

    def refresh_stats(self):
        s = self.db.stats()
        self.stat_total.set(f"候选人 {s['total']}")
        self.stat_high.set(f"高匹配(≥70) {s['high']}")
        self.stat_contacted.set(f"已跟进 {s['contacted']}")
        self.stat_avg.set(f"平均分 {s['avg']}")

    def log(self, msg):
        self.log_q.put(msg)

    def ui(self, fn):
        """线程安全：后台线程把 UI 操作投递到主线程执行。"""
        self.ui_q.put(fn)

    def _poll(self):
        while True:
            try:
                fn = self.ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
            except queue.Empty:
                break
        while True:
            try:
                self.filter_tab.log_area.configure(state="normal")
                self.filter_tab.log_area.insert("end", self.log_q.get_nowait() + "\n")
                self.filter_tab.log_area.configure(state="disabled")
                self.filter_tab.log_area.see("end")
            except queue.Empty:
                break
        self.after(100, self._poll)

    def get_bot(self):
        from searcher import CandidateSearcher
        if self.bot is None:
            cfg = {
                "hide_browser": self.cfg.getboolean("global", "hide_browser", fallback=False),
                "chrome_path": self.cfg.get("global", "chrome_path", fallback="") or None,
            }
            self.bot = CandidateSearcher(cfg, self.db)
            self.bot.launch()
        return self.bot

    def get_filters(self):
        return self.filter_tab.collect()

    def rank_pool(self, kws, filters):
        rows = self.db.query("SELECT * FROM candidates")
        if not rows:
            return 0
        cols = [c[1] for c in self.db.conn.execute("PRAGMA table_info(candidates)").fetchall()]
        cands = [dict(zip(cols, r)) for r in rows]
        ranked = rank_candidates(cands, kws, filters)
        for c in ranked:
            self.db.conn.execute(
                "UPDATE candidates SET score=?, rank=?, detail=? WHERE id=?",
                (c["_score"], c["_rank"], json.dumps(c["_detail"], ensure_ascii=False), c["id"]))
        self.db.conn.commit()
        return len(ranked)


# ======================================================================
# 页面 ① 筛选：写条件 + 选条件 + 开始筛选（进度可见）
# ======================================================================
class FilterRunTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self._running = False

        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(self, width=430)
        right.pack(side="right", fill="both", padx=(8, 0))
        right.pack_propagate(False)

        # ---------- 第 1 步：岗位要求 ----------
        s1 = ttk.LabelFrame(left, text="第 1 步 · 你要招什么人（写条件）")
        s1.pack(fill="x", pady=4)
        m = ttk.Frame(s1); m.pack(fill="x", padx=8, pady=6)
        ttk.Label(m, text="关键词:").grid(row=0, column=0, sticky="w", pady=3)
        self.kw_var = tk.StringVar()
        ttk.Entry(m, textvariable=self.kw_var, width=46).grid(row=0, column=1, sticky="w")
        ttk.Label(m, text="（空格/逗号分隔，如：Java 销售）").grid(row=0, column=2, sticky="w", padx=6)
        ttk.Label(m, text="岗位 JD:").grid(row=1, column=0, sticky="nw", pady=3)
        self.jd_text = tk.Text(m, height=5, width=46, font=("Microsoft YaHei", 10), wrap="word")
        self.jd_text.grid(row=1, column=1, columnspan=2, sticky="we", pady=3)
        jb = ttk.Frame(m); jb.grid(row=2, column=1, columnspan=2, sticky="w", pady=2)
        ttk.Button(jb, text="解析 JD 并自动填条件", command=self.do_parse_jd).pack(side="left")
        self.parse_label = tk.StringVar(value="")
        ttk.Label(jb, textvariable=self.parse_label, foreground=PRIMARY,
                  font=("Microsoft YaHei", 8), wraplength=430).pack(side="left", padx=8)

        # ---------- 第 2 步：筛选条件 ----------
        s2 = ttk.LabelFrame(left, text="第 2 步 · 筛人条件（选条件，留空=不限）")
        s2.pack(fill="x", pady=4)

        edu = ttk.Frame(s2); edu.pack(fill="x", padx=8, pady=3)
        ttk.Label(edu, text="学历 ≥").pack(side="left")
        self.edu_vars = {}
        for lab in EDU_ORDER:
            self.edu_vars[lab] = tk.BooleanVar(value=False)
            ttk.Checkbutton(edu, text=lab, variable=self.edu_vars[lab]).pack(side="left", padx=4)

        exp = ttk.Frame(s2); exp.pack(fill="x", padx=8, pady=3)
        ttk.Label(exp, text="经验 ≥").pack(side="left")
        self.exp_vars = {}
        for lab in EXP_ORDER:
            self.exp_vars[lab] = tk.BooleanVar(value=False)
            ttk.Checkbutton(exp, text=lab, variable=self.exp_vars[lab]).pack(side="left", padx=4)

        row3 = ttk.Frame(s2); row3.pack(fill="x", padx=8, pady=3)
        ttk.Label(row3, text="地点含").pack(side="left")
        self.loc_var = tk.StringVar()
        ttk.Entry(row3, textvariable=self.loc_var, width=20).pack(side="left", padx=4)
        ttk.Label(row3, text="年龄").pack(side="left", padx=(12, 2))
        self.age_min = tk.StringVar(); self.age_max = tk.StringVar()
        ttk.Entry(row3, textvariable=self.age_min, width=4).pack(side="left")
        ttk.Label(row3, text="~").pack(side="left", padx=2)
        ttk.Entry(row3, textvariable=self.age_max, width=4).pack(side="left")
        ttk.Label(row3, text="岁").pack(side="left", padx=2)
        ttk.Label(row3, text="性别").pack(side="left", padx=(12, 2))
        self.sex_var = tk.StringVar(value="不限")
        for lab in ("不限", "男", "女"):
            ttk.Radiobutton(row3, text=lab, value=lab, variable=self.sex_var).pack(side="left", padx=2)
        ttk.Label(row3, text="活跃度 ≥").pack(side="left", padx=(12, 2))
        self.act_var = tk.StringVar(value="不限")
        for lab in ("不限", "在线", "刚刚活跃", "今日活跃", "本周活跃"):
            ttk.Radiobutton(row3, text=lab, value=lab, variable=self.act_var).pack(side="left", padx=2)

        # 预设
        ps = ttk.Frame(s2); ps.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Button(ps, text="存为预设", command=self._save_preset).pack(side="left")
        ttk.Label(ps, text="加载预设:").pack(side="left", padx=(10, 2))
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(ps, textvariable=self.preset_var, width=16, state="readonly")
        self.preset_cb.pack(side="left", padx=2)
        self.preset_cb.bind("<<ComboboxSelected>>", self._load_preset)
        self._refresh_presets()

        # ---------- 第 3 步：开始筛选 ----------
        s3 = ttk.LabelFrame(left, text="第 3 步 · 开始筛选")
        s3.pack(fill="x", pady=4)
        run = ttk.Frame(s3); run.pack(fill="x", padx=8, pady=8)
        self.start_btn = ttk.Button(run, text="▶  开 始 筛 选", style="Big.TButton",
                                    command=self.start_filter)
        self.start_btn.pack(side="left", padx=6)
        self.demo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(run, text="演示模式（不登录，用模拟数据体验）",
                        variable=self.demo_var).pack(side="left", padx=10)
        ttk.Button(run, text="复查登录状态", command=self.recheck_login).pack(side="left", padx=6)

        prog = ttk.Frame(s3); prog.pack(fill="x", padx=8, pady=(0, 8))
        self.progress_bar = ttk.Progressbar(prog, maximum=100, value=0)
        self.progress_bar.pack(fill="x", pady=(0, 4))
        self.status_var = tk.StringVar(value="就绪：填好条件后点「开始筛选」")
        ttk.Label(prog, textvariable=self.status_var, foreground=PRIMARY,
                  font=("Microsoft YaHei", 10, "bold")).pack(anchor="w")

        # ---------- 右侧：日志 ----------
        logf = ttk.LabelFrame(right, text="筛选过程（实时）")
        logf.pack(fill="both", expand=True)
        self.log_area = scrolledtext.ScrolledText(logf, state="disabled", font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, padx=6, pady=6)

        self._load_filters_cfg()

    # ---------- 条件 读取/填充 ----------
    def collect(self):
        f = {}
        edu = [k for k, v in self.edu_vars.items() if v.get()]
        if edu:
            f["education"] = edu
        if self.sex_var.get() != "不限":
            f["gender"] = self.sex_var.get()
        amin, amax = self.age_min.get().strip(), self.age_max.get().strip()
        if amin or amax:
            f["age_min"] = amin or "0"
            f["age_max"] = amax or "100"
        exp = [k for k, v in self.exp_vars.items() if v.get()]
        if exp:
            f["experience"] = exp
        if self.act_var.get() != "不限":
            f["activity"] = self.act_var.get()
        if self.loc_var.get().strip():
            f["location"] = self.loc_var.get().strip()
        return f

    def _load_filters_cfg(self):
        cfg = self.app.cfg
        for lab in self.edu_vars:
            self.edu_vars[lab].set(lab in cfg.get("filter", "education", fallback=""))
        self.sex_var.set(cfg.get("filter", "gender", fallback="不限"))
        self.age_min.set(cfg.get("filter", "age_min", fallback=""))
        self.age_max.set(cfg.get("filter", "age_max", fallback=""))
        for lab in self.exp_vars:
            self.exp_vars[lab].set(lab in cfg.get("filter", "experience", fallback=""))
        self.act_var.set(cfg.get("filter", "activity", fallback="不限"))
        self.loc_var.set(cfg.get("filter", "location", fallback=""))

    def _save_filters_cfg(self):
        cfg = self.app.cfg
        d = self.collect()
        if not cfg.has_section("filter"):
            cfg.add_section("filter")
        cfg.set("filter", "education", "|".join(d.get("education", [])))
        cfg.set("filter", "gender", self.sex_var.get())
        cfg.set("filter", "age_min", self.age_min.get())
        cfg.set("filter", "age_max", self.age_max.get())
        cfg.set("filter", "experience", "|".join(d.get("experience", [])))
        cfg.set("filter", "activity", self.act_var.get())
        cfg.set("filter", "location", self.loc_var.get())
        save_config(cfg)

    def apply_hard(self, hard):
        if hard.get("education") and hard["education"] in EDU_ORDER:
            idx = EDU_ORDER.index(hard["education"])
            for i, lab in enumerate(EDU_ORDER):
                self.edu_vars[lab].set(i >= idx)
        if hard.get("experience") and hard["experience"] in EXP_ORDER:
            idx = EXP_ORDER.index(hard["experience"])
            for i, lab in enumerate(EXP_ORDER):
                self.exp_vars[lab].set(i >= idx)
        if hard.get("location"):
            self.loc_var.set("、".join(hard["location"]))

    # ---------- 预设 ----------
    def _refresh_presets(self):
        names = self.app.cfg.options("presets") if self.app.cfg.has_section("presets") else []
        self.preset_cb["values"] = names

    def _save_preset(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("存为预设", "预设名称:", parent=self)
        if not name:
            return
        cfg = self.app.cfg
        if not cfg.has_section("presets"):
            cfg.add_section("presets")
        cfg.set("presets", name, json.dumps(self.collect(), ensure_ascii=False))
        save_config(cfg)
        self._refresh_presets()
        self.app.log(f"预设「{name}」已保存")

    def _load_preset(self, _e=None):
        name = self.preset_var.get()
        if not name or not self.app.cfg.has_section("presets"):
            return
        try:
            f = json.loads(self.app.cfg.get("presets", name))
            for lab in self.edu_vars:
                self.edu_vars[lab].set(lab in f.get("education", []))
            self.sex_var.set(f.get("gender", "不限"))
            self.age_min.set(f.get("age_min", ""))
            self.age_max.set(f.get("age_max", ""))
            for lab in self.exp_vars:
                self.exp_vars[lab].set(lab in f.get("experience", []))
            self.act_var.set(f.get("activity", "不限"))
            self.loc_var.set(f.get("location", ""))
            self.app.log(f"已加载预设「{name}」")
        except Exception as e:
            self.app.log(f"加载预设失败: {e}")

    # ---------- JD 解析 ----------
    def do_parse_jd(self):
        from jd_parser import parse_jd, summarize
        jd = self.jd_text.get("1.0", "end")
        if not jd.strip():
            self.app.log("请先粘贴岗位 JD")
            return
        try:
            p = parse_jd(jd)
            self.parse_label.set(summarize(p))
            self.app.log("JD 解析: " + summarize(p))
            if any(p["hard"].values()):
                self.apply_hard(p["hard"])
                self.app.log("已自动填好学历/经验/地点条件")
            else:
                self.app.log("未识别出硬性条件，请手动勾选")
        except Exception as e:
            self.app.log(f"JD 解析出错: {e}")

    # ---------- 开始筛选（核心流水线） ----------
    def start_filter(self):
        if self._running:
            self.app.log("筛选正在运行中，请等待完成")
            return
        snap = {
            "kw": self.kw_var.get(),
            "jd": self.jd_text.get("1.0", "end"),
            "filters": self.collect(),
            "demo": self.demo_var.get(),
        }
        self._save_filters_cfg()
        self._running = True
        self.app.ui(lambda: (self.start_btn.configure(state="disabled"),
                             self.progress_bar.configure(value=0)))
        threading.Thread(target=self._pipeline, args=(snap,), daemon=True).start()

    def _kws_from(self, snap):
        import re
        manual = [k.strip() for k in re.split(r"[\s,，、;；]+", snap["kw"]) if k.strip()]
        return extract_keywords(snap["jd"], manual)

    def _status(self, msg, pct=None):
        def upd():
            self.status_var.set(msg)
            if pct is not None:
                try:
                    self.progress_bar["value"] = pct
                except Exception:
                    pass
        self.app.ui(upd)
        self.app.log(msg)

    def _finish(self, ok_msg=None, fail_msg=None):
        if fail_msg:
            self._status(fail_msg)
        elif ok_msg:
            self._status(ok_msg, 100)
            self.app.ui(self.app.pool.refresh)
            self.app.ui(self.app.refresh_stats)
            self.app.ui(lambda: self.app.nb.select(self.app.pool))
        self._running = False
        self.app.ui(lambda: self.start_btn.configure(state="normal"))

    def _pipeline(self, snap):
        try:
            if snap["demo"]:
                from demo_data import gen_candidates
                self._status("演示模式：生成模拟候选人 ...", 15)
                cands = gen_candidates(40)
            else:
                kws_pre = self._kws_from(snap)
                kw_search = snap["kw"].strip() or (kws_pre[0] if kws_pre else "")
                if not kw_search:
                    self._finish(fail_msg="请先输入搜索关键词（如：Java / 销售 / 会计），或粘贴 JD 自动提取")
                    return
                self._status("① 正在启动浏览器（复用已保存的登录态）...", 8)
                try:
                    bot = self.app.get_bot()
                except Exception as e:
                    self._finish(fail_msg=f"浏览器启动失败：{e}（若有本工具之前打开的浏览器窗口，请先关闭再试）")
                    return
                self._status("② 正在进入智联招聘·搜索人才 ...", 20)
                try:
                    logged = bot.go_search()
                except Exception as e:
                    self._finish(fail_msg=f"访问智联招聘失败：{e}")
                    return
                if not logged:
                    try:
                        bot.mark_window()
                    except Exception:
                        pass
                    self._status("② 需要登录：请在标题带【云只智联】的浏览器窗口扫码/短信登录 ...", 25)
                    if not self._wait_login(bot, 300):
                        self._finish(fail_msg="等待登录超时。登录完成后请重新点「开始筛选」")
                        return
                    self._status("② 登录成功 ✓", 32)
                    try:
                        bot.go_search()
                    except Exception:
                        pass
                else:
                    self._status("② 已登录（上次登录态有效）✓", 32)
                self._status(f"③ 搜索『{kw_search}』并翻页抓取候选人 ...", 40)
                try:
                    cands = bot.search_and_scrape(
                        kw_search, max_pages=5, max_count=200,
                        on_progress=lambda n, p: self._status(f"③ 第 {p} 页 · 已发现 {n} 个候选人 ...", 40))
                except Exception as e:
                    self._finish(fail_msg=f"抓取候选人出错：{e}")
                    return
                if not cands:
                    self._finish(fail_msg=f"关键词『{kw_search}』未搜到候选人，请更换关键词再试")
                    return
            kws = self._kws_from(snap)
            self._status(f"④ 抓到 {len(cands)} 人 · 关键词 {kws} · 打分筛选中 ...", 70)
            ranked = rank_candidates(cands, kws, snap["filters"])
            for c in ranked:
                c["score"] = c["_score"]
                c["rank"] = c["_rank"]
                c["detail"] = json.dumps(c["_detail"], ensure_ascii=False)
            saved = self.app.db.save_candidates(ranked)
            self._status(f"⑤ 新入库 {saved} 人，正在对整个候选人池重新排序 ...", 85)
            total = self.app.rank_pool(kws, snap["filters"])
            high = self.app.db.stats()["high"]
            self._finish(ok_msg=f"✓ 筛选完成：{total} 人已按匹配度排序，高匹配(≥70) {high} 人 → 已切换到「候选人排序」页")
        except Exception as e:
            self._finish(fail_msg=f"筛选出错：{e}")

    def _wait_login(self, bot, timeout=300):
        import time
        deadline = time.time() + timeout
        while time.time() < deadline and self.app.bot is not None:
            try:
                if bot.is_logged_in():
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def recheck_login(self):
        def worker():
            if self.app.bot is None:
                self.app.log("还没启动过浏览器，直接点「开始筛选」即可（会自动打开并引导登录）")
                return
            try:
                ok = self.app.bot.is_logged_in()
            except Exception as e:
                self.app.log(f"复查失败: {e}")
                return
            self.app.log("✓ 已登录" if ok else "尚未登录：开始筛选时会自动引导登录")
        threading.Thread(target=worker, daemon=True).start()


# ======================================================================
# 页面 ② 候选人排序
# ======================================================================
class PoolTab(ttk.Frame):
    COLS = ("rank", "name", "title", "location", "education", "experience", "activity", "score", "status")

    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(bar, text="对比选中", command=self.compare).pack(side="left", padx=3)
        ttk.Label(bar, text="标记选中:").pack(side="left", padx=(10, 2))
        self.status_cb = ttk.Combobox(bar, values=STATUS_SET, width=8, state="readonly")
        self.status_cb.set(STATUS_SET[1])
        self.status_cb.pack(side="left", padx=2)
        ttk.Button(bar, text="应用", command=self.mark_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="清空池", command=self.clear).pack(side="left", padx=8)
        ttk.Button(bar, text="导出 CSV", command=self.export).pack(side="left", padx=3)
        ttk.Label(bar, text="双击看详情；颜色=匹配分(绿≥70/黄≥40/灰<40)").pack(side="left", padx=10)

        heads = {"rank": "排名", "name": "姓名", "title": "职位", "location": "地点",
                 "education": "学历", "experience": "经验", "activity": "活跃度",
                 "score": "匹配分", "status": "跟进状态"}
        self.tree = ttk.Treeview(self, columns=self.COLS, show="headings")
        for c in self.COLS:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=90, anchor="center")
        self.tree.column("name", width=100, anchor="w")
        self.tree.column("title", width=160, anchor="w")
        self.tree.column("score", width=70)
        self.tree.column("status", width=80)

        self.tree.tag_configure("hi", background="#E6F7EF")
        self.tree.tag_configure("mid", background="#FEF6E0")
        self.tree.tag_configure("lo", background="#F3F4F6")
        self.tree.tag_configure("st_contacted", foreground=PRIMARY)
        self.tree.tag_configure("st_interview", foreground=OK_GREEN)
        self.tree.tag_configure("st_bad", foreground=DANGER_RED)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.show_detail)
        self.refresh()

    def _tags(self, score, status):
        tags = []
        if score >= 70:
            tags.append("hi")
        elif score >= 40:
            tags.append("mid")
        else:
            tags.append("lo")
        if status == "已联系":
            tags.append("st_contacted")
        elif status == "已约面试":
            tags.append("st_interview")
        elif status == "不合适":
            tags.append("st_bad")
        return tags

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = self.app.db.query(
            "SELECT id, COALESCE(rank,0), name, title, location, education, experience, activity, "
            "COALESCE(score,0), status FROM candidates ORDER BY rank ASC, score DESC LIMIT 2000")
        for r in rows:
            cid, rank, name, title, loc, edu, exp, act, score, status = r
            self.tree.insert("", "end", iid=str(cid),
                             values=(rank, name, title, loc, edu, exp, act, score, status),
                             tags=self._tags(score, status))
        self.app.refresh_stats()

    def _selected_id(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def mark_selected(self):
        cid = self._selected_id()
        if not cid:
            messagebox.showinfo("提示", "请先在列表选中一名候选人")
            return
        status = self.status_cb.get()
        self.app.db.update_status(int(cid), status)
        self.refresh()
        self.app.log(f"候选人 ID={cid} 已标记为「{status}」")

    def compare(self):
        sel = self.tree.selection()
        if len(sel) < 2:
            messagebox.showinfo("提示", "请用 Ctrl/Shift 同时选中 2-3 名候选人再进行对比")
            return
        ids = [int(x) for x in sel[:3]]
        rows = self.app.db.query(
            "SELECT name,title,location,education,experience,age,activity,skills,text,score,status "
            "FROM candidates WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
        if not rows:
            messagebox.showinfo("提示", "未读取到候选人数据")
            return
        CompareDialog(self, rows)

    def show_detail(self, _e=None):
        cid = self._selected_id()
        if not cid:
            return
        rows = self.app.db.query(
            "SELECT name,title,location,education,experience,age,activity,skills,text,score,status,detail,source "
            "FROM candidates WHERE id=?", (int(cid),))
        if not rows:
            return
        (name, title, loc, edu, exp, age, act, skills, text, score, status, detail, source) = rows[0]
        dlg = tk.Toplevel(self)
        dlg.title(f"候选人详情 · {name}")
        dlg.geometry("560x540")
        dlg.transient(self)
        info = [("姓名", name), ("职位", title), ("地点", loc), ("学历", edu),
                ("经验", exp), ("年龄", str(age or "")), ("活跃度", act),
                ("匹配分", str(score)), ("跟进状态", status), ("来源", source)]
        box = ttk.Frame(dlg, padding=12)
        box.pack(fill="both", expand=True)
        for i, (k, v) in enumerate(info):
            ttk.Label(box, text=f"{k}:", foreground="#6B7280").grid(row=i, column=0, sticky="ne", pady=2, padx=4)
            ttk.Label(box, text=v or "-", font=("Microsoft YaHei", 10, "bold")).grid(row=i, column=1, sticky="w", pady=2)
        ttk.Label(box, text="匹配明细:").grid(row=len(info), column=0, sticky="ne", pady=(8, 2), padx=4)
        try:
            det = json.loads(detail or "{}")
            det_txt = "  ".join(f"{k}:{v}" for k, v in det.items())
        except Exception:
            det_txt = detail or "-"
        ttk.Label(box, text=det_txt, foreground=PRIMARY).grid(row=len(info), column=1, sticky="w", pady=(8, 2))
        ttk.Label(box, text="简历/技能:").grid(row=len(info) + 1, column=0, sticky="ne", pady=(8, 2), padx=4)
        txt = tk.Text(box, height=10, wrap="word", font=("Microsoft YaHei", 9))
        txt.insert("1.0", (text or "") + "\n\n技能: " + (skills or ""))
        txt.configure(state="disabled")
        txt.grid(row=len(info) + 1, column=1, sticky="we", pady=(8, 2))
        box.columnconfigure(1, weight=1)
        bar = ttk.Frame(dlg, padding=10)
        bar.pack(fill="x")
        for s in STATUS_SET:
            ttk.Button(bar, text=s, command=lambda s=s: self._set_and_close(int(cid), s, dlg)).pack(side="left", padx=4)
        ttk.Button(bar, text="关闭", command=dlg.destroy).pack(side="right", padx=4)

    def _set_and_close(self, cid, status, dlg):
        self.app.db.update_status(cid, status)
        self.refresh()
        dlg.destroy()
        self.app.log(f"候选人 ID={cid} 已标记为「{status}」")

    def clear(self):
        if messagebox.askyesno("确认", "清空候选人池？"):
            self.app.db.clear_candidates()
            self.refresh()
            self.app.log("候选人池已清空。")

    def export(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="candidates.csv")
        if p:
            import csv
            rows = self.app.db.query(
                "SELECT COALESCE(rank,0),name,title,location,education,experience,activity,COALESCE(score,0),status "
                "FROM candidates ORDER BY rank ASC LIMIT 5000")
            with open(p, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["排名", "姓名", "职位", "地点", "学历", "经验", "活跃度", "匹配分", "跟进状态"])
                w.writerows(rows)
            self.app.log(f"已导出 {p}")


class CompareDialog(tk.Toplevel):
    LABELS = [("name", "姓名"), ("title", "职位"), ("location", "地点"), ("education", "学历"),
              ("experience", "经验"), ("age", "年龄"), ("activity", "活跃度"),
              ("score", "匹配分"), ("status", "跟进状态"), ("text", "简历/技能")]
    IDX = {"name": 0, "title": 1, "location": 2, "education": 3, "experience": 4,
           "age": 5, "activity": 6, "skills": 7, "text": 8, "score": 9, "status": 10}

    def __init__(self, parent, rows):
        super().__init__(parent)
        self.title("候选人对比")
        n = len(rows)
        self.geometry(f"{min(350 * n + 170, 1100)}x640")
        self.transient(parent)
        bag = ttk.Frame(self, padding=12)
        bag.pack(fill="both", expand=True)
        best_i = max(range(len(rows)), key=lambda i: rows[i][9] or 0)
        ttk.Label(bag, text="字段", font=("Microsoft YaHei", 9, "bold")).grid(row=0, column=0, sticky="w", padx=8, pady=5)
        for j, r in enumerate(rows, 1):
            is_best = (j - 1 == best_i)
            head = ("★ " if is_best else "") + str(r[0] or "?")
            if is_best:
                head += "（最匹配）"
            ttk.Label(bag, text=head, font=("Microsoft YaHei", 10, "bold"),
                      foreground=OK_GREEN if is_best else "#111827").grid(row=0, column=j, sticky="w", padx=8, pady=5)
        for r_i, (key, label) in enumerate(self.LABELS, 1):
            ttk.Label(bag, text=label, foreground="#6B7280").grid(row=r_i, column=0, sticky="ne", padx=8, pady=3)
            for j, r in enumerate(rows, 1):
                is_best = (j - 1 == best_i)
                if key == "text":
                    content = (str(r[self.IDX["text"]] or "") + "\n\n技能: " + str(r[7] or ""))
                    txt = tk.Text(bag, height=6, width=30, wrap="word", font=("Microsoft YaHei", 8))
                    txt.insert("1.0", content)
                    txt.configure(state="disabled")
                    txt.grid(row=r_i, column=j, sticky="we", padx=8, pady=3)
                else:
                    val = r[self.IDX[key]]
                    disp = str(val) if (val is not None and val != "") else "—"
                    if key == "score" and is_best:
                        lb = ttk.Label(bag, text=disp, foreground=OK_GREEN, font=("Microsoft YaHei", 11, "bold"))
                    else:
                        lb = ttk.Label(bag, text=disp, font=("Microsoft YaHei", 9))
                    lb.grid(row=r_i, column=j, sticky="w", padx=8, pady=3)
            bag.rowconfigure(r_i, weight=1)
        ttk.Button(bag, text="关闭", command=self.destroy).grid(row=len(self.LABELS) + 1, column=0, columnspan=n + 1, pady=10)
        for c in range(n + 1):
            bag.columnconfigure(c, weight=1)


# ======================================================================
# 采集数据 / 设置
# ======================================================================
class DataTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(bar, text="去重", command=self.dedup).pack(side="left", padx=3)
        ttk.Button(bar, text="清空", command=self.clear).pack(side="left", padx=3)
        ttk.Button(bar, text="导出 CSV", command=self.export).pack(side="left", padx=3)
        ttk.Label(bar, text="（打招呼后采集到的微信/手机号）").pack(side="left", padx=8)
        cols = ("name", "phone", "wechat", "location", "source", "collected_at")
        heads = {"name": "姓名", "phone": "手机号", "wechat": "微信",
                 "location": "地点", "source": "来源", "collected_at": "采集时间"}
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=135)
        self.tree.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.app.db.query(
                "SELECT name,phone,wechat,location,source,collected_at FROM resumes ORDER BY id DESC LIMIT 2000"):
            self.tree.insert("", "end", values=r)

    def dedup(self):
        self.app.db.dedup(); self.refresh(); self.app.log("去重完成。")

    def clear(self):
        if messagebox.askyesno("确认", "清空全部采集数据？"):
            self.app.db.clear_db(); self.refresh(); self.app.log("已清空。")

    def export(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="resumes.csv")
        if p:
            self.app.db.export_csv(p); self.app.log(f"已导出 {p}")


class SettingTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        f = ttk.LabelFrame(self, text="运行设置")
        f.pack(fill="x", pady=4)
        g = ttk.Frame(f); g.pack(fill="x", padx=8, pady=8)
        ttk.Label(g, text="谷歌浏览器路径:").grid(row=0, column=0, sticky="w", pady=4)
        self.chrome_var = tk.StringVar(value=self.app.cfg.get(
            "global", "chrome_path", fallback="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"))
        ttk.Entry(g, textvariable=self.chrome_var, width=52).grid(row=0, column=1, pady=4)
        ttk.Button(g, text="浏览", command=self._browse).grid(row=0, column=2, padx=4)
        self.hide_var = tk.BooleanVar(value=self.app.cfg.getboolean("global", "hide_browser", fallback=False))
        ttk.Checkbutton(g, text="隐藏浏览器窗口（后台运行）", variable=self.hide_var).grid(
            row=1, column=1, sticky="w", pady=4)
        ttk.Button(g, text="保存设置", command=self.save).grid(row=2, column=1, sticky="w", pady=8)

    def _browse(self):
        p = filedialog.askopenfilename(title="选择 chrome.exe")
        if p:
            self.chrome_var.set(p)

    def save(self):
        cfg = self.app.cfg
        for sec, key, val in (("global", "chrome_path", self.chrome_var.get()),
                              ("global", "hide_browser", "true" if self.hide_var.get() else "false")):
            if not cfg.has_section(sec):
                cfg.add_section(sec)
            cfg.set(sec, key, val)
        save_config(cfg)
        self.app.log("设置已保存")


if __name__ == "__main__":
    App().mainloop()