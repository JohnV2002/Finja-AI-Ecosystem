#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – L1 Diagnosis Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Unit tests for Flare's L1 diagnosis (worker/l1_diagnosis.py)
               and for the orchestrator's rendering of it into the model
               prompt.

               L1 is sold as reliable, so the properties that make it
               reliable are what gets tested: it never executes code, it
               is deterministic, and it declares its own blind spots
               instead of staying silent about them.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the L1 contract itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("JOB_ID", "testjob")
os.environ.setdefault("JOBS_DIR", "/tmp/finja-agentic-test-jobs")

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT / "worker"))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import l1_diagnosis  # noqa: E402
import main  # noqa: E402
import worker  # noqa: E402


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _findings(ws: Path, check: str | None = None) -> list[dict]:
    findings = l1_diagnosis.diagnose(ws)["findings"]
    if check is None:
        return findings
    return [finding for finding in findings if finding["check"] == check]


# ==============================================================================
# The reliability properties L1 is named for
# ==============================================================================

class TestReliabilityProperties:

    def test_diagnosis_declares_that_it_never_executes_code(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        diagnosis = l1_diagnosis.diagnose(workspace)
        assert diagnosis["executes_code"] is False
        assert diagnosis["deterministic"] is True
        assert diagnosis["schema_version"] == l1_diagnosis.SCHEMA_VERSION

    def test_importing_a_module_is_never_triggered(self, workspace: Path) -> None:
        """
        A file whose import would have a side effect must stay inert. If L1
        ever imported the workspace, this test would fail by writing a file.
        """
        marker = workspace.parent / "side-effect-happened"
        (workspace / "evil.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('boom')\n",
            encoding="utf-8",
        )
        l1_diagnosis.diagnose(workspace)
        assert not marker.exists(), "L1 executed the submitted code"

    def test_repeated_runs_are_byte_identical(self, workspace: Path) -> None:
        (workspace / "b.py").write_text("def f(:\n", encoding="utf-8")
        (workspace / "a.json").write_text("{nope}", encoding="utf-8")
        (workspace / "c.toml").write_text("key = = 1\n", encoding="utf-8")

        first = json.dumps(l1_diagnosis.diagnose(workspace), sort_keys=True)
        second = json.dumps(l1_diagnosis.diagnose(workspace), sort_keys=True)
        assert first == second

    def test_findings_are_sorted_by_path_then_position(self, workspace: Path) -> None:
        (workspace / "z.json").write_text("{", encoding="utf-8")
        (workspace / "a.json").write_text("{", encoding="utf-8")
        (workspace / "m.json").write_text("{", encoding="utf-8")
        paths = [finding["path"] for finding in _findings(workspace)]
        assert paths == sorted(paths)

    def test_clean_workspace_reports_a_clean_verdict(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        diagnosis = l1_diagnosis.diagnose(workspace)
        assert diagnosis["verdict"] == "clean"
        assert diagnosis["counts"] == {"error": 0, "warning": 0}

    def test_an_error_blocks_the_verdict_but_a_warning_does_not(self, workspace: Path) -> None:
        (workspace / "warn.py").write_text("from .missing import thing\n", encoding="utf-8")
        warned = l1_diagnosis.diagnose(workspace)
        assert warned["counts"]["warning"] == 1
        assert warned["verdict"] == "clean"

        (workspace / "broken.json").write_text("{", encoding="utf-8")
        blocked = l1_diagnosis.diagnose(workspace)
        assert blocked["counts"]["error"] == 1
        assert blocked["verdict"] == "blocked"


# ==============================================================================
# Blind spots must be declared, never passed over in silence
# ==============================================================================

class TestHonestBlindSpots:

    def test_javascript_is_reported_as_undiagnosed_with_a_reason(self, workspace: Path) -> None:
        (workspace / "app.js") .write_text("function f( {\n", encoding="utf-8")
        diagnosis = l1_diagnosis.diagnose(workspace)
        assert diagnosis["findings"] == []
        assert diagnosis["files_diagnosed"] == 0
        assert diagnosis["undiagnosed"] == [
            {"path": "app.js", "reason": "no JavaScript parser in the offline sandbox"}
        ]

    def test_prose_is_reported_as_undiagnosed(self, workspace: Path) -> None:
        (workspace / "notes.md").write_text("# hi\n", encoding="utf-8")
        reasons = [entry["reason"] for entry in l1_diagnosis.diagnose(workspace)["undiagnosed"]]
        assert reasons == ["prose or markup; no trustworthy static check"]

    def test_unknown_extension_is_reported_as_undiagnosed(self, workspace: Path) -> None:
        (workspace / "data.bin").write_text("x\n", encoding="utf-8")
        entry = l1_diagnosis.diagnose(workspace)["undiagnosed"][0]
        assert entry["path"] == "data.bin"
        assert "no checker" in entry["reason"]

    def test_missing_pyyaml_is_a_declared_skip_not_a_clean_bill(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(l1_diagnosis, "_load_yaml_module", lambda: None)
        (workspace / "conf.yml").write_text("a: [1,\n", encoding="utf-8")

        diagnosis = l1_diagnosis.diagnose(workspace)
        assert diagnosis["findings"] == []
        assert diagnosis["checks_skipped"] == [
            {"check": "yaml.parse", "reason": "PyYAML is not installed in the worker image"}
        ]
        assert diagnosis["undiagnosed"][0]["path"] == "conf.yml"
        assert l1_diagnosis.CHECK_YAML_PARSE not in diagnosis["checks_run"]

    def test_patch_artifacts_are_not_diagnosed(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        (workspace / "demo.py.orig").write_text("def broken(:\n", encoding="utf-8")
        diagnosis = l1_diagnosis.diagnose(workspace)
        assert diagnosis["files_seen"] == 1
        assert diagnosis["findings"] == []
        assert diagnosis["undiagnosed"] == []


# ==============================================================================
# The individual checks
# ==============================================================================

class TestPythonChecks:

    def test_syntax_error_is_reported_and_marked_truncated(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("def add(a, b):\n    return a +\n", encoding="utf-8")
        findings = _findings(workspace, l1_diagnosis.CHECK_PYTHON_SYNTAX)

        assert len(findings) == 1
        assert findings[0]["severity"] == "error"
        assert findings[0]["line"] == 2
        assert findings[0]["truncated"] is True, (
            "ast stops at the first error, so the rest of the file is unknown "
            "and the finding must say so rather than imply a single problem"
        )

    def test_a_broken_file_does_not_mask_other_files(self, workspace: Path) -> None:
        (workspace / "a.py").write_text("def broken(:\n", encoding="utf-8")
        (workspace / "b.json").write_text("{", encoding="utf-8")
        checks = {finding["check"] for finding in _findings(workspace)}
        assert checks == {l1_diagnosis.CHECK_PYTHON_SYNTAX, l1_diagnosis.CHECK_JSON_PARSE}

    def test_bom_prefixed_python_still_parses(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8-sig")
        assert _findings(workspace) == []

    def test_unresolved_relative_import_is_a_warning(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("from .helpers import thing\n", encoding="utf-8")
        findings = _findings(workspace, l1_diagnosis.CHECK_PYTHON_RELATIVE_IMPORT)

        assert len(findings) == 1
        assert findings[0]["severity"] == "warning"
        assert "helpers" in findings[0]["message"]

    def test_resolved_relative_import_is_not_reported(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("from .helpers import thing\n", encoding="utf-8")
        (workspace / "helpers.py").write_text("thing = 1\n", encoding="utf-8")
        assert _findings(workspace, l1_diagnosis.CHECK_PYTHON_RELATIVE_IMPORT) == []

    def test_relative_import_of_a_package_is_not_reported(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("from .pkg import thing\n", encoding="utf-8")
        (workspace / "pkg").mkdir()
        (workspace / "pkg" / "__init__.py").write_text("thing = 1\n", encoding="utf-8")
        assert _findings(workspace, l1_diagnosis.CHECK_PYTHON_RELATIVE_IMPORT) == []

    def test_absolute_third_party_import_is_never_flagged(self, workspace: Path) -> None:
        """
        Offline, a missing package is indistinguishable from an uninstalled
        one. Flagging it would be the false alarm L1 exists to avoid.
        """
        (workspace / "demo.py").write_text("import requests\nfrom flask import Flask\n", encoding="utf-8")
        assert _findings(workspace) == []


class TestDataFormatChecks:

    def test_broken_json_is_reported_with_a_position(self, workspace: Path) -> None:
        (workspace / "conf.json").write_text('{"a": 1,\n "b": }\n', encoding="utf-8")
        findings = _findings(workspace, l1_diagnosis.CHECK_JSON_PARSE)
        assert len(findings) == 1
        assert findings[0]["line"] == 2

    def test_valid_json_is_clean(self, workspace: Path) -> None:
        (workspace / "conf.json").write_text('{"a": [1, 2]}\n', encoding="utf-8")
        assert _findings(workspace) == []

    def test_broken_toml_is_reported(self, workspace: Path) -> None:
        (workspace / "pyproject.toml").write_text("[tool\nname = 1\n", encoding="utf-8")
        assert len(_findings(workspace, l1_diagnosis.CHECK_TOML_PARSE)) == 1

    def test_valid_toml_is_clean(self, workspace: Path) -> None:
        (workspace / "pyproject.toml").write_text('[tool]\nname = "flare"\n', encoding="utf-8")
        assert _findings(workspace) == []

    def test_broken_yaml_is_reported_when_pyyaml_is_available(self, workspace: Path) -> None:
        pytest.importorskip("yaml")
        (workspace / "conf.yml").write_text("a: [1,\nb: 2\n", encoding="utf-8")
        assert len(_findings(workspace, l1_diagnosis.CHECK_YAML_PARSE)) == 1

    def test_valid_yaml_is_clean_when_pyyaml_is_available(self, workspace: Path) -> None:
        pytest.importorskip("yaml")
        (workspace / "conf.yml").write_text("a: 1\nb: [2, 3]\n", encoding="utf-8")
        assert _findings(workspace) == []


class TestEncodingChecks:

    def test_nul_bytes_make_a_file_non_text(self, workspace: Path) -> None:
        (workspace / "demo.py").write_bytes(b"x = 1\x00\n")
        findings = _findings(workspace, l1_diagnosis.CHECK_TEXT_ENCODING)
        assert len(findings) == 1
        assert findings[0]["severity"] == "error"

    def test_invalid_utf8_is_a_finding_not_a_crash(self, workspace: Path) -> None:
        """
        The old gate read with strict utf-8-sig, so an undecodable file raised
        and took the whole worker phase down as FLARE-501. It is a finding now.
        """
        (workspace / "demo.py").write_bytes(b"x = '\xff\xfe invalid'\n")
        findings = _findings(workspace, l1_diagnosis.CHECK_TEXT_ENCODING)
        assert len(findings) == 1
        assert "UTF-8" in findings[0]["message"]


class TestFindingCap:

    def test_finding_list_is_capped_and_says_so(self, workspace: Path) -> None:
        for index in range(l1_diagnosis.MAX_FINDINGS + 5):
            (workspace / f"f{index:04d}.json").write_text("{", encoding="utf-8")
        diagnosis = l1_diagnosis.diagnose(workspace)
        assert len(diagnosis["findings"]) == l1_diagnosis.MAX_FINDINGS
        assert diagnosis["findings_truncated"] is True


# ==============================================================================
# Back compatibility -- the old gate must keep working unchanged
# ==============================================================================

class TestBackCompatibleSyntaxView:

    def test_view_has_the_legacy_shape(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("def add(a, b):\n    return a +\n", encoding="utf-8")
        legacy = l1_diagnosis.syntax_findings(l1_diagnosis.diagnose(workspace))
        assert set(legacy[0]) == {"path", "line", "offset", "message"}

    def test_view_excludes_non_syntax_checks(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("from .missing import thing\n", encoding="utf-8")
        (workspace / "conf.json").write_text("{", encoding="utf-8")
        assert l1_diagnosis.syntax_findings(l1_diagnosis.diagnose(workspace)) == []

    def test_worker_still_exposes_the_old_entry_point(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker, "WORKSPACE", workspace)
        (workspace / "demo.py").write_text("def add(a, b):\n    return a +\n", encoding="utf-8")
        findings = worker.check_python_syntax()
        assert len(findings) == 1
        assert findings[0]["path"] == "demo.py"


# ==============================================================================
# How the orchestrator hands L1 to the model
# ==============================================================================

class TestPromptRendering:

    def _diagnosis(self, workspace: Path) -> dict:
        return {"l1_diagnosis": l1_diagnosis.diagnose(workspace)}

    def test_rendering_states_that_nothing_was_executed(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        rendered = main.format_l1_diagnosis(self._diagnosis(workspace))
        assert "no submitted code was executed" in rendered

    def test_rendering_carries_findings_with_position(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("def add(a, b):\n    return a +\n", encoding="utf-8")
        rendered = main.format_l1_diagnosis(self._diagnosis(workspace))
        assert "ERROR" in rendered
        assert "demo.py:2" in rendered
        assert "python.syntax" in rendered
        assert "parsing stopped here" in rendered

    def test_rendering_carries_the_blind_spots(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(l1_diagnosis, "_load_yaml_module", lambda: None)
        (workspace / "app.js").write_text("function f( {\n", encoding="utf-8")
        (workspace / "conf.yml").write_text("a: 1\n", encoding="utf-8")

        rendered = main.format_l1_diagnosis(self._diagnosis(workspace))
        assert "check skipped: yaml.parse" in rendered
        assert "not diagnosed: app.js" in rendered, (
            "a planner must be able to tell 'checked and clean' from 'never looked'"
        )

    def test_rendering_falls_back_for_results_staged_before_l1(self) -> None:
        legacy = {"job_id": "x", "preflight_python_syntax": []}
        rendered = main.format_l1_diagnosis(legacy)
        assert "Preflight worker result:" in rendered

    def test_prompt_includes_the_structured_section(
        self, workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix the bug",
            files=[main.JobFile(path="demo.py", content="def add(a, b):\n    return a +\n")],
        ))
        staged = main.job_dir(job_id) / "workspace"

        prompt = main.build_prompt(job_id, {"l1_diagnosis": l1_diagnosis.diagnose(staged)})
        assert "L1 diagnosis" in prompt
        assert "python.syntax" in prompt
        assert "Fix the bug" in prompt
