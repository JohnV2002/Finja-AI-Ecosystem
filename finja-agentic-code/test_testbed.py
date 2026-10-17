#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Test Track Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Unit tests for the Phase A test track (worker-broken/ and
               testbed/). Two halves:

               1. The fault-plan parser of the broken demo worker, so a
                  typo in a scenario cannot quietly become "ok".
               2. The orchestrator's reaction to each known-bad worker
                  shape, by faking the Docker boundary instead of
                  spawning a container.

  Needs NEITHER Docker NOR OpenRouter, so unlike testbed/run_testbed.py
  this suite runs in CI. The live integration pass over the same catalog
  is testbed/run_testbed.py against docker-compose.testbed.yml.

  New in v1.11.0:
    • First version, alongside the broken demo worker itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# worker.py and worker_broken.py read these at import time.
os.environ.setdefault("JOB_ID", "testjob")
os.environ.setdefault("JOBS_DIR", "/tmp/finja-agentic-test-jobs")

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT / "worker"))
sys.path.insert(0, str(_MODULE_ROOT / "worker-broken"))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
import worker  # noqa: E402
import worker_broken  # noqa: E402
from testbed import run_testbed  # noqa: E402

SCENARIO_FILE = _MODULE_ROOT / "testbed" / "scenarios.json"


def _load_compose(path: Path) -> dict:
    """
    safe_load, but tolerant of Compose's merge tags.

    The override has to carry `ports: !override`, and PyYAML's SafeLoader
    refuses unknown tags outright -- so without this the compose tests here
    would break on the very thing they exist to pin. The tag only steers
    Compose's merge, so dropping it and keeping the value is exactly right
    for reading the file.
    """
    yaml = pytest.importorskip("yaml")

    class _ComposeLoader(yaml.SafeLoader):
        pass

    def _keep_value(loader, _suffix, node):  # noqa: ANN001 - PyYAML signature
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node, deep=True)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node, deep=True)
        return loader.construct_scalar(node)

    _ComposeLoader.add_multi_constructor("!", _keep_value)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)


def _documented_compose_commands(path: Path) -> list[str]:
    """Every documented `docker compose ... docker-compose.testbed.yml` call."""
    # Fold shell line continuations so a wrapped command reads as one.
    folded = path.read_text(encoding="utf-8").replace("\\\n", " ")
    return [
        line.strip()
        for line in folded.splitlines()
        if "docker compose" in line and "docker-compose.testbed.yml" in line
    ]


# ==============================================================================
# Fault plan parsing -- a typo must never silently mean "ok"
# ==============================================================================

class TestParsePlan:
    """The plan is the whole contract of the broken worker; it must be strict."""

    def test_empty_plan_behaves_like_the_real_worker(self) -> None:
        assert worker_broken.parse_plan("") == {"default": "ok", "phases": {}}

    def test_bare_mode_applies_to_every_phase(self) -> None:
        plan = worker_broken.parse_plan("hang")
        assert plan == {"default": "hang", "phases": {}}
        assert worker_broken.resolve_mode(plan, "verify") == "hang"

    def test_shorthand_targets_single_phases(self) -> None:
        plan = worker_broken.parse_plan("verify=hang,default=ok")
        assert worker_broken.resolve_mode(plan, "verify") == "hang"
        assert worker_broken.resolve_mode(plan, "preflight") == "ok"

    def test_json_object_form(self) -> None:
        plan = worker_broken.parse_plan('{"default": "ok", "phases": {"verify": "crash:3"}}')
        assert worker_broken.resolve_mode(plan, "verify") == "crash:3"
        assert worker_broken.resolve_mode(plan, "preflight") == "ok"

    def test_json_string_form(self) -> None:
        assert worker_broken.parse_plan('"hang"')["default"] == "hang"

    def test_mode_argument_is_split_off(self) -> None:
        assert worker_broken.split_mode("slow:8") == ("slow", "8")
        assert worker_broken.split_mode("hang") == ("hang", "")

    @pytest.mark.parametrize("raw", [
        "{not json",            # truncated object
        "[1, 2]",               # wrong JSON shape via the string branch
        "verify=",              # empty mode
        "verify=hang,broken",   # entry without '='
    ])
    def test_unusable_plans_exit_non_zero(self, raw: str) -> None:
        with pytest.raises(SystemExit) as excinfo:
            worker_broken.parse_plan(raw)
        assert excinfo.value.code == worker_broken.PLAN_EXIT_CODE

    def test_unknown_mode_is_rejected_not_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker_broken, "FAULT_PLAN_ENV", "typoo")
        monkeypatch.setattr(worker_broken, "WORKSPACE", Path("/nonexistent-workspace"))
        with pytest.raises(SystemExit) as excinfo:
            worker_broken.main()
        assert excinfo.value.code == worker_broken.PLAN_EXIT_CODE


class TestPlanResolution:
    """The plan travelling inside the payload must win over the stack default."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = tmp_path / "job"
        workspace = root / "workspace"
        workspace.mkdir(parents=True)
        monkeypatch.setattr(worker_broken, "ROOT", root)
        monkeypatch.setattr(worker_broken, "WORKSPACE", workspace)
        monkeypatch.setattr(worker_broken, "FAULT_PLAN_ENV", "")
        # worker_broken reassigns these when it delegates; monkeypatch still
        # restores the values recorded here, so test_worker.py stays unaffected.
        monkeypatch.setattr(worker, "ROOT", root)
        monkeypatch.setattr(worker, "WORKSPACE", workspace)

    def test_env_plan_is_used_without_a_payload_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker_broken, "FAULT_PLAN_ENV", "crash:4")
        assert worker_broken.resolve_plan()["default"] == "crash:4"

    def test_payload_file_overrides_the_env_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker_broken, "FAULT_PLAN_ENV", "hang")
        (worker_broken.WORKSPACE / worker_broken.FAULT_FILE_NAME).write_text(
            json.dumps({"default": "ok", "phases": {"verify": "crash:7"}}), encoding="utf-8"
        )
        plan = worker_broken.resolve_plan()
        assert worker_broken.resolve_mode(plan, "preflight") == "ok"
        assert worker_broken.resolve_mode(plan, "verify") == "crash:7"


class TestInjectedResultShapes:
    """Each injected result must be well-formed enough to reach the guard it targets."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = tmp_path / "job"
        workspace = root / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "demo.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(worker_broken, "ROOT", root)
        monkeypatch.setattr(worker_broken, "WORKSPACE", workspace)
        monkeypatch.setattr(worker_broken, "JOB_PHASE", "preflight")
        monkeypatch.setattr(worker, "ROOT", root)
        monkeypatch.setattr(worker, "WORKSPACE", workspace)
        self.root = root

    def _written(self) -> dict:
        return json.loads((self.root / "preflight_result.json").read_text(encoding="utf-8"))

    def test_patch_fail_reports_a_refused_patch(self) -> None:
        worker_broken._run_patch_fail()
        result = self._written()
        assert result["patch_result"]["returncode"] == 1
        assert result["patch_applied"] is False
        assert result["fault_injected"] is True

    def test_syntax_fail_reports_a_postflight_finding(self) -> None:
        worker_broken._run_syntax_fail()
        findings = self._written()["postflight_python_syntax"]
        assert len(findings) == 1
        assert findings[0]["path"] == "demo.py"

    def test_wrong_job_claims_another_job(self) -> None:
        worker_broken._run_wrong_job()
        assert self._written()["job_id"] == worker_broken.PLACEHOLDER_JOB_ID

    def test_wrong_phase_claims_another_phase(self) -> None:
        worker_broken._run_wrong_phase()
        assert self._written()["phase"] == "verify"

    def test_invalid_result_is_not_parsable(self) -> None:
        worker_broken._run_invalid_result()
        with pytest.raises(ValueError):
            self._written()

    def test_crash_exits_with_the_requested_code(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            worker_broken._run_crash("7")
        assert excinfo.value.code == 7

    def test_crash_zero_is_refused_as_meaningless(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            worker_broken._run_crash("0")
        assert excinfo.value.code == worker_broken.PLAN_EXIT_CODE


# ==============================================================================
# The guards themselves -- Docker faked, real run_worker_phase
# ==============================================================================

class _FakeWorkerProcess:
    """Stands in for the Popen of a `docker run` that misbehaved."""

    def __init__(self, returncode: int, *, never_finishes: bool = False) -> None:
        self.returncode = returncode
        self._never_finishes = never_finishes
        self._running = True

    def poll(self) -> int | None:
        return None if self._running else self.returncode

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self._never_finishes:
            raise subprocess.TimeoutExpired(cmd="docker run", timeout=timeout or 0.0)
        self._running = False
        return "", "flare-fault: injected\n"

    def terminate(self) -> None:
        self._running = False

    def kill(self) -> None:
        self._running = False

    def wait(self, timeout: float | None = None) -> int:
        self._running = False
        return self.returncode


class TestOrchestratorGuardsAgainstBrokenWorker:
    """
    Drives run_worker_phase with each broken shape the demo container can
    produce, and pins the structured code the orchestrator must answer with.
    """

    @pytest.fixture(autouse=True)
    def _isolated_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "HOST_JOBS_DIR", "/host/jobs")
        monkeypatch.setattr(main, "_force_remove_worker_container", lambda name: None)
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.clear()

    def _job(self) -> str:
        return main.stage_job(main.CreateJobRequest(
            task="Flare test track",
            repository="flare-testbed",
            files=[main.JobFile(path="demo.py", content="def add(a, b):\n    return a - b\n")],
        ))

    def _install_worker(self, monkeypatch: pytest.MonkeyPatch, returncode: int,
                        *, writes: object = None, never_finishes: bool = False,
                        job_id: str = "", phase: str = "preflight") -> None:
        """Fake `docker run` and, optionally, the result file it leaves behind."""
        real_popen = subprocess.Popen

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN003
            if cmd[0] != "docker":
                return real_popen(cmd, **kwargs)
            if writes is not None:
                target = main.job_dir(job_id) / "sandbox" / f"{phase}_result.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(writes, str):
                    target.write_text(writes, encoding="utf-8")
                else:
                    target.write_text(json.dumps(writes), encoding="utf-8")
            return _FakeWorkerProcess(returncode, never_finishes=never_finishes)

        monkeypatch.setattr(main.subprocess, "Popen", fake_popen)

    def _good_result(self, job_id: str, phase: str = "preflight") -> dict:
        return {
            "job_id": job_id,
            "phase": phase,
            "preflight_python_syntax": [],
            "patch_applied": False,
            "patch_result": None,
            "postflight_python_syntax": [],
            "files": [{"path": "demo.py", "content": "def add(a, b):\n    return a - b\n"}],
        }

    def test_ok_shape_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = self._job()
        self._install_worker(monkeypatch, 0, writes=self._good_result(job_id), job_id=job_id)

        result = main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)

        assert result["job_id"] == job_id
        assert result["phase"] == "preflight"

    def test_crash_becomes_flare_501(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = self._job()
        self._install_worker(monkeypatch, 9, job_id=job_id)

        with pytest.raises(main.WorkerExecutionError) as excinfo:
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)

        assert excinfo.value.code == "FLARE-501"
        assert "exited with 9" in str(excinfo.value)

    def test_exit_zero_without_a_result_is_still_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = self._job()
        self._install_worker(monkeypatch, 0, job_id=job_id)

        with pytest.raises(main.WorkerExecutionError) as excinfo:
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)

        assert excinfo.value.code == "FLARE-501"
        assert "did not write" in str(excinfo.value)

    def test_unparsable_result_becomes_flare_501(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = self._job()
        self._install_worker(
            monkeypatch, 0, writes="{ this is deliberately not json", job_id=job_id
        )

        with pytest.raises(main.WorkerExecutionError) as excinfo:
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)

        assert excinfo.value.code == "FLARE-501"

    def test_hanging_phase_becomes_flare_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = self._job()
        self._install_worker(monkeypatch, 0, never_finishes=True, job_id=job_id)
        monkeypatch.setattr(main, "JOB_TIMEOUT_SECONDS", 1)

        with pytest.raises(main.WorkerExecutionTimedOutError) as excinfo:
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 1)

        assert excinfo.value.code == "FLARE-500"

    def test_refused_patch_blocks_the_candidate(self) -> None:
        job_id = self._job()
        result = self._good_result(job_id)
        result["patch_result"] = {"returncode": 1, "stdout": "", "stderr": "refused"}

        with pytest.raises(main.WorkerExecutionError) as excinfo:
            main._assert_phase_success(result, require_patch=True)

        assert excinfo.value.code == "FLARE-501"

    def test_injected_syntax_finding_blocks_the_candidate(self) -> None:
        job_id = self._job()
        result = self._good_result(job_id)
        result["postflight_python_syntax"] = [
            {"path": "demo.py", "line": 1, "offset": 1, "message": "injected"}
        ]

        with pytest.raises(main.WorkerExecutionError) as excinfo:
            main._assert_phase_success(result, require_patch=False)

        assert excinfo.value.code == "FLARE-501"

    def test_checkpoint_from_another_job_is_refused(self) -> None:
        job_id = self._job()
        poisoned = self._good_result(job_id)
        poisoned["job_id"] = worker_broken.PLACEHOLDER_JOB_ID
        main.write_json(main.job_dir(job_id) / "preflight_result.json", poisoned)

        with pytest.raises(main.JobPersistenceError) as excinfo:
            main.load_phase_result(job_id, "preflight")

        assert excinfo.value.code == "FLARE-801"

    def test_checkpoint_from_another_phase_is_refused(self) -> None:
        job_id = self._job()
        poisoned = self._good_result(job_id)
        poisoned["phase"] = "verify"
        main.write_json(main.job_dir(job_id) / "preflight_result.json", poisoned)

        with pytest.raises(main.JobPersistenceError) as excinfo:
            main.load_phase_result(job_id, "preflight")

        assert excinfo.value.code == "FLARE-801"


class TestL3ApprovalFlow:
    def test_changed_candidate_is_rejected(self) -> None:
        baseline = {"source_sha256": "first", "tests_run": 1, "status": "passed"}
        altered = {"source_sha256": "second", "tests_run": 1, "status": "passed"}
        with pytest.raises(main.WorkerExecutionError):
            main._assert_reproducible_result(baseline, altered)

    def test_tested_candidate_is_replayed_and_verified_after_approval(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "HOST_JOBS_DIR", "/host/jobs")
        monkeypatch.setattr(main, "WORKER_NETWORK", "none")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "test-only")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "_force_remove_worker_container", lambda name: None)
        monkeypatch.setattr(main, "call_openrouter", lambda *args: (
            "--- demo.py\n+++ demo.py\n@@ -1,2 +1,2 @@\n"
            " def add(a, b):\n-    return a - b\n+    return a + b\n"
        ))
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: True)

        def fake_patch() -> dict:
            target = worker.WORKSPACE / "demo.py"
            target.write_text(target.read_text(encoding="utf-8").replace("a - b", "a + b"), encoding="utf-8", newline="\n")
            return {"returncode": 0, "stdout": "", "stderr": ""}

        monkeypatch.setattr(worker, "apply_model_patch", fake_patch)

        real_popen = subprocess.Popen

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN003
            if cmd[0] != "docker":
                return real_popen(cmd, **kwargs)
            phase = next(item.split("=", 1)[1] for item in cmd if item.startswith("JOB_PHASE="))
            job_id = next(item.split("=", 1)[1] for item in cmd if item.startswith("JOB_ID="))
            sandbox = main.job_dir(job_id) / "sandbox"
            assert f"/sandbox:/jobs/{job_id}" in cmd[cmd.index("-v") + 1]
            assert "--read-only" in cmd and "--cap-drop" in cmd
            assert not (sandbox / "status.json").exists()
            assert not (sandbox / "request.json").exists()
            monkeypatch.setattr(worker, "ROOT", sandbox)
            monkeypatch.setattr(worker, "WORKSPACE", sandbox / "workspace")
            monkeypatch.setattr(worker, "JOB_ID", job_id)
            monkeypatch.setattr(worker, "JOB_PHASE", phase)
            worker.main()
            return _FakeWorkerProcess(0)

        monkeypatch.setattr(main.subprocess, "Popen", fake_popen)
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix add without changing the test",
            files=[
                main.JobFile(path="demo.py", content="def add(a, b):\n    return a - b\n"),
                main.JobFile(path="test_demo.py", content=(
                    "import unittest\nfrom demo import add\n"
                    "class DemoTest(unittest.TestCase):\n"
                    "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
                )),
            ],
        ))

        main.run_preapproval(job_id)
        awaiting = main.read_status(job_id)
        assert awaiting["status"] == "awaiting_approval", awaiting.get("error")
        assert awaiting["result"]["test_evidence"]["status"] == "passed"
        assert awaiting["result"]["test_evidence"]["tests_run"] == 1
        assert main.read_bytes(main.job_dir(job_id) / "test_patch_tests.log")
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        main.run_approved(job_id)

        completed = main.read_status(job_id)
        assert completed["status"] == "completed", completed.get("error")
        assert completed["result"]["test_evidence"]["source_sha256"] == awaiting["result"]["test_evidence"]["source_sha256"]
        assert completed["result"]["files"][0]["content"] == "def add(a, b):\n    return a + b\n"
        assert not (main.job_dir(job_id) / "sandbox").exists()

    @pytest.mark.parametrize("status,error_type", [
        ("failed", main.WorkerExecutionError),
        ("timed_out", main.WorkerExecutionTimedOutError),
    ])
    def test_failing_or_timed_out_tests_block_approval(self, status: str, error_type: type) -> None:
        with pytest.raises(error_type):
            main._assert_phase_success({
                "phase": "test_patch",
                "postflight_python_syntax": [],
                "test_evidence": {"status": status},
            }, require_patch=False)


# ==============================================================================
# The catalog itself -- a scenario nobody can run is worse than no scenario
# ==============================================================================

class TestScenarioCatalog:
    """Keeps testbed/scenarios.json honest against the worker it drives."""

    @staticmethod
    def _scenarios() -> list[dict]:
        return json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))["scenarios"]

    def test_catalog_is_loadable(self) -> None:
        assert len(self._scenarios()) >= 10

    def test_scenario_names_are_unique(self) -> None:
        names = [scenario["name"] for scenario in self._scenarios()]
        assert len(names) == len(set(names))

    def test_every_scenario_explains_itself(self) -> None:
        for scenario in self._scenarios():
            assert scenario.get("why"), f"{scenario['name']} has no 'why'"
            assert scenario.get("expect"), f"{scenario['name']} has no expectation"

    def test_every_plan_uses_a_mode_the_worker_knows(self) -> None:
        for scenario in self._scenarios():
            plan = scenario.get("plan")
            if plan is None:
                continue
            normalised = plan if isinstance(plan, dict) else {"default": plan, "phases": {}}
            specs = [normalised.get("default", "ok"), *normalised.get("phases", {}).values()]
            for spec in specs:
                mode, _ = worker_broken.split_mode(str(spec))
                assert mode in worker_broken.KNOWN_MODES, (
                    f"{scenario['name']} uses unknown mode {spec!r}"
                )

    def test_payloads_without_a_model_patch_parse_as_python(self) -> None:
        """
        In dry-run mode the submitted candidate itself goes through postflight
        verification, so only the scenario that targets the syntax guard may
        ship unparsable Python.
        """
        import ast

        for scenario in self._scenarios():
            if scenario["name"] == "preflight_rejects_broken_syntax":
                continue
            for entry in scenario["files"]:
                if not entry["path"].endswith(".py"):
                    continue
                ast.parse(entry["content"], filename=entry["path"])

    def test_submit_rejections_match_what_the_api_really_answers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        create_job takes the body as a plain dict -- the encrypted envelope
        needs that -- and validates it itself, so a refused payload comes back
        as a structured AppError (FLARE-605 -> 400) and FastAPI's automatic
        422 can never happen on this endpoint. A catalog expecting 422 would
        fail on a healthy stack, so the numbers are driven through the app
        here instead of being trusted.
        """
        testclient = pytest.importorskip("fastapi.testclient")
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        client = testclient.TestClient(main.app)

        for scenario in self._scenarios():
            submit_status = scenario["expect"].get("submit_status")
            if submit_status is None:
                continue
            response = client.post("/jobs", json={
                "task": scenario["task"],
                "repository": scenario.get("repository", "flare-testbed"),
                "files": [dict(entry) for entry in scenario["files"]],
            })
            assert response.status_code == submit_status, (
                f"{scenario['name']} expects HTTP {submit_status}, but the "
                f"orchestrator answers {response.status_code}"
            )

    def test_scenarios_expecting_approval_do_not_also_expect_failure_first(self) -> None:
        for scenario in self._scenarios():
            expect = scenario["expect"]
            if expect.get("approve") and expect.get("terminal_status") == "failed":
                pytest.fail(
                    f"{scenario['name']} cannot be approved and still end as 'failed': "
                    "a pre-approval failure never reaches awaiting_approval"
                )


# ==============================================================================
# Stack isolation -- the track must never be able to touch production jobs
# ==============================================================================

class TestTestbedStackIsolation:
    """
    recover_incomplete_jobs() resumes every recoverable job it can see on
    start. If the test-track stack ever shared a job directory with a real
    one, it would pick up production jobs and run them through the
    fault-injection worker. These tests keep that door shut.
    """

    OVERRIDE = _MODULE_ROOT / "docker-compose.testbed.yml"
    BASE = _MODULE_ROOT / "docker-compose.yml"
    TESTBED_VAR = "FLARE_TESTBED_JOBS_DIR"
    PRODUCTION_VAR = "AGENT_JOBS_HOST_DIR"

    def test_override_never_inherits_the_production_jobs_dir(self) -> None:
        """Dependency-free guard: the override must not fall back to .env."""
        text = self.OVERRIDE.read_text(encoding="utf-8")
        assert f"${{{self.PRODUCTION_VAR}}}" not in text, (
            "the test track must not reuse the production jobs directory"
        )
        assert f"{self.TESTBED_VAR}:?" in text, (
            f"{self.TESTBED_VAR} must be mandatory, so the stack refuses to "
            "start rather than silently sharing a job tree"
        )

    def test_base_stack_still_uses_its_own_variable(self) -> None:
        assert f"${{{self.PRODUCTION_VAR}}}" in self.BASE.read_text(encoding="utf-8")

    def test_base_api_binds_loopback_by_default(self) -> None:
        ports = _load_compose(self.BASE)["services"]["orchestrator"]["ports"]
        assert ports == ["${FLARE_BIND_HOST:-127.0.0.1}:8077:8077"]

    def test_override_binds_jobs_and_worker_mount_to_the_testbed_dir(self) -> None:
        service = _load_compose(self.OVERRIDE)["services"]["orchestrator"]

        # The container mount the orchestrator itself reads.
        jobs_mounts = [entry for entry in service["volumes"] if entry.endswith(":/jobs")]
        assert len(jobs_mounts) == 1
        assert self.TESTBED_VAR in jobs_mounts[0]

        # The host path handed to each spawned worker container.
        assert self.TESTBED_VAR in service["environment"][self.PRODUCTION_VAR]

    def test_override_runs_the_broken_image_on_its_own_port_and_name(self) -> None:
        base = _load_compose(self.BASE)
        service = _load_compose(self.OVERRIDE)["services"]["orchestrator"]

        assert "broken" in service["environment"]["WORKER_IMAGE"]
        assert service["container_name"] != base["services"]["orchestrator"]["container_name"]
        assert service["ports"] != base["services"]["orchestrator"]["ports"]
        assert service["environment"]["WORKER_NETWORK"] == "none"
        assert str(service["environment"]["FLARE_TESTBED_MODE"]) == "1"

    def test_override_replaces_inherited_env_file(self) -> None:
        text = self.OVERRIDE.read_text(encoding="utf-8")
        service = _load_compose(self.OVERRIDE)["services"]["orchestrator"]
        assert "env_file: !override []" in text
        assert service["env_file"] == []

    @pytest.mark.parametrize("url", [
        "https://localhost:8078", "http://example.com:8078",
        "http://user:pass@localhost:8078", "http://localhost:8078/jobs",
    ])
    def test_runner_rejects_non_local_endpoints(self, url: str) -> None:
        with pytest.raises(run_testbed.RuntimeConfigurationError):
            run_testbed._require_loopback_url(url)

    def test_runner_requires_testbed_health_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(run_testbed, "_request", lambda *_: (200, {
            "worker_image": "finja-agent-worker-broken:dev",
            "testbed_mode": False,
        }))
        with pytest.raises(run_testbed.RuntimeConfigurationError):
            run_testbed._assert_track_is_broken("http://localhost:8078", "")

    def test_override_forces_a_deterministic_dry_run(self) -> None:
        environment = _load_compose(self.OVERRIDE)[
            "services"]["orchestrator"]["environment"]
        assert environment["OPENROUTER_API_KEY"] == ""
        assert str(environment["DEDUPE_WINDOW_SECONDS"]) == "0"
        assert int(environment["JOB_TIMEOUT_SECONDS"]) <= 60

    def test_override_neutralises_every_inherited_production_credential(self) -> None:
        """
        docker-compose.yml loads the production .env into this service too,
        so a credential it defines reaches the track unless the override
        blanks it by name. An inherited ORCHESTRATOR_AUTH_TOKEN turns every
        submission into a 401 while /health, being unauthenticated, still
        reports a healthy stack -- the catalog then fails for a reason that
        has nothing to do with the guards it is testing. An inherited
        CODE_AGENT_TRANSPORT_KEY would additionally put a production secret
        into a throwaway stack.
        """
        environment = _load_compose(self.OVERRIDE)["services"]["orchestrator"]["environment"]
        for name in ("ORCHESTRATOR_AUTH_TOKEN", "CODE_AGENT_TRANSPORT_KEY", "OPENROUTER_API_KEY"):
            assert name in environment, (
                f"{name} is defined in .env.example, so the track inherits it "
                "and must blank it explicitly"
            )
            assert environment[name] == "", f"{name} must be empty on the test track"

    def test_unauthenticated_track_is_not_exposed_to_the_network(self) -> None:
        """Auth is off here on purpose, so the port must stay on loopback."""
        ports = _load_compose(self.OVERRIDE)["services"]["orchestrator"]["ports"]
        for entry in map(str, ports):
            assert entry.startswith("127.0.0.1:") or entry.startswith("localhost:"), (
                f"the track runs without auth; {entry} must bind loopback only"
            )

    def test_every_credential_in_env_example_is_accounted_for(self) -> None:
        """
        Catches the next credential somebody adds to .env.example: if it
        looks like a secret and the override neither blanks it nor is
        updated, the track silently inherits production's value.
        """
        env_example = (_MODULE_ROOT / ".env.example").read_text(encoding="utf-8")
        declared = {
            line.split("=", 1)[0].strip()
            for line in env_example.splitlines()
            if "=" in line and not line.strip().startswith("#")
        }
        secretish = {
            name for name in declared
            if any(marker in name for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        }
        environment = _load_compose(self.OVERRIDE)["services"]["orchestrator"]["environment"]
        missing = {name for name in secretish if environment.get(name, None) != ""}
        assert not missing, (
            f"the test track inherits these production credentials without "
            f"blanking them: {sorted(missing)}"
        )

    def test_override_replaces_the_inherited_port_instead_of_appending(self) -> None:
        """
        Compose APPENDS sequences when merging -f files. Without a merge tag
        the testbed service inherits "8077:8077" from the base file on top of
        its own port, wants to bind both, and the start fails with "port is
        already allocated" -- exactly when a production stack is running,
        which is the one case the track exists for.
        """
        text = self.OVERRIDE.read_text(encoding="utf-8")
        assert "ports: !override" in text or "ports: !reset" in text, (
            "the override must replace the inherited ports sequence, not add "
            "to it, or the track cannot start beside a running stack"
        )

        ports = _load_compose(self.OVERRIDE)["services"]["orchestrator"]["ports"]
        base_ports = _load_compose(self.BASE)["services"]["orchestrator"]["ports"]
        assert not set(map(str, ports)) & set(map(str, base_ports)), (
            "the track must not try to bind a port the production stack holds"
        )

    def test_documented_commands_carry_their_own_project_name(self) -> None:
        """
        Without -p the track runs in the production project under the same
        service name, so Compose replaces the production container with the
        testbed one -- while the command still looks successful. Every place
        that documents the command has to say so.
        """
        documented = {
            path: _documented_compose_commands(_MODULE_ROOT / path)
            for path in ("README.md", "docker-compose.testbed.yml",
                         "testbed/run_testbed.py")
        }
        for path, commands in documented.items():
            assert commands, f"{path} documents no testbed compose command"
            for command in commands:
                assert "-p flare-testbed" in command, (
                    f"{path} documents a testbed compose command without its "
                    f"own project name: {command}"
                )
