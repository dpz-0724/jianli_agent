# -*- coding: utf-8 -*-
"""Database connection lifecycle and audit primitives."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .db_schema import SCHEMA, SCHEMA_VERSION, default_data_dir, now_iso


class DatabaseBase:
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path else default_data_dir() / "workbench.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        if write:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        # sqlite3.Connection's context manager commits/rolls back but does not close.
        # Explicit close is required on Windows so temporary/test databases can be deleted.
        from .db_schema import migrate_schema

        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            # 旧版本数据库升级：补齐新增列（profile_status 等），否则查询直接崩溃。
            migrate_schema(conn)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()
        finally:
            conn.close()

    def _audit_conn(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        actor: str = "",
    ) -> None:
        conn.execute(
            "INSERT INTO audit_events(event_type,entity_type,entity_id,actor,payload_json,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (event_type, entity_type, entity_id, actor, json.dumps(payload, ensure_ascii=False), now_iso()),
        )
