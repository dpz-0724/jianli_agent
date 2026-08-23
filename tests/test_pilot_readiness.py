# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.pilot_readiness import run_readiness_checks, write_readiness_report


class PilotReadinessTests(unittest.TestCase):
    def test_offline_readiness_checks_database_and_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch("workbench.pilot_readiness._check_browser_runtime", return_value="test browser OK"):
                report = run_readiness_checks(root)
            self.assertEqual(report["overall"], "PASS")
            checks = {item["name"]: item for item in report["checks"]}
            self.assertTrue(checks["local_data_directory"]["passed"])
            self.assertTrue(checks["sqlite_backup_restore"]["passed"])
            self.assertTrue(checks["settings_roundtrip"]["passed"])
            self.assertTrue(checks["browser_runtime"]["passed"])
            self.assertTrue(report["field_validation_required"])

    def test_report_is_atomic_and_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "report.json"
            with patch("workbench.pilot_readiness._check_browser_runtime", return_value="test browser OK"):
                report = write_readiness_report(destination, data_root=root)
            parsed = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(parsed["overall"], report["overall"])
            self.assertEqual(parsed["version"], "0.9.1")
            self.assertFalse(destination.with_suffix(".json.tmp").exists())

    def test_required_failure_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "workbench.pilot_readiness._check_browser_runtime",
                side_effect=RuntimeError("browser missing"),
            ):
                report = run_readiness_checks(temp)
            self.assertEqual(report["overall"], "FAIL")
            browser = next(item for item in report["checks"] if item["name"] == "browser_runtime")
            self.assertFalse(browser["passed"])
            self.assertIn("browser missing", browser["detail"])


if __name__ == "__main__":
    unittest.main()
