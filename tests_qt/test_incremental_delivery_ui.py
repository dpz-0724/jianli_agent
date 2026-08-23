# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from workbench.models import BrowserEvent, ProfileStatus, SearchPlan
from workbench.product_profile import build_recruiter_confirmed_profile
from workbench.qt_workspace_runtime import RecruitmentWorkspaceWindow


class IncrementalDeliveryQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_is_persisted_and_acknowledged_before_completed_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            window = RecruitmentWorkspaceWindow(str(Path(temp_dir) / "checkpoint.db"))
            window._update_login_ui(True, "test")
            job_id = window.db.create_job("Java工程师", "Java", "")
            profile = build_recruiter_confirmed_profile(
                keyword="Java",
                jd="本科及以上，至少3年经验，熟悉Java。",
                min_education="本科",
                min_experience_years=3,
                required_skills="Java",
            )
            window.db.update_job(
                job_id,
                profile=profile,
                profile_status=ProfileStatus.DRAFT,
            )
            window.db.confirm_job_profile(job_id)
            window.refresh_jobs(job_id)
            run_id = window.service.create_sourcing_run(
                job_id,
                SearchPlan(query="Java", max_pages=3, max_count=50),
            )
            request_id = "page-stream-test"
            window.pending[request_id] = {
                "job_id": job_id,
                "run_id": run_id,
                "plan": SearchPlan(query="Java", max_pages=3, max_count=50),
                "start_page": 1,
            }
            window.active_run_id = run_id
            ack_token, ack_event = window.worker._register_page_ack()

            window._handle_browser_event(
                BrowserEvent(
                    event="PAGE_RESULT",
                    request_id=request_id,
                    payload={
                        "run_id": run_id,
                        "page_no": 1,
                        "ack_token": ack_token,
                        "candidates": [
                            {
                                "platform": "zhilian",
                                "platform_uid": "uid-1",
                                "name": "候选人A",
                                "title": "Java工程师",
                                "education": "本科",
                                "experience": "5年",
                                "skills": "Java",
                                "text": "Java",
                            }
                        ],
                    },
                )
            )
            window.worker._await_page_ack(ack_token, ack_event, timeout=0.2)
            run = window.db.get_sourcing_run(run_id)
            self.assertEqual(run["last_page"], 1)
            self.assertEqual(run["found_count"], 1)
            self.assertEqual(len(window.db.list_job_candidates(job_id)), 1)

            window._handle_browser_event(
                BrowserEvent(
                    event="COMPLETED",
                    request_id=request_id,
                    payload={"run_id": run_id, "page_persisted": True, "count": 1},
                )
            )
            run = window.db.get_sourcing_run(run_id)
            self.assertEqual(run["status"], "SUCCEEDED")
            self.assertEqual(run["found_count"], 1)
            window.close()


if __name__ == "__main__":
    unittest.main()
