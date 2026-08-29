# -*- coding: utf-8 -*-
"""简历智能体 · 网页版后端（FastAPI）。

复用 workbench 全部能力：岗位管理 / JD 智能分析 / 受控浏览器搜索 / 实时进度 /
浏览器画面截图流 / 候选人匹配排序。面向甲方演示的单页网页服务。

启动：python -m webapp.server   （然后浏览器打开 http://127.0.0.1:8899）
"""
from __future__ import annotations

import json
import math
import queue
import sys
import threading
import time
import csv
import io
from pathlib import Path
from typing import Any

# 让脚本能 import workbench 包
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
from urllib.parse import quote  # noqa: E402
from fastapi import FastAPI, Body, Response  # noqa: E402
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse  # noqa: E402

from workbench.database import WorkbenchDB, default_data_dir  # noqa: E402
from workbench.service import RecruitmentService  # noqa: E402
from workbench.browser_worker import BrowserWorker  # noqa: E402
from workbench.jd_analyzer import analyze_job  # noqa: E402
from workbench.models import SearchPlan  # noqa: E402

PREVIEW_PATH = default_data_dir() / "preview" / "latest.png"
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="简历智能体")

db = WorkbenchDB()
service = RecruitmentService(db)
_events: "queue.Queue" = queue.Queue()
worker = BrowserWorker(_events, hide_browser=True)  # 离屏有头：画面经截图流进网页


# ---------------- 运行态（内存） ----------------
class RunState:
    def __init__(self):
        self.lock = threading.Lock()
        self.runs: dict[int, dict[str, Any]] = {}   # job_id -> 状态
        self.run_job: dict[int, int] = {}            # run_id -> job_id

    def update(self, job_id: int, **kw):
        with self.lock:
            st = self.runs.setdefault(job_id, {
                "status": "IDLE", "message": "", "progress": 0, "found": 0,
                "page": 0, "max_pages": 0, "target": 0, "need_login": False,
                "error": "", "finished": False, "stats": {},
            })
            st.update(kw)

    def get(self, job_id: int):
        with self.lock:
            return dict(self.runs.get(job_id, {"status": "IDLE", "found": 0, "progress": 0}))


state = RunState()


def _drain_events():
    """后台线程：消费 BrowserWorker 事件队列 → 落库 + 更新运行态。"""
    while True:
        try:
            ev = _events.get(timeout=0.5)
        except queue.Empty:
            continue
        except Exception:
            continue
        run_id = ev.payload.get("run_id")
        job_id = state.run_job.get(_to_int(run_id)) if run_id is not None else None
        name = ev.event
        p = ev.payload

        if name == "STATUS":
            if job_id:
                state.update(job_id, status="RUNNING", message=p.get("message", ""),
                             progress=p.get("progress", 0))
        elif name == "PROGRESS":
            if job_id:
                state.update(job_id, status="RUNNING", found=p.get("count", 0),
                             page=p.get("page_no", 0), progress=p.get("progress", 0),
                             message=p.get("message", ""))
        elif name == "PAGE_BATCH":
            if job_id:
                try:
                    summary = service.ingest_candidates(
                        job_id=job_id, run_id=_to_int(run_id), candidates=p.get("candidates") or [])
                    st = state.get(job_id)
                    stats = st.get("stats") or {}
                    stats["pass"] = stats.get("pass", 0) + summary.pass_count
                    stats["review"] = stats.get("review", 0) + summary.review_count
                    stats["conflict"] = stats.get("conflict", 0) + summary.conflict_count
                    state.update(job_id, stats=stats)
                except Exception as e:
                    state.update(job_id, message=f"落库异常: {e}")
        elif name == "CHECKPOINT":
            if job_id:
                state.update(job_id, found=p.get("count", 0), page=p.get("page_no", 0))
        elif name == "NEED_LOGIN":
            if job_id:
                state.update(job_id, status="NEED_LOGIN", need_login=True,
                             message="需要在浏览器中登录智联招聘")
            _capture_login_page()
        elif name == "COMPLETED":
            if job_id:
                st = state.get(job_id)
                state.update(job_id, status="SUCCEEDED", finished=True,
                             progress=100, found=p.get("count", st.get("found", 0)),
                             message=p.get("message", "搜索完成"))
        elif name in ("FAILED", "CANCELLED"):
            if job_id:
                state.update(job_id, status=name, finished=True,
                             error=p.get("error", ""), message=p.get("message", ""))
        elif name == "LOGIN_CHECKED":
            pass


def _to_int(v) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _capture_login_page():
    try:
        worker.submit("CAPTURE_PREVIEW", {})
    except Exception:
        pass


threading.Thread(target=_drain_events, daemon=True).start()


# ---------------- API ----------------
@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


@app.post("/api/analyze")
def api_analyze(payload: dict = Body(...)):
    jd = str(payload.get("jd") or "")
    keyword = str(payload.get("keyword") or "")
    if not jd.strip() and not keyword.strip():
        return JSONResponse({"ok": False, "error": "请填写岗位描述或关键词"}, status_code=400)
    return {"ok": True, "analysis": analyze_job(jd, keyword).as_dict()}


@app.post("/api/jobs")
def api_create_job(payload: dict = Body(...)):
    title = str(payload.get("title") or "").strip()
    jd = str(payload.get("jd") or "")
    keyword = str(payload.get("keyword") or "").strip()
    if not title:
        return JSONResponse({"ok": False, "error": "岗位名称不能为空"}, status_code=400)
    job_id = db.create_job(title, keyword=keyword, jd=jd)
    # 解析并确认画像（演示流程：AI 分析 → 一键确认）
    service.parse_and_save_job(job_id, title=title, keyword=keyword, jd=jd)
    service.confirm_job_profile(job_id, confirmed_by="web")
    return {"ok": True, "job_id": job_id, "analysis": analyze_job(jd, keyword).as_dict()}


@app.get("/api/jobs")
def api_list_jobs():
    jobs = db.list_jobs()
    out = []
    for j in jobs:
        jid = j["id"]
        try:
            rows = db.list_job_candidates(jid, limit=100000)
        except Exception:
            rows = []
        st = state.get(jid)
        out.append({
            "id": jid, "title": j["title"], "keyword": j.get("keyword", ""),
            "candidate_count": len(rows),
            "pass": sum(1 for r in rows if r.get("assessment_status") == "PASS"),
            "review": sum(1 for r in rows if r.get("assessment_status") == "REVIEW"),
            "conflict": sum(1 for r in rows if r.get("assessment_status") == "CONFLICT"),
            "status": st.get("status", "IDLE"),
            "created_at": j.get("created_at", ""),
        })
    return {"ok": True, "jobs": out}


@app.post("/api/jobs/{job_id}/start")
def api_start(job_id: int, payload: dict = Body(default={})):
    target = int(payload.get("target_count") or 100)
    fetch_detail = bool(payload.get("fetch_detail", False))
    max_detail = max(1, min(int(payload.get("max_detail") or 20), 50))
    target = max(10, min(target, 500))
    job = db.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "岗位不存在"}, status_code=404)
    if job.get("profile_status") != "CONFIRMED":
        service.confirm_job_profile(job_id, confirmed_by="web")
    analysis = analyze_job(job.get("jd", ""), job.get("keyword", ""))
    query = job.get("keyword") or analysis.search_query or job.get("title")
    max_pages = min(20, max(3, math.ceil(target / 20) + 1))
    plan = SearchPlan(query=query, max_pages=max_pages, max_count=target, browser_mode="managed")
    run_id = service.create_sourcing_run(job_id, plan)
    state.run_job[run_id] = job_id
    # 源头筛选条件：城市取 JD 第一个目标城市，学历/经验直接映射到智联筛选器
    filters = {
        "city": (analysis.locations[0] if analysis.locations else ""),
        "min_education": analysis.min_education or "",
        "min_experience_years": analysis.min_experience_years or 0,
    }
    state.update(job_id, status="RUNNING", message="正在启动…", progress=2, found=0,
                 page=0, target=target, max_pages=max_pages, need_login=False,
                 error="", finished=False, stats={"pass": 0, "review": 0, "conflict": 0})
    worker.submit("SEARCH", {
        "run_id": run_id, "query": query, "max_pages": max_pages,
        "max_count": target, "start_page": 1, "filters": filters,
        "fetch_detail": fetch_detail, "max_detail": max_detail,
    })
    return {"ok": True, "run_id": run_id, "query": query, "max_pages": max_pages, "target": target}


@app.post("/api/jobs/{job_id}/stop")
def api_stop(job_id: int):
    worker.submit("CANCEL", {})
    state.update(job_id, status="CANCELLED", finished=True, message="已手动停止")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/login_shown")
def api_login_shown(job_id: int):
    worker.submit("BRING_TO_FRONT", {})
    return {"ok": True}


@app.get("/api/jobs/{job_id}/status")
def api_status(job_id: int):
    st = state.get(job_id)
    try:
        rows = db.list_job_candidates(job_id, limit=100000)
        st["pool_total"] = len(rows)
    except Exception:
        st["pool_total"] = st.get("found", 0)
    return {"ok": True, "state": st}


def _serialize_candidate(r: dict, *, detail: bool = False) -> dict:
    item = {
        "id": r["job_candidate_id"],
        "candidate_id": r.get("candidate_id"),
        "name": r.get("name", "") or "（未署名）",
        "title": r.get("title", ""),
        "location": r.get("location", ""),
        "education": r.get("education", ""),
        "experience": r.get("experience", ""),
        "age": r.get("age", 0),
        "salary": r.get("expected_salary", ""),
        "certificates": r.get("certificates", ""),
        "skills": r.get("skills", ""),
        "activity": r.get("activity", ""),
        "status": r.get("assessment_status") or "REVIEW",
        "score": round(float(r.get("fit_score") or 0), 1),
        "reasons": r.get("reasons", [])[:8],
        "stage": r.get("stage") or "TO_REVIEW",
        "note": r.get("note", ""),
        "has_resume": bool(r.get("full_text")),
    }
    if detail:
        item["evidence"] = r.get("evidence", {})
        item["text"] = r.get("text", "")
        item["full_text"] = r.get("full_text", "")
        item["source_url"] = r.get("source_url", "")
        item["last_seen_at"] = r.get("last_seen_at", "")
    return item


def _serialize_profile(p) -> dict:
    return {
        "keyword": p.keyword, "required_skills": list(p.required_skills),
        "preferred_skills": list(p.preferred_skills), "min_education": p.min_education,
        "min_experience_years": p.min_experience_years, "locations": list(p.locations),
        "age_min": p.age_min, "age_max": p.age_max, "certificates": list(p.certificates),
        "salary_min": p.salary_min, "salary_max": p.salary_max,
    }


_SORT_KEYS = {
    "score": lambda r: float(r.get("fit_score") or 0),
    "age": lambda r: int(r.get("age") or 0),
    "experience": lambda r: r.get("experience", ""),
    "salary": lambda r: r.get("expected_salary", ""),
    "education": lambda r: r.get("education", ""),
}


@app.get("/api/jobs/{job_id}")
def api_job_detail(job_id: int):
    job = db.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "岗位不存在"}, status_code=404)
    profile = service.load_profile(job_id)
    rows = db.list_job_candidates(job_id, limit=100000)
    st = state.get(job_id)
    return {"ok": True, "job": {
        "id": job_id, "title": job["title"], "keyword": job.get("keyword", ""),
        "jd": job.get("jd", ""), "created_at": job.get("created_at", ""),
        "profile": _serialize_profile(profile),
        "stats": {
            "total": len(rows),
            "pass": sum(1 for r in rows if r.get("assessment_status") == "PASS"),
            "review": sum(1 for r in rows if r.get("assessment_status") == "REVIEW"),
            "conflict": sum(1 for r in rows if r.get("assessment_status") == "CONFLICT"),
        },
        "run_status": st.get("status", "IDLE"), "run_finished": st.get("finished", False),
    }}


@app.get("/api/jobs/{job_id}/candidates")
def api_candidates(job_id: int, status: str = "ALL", stage: str = "ALL", search: str = "",
                   education: str = "", activity: str = "", sort: str = "score", order: str = "desc", limit: int = 1000):
    rows = db.list_job_candidates(job_id, assessment_status=status,
                                  stage=stage, search=search, limit=100000)
    if education:
        rows = [r for r in rows if (r.get("education") or "") == education]
    if activity:
        rows = [r for r in rows if activity in (r.get("activity") or "")]
    key = _SORT_KEYS.get(sort, _SORT_KEYS["score"])
    rows.sort(key=key, reverse=(order != "asc"))
    out = [_serialize_candidate(r) for r in rows[:limit]]
    return {"ok": True, "candidates": out, "total": len(rows)}


@app.get("/api/candidates/{job_candidate_id}")
def api_candidate_detail(job_candidate_id: int):
    r = db.get_job_candidate(job_candidate_id)
    if not r:
        return JSONResponse({"ok": False, "error": "候选人不存在"}, status_code=404)
    item = _serialize_candidate(r, detail=True)
    item["follow_ups"] = db.list_follow_ups(job_candidate_id)
    # 结构化解析完整简历（若有），供前端渲染工作经历时间线
    if item.get("full_text"):
        try:
            from workbench.resume_parser import parse_resume
            item["parsed_resume"] = parse_resume(item["full_text"])
        except Exception:
            item["parsed_resume"] = None
    return {"ok": True, "candidate": item}


@app.patch("/api/candidates/{job_candidate_id}")
def api_update_candidate(job_candidate_id: int, payload: dict = Body(...)):
    stage = payload.get("stage")
    note = payload.get("note")
    try:
        db.update_job_candidate(job_candidate_id, stage=stage, note=note, actor="web")
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if stage:
        db.add_follow_up(job_candidate_id, action=f"STAGE:{stage}", note=note or "", actor="web")
    return {"ok": True}


@app.put("/api/jobs/{job_id}/profile")
def api_update_profile(job_id: int, payload: dict = Body(...)):
    if not db.get_job(job_id):
        return JSONResponse({"ok": False, "error": "岗位不存在"}, status_code=404)
    profile = service.update_job_profile(
        job_id,
        keyword=payload.get("keyword"),
        min_education=payload.get("min_education"),
        min_experience_years=payload.get("min_experience_years"),
        age_min=payload.get("age_min"),
        age_max=payload.get("age_max"),
        locations=payload.get("locations"),
        required_skills=payload.get("required_skills"),
        preferred_skills=payload.get("preferred_skills"),
        certificates=payload.get("certificates"),
        salary_min=payload.get("salary_min"),
        salary_max=payload.get("salary_max"),
        confirmed_by="web",
    )
    return {"ok": True, "profile": _serialize_profile(profile)}


@app.get("/api/jobs/{job_id}/export")
def api_export(job_id: int):
    job = db.get_job(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "岗位不存在"}, status_code=404)
    rows = db.list_job_candidates(job_id, limit=100000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["姓名", "职位", "匹配结论", "匹配分", "招聘状态", "城市", "学历", "经验",
                "年龄", "期望薪资", "证书", "在职状态", "技能", "匹配理由", "备注"])
    status_cn = {"PASS": "匹配", "REVIEW": "待复核", "CONFLICT": "不符"}
    stage_cn = {"NEW": "新入库", "TO_REVIEW": "待评估", "TO_CONTACT": "待联系", "CONTACTED": "已联系",
                "INTERVIEW": "约面", "OFFER": "已发offer", "HIRED": "已入职", "REJECTED": "已淘汰", "TALENT_POOL": "人才库"}
    for r in rows:
        w.writerow([
            r.get("name", ""), r.get("title", ""),
            status_cn.get(r.get("assessment_status"), r.get("assessment_status", "")),
            round(float(r.get("fit_score") or 0), 1),
            stage_cn.get(r.get("stage"), r.get("stage", "")),
            r.get("location", ""), r.get("education", ""), r.get("experience", ""),
            r.get("age", 0) or "", r.get("expected_salary", ""), r.get("certificates", ""),
            r.get("activity", ""), r.get("skills", ""),
            "；".join(r.get("reasons", [])[:5]), r.get("note", ""),
        ])
    # UTF-8 BOM 让 Excel 正确识别中文
    data = "﻿" + buf.getvalue()
    fname = f"候选人_{job['title']}_{job_id}.csv"
    return Response(content=data.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"})


@app.get("/api/preview.png")
def api_preview():
    if PREVIEW_PATH.is_file():
        return FileResponse(str(PREVIEW_PATH), media_type="image/png",
                            headers={"Cache-Control": "no-store"})
    # 返回 1x1 占位图
    return JSONResponse({"ok": False}, status_code=404)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "简历智能体", "ts": time.time()}


def main():
    port = 8899
    print(f"\n  简历智能体 · 网页版已启动")
    print(f"  请在浏览器打开:  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()