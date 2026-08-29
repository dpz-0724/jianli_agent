# -*- coding: utf-8 -*-
"""Candidate, assessment, review and follow-up repository methods."""
from __future__ import annotations

import json
from typing import Any

from .db_schema import now_iso
from .evaluation import candidate_fingerprint, sanitize_candidate, source_snapshot_hash
from .models import CandidateAssessment, CandidateStage, RequirementProfile


class CandidateMixin:
    def upsert_candidate(self, candidate: dict[str, Any], run_id: int | None = None) -> tuple[int, bool, int | None]:
        data = sanitize_candidate(candidate)
        canonical_key = candidate_fingerprint(data)
        platform = str(data.get("platform") or "zhilian")
        platform_uid = str(data.get("platform_uid") or "") or None
        source_url = str(data.get("source_url") or data.get("source") or "")
        now = now_iso()
        snapshot_hash = source_snapshot_hash(data)
        snapshot_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        with self.connect(write=True) as conn:
            existing = conn.execute("SELECT id FROM candidates WHERE canonical_key=?", (canonical_key,)).fetchone()
            created = existing is None
            if created:
                cur = conn.execute(
                    """
                    INSERT INTO candidates(
                        canonical_key,platform,platform_uid,name,title,location,education,experience,
                        activity,skills,text,source_url,age,expected_salary,certificates,full_text,first_seen_at,last_seen_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        canonical_key, platform, platform_uid, data.get("name", ""), data.get("title", ""),
                        data.get("location", ""), data.get("education", ""), data.get("experience", ""),
                        data.get("activity", ""), data.get("skills", ""), data.get("text", ""),
                        source_url, int(data.get("age") or 0), str(data.get("expected_salary") or ""),
                        str(data.get("certificates") or ""), str(data.get("full_text") or ""), now, now,
                    ),
                )
                candidate_id = int(cur.lastrowid)
            else:
                candidate_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE candidates SET platform=?,platform_uid=COALESCE(?,platform_uid),name=?,title=?,
                        location=?,education=?,experience=?,activity=?,skills=?,text=?,source_url=?,
                        age=?,expected_salary=?,certificates=?,
                        full_text=CASE WHEN ? != '' THEN ? ELSE full_text END,last_seen_at=?
                    WHERE id=?
                    """,
                    (
                        platform, platform_uid, data.get("name", ""), data.get("title", ""),
                        data.get("location", ""), data.get("education", ""), data.get("experience", ""),
                        data.get("activity", ""), data.get("skills", ""), data.get("text", ""),
                        source_url, int(data.get("age") or 0), str(data.get("expected_salary") or ""),
                        str(data.get("certificates") or ""),
                        str(data.get("full_text") or ""), str(data.get("full_text") or ""), now, candidate_id,
                    ),
                )
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO candidate_snapshots(candidate_id,run_id,source_hash,data_json,captured_at)
                VALUES(?,?,?,?,?)
                """,
                (candidate_id, run_id, snapshot_hash, snapshot_json, now),
            )
            snapshot_id = int(cur.lastrowid) if cur.lastrowid else None
            return candidate_id, created, snapshot_id

    def link_candidate_to_job(self, job_id: int, candidate_id: int) -> tuple[int, bool]:
        now = now_iso()
        with self.connect(write=True) as conn:
            row = conn.execute(
                "SELECT id FROM job_candidates WHERE job_id=? AND candidate_id=?", (job_id, candidate_id)
            ).fetchone()
            if row:
                job_candidate_id = int(row["id"])
                conn.execute("UPDATE job_candidates SET updated_at=? WHERE id=?", (now, job_candidate_id))
                return job_candidate_id, False
            cur = conn.execute(
                "INSERT INTO job_candidates(job_id,candidate_id,stage,created_at,updated_at) VALUES(?,?,?,?,?)",
                (job_id, candidate_id, CandidateStage.TO_REVIEW.value, now, now),
            )
            job_candidate_id = int(cur.lastrowid)
            self._audit_conn(
                conn, "CANDIDATE_LINKED", "job_candidate", str(job_candidate_id),
                {"job_id": job_id, "candidate_id": candidate_id},
            )
            return job_candidate_id, True

    def save_assessment(
        self, job_candidate_id: int, assessment: CandidateAssessment, profile: RequirementProfile
    ) -> int:
        with self.connect(write=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO assessments(
                    job_candidate_id,engine_version,parser_version,status,fit_score,reasons_json,
                    evidence_json,requirements_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_candidate_id, assessment.engine_version, profile.parser_version,
                    assessment.status.value, assessment.fit_score,
                    json.dumps(list(assessment.reasons), ensure_ascii=False),
                    json.dumps(assessment.evidence, ensure_ascii=False),
                    json.dumps(profile.as_dict(), ensure_ascii=False), now_iso(),
                ),
            )
            assessment_id = int(cur.lastrowid)
            self._audit_conn(
                conn, "ASSESSMENT_SAVED", "assessment", str(assessment_id),
                {"job_candidate_id": job_candidate_id, "status": assessment.status.value},
            )
            return assessment_id

    def list_job_candidates(
        self,
        job_id: int,
        *,
        assessment_status: str | None = None,
        stage: str | None = None,
        search: str = "",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        conditions = ["jc.job_id=?"]
        args: list[Any] = [job_id]
        if assessment_status and assessment_status != "ALL":
            conditions.append("a.status=?")
            args.append(assessment_status)
        if stage and stage != "ALL":
            conditions.append("jc.stage=?")
            args.append(stage)
        if search.strip():
            token = f"%{search.strip()}%"
            conditions.append("(c.name LIKE ? OR c.title LIKE ? OR c.skills LIKE ? OR c.text LIKE ?)")
            args.extend([token, token, token, token])
        args.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT jc.id AS job_candidate_id,jc.stage,jc.owner,jc.note,jc.next_follow_up_at,
                    c.id AS candidate_id,c.name,c.title,c.location,c.education,c.experience,
                    c.activity,c.skills,c.text,c.source_url,c.last_seen_at,
                    c.age,c.expected_salary,c.certificates,c.full_text,
                    a.id AS assessment_id,a.status AS assessment_status,a.fit_score,
                    a.reasons_json,a.evidence_json,a.engine_version,a.created_at AS assessed_at
                FROM job_candidates jc JOIN candidates c ON c.id=jc.candidate_id
                LEFT JOIN assessments a ON a.id=(
                    SELECT a2.id FROM assessments a2 WHERE a2.job_candidate_id=jc.id ORDER BY a2.id DESC LIMIT 1
                )
                WHERE {' AND '.join(conditions)}
                ORDER BY CASE COALESCE(a.status,'REVIEW') WHEN 'PASS' THEN 0 WHEN 'REVIEW' THEN 1 ELSE 2 END,
                    COALESCE(a.fit_score,0) DESC,jc.id DESC LIMIT ?
                """,
                args,
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
                item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
                result.append(item)
            return result

    def pipeline_dashboard(self) -> dict[str, Any]:
        """跨岗位工作台：漏斗统计 + 各岗位分布 + 该跟进的候选人。"""
        with self.connect() as conn:
            # 各招聘阶段数量（跨全部未归档岗位）
            stage_rows = conn.execute(
                """
                SELECT jc.stage, COUNT(*) AS n
                FROM job_candidates jc JOIN jobs j ON j.id=jc.job_id
                WHERE j.status <> 'ARCHIVED'
                GROUP BY jc.stage
                """
            ).fetchall()
            stage_counts = {r["stage"]: r["n"] for r in stage_rows}
            total = sum(stage_counts.values())

            # 各岗位概览
            job_rows = conn.execute(
                """
                SELECT j.id, j.title,
                       COUNT(jc.id) AS cnt,
                       SUM(CASE WHEN jc.stage='TO_CONTACT' THEN 1 ELSE 0 END) AS to_contact,
                       SUM(CASE WHEN jc.stage='CONTACTED' THEN 1 ELSE 0 END) AS contacted,
                       SUM(CASE WHEN jc.stage='INTERVIEW' THEN 1 ELSE 0 END) AS interview
                FROM jobs j LEFT JOIN job_candidates jc ON jc.job_id=j.id
                WHERE j.status <> 'ARCHIVED'
                GROUP BY j.id, j.title
                ORDER BY cnt DESC, j.id DESC LIMIT 12
                """
            ).fetchall()

            # 该跟进的候选人：待联系 / 已联系 / 约面（按最近更新排序）
            follow_rows = conn.execute(
                """
                SELECT jc.id AS job_candidate_id, jc.job_id, jc.stage, jc.note, jc.updated_at,
                       j.title AS job_title,
                       c.name, c.title, c.location, c.education, c.age, c.expected_salary, c.activity,
                       a.status AS assessment_status, a.fit_score
                FROM job_candidates jc
                JOIN jobs j ON j.id=jc.job_id
                JOIN candidates c ON c.id=jc.candidate_id
                LEFT JOIN assessments a ON a.id=(
                    SELECT a2.id FROM assessments a2 WHERE a2.job_candidate_id=jc.id ORDER BY a2.id DESC LIMIT 1
                )
                WHERE j.status <> 'ARCHIVED' AND jc.stage IN ('TO_CONTACT','CONTACTED','INTERVIEW')
                ORDER BY CASE jc.stage WHEN 'INTERVIEW' THEN 0 WHEN 'TO_CONTACT' THEN 1 ELSE 2 END,
                         jc.updated_at DESC LIMIT 50
                """
            ).fetchall()

        return {
            "stage_counts": stage_counts,
            "total": total,
            "jobs": [dict(r) for r in job_rows],
            "follow_ups": [dict(r) for r in follow_rows],
        }

    def get_job_candidate(self, job_candidate_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT jc.*,c.*,jc.id AS job_candidate_id,c.id AS candidate_id,
                    a.status AS assessment_status,a.fit_score,a.reasons_json,a.evidence_json,
                    a.engine_version,a.created_at AS assessed_at
                FROM job_candidates jc JOIN candidates c ON c.id=jc.candidate_id
                LEFT JOIN assessments a ON a.id=(
                    SELECT id FROM assessments WHERE job_candidate_id=jc.id ORDER BY id DESC LIMIT 1
                ) WHERE jc.id=?
                """,
                (job_candidate_id,),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
            item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
            return item

    def update_job_candidate(
        self,
        job_candidate_id: int,
        *,
        stage: CandidateStage | str | None = None,
        owner: str | None = None,
        note: str | None = None,
        next_follow_up_at: str | None = None,
        actor: str = "",
    ) -> None:
        updates: dict[str, Any] = {"updated_at": now_iso()}
        if stage is not None:
            updates["stage"] = stage.value if isinstance(stage, CandidateStage) else str(stage)
        if owner is not None:
            updates["owner"] = owner.strip()
        if note is not None:
            updates["note"] = note
        if next_follow_up_at is not None:
            updates["next_follow_up_at"] = next_follow_up_at or None
        sql = "UPDATE job_candidates SET " + ",".join(f"{key}=?" for key in updates) + " WHERE id=?"
        with self.connect(write=True) as conn:
            conn.execute(sql, [*updates.values(), job_candidate_id])
            self._audit_conn(
                conn, "JOB_CANDIDATE_UPDATED", "job_candidate", str(job_candidate_id),
                {"fields": list(updates), "actor": actor}, actor,
            )

    def add_review_decision(
        self, job_candidate_id: int, decision: str, reason: str = "", reviewer: str = ""
    ) -> int:
        with self.connect(write=True) as conn:
            cur = conn.execute(
                "INSERT INTO review_decisions(job_candidate_id,decision,reason,reviewer,created_at) VALUES(?,?,?,?,?)",
                (job_candidate_id, decision, reason, reviewer, now_iso()),
            )
            decision_id = int(cur.lastrowid)
            self._audit_conn(
                conn, "REVIEW_DECISION_ADDED", "job_candidate", str(job_candidate_id),
                {"decision": decision, "reason": reason}, reviewer,
            )
            return decision_id

    def add_follow_up(self, job_candidate_id: int, action: str, note: str = "", actor: str = "") -> int:
        with self.connect(write=True) as conn:
            cur = conn.execute(
                "INSERT INTO follow_ups(job_candidate_id,action,note,actor,created_at) VALUES(?,?,?,?,?)",
                (job_candidate_id, action, note, actor, now_iso()),
            )
            follow_up_id = int(cur.lastrowid)
            self._audit_conn(
                conn, "FOLLOW_UP_ADDED", "job_candidate", str(job_candidate_id), {"action": action}, actor
            )
            return follow_up_id

    def list_reviews(self, job_candidate_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_decisions WHERE job_candidate_id=? ORDER BY id DESC", (job_candidate_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def list_follow_ups(self, job_candidate_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM follow_ups WHERE job_candidate_id=? ORDER BY id DESC", (job_candidate_id,)
            ).fetchall()
            return [dict(row) for row in rows]
