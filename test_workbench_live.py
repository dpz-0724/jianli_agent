# -*- coding: utf-8 -*-
"""V1 现场验收（自动化部分）：用真实智联账号跑新 workbench 架构。

覆盖验收清单：
  A-4 应用退出后浏览器工作线程能够关闭
  B   岗位隔离（候选人/评估/导出不得串岗）
  D-4 搜索、翻页和候选人解析正常
  D-5 候选人再次出现时更新最新资料并保留快照
"""
import os
import queue
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workbench.database import WorkbenchDB
from workbench.browser_worker import BrowserWorker
from workbench.service import RecruitmentService

RESULTS = []


def check(item, ok, detail=""):
    RESULTS.append((item, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {item} {detail}")


tmpdb = os.path.join(tempfile.gettempdir(), f"wb_accept_{int(time.time())}.db")
db = WorkbenchDB(tmpdb)
svc = RecruitmentService(db)

# ---------- B 准备：两个岗位 ----------
job_java = db.create_job("Java工程师", "Java")
svc.parse_and_save_job(
    job_java, title="Java工程师", keyword="Java",
    jd="招聘高级Java后端开发，熟悉Spring Boot、MySQL、Redis",
    min_education="本科", min_experience_years=3, locations=["北京"])
job_sales = db.create_job("销售经理", "销售")
svc.parse_and_save_job(
    job_sales, title="销售经理", keyword="销售",
    jd="大客户销售，负责华北区域", locations=["北京"])
# V0.9 规则：岗位画像必须确认后才能搜索
db.confirm_job_profile(job_java, confirmed_by="live-test")
db.confirm_job_profile(job_sales, confirmed_by="live-test")
print("岗位已建: Java=%s 销售=%s" % (job_java, job_sales))

# ---------- D：BrowserWorker 真实搜索 ----------
events = queue.Queue()
worker = BrowserWorker(events, hide_browser=True)
run_id = db.create_sourcing_run(job_java, "Java")
worker.submit("SEARCH", {"run_id": run_id, "query": "Java", "max_pages": 2, "max_count": 60})

candidates = None
deadline = time.time() + 240
final_event = None
while time.time() < deadline:
    try:
        ev = events.get(timeout=1)
    except queue.Empty:
        continue
    kind = ev.event
    msg = ev.payload.get("message", "")
    if kind in ("STATUS", "PROGRESS"):
        print(f"  · {kind}: {msg}")
    elif kind == "NEED_LOGIN":
        print("  · NEED_LOGIN: 本测试环境应已有登录态，出现即失败")
        final_event = ev
        break
    elif kind == "COMPLETED":
        candidates = ev.payload.get("candidates") or []
        final_event = ev
        print(f"  · COMPLETED: {msg}")
        break
    elif kind == "FAILED":
        final_event = ev
        print(f"  · FAILED: {ev.payload.get('error_code')} {msg}")
        break

check("D-4 搜索/翻页/解析", bool(candidates) and len(candidates) >= 20,
      f"抓到 {0 if candidates is None else len(candidates)} 人")
if candidates:
    c0 = candidates[0]
    fields_ok = all(c0.get(k) for k in ("name", "education", "experience"))
    check("D-4 字段解析完整", fields_ok,
          f"样例: {c0.get('name')} {c0.get('education')} {c0.get('experience')}")

# ---------- 入库 + 评估 ----------
summary = None
if candidates:
    summary = svc.ingest_candidates(job_id=job_java, run_id=run_id, candidates=candidates)
    db.update_sourcing_run(run_id, status="SUCCEEDED",
                           found_count=summary.found, new_count=summary.new_candidates)
    print(f"  入库: found={summary.found} new={summary.new_candidates} "
          f"PASS={summary.pass_count} REVIEW={summary.review_count} CONFLICT={summary.conflict_count}")

# ---------- D-5：重复出现 → 更新资料 + 保留快照 ----------
if candidates:
    summary2 = svc.ingest_candidates(job_id=job_java, run_id=run_id, candidates=candidates)
    with db.connect() as conn:
        snap_cnt = conn.execute("SELECT COUNT(*) FROM candidate_snapshots").fetchone()[0]
    check("D-5 重复入库不新增候选人", summary2.new_candidates == 0,
          f"第二次 new={summary2.new_candidates}")
    check("D-5 快照已保留", snap_cnt >= len(candidates), f"快照行数={snap_cnt}")

# ---------- B：岗位隔离 ----------
fake_sales = [
    {"name": "测试销售甲", "title": "大客户销售", "location": "北京", "education": "本科",
     "experience": "5-10年（6年）", "activity": "今日活跃", "skills": "销售",
     "text": "大客户销售 渠道管理", "source": "mock"},
    {"name": "测试销售乙", "title": "销售助理", "location": "上海", "education": "大专",
     "experience": "1-3年（2年）", "activity": "", "skills": "",
     "text": "电话销售", "source": "mock"},
]
svc.ingest_candidates(job_id=job_sales, run_id=None, candidates=fake_sales)
sales_before = db.job_stats(job_sales)
if candidates:
    svc.reassess_job(job_java)          # 重评 Java 岗
    svc.ingest_candidates(job_id=job_java, run_id=run_id, candidates=candidates[:5])
sales_after = db.job_stats(job_sales)
check("B-4 重评Java不影响销售岗", sales_before == sales_after,
      f"before={sales_before['total']}/{sales_after['total']}")

outdir = os.path.join(tempfile.gettempdir(), f"wb_export_{int(time.time())}")
n1 = db.export_job_csv(job_java, os.path.join(outdir, "java.csv"))
n2 = db.export_job_csv(job_sales, os.path.join(outdir, "sales.csv"))
sales_csv = open(os.path.join(outdir, "sales.csv"), encoding="utf-8-sig").read()
java_csv = open(os.path.join(outdir, "java.csv"), encoding="utf-8-sig").read()
check("B-5 导出不串岗", ("测试销售甲" in sales_csv) and ("测试销售甲" not in java_csv)
      and (n2 == 2), f"java.csv {n1} 行, sales.csv {n2} 行")

# ---------- A-4：工作线程关闭 ----------
worker.shutdown(timeout=15)
check("A-4 浏览器工作线程已关闭", not worker._thread.is_alive())

print("\n========== 验收汇总 ==========")
ok_all = all(ok for _, ok, _ in RESULTS)
for item, ok, detail in RESULTS:
    print(f"  [{'✓' if ok else '✗'}] {item}")
print("LIVE ACCEPTANCE:", "OK" if ok_all else "FAILED")
print("临时库:", tmpdb)