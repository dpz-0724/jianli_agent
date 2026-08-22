# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from workbench.database import WorkbenchDB
from workbench.models import ProfileStatus, SearchPlan
from workbench.service import RecruitmentService
from workbench.settings import AppSettings, load_settings, save_settings


class ProductizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = WorkbenchDB(self.root / "workbench.db")
        self.service = RecruitmentService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_is_blocked_until_profile_is_confirmed(self):
        job_id = self.db.create_job("Java工程师", "Java", "熟悉 Java")
        self.service.parse_and_save_job(
            job_id,
            title="Java工程师",
            keyword="Java",
            jd="熟悉 Java，有 Redis 经验优先",
        )
        with self.assertRaisesRegex(ValueError, "确认岗位标准"):
            self.service.create_sourcing_run(job_id, SearchPlan(query="Java"))

        version = self.service.confirm_job_profile(job_id, "tester")
        self.assertEqual(version, 1)
        run_id = self.service.create_sourcing_run(
            job_id,
            SearchPlan(query="Java", max_pages=7, max_count=350, browser_mode="edge"),
        )
        run = self.db.get_sourcing_run(run_id)
        self.assertEqual(run["max_pages"], 7)
        self.assertEqual(run["max_count"], 350)
        self.assertEqual(run["browser_mode"], "edge")

    def test_editing_profile_returns_it_to_draft(self):
        job_id = self.db.create_job("销售经理", "销售", "")
        self.service.parse_and_save_job(job_id, title="销售经理", keyword="销售", jd="具备销售经验")
        self.service.confirm_job_profile(job_id)
        self.assertEqual(self.db.get_job(job_id)["profile_status"], ProfileStatus.CONFIRMED.value)

        self.service.parse_and_save_job(
            job_id,
            title="高级销售经理",
            keyword="销售 管理",
            jd="具备销售管理经验",
        )
        self.assertEqual(self.db.get_job(job_id)["profile_status"], ProfileStatus.DRAFT.value)

    def test_v1_database_is_migrated_additively(self):
        old_path = self.root / "legacy.db"
        conn = sqlite3.connect(old_path)
        conn.executescript(
            """
            CREATE TABLE jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,keyword TEXT NOT NULL DEFAULT '',
              jd TEXT NOT NULL DEFAULT '',requirements_json TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE sourcing_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL,query TEXT NOT NULL,
              status TEXT NOT NULL,found_count INTEGER NOT NULL DEFAULT 0,new_count INTEGER NOT NULL DEFAULT 0,
              error_code TEXT,error_message TEXT,diagnostic_dir TEXT,started_at TEXT,finished_at TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()
        migrated = WorkbenchDB(old_path)
        with migrated.connect() as check:
            job_cols = {row[1] for row in check.execute("PRAGMA table_info(jobs)")}
            run_cols = {row[1] for row in check.execute("PRAGMA table_info(sourcing_runs)")}
        self.assertTrue({"profile_status", "profile_version", "confirmed_at", "confirmed_by"}.issubset(job_cols))
        self.assertTrue({"max_pages", "max_count", "browser_mode", "checkpoint_json", "last_page"}.issubset(run_cols))

    def test_settings_round_trip_and_normalization(self):
        path = self.root / "settings.json"
        save_settings(
            AppSettings(browser_mode="EDGE", default_max_pages=99, default_max_count=99999, slow_mo_ms=-1),
            path,
        )
        loaded = load_settings(path)
        self.assertEqual(loaded.browser_mode, "edge")
        self.assertEqual(loaded.default_max_pages, 20)
        self.assertEqual(loaded.default_max_count, 2000)
        self.assertEqual(loaded.slow_mo_ms, 0)


if __name__ == "__main__":
    unittest.main()
