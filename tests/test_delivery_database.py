# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench.database import WorkbenchDB
from workbench.product_profile import build_recruiter_confirmed_profile


class DeliveryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "delivery.db"
        self.db = WorkbenchDB(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_and_restore_roundtrip(self):
        self.db.create_job("原岗位", "Java", "")
        backup = Path(self.tmp.name) / "backup.db"
        self.db.backup_to(backup)
        self.db.create_job("后续岗位", "销售", "")
        self.assertEqual(len(self.db.list_jobs()), 2)

        pre_restore = self.db.restore_from(backup)
        self.assertTrue(pre_restore.exists())
        jobs = self.db.list_jobs()
        self.assertEqual([job["title"] for job in jobs], ["原岗位"])

    def test_late_platform_uid_binds_to_existing_fallback_candidate(self):
        first = {
            "platform": "zhilian",
            "name": "李明",
            "title": "Java工程师",
            "location": "南京",
            "education": "本科",
            "experience": "5年",
            "text": "Java MySQL",
        }
        first_id, created, _ = self.db.upsert_candidate(first)
        self.assertTrue(created)

        second = {
            **first,
            "platform_uid": "resume-1001",
            "title": "高级Java工程师",
            "text": "Java Spring Boot MySQL Redis",
        }
        second_id, created_again, _ = self.db.upsert_candidate(second)
        self.assertEqual(first_id, second_id)
        self.assertFalse(created_again)
        with self.db.connect() as conn:
            row = conn.execute("SELECT platform_uid,title FROM candidates WHERE id=?", (first_id,)).fetchone()
            identities = conn.execute(
                "SELECT kind FROM candidate_identities WHERE candidate_id=?", (first_id,)
            ).fetchall()
        self.assertEqual(row["platform_uid"], "resume-1001")
        self.assertEqual(row["title"], "高级Java工程师")
        self.assertIn("platform_uid", {item["kind"] for item in identities})

    def test_manual_merge_preserves_job_links_and_marks_duplicate(self):
        job = self.db.create_job("Java工程师")
        first_id, _, _ = self.db.upsert_candidate(
            {"platform": "demo", "platform_uid": "a", "name": "A", "title": "Java"}
        )
        second_id, _, _ = self.db.upsert_candidate(
            {"platform": "demo", "platform_uid": "b", "name": "A", "title": "高级Java"}
        )
        self.db.link_candidate_to_job(job, first_id)
        self.db.link_candidate_to_job(job, second_id)
        self.db.merge_candidates(first_id, second_id)
        with self.db.connect() as conn:
            link_count = conn.execute(
                "SELECT COUNT(*) FROM job_candidates WHERE job_id=? AND candidate_id=?", (job, first_id)
            ).fetchone()[0]
            duplicate = conn.execute(
                "SELECT merged_into_candidate_id FROM candidates WHERE id=?", (second_id,)
            ).fetchone()
        self.assertEqual(link_count, 1)
        self.assertEqual(duplicate["merged_into_candidate_id"], first_id)


class RecruiterProfileTests(unittest.TestCase):
    def test_structured_values_override_jd_and_search_terms_are_not_hard_skills(self):
        profile = build_recruiter_confirmed_profile(
            keyword="Java Spring",
            jd="本科及以上，至少5年经验，要求熟悉Java；Redis经验优先。",
            min_education="不限",
            min_experience_years=3,
            required_skills="MySQL",
            preferred_skills="Redis",
        )
        self.assertEqual(profile.min_education, "")
        self.assertEqual(profile.min_experience_years, 3)
        self.assertEqual(profile.required_skills, ("MySQL",))
        self.assertEqual(profile.preferred_skills, ("Redis",))
        self.assertNotIn("spring", {skill.lower() for skill in profile.required_skills})
        self.assertIn("spring", {term.lower() for term in profile.title_terms})


if __name__ == "__main__":
    unittest.main()
