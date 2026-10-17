"""
======================================================================
      Flare (Finja Agentic Code) – Broken Demo Worker (Test Track)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / worker-broken
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    - First version: deliberately broken drop-in worker for Phase A.

----------------------------------------------------------------------

  A DELIBERATELY BROKEN drop-in replacement for the real worker sandbox.
  Same contract as worker/worker.py (JOB_ID, JOB_PHASE, JOBS_DIR, the
  /jobs mount, {phase}_result.json), but each job phase can be told to
  misbehave in one known-bad way. That makes Flare's own stability guards
  testable on purpose instead of by accident.

  This image is test infrastructure. It must never be the configured
  WORKER_IMAGE of a production stack.

  The fault plan is resolved in this order:
    1. workspace/flare_fault.json  -- travels inside the job payload
    2. FLARE_FAULT_PLAN            -- stack-wide default via env
    3. "ok"                        -- behave like the real worker

  Plan shapes (both accepted in either place):
    "hang"                                    every phase hangs
    "verify=hang,default=ok"                  only the verify phase hangs
    {"default": "ok", "phases": {"verify": "hang"}}

  Modes, and the guard each one is meant to trip:
    ok              real worker logic                 -- happy path
    slow:<seconds>  late but correct                  -- heartbeats / reports
    hang            never returns                     -- FLARE-500 + fail-soft
    crash:<code>    non-zero exit                     -- FLARE-501
    no_result       exits 0, writes nothing           -- FLARE-501
    invalid_result  writes unparsable JSON            -- FLARE-501
    patch_fail      patch_result.returncode != 0      -- FLARE-501
    syntax_fail     postflight syntax finding         -- FLARE-501
    wrong_job       result claims another job_id      -- FLARE-801
    wrong_phase     result claims another phase       -- FLARE-801
    oom             grows past the container limit    -- FLARE-501 (killed)
    inject_patch:<v> plants a candidate diff for L2   -- FLARE-606 / FLARE-607
                    variants: outside, unknown, prefixed, prose, huge

  A broken plan is reported on stderr with a non-zero exit, which the
  orchestrator surfaces as FLARE-501 with the stderr tail attached. The
  sandbox has no structured error channel of its own by design: it holds
  no secrets and shares no code with core/exceptions.py.

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
import os
import sys
import time
from pathlib import Path

import worker

JOBS_DIR = Path(os.getenv("JOBS_DIR", "/jobs"))
JOB_ID = os.environ["JOB_ID"]
JOB_PHASE = os.getenv("JOB_PHASE", "preflight")
FAULT_PLAN_ENV = os.getenv("FLARE_FAULT_PLAN", "")

ROOT = JOBS_DIR / JOB_ID
WORKSPACE = ROOT / "workspace"

FAULT_FILE_NAME = "flare_fault.json"
PLACEHOLDER_JOB_ID = "00000000-0000-0000-0000-000000000000"

MODE_OK = "ok"
MODE_SLOW = "slow"
MODE_HANG = "hang"
MODE_CRASH = "crash"
MODE_NO_RESULT = "no_result"
MODE_INVALID_RESULT = "invalid_result"
MODE_PATCH_FAIL = "patch_fail"
MODE_SYNTAX_FAIL = "syntax_fail"
MODE_WRONG_JOB = "wrong_job"
MODE_WRONG_PHASE = "wrong_phase"
MODE_OOM = "oom"
MODE_INJECT_PATCH = "inject_patch"

KNOWN_MODES = frozenset({
    MODE_OK, MODE_SLOW, MODE_HANG, MODE_CRASH, MODE_NO_RESULT,
    MODE_INVALID_RESULT, MODE_PATCH_FAIL, MODE_SYNTAX_FAIL,
    MODE_WRONG_JOB, MODE_WRONG_PHASE, MODE_OOM, MODE_INJECT_PATCH,
})

# Candidate diffs the L2 scope review must refuse. The dry-run track calls no
# model, so there is no other way to put a diff in front of L2: the worker
# plants one in the job root, where the orchestrator picks it up after this
# phase and reviews it before any testing happens.
INJECTED_PATCHES = {
    "outside": (
        "--- ../../../etc/passwd\n"
        "+++ ../../../etc/passwd\n"
        "@@ -1 +1 @@\n"
        "-root:x:0:0\n"
        "+flare:x:0:0\n"
    ),
    "unknown": (
        "--- never_submitted.py\n"
        "+++ never_submitted.py\n"
        "@@ -1 +1 @@\n"
        "-a = 1\n"
        "+a = 2\n"
    ),
    "prefixed": (
        "--- a/demo.py\n"
        "+++ b/demo.py\n"
        "@@ -1 +1 @@\n"
        "-def add(a, b):\n"
        "+def add(a, b):  # touched\n"
    ),
    "prose": "Sure! The bug is on line 2. I would change the operator.\n",
    "huge": (
        "--- demo.py\n"
        "+++ demo.py\n"
        "@@ -1,2 +1,400 @@\n"
        "-def add(a, b):\n"
        "-    return a - b\n"
        + "".join(f"+line_{index} = {index}\n" for index in range(400))
    ),
}

HANG_SLEEP_SECONDS = 86400.0
DEFAULT_SLOW_SECONDS = 2.0
DEFAULT_CRASH_CODE = 9
PLAN_EXIT_CODE = 2
OOM_CHUNK_BYTES = 64 * 1024 * 1024
# Keeps the mode survivable when someone runs it outside a memory-capped
# container: without a cap "oom" would eat the whole dev machine.
OOM_MAX_BYTES = 4 * 1024 * 1024 * 1024


def _fail_hard(message: str) -> None:
    """Report an unusable fault plan the only way a sandbox can: stderr + exit."""
    sys.stderr.write(f"flare-fault: {message}\n")
    raise SystemExit(PLAN_EXIT_CODE)


def _normalise_plan(data: object, source: str) -> dict:
    if isinstance(data, str):
        return {"default": data.strip() or MODE_OK, "phases": {}}
    if not isinstance(data, dict):
        _fail_hard(f"{source} must hold an object or a mode string")
    phases = data.get("phases", {})
    if not isinstance(phases, dict):
        _fail_hard(f"{source} has a non-object 'phases'")
    default = data.get("default", MODE_OK)
    if not isinstance(default, str):
        _fail_hard(f"{source} has a non-string 'default'")
    return {
        "default": default.strip() or MODE_OK,
        "phases": {str(key): str(value).strip() for key, value in phases.items()},
    }


def parse_plan(raw: str, source: str = "fault plan") -> dict:
    """Read a plan from JSON, or from the ``phase=mode,...`` shorthand."""
    text = (raw or "").strip()
    if not text:
        return {"default": MODE_OK, "phases": {}}
    if text[0] in '{["':
        try:
            parsed = json.loads(text)
        except ValueError:
            _fail_hard(f"{source} is not valid JSON")
        return _normalise_plan(parsed, source)
    if "=" not in text:
        return {"default": text, "phases": {}}

    default = MODE_OK
    phases: dict[str, str] = {}
    for chunk in text.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        if "=" not in entry:
            _fail_hard(f"{source} entry {entry!r} is missing '='")
        key, _, value = entry.partition("=")
        key, value = key.strip(), value.strip()
        if not value:
            _fail_hard(f"{source} entry {entry!r} has an empty mode")
        if key == "default":
            default = value
        else:
            phases[key] = value
    return {"default": default, "phases": phases}


def resolve_plan() -> dict:
    """Prefer the plan that travelled with the job over the stack default."""
    payload_plan = WORKSPACE / FAULT_FILE_NAME
    if payload_plan.is_file():
        try:
            raw = payload_plan.read_text(encoding="utf-8-sig")
        except OSError as exc:
            _fail_hard(f"{FAULT_FILE_NAME} could not be read: {type(exc).__name__}")
        return parse_plan(raw, FAULT_FILE_NAME)
    return parse_plan(FAULT_PLAN_ENV, "FLARE_FAULT_PLAN")


def resolve_mode(plan: dict, phase: str) -> str:
    return plan["phases"].get(phase, plan["default"])


def split_mode(spec: str) -> tuple[str, str]:
    name, _, argument = (spec or "").strip().partition(":")
    return name.strip(), argument.strip()


def _sync_real_worker() -> None:
    """Point the real worker's module globals at this job before delegating."""
    worker.JOBS_DIR = JOBS_DIR
    worker.JOB_ID = JOB_ID
    worker.JOB_PHASE = JOB_PHASE
    worker.ROOT = ROOT
    worker.WORKSPACE = WORKSPACE


def _write_results(result: dict) -> None:
    worker.write_json(ROOT / "result.json", result)
    worker.write_json(ROOT / f"{JOB_PHASE}_result.json", result)


def _base_result() -> dict:
    _sync_real_worker()
    return {
        "job_id": JOB_ID,
        "phase": JOB_PHASE,
        "preflight_python_syntax": [],
        "patch_applied": False,
        "patch_result": None,
        "postflight_python_syntax": [],
        "files": worker.snapshot_files(),
        "fault_injected": True,
    }


def _run_ok(delay_seconds: float = 0.0) -> None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    _sync_real_worker()
    worker.main()


def _run_slow(argument: str) -> None:
    seconds = DEFAULT_SLOW_SECONDS
    if argument:
        try:
            seconds = float(argument)
        except ValueError:
            _fail_hard(f"slow duration {argument!r} is not a number")
    if seconds < 0:
        _fail_hard(f"slow duration {argument!r} is negative")
    _run_ok(seconds)


def _run_hang() -> None:
    sys.stderr.write("flare-fault: hanging until the orchestrator kills this phase\n")
    sys.stderr.flush()
    while True:
        time.sleep(HANG_SLEEP_SECONDS)


def _run_crash(argument: str) -> None:
    code = DEFAULT_CRASH_CODE
    if argument:
        try:
            code = int(argument)
        except ValueError:
            _fail_hard(f"crash code {argument!r} is not an integer")
    if code == 0:
        _fail_hard("crash:0 would look like success")
    sys.stderr.write(f"flare-fault: exiting with {code} before writing a result\n")
    raise SystemExit(code)


def _run_invalid_result() -> None:
    target = ROOT / f"{JOB_PHASE}_result.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{ this is deliberately not json", encoding="utf-8")


def _run_patch_fail() -> None:
    result = _base_result()
    result["patch_applied"] = False
    result["patch_result"] = {
        "returncode": 1,
        "stdout": "",
        "stderr": "flare-fault: the candidate patch was refused on purpose",
    }
    _write_results(result)


def _run_syntax_fail() -> None:
    result = _base_result()
    first = result["files"][0]["path"] if result["files"] else "demo.py"
    result["postflight_python_syntax"] = [{
        "path": first,
        "line": 1,
        "offset": 1,
        "message": "flare-fault: injected syntax finding",
    }]
    _write_results(result)


def _run_wrong_job() -> None:
    result = _base_result()
    result["job_id"] = PLACEHOLDER_JOB_ID
    _write_results(result)


def _run_wrong_phase() -> None:
    result = _base_result()
    result["phase"] = "preflight" if JOB_PHASE != "preflight" else "verify"
    _write_results(result)


def _run_inject_patch(argument: str) -> None:
    """Plant a candidate diff for L2 to refuse, then behave normally."""
    variant = argument or "outside"
    patch = INJECTED_PATCHES.get(variant)
    if patch is None:
        _fail_hard(
            f"unknown inject_patch variant {variant!r}; "
            f"known: {', '.join(sorted(INJECTED_PATCHES))}"
        )
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "model.patch").write_text(patch, encoding="utf-8")
    sys.stderr.write(f"flare-fault: planted a '{variant}' candidate diff for L2\n")
    _run_ok()


def _run_oom() -> None:
    sys.stderr.write("flare-fault: growing until the container memory limit kills this phase\n")
    sys.stderr.flush()
    blocks: list[bytearray] = []
    held = 0
    while held < OOM_MAX_BYTES:
        blocks.append(bytearray(OOM_CHUNK_BYTES))
        held += OOM_CHUNK_BYTES
    _fail_hard(f"oom grew to {held} bytes without being killed -- is there a memory limit?")


def main() -> None:
    plan = resolve_plan()
    spec = resolve_mode(plan, JOB_PHASE)
    mode, argument = split_mode(spec)
    if mode not in KNOWN_MODES:
        _fail_hard(f"unknown mode {spec!r} for phase {JOB_PHASE!r}")
    sys.stderr.write(f"flare-fault: phase={JOB_PHASE} mode={spec}\n")
    sys.stderr.flush()

    if mode == MODE_OK:
        _run_ok()
    elif mode == MODE_SLOW:
        _run_slow(argument)
    elif mode == MODE_HANG:
        _run_hang()
    elif mode == MODE_CRASH:
        _run_crash(argument)
    elif mode == MODE_NO_RESULT:
        sys.stderr.write("flare-fault: exiting 0 without writing a result\n")
    elif mode == MODE_INVALID_RESULT:
        _run_invalid_result()
    elif mode == MODE_PATCH_FAIL:
        _run_patch_fail()
    elif mode == MODE_SYNTAX_FAIL:
        _run_syntax_fail()
    elif mode == MODE_WRONG_JOB:
        _run_wrong_job()
    elif mode == MODE_WRONG_PHASE:
        _run_wrong_phase()
    elif mode == MODE_OOM:
        _run_oom()
    elif mode == MODE_INJECT_PATCH:
        _run_inject_patch(argument)


if __name__ == "__main__":
    main()
