"""
======================================================================
         Flare (Finja Agentic Code) – Worker
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / worker
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    - Preflight is now the L1 diagnosis (see l1_diagnosis.py); the
      long-standing python-syntax gate is a view onto it, so the gate
      and the diagnosis cannot disagree.
    - L3 runs submitted Python unittest files in the offline sandbox and
      records reproducible input/result evidence.
    - The workspace snapshot is taken from the bytes, not from text, so a
      file with Windows line endings comes back exactly as it is on disk.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import l1_diagnosis


JOBS_DIR = Path(os.getenv("JOBS_DIR", "/jobs"))
JOB_ID = os.environ["JOB_ID"]
JOB_PHASE = os.getenv("JOB_PHASE", "preflight")

ROOT = JOBS_DIR / JOB_ID
WORKSPACE = ROOT / "workspace"
TEST_OUTPUT_LIMIT = 16_384
TEST_TIMEOUT_SECONDS = 30


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def list_files() -> list[Path]:
    return sorted(path for path in WORKSPACE.rglob("*") if path.is_file())


def run_l1_diagnosis() -> dict:
    """Flare's first look: static, offline, deterministic (see l1_diagnosis)."""
    return l1_diagnosis.diagnose(WORKSPACE)


def check_python_syntax() -> list[dict]:
    """
    The orchestrator's long-standing syntax gate, now a view onto the L1
    diagnosis instead of a second parser. One source of truth means the
    gate and the diagnosis can never disagree about a file.
    """
    return l1_diagnosis.syntax_findings(run_l1_diagnosis())


def apply_model_patch() -> dict:
    diff_path = ROOT / "model.patch"
    if not diff_path.exists():
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "model.patch is missing",
        }
    completed = subprocess.run(
        ["patch", "--batch", "--no-backup-if-mismatch", "-p0", "-i", str(diff_path)],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def diff_path_has_content() -> bool:
    path = ROOT / "model.patch"
    return path.exists() and bool(path.read_text(encoding="utf-8").strip())


def snapshot_files() -> list[dict]:
    # Decode the bytes, do not read text. Reading text translates "\r\n" to
    # "\n", so a file with Windows line endings came back altered even when
    # nothing had touched it. The digest the sandbox compares before and after
    # the apply is taken over the bytes on disk, so an altered snapshot made
    # the verification disagree with the test: any job holding an untouched
    # CRLF file was rolled back with "Approved candidate differed from its
    # sandbox test evidence".
    return [
        {
            "path": path.relative_to(WORKSPACE).as_posix(),
            "content": path.read_bytes().decode("utf-8", errors="replace"),
        }
        for path in list_files()
        if not path.name.endswith(".orig")
    ]


def _workspace_fingerprint() -> str:
    """Hash the exact candidate bytes before tests can create artifacts."""
    digest = hashlib.sha256()
    for path in list_files():
        rel = path.relative_to(WORKSPACE).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def run_reproducible_tests() -> dict:
    """Run only stdlib unittest discovery, with a fixed offline environment."""
    test_files = [
        path.relative_to(WORKSPACE).as_posix()
        for path in list_files()
        if path.name.startswith("test_") and path.suffix == ".py"
    ]
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-v"]
    evidence = {
        "schema_version": 1,
        "runner": "python-unittest",
        "python_version": sys.version.split()[0],
        "runner_sha256": hashlib.sha256(
            Path(__file__).read_bytes() + Path(l1_diagnosis.__file__).read_bytes()
        ).hexdigest(),
        "command": ["python", "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-v"],
        "source_sha256": _workspace_fingerprint(),
        "test_files": test_files,
        "tests_run": 0,
        "status": "not_run",
        "output_sha256": None,
        "log_artifact": None,
    }
    if not test_files:
        return evidence
    environment = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        completed = subprocess.run(
            command, cwd=WORKSPACE, env=environment,
            capture_output=True, timeout=TEST_TIMEOUT_SECONDS, check=False,
        )
        output = completed.stdout + b"\n" + completed.stderr
        match = re.search(rb"Ran (\d+) tests?", completed.stderr)
        evidence["tests_run"] = int(match.group(1)) if match else 0
        evidence["status"] = "passed" if completed.returncode == 0 and evidence["tests_run"] > 0 else "failed"
        evidence["returncode"] = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"") + b"\n" + (exc.stderr or b"")
        evidence["status"] = "timed_out"
        evidence["returncode"] = None
    evidence["output_sha256"] = hashlib.sha256(output).hexdigest()
    evidence["workspace_mutated"] = _workspace_fingerprint() != evidence["source_sha256"]
    if evidence["workspace_mutated"] and evidence["status"] == "passed":
        evidence["status"] = "failed"
    artifact = f"{JOB_PHASE}_tests.log"
    (ROOT / artifact).write_bytes(output[-TEST_OUTPUT_LIMIT:])
    evidence["log_artifact"] = artifact
    return evidence


def main() -> None:
    preflight_diagnosis = run_l1_diagnosis()
    result: dict = {
        "job_id": JOB_ID,
        "phase": JOB_PHASE,
        "l1_diagnosis": preflight_diagnosis,
        "preflight_python_syntax": l1_diagnosis.syntax_findings(preflight_diagnosis),
        "patch_applied": False,
        "patch_result": None,
        "postflight_l1_diagnosis": None,
        "postflight_python_syntax": None,
        "test_evidence": None,
        "files": None,
    }

    if JOB_PHASE in {"test_patch", "apply_patch"} and diff_path_has_content():
        patch_result = apply_model_patch()
        result["patch_result"] = patch_result
        result["patch_applied"] = patch_result["returncode"] == 0

    postflight_diagnosis = run_l1_diagnosis()
    result["postflight_l1_diagnosis"] = postflight_diagnosis
    result["postflight_python_syntax"] = l1_diagnosis.syntax_findings(postflight_diagnosis)
    result["files"] = snapshot_files()
    if JOB_PHASE in {"test_patch", "verify"} and not result["postflight_python_syntax"]:
        result["test_evidence"] = run_reproducible_tests()
    write_json(ROOT / "result.json", result)
    write_json(ROOT / f"{JOB_PHASE}_result.json", result)


if __name__ == "__main__":
    main()
