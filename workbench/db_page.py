# -*- coding: utf-8 -*-
"""Atomic sourcing-page persistence.

A page checkpoint is advanced in the same SQLite transaction that stores candidate
identities, snapshots, job links and assessments. This is the durable recovery boundary.
"""
from __future__ import annotations

import json
from typing import Any

from .db_schema import now_iso
from .models import CandidateAssessment, RequirementProfile, RunStatus


class SourcingPageMixin:
    def persist_sourcing_page(
        self,
        *,
        job_id: int,
        run_id: int,
        page_no: int,
        entries: list[tuple[dict[str, Any], CandidateAssessment]],
        profile: RequirementProfile,
    ) -> dict[str, Any]:
        page_no = int(page_no)
        if page_no < 1:
            raise ValueError("页面编号必须大于等于 1")

        with self.connect(write=True) as conn:
            run = conn.execute(
                "SELECT * FROM sourcing_runs WHERE id=? AND job_id=?",
                (run_id, job_id),
            ).fetchone()
            if not run:
                raise KeyError(f"招聘任务不存在或岗位不匹配: {run_id}")

            last_page = int(run["last_page"] or 0)
            found_before = int(run["found_count"] or 0)
            new_before = int(run["new_count"] or 0)
            if page_no <= last_page:
                return {
                    "already_persisted": True,
                    "page_found": 0,
                    "page_new_candidates": 0,
                    "page_new_job_links": 0,
                    "found_total": found_before,
                    "new_total": new_before,
                    "last_page": last_page,
                }
            if page_no != last_page + 1:
                raise ValueError(
                    f"页面检查点不连续：数据库已提交第 {last_page} 页，本次收到第 {page_no} 页"
                )

            page_found = 0
            page_new_candidates = 0
            page_new_job_links = 0
            for candidate, assessment in entries:
                page_found += 1
                candidate_id, created, _snapshot_id = self._upsert_candidate_conn(
                    conn, candidate, run_id
                )
                job_candidate_id, linked = self._link_candidate_to_job_conn(
                    conn, job_id, candidate_id
                )
                assessment_id = self._save_assessment_conn(
                    conn, job_candidate_id, assessment, profile
                )
                page_new_candidates += int(created)
                page_new_job_links += int(linked)
                self._audit_conn(
                    conn,
                    "ASSESSMENT_SAVED",
                    "assessment",
                    str(assessment_id),
                    {
                        "job_candidate_id": job_candidate_id,
                        "status": assessment.status.value,
                        "run_id": run_id,
                        "page_no": page_no,
                    },
                )

            found_total = found_before + page_found
            new_total = new_before + page_new_job_links
            checkpoint = {
                "last_completed_page": page_no,
                "persisted_candidate_count": found_total,
                "new_job_links": new_total,
                "query": str(run["query"] or ""),
                "committed_at": now_iso(),
            }
            conn.execute(
                """
                UPDATE sourcing_runs
                   SET status=?,found_count=?,new_count=?,last_page=?,checkpoint_json=?,
                       error_code=NULL,error_message=NULL
                 WHERE id=? AND job_id=?
                """,
                (
                    RunStatus.RUNNING.value,
                    found_total,
                    new_total,
                    page_no,
                    json.dumps(checkpoint, ensure_ascii=False),
                    run_id,
                    job_id,
                ),
            )
            self._audit_conn(
                conn,
                "SOURCING_PAGE_COMMITTED",
                "sourcing_run",
                str(run_id),
                {
                    "job_id": job_id,
                    "page_no": page_no,
                    "page_found": page_found,
                    "page_new_candidates": page_new_candidates,
                    "page_new_job_links": page_new_job_links,
                    "found_total": found_total,
                    "new_total": new_total,
                },
            )
            return {
                "already_persisted": False,
                "page_found": page_found,
                "page_new_candidates": page_new_candidates,
                "page_new_job_links": page_new_job_links,
                "found_total": found_total,
                "new_total": new_total,
                "last_page": page_no,
            }


__all__ = ["SourcingPageMixin"]
