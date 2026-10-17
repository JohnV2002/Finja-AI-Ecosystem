#!/usr/bin/env python3
"""
======================================================================
         Flare (Finja Agentic Code) – Orchestrator Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Unit tests for the orchestrator (orchestrator/app/main.py).
               Covers the pieces that need NEITHER Docker NOR OpenRouter:
               path-validation security, the AES-GCM transport envelope
               round-trip, bearer auth, prompt/context building, fence
               stripping, and the endpoints that don't spawn a worker
               thread (/health, and the validation/auth paths of /jobs).

  Note: the real end-to-end job flow (spawning offline Docker workers +
        calling OpenRouter) is exercised by the separate manual smoke
        test `test_agentic_job.py`, which needs a running orchestrator,
        a Docker daemon, and an OpenRouter key -- deliberately NOT run
        in CI. These unit tests mock/monkeypatch that boundary away.

  New in v1.11.0:
    • Covers repeated green hotfix runs, durable checkpoints, and the
      revision-bound approval gate.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# The orchestrator app is laid out as orchestrator/app/main.py and run as
# `uvicorn app.main:app` inside the container. For tests we import it by its
# bare module name with that directory on sys.path.
_APP_DIR = Path(__file__).parent / "orchestrator" / "app"
sys.path.insert(0, str(_APP_DIR))

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Each test gets a fresh JOBS_DIR under tmp, no auth, and no transport
    key by default. Individual tests opt back into auth/encryption.
    """
    monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
    monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
    monkeypatch.setattr(main, "RETRY_BASE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(main, "DEDUPE_WINDOW_SECONDS", 300.0)
    monkeypatch.setattr(main, "MAX_ACTIVE_JOBS", 5)
    with main.ACTIVE_JOBS_LOCK:
        main.ACTIVE_JOBS.clear()


# ==============================================================================
# validate_relative_path() -- Security-Critical Path Validation
# ==============================================================================

class TestValidateRelativePath:
    """
    This is the sandbox's first line of defense: only safe, relative,
    code/text paths may be staged. Every rejection path matters.
    """

    def test_accepts_simple_filename(self) -> None:
        assert main.validate_relative_path("demo.py").as_posix() == "demo.py"

    def test_accepts_nested_relative_path(self) -> None:
        assert main.validate_relative_path("src/app/demo.py").as_posix() == "src/app/demo.py"

    @pytest.mark.parametrize("bad", [
        "../etc/passwd",          # parent traversal
        "src/../../etc/passwd",   # traversal mid-path
    ])
    def test_rejects_parent_traversal(self, bad: str) -> None:
        with pytest.raises(HTTPException) as exc:
            main.validate_relative_path(bad)
        assert exc.value.status_code == 400

    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(HTTPException):
            main.validate_relative_path("/etc/passwd")

    def test_rejects_backslash(self) -> None:
        """Windows-style separators must not slip through the POSIX check."""
        with pytest.raises(HTTPException):
            main.validate_relative_path("src\\demo.py")

    def test_rejects_leading_dot(self) -> None:
        with pytest.raises(HTTPException):
            main.validate_relative_path(".env")

    def test_rejects_unsupported_characters(self) -> None:
        with pytest.raises(HTTPException):
            main.validate_relative_path("demo$(whoami).py")

    def test_rejects_non_code_extension(self) -> None:
        """Slice 1 only allows code/text files -- no binaries, no executables."""
        with pytest.raises(HTTPException) as exc:
            main.validate_relative_path("payload.exe")
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("good", ["a.py", "b.js", "c.ts", "d.json", "e.md", "f.yml", "g.txt"])
    def test_accepts_allowed_extensions(self, good: str) -> None:
        assert main.validate_relative_path(good).as_posix() == good


# ==============================================================================
# Transport Encryption Round-Trip (AES-GCM envelope)
# ==============================================================================

class TestTransportEncryption:
    """
    When CODE_AGENT_TRANSPORT_KEY is set, payloads are wrapped in an
    AES-GCM envelope. These verify the encrypt/decrypt and seal/open
    round-trips, plus the plaintext passthrough when no key is set.
    """

    def test_no_key_is_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        assert main.transport_enabled() is False
        data = b"hello world"
        assert main.encrypt_bytes(data) == data          # no-op
        assert main.decrypt_bytes(data) == data
        assert main.is_encrypted_bytes(data) is False

    def test_bytes_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "my-secret-transport-key")
        assert main.transport_enabled() is True

        plaintext = b"def add(a, b):\n    return a + b\n"
        sealed = main.encrypt_bytes(plaintext)

        assert sealed != plaintext
        assert main.is_encrypted_bytes(sealed) is True
        assert main.decrypt_bytes(sealed) == plaintext

    def test_json_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "another-key")
        payload = {"job_id": "abc123", "status": "done", "nested": {"n": 1}}

        sealed = main.seal_json(payload)
        assert sealed["encrypted"] is True
        assert sealed["alg"] == "AES-256-GCM"

        assert main.open_json(sealed) == payload

    def test_open_json_passthrough_for_plain_dict(self) -> None:
        assert main.open_json({"task": "x", "files": []}) == {"task": "x", "files": []}

    def test_decrypt_with_wrong_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "key-one")
        sealed = main.encrypt_bytes(b"secret")

        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "key-two")
        with pytest.raises(HTTPException) as exc:
            main.decrypt_bytes(sealed)
        assert exc.value.status_code == 400

    def test_raw_key_accepts_base64_of_valid_length(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A 32-byte urlsafe-b64 key is used directly; anything else is SHA-256'd."""
        import base64
        key32 = base64.urlsafe_b64encode(b"0" * 32).decode("ascii").rstrip("=")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", key32)
        assert main._transport_key_bytes() == b"0" * 32


# ==============================================================================
# Encrypted-at-Rest File Helpers
# ==============================================================================

class TestFileHelpers:
    def test_text_round_trip_plaintext(self, tmp_path: Path) -> None:
        p = tmp_path / "task.txt"
        main.write_text(p, "fix the bug")
        assert main.read_text(p) == "fix the bug"

    def test_json_round_trip_encrypted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "file-key")
        p = tmp_path / "status.json"
        main.write_json(p, {"status": "done"})

        # On disk it must NOT be readable plaintext JSON
        assert main.is_encrypted_bytes(p.read_bytes()) is True
        # But the helper round-trips it back
        assert main.read_json(p) == {"status": "done"}


# ==============================================================================
# strip_fences()
# ==============================================================================

class TestStripFences:
    def test_removes_triple_backtick_fences(self) -> None:
        text = "```diff\n--- a\n+++ b\n```"
        cleaned = main.strip_fences(text)
        assert not cleaned.startswith("```")
        assert not cleaned.rstrip().endswith("```")
        assert "--- a" in cleaned

    def test_adds_trailing_newline(self) -> None:
        assert main.strip_fences("no newline").endswith("\n")

    def test_leaves_plain_diff_alone(self) -> None:
        diff = "--- a\n+++ b\n"
        assert main.strip_fences(diff) == diff


# ==============================================================================
# require_auth()
# ==============================================================================

class TestRequireAuth:
    def test_disabled_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        # Should not raise regardless of header
        main.require_auth(authorization="")
        main.require_auth(authorization="Bearer whatever")

    def test_rejects_wrong_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "correct")
        with pytest.raises(HTTPException) as exc:
            main.require_auth(authorization="Bearer wrong")
        assert exc.value.status_code == 401

    def test_accepts_correct_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "correct")
        main.require_auth(authorization="Bearer correct")  # must not raise


# ==============================================================================
# stage_job() + collect_context()
# ==============================================================================

class TestStageJob:
    def _request(self) -> "main.CreateJobRequest":
        return main.CreateJobRequest(
            task="Fix the bug",
            files=[main.JobFile(path="demo.py", content="def add(a, b):\n    return a +\n")],
        )

    def test_stage_job_creates_workspace_and_status(self) -> None:
        job_id = main.stage_job(self._request())

        root = main.job_dir(job_id)
        assert (root / "workspace" / "demo.py").exists()
        assert (root / "task.txt").exists()
        status = main.read_status(job_id)
        assert status["status"] == "queued"
        assert status["revision"] == 1
        assert status["state_schema_version"] == 3
        assert status["status_history"][0]["reason"] == "job_submitted"

    def test_stage_job_rejects_duplicate_paths(self) -> None:
        request = main.CreateJobRequest(
            task="x",
            files=[
                main.JobFile(path="demo.py", content="a"),
                main.JobFile(path="demo.py", content="b"),
            ],
        )
        with pytest.raises(HTTPException) as exc:
            main.stage_job(request)
        assert exc.value.status_code == 400

    def test_collect_context_includes_file_content(self) -> None:
        job_id = main.stage_job(self._request())
        context = main.collect_context(job_id)
        assert "FILE: demo.py" in context
        assert "def add(a, b)" in context

    def test_status_updates_preserve_creation_metadata(self) -> None:
        job_id = main.stage_job(self._request())
        created_at = main.read_status(job_id)["created_at"]

        main.write_status(job_id, "analysing", started_at=main.now_iso())

        status = main.read_status(job_id)
        assert status["created_at"] == created_at
        assert status["status"] == "analysing"
        assert status["revision"] == 2
        assert status["previous_status"] == "queued"
        assert status["status_message"] == "Flare is analysing the task"
        assert [entry["status"] for entry in status["status_history"]] == ["queued", "analysing"]


# Exact v2 state machine, approval gate, rollback, and recovery
# ==============================================================================


class TestJobStateMachine:
    def _request(self) -> "main.CreateJobRequest":
        return main.CreateJobRequest(task="state test", files=[main.JobFile(path="demo.py", content="x = 1\n")])

    def test_exact_public_status_vocabulary(self) -> None:
        assert main.JOB_STATUS_VALUES == {
            "queued", "analysing", "patching", "testing", "awaiting_approval",
            "applying", "verifying", "completed", "failed", "rolled_back",
        }

    def test_happy_path_transition_chain(self) -> None:
        chain = [
            "queued", "analysing", "patching", "testing", "awaiting_approval",
            "applying", "verifying", "completed",
        ]
        for current, target in zip(chain, chain[1:]):
            main._validate_transition(current, target)

    def test_every_unlisted_transition_is_rejected(self) -> None:
        for current in main.JOB_STATUS_VALUES:
            for target in main.JOB_STATUS_VALUES:
                allowed = current == target or target in main.NORMAL_JOB_TRANSITIONS[current]
                if allowed:
                    main._validate_transition(current, target)
                else:
                    with pytest.raises(main.InvalidJobStateTransitionError):
                        main._validate_transition(current, target)

    @pytest.mark.parametrize("terminal", ["completed", "failed", "rolled_back"])
    def test_terminal_states_are_immutable(self, terminal: str) -> None:
        for target in main.JOB_STATUS_VALUES - {terminal}:
            with pytest.raises(main.InvalidJobStateTransitionError):
                main._validate_transition(terminal, target)

    def test_legacy_statuses_migrate_to_current_schema(self) -> None:
        job_id = main.stage_job(self._request())
        legacy = {
            "job_id": job_id,
            "status": "done",
            "state_schema_version": 1,
            "created_at": main.now_iso(),
            "updated_at": main.now_iso(),
            "result": {"files": []},
        }
        main.write_json(main.status_path(job_id), legacy)

        migrated = main.read_status(job_id)

        assert migrated["status"] == "completed"
        assert migrated["state_schema_version"] == 3
        assert migrated["status_history"][0]["status"] == "completed"

    def test_legacy_cancellation_migrates_to_a_restored_rollback(self) -> None:
        job_id = main.stage_job(self._request())
        legacy = main.read_status(job_id)
        legacy["status"] = "cancelled"
        legacy["state_schema_version"] = 1
        (main.job_dir(job_id) / "workspace" / "demo.py").write_text("x = 99\n", encoding="utf-8")
        main.write_json(main.status_path(job_id), legacy)

        migrated = main.read_status(job_id)

        assert migrated["status"] == "rolled_back"
        assert migrated["result"]["files"] == [{"path": "demo.py", "content": "x = 1\n"}]
        assert (main.job_dir(job_id) / "workspace" / "demo.py").read_text(encoding="utf-8") == "x = 1\n"


class TestApprovalWorkflow:
    def _request(self) -> "main.CreateJobRequest":
        return main.CreateJobRequest(task="Fix it", files=[main.JobFile(path="demo.py", content="x = 1\n")])

    def _awaiting_job(self) -> tuple[str, dict]:
        job_id = main.stage_job(self._request())
        main.write_status(job_id, "analysing")
        main.write_status(job_id, "patching")
        main.write_status(job_id, "testing")
        status = main.write_status(job_id, "awaiting_approval", result={"files": []}, approval_required=True)
        return job_id, status

    def test_approval_is_required_before_applying(self) -> None:
        job_id = main.stage_job(self._request())
        with pytest.raises(main.InvalidJobStateTransitionError):
            main.write_status(job_id, "applying")

    def test_approve_checks_revision_and_starts_apply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, awaiting = self._awaiting_job()
        started: list[str] = []
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: started.append(candidate) or True)

        approved = main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))

        assert approved["status"] == "applying"
        assert approved["approved_revision"] == awaiting["revision"]
        assert started == [job_id]

    def test_stale_approval_is_rejected(self) -> None:
        job_id, awaiting = self._awaiting_job()
        with pytest.raises(main.InvalidJobStateTransitionError) as exc:
            main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"] - 1))
        assert exc.value.code == "FLARE-602"
        assert main.read_status(job_id)["status"] == "awaiting_approval"

    def test_reject_rolls_back_to_original_files(self) -> None:
        job_id, awaiting = self._awaiting_job()

        rejected = main.reject_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))

        assert rejected["status"] == "rolled_back"
        assert rejected["result"]["files"] == [{"path": "demo.py", "content": "x = 1\n"}]

    def test_cancel_does_not_add_a_public_cancel_state(self) -> None:
        job_id, _awaiting = self._awaiting_job()

        cancelled = main.request_job_cancel(job_id)

        assert cancelled["status"] == "rolled_back"
        assert cancelled["error_code"] == "FLARE-600"
        assert main.cancel_path(job_id).exists()

    def test_recovery_leaves_awaiting_approval_parked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, awaiting = self._awaiting_job()
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: pytest.fail("approval gate was bypassed"))

        assert main.recover_incomplete_jobs() == 0
        assert main.read_status(job_id)["revision"] == awaiting["revision"]

    def test_recovery_resumes_current_state_without_moving_backwards(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = main.stage_job(self._request())
        main.write_status(job_id, "analysing")
        started: list[str] = []
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: started.append(candidate) or True)

        assert main.recover_incomplete_jobs() == 1
        assert main.read_status(job_id)["status"] == "analysing"
        assert started == [job_id]

    def test_runner_stops_for_approval_then_completes_after_approval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = main.stage_job(self._request())
        phases: list[str] = []

        def fake_phase(candidate: str, phase: str, deadline: float) -> dict:
            phases.append(phase)
            result = {
                "job_id": candidate,
                "phase": phase,
                "patch_result": None,
                "files": [{"path": "demo.py", "content": "x = 1\n"}],
            }
            if phase in {"test_patch", "verify"}:
                result["test_evidence"] = {
                    "status": "not_run", "tests_run": 0, "source_sha256": "same-candidate",
                    "runner": "python-unittest", "python_version": "test-version",
                    "runner_sha256": "same-runner", "command": ["unittest"],
                }
            main.write_json(main.job_dir(candidate) / f"{phase}_result.json", result)
            return result

        monkeypatch.setattr(main, "run_worker_phase", fake_phase)
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: True)
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")

        main.run_preapproval(job_id)
        awaiting = main.read_status(job_id)
        assert awaiting["status"] == "awaiting_approval", awaiting.get("error")
        assert awaiting["locks_held"] is False
        assert phases == ["preflight", "test_patch"]
        assert main.held_resource_lock_count() == 0


        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        main.run_approved(job_id)

        completed = main.read_status(job_id)
        assert completed["status"] == "completed"
        assert completed["locks_held"] is False
        assert [entry["status"] for entry in completed["status_history"]] == [
            "queued", "analysing", "patching", "testing", "awaiting_approval",
            "applying", "verifying", "completed",
        ]
        assert phases == ["preflight", "test_patch", "verify"]
        assert main.held_resource_lock_count() == 0

    def test_failure_after_approval_rolls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, awaiting = self._awaiting_job()
        preflight = {
            "job_id": job_id,
            "phase": "preflight",
            "patch_result": None,
            "files": [{"path": "demo.py", "content": "x = 1\n"}],
        }
        main.write_json(main.job_dir(job_id) / "preflight_result.json", preflight)
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: True)
        monkeypatch.setattr(
            main,
            "run_worker_phase",
            lambda *args: (_ for _ in ()).throw(main.WorkerExecutionError("verification failed")),
        )
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))

        main.run_approved(job_id)

        rolled_back = main.read_status(job_id)
        assert rolled_back["status"] == "rolled_back"
        assert rolled_back["error_code"] == "FLARE-501"

    def test_preapproval_timeout_rolls_back_fail_soft_and_releases_locks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = main.stage_job(self._request())
        monkeypatch.setattr(
            main,
            "run_worker_phase",
            lambda *args: (_ for _ in ()).throw(main.WorkerExecutionTimedOutError("preflight too slow")),
        )

        main.run_preapproval(job_id)

        timed_out = main.read_status(job_id)
        assert timed_out["status"] == "rolled_back"
        assert timed_out["outcome"] == "timeout_soft"
        assert timed_out["error_code"] == "FLARE-500"
        assert timed_out["retryable"] is True
        assert timed_out["timed_out_from_status"] == "analysing"
        assert timed_out["locks_held"] is False
        assert timed_out["result"]["files"] == [{"path": "demo.py", "content": "x = 1\n"}]
        assert main.held_resource_lock_count() == 0

    def test_approved_timeout_rolls_back_fail_soft_and_releases_locks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id, awaiting = self._awaiting_job()
        preflight = {
            "job_id": job_id,
            "phase": "preflight",
            "patch_result": None,
            "files": [{"path": "demo.py", "content": "x = 1\n"}],
        }
        main.write_json(main.job_dir(job_id) / "preflight_result.json", preflight)
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: True)
        monkeypatch.setattr(
            main,
            "run_worker_phase",
            lambda *args: (_ for _ in ()).throw(main.WorkerExecutionTimedOutError("verify too slow")),
        )
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))

        main.run_approved(job_id)

        timed_out = main.read_status(job_id)
        assert timed_out["status"] == "rolled_back"
        assert timed_out["outcome"] == "timeout_soft"
        assert timed_out["timed_out_from_status"] == "verifying"
        assert timed_out["locks_held"] is False
        assert main.held_resource_lock_count() == 0

    def test_timeout_rollback_failure_becomes_explicit_hard_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = main.stage_job(self._request())
        main.write_status(job_id, "analysing")
        monkeypatch.setattr(
            main,
            "restore_workspace_from_request",
            lambda candidate: (_ for _ in ()).throw(main.JobPersistenceError("snapshot unavailable")),
        )

        failed = main._finish_timeout_soft(
            job_id,
            main.WorkerExecutionTimedOutError("analysis too slow"),
            "analysing",
        )

        assert failed["status"] == "failed"
        assert failed["outcome"] == "timeout_rollback_failed"
        assert failed["error_code"] == "FLARE-801"
        assert failed["original_error"]["code"] == "FLARE-500"
        assert failed["retryable"] is False


class TestHotfixApprovalGate:
    def test_mode_changes_identity_without_breaking_standard_dedupe(self) -> None:
        standard = main.CreateJobRequest(task="Repair", files=[main.JobFile(path="demo.py", content="x=1\n")])
        hotfix = standard.model_copy(update={"mode": "hotfix"})
        old_payload = standard.model_dump(mode="json", exclude={"mode"})
        old_canonical = json.dumps(old_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert main.request_fingerprint(standard) == hashlib.sha256(old_canonical.encode()).hexdigest()
        assert main.request_fingerprint(hotfix) != main.request_fingerprint(standard)

    def _hotfix(self, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, list[str]]:
        monkeypatch.setattr(main, "L4_REQUIRED_GREEN_RUNS", 3)
        request = main.CreateJobRequest(
            task="Repair", mode="hotfix",
            files=[main.JobFile(path="demo.py", content="x = 1\n"),
                   main.JobFile(path="test_demo.py", content="import unittest\n")],
        )
        job_id = main.stage_job(request)
        main.write_status(job_id, "analysing")
        main.write_status(job_id, "patching")
        main.write_status(job_id, "testing")
        diff = "--- demo.py\n+++ demo.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        main.write_text(main.job_dir(job_id) / "model.patch", diff)
        calls: list[str] = []

        def fake_phase(candidate: str, phase: str, deadline: float) -> dict:
            calls.append(phase)
            evidence = {
                "status": "passed", "tests_run": 1, "source_sha256": "same-candidate",
                "runner": "python-unittest", "python_version": "test-version",
                "runner_sha256": "same-runner", "command": ["unittest"],
                "workspace_mutated": False,
            }
            result = {"job_id": candidate, "phase": phase,
                      "patch_result": {"returncode": 0}, "test_evidence": evidence}
            main.write_json(main.job_dir(candidate) / f"{phase}_result.json", result)
            return result

        monkeypatch.setattr(main, "run_worker_phase", fake_phase)
        return job_id, diff, calls

    def test_three_green_runs_are_durable_and_approve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, diff, calls = self._hotfix(monkeypatch)
        tested, packet = main._run_hotfix_tests(job_id, diff, time.monotonic() + 30)
        assert tested["test_evidence"]["status"] == "passed"
        assert calls == ["test_patch"] * 3
        assert len(packet["runs"]) == 3
        assert main.read_json(main.job_dir(job_id) / "hotfix_evidence.json") == packet

        # A process restart reuses completed per-run checkpoints.
        main._run_hotfix_tests(job_id, diff, time.monotonic() + 30)
        assert calls == ["test_patch"] * 3

        awaiting = main.write_status(job_id, "awaiting_approval", hotfix_evidence=packet)
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: True)
        approved = main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        assert approved["status"] == "applying"

    def test_preapproval_reaches_gate_only_after_three_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, _diff, calls = self._hotfix(monkeypatch)
        main.write_json(main.job_dir(job_id) / "preflight_result.json",
                        {"job_id": job_id, "phase": "preflight", "files": []})
        monkeypatch.setattr(main, "review_repair_scope", lambda *args: {"allowed": True})
        monkeypatch.setattr(main.repair_scope, "enforce", lambda report: None)
        main.run_preapproval(job_id)
        awaiting = main.read_status(job_id)
        assert awaiting["status"] == "awaiting_approval", awaiting
        assert calls == ["test_patch", "test_patch", "test_patch"]
        assert len(awaiting["hotfix_evidence"]["runs"]) == 3
        assert awaiting["locks_held"] is False

    def test_missing_evidence_never_opens_approval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, _diff, _calls = self._hotfix(monkeypatch)
        awaiting = main.write_status(job_id, "awaiting_approval")
        with pytest.raises(main.HotfixApprovalGateError) as exc:
            main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        assert exc.value.code == "FLARE-608"
        assert main.read_status(job_id)["status"] == "awaiting_approval"

    def test_non_green_and_changed_patch_are_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, diff, _calls = self._hotfix(monkeypatch)
        _tested, packet = main._run_hotfix_tests(job_id, diff, time.monotonic() + 30)
        packet["runs"][1]["test_evidence"]["status"] = "failed"
        with pytest.raises(main.HotfixApprovalGateError):
            main._validate_hotfix_packet(job_id, diff, packet)
        packet["runs"][1]["test_evidence"]["status"] = "passed"
        with pytest.raises(main.HotfixApprovalGateError):
            main._validate_hotfix_packet(job_id, diff + "# changed", packet)

    def test_no_discovered_tests_cannot_count_as_green(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id, diff, _calls = self._hotfix(monkeypatch)

        def no_tests(candidate: str, phase: str, deadline: float) -> dict:
            result = {"job_id": candidate, "phase": phase,
                      "patch_result": {"returncode": 0},
                      "test_evidence": {"status": "not_run", "tests_run": 0,
                                        "source_sha256": "same-candidate", "runner": "python-unittest",
                                        "python_version": "test-version", "runner_sha256": "same-runner",
                                        "command": ["unittest"], "workspace_mutated": False}}
            main.write_json(main.job_dir(candidate) / f"{phase}_result.json", result)
            return result

        monkeypatch.setattr(main, "run_worker_phase", no_tests)
        with pytest.raises(main.HotfixApprovalGateError) as exc:
            main._run_hotfix_tests(job_id, diff, time.monotonic() + 30)
        assert exc.value.code == "FLARE-608"
        assert not (main.job_dir(job_id) / "hotfix_evidence.json").exists()


class TestRuntimeObservability:
    def _request(self) -> "main.CreateJobRequest":
        return main.CreateJobRequest(task="observe it", files=[main.JobFile(path="demo.py", content="x = 1\n")])

    def test_transitions_create_structured_progress_reports(self) -> None:
        job_id = main.stage_job(self._request())

        status = main.write_status(job_id, "analysing", transition_reason="analysis_started")

        assert status["progress_percent"] == 10
        assert status["latest_report"]["kind"] == "transition"
        assert status["latest_report"]["status"] == "analysing"
        assert [report["status"] for report in status["progress_reports"]] == ["queued", "analysing"]

    def test_heartbeat_is_durable_and_rate_limited(self) -> None:
        job_id = main.stage_job(self._request())

        first = main.emit_heartbeat(job_id, "Analysis is still running", force=True)
        suppressed = main.emit_heartbeat(job_id, "Analysis is still running")

        assert first["heartbeat_sequence"] == 1
        assert first["latest_report"]["kind"] == "heartbeat"
        assert first["latest_report"]["message"] == "Analysis is still running"
        assert suppressed["revision"] == first["revision"]

    def test_blocking_operation_emits_periodic_heartbeats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = main.stage_job(self._request())
        monkeypatch.setattr(main, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

        with main.JobHeartbeat(job_id, "Provider request is still running"):
            time.sleep(0.035)

        status = main.read_status(job_id)
        assert status["heartbeat_sequence"] >= 2
        assert status["latest_report"]["message"] == "Provider request is still running"

    def test_progress_report_history_is_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = main.stage_job(self._request())
        monkeypatch.setattr(main, "PROGRESS_REPORT_LIMIT", 3)

        for index in range(5):
            main.emit_heartbeat(job_id, f"heartbeat {index}", force=True)

        reports = main.read_status(job_id)["progress_reports"]
        assert len(reports) == 3
        assert [report["message"] for report in reports] == ["heartbeat 2", "heartbeat 3", "heartbeat 4"]

    def test_runtime_limit_raises_structured_timeout(self) -> None:
        with pytest.raises(main.WorkerExecutionTimedOutError) as exc:
            main._remaining_seconds(time.monotonic() - 1, 10, "phase deadline exceeded")
        assert exc.value.code == "FLARE-500"

    def test_model_runtime_deadline_is_visible_while_request_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = main.stage_job(self._request())
        main.write_status(job_id, "analysing")
        main.write_status(job_id, "patching")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "test-key")

        class Response:
            def __enter__(self):
                status = main.read_status(job_id)
                assert status["phase_started_at"]
                assert status["phase_deadline_at"]
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": ""}}]}).encode()

        monkeypatch.setattr(main.urllib.request, "urlopen", lambda request, timeout: Response())

        assert main.call_openrouter("prompt", job_id, time.monotonic() + 5) == ""
        assert main.read_status(job_id)["latest_report"]["kind"] == "heartbeat"

    def test_exhausted_model_timeout_remains_flare_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = main.stage_job(self._request())
        main.write_status(job_id, "analysing")
        main.write_status(job_id, "patching")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "test-key")
        monkeypatch.setattr(main, "OPENROUTER_MAX_ATTEMPTS", 1)
        monkeypatch.setattr(
            main.urllib.request,
            "urlopen",
            lambda request, timeout: (_ for _ in ()).throw(TimeoutError("model too slow")),
        )

        with pytest.raises(main.WorkerExecutionTimedOutError) as exc:
            main.call_openrouter("prompt", job_id, time.monotonic() + 5)

        assert exc.value.code == "FLARE-500"

    def test_stale_counter_excludes_approval_wait(self) -> None:
        job_id = main.stage_job(self._request())
        payload = main.read_status(job_id)
        payload["heartbeat_at"] = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        main.write_json(main.status_path(job_id), payload)
        assert main.stale_active_job_count() == 1

        for status in ["analysing", "patching", "testing", "awaiting_approval"]:
            main.write_status(job_id, status)
        payload = main.read_status(job_id)
        payload["heartbeat_at"] = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        main.write_json(main.status_path(job_id), payload)
        assert main.stale_active_job_count() == 0


class TestRepositoryAndFileLocks:
    def _stage(self, repository: str, path: str) -> str:
        return main.stage_job(
            main.CreateJobRequest(
                task="lock it",
                repository=repository,
                files=[main.JobFile(path=path, content="x = 1\n")],
            )
        )

    @pytest.mark.parametrize("repository", ["../repo", "repo/name", "repo name"])
    def test_repository_identifier_rejects_paths(self, repository: str) -> None:
        with pytest.raises(ValueError):
            main.CreateJobRequest(
                task="unsafe repo",
                repository=repository,
                files=[main.JobFile(path="a.py", content="x = 1\n")],
            )

    def test_repository_limit_blocks_different_files_in_same_repo(self) -> None:
        first_id = self._stage("finja-core", "a.py")
        second_id = self._stage("finja-core", "b.py")
        first = main.JobResourceLease(first_id, time.monotonic() + 2)
        second = main.JobResourceLease(second_id, time.monotonic() + 2)

        assert first._try_acquire_all() is True
        try:
            assert second._try_acquire_all() is False
            assert main.held_resource_lock_count() == 3
        finally:
            first.release()

        assert second._try_acquire_all() is True
        second.release()

    def test_file_lock_blocks_overlap_when_repo_has_multiple_slots(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "MAX_PARALLEL_JOBS_PER_REPOSITORY", 2)
        first_id = self._stage("finja-core", "shared.py")
        second_id = self._stage("finja-core", "shared.py")
        other_id = self._stage("finja-core", "other.py")
        first = main.JobResourceLease(first_id, time.monotonic() + 2)
        second = main.JobResourceLease(second_id, time.monotonic() + 2)
        other = main.JobResourceLease(other_id, time.monotonic() + 2)

        assert first._try_acquire_all() is True
        try:
            assert second._try_acquire_all() is False
            assert other._try_acquire_all() is True
            other.release()
        finally:
            first.release()

    def test_lock_scope_is_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "MAX_PARALLEL_JOBS_PER_REPOSITORY", 2)
        first = main.JobResourceLease(self._stage("Finja-Core", "Shared.py"), time.monotonic() + 2)
        second = main.JobResourceLease(self._stage("finja-core", "shared.py"), time.monotonic() + 2)

        assert first._try_acquire_all() is True
        try:
            assert second._try_acquire_all() is False
        finally:
            first.release()

    def test_different_repositories_do_not_block_each_other(self) -> None:
        first = main.JobResourceLease(self._stage("repo-a", "shared.py"), time.monotonic() + 2)
        second = main.JobResourceLease(self._stage("repo-b", "shared.py"), time.monotonic() + 2)

        assert first._try_acquire_all() is True
        try:
            assert second._try_acquire_all() is True
        finally:
            second.release()
            first.release()

    def test_global_limit_applies_across_repositories(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "MAX_PARALLEL_JOBS", 1)
        first = main.JobResourceLease(self._stage("repo-a", "a.py"), time.monotonic() + 2)
        second = main.JobResourceLease(self._stage("repo-b", "b.py"), time.monotonic() + 2)

        assert first._try_acquire_all() is True
        try:
            assert second._try_acquire_all() is False
        finally:
            first.release()

    def test_lock_wait_respects_total_runtime_deadline(self) -> None:
        first = main.JobResourceLease(self._stage("finja-core", "shared.py"), time.monotonic() + 2)
        blocked_id = self._stage("finja-core", "shared.py")
        blocked = main.JobResourceLease(blocked_id, time.monotonic() - 1)
        assert first._try_acquire_all() is True
        try:
            with pytest.raises(main.WorkerExecutionTimedOutError) as exc:
                blocked.acquire()
            assert exc.value.code == "FLARE-500"
            assert "repository or file locks" in str(exc.value)
        finally:
            first.release()

    def test_lock_paths_contain_hashes_not_repo_or_file_names(self) -> None:
        lease = main.JobResourceLease(self._stage("private-repo", "secret.py"), time.monotonic() + 2)
        paths = lease._repo_lock_paths() + lease._file_lock_paths()

        assert all("private-repo" not in str(path) and "secret.py" not in str(path) for path in paths)
        assert all(path.suffix == ".lock" for path in paths)

    def test_advisory_lock_blocks_a_second_process(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "cross-process.lock"
        child_code = """
import os
import sys
import time

handle = open(sys.argv[1], "a+b")
if handle.seek(0, os.SEEK_END) == 0:
    handle.write(b"\\0")
    handle.flush()
handle.seek(0)
if os.name == "nt":
    import msvcrt
    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
print("ready", flush=True)
time.sleep(10)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", child_code, str(lock_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert process.stdout is not None
            assert process.stdout.readline().strip() == "ready"
            assert main._try_os_resource_lock(lock_path) is None
        finally:
            process.terminate()
            process.wait(timeout=5)

        handle = main._try_os_resource_lock(lock_path)
        assert handle is not None
        main._release_os_resource_lock(handle)


# ==============================================================================
# FastAPI Endpoints (no worker thread spawned)
# ==============================================================================

@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


class TestHealthEndpoint:
    def test_health_shape(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "worker_image" in data
        assert "transport_encryption" in data
        assert data["job_total_timeout_seconds"] == main.JOB_TOTAL_TIMEOUT_SECONDS
        assert data["openrouter_max_attempts"] == main.OPENROUTER_MAX_ATTEMPTS
        assert data["finja_timeout_retry_after_seconds"] == main.FINJA_TIMEOUT_RETRY_AFTER_SECONDS
        assert data["dedupe_window_seconds"] == main.DEDUPE_WINDOW_SECONDS
        assert data["max_active_jobs"] == main.MAX_ACTIVE_JOBS
        assert data["max_parallel_jobs_per_repository"] == main.MAX_PARALLEL_JOBS_PER_REPOSITORY
        assert data["held_resource_locks"] == 0
        assert data["heartbeat_interval_seconds"] == main.HEARTBEAT_INTERVAL_SECONDS
        assert data["heartbeat_stale_seconds"] == main.HEARTBEAT_STALE_SECONDS
        assert data["progress_report_limit"] == main.PROGRESS_REPORT_LIMIT


class TestTimeoutRetryEndpoint:
    def _timed_out_job(self) -> str:
        request = main.CreateJobRequest(
            task="retry it",
            repository="finja-core",
            files=[main.JobFile(path="demo.py", content="x = 1\n")],
        )
        job_id = main.stage_job(request)
        main.write_status(job_id, "analysing")
        main._finish_timeout_soft(
            job_id,
            main.WorkerExecutionTimedOutError("analysis too slow"),
            "analysing",
        )
        return job_id

    def test_retry_creates_one_new_attempt_and_reuses_it(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = self._timed_out_job()
        started: list[str] = []
        monkeypatch.setattr(main, "start_job_thread", lambda candidate: started.append(candidate) or True)

        first = client.post(f"/jobs/{job_id}/retry")
        second = client.post(f"/jobs/{job_id}/retry")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["job_id"] == second.json()["job_id"]
        assert first.json()["deduplicated"] is False
        assert second.json()["deduplicated"] is True
        retry_id = first.json()["job_id"]
        assert main.read_status(retry_id)["retry_of"] == job_id
        assert main.read_status(job_id)["retry_job_id"] == retry_id
        assert started == [retry_id]

    def test_reports_expose_fail_soft_fields(self, client: TestClient) -> None:
        job_id = self._timed_out_job()

        response = client.get(f"/jobs/{job_id}/reports")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rolled_back"
        assert data["outcome"] == "timeout_soft"
        assert data["retryable"] is True
        assert data["error_code"] == "FLARE-500"
        assert data["retry_endpoint"] == f"/jobs/{job_id}/retry"

    def test_retry_rejects_non_timeout_terminal_job(self, client: TestClient) -> None:
        request = main.CreateJobRequest(task="not retryable", files=[main.JobFile(path="demo.py", content="x=1\n")])
        job_id = main.stage_job(request)
        main.write_status(job_id, "failed")

        response = client.post(f"/jobs/{job_id}/retry")

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "FLARE-602"


class TestJobsEndpointAuth:
    def test_post_jobs_rejects_repository_paths_with_structured_code(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)

        response = client.post(
            "/jobs",
            json={
                "task": "unsafe repository",
                "repository": "../private",
                "files": [{"path": "demo.py", "content": "x=1\n"}],
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "FLARE-605"

    def test_active_quest_cap_has_structured_public_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        for index in range(5):
            response = client.post(
                "/jobs",
                json={"task": f"quest {index}", "files": [{"path": "demo.py", "content": f"x={index}\n"}]},
            )
            assert response.status_code == 200

        blocked = client.post(
            "/jobs",
            json={"task": "quest six", "files": [{"path": "demo.py", "content": "x=6\n"}]},
        )

        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "FLARE-603"

    def test_post_jobs_requires_auth_when_configured(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "secret")
        response = client.post("/jobs", json={"task": "x", "files": [{"path": "a.py", "content": "b"}]})
        assert response.status_code == 401

    def test_post_jobs_rejects_unsafe_path(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        # Prevent a real worker thread from starting; we only exercise validation.
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        response = client.post("/jobs", json={"task": "x", "files": [{"path": "../evil.py", "content": "b"}]})
        assert response.status_code == 400

    def test_post_jobs_happy_path_returns_job_id(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        # Stub out the background worker so no Docker is needed.
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        response = client.post("/jobs", json={"task": "fix it", "files": [{"path": "demo.py", "content": "x=1\n"}]})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["revision"] == 1
        assert data["deduplicated"] is False
        assert len(data["job_id"]) == 32  # uuid4 hex

    def test_idempotency_key_returns_same_durable_job(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        body = {"task": "fix it", "files": [{"path": "demo.py", "content": "x=1\n"}]}
        headers = {"Idempotency-Key": "finja-request-123"}

        first = client.post("/jobs", json=body, headers=headers)
        second = client.post("/jobs", json=body, headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["job_id"] == first.json()["job_id"]
        assert second.json()["deduplicated"] is True
        stored_status = main.read_status(first.json()["job_id"])
        assert stored_status["dedupe_count"] == 1
        assert stored_status["idempotency_key_hash"] != headers["Idempotency-Key"]
        assert len(stored_status["idempotency_key_hash"]) == 64

    def test_idempotency_key_rejects_different_request(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        headers = {"Idempotency-Key": "finja-request-123"}
        first = {"task": "first", "files": [{"path": "demo.py", "content": "x=1\n"}]}
        changed = {"task": "changed", "files": [{"path": "demo.py", "content": "x=2\n"}]}

        assert client.post("/jobs", json=first, headers=headers).status_code == 200
        conflict = client.post("/jobs", json=changed, headers=headers)

        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "FLARE-601"

    def test_identical_request_without_key_is_deduplicated(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        body = {"task": "same", "files": [{"path": "demo.py", "content": "x=1\n"}]}

        first = client.post("/jobs", json=body)
        second = client.post("/jobs", json=body)

        assert second.json()["job_id"] == first.json()["job_id"]
        assert second.json()["deduplicated"] is True

    def test_failed_request_without_key_can_be_submitted_again(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        body = {"task": "retry", "files": [{"path": "demo.py", "content": "x=1\n"}]}
        first = client.post("/jobs", json=body)
        first_id = first.json()["job_id"]
        main.write_status(first_id, "failed", error="test")

        second = client.post("/jobs", json=body)

        assert second.json()["job_id"] != first_id
        assert second.json()["deduplicated"] is False

    def test_recent_success_without_key_is_deduplicated(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        body = {"task": "completed", "files": [{"path": "demo.py", "content": "x=1\n"}]}
        first = client.post("/jobs", json=body)
        first_id = first.json()["job_id"]
        for status in ["analysing", "patching", "testing", "awaiting_approval", "applying", "verifying"]:
            main.write_status(first_id, status)
        main.write_status(first_id, "completed", result={"files": []}, finished_at=main.now_iso())

        second = client.post("/jobs", json=body)

        assert second.json()["job_id"] == first_id
        assert second.json()["status"] == "completed"
        assert second.json()["deduplicated"] is True

    def test_get_unknown_job_is_404(self, client: TestClient) -> None:
        response = client.get("/jobs/does-not-exist")
        assert response.status_code == 404

    def test_reports_endpoint_returns_finja_progress_stream(self, client: TestClient) -> None:
        request = main.CreateJobRequest(task="x", files=[main.JobFile(path="a.py", content="x = 1\n")])
        job_id = main.stage_job(request)
        main.emit_heartbeat(job_id, "Flare is alive", force=True)

        response = client.get(f"/jobs/{job_id}/reports")

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert response.json()["heartbeat_sequence"] == 1
        assert response.json()["reports"][-1]["message"] == "Flare is alive"

    def test_cancel_endpoint_marks_job(self, client: TestClient) -> None:
        request = main.CreateJobRequest(task="x", files=[main.JobFile(path="a.py", content="x = 1\n")])
        job_id = main.stage_job(request)

        response = client.post(f"/jobs/{job_id}/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert response.json()["cancellation_requested"] is True

    def test_delete_rejects_non_terminal_job(self, client: TestClient) -> None:
        request = main.CreateJobRequest(task="x", files=[main.JobFile(path="a.py", content="x = 1\n")])
        job_id = main.stage_job(request)

        response = client.delete(f"/jobs/{job_id}")

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "FLARE-602"

    def test_delete_accepts_terminal_job(self, client: TestClient) -> None:
        request = main.CreateJobRequest(task="x", files=[main.JobFile(path="a.py", content="x = 1\n")])
        job_id = main.stage_job(request)
        main._roll_back_job(job_id, "test_cleanup")

        response = client.delete(f"/jobs/{job_id}")

        assert response.status_code == 200
        assert not main.job_dir(job_id).exists()

    def test_files_endpoint_uses_persisted_result_after_cleanup(self, client: TestClient) -> None:
        request = main.CreateJobRequest(task="x", files=[main.JobFile(path="a.py", content="x = 1\n")])
        job_id = main.stage_job(request)
        files = [{"path": "a.py", "content": "x = 2\n"}]
        for status in ["analysing", "patching", "testing", "awaiting_approval", "applying", "verifying"]:
            main.write_status(job_id, status)
        main.write_status(job_id, "completed", result={"files": files}, finished_at=main.now_iso())
        shutil.rmtree(main.job_dir(job_id) / "workspace")

        response = client.get(f"/jobs/{job_id}/files")

        assert response.status_code == 200
        delivered = response.json()["files"]
        # Each delivered file also names its exact bytes (additive); the
        # original path and content must be unchanged.
        assert [{"path": f["path"], "content": f["content"]} for f in delivered] == files
        assert all(f["sha256"] == hashlib.sha256(f["content"].encode("utf-8")).hexdigest() for f in delivered)


# ==============================================================================
# redact_host_paths() -- no host filesystem details in anything Finja may show
# ==============================================================================

# These tests need host-path SHAPES as input, and a personal-looking path
# literal is exactly what the GitHub contract keeps out of this tree. So the
# fixtures use synthetic account names and are assembled from parts: there is
# no real username here and no personal path literal for a scanner to find.
_HOME_ROOT = "/" + "home"
_USERS_ROOT = "/" + "Users"
_FIXTURE_USER = "fixture-account"
_FIXTURE_HOME = f"{_HOME_ROOT}/{_FIXTURE_USER}"
_FIXTURE_JOBS_DIR = f"{_FIXTURE_HOME}/flare/agent_jobs"


class TestHostPathRedaction:
    """
    A failing `docker run` echoes its own mount spec, so a daemon error used
    to carry AGENT_JOBS_HOST_DIR -- operator username and directory layout
    included -- into a FLARE-501 message. That message is stored as `error`
    in the job status, GET /jobs returns the status verbatim, and Finja may
    display those states to a user.
    """

    def test_the_configured_jobs_dir_is_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "HOST_JOBS_DIR", _FIXTURE_JOBS_DIR)
        stderr = (
            'docker: Error response from daemon: invalid mount config for type "bind": '
            f"bind source path does not exist: {_FIXTURE_JOBS_DIR}.\n"
        )
        cleaned = main.redact_host_paths(stderr)

        assert _FIXTURE_HOME not in cleaned
        assert _FIXTURE_USER not in cleaned
        assert "agent_jobs" not in cleaned
        assert "<agent-jobs-dir>" in cleaned
        assert "invalid mount config" in cleaned, "the diagnosis itself must survive"

    def test_a_home_directory_is_redacted_even_when_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "HOST_JOBS_DIR", "")
        cleaned = main.redact_host_paths(f"mkdir {_FIXTURE_HOME}/secret-project: denied")
        assert _FIXTURE_USER not in cleaned
        assert "<home>" in cleaned

    @pytest.mark.parametrize("shape,leak", [
        (f"{_USERS_ROOT}/{_FIXTURE_USER}/Projects/x", _FIXTURE_USER),
        ("/" + "root" + "/.ssh/id_ed25519", ".ssh"),
        ("Q:" + f"/{_USERS_ROOT.strip('/')}/{_FIXTURE_USER}/flare", _FIXTURE_USER),
    ])
    def test_other_host_path_shapes_are_redacted(self, shape: str, leak: str) -> None:
        assert leak not in main.redact_host_paths(f"error at {shape}")

    def test_container_paths_are_kept_because_they_are_not_host_details(self) -> None:
        """/jobs/... is what makes a worker failure diagnosable at all."""
        cleaned = main.redact_host_paths("Traceback: /worker/worker.py line 7, /jobs/abc/workspace")
        assert "/worker/worker.py" in cleaned
        assert "/jobs/abc/workspace" in cleaned

    def test_the_parent_of_the_jobs_dir_is_redacted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "HOST_JOBS_DIR", "/srv/flare-deploy/agent_jobs")
        cleaned = main.redact_host_paths("mkdir /srv/flare-deploy: permission denied")
        assert "flare-deploy" not in cleaned

    def test_redaction_survives_empty_and_clean_input(self) -> None:
        assert main.redact_host_paths("") == ""
        assert main.redact_host_paths("worker exited with 9") == "worker exited with 9"

    def test_worker_failure_message_carries_no_host_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End to end: the leak has to be gone from the raised error itself."""
        host_dir = _FIXTURE_JOBS_DIR
        monkeypatch.setattr(main, "HOST_JOBS_DIR", host_dir)
        monkeypatch.setattr(main, "_force_remove_worker_container", lambda name: None)
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix the bug",
            files=[main.JobFile(path="demo.py", content="x = 1\n")],
        ))

        class _FailingProcess:
            returncode = 125

            def poll(self) -> int | None:
                return None

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                return "", f"docker: bind source path does not exist: {host_dir}\n"

            def terminate(self) -> None:
                pass

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

            def kill(self) -> None:
                pass

        monkeypatch.setattr(main.subprocess, "Popen", lambda cmd, **kw: _FailingProcess())

        with pytest.raises(main.WorkerExecutionError) as excinfo:
            main.run_worker_phase(job_id, "preflight", time.monotonic() + 30)

        message = str(excinfo.value)
        assert excinfo.value.code == "FLARE-501"
        assert host_dir not in message
        assert _FIXTURE_HOME not in message
        assert _FIXTURE_USER not in message
        assert "exited with 125" in message

        # ... and gone from the status document GET /jobs hands back verbatim.
        main.write_status(job_id, "failed", **main._error_status_fields(excinfo.value))
        assert host_dir not in json.dumps(main.read_status(job_id))


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--color=yes"])
