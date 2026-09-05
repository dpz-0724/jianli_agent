# -*- coding: utf-8 -*-
"""Single-user product repository policies: identity safety, attribution and stale assessments."""
from __future__ import annotations

import getpass
from datetime import datetime
from pathlib import Path
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

    def _lookup_candidate_conn(self, conn, identities, canonical_key: str) -> tuple[int | None, str]:
        """Prefer exact aliases; only use fuzzy migration when a new platform UID exists.

        A no-UID candidate whose text or title changes is safer as a visible duplicate
        than as a silent false merge. The stable signature is therefore used only to bind
        a newly discovered platform UID to one unique legacy candidate that previously
        lacked an exact identity.
        """
        exact_kinds = {"platform_uid", "source_url", "fingerprint"}
        for kind, key, _confidence in identities:
            if kind not in exact_kinds:
                continue
            row = conn.execute(
                """
                SELECT ci.candidate_id FROM candidate_identities ci
                JOIN candidates c ON c.id=ci.candidate_id
                WHERE ci.kind=? AND ci.identity_key=? AND c.merged_into_candidate_id IS NULL
                LIMIT 1
                """,
                (kind, key),
            ).fetchone()
            if row:
                return int(row["candidate_id"]), kind

        row = conn.execute(
            "SELECT id FROM candidates WHERE canonical_key=? AND merged_into_candidate_id IS NULL",
            (canonical_key,),
        ).fetchone()
        if row:
            return int(row["id"]), "legacy_canonical_key"

        incoming_has_uid = any(kind == "platform_uid" for kind, _key, _confidence in identities)
        stable_keys = [key for kind, key, _confidence in identities if kind == "stable_signature"]
        if incoming_has_uid and stable_keys:
            rows = conn.execute(
                """
                SELECT DISTINCT ci.candidate_id FROM candidate_identities ci
                JOIN candidates c ON c.id=ci.candidate_id
                WHERE ci.kind='stable_signature' AND ci.identity_key=?
                  AND c.merged_into_candidate_id IS NULL
                  AND COALESCE(c.platform_uid,'')=''
                LIMIT 2
                """,
                (stable_keys[0],),
            ).fetchall()
            if len(rows) == 1:
                return int(rows[0]["candidate_id"]), "stable_signature_uid_migration"
        return None, ""

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

    def merge_candidates(self, primary_id: int, duplicate_id: int, actor: str = "") -> None:
        """Create a recoverable database backup before an irreversible identity merge."""
        backup_dir = Path(self.path).parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"before-candidate-merge-{primary_id}-{duplicate_id}-{stamp}.db"
        self.backup_to(backup_path)
        resolved_actor = _actor(actor)
        super().merge_candidates(primary_id, duplicate_id, actor=resolved_actor)
        with self.connect(write=True) as conn:
            self._audit_conn(
                conn,
                "CANDIDATE_MERGE_BACKUP_CREATED",
                "candidate",
                str(primary_id),
                {"duplicate_candidate_id": duplicate_id, "backup_path": str(backup_path)},
                resolved_actor,
            )

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
