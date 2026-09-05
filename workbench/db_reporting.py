# -*- coding: utf-8 -*-
"""Reporting, export and audit repository methods."""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

from .db_schema import now_iso


class ReportingMixin:
    def job_stats(self, job_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM job_candidates WHERE job_id=?", (job_id,)).fetchone()[0]
            status_rows = conn.execute(
                """
                SELECT COALESCE(a.status,'UNASSESSED') status,COUNT(*) count
                FROM job_candidates jc
                LEFT JOIN assessments a ON a.id=(
                    SELECT id FROM assessments WHERE job_candidate_id=jc.id ORDER BY id DESC LIMIT 1
                ) WHERE jc.job_id=? GROUP BY COALESCE(a.status,'UNASSESSED')
                """,
                (job_id,),
            ).fetchall()
            stages = conn.execute(
                "SELECT stage,COUNT(*) count FROM job_candidates WHERE job_id=? GROUP BY stage", (job_id,)
            ).fetchall()
            return {
                "total": total,
                "assessments": {row["status"]: row["count"] for row in status_rows},
                "stages": {row["stage"]: row["count"] for row in stages},
            }

    def export_job_csv(self, job_id: int, path: str | os.PathLike[str], actor: str = "") -> int:
        rows = self.list_job_candidates(job_id, limit=100000)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "姓名", "职位", "地点", "学历", "经验", "评估结论", "匹配度",
                    "评估依据", "招聘阶段", "负责人", "备注", "下次跟进", "来源",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["name"], row["title"], row["location"], row["education"], row["experience"],
                        row.get("assessment_status") or "UNASSESSED", row.get("fit_score") or "",
                        "；".join(row.get("reasons") or []), row["stage"], row["owner"], row["note"],
                        row["next_follow_up_at"] or "", row["source_url"],
                    ]
                )
        with self.connect(write=True) as conn:
            conn.execute(
                "INSERT INTO exports(job_id,path,actor,row_count,created_at) VALUES(?,?,?,?,?)",
                (job_id, str(destination), actor, len(rows), now_iso()),
            )
            self._audit_conn(
                conn, "JOB_EXPORTED", "job", str(job_id),
                {"path": str(destination), "rows": len(rows)}, actor,
            )
        return len(rows)

    def list_audit_events(self, entity_type: str, entity_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE entity_type=? AND entity_id=? ORDER BY id DESC LIMIT ?",
                (entity_type, entity_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def clear_all_data(self) -> None:
        with self.connect(write=True) as conn:
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM candidates")
            conn.execute("DELETE FROM audit_events")
