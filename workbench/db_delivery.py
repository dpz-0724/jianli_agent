# -*- coding: utf-8 -*-
"""Delivery-grade database operations: identity resolution, batch persistence and backup."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

from .db_schema import now_iso
from .evaluation import candidate_fingerprint, sanitize_candidate, source_snapshot_hash
from .models import CandidateAssessment, CandidateStage, RequirementProfile

_EXACT_IDENTITY_KINDS = {"platform_uid", "source_url", "fingerprint"}
_STAGE_RANK = {
    CandidateStage.NEW.value: 0,
    CandidateStage.TO_REVIEW.value: 1,
    CandidateStage.TO_CONTACT.value: 2,
    CandidateStage.CONTACTED.value: 3,
    CandidateStage.INTERVIEW.value: 4,
    CandidateStage.OFFER.value: 5,
    CandidateStage.HIRED.value: 6,
    CandidateStage.REJECTED.value: 6,
    CandidateStage.TALENT_POOL.value: 4,
}


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _source_identity(url: str) -> str:
    raw = (url or "").strip()
    if not raw.lower().startswith(("http://", "https://")):
        return ""
    parsed = urlparse(raw)
    if parsed.path.rstrip("/").lower().endswith("/app/search"):
        return ""
    query = parse_qs(parsed.query)
    for key in ("resumeId", "resumeid", "encResumeId", "resumeNumber", "candidateId", "userId"):
        value = (query.get(key) or [""])[0]
        if value:
            return f"{parsed.netloc.lower()}:{key.lower()}:{value}"
    if any(token in parsed.path.lower() for token in ("resume", "candidate", "talent")):
        return f"{parsed.netloc.lower()}:{parsed.path.rstrip('/').lower()}"
    return ""


def _title_family(value: Any) -> str:
    title = _normalized(value)
    for token in ("资深", "高级", "中级", "初级", "专家", "工程师", "经理", "主管", "专员"):
        title = title.replace(token, "")
    return title.strip(" -_/·")


def _stable_signature(data: dict[str, Any]) -> str:
    name = _normalized(data.get("name"))
    title_family = _title_family(data.get("title"))
    stable = [
        title_family,
        _normalized(data.get("location")),
        _normalized(data.get("education")),
        _normalized(data.get("experience")),
    ]
    if not name or not title_family or sum(bool(item) for item in stable[1:]) < 2:
        return ""
    raw = "|".join([name, *stable])
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:40]


class DeliveryDatabaseMixin:
    """Overrides focused repository methods without changing legacy call sites."""

    def __init__(self, *args, **kwargs):
        self._delivery_lock = threading.RLock()
        super().__init__(*args, **kwargs)
        self._backfill_candidate_identities()

    def _backfill_candidate_identities(self) -> None:
        """Lazily attach identity aliases to candidates created by pre-V3 builds."""
        with self.connect(write=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM candidates
                WHERE merged_into_candidate_id IS NULL
                  AND NOT EXISTS (SELECT 1 FROM candidate_identities ci WHERE ci.candidate_id=candidates.id)
                """
            ).fetchall()
            for row in rows:
                data = dict(row)
                data["source"] = data.get("source_url", "")
                self._attach_identities_conn(conn, int(row["id"]), self._identities(data))

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with self._delivery_lock:
            with super().connect(write=write) as conn:
                yield conn

    @staticmethod
    def _assert_integrity(path: Path) -> None:
        conn = sqlite3.connect(path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise ValueError(f"数据库完整性检查失败：{result[0] if result else '无结果'}")
        finally:
            conn.close()

    def backup_to(self, path: str | os.PathLike[str]) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with self._delivery_lock:
            if temporary.exists():
                temporary.unlink()
            source = sqlite3.connect(self.path, timeout=30)
            target = sqlite3.connect(temporary)
            try:
                source.execute("PRAGMA wal_checkpoint(FULL)")
                source.backup(target)
                target.commit()
            finally:
                target.close()
                source.close()
            self._assert_integrity(temporary)
            temporary.replace(destination)
            metadata = {
                "created_at": now_iso(),
                "source": str(self.path),
                "database_size": destination.stat().st_size,
            }
            destination.with_suffix(destination.suffix + ".json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return destination

    def restore_from(self, path: str | os.PathLike[str]) -> Path:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"备份文件不存在：{source}")
        self._assert_integrity(source)
        with self._delivery_lock:
            backup_dir = self.path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            pre_restore = backup_dir / f"before-restore-{stamp}.db"
            if self.path.exists():
                self.backup_to(pre_restore)
            replacement = self.path.with_suffix(".restore.tmp")
            shutil.copy2(source, replacement)
            self._assert_integrity(replacement)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            replacement.replace(self.path)
            self._initialize()
        return pre_restore

    @staticmethod
    def _identities(data: dict[str, Any]) -> list[tuple[str, str, int]]:
        platform = _normalized(data.get("platform") or "zhilian")
        identities: list[tuple[str, str, int]] = []
        uid = _normalized(data.get("platform_uid"))
        if uid:
            identities.append(("platform_uid", f"{platform}:{uid}", 100))
        source = _source_identity(str(data.get("source_url") or data.get("source") or ""))
        if source:
            identities.append(("source_url", source, 95))
        fingerprint = candidate_fingerprint(data)
        if fingerprint:
            identities.append(("fingerprint", fingerprint, 80))
        signature = _stable_signature(data)
        if signature:
            identities.append(("stable_signature", signature, 55))
        return identities

    @staticmethod
    def _lookup_candidate_conn(
        conn: sqlite3.Connection,
        identities: list[tuple[str, str, int]],
        canonical_key: str,
    ) -> tuple[int | None, str]:
        for kind, key, _confidence in identities:
            if kind not in _EXACT_IDENTITY_KINDS:
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
        fuzzy = [key for kind, key, _confidence in identities if kind == "stable_signature"]
        if fuzzy:
            rows = conn.execute(
                """
                SELECT DISTINCT ci.candidate_id FROM candidate_identities ci
                JOIN candidates c ON c.id=ci.candidate_id
                WHERE ci.kind='stable_signature' AND ci.identity_key=?
                  AND c.merged_into_candidate_id IS NULL
                LIMIT 2
                """,
                (fuzzy[0],),
            ).fetchall()
            if len(rows) == 1:
                return int(rows[0]["candidate_id"]), "stable_signature"
        return None, ""

    def _attach_identities_conn(
        self,
        conn: sqlite3.Connection,
        candidate_id: int,
        identities: list[tuple[str, str, int]],
    ) -> None:
        for kind, key, confidence in identities:
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_identities(
                    candidate_id,kind,identity_key,confidence,created_at
                ) VALUES(?,?,?,?,?)
                """,
                (candidate_id, kind, key, confidence, now_iso()),
            )

    def _upsert_candidate_conn(
        self,
        conn: sqlite3.Connection,
        candidate: dict[str, Any],
        run_id: int | None,
    ) -> tuple[int, bool, int | None]:
        data = sanitize_candidate(candidate)
        canonical_key = candidate_fingerprint(data)
        identities = self._identities(data)
        candidate_id, matched_by = self._lookup_candidate_conn(conn, identities, canonical_key)
        platform = str(data.get("platform") or "zhilian")
        platform_uid = str(data.get("platform_uid") or "") or None
        source_url = str(data.get("source_url") or data.get("source") or "")
        now = now_iso()
        created = candidate_id is None
        if created:
            cur = conn.execute(
                """
                INSERT INTO candidates(
                    canonical_key,platform,platform_uid,name,title,location,education,experience,
                    activity,skills,text,source_url,first_seen_at,last_seen_at,merged_into_candidate_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
                """,
                (
                    canonical_key, platform, platform_uid, data.get("name", ""), data.get("title", ""),
                    data.get("location", ""), data.get("education", ""), data.get("experience", ""),
                    data.get("activity", ""), data.get("skills", ""), data.get("text", ""),
                    source_url, now, now,
                ),
            )
            candidate_id = int(cur.lastrowid)
        else:
            conn.execute(
                """
                UPDATE candidates SET
                    platform=COALESCE(NULLIF(?,''),platform),
                    platform_uid=COALESCE(NULLIF(?,''),platform_uid),
                    name=COALESCE(NULLIF(?,''),name),
                    title=COALESCE(NULLIF(?,''),title),
                    location=COALESCE(NULLIF(?,''),location),
                    education=COALESCE(NULLIF(?,''),education),
                    experience=COALESCE(NULLIF(?,''),experience),
                    activity=COALESCE(NULLIF(?,''),activity),
                    skills=COALESCE(NULLIF(?,''),skills),
                    text=COALESCE(NULLIF(?,''),text),
                    source_url=COALESCE(NULLIF(?,''),source_url),
                    last_seen_at=?
                WHERE id=?
                """,
                (
                    platform, platform_uid or "", data.get("name", ""), data.get("title", ""),
                    data.get("location", ""), data.get("education", ""), data.get("experience", ""),
                    data.get("activity", ""), data.get("skills", ""), data.get("text", ""),
                    source_url, now, candidate_id,
                ),
            )
        self._attach_identities_conn(conn, candidate_id, identities)
        snapshot_hash = source_snapshot_hash(data)
        snapshot_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO candidate_snapshots(candidate_id,run_id,source_hash,data_json,captured_at)
            VALUES(?,?,?,?,?)
            """,
            (candidate_id, run_id, snapshot_hash, snapshot_json, now),
        )
        snapshot_id = int(cur.lastrowid) if cur.lastrowid else None
        if not created and matched_by:
            self._audit_conn(
                conn,
                "CANDIDATE_MATCHED",
                "candidate",
                str(candidate_id),
                {"matched_by": matched_by, "run_id": run_id},
            )
        return candidate_id, created, snapshot_id

    def upsert_candidate(
        self, candidate: dict[str, Any], run_id: int | None = None
    ) -> tuple[int, bool, int | None]:
        with self.connect(write=True) as conn:
            return self._upsert_candidate_conn(conn, candidate, run_id)

    @staticmethod
    def _link_candidate_to_job_conn(
        conn: sqlite3.Connection, job_id: int, candidate_id: int
    ) -> tuple[int, bool]:
        now = now_iso()
        row = conn.execute(
            "SELECT id FROM job_candidates WHERE job_id=? AND candidate_id=?",
            (job_id, candidate_id),
        ).fetchone()
        if row:
            job_candidate_id = int(row["id"])
            conn.execute("UPDATE job_candidates SET updated_at=? WHERE id=?", (now, job_candidate_id))
            return job_candidate_id, False
        cur = conn.execute(
            "INSERT INTO job_candidates(job_id,candidate_id,stage,created_at,updated_at) VALUES(?,?,?,?,?)",
            (job_id, candidate_id, CandidateStage.TO_REVIEW.value, now, now),
        )
        return int(cur.lastrowid), True

    @staticmethod
    def _save_assessment_conn(
        conn: sqlite3.Connection,
        job_candidate_id: int,
        assessment: CandidateAssessment,
        profile: RequirementProfile,
    ) -> int:
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
        return int(cur.lastrowid)

    def persist_candidate_assessment_batch(
        self,
        *,
        job_id: int,
        run_id: int | None,
        entries: list[tuple[dict[str, Any], CandidateAssessment]],
        profile: RequirementProfile,
    ) -> dict[str, int]:
        counts = {"found": 0, "new_candidates": 0, "new_job_links": 0}
        with self.connect(write=True) as conn:
            for candidate, assessment in entries:
                counts["found"] += 1
                candidate_id, created, _snapshot_id = self._upsert_candidate_conn(conn, candidate, run_id)
                job_candidate_id, linked = self._link_candidate_to_job_conn(conn, job_id, candidate_id)
                assessment_id = self._save_assessment_conn(conn, job_candidate_id, assessment, profile)
                counts["new_candidates"] += int(created)
                counts["new_job_links"] += int(linked)
                self._audit_conn(
                    conn,
                    "ASSESSMENT_SAVED",
                    "assessment",
                    str(assessment_id),
                    {"job_candidate_id": job_candidate_id, "status": assessment.status.value},
                )
        return counts

    def merge_candidates(self, primary_id: int, duplicate_id: int, actor: str = "") -> None:
        if primary_id == duplicate_id:
            raise ValueError("不能合并同一个候选人")
        with self.connect(write=True) as conn:
            primary = conn.execute("SELECT * FROM candidates WHERE id=?", (primary_id,)).fetchone()
            duplicate = conn.execute("SELECT * FROM candidates WHERE id=?", (duplicate_id,)).fetchone()
            if not primary or not duplicate:
                raise KeyError("候选人不存在")
            if primary["merged_into_candidate_id"] or duplicate["merged_into_candidate_id"]:
                raise ValueError("只能合并尚未被合并的候选人")

            links = conn.execute("SELECT * FROM job_candidates WHERE candidate_id=?", (duplicate_id,)).fetchall()
            for link in links:
                existing = conn.execute(
                    "SELECT * FROM job_candidates WHERE job_id=? AND candidate_id=?",
                    (link["job_id"], primary_id),
                ).fetchone()
                if existing:
                    primary_stage = str(existing["stage"])
                    duplicate_stage = str(link["stage"])
                    best_stage = (
                        duplicate_stage
                        if _STAGE_RANK.get(duplicate_stage, 0) > _STAGE_RANK.get(primary_stage, 0)
                        else primary_stage
                    )
                    conn.execute(
                        """
                        UPDATE job_candidates SET stage=?,owner=COALESCE(NULLIF(owner,''),?),
                            note=CASE WHEN note='' THEN ? ELSE note END,
                            next_follow_up_at=COALESCE(next_follow_up_at,?),updated_at=? WHERE id=?
                        """,
                        (
                            best_stage, link["owner"], link["note"], link["next_follow_up_at"],
                            now_iso(), existing["id"],
                        ),
                    )
                    for table in ("assessments", "review_decisions", "follow_ups"):
                        conn.execute(
                            f"UPDATE {table} SET job_candidate_id=? WHERE job_candidate_id=?",
                            (existing["id"], link["id"]),
                        )
                    conn.execute("DELETE FROM job_candidates WHERE id=?", (link["id"],))
                else:
                    conn.execute(
                        "UPDATE job_candidates SET candidate_id=?,updated_at=? WHERE id=?",
                        (primary_id, now_iso(), link["id"]),
                    )

            snapshots = conn.execute(
                "SELECT run_id,source_hash,data_json,captured_at FROM candidate_snapshots WHERE candidate_id=?",
                (duplicate_id,),
            ).fetchall()
            for snapshot in snapshots:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO candidate_snapshots(
                        candidate_id,run_id,source_hash,data_json,captured_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (primary_id, snapshot["run_id"], snapshot["source_hash"], snapshot["data_json"], snapshot["captured_at"]),
                )
            conn.execute("DELETE FROM candidate_snapshots WHERE candidate_id=?", (duplicate_id,))

            identities = conn.execute(
                "SELECT kind,identity_key,confidence,created_at FROM candidate_identities WHERE candidate_id=?",
                (duplicate_id,),
            ).fetchall()
            for identity in identities:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO candidate_identities(
                        candidate_id,kind,identity_key,confidence,created_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (primary_id, identity["kind"], identity["identity_key"], identity["confidence"], identity["created_at"]),
                )
            conn.execute("DELETE FROM candidate_identities WHERE candidate_id=?", (duplicate_id,))
            conn.execute(
                "UPDATE candidates SET merged_into_candidate_id=?,last_seen_at=? WHERE id=?",
                (primary_id, now_iso(), duplicate_id),
            )
            self._audit_conn(
                conn,
                "CANDIDATES_MERGED",
                "candidate",
                str(primary_id),
                {"duplicate_candidate_id": duplicate_id},
                actor,
            )
