# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path

from workbench.database import WorkbenchDB
from workbench.evaluation import assess_candidate, build_requirement_profile


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = WorkbenchDB(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_jobs_are_isolated(self):
        job_java = self.db.create_job("Java工程师", "Java", "")
        job_sales = self.db.create_job("销售经理", "销售", "")
        profile_java = build_requirement_profile(keyword="Java", jd="熟悉Java。")
        profile_sales = build_requirement_profile(keyword="销售", jd="具备销售经验。")
        self.db.update_job(job_java, profile=profile_java)
        self.db.update_job(job_sales, profile=profile_sales)

        candidate = {
            "platform": "demo",
            "platform_uid": "same-person",
            "name": "张三",
            "title": "Java工程师",
            "skills": "Java",
            "text": "Java开发",
        }
        candidate_id, _, _ = self.db.upsert_candidate(candidate)
        java_link, _ = self.db.link_candidate_to_job(job_java, candidate_id)
        sales_link, _ = self.db.link_candidate_to_job(job_sales, candidate_id)
        self.db.save_assessment(java_link, assess_candidate(candidate, profile_java), profile_java)
        self.db.save_assessment(sales_link, assess_candidate(candidate, profile_sales), profile_sales)

        java_rows = self.db.list_job_candidates(job_java)
        sales_rows = self.db.list_job_candidates(job_sales)
        self.assertEqual(len(java_rows), 1)
        self.assertEqual(len(sales_rows), 1)
        self.assertEqual(java_rows[0]["job_candidate_id"], java_link)
        self.assertEqual(sales_rows[0]["job_candidate_id"], sales_link)
        self.assertNotEqual(java_link, sales_link)

    def test_second_scrape_updates_candidate_and_adds_snapshot(self):
        job = self.db.create_job("Java工程师", "Java", "")
        run1 = self.db.create_sourcing_run(job, "Java")
        first = {
            "platform": "zhilian",
            "platform_uid": "uid-1",
            "name": "李四",
            "title": "Java工程师",
            "activity": "本周活跃",
            "text": "Java",
        }
        candidate_id, created, snapshot1 = self.db.upsert_candidate(first, run1)
        self.assertTrue(created)
        self.assertIsNotNone(snapshot1)

        run2 = self.db.create_sourcing_run(job, "Java")
        second = {**first, "activity": "在线", "text": "Java Redis"}
        same_id, created_again, snapshot2 = self.db.upsert_candidate(second, run2)
        self.assertEqual(candidate_id, same_id)
        self.assertFalse(created_again)
        self.assertIsNotNone(snapshot2)

        with self.db.connect() as conn:
            row = conn.execute("SELECT activity,text FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM candidate_snapshots WHERE candidate_id=?", (candidate_id,)
            ).fetchone()[0]
        self.assertEqual(row["activity"], "在线")
        self.assertEqual(row["text"], "Java Redis")
        self.assertEqual(count, 2)

    def test_job_export_only_contains_selected_job(self):
        job1 = self.db.create_job("岗位1")
        job2 = self.db.create_job("岗位2")
        candidate1, _, _ = self.db.upsert_candidate(
            {"platform": "demo", "platform_uid": "a", "name": "A", "title": "职位A"}
        )
        candidate2, _, _ = self.db.upsert_candidate(
            {"platform": "demo", "platform_uid": "b", "name": "B", "title": "职位B"}
        )
        self.db.link_candidate_to_job(job1, candidate1)
        self.db.link_candidate_to_job(job2, candidate2)
        output = Path(self.tmp.name) / "job1.csv"
        rows = self.db.export_job_csv(job1, output)
        text = output.read_text(encoding="utf-8-sig")
        self.assertEqual(rows, 1)
        self.assertIn("A", text)
        self.assertNotIn("职位B", text)


if __name__ == "__main__":
    unittest.main()
