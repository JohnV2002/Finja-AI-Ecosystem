#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Test Track Runner (Phase A)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / testbed
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    - First version: drives testbed/scenarios.json against a live stack.

----------------------------------------------------------------------

  Drives the known-bad scenarios from testbed/scenarios.json against a
  RUNNING orchestrator that uses the broken worker image, and checks the
  observed lifecycle against each scenario's expectation.

  This is an integration driver, not a pytest suite: it needs Docker and
  a live stack. The same guards are covered without Docker by
  test_testbed.py, which is what CI runs.

    docker build -f worker-broken/Dockerfile -t finja-agent-worker-broken:dev .
    docker compose -p flare-testbed -f docker-compose.yml -f docker-compose.testbed.yml up -d --build
    python testbed/run_testbed.py --base-url http://localhost:8078

  The -p is mandatory: without its own project name Compose replaces the
  production orchestrator container with this one. See the header of
  docker-compose.testbed.yml.

  Exit codes:
    0  every selected scenario met its expectation
    1  at least one scenario did not
    2  the track itself could not run (FLARE-100)

  Scenarios carrying a "requires" key are skipped: they need a process
  restart or two concurrent jobs, which this sequential driver does not
  orchestrate yet.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_MODULE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MODULE_ROOT))

from core.exceptions import RuntimeConfigurationError  # noqa: E402

SCENARIO_FILE = Path(__file__).resolve().parent / "scenarios.json"
FAULT_FILE_NAME = "flare_fault.json"

PRE_APPROVAL_STOP = frozenset({"awaiting_approval", "failed", "rolled_back", "completed"})
TERMINAL = frozenset({"completed", "failed", "rolled_back"})

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNUSABLE = 2


def _emit(line: str = "") -> None:
    """
    The runner's single report channel. One call site keeps the human-readable
    result table separate from the error path, which uses FLARE-100 on stderr,
    and matches the sandbox's existing sys.stderr.write idiom.
    """
    sys.stdout.write(f"{line}\n")


class ScenarioOutcome:
    """One scenario's verdict plus the mismatches that produced it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.skipped_because = ""
        self.mismatches: list[str] = []
        self.observed_status = ""

    @property
    def passed(self) -> bool:
        return not self.mismatches and not self.skipped_because

    def note(self, field: str, expected: object, actual: object) -> None:
        self.mismatches.append(f"{field}: expected {expected!r}, got {actual!r}")


def _request(url: str, token: str, *, method: str = "GET", payload: dict | None = None,
             extra_headers: dict | None = None, timeout: float = 15.0) -> tuple[int, dict]:
    """Return (http_status, decoded_body). HTTP errors are values, not exceptions."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except ValueError:
            return exc.code, {"detail": raw}
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeConfigurationError(
            f"The test track could not reach {url}: {type(exc).__name__}"
        ) from exc


def load_scenarios(path: Path = SCENARIO_FILE) -> list[dict]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeConfigurationError(f"{path.name} could not be read") from exc
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{path.name} is not valid JSON") from exc
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise RuntimeConfigurationError(f"{path.name} holds no scenarios")
    return scenarios


def build_payload(scenario: dict) -> dict:
    """Copy the payload and attach the fault plan as a staged file."""
    files = [dict(entry) for entry in scenario.get("files", [])]
    plan = scenario.get("plan")
    if plan is not None:
        files.append({
            "path": FAULT_FILE_NAME,
            "content": json.dumps(plan if isinstance(plan, dict) else str(plan), indent=2) + "\n",
        })
    return {
        "task": scenario["task"],
        "repository": scenario.get("repository", "flare-testbed"),
        "files": files,
    }


def _poll(base_url: str, token: str, job_id: str, stop_states: frozenset[str],
          budget_seconds: float) -> tuple[dict, int, int]:
    """
    Poll until the job reaches a stop state or the budget runs out.

    Returns the last status plus the highest heartbeat sequence and report
    count seen on the way, because those counters may be pruned once the
    job is terminal.
    """
    url = f"{base_url}/jobs/{job_id}"
    deadline = time.monotonic() + budget_seconds
    status: dict = {}
    max_sequence = 0
    max_reports = 0
    while True:
        _, status = _request(url, token)
        sequence = status.get("heartbeat_sequence")
        if isinstance(sequence, int):
            max_sequence = max(max_sequence, sequence)
        reports = status.get("progress_reports")
        if isinstance(reports, list):
            max_reports = max(max_reports, len(reports))
        if str(status.get("status", "")) in stop_states:
            return status, max_sequence, max_reports
        if time.monotonic() >= deadline:
            return status, max_sequence, max_reports
        time.sleep(0.5)


def _check(outcome: ScenarioOutcome, expect: dict, status: dict,
           max_sequence: int, max_reports: int) -> None:
    simple_fields = (
        ("terminal_status", "status"),
        ("error_code", "error_code"),
        ("outcome", "outcome"),
        ("retryable", "retryable"),
        ("timed_out_from_status", "timed_out_from_status"),
        ("locks_held", "locks_held"),
    )
    for expected_key, status_key in simple_fields:
        if expected_key not in expect:
            continue
        wanted = expect[expected_key]
        actual = status.get(status_key)
        if actual != wanted:
            outcome.note(expected_key, wanted, actual)

    if "min_progress_reports" in expect and max_reports < expect["min_progress_reports"]:
        outcome.note("min_progress_reports", f">={expect['min_progress_reports']}", max_reports)
    if "min_heartbeat_sequence" in expect and max_sequence < expect["min_heartbeat_sequence"]:
        outcome.note("min_heartbeat_sequence", f">={expect['min_heartbeat_sequence']}", max_sequence)

    _check_l1(outcome, expect, status)


def _find_l1_diagnosis(status: dict) -> dict | None:
    """
    Dig the L1 contract out of the job result. Pre-approval it rides under
    `preflight`, and once applied under `postflight`, so the shape differs
    by lifecycle half rather than by anything the scenario controls.
    """
    result = status.get("result")
    if not isinstance(result, dict):
        return None
    for section in ("preflight", "postflight"):
        phase = result.get(section)
        if isinstance(phase, dict) and isinstance(phase.get("l1_diagnosis"), dict):
            return phase["l1_diagnosis"]
    return None


def _check_l1(outcome: ScenarioOutcome, expect: dict, status: dict) -> None:
    l1_keys = ("l1_verdict", "min_l1_findings", "l1_undiagnosed_contains", "l1_executes_code")
    if not any(key in expect for key in l1_keys):
        return

    diagnosis = _find_l1_diagnosis(status)
    if diagnosis is None:
        outcome.note("l1_diagnosis", "present in the job result", None)
        return

    if "l1_verdict" in expect and diagnosis.get("verdict") != expect["l1_verdict"]:
        outcome.note("l1_verdict", expect["l1_verdict"], diagnosis.get("verdict"))
    if "l1_executes_code" in expect and diagnosis.get("executes_code") != expect["l1_executes_code"]:
        outcome.note("l1_executes_code", expect["l1_executes_code"], diagnosis.get("executes_code"))

    if "min_l1_findings" in expect:
        found = len(diagnosis.get("findings", []))
        if found < expect["min_l1_findings"]:
            outcome.note("min_l1_findings", f">={expect['min_l1_findings']}", found)

    if "l1_undiagnosed_contains" in expect:
        wanted = expect["l1_undiagnosed_contains"]
        paths = [entry.get("path") for entry in diagnosis.get("undiagnosed", [])]
        if wanted not in paths:
            outcome.note("l1_undiagnosed_contains", wanted, paths)


def run_scenario(scenario: dict, base_url: str, token: str, budget: float) -> ScenarioOutcome:
    outcome = ScenarioOutcome(scenario["name"])
    if scenario.get("requires"):
        outcome.skipped_because = f"needs {scenario['requires']}"
        return outcome

    expect = scenario.get("expect", {})
    submit_status, created = _request(
        f"{base_url}/jobs", token, method="POST", payload=build_payload(scenario)
    )

    expected_submit = expect.get("submit_status")
    if expected_submit is not None:
        if submit_status != expected_submit:
            outcome.note("submit_status", expected_submit, submit_status)
        # A bare status can be right for the wrong reason: 422 from the
        # exclusion gate versus 422 from anything else. When a scenario names
        # the FLARE code, the refusal has to carry exactly that one.
        if "error_code" in expect:
            detail = created.get("detail") if isinstance(created, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else None
            if code != expect["error_code"]:
                outcome.note("error_code", expect["error_code"], code)
        outcome.observed_status = f"HTTP {submit_status}"
        return outcome

    if submit_status >= 400 or "job_id" not in created:
        outcome.note("submit_status", "< 400 with a job_id", submit_status)
        outcome.observed_status = f"HTTP {submit_status}"
        return outcome

    job_id = created["job_id"]
    status, max_sequence, max_reports = _poll(base_url, token, job_id, PRE_APPROVAL_STOP, budget)

    if expect.get("approve"):
        if str(status.get("status")) != "awaiting_approval":
            outcome.note("status before approval", "awaiting_approval", status.get("status"))
            outcome.observed_status = str(status.get("status", "?"))
            return outcome
        approve_status, _ = _request(
            f"{base_url}/jobs/{job_id}/approve", token,
            method="POST", payload={"revision": status.get("revision")},
        )
        if approve_status >= 400:
            outcome.note("approve http status", "< 400", approve_status)
            outcome.observed_status = str(status.get("status", "?"))
            return outcome
        status, approved_sequence, approved_reports = _poll(
            base_url, token, job_id, TERMINAL, budget
        )
        max_sequence = max(max_sequence, approved_sequence)
        max_reports = max(max_reports, approved_reports)

    outcome.observed_status = str(status.get("status", "?"))
    _check(outcome, expect, status, max_sequence, max_reports)
    return outcome


def _assert_track_is_broken(base_url: str, token: str) -> str:
    """
    Guard against a green run that proves nothing: the track is only
    meaningful against the broken worker image.
    """
    _, health = _request(f"{base_url}/health", token)
    image = str(health.get("worker_image", ""))
    if image != "finja-agent-worker-broken:dev" or health.get("testbed_mode") is not True:
        raise RuntimeConfigurationError(
            "The endpoint is not the isolated Flare testbed stack"
        )
    # /health only reports the container path, so it cannot prove the job
    # directory is separate. Pre-existing quests are the one hint available
    # that this stack may be looking at somebody else's job tree.
    quests = health.get("active_quests")
    if isinstance(quests, int) and quests > 0:
        _emit(f"WARN  {quests} job(s) are already active here. A fresh test track "
              "starts empty -- check that FLARE_TESTBED_JOBS_DIR is not a "
              "production jobs folder.")
    return image


def _require_loopback_url(base_url: str) -> None:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} \
            or parsed.username or parsed.password or parsed.path not in {"", "/"} \
            or parsed.query or parsed.fragment:
        raise RuntimeConfigurationError("The test track must use a local loopback URL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Flare's Phase A test track.")
    parser.add_argument("--base-url", default="http://localhost:8078",
                        help="Orchestrator base URL of the test-track stack.")
    parser.add_argument("--token", default="", help="Bearer token, if the stack requires auth.")
    parser.add_argument("--scenario", action="append", default=[],
                        help="Run only this scenario; repeatable.")
    parser.add_argument("--budget", type=float, default=90.0,
                        help="Seconds to wait per lifecycle half.")
    parser.add_argument("--list", action="store_true", help="List the catalog and exit.")
    args = parser.parse_args(argv)

    base_url = args.base_url.rstrip("/")
    scenarios = load_scenarios()

    if args.list:
        for scenario in scenarios:
            marker = f"[needs {scenario['requires']}]" if scenario.get("requires") else ""
            _emit(f"  {scenario['name']:<45}{marker}")
            _emit(f"    {scenario['why']}")
        return EXIT_OK

    _require_loopback_url(base_url)

    if args.scenario:
        wanted = set(args.scenario)
        unknown = wanted - {scenario["name"] for scenario in scenarios}
        if unknown:
            raise RuntimeConfigurationError(f"Unknown scenario(s): {', '.join(sorted(unknown))}")
        scenarios = [scenario for scenario in scenarios if scenario["name"] in wanted]

    image = _assert_track_is_broken(base_url, args.token)
    _emit(f"Test track worker image: {image}")
    _emit()

    outcomes = [run_scenario(scenario, base_url, args.token, args.budget) for scenario in scenarios]

    failed = 0
    for outcome in outcomes:
        if outcome.skipped_because:
            _emit(f"SKIP  {outcome.name:<45}{outcome.skipped_because}")
            continue
        if outcome.passed:
            _emit(f"PASS  {outcome.name:<45}{outcome.observed_status}")
            continue
        failed += 1
        _emit(f"FAIL  {outcome.name:<45}{outcome.observed_status}")
        for mismatch in outcome.mismatches:
            _emit(f"        {mismatch}")

    checked = sum(1 for outcome in outcomes if not outcome.skipped_because)
    skipped = len(outcomes) - checked
    _emit()
    _emit(f"{checked - failed}/{checked} scenarios met their expectation ({skipped} skipped).")
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeConfigurationError as error:
        sys.stderr.write(f"{error.code}: {error}\n")
        raise SystemExit(EXIT_UNUSABLE) from error
