"""
======================================================================
         Flare (Finja Agentic Code) – Worker
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / worker
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path


JOBS_DIR = Path(os.getenv("JOBS_DIR", "/jobs"))
JOB_ID = os.environ["JOB_ID"]
JOB_PHASE = os.getenv("JOB_PHASE", "preflight")

ROOT = JOBS_DIR / JOB_ID
WORKSPACE = ROOT / "workspace"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_files() -> list[Path]:
    return sorted(path for path in WORKSPACE.rglob("*") if path.is_file())


def check_python_syntax() -> list[dict]:
    findings: list[dict] = []
    for path in list_files():
        if path.suffix != ".py":
            continue
        rel = path.relative_to(WORKSPACE).as_posix()
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
        except SyntaxError as exc:
            findings.append(
                {
                    "path": rel,
                    "line": exc.lineno,
                    "offset": exc.offset,
                    "message": exc.msg,
                }
            )
    return findings


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


def snapshot_files() -> list[dict]:
    return [
        {
            "path": path.relative_to(WORKSPACE).as_posix(),
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }
        for path in list_files()
        if not path.name.endswith(".orig")
    ]


def main() -> None:
    preflight = check_python_syntax()
    result: dict = {
        "job_id": JOB_ID,
        "phase": JOB_PHASE,
        "preflight_python_syntax": preflight,
        "patch_applied": False,
        "patch_result": None,
        "postflight_python_syntax": None,
        "files": None,
    }

    if JOB_PHASE == "apply_patch":
        patch_result = apply_model_patch()
        result["patch_result"] = patch_result
        result["patch_applied"] = patch_result["returncode"] == 0

    result["postflight_python_syntax"] = check_python_syntax()
    result["files"] = snapshot_files()
    write_json(ROOT / "result.json", result)
    write_json(ROOT / f"{JOB_PHASE}_result.json", result)


if __name__ == "__main__":
    main()
