# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog

from workbench.qt_job_dialog import JobCreateDialog
from workbench.qt_workspace import ProductRecruitmentWorkbenchWindow


class JobCreationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_explains_missing_title_and_enables_create(self):
        dialog = JobCreateDialog()
        self.assertFalse(dialog.create_button.isEnabled())
        self.assertTrue(dialog.validation_label.isVisible())
        dialog.title_edit.setText("高级 Java 工程师")
        self.assertTrue(dialog.create_button.isEnabled())
        dialog._validate_and_accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.values()["keyword"], "高级 Java 工程师")
        dialog.close()

    def test_create_button_path_persists_structured_job_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ui.db"
            window = ProductRecruitmentWorkbenchWindow(str(db_path))
            window._update_login_ui(True, "test")

            class AcceptedDialog:
                def __init__(self, _parent=None):
                    pass

                def exec(self):
                    return QDialog.DialogCode.Accepted

                @staticmethod
                def values():
                    return {
                        "title": "高级 Java 工程师",
                        "keyword": "Java Spring",
                        "jd": "本科及以上，至少 3 年经验。微服务经验优先。",
                        "min_education": "本科",
                        "min_experience_years": 3,
                        "locations": "南京、苏州",
                        "required_skills": "Java、Spring Boot、MySQL",
                        "preferred_skills": "微服务、Kubernetes",
                    }

            with patch("workbench.qt_workspace.JobCreateDialog", AcceptedDialog):
                window.new_job()

            jobs = window.db.list_jobs()
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["title"], "高级 Java 工程师")
            profile = window.service.load_profile(int(jobs[0]["id"]))
            self.assertEqual(profile.min_education, "本科")
            self.assertEqual(profile.min_experience_years, 3)
            self.assertIn("Java", profile.required_skills)
            self.assertIn("微服务", profile.preferred_skills)
            self.assertEqual(jobs[0]["profile_status"], "DRAFT")
            window.close()


if __name__ == "__main__":
    unittest.main()
