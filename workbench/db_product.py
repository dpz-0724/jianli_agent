# -*- coding: utf-8 -*-
"""Single-user product repository policies: actor attribution and stale-assessment safety."""
from __future__ import annotations

import getpass
from datetime import datetime
from typing import Any


def _actor(value: str = "") -> str:
    return value.strip() or getpass.getuser() or "local-user"


def _after(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return datetime.fromisoformat(left) > datetime.fromisoformat(right)
    except ValueError:
        return left > right


class ProductRepositoryMixin:
    def _audit_conn(
        self,
        conn,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        actor: str = "",
    ) -> None:
        return super()._audit_conn(
            conn, event_type, entity_type, entity_id, payload, _actor(actor)
        )

    def confirm_job_profile(self, job_id: int, confirmed_by: str = "") -> int:
        return super().confirm_job_profile(job_id, confirmed_by=_actor(confirmed_by))

    def update_job_candidate(self, job_candidate_id: int, *, actor: str = "", **kwargs) -> None:
        return super().update_job_candidate(job_candidate_id, actor=_actor(actor), **kwargs)

    def add_review_decision(
        self,
        job_candidate_id: int,
        decision: str,
        reason: str = "",
        reviewer: str = "",
    ) -> int:
        return super().add_review_decision(
            job_candidate_id, decision, reason, reviewer=_actor(reviewer)
        )

    def add_follow_up(
        self,
        job_candidate_id: int,
        action: str,
        note: str = "",
        actor: str = "",
    ) -> int:
        return super().add_follow_up(
            job_candidate_id, action, note, actor=_actor(actor)
        )

    def export_job_csv(self, job_id: int, path, actor: str = "") -> int:
        return super().export_job_csv(job_id, path, actor=_actor(actor))

    @staticmethod
    def _mark_stale(item: dict[str, Any]) -> dict[str, Any]:
        stale = _after(str(item.get("last_seen_at") or ""), str(item.get("assessed_at") or ""))
        item["assessment_stale"] = stale
        if stale and item.get("assessment_id"):
            item["assessment_status"] = "REVIEW"
            reasons = list(item.get("reasons") or [])
            message = "候选人资料在本次评估后更新，请重新评估"
            if message not in reasons:
                reasons.append(message)
            item["reasons"] = reasons
        return item

    def list_job_candidates(
        self,
        job_id: int,
        *,
        assessment_status: str | None = None,
        stage: str | None = None,
        search: str = "",
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        rows = super().list_job_candidates(
            job_id,
            assessment_status=None if assessment_status == "REVIEW" else assessment_status,
            stage=stage,
            search=search,
            limit=limit,
        )
        normalized = [self._mark_stale(row) for row in rows]
        if assessment_status and assessment_status != "ALL":
            normalized = [row for row in normalized if row.get("assessment_status") == assessment_status]
        return normalized

    def get_job_candidate(self, job_candidate_id: int) -> dict[str, Any] | None:
        item = super().get_job_candidate(job_candidate_id)
        return self._mark_stale(item) if item else None

    def job_stats(self, job_id: int) -> dict[str, Any]:
        rows = self.list_job_candidates(job_id, limit=100000)
        assessments: dict[str, int] = {}
        stages: dict[str, int] = {}
        for row in rows:
            status = str(row.get("assessment_status") or "UNASSESSED")
            assessments[status] = assessments.get(status, 0) + 1
            stage = str(row.get("stage") or "")
            stages[stage] = stages.get(stage, 0) + 1
        return {"total": len(rows), "assessments": assessments, "stages": stages}


__all__ = ["ProductRepositoryMixin"]
