# -*- coding: utf-8 -*-
"""SQLite schema, migrations and shared database helpers."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 3


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "RecruitmentWorkbench"


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, keyword TEXT NOT NULL DEFAULT '',
 jd TEXT NOT NULL DEFAULT '', requirements_json TEXT NOT NULL DEFAULT '{}',
 profile_status TEXT NOT NULL DEFAULT 'DRAFT', profile_version INTEGER NOT NULL DEFAULT 0,
 confirmed_at TEXT, confirmed_by TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sourcing_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 query TEXT NOT NULL, status TEXT NOT NULL, found_count INTEGER NOT NULL DEFAULT 0,
 new_count INTEGER NOT NULL DEFAULT 0, max_pages INTEGER NOT NULL DEFAULT 5,
 max_count INTEGER NOT NULL DEFAULT 200, browser_mode TEXT NOT NULL DEFAULT 'managed',
 checkpoint_json TEXT NOT NULL DEFAULT '{}', last_page INTEGER NOT NULL DEFAULT 0,
 error_code TEXT, error_message TEXT, diagnostic_dir TEXT,
 started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_job ON sourcing_runs(job_id,id DESC);
CREATE TABLE IF NOT EXISTS candidates (
 id INTEGER PRIMARY KEY AUTOINCREMENT, canonical_key TEXT NOT NULL UNIQUE,
 platform TEXT NOT NULL DEFAULT 'zhilian', platform_uid TEXT, name TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '', education TEXT NOT NULL DEFAULT '',
 experience TEXT NOT NULL DEFAULT '', activity TEXT NOT NULL DEFAULT '', skills TEXT NOT NULL DEFAULT '',
 text TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
 age INTEGER NOT NULL DEFAULT 0, expected_salary TEXT NOT NULL DEFAULT '', certificates TEXT NOT NULL DEFAULT '',
 first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 merged_into_candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_candidates_uid ON candidates(platform,platform_uid);
CREATE TABLE IF NOT EXISTS candidate_identities (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, identity_key TEXT NOT NULL, confidence INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 UNIQUE(candidate_id,kind,identity_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_identity_exact
 ON candidate_identities(kind,identity_key)
 WHERE kind IN ('platform_uid','source_url','fingerprint');
CREATE INDEX IF NOT EXISTS idx_candidate_identity_lookup
 ON candidate_identities(kind,identity_key,candidate_id);
CREATE TABLE IF NOT EXISTS candidate_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 run_id INTEGER REFERENCES sourcing_runs(id) ON DELETE SET NULL,
 source_hash TEXT NOT NULL, data_json TEXT NOT NULL, captured_at TEXT NOT NULL,
 UNIQUE(candidate_id,run_id,source_hash)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_candidate ON candidate_snapshots(candidate_id,id DESC);
CREATE TABLE IF NOT EXISTS job_candidates (
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 stage TEXT NOT NULL DEFAULT 'TO_REVIEW', owner TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
 next_follow_up_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(job_id,candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_job_candidates_job ON job_candidates(job_id,id DESC);
CREATE TABLE IF NOT EXISTS assessments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 job_candidate_id INTEGER NOT NULL REFERENCES job_candidates(id) ON DELETE CASCADE,
 engine_version TEXT NOT NULL, parser_version TEXT NOT NULL, status TEXT NOT NULL,
 fit_score REAL NOT NULL, reasons_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
 requirements_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessment_latest ON assessments(job_candidate_id,id DESC);
CREATE TABLE IF NOT EXISTS review_decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 job_candidate_id INTEGER NOT NULL REFERENCES job_candidates(id) ON DELETE CASCADE,
 decision TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', reviewer TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS follow_ups (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 job_candidate_id INTEGER NOT NULL REFERENCES job_candidates(id) ON DELETE CASCADE,
 action TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, actor TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type,entity_id,id DESC);
CREATE TABLE IF NOT EXISTS exports (
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 path TEXT NOT NULL, actor TEXT NOT NULL DEFAULT '', row_count INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply additive, idempotent migrations for existing local workbench databases."""
    jobs = _columns(conn, "jobs")
    job_columns = {
        "profile_status": "TEXT NOT NULL DEFAULT 'DRAFT'",
        "profile_version": "INTEGER NOT NULL DEFAULT 0",
        "confirmed_at": "TEXT",
        "confirmed_by": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in job_columns.items():
        if name not in jobs:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")

    runs = _columns(conn, "sourcing_runs")
    run_columns = {
        "max_pages": "INTEGER NOT NULL DEFAULT 5",
        "max_count": "INTEGER NOT NULL DEFAULT 200",
        "browser_mode": "TEXT NOT NULL DEFAULT 'managed'",
        "checkpoint_json": "TEXT NOT NULL DEFAULT '{}'",
        "last_page": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in run_columns.items():
        if name not in runs:
            conn.execute(f"ALTER TABLE sourcing_runs ADD COLUMN {name} {definition}")

    candidates = _columns(conn, "candidates")
    if "merged_into_candidate_id" not in candidates:
        conn.execute(
            "ALTER TABLE candidates ADD COLUMN merged_into_candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL"
        )
    # v3+ 新增候选人全字段：年龄/期望薪资/证书（老库增量补齐）
    for name, definition in (
        ("age", "INTEGER NOT NULL DEFAULT 0"),
        ("expected_salary", "TEXT NOT NULL DEFAULT ''"),
        ("certificates", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in candidates:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {name} {definition}")

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_candidates_merge ON candidates(merged_into_candidate_id);
        CREATE TABLE IF NOT EXISTS candidate_identities (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
         kind TEXT NOT NULL, identity_key TEXT NOT NULL, confidence INTEGER NOT NULL DEFAULT 0,
         created_at TEXT NOT NULL,
         UNIQUE(candidate_id,kind,identity_key)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_identity_exact
         ON candidate_identities(kind,identity_key)
         WHERE kind IN ('platform_uid','source_url','fingerprint');
        CREATE INDEX IF NOT EXISTS idx_candidate_identity_lookup
         ON candidate_identities(kind,identity_key,candidate_id);
        """
    )

    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
