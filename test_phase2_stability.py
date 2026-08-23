# -*- coding: utf-8 -*-
"""第二阶段：真实搜索稳定性测试。

要求覆盖：
  - 20 次真实招聘搜索（2 个岗位，每次 3~5 页）
  - 候选人字段人工抽查（自动抽样 + 统计）
  - 平台 UID 与来源链接验证
  - 同岗位重复搜索（去重/upsert 生效）
  - 跨岗位重复搜索（同候选人挂两个岗位，互不污染）
  - V0.9.1 新特性：断点续搜（start_page）
"""
import csv
import json
import os
import queue
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workbench.database import WorkbenchDB
from workbench.browser_worker import BrowserWorker
from workbench.service import RecruitmentService

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase2_results")
os.makedirs(OUT_DIR, exist_ok=True)
RESULT_CSV = os.path.join(OUT_DIR, "search_log.csv")

EDU_SET = {"初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"}
EXP_SEG = re.compile(r"(在校/应届|一年以内|1-3年|3-5年|5-10年|10年以上)")

# ---------------- 搜索计划：20 次 ----------------
# (岗位键, 关键词, 页数, 备注)
PLAN = [
    ("A", "Python 大模型", 3, "FDE基线"),
    ("B", "销售", 3, "销售基线"),
    ("A", "Python 大模型", 3, "同岗位重复1"),
    ("A", "Python 大模型", 4, "同岗位重复2"),
    ("B", "销售", 3, "同岗位重复1"),
    ("B", "销售", 4, "同岗位重复2"),
    ("A", "AI 工程师", 3, "A换词"),
    ("B", "大客户销售", 3, "B换词"),
    ("A", "Java", 4, "A扩词"),
    ("B", "销售", 5, "B加深5页"),
    ("A", "Python 大模型", 5, "A加深5页"),
    ("B", "渠道销售", 3, "B换词2"),
    ("A", "算法工程师", 3, "A换词2"),
    ("B", "销售", 3, "跨岗位:同词销售在B第3次"),
    ("A", "销售", 3, "跨岗位:销售词挂到A"),
    ("B", "Python", 3, "跨岗位:Python词挂到B"),
    ("A", "Python 大模型", 3, "同岗位重复3"),
    ("B", "大客户销售", 3, "B换词重复"),
    ("A", "Python 大模型", 3, "断点续搜start_page=2", "start_page=2"),
    ("B", "销售", 3, "收官"),
]

tmpdb = os.path.join(tempfile.gettempdir(), f"phase2_{int(time.time())}.db")
db = WorkbenchDB(tmpdb)
svc = RecruitmentService(db)

job_ids = {}
job_ids["A"] = db.create_job("FDE前沿部署工程师", "Python 大模型")
svc.parse_and_save_job(job_ids["A"], title="FDE前沿部署工程师", keyword="Python 大模型",
                       jd="本科及以上学历，3年以上经验，精通Python，熟悉大模型/RAG/Agent，工作地北京",
                       min_education="本科", min_experience_years=3, locations=["北京"])
job_ids["B"] = db.create_job("销售经理", "销售")
svc.parse_and_save_job(job_ids["B"], title="销售经理", keyword="销售",
                       jd="大客户销售，本科及以上学历，工作地北京", locations=["北京"])
db.confirm_job_profile(job_ids["A"], confirmed_by="phase2")
db.confirm_job_profile(job_ids["B"], confirmed_by="phase2")
print("岗位: A(FDE)=%s  B(销售)=%s" % (job_ids["A"], job_ids["B"]))

events = queue.Queue()
worker = BrowserWorker(events, hide_browser=True)

log_rows = []


def run_search(idx, job_key, query, pages, note, start_page=1):
    job_id = job_ids[job_key]
    run_id = db.create_sourcing_run(job_id, query)
    rid = worker.submit("SEARCH", {
        "run_id": run_id, "query": query,
        "max_pages": pages, "max_count": 200, "start_page": start_page,
    })
    t0 = time.time()
    result, candidates, need_login = None, None, False
    deadline = time.time() + 420
    while time.time() < deadline:
        try:
            ev = events.get(timeout=2)
        except queue.Empty:
            continue
        if ev.request_id != rid:
            continue
        if ev.event == "COMPLETED":
            result, candidates = "COMPLETED", ev.payload.get("candidates") or []
            break
        if ev.event == "FAILED":
            result = "FAILED:" + str(ev.payload.get("error_code"))
            break
        if ev.event == "NEED_LOGIN":
            result, need_login = "NEED_LOGIN", True
            break
        if ev.event == "CANCELLED":
            result = "CANCELLED"
            break
    dur = round(time.time() - t0, 1)
    if result is None:
        result = "TIMEOUT"
    row = {"idx": idx, "job": job_key, "query": query, "pages": pages, "note": note,
           "result": result, "found": 0, "new": 0, "pass": 0, "review": 0, "conflict": 0,
           "uid_rate": "", "bad_field": 0, "duration": dur}
    if candidates is not None:
        summary = svc.ingest_candidates(job_id=job_id, run_id=run_id, candidates=candidates)
        db.update_sourcing_run(run_id, status="SUCCEEDED" if result == "COMPLETED" else "FAILED",
                               found_count=summary.found, new_count=summary.new_candidates)
        # ---- 字段抽查 ----
        bad = 0
        uid_n = 0
        for c in candidates:
            if c.get("platform_uid"):
                uid_n += 1
            if not c.get("name") or not c.get("education") or not c.get("experience"):
                bad += 1
                continue
            if c.get("education") not in EDU_SET:
                bad += 1
                continue
            if not EXP_SEG.search(c.get("experience", "")):
                bad += 1
                continue
            age = c.get("age") or 0
            if age and not (16 <= int(age) <= 65):
                bad += 1
        row.update({
            "found": summary.found, "new": summary.new_candidates,
            "pass": summary.pass_count, "review": summary.review_count,
            "conflict": summary.conflict_count,
            "uid_rate": f"{uid_n}/{len(candidates)}", "bad_field": bad,
        })
        # 来源链接抽样
        if candidates:
            src = candidates[0].get("source_url") or candidates[0].get("source") or ""
            row["sample_source"] = src[:90]
    else:
        db.update_sourcing_run(run_id, status="FAILED", error_message=result)
    log_rows.append(row)
    with open(RESULT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerows(log_rows)
    print(f"[{idx:02d}] {job_key} 「{query}」x{pages}页 {note}: {result} "
          f"found={row['found']} new={row['new']} P/R/C={row['pass']}/{row['review']}/{row['conflict']} "
          f"UID={row['uid_rate']} 坏字段={row['bad_field']} {dur}s", flush=True)
    return result


print("=" * 70, flush=True)
for i, item in enumerate(PLAN, 1):
    job_key, query, pages, note = item[0], item[1], item[2], item[3]
    start_page = int(item[4].split("=")[1]) if len(item) > 4 else 1
    r = run_search(i, job_key, query, pages, note, start_page)
    if r == "NEED_LOGIN":
        print("!! 登录态失效，终止后续测试", flush=True)
        break
    time.sleep(2)  # 平台节流

# ---------------- 汇总 ----------------
print("=" * 70)
total = len(log_rows)
ok = sum(1 for r in log_rows if r["result"] == "COMPLETED")
total_found = sum(r["found"] for r in log_rows)
print(f"搜索次数: {total}  成功: {ok}  失败: {total - ok}  累计发现: {total_found}")

# 同岗位重复：第3次A搜索(重复1)的 new 率
rep = [r for r in log_rows if "同岗位重复" in r["note"] and r["found"]]
if rep:
    rates = [r["new"] / r["found"] for r in rep]
    print("同岗位重复搜索 new率: %s (平均 %.0f%%)" % (
        [f"{x:.0%}" for x in rates], 100 * sum(rates) / len(rates)))

# 跨岗位：「销售」词在 A、B 两岗都搜过 → 候选人应同时挂两岗
with db.connect() as conn:
    cross = conn.execute(
        "SELECT COUNT(*) FROM candidates c WHERE "
        "(SELECT COUNT(DISTINCT job_id) FROM job_candidates jc WHERE jc.candidate_id=c.id) >= 2"
    ).fetchone()[0]
print("跨岗位共享候选人(挂≥2岗):", cross)

stats_a, stats_b = db.job_stats(job_ids["A"]), db.job_stats(job_ids["B"])
print("岗位A统计:", json.dumps(stats_a, ensure_ascii=False))
print("岗位B统计:", json.dumps(stats_b, ensure_ascii=False))

worker.shutdown(timeout=20)
print("线程已关闭:", not worker._thread.is_alive())
print("PHASE2 DONE, 明细:", RESULT_CSV)