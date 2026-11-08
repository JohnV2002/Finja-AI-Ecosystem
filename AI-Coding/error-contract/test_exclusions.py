"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  test_exclusions.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.4.0
  Description:
    Regression tests for scan_exclude: reasons required, reported, kept.

  New in v1.4.0:
    • Excluded files are not scanned and are counted per rule
    • Entries without a reason are rejected as findings
    • The ledger keeps scan_exclude when it rewrites the legend

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from error_contract.exclusions import format_exclusions, glob_match, parse_exclusions
from error_contract.ledger import load_ledger
from error_contract.scanner import scan_project

LEGEND = {
    "schema_version": 1,
    "title": "Error Code Legend",
    "namespaces": {"DEMO": {"categories": {}, "codes": {}}},
}


def _project(root: Path, scan_exclude: object | None) -> None:
    legend = dict(LEGEND)
    if scan_exclude is not None:
        legend["scan_exclude"] = scan_exclude
    (root / "error_contract.json").write_text(json.dumps(legend), encoding="utf-8")
    (root / "vendor").mkdir()
    (root / "vendor" / "lib.min.js").write_text("try{x()}catch(e){}\n", encoding="utf-8")
    (root / "app.js").write_text("console.log('own code');\n", encoding="utf-8")


class GlobTests(unittest.TestCase):
    def test_single_star_stays_in_one_folder(self) -> None:
        self.assertTrue(glob_match("vendor/*.js", "vendor/lib.js"))
        self.assertFalse(glob_match("vendor/*.js", "vendor/sub/lib.js"))

    def test_double_star_and_folder_suffix(self) -> None:
        self.assertTrue(glob_match("vendor/**/*.js", "vendor/lib.js"))
        self.assertTrue(glob_match("vendor/**/*.js", "vendor/a/b/lib.js"))
        self.assertTrue(glob_match("vendor/", "vendor/a/lib.js"))
        self.assertFalse(glob_match("vendor/", "src/vendor.js"))


class ParseTests(unittest.TestCase):
    def test_entry_without_reason_is_rejected(self) -> None:
        config = parse_exclusions(
            [{"path": "a.js", "reason": "  "}, {"path": "b.js"}, {"path": "c.js", "reason": "vendor"}]
        )
        self.assertEqual([rule.path for rule in config.rules], ["c.js"])
        self.assertEqual(len(config.errors), 2)
        self.assertTrue(all("reason" in error for error in config.errors))

    def test_absolute_and_parent_paths_are_rejected(self) -> None:
        drive_path = "Q" + ":/x.js"  # built at runtime so leak scanners do not flag the fixture
        config = parse_exclusions(
            [{"path": "/etc/x.js", "reason": "r"}, {"path": "../x.js", "reason": "r"}, {"path": drive_path, "reason": "r"}]
        )
        self.assertEqual(config.rules, [])
        self.assertEqual(len(config.errors), 3)

    def test_non_list_is_rejected(self) -> None:
        config = parse_exclusions({"path": "a.js", "reason": "r"})
        self.assertEqual(config.rules, [])
        self.assertEqual(len(config.errors), 1)


class ScanTests(unittest.TestCase):
    def test_excluded_file_is_not_scanned_and_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, [{"path": "vendor/**", "reason": "Third-party build, replaced as a whole"}])
            report = scan_project(root, prefix="DEMO")
            paths = {finding.path for finding in report.findings}
            self.assertNotIn("vendor/lib.min.js", paths)
            self.assertIn("app.js", paths)
            self.assertEqual(report.exclusions.excluded_count, 1)
            text = "\n".join(format_exclusions(report.exclusions))
            self.assertIn("Excluded: 1 file(s)", text)
            self.assertIn("Third-party build", text)
            self.assertEqual(report.to_dict()["exclusions"]["excluded_files"], 1)

    def test_rejected_entry_is_a_finding_and_file_stays_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, [{"path": "vendor/**"}])
            report = scan_project(root, prefix="DEMO")
            rules = {finding.rule for finding in report.findings}
            self.assertIn("invalid_scan_exclude", rules)
            self.assertIn("vendor/lib.min.js", {finding.path for finding in report.findings})

    def test_stale_rule_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, [{"path": "gone/*.js", "reason": "old vendor"}])
            report = scan_project(root, prefix="DEMO")
            self.assertIn("matches nothing", "\n".join(format_exclusions(report.exclusions)))

    def test_no_config_means_no_exclusion_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, None)
            report = scan_project(root, prefix="DEMO")
            self.assertEqual(format_exclusions(report.exclusions), [])


class LedgerTests(unittest.TestCase):
    def test_ledger_rewrite_keeps_scan_exclude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "error_contract.json"
            entries = [{"path": "vendor/**", "reason": "Third-party build"}]
            path.write_text(json.dumps({**LEGEND, "scan_exclude": entries}), encoding="utf-8")
            load_ledger(path).save(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["scan_exclude"], entries)


if __name__ == "__main__":
    unittest.main()
