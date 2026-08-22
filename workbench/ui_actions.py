# -*- coding: utf-8 -*-
"""UI action handlers."""
from __future__ import annotations

import queue
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .demo import demo_candidates
from .evaluation import requirement_summary
from .models import BrowserEvent, CandidateStage, JobStatus, RunStatus
from .ui_helpers import ASSESSMENT_LABELS, RUN_LABELS, STAGE_LABELS, open_folder


class UIActionsMixin:

    def new_job(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("新建岗位")
        dialog.geometry("640x440")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(2, weight=1)
        title, keyword = tk.StringVar(), tk.StringVar()
        ttk.Label(dialog, text="岗位名称").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ttk.Entry(dialog, textvariable=title).grid(row=0, column=1, padx=(0, 10), pady=8, sticky="ew")
        ttk.Label(dialog, text="搜索关键词").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Entry(dialog, textvariable=keyword).grid(row=1, column=1, padx=(0, 10), pady=5, sticky="ew")
        ttk.Label(dialog, text="岗位 JD").grid(row=2, column=0, padx=10, pady=5, sticky="nw")
        jd = scrolledtext.ScrolledText(dialog, wrap="word")
        jd.grid(row=2, column=1, padx=(0, 10), pady=5, sticky="nsew")

        def save() -> None:
            try:
                job_id = self.db.create_job(title.get(), keyword.get(), jd.get("1.0", "end"))
                self.service.parse_and_save_job(job_id, title=title.get(), keyword=keyword.get(), jd=jd.get("1.0", "end"))
            except Exception as error:
                messagebox.showerror("创建失败", str(error), parent=dialog)
                return
            dialog.destroy()
            self.refresh_jobs(job_id)

        ttk.Button(dialog, text="创建并解析", style="Primary.TButton", command=save).grid(row=3, column=1, padx=10, pady=10, sticky="e")

    def refresh_jobs(self, select_id: int | None = None) -> None:
        selected = select_id or self.current_job_id
        self.job_tree.delete(*self.job_tree.get_children())
        jobs = self.db.list_jobs()
        for job in jobs:
            self.job_tree.insert("", "end", iid=str(job["id"]), values=(job["title"], job["candidate_count"]))
        if selected and self.job_tree.exists(str(selected)):
            self.job_tree.selection_set(str(selected)); self.load_job(int(selected))
        elif jobs:
            first = int(jobs[0]["id"]); self.job_tree.selection_set(str(first)); self.load_job(first)
        else:
            self.current_job_id = None

    def _job_selected(self, _event=None) -> None:
        selection = self.job_tree.selection()
        if selection:
            self.load_job(int(selection[0]))

    def load_job(self, job_id: int) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        self.current_job_id = job_id
        self.title_var.set(job["title"]); self.keyword_var.set(job["keyword"])
        self.jd_text.delete("1.0", "end"); self.jd_text.insert("1.0", job["jd"])
        profile = self.service.load_profile(job_id)
        self.edu_var.set(profile.min_education or "不限")
        self.exp_var.set(str(profile.min_experience_years or 0))
        self.location_var.set("、".join(profile.locations))
        self.profile_summary.set(requirement_summary(profile))
        self.global_status.set(f"当前岗位：{job['title']}")
        self.refresh_candidates(); self.refresh_runs(); self.refresh_stats()

    def archive_job(self) -> None:
        if not self.current_job_id or not messagebox.askyesno("归档岗位", "确认归档当前岗位？候选人主数据不会删除。"):
            return
        self.db.update_job(self.current_job_id, status=JobStatus.ARCHIVED)
        self.current_job_id = None; self.refresh_jobs()

    def save_profile(self) -> bool:
        if not self.current_job_id:
            messagebox.showinfo("提示", "请先创建岗位。")
            return False
        try:
            profile = self.service.parse_and_save_job(
                self.current_job_id, title=self.title_var.get(), keyword=self.keyword_var.get(),
                jd=self.jd_text.get("1.0", "end"), min_education=self.edu_var.get(),
                min_experience_years=self.exp_var.get(), locations=self.location_var.get(),
            )
        except Exception as error:
            messagebox.showerror("保存失败", str(error)); return False
        self.profile_summary.set(requirement_summary(profile)); self.refresh_jobs(self.current_job_id)
        return True

    def reassess(self) -> None:
        if not self.save_profile() or not self.current_job_id:
            return
        summary = self.service.reassess_job(self.current_job_id)
        self.log(f"重新评估：通过 {summary.pass_count}，待复核 {summary.review_count}，冲突 {summary.conflict_count}")
        self.refresh_candidates(); self.refresh_stats()

    def _submit_search(self, job_id: int, run_id: int, query: str) -> None:
        request_id = self.worker.submit("SEARCH", {"job_id": job_id, "run_id": run_id, "query": query, "max_pages": 5, "max_count": 200})
        self.pending[request_id] = {"job_id": job_id, "run_id": run_id, "query": query}
        self.search_btn.configure(state="disabled"); self.progress["value"] = 5; self.task_status.set("正在启动浏览器…")

    def start_search(self) -> None:
        if not self.save_profile() or not self.current_job_id:
            return
        query = self.keyword_var.get().strip() or self.title_var.get().strip()
        if not query:
            messagebox.showwarning("缺少搜索词", "请填写搜索关键词。")
            return
        run_id = self.db.create_sourcing_run(self.current_job_id, query)
        self._submit_search(self.current_job_id, run_id, query); self.refresh_runs()

    def continue_login(self) -> None:
        if not self.waiting_login:
            return
        item, self.waiting_login = self.waiting_login, None
        self.login_btn.configure(state="disabled")
        self.db.update_sourcing_run(item["run_id"], status=RunStatus.RUNNING)
        self._submit_search(item["job_id"], item["run_id"], item["query"])

    def import_demo(self) -> None:
        if not self.save_profile() or not self.current_job_id:
            return
        run_id = self.db.create_sourcing_run(self.current_job_id, "DEMO")
        try:
            summary = self.service.ingest_candidates(job_id=self.current_job_id, run_id=run_id, candidates=demo_candidates())
            self.db.update_sourcing_run(run_id, status=RunStatus.SUCCEEDED, found_count=summary.found, new_count=summary.new_job_links)
        except Exception as error:
            self.db.update_sourcing_run(run_id, status=RunStatus.FAILED, error_code="DEMO_IMPORT_FAILED", error_message=str(error))
            messagebox.showerror("导入失败", str(error)); return
        self.log(f"演示导入：发现 {summary.found}，待复核 {summary.review_count}")
        self.refresh_jobs(self.current_job_id)

    def _poll_events(self) -> None:
        while True:
            try:
                self._handle_event(self.browser_events.get_nowait())
            except queue.Empty:
                break
        self.after(150, self._poll_events)

    def _handle_event(self, event: BrowserEvent) -> None:
        payload, context = event.payload, self.pending.get(event.request_id, {})
        run_id = int(payload.get("run_id") or context.get("run_id") or 0)
        if event.event in {"STATUS", "PROGRESS"}:
            self.task_status.set(str(payload.get("message") or "任务运行中")); self.progress["value"] = int(payload.get("progress") or 0)
            return
        if event.event == "NEED_LOGIN":
            self.db.update_sourcing_run(run_id, status=RunStatus.NEED_LOGIN)
            self.waiting_login = {"job_id": context["job_id"], "run_id": run_id, "query": context["query"]}
            self.login_btn.configure(state="normal"); self.search_btn.configure(state="normal")
            self.task_status.set(str(payload.get("message") or "等待登录")); self.refresh_runs(); return
        if event.event == "COMPLETED":
            try:
                summary = self.service.ingest_candidates(job_id=context["job_id"], run_id=run_id, candidates=payload.get("candidates") or [])
                self.db.update_sourcing_run(run_id, status=RunStatus.SUCCEEDED, found_count=summary.found, new_count=summary.new_job_links)
                self.task_status.set(f"完成：发现 {summary.found}，新入池 {summary.new_job_links}"); self.progress["value"] = 100
            except Exception as error:
                self.db.update_sourcing_run(run_id, status=RunStatus.FAILED, error_code="INGEST_FAILED", error_message=str(error))
                self.task_status.set(f"入库失败：{error}")
            self.search_btn.configure(state="normal"); self.pending.pop(event.request_id, None)
            self.refresh_jobs(context.get("job_id")); return
        if event.event == "FAILED":
            self.db.update_sourcing_run(
                run_id, status=RunStatus.FAILED, error_code=str(payload.get("error_code") or "UNKNOWN"),
                error_message=str(payload.get("error") or "未知错误"), diagnostic_dir=str(payload.get("diagnostic_dir") or ""),
            )
            self.search_btn.configure(state="normal"); self.progress["value"] = 0
            self.task_status.set(f"任务失败：{payload.get('error_code') or 'UNKNOWN'}"); self.refresh_runs()

    def refresh_candidates(self) -> None:
        self.candidate_tree.delete(*self.candidate_tree.get_children())
        if not self.current_job_id:
            return
        rows = self.db.list_job_candidates(
            self.current_job_id, assessment_status=self.assess_filter.get(), stage=self.stage_filter.get(), search=self.search_filter.get()
        )
        for row in rows:
            score = "" if row.get("fit_score") is None else f"{float(row['fit_score']):.1f}"
            self.candidate_tree.insert("", "end", iid=str(row["job_candidate_id"]), values=(
                ASSESSMENT_LABELS.get(row.get("assessment_status"), row.get("assessment_status")), score,
                row["name"], row["title"], row["location"], row["education"], row["experience"],
                STAGE_LABELS.get(row["stage"], row["stage"]), row["owner"],
            ))

    def selected_candidate(self) -> int | None:
        selection = self.candidate_tree.selection()
        return int(selection[0]) if selection else None

    def set_stage(self, stage: CandidateStage) -> None:
        candidate_id = self.selected_candidate()
        if not candidate_id:
            return
        self.db.update_job_candidate(candidate_id, stage=stage)
        self.db.add_follow_up(candidate_id, "STAGE_CHANGED", STAGE_LABELS[stage.value])
        self.refresh_candidates()

    def review_candidate(self) -> None:
        candidate_id = self.selected_candidate()
        row = self.db.get_job_candidate(candidate_id) if candidate_id else None
        if not row:
            messagebox.showinfo("提示", "请先选择候选人。")
            return
        dialog = tk.Toplevel(self); dialog.title(f"候选人复核 · {row.get('name') or '未命名'}"); dialog.geometry("820x650")
        dialog.columnconfigure(1, weight=1); dialog.rowconfigure(4, weight=1)
        summary = f"{row.get('name','')} · {row.get('title','')}\n{row.get('location','')} / {row.get('education','')} / {row.get('experience','')}\n评估：{ASSESSMENT_LABELS.get(row.get('assessment_status'))}  匹配度：{row.get('fit_score') or '-'}"
        ttk.Label(dialog, text=summary, font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=10)
        reasons = "\n".join(f"• {item}" for item in row.get("reasons") or ["暂无依据"])
        ttk.Label(dialog, text=reasons, wraplength=760, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=5)
        stage_var, owner_var = tk.StringVar(value=row["stage"]), tk.StringVar(value=row["owner"] or "")
        ttk.Label(dialog, text="阶段").grid(row=2, column=0, padx=12, pady=5, sticky="w")
        ttk.Combobox(dialog, textvariable=stage_var, values=tuple(item.value for item in CandidateStage), state="readonly").grid(row=2, column=1, padx=(0, 12), sticky="ew")
        ttk.Label(dialog, text="负责人").grid(row=3, column=0, padx=12, pady=5, sticky="w")
        ttk.Entry(dialog, textvariable=owner_var).grid(row=3, column=1, padx=(0, 12), sticky="ew")
        ttk.Label(dialog, text="备注").grid(row=4, column=0, padx=12, pady=5, sticky="nw")
        note = scrolledtext.ScrolledText(dialog, height=8, wrap="word"); note.grid(row=4, column=1, padx=(0, 12), sticky="nsew"); note.insert("1.0", row["note"] or "")
        decision, reason = tk.StringVar(), tk.StringVar()
        ttk.Label(dialog, text="复核决定").grid(row=5, column=0, padx=12, pady=5, sticky="w")
        ttk.Combobox(dialog, textvariable=decision, values=("", "确认进入下一步", "保留待复核", "确认不合适"), state="readonly").grid(row=5, column=1, padx=(0, 12), sticky="ew")
        ttk.Label(dialog, text="复核理由").grid(row=6, column=0, padx=12, pady=5, sticky="w")
        ttk.Entry(dialog, textvariable=reason).grid(row=6, column=1, padx=(0, 12), sticky="ew")
        bar = ttk.Frame(dialog); bar.grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=10)
        if row.get("source_url") and not str(row["source_url"]).startswith("demo://"):
            ttk.Button(bar, text="打开来源", command=lambda: webbrowser.open(row["source_url"])).pack(side="left")

        def save() -> None:
            self.db.update_job_candidate(candidate_id, stage=stage_var.get(), owner=owner_var.get(), note=note.get("1.0", "end").strip())
            if decision.get():
                self.db.add_review_decision(candidate_id, decision.get(), reason.get())
            self.db.add_follow_up(candidate_id, "REVIEW_SAVED", reason.get())
            dialog.destroy(); self.refresh_candidates(); self.refresh_stats()
        ttk.Button(bar, text="保存复核", style="Primary.TButton", command=save).pack(side="right")

    def export_job(self) -> None:
        if not self.current_job_id:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=(("CSV 文件", "*.csv"),))
        if path:
            count = self.db.export_job_csv(self.current_job_id, path); messagebox.showinfo("导出完成", f"已导出 {count} 名候选人。")

    def refresh_runs(self) -> None:
        self.run_tree.delete(*self.run_tree.get_children())
        if not self.current_job_id:
            return
        for run in self.db.list_sourcing_runs(self.current_job_id):
            error = run.get("error_code") or ""
            if run.get("diagnostic_dir"):
                error = f"{error} · {run['diagnostic_dir']}".strip(" ·")
            self.run_tree.insert("", "end", iid=str(run["id"]), values=(run["id"], RUN_LABELS.get(run["status"], run["status"]), run["query"], run["found_count"], run["new_count"], run["started_at"] or run["created_at"], error))

    def open_diagnostics(self) -> None:
        selection = self.run_tree.selection()
        if not selection or not self.current_job_id:
            return
        run = next((item for item in self.db.list_sourcing_runs(self.current_job_id) if int(item["id"]) == int(selection[0])), None)
        if run and run.get("diagnostic_dir"):
            open_folder(run["diagnostic_dir"])
        else:
            messagebox.showinfo("没有诊断包", "该任务没有诊断目录。")

    def refresh_stats(self) -> None:
        if not self.current_job_id:
            self.stats_var.set(""); return
        stats = self.db.job_stats(self.current_job_id)["assessments"]
        total = self.db.job_stats(self.current_job_id)["total"]
        self.stats_var.set(f"候选人 {total} · 通过 {stats.get('PASS',0)} · 待复核 {stats.get('REVIEW',0)} · 明确冲突 {stats.get('CONFLICT',0)}")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal"); self.log_text.insert("end", message + "\n"); self.log_text.configure(state="disabled"); self.log_text.see("end")

    def _on_close(self) -> None:
        try:
            self.worker.shutdown(timeout=5)
        finally:
            self.destroy()
