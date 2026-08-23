# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from workbench.database import WorkbenchDB
from workbench.service import RecruitmentService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = WorkbenchDB(Path(self.tmp.name) / "service.db")
        self.service = RecruitmentService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ingest_creates_assessments_and_job_links(self):
        job = self.db.create_job("Java工程师", "Java", "本科及以上，至少3年经验，熟悉Java。")
        self.service.parse_and_save_job(
            job,
            title="Java工程师",
            keyword="Java",
            jd="本科及以上，至少3年经验，熟悉Java。",
        )
        # V0.9 产品规则：岗位画像必须确认后才有搜索
        self.db.confirm_job_profile(job, confirmed_by="unit-test")
        run = self.db.create_sourcing_run(job, "Java")
        summary = self.service.ingest_candidates(
            job_id=job,
            run_id=run,
            candidates=[
                {
                    "platform": "demo",
                    "platform_uid": "1",
                    "name": "A",
                    "title": "Java工程师",
                    "education": "本科",
                    "experience": "5年",
                    "skills": "Java",
                    "text": "Java",
                },
                {
                    "platform": "demo",
                    "platform_uid": "2",
                    "name": "B",
                    "title": "Java工程师",
                    "education": "大专",
                    "experience": "5年",
                    "skills": "Java",
                    "text": "Java",
                },
            ],
        )
        self.assertEqual(summary.found, 2)
        self.assertEqual(summary.new_job_links, 2)
        self.assertEqual(summary.pass_count, 1)
        self.assertEqual(summary.conflict_count, 1)
        self.assertEqual(len(self.db.list_job_candidates(job)), 2)


if __name__ == "__main__":
    unittest.main()
