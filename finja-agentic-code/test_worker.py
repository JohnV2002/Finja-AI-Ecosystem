#!/usr/bin/env python3
"""
======================================================================
         Flare (Finja Agentic Code) – Worker Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
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
        (workspace / "demo.py").write_text("hello = 1\n", encoding="utf-8")
        snapshot = worker.snapshot_files()
        assert snapshot[0]["content"] == "hello = 1\n"


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


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--color=yes"])
