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

    def test_audit_actor_is_attributed_and_stale_assessment_returns_to_review(self):
        from workbench.models import ProfileStatus
        from workbench.service import RecruitmentService

        job = self.db.create_job("Java工程师", "Java", "")
        profile = build_recruiter_confirmed_profile(
            keyword="Java", jd="熟悉Java。", required_skills="Java"
        )
        self.db.update_job(job, profile=profile, profile_status=ProfileStatus.DRAFT)
        self.db.confirm_job_profile(job)
        service = RecruitmentService(self.db)
        service.ingest_candidates(
            job_id=job,
            run_id=None,
            candidates=[
                {
                    "platform": "demo",
                    "platform_uid": "stale-1",
                    "name": "候选人",
                    "title": "Java工程师",
                    "skills": "Java",
                    "text": "Java",
                }
            ],
        )
        with self.db.connect(write=True) as conn:
            conn.execute(
                "UPDATE candidates SET last_seen_at='9999-12-31T23:59:59+00:00' WHERE platform_uid='stale-1'"
            )
        row = self.db.list_job_candidates(job)[0]
        self.assertTrue(row["assessment_stale"])
        self.assertEqual(row["assessment_status"], "REVIEW")
        self.assertTrue(any("资料在本次评估后更新" in reason for reason in row["reasons"]))
        with self.db.connect() as conn:
            actor = conn.execute(
                "SELECT actor FROM audit_events WHERE event_type='JOB_CREATED' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        self.assertTrue(actor)

    def test_manual_merge_preserves_job_links_marks_duplicate_and_creates_backup(self):
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
            backup_event = conn.execute(
                "SELECT payload_json FROM audit_events WHERE event_type='CANDIDATE_MERGE_BACKUP_CREATED' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        backups = list((self.db_path.parent / "backups").glob("before-candidate-merge-*.db"))
        self.assertEqual(link_count, 1)
        self.assertEqual(duplicate["merged_into_candidate_id"], first_id)
        self.assertEqual(len(backups), 1)
        self.assertIsNotNone(backup_event)


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
