# -*- coding: utf-8 -*-
"""Job and sourcing-run repository methods."""
from __future__ import annotations

import json
from typing import Any

from .db_schema import now_iso
from .models import JobStatus, RequirementProfile, RunStatus


class JobRunMixin:
    def create_job(self, title: str, keyword: str = "", jd: str = "") -> int:
        title = title.strip()
        if not title:
            raise ValueError("岗位名称不能为空")
        now = now_iso()
        with self.connect(write=True) as conn:
            cur = conn.execute(
                "INSERT INTO jobs(title,keyword,jd,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (title, keyword.strip(), jd.strip(), JobStatus.ACTIVE.value, now, now),
            )
            job_id = int(cur.lastrowid)
            self._audit_conn(conn, "JOB_CREATED", "job", str(job_id), {"title": title})
            return job_id

    def update_job(
        self,
        job_id: int,
        *,
        title: str | None = None,
        keyword: str | None = None,
        jd: str | None = None,
        profile: RequirementProfile | None = None,
        status: JobStatus | str | None = None,
    ) -> None:
        updates: dict[str, Any] = {"updated_at": now_iso()}
        if title is not None:
            if not title.strip():
                raise ValueError("岗位名称不能为空")
            updates["title"] = title.strip()
        if keyword is not None:
            updates["keyword"] = keyword.strip()
        if jd is not None:
            updates["jd"] = jd.strip()
        if profile is not None:
            updates["requirements_json"] = json.dumps(profile.as_dict(), ensure_ascii=False)
        if status is not None:
            updates["status"] = status.value if isinstance(status, JobStatus) else str(status)
        sql = "UPDATE jobs SET " + ",".join(f"{key}=?" for key in updates) + " WHERE id=?"
        with self.connect(write=True) as conn:
            cur = conn.execute(sql, [*updates.values(), job_id])
            if cur.rowcount != 1:
                raise KeyError(f"岗位不存在: {job_id}")
            self._audit_conn(conn, "JOB_UPDATED", "job", str(job_id), {"fields": list(updates)})

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE status <> 'ARCHIVED'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT j.*,
                       (SELECT COUNT(*) FROM job_candidates jc WHERE jc.job_id=j.id) AS candidate_count,
                       (SELECT COUNT(*) FROM sourcing_runs r WHERE r.job_id=j.id) AS run_count
                FROM jobs j {where}
                ORDER BY CASE j.status WHEN 'ACTIVE' THEN 0 WHEN 'PAUSED' THEN 1 ELSE 2 END,
                         j.updated_at DESC, j.id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_job(self, job_id: int) -> None:
        with self.connect(write=True) as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            self._audit_conn(conn, "JOB_DELETED", "job", str(job_id), {})

    def create_sourcing_run(self, job_id: int, query: str) -> int:
        now = now_iso()
        with self.connect(write=True) as conn:
            cur = conn.execute(
                "INSERT INTO sourcing_runs(job_id,query,status,started_at,created_at) VALUES(?,?,?,?,?)",
                (job_id, query.strip(), RunStatus.RUNNING.value, now, now),
            )
            run_id = int(cur.lastrowid)
            self._audit_conn(conn, "SOURCING_STARTED", "sourcing_run", str(run_id), {"job_id": job_id})
            return run_id

    def update_sourcing_run(
        self,
        run_id: int,
        *,
        status: RunStatus | str,
        found_count: int | None = None,
        new_count: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        diagnostic_dir: str | None = None,
    ) -> None:
        status_value = status.value if isinstance(status, RunStatus) else str(status)
        updates: dict[str, Any] = {"status": status_value}
        if found_count is not None:
            updates["found_count"] = int(found_count)
        if new_count is not None:
            updates["new_count"] = int(new_count)
        if error_code is not None:
            updates["error_code"] = error_code
        if error_message is not None:
            updates["error_message"] = error_message
        if diagnostic_dir is not None:
            updates["diagnostic_dir"] = diagnostic_dir
        if status_value in {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}:
            updates["finished_at"] = now_iso()
        sql = "UPDATE sourcing_runs SET " + ",".join(f"{key}=?" for key in updates) + " WHERE id=?"
        with self.connect(write=True) as conn:
            conn.execute(sql, [*updates.values(), run_id])
            self._audit_conn(
                conn,
                "SOURCING_STATUS_CHANGED",
                "sourcing_run",
                str(run_id),
                {"status": status_value, "error_code": error_code},
            )

    def list_sourcing_runs(self, job_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sourcing_runs WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
