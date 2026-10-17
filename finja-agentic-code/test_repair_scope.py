#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – L2 Repair Scope Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Unit tests for the L2 repair-scope review
               (core/repair_scope.py) and its place in the lifecycle.

               The point of L2 is that "keep changes minimal" stops being
               a sentence in a prompt and becomes a checked bound, so the
               tests are mostly about what gets REFUSED and with which
               structured code.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the repair-scope review itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import sys
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import repair_scope  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PAYLOAD = frozenset({"demo.py", "pkg/helper.py"})


def _diff(path: str, *, old: str | None = None, added: int = 1, removed: int = 1,
          old_start: int = 1) -> str:
    source = old if old is not None else path
    body = "".join(f"-old line {index}\n" for index in range(removed))
    body += "".join(f"+new line {index}\n" for index in range(added))
    return (
        f"--- {source}\n"
        f"+++ {path}\n"
        f"@@ -{old_start},{max(removed, 1)} +{old_start},{max(added, 1)} @@\n"
        f"{body}"
    )


def _review(diff: str, **kwargs) -> dict:
    kwargs.setdefault("payload_paths", PAYLOAD)
    return repair_scope.review_repair_patch(diff, **kwargs)


# ==============================================================================
# Parsing
# ==============================================================================

class TestParseUnifiedDiff:

    def test_modification_is_recognised_with_counts(self) -> None:
        changes = repair_scope.parse_unified_diff(_diff("demo.py", added=3, removed=2))
        assert len(changes) == 1
        assert changes[0]["kind"] == "modify"
        assert changes[0]["path"] == "demo.py"
        assert changes[0]["added"] == 3
        assert changes[0]["removed"] == 2

    def test_creation_is_recognised(self) -> None:
        diff = "--- /dev/null\n+++ brand_new.py\n@@ -0,0 +1 @@\n+x = 1\n"
        change = repair_scope.parse_unified_diff(diff)[0]
        assert change["kind"] == "create"
        assert change["path"] == "brand_new.py"

    def test_deletion_is_recognised(self) -> None:
        diff = "--- demo.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n"
        change = repair_scope.parse_unified_diff(diff)[0]
        assert change["kind"] == "delete"
        assert change["path"] == "demo.py"

    def test_several_files_are_separated(self) -> None:
        diff = _diff("demo.py") + _diff("pkg/helper.py")
        assert [c["path"] for c in repair_scope.parse_unified_diff(diff)] == [
            "demo.py", "pkg/helper.py"
        ]

    def test_hunk_range_is_captured_for_evidence(self) -> None:
        diff = "--- demo.py\n+++ demo.py\n@@ -10,4 +10,4 @@\n-a\n+b\n one\n two\n three\n"
        hunk = repair_scope.parse_unified_diff(diff)[0]["hunks"][0]
        assert hunk["old_start"] == 10
        assert hunk["old_end"] == 13

    def test_header_timestamp_is_stripped(self) -> None:
        diff = "--- demo.py\t2026-10-17 10:00:00\n+++ demo.py\t2026-10-17 10:01:00\n@@ -1 +1 @@\n-a\n+b\n"
        assert repair_scope.parse_unified_diff(diff)[0]["path"] == "demo.py"

    def test_prose_parses_to_nothing(self) -> None:
        assert repair_scope.parse_unified_diff("Sure! Here is the fix you asked for.") == []


# ==============================================================================
# Paths are hard -- Flare asserts containment itself
# ==============================================================================

class TestPathRules:

    @pytest.mark.parametrize("bad", [
        "../outside.py",
        "pkg/../../outside.py",
        "/etc/passwd",
        ".hidden.py",
        "pkg\\windows.py",
        "pkg/launcher.exe",
        "",
    ])
    def test_unsafe_targets_are_refused(self, bad: str) -> None:
        report = _review(_diff(bad))
        assert report["verdict"] == "rejected"
        kinds = {violation["kind"] for violation in report["violations"]}
        assert kinds & {repair_scope.VIOLATION_UNSAFE_PATH, repair_scope.VIOLATION_PREFIXED_PATH}

    def test_git_style_prefixes_get_their_own_violation(self) -> None:
        """
        `a/` and `b/` are safe paths but still wrong: under patch -p0 they
        simply would not apply. The operator needs to know the model used the
        wrong convention, not that something attacked the sandbox.
        """
        diff = "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        report = _review(diff)
        assert report["verdict"] == "rejected"
        kinds = {violation["kind"] for violation in report["violations"]}
        assert repair_scope.VIOLATION_PREFIXED_PATH in kinds
        assert repair_scope.VIOLATION_UNSAFE_PATH not in kinds

    def test_modifying_a_file_outside_the_payload_is_refused(self) -> None:
        report = _review(_diff("not_submitted.py"))
        assert report["verdict"] == "rejected"
        assert report["violations"][0]["kind"] == repair_scope.VIOLATION_UNKNOWN_PATH

    def test_unsafe_old_header_is_refused_even_with_allowed_new_header(self) -> None:
        report = _review(_diff("demo.py", old="../../outside.py"))
        assert report["verdict"] == "rejected"
        assert repair_scope.VIOLATION_UNSAFE_PATH in {
            violation["kind"] for violation in report["violations"]
        }

    def test_cross_file_modification_is_refused(self) -> None:
        report = _review(_diff("demo.py", old="pkg/helper.py"))
        assert report["verdict"] == "rejected"
        assert repair_scope.VIOLATION_MALFORMED in {
            violation["kind"] for violation in report["violations"]
        }

    @pytest.mark.parametrize("bad_diff", [
        "preamble\n" + _diff("demo.py"),
        _diff("demo.py") + "unreviewed trailer\n",
        "--- demo.py\n+++ demo.py\n",
        "--- demo.py\n+++ demo.py\n@@ -1,1 +1,1 @@\n-old\n+new\n+extra\n",
        _diff("demo.py") + _diff("demo.py"),
    ])
    def test_incomplete_or_hidden_patch_sections_are_refused(self, bad_diff: str) -> None:
        report = _review(bad_diff)
        assert report["verdict"] == "rejected"
        assert repair_scope.VIOLATION_MALFORMED in {
            violation["kind"] for violation in report["violations"]
        }

    def test_creating_a_new_file_inside_the_payload_is_allowed(self) -> None:
        diff = "--- /dev/null\n+++ pkg/new_helper.py\n@@ -0,0 +1 @@\n+x = 1\n"
        report = _review(diff)
        assert report["verdict"] == "clean"

    def test_payload_files_pass(self) -> None:
        assert _review(_diff("demo.py") + _diff("pkg/helper.py"))["verdict"] == "clean"

    def test_path_rule_agrees_with_the_orchestrator_payload_rule(self) -> None:
        """
        The diff rule and the payload rule are separate code, so they are
        pinned against one shared table. Extensions are all .py here, since
        the payload rule additionally restricts file types and the diff rule
        deliberately does not.
        """
        table = [
            "demo.py", "pkg/helper.py", "a/b/c.py",
            "../outside.py", "/etc/passwd", ".hidden.py",
            "pkg/../../outside.py", "./demo.py",
        ]
        for candidate in table:
            diff_ok = repair_scope.path_is_safe(candidate)
            try:
                main.validate_relative_path(candidate)
                payload_ok = True
            except HTTPException:
                payload_ok = False
            assert diff_ok == payload_ok, f"rules disagree about {candidate!r}"


# ==============================================================================
# Size is policy -- bounded, and tunable on purpose
# ==============================================================================

class TestScopeLimits:

    def test_too_many_files_is_too_large_not_rejected(self) -> None:
        payload = frozenset(f"f{index}.py" for index in range(8))
        diff = "".join(_diff(f"f{index}.py") for index in range(8))
        report = _review(diff, payload_paths=payload, max_files=5)

        assert report["verdict"] == "too_large"
        assert report["files_touched"] == 8
        kinds = {violation["kind"] for violation in report["violations"]}
        assert kinds == {repair_scope.VIOLATION_TOO_MANY_FILES}

    def test_too_many_lines_is_too_large(self) -> None:
        report = _review(_diff("demo.py", added=150, removed=150), max_lines=200)
        assert report["verdict"] == "too_large"
        assert report["lines_changed"] == 300

    def test_limits_travel_with_the_report(self) -> None:
        report = _review(_diff("demo.py"), max_files=3, max_lines=42)
        assert report["limits"] == {"max_files": 3, "max_lines": 42}

    def test_a_minimal_diff_is_clean(self) -> None:
        report = _review(_diff("demo.py", added=1, removed=1))
        assert report["verdict"] == "clean"
        assert report["violations"] == []

    def test_an_unsafe_path_outranks_a_size_violation(self) -> None:
        """A diff that is both unusable and huge must read as rejected."""
        diff = _diff("../outside.py", added=500, removed=500)
        assert _review(diff)["verdict"] == "rejected"


# ==============================================================================
# Evidence is reported, never enforced
# ==============================================================================

class TestEvidenceLinking:

    def _diagnosis(self, path: str, line: int) -> dict:
        return {"findings": [{"path": path, "line": line, "check": "python.syntax"}]}

    def test_finding_inside_a_hunk_counts_as_addressed(self) -> None:
        report = _review(_diff("demo.py", old_start=10, removed=4),
                         diagnosis=self._diagnosis("demo.py", 12))
        assert report["findings_addressed"] == 1
        assert report["files_without_evidence"] == []

    def test_finding_outside_every_hunk_is_not_counted(self) -> None:
        report = _review(_diff("demo.py", old_start=10, removed=2),
                         diagnosis=self._diagnosis("demo.py", 90))
        assert report["findings_addressed"] == 0

    def test_a_touched_file_with_no_finding_is_reported_not_refused(self) -> None:
        report = _review(_diff("pkg/helper.py"), diagnosis=self._diagnosis("demo.py", 1))
        assert report["files_without_evidence"] == ["pkg/helper.py"]
        assert report["verdict"] == "clean", (
            "a legitimate fix may touch a file L1 had nothing to say about; "
            "refusing that would block honest repairs"
        )

    def test_review_works_without_any_diagnosis(self) -> None:
        report = _review(_diff("demo.py"), diagnosis=None)
        assert report["verdict"] == "clean"
        assert report["findings_addressed"] == 0


# ==============================================================================
# What the lifecycle does with the verdict
# ==============================================================================

class TestEnforcement:

    def test_clean_report_raises_nothing(self) -> None:
        repair_scope.enforce(_review(_diff("demo.py")))

    def test_empty_diff_raises_nothing(self) -> None:
        report = _review("")
        assert report["verdict"] == "empty"
        repair_scope.enforce(report)

    def test_rejected_report_raises_flare_606(self) -> None:
        with pytest.raises(main.RepairPatchRejectedError) as excinfo:
            repair_scope.enforce(_review(_diff("../outside.py")))
        assert excinfo.value.code == "FLARE-606"

    def test_too_large_report_raises_flare_607(self) -> None:
        with pytest.raises(main.RepairPatchTooLargeError) as excinfo:
            repair_scope.enforce(_review(_diff("demo.py", added=400), max_lines=10))
        assert excinfo.value.code == "FLARE-607"

    def test_malformed_model_output_raises_flare_606(self) -> None:
        with pytest.raises(main.RepairPatchRejectedError):
            repair_scope.enforce(_review("I would fix line 2, but here is no diff."))

    def test_report_states_that_nothing_was_applied(self) -> None:
        assert _review(_diff("demo.py"))["applied"] is False


# ==============================================================================
# The orchestrator's entry point
# ==============================================================================

class TestOrchestratorReview:

    @pytest.fixture(autouse=True)
    def _isolated_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.clear()

    def _job(self) -> str:
        return main.stage_job(main.CreateJobRequest(
            task="Fix the bug",
            files=[main.JobFile(path="demo.py", content="x = 1\n")],
        ))

    def test_review_takes_payload_paths_from_the_staged_request(self) -> None:
        job_id = self._job()
        report = main.review_repair_scope(job_id, _diff("demo.py"), {})
        assert report["verdict"] == "clean"

    def test_review_refuses_a_file_the_payload_never_contained(self) -> None:
        job_id = self._job()
        report = main.review_repair_scope(job_id, _diff("elsewhere.py"), {})
        assert report["verdict"] == "rejected"

    def test_review_uses_the_l1_diagnosis_when_present(self) -> None:
        job_id = self._job()
        preflight = {"l1_diagnosis": {
            "findings": [{"path": "demo.py", "line": 1, "check": "python.syntax"}]
        }}
        report = main.review_repair_scope(job_id, _diff("demo.py", old_start=1), preflight)
        assert report["findings_addressed"] == 1

    def test_review_honours_the_configured_limits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "MAX_REPAIR_LINES", 2)
        job_id = self._job()
        report = main.review_repair_scope(job_id, _diff("demo.py", added=9, removed=9), {})
        assert report["verdict"] == "too_large"
