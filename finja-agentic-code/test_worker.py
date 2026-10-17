#!/usr/bin/env python3
"""
======================================================================
         Flare (Finja Agentic Code) – Worker Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Unit tests for the sandbox worker (worker/worker.py).
               The worker runs offline inside a throwaway container in
               production, but every function it uses is plain Python
               (ast-based syntax check, file listing, the `patch` call)
               and testable directly against a temp workspace -- no
               Docker needed.

  Note: worker.py reads JOB_ID/JOBS_DIR from the environment at import
        time (it's designed to be the container entrypoint), so this
        module sets those env vars BEFORE importing it, then retargets
        the module-level WORKSPACE/ROOT globals per-test via monkeypatch.

  New in v1.0.0:
    • Initial pytest suite for the worker

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

# worker.py reads these at import time -- must be set before the import.
os.environ.setdefault("JOB_ID", "testjob")
os.environ.setdefault("JOBS_DIR", "/tmp/finja-agentic-test-jobs")

_WORKER_DIR = Path(__file__).parent / "worker"
sys.path.insert(0, str(_WORKER_DIR))

import worker  # noqa: E402


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Point the worker's module-level ROOT/WORKSPACE globals at a fresh temp
    job folder. Returns the workspace dir for the test to populate.
    """
    root = tmp_path / "testjob"
    ws = root / "workspace"
    ws.mkdir(parents=True)
    monkeypatch.setattr(worker, "ROOT", root)
    monkeypatch.setattr(worker, "WORKSPACE", ws)
    return ws


# ==============================================================================
# check_python_syntax()
# ==============================================================================

class TestCheckPythonSyntax:
    def test_clean_file_has_no_findings(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        assert worker.check_python_syntax() == []

    def test_broken_file_is_reported(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("def add(a, b):\n    return a +\n", encoding="utf-8")
        findings = worker.check_python_syntax()

        assert len(findings) == 1
        assert findings[0]["path"] == "demo.py"
        assert findings[0]["line"] is not None
        assert findings[0]["message"]

    def test_non_python_files_are_ignored(self, workspace: Path) -> None:
        # A .txt with "invalid python" must not be syntax-checked.
        (workspace / "notes.txt").write_text("this is := not )( python", encoding="utf-8")
        assert worker.check_python_syntax() == []

    def test_handles_bom_encoded_file(self, workspace: Path) -> None:
        """Worker reads with utf-8-sig, so a BOM-prefixed file must still parse."""
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8-sig")
        assert worker.check_python_syntax() == []


# ==============================================================================
# list_files() / snapshot_files()
# ==============================================================================

class TestFileListing:
    def test_list_files_finds_nested(self, workspace: Path) -> None:
        (workspace / "a.py").write_text("x=1\n", encoding="utf-8")
        (workspace / "sub").mkdir()
        (workspace / "sub" / "b.py").write_text("y=2\n", encoding="utf-8")

        rels = [p.relative_to(workspace).as_posix() for p in worker.list_files()]
        assert rels == ["a.py", "sub/b.py"]

    def test_snapshot_excludes_orig_files(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("x=1\n", encoding="utf-8")
        (workspace / "demo.py.orig").write_text("old\n", encoding="utf-8")

        snapshot = worker.snapshot_files()
        paths = [entry["path"] for entry in snapshot]
        assert "demo.py" in paths
        assert "demo.py.orig" not in paths

    def test_snapshot_includes_content(self, workspace: Path) -> None:
        # newline="\n": a plain write_text turns "\n" into "\r\n" on Windows, and
        # the snapshot now returns the bytes exactly as they are on disk.
        (workspace / "demo.py").write_text("hello = 1\n", encoding="utf-8", newline="\n")
        snapshot = worker.snapshot_files()
        assert snapshot[0]["content"] == "hello = 1\n"

    def test_snapshot_preserves_windows_line_endings(self, workspace: Path) -> None:
        """
        Reading text would translate Windows line endings to Unix ones, so a
        file nothing had touched came back altered. The sandbox compares a digest of the bytes
        on disk before and after the apply, and a snapshot that differs from
        the disk made any job holding an untouched CRLF file fail that
        comparison and roll back.
        """
        (workspace / "crlf.py").write_bytes(b"x = 1\r\ny = 2\r\n")
        (workspace / "lf.py").write_bytes(b"x = 1\ny = 2\n")
        (workspace / "mixed.py").write_bytes(b"a\r\nb\nc\r\n")

        by_path = {entry["path"]: entry["content"] for entry in worker.snapshot_files()}
        assert by_path["crlf.py"] == "x = 1\r\ny = 2\r\n"
        assert by_path["lf.py"] == "x = 1\ny = 2\n"
        assert by_path["mixed.py"] == "a\r\nb\nc\r\n"

    def test_restoring_a_snapshot_reproduces_the_workspace_digest(
        self, workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        The invariant the verification depends on: write the snapshot back the
        way the orchestrator does (newline="\\n", no translation) and the
        workspace fingerprint must be unchanged, for any line endings.
        """
        (workspace / "crlf.py").write_bytes(b"x = 1\r\ny = 2\r\n")
        (workspace / "sub").mkdir()
        (workspace / "sub" / "lf.py").write_bytes(b"z = 3\n")
        before = worker._workspace_fingerprint()

        restored = tmp_path / "restored" / "workspace"
        restored.mkdir(parents=True)
        for entry in worker.snapshot_files():
            target = restored / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry["content"], encoding="utf-8", newline="\n")

        monkeypatch.setattr(worker, "WORKSPACE", restored)
        assert worker._workspace_fingerprint() == before


# ==============================================================================
# apply_model_patch()
# ==============================================================================

@pytest.mark.skipif(shutil.which("patch") is None, reason="`patch` binary not available")
class TestApplyModelPatch:
    def test_missing_patch_file_reports_error(self, workspace: Path) -> None:
        # ROOT has no model.patch
        result = worker.apply_model_patch()
        assert result["returncode"] == 1
        assert "missing" in result["stderr"].lower()

    def test_applies_a_valid_patch(self, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Stage a file and a unified diff that fixes it.
        (workspace / "demo.py").write_text("def add(a, b):\n    return a\n", encoding="utf-8")
        patch_text = (
            "--- demo.py\n"
            "+++ demo.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def add(a, b):\n"
            "-    return a\n"
            "+    return a + b\n"
        )
        (worker.ROOT / "model.patch").write_text(patch_text, encoding="utf-8")

        result = worker.apply_model_patch()

        assert result["returncode"] == 0
        assert "return a + b" in (workspace / "demo.py").read_text(encoding="utf-8")


# ==============================================================================
# main() -- end-to-end within the worker (no Docker)
# ==============================================================================

class TestWorkerMain:
    def test_preflight_writes_result_json(self, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker, "JOB_PHASE", "preflight")
        (workspace / "demo.py").write_text("def add(a, b):\n    return a +\n", encoding="utf-8")

        worker.main()

        import json
        result = json.loads((worker.ROOT / "result.json").read_text(encoding="utf-8"))
        assert result["phase"] == "preflight"
        assert result["patch_applied"] is False
        # The broken file must show up in the preflight syntax findings.
        assert len(result["preflight_python_syntax"]) == 1
        assert (worker.ROOT / "preflight_result.json").exists()

    @pytest.mark.skipif(shutil.which("patch") is None, reason="`patch` binary not available")
    def test_test_patch_phase_applies_candidate_in_disposable_workspace(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker, "JOB_PHASE", "test_patch")
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        (worker.ROOT / "model.patch").write_text(
            "--- demo.py\n+++ demo.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
            encoding="utf-8",
        )

        worker.main()

        result = json.loads((worker.ROOT / "test_patch_result.json").read_text(encoding="utf-8"))
        assert result["patch_applied"] is True
        assert result["files"] == [{"path": "demo.py", "content": "x = 2\n"}]


class TestL3SandboxTests:
    def test_pass_report_is_repeatable_for_same_input(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker, "JOB_PHASE", "test_patch")
        (workspace / "demo.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (workspace / "test_demo.py").write_text(
            "import unittest\nfrom demo import add\n"
            "class DemoTest(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )

        first = worker.run_reproducible_tests()
        second = worker.run_reproducible_tests()

        assert first["status"] == second["status"] == "passed"
        assert first["tests_run"] == second["tests_run"] == 1
        assert first["source_sha256"] == second["source_sha256"]
        assert first["workspace_mutated"] is False
        assert first["log_artifact"] == "test_patch_tests.log"

    def test_failing_test_is_not_green(self, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker, "JOB_PHASE", "test_patch")
        (workspace / "test_bad.py").write_text(
            "import unittest\nclass Bad(unittest.TestCase):\n"
            "    def test_no(self):\n        self.assertEqual(1, 2)\n",
            encoding="utf-8",
        )
        assert worker.run_reproducible_tests()["status"] == "failed"

    def test_no_tests_is_reported_not_run(self, workspace: Path) -> None:
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        evidence = worker.run_reproducible_tests()
        assert evidence["status"] == "not_run"
        assert evidence["tests_run"] == 0

    def test_tests_cannot_mutate_promoted_candidate(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker, "JOB_PHASE", "test_patch")
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        (workspace / "test_mutate.py").write_text(
            "import unittest\nfrom pathlib import Path\n"
            "class Mutate(unittest.TestCase):\n"
            "    def test_change(self):\n        Path('demo.py').write_text('x = 2\\n')\n",
            encoding="utf-8",
        )
        report = worker.run_reproducible_tests()
        assert report["status"] == "failed"
        assert report["workspace_mutated"] is True


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--color=yes"])
