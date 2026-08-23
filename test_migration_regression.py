# -*- coding: utf-8 -*-
"""回归测试：老数据库(V1 schema，无 merged_into_candidate_id) 打开应自动迁移，不崩溃。"""
import os
import sqlite3
import tempfile

from workbench.database import WorkbenchDB

tmp = tempfile.gettempdir()
old = os.path.join(tmp, "reg_legacy.db")
open(os.path.join(tmp, "reg.db"), "w").close()  # 占位

# 1. 构造一个“老库”：只有 v1 时代的 candidates 表（无 merged_into_candidate_id / candidate_identities）
conn = sqlite3.connect(old)
conn.executescript("""
CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,keyword TEXT NOT NULL DEFAULT '',
 jd TEXT NOT NULL DEFAULT '',requirements_json TEXT NOT NULL DEFAULT '{}',
 status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE sourcing_runs (id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL,query TEXT NOT NULL,
 status TEXT NOT NULL,found_count INTEGER NOT NULL DEFAULT 0,new_count INTEGER NOT NULL DEFAULT 0,
 error_code TEXT,error_message TEXT,diagnostic_dir TEXT,started_at TEXT,finished_at TEXT,created_at TEXT NOT NULL);
CREATE TABLE candidates (id INTEGER PRIMARY KEY AUTOINCREMENT,canonical_key TEXT NOT NULL UNIQUE,
 platform TEXT NOT NULL DEFAULT 'zhilian',platform_uid TEXT,name TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL DEFAULT '',location TEXT NOT NULL DEFAULT '',education TEXT NOT NULL DEFAULT '',
 experience TEXT NOT NULL DEFAULT '',activity TEXT NOT NULL DEFAULT '',skills TEXT NOT NULL DEFAULT '',
 text TEXT NOT NULL DEFAULT '',source_url TEXT NOT NULL DEFAULT '',
 first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL);
INSERT INTO candidates(canonical_key,platform,name,title,first_seen_at,last_seen_at)
 VALUES('k1','zhilian','张三','Java','2026-01-01','2026-01-01');
""")
conn.commit()
conn.close()
print("已构造老库:", old)

# 2. 打开应自动迁移
db = WorkbenchDB(old)
with db.connect() as c:
    cols = {r[1] for r in c.execute("PRAGMA table_info(candidates)")}
    assert "merged_into_candidate_id" in cols, "迁移失败: 缺 merged_into_candidate_id 列"
    jobs_cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    assert "profile_status" in jobs_cols, "迁移失败: 缺 profile_status"
    run_cols = {r[1] for r in c.execute("PRAGMA table_info(sourcing_runs)")}
    assert "max_pages" in run_cols, "迁移失败: 缺 max_pages"
    ident = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_identities'").fetchone()
    assert ident, "迁移失败: 缺 candidate_identities 表"
    n = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    assert n == 1, "迁移丢失数据"
print("PASS: 老库迁移成功（列/表/数据完整）")

# 3. 全新库也能正常建
fresh = os.path.join(tmp, "reg_fresh.db")
db2 = WorkbenchDB(fresh)
with db2.connect() as c:
    cols = {r[1] for r in c.execute("PRAGMA table_info(candidates)")}
    assert "merged_into_candidate_id" in cols
print("PASS: 全新库建表正常")
print("MIGRATION REGRESSION OK")