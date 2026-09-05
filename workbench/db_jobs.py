# -*- coding: utf-8 -*-
"""Job and sourcing-run repository methods."""
from __future__ import annotations

import json
from typing import Any

from .db_schema import now_iso
from .models import JobStatus, ProfileStatus, RequirementProfile, RunStatus, SearchPlan


class JobRunMixin:
    def create_job(self, title: str, keyword: str = "", jd: str = "") -> int:
        title = title.strip()
        if not title:
            raise ValueError("岗位名称不能为空")
        now = now_iso()
        with self.connect(write=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO jobs(
                    title,keyword,jd,profile_status,profile_version,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    title, keyword.strip(), jd.strip(), ProfileStatus.DRAFT.value, 0,
                    JobStatus.ACTIVE.value, now, now,
                ),
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
        profile_status: ProfileStatus | str | None = None,
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
        if profile_status is not None:
            updates["profile_status"] = (
                profile_status.value if isinstance(profile_status, ProfileStatus) else str(profile_status)
            )
            if updates["profile_status"] == ProfileStatus.DRAFT.value:
                updates["confirmed_at"] = None
                updates["confirmed_by"] = ""
        if status is not None:
            updates["status"] = status.value if isinstance(status, JobStatus) else str(status)
        sql = "UPDATE jobs SET " + ",".join(f"{key}=?" for key in updates) + " WHERE id=?"
        with self.connect(write=True) as conn:
            cur = conn.execute(sql, [*updates.values(), job_id])
            if cur.rowcount != 1:
                raise KeyError(f"岗位不存在: {job_id}")
            self._audit_conn(conn, "JOB_UPDATED", "job", str(job_id), {"fields": list(updates)})

    def confirm_job_profile(self, job_id: int, confirmed_by: str = "") -> int:
        """Make the current parsed profile authoritative and return its new version."""
        now = now_iso()
        with self.connect(write=True) as conn:
            row = conn.execute(
                "SELECT requirements_json,profile_version FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"岗位不存在: {job_id}")
            raw = str(row["requirements_json"] or "{}")
            try:
                profile = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError("岗位画像数据损坏，请重新解析") from error
            if not profile:
                raise ValueError("请先解析并保存岗位画像")
            version = int(row["profile_version"] or 0) + 1
            conn.execute(
                """
                UPDATE jobs SET profile_status=?,profile_version=?,confirmed_at=?,confirmed_by=?,updated_at=?
                WHERE id=?
                """,
                (ProfileStatus.CONFIRMED.value, version, now, confirmed_by.strip(), now, job_id),
            )
            self._audit_conn(
                conn,
                "JOB_PROFILE_CONFIRMED",
                "job",
                str(job_id),
                {"profile_version": version},
                confirmed_by,
            )
            return version

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

    def create_sourcing_run(self, job_id: int, query: str, plan: SearchPlan | None = None) -> int:
        normalized = (plan or SearchPlan(query=query)).normalized()
        if not normalized.query:
            raise ValueError("搜索关键词不能为空")
        now = now_iso()
        with self.connect(write=True) as conn:
            job = conn.execute("SELECT profile_status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise KeyError(f"岗位不存在: {job_id}")
            if job["profile_status"] != ProfileStatus.CONFIRMED.value:
                raise ValueError("岗位标准尚未确认，不能开始搜索")
            cur = conn.execute(
                """
                INSERT INTO sourcing_runs(
                    job_id,query,status,max_pages,max_count,browser_mode,checkpoint_json,
                    started_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id, normalized.query, RunStatus.RUNNING.value, normalized.max_pages,
                    normalized.max_count, normalized.browser_mode, "{}", now, now,
                ),
            )
            run_id = int(cur.lastrowid)
            self._audit_conn(
                conn,
                "SOURCING_STARTED",
                "sourcing_run",
                str(run_id),
                {
                    "job_id": job_id,
                    "max_pages": normalized.max_pages,
                    "max_count": normalized.max_count,
                    "browser_mode": normalized.browser_mode,
                },
            )
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
        last_page: int | None = None,
        checkpoint: dict[str, Any] | None = None,
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
        if last_page is not None:
            updates["last_page"] = max(0, int(last_page))
        if checkpoint is not None:
            updates["checkpoint_json"] = json.dumps(checkpoint, ensure_ascii=False)
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
                {"status": status_value, "error_code": error_code, "last_page": last_page},
            )

    def get_sourcing_run(self, run_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sourcing_runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def list_sourcing_runs(self, job_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sourcing_runs WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_incomplete_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*,j.title AS job_title FROM sourcing_runs r
                JOIN jobs j ON j.id=r.job_id
                WHERE r.status IN ('RUNNING','NEED_LOGIN','PAUSED','TAKEOVER')
                ORDER BY r.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
