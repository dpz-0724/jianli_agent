# -*- coding: utf-8 -*-
"""UI layout mixin."""
from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from .models import CandidateStage


class UILayoutMixin:

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Microsoft YaHei UI", 9))
        style.configure("Treeview", rowheight=29)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 7))

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(14, 9))
        header.pack(fill="x")
        ttk.Label(header, text="招聘自动化工作台", font=("Microsoft YaHei UI", 18, "bold")).pack(side="left")
        ttk.Label(header, text="岗位中心 · 证据化评估 · 人工复核", foreground="#667085").pack(side="left", padx=16)
        self.global_status = tk.StringVar(value="就绪")
        ttk.Label(header, textvariable=self.global_status, foreground="#175CD3").pack(side="right")

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        left, right = ttk.Frame(panes, padding=7), ttk.Frame(panes, padding=(7, 0, 0, 0))
        panes.add(left, weight=1)
        panes.add(right, weight=5)

        job_bar = ttk.Frame(left)
        job_bar.pack(fill="x", pady=(0, 7))
        ttk.Button(job_bar, text="新建岗位", command=self.new_job).pack(side="left")
        ttk.Button(job_bar, text="刷新", command=self.refresh_jobs).pack(side="left", padx=5)
        ttk.Button(job_bar, text="归档", command=self.archive_job).pack(side="right")
        self.job_tree = ttk.Treeview(left, columns=("job", "count"), show="headings", selectmode="browse")
        self.job_tree.heading("job", text="岗位")
        self.job_tree.heading("count", text="候选人")
        self.job_tree.column("job", width=205, anchor="w")
        self.job_tree.column("count", width=65, anchor="center")
        self.job_tree.pack(fill="both", expand=True)
        self.job_tree.bind("<<TreeviewSelect>>", self._job_selected)

        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        self.profile_tab, self.candidate_tab, self.run_tab = (ttk.Frame(self.tabs, padding=11) for _ in range(3))
        self.tabs.add(self.profile_tab, text="岗位要求与搜索")
        self.tabs.add(self.candidate_tab, text="候选人复核")
        self.tabs.add(self.run_tab, text="任务与异常")
        self._build_profile_tab()
        self._build_candidate_tab()
        self._build_run_tab()

    def _build_profile_tab(self) -> None:
        form = ttk.LabelFrame(self.profile_tab, text="岗位画像（解析结果须由招聘人员确认）", padding=10)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        self.title_var, self.keyword_var = tk.StringVar(), tk.StringVar()
        self.edu_var, self.exp_var, self.location_var = tk.StringVar(value="不限"), tk.StringVar(value="0"), tk.StringVar()
        fields = (("岗位名称", self.title_var), ("搜索关键词", self.keyword_var))
        for index, (label, variable) in enumerate(fields):
            column = index * 2
            ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", pady=4)
            ttk.Entry(form, textvariable=variable).grid(row=0, column=column + 1, sticky="ew", padx=(7, 18 if index == 0 else 0))
        ttk.Label(form, text="最低学历").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(form, textvariable=self.edu_var, values=("不限", "高中", "大专", "本科", "硕士", "博士"), state="readonly").grid(row=1, column=1, sticky="ew", padx=(7, 18))
        ttk.Label(form, text="最低经验（年）").grid(row=1, column=2, sticky="w")
        ttk.Spinbox(form, from_=0, to=30, textvariable=self.exp_var).grid(row=1, column=3, sticky="ew", padx=(7, 0))
        ttk.Label(form, text="工作地点").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.location_var).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(7, 0))
        ttk.Label(form, text="岗位 JD").grid(row=3, column=0, sticky="nw", pady=4)
        self.jd_text = scrolledtext.ScrolledText(form, height=10, wrap="word")
        self.jd_text.grid(row=3, column=1, columnspan=3, sticky="nsew", padx=(7, 0))

        bar = ttk.Frame(self.profile_tab, padding=(0, 9))
        bar.pack(fill="x")
        ttk.Button(bar, text="解析并保存", style="Primary.TButton", command=self.save_profile).pack(side="left")
        ttk.Button(bar, text="重新评估", command=self.reassess).pack(side="left", padx=6)
        self.search_btn = ttk.Button(bar, text="开始智联搜索", style="Primary.TButton", command=self.start_search)
        self.search_btn.pack(side="left", padx=(16, 0))
        self.login_btn = ttk.Button(bar, text="登录完成，继续", command=self.continue_login, state="disabled")
        self.login_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="导入演示数据", command=self.import_demo).pack(side="right")

        self.profile_summary = tk.StringVar(value="请先创建岗位。")
        ttk.Label(self.profile_tab, textvariable=self.profile_summary, wraplength=1000, foreground="#344054").pack(fill="x", pady=8)
        self.progress = ttk.Progressbar(self.profile_tab, maximum=100)
        self.progress.pack(fill="x", pady=(10, 4))
        self.task_status = tk.StringVar(value="暂无运行任务")
        ttk.Label(self.profile_tab, textvariable=self.task_status, foreground="#175CD3").pack(anchor="w")
        self.stats_var = tk.StringVar()
        ttk.Label(self.profile_tab, textvariable=self.stats_var, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=12)

    def _build_candidate_tab(self) -> None:
        bar = ttk.Frame(self.candidate_tab)
        bar.pack(fill="x", pady=(0, 7))
        self.assess_filter, self.stage_filter, self.search_filter = tk.StringVar(value="ALL"), tk.StringVar(value="ALL"), tk.StringVar()
        ttk.Label(bar, text="评估").pack(side="left")
        assess = ttk.Combobox(bar, textvariable=self.assess_filter, values=("ALL", "PASS", "REVIEW", "CONFLICT"), state="readonly", width=11)
        assess.pack(side="left", padx=4)
        assess.bind("<<ComboboxSelected>>", lambda _event: self.refresh_candidates())
        ttk.Label(bar, text="阶段").pack(side="left", padx=(10, 0))
        stage = ttk.Combobox(bar, textvariable=self.stage_filter, values=("ALL", *[item.value for item in CandidateStage]), state="readonly", width=14)
        stage.pack(side="left", padx=4)
        stage.bind("<<ComboboxSelected>>", lambda _event: self.refresh_candidates())
        entry = ttk.Entry(bar, textvariable=self.search_filter, width=26)
        entry.pack(side="left", padx=(10, 4))
        entry.bind("<Return>", lambda _event: self.refresh_candidates())
        ttk.Button(bar, text="搜索", command=self.refresh_candidates).pack(side="left")
        ttk.Button(bar, text="导出本岗位", command=self.export_job).pack(side="right")

        columns = ("assessment", "score", "name", "title", "location", "education", "experience", "stage", "owner")
        self.candidate_tree = ttk.Treeview(self.candidate_tab, columns=columns, show="headings", selectmode="browse")
        labels = ("评估", "匹配度", "姓名", "当前/期望职位", "地点", "学历", "经验", "招聘阶段", "负责人")
        widths = (90, 75, 105, 250, 90, 75, 100, 105, 90)
        for column, label, width in zip(columns, labels, widths):
            self.candidate_tree.heading(column, text=label)
            self.candidate_tree.column(column, width=width, anchor="w" if column in {"name", "title"} else "center")
        self.candidate_tree.pack(fill="both", expand=True)
        self.candidate_tree.bind("<Double-1>", lambda _event: self.review_candidate())
        actions = ttk.Frame(self.candidate_tab, padding=(0, 7))
        actions.pack(fill="x")
        ttk.Button(actions, text="查看并复核", style="Primary.TButton", command=self.review_candidate).pack(side="left")
        ttk.Button(actions, text="待联系", command=lambda: self.set_stage(CandidateStage.TO_CONTACT)).pack(side="left", padx=5)
        ttk.Button(actions, text="已联系", command=lambda: self.set_stage(CandidateStage.CONTACTED)).pack(side="left")
        ttk.Button(actions, text="人才库", command=lambda: self.set_stage(CandidateStage.TALENT_POOL)).pack(side="left", padx=5)

    def _build_run_tab(self) -> None:
        bar = ttk.Frame(self.run_tab)
        bar.pack(fill="x", pady=(0, 7))
        ttk.Button(bar, text="刷新任务", command=self.refresh_runs).pack(side="left")
        ttk.Button(bar, text="打开诊断目录", command=self.open_diagnostics).pack(side="left", padx=5)
        ttk.Button(bar, text="重置浏览器", command=lambda: self.worker.submit("RESET_BROWSER")).pack(side="left")
        columns = ("id", "status", "query", "found", "new", "started", "error")
        self.run_tree = ttk.Treeview(self.run_tab, columns=columns, show="headings", selectmode="browse")
        labels = ("任务ID", "状态", "搜索词", "发现", "新入池", "开始时间", "错误/诊断")
        widths = (70, 100, 170, 65, 70, 170, 410)
        for column, label, width in zip(columns, labels, widths):
            self.run_tree.heading(column, text=label)
            self.run_tree.column(column, width=width, anchor="w" if column == "error" else "center")
        self.run_tree.pack(fill="both", expand=True)
        self.run_tree.bind("<Double-1>", lambda _event: self.open_diagnostics())
        self.log_text = scrolledtext.ScrolledText(self.run_tab, height=8, state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill="x", pady=(8, 0))
