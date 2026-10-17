#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – L5 Manual Scope Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Manual routing before model/worker or before repair sandbox.

  New in v1.11.0:
    - Covers explicit architecture requests and multi-file candidate handoff.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

======================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import manual_scope  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
    monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
    with main.ACTIVE_JOBS_LOCK:
        main.ACTIVE_JOBS.clear()


def _change(path: str) -> str:
    return f"--- {path}\n+++ {path}\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


class TestManualPolicy:
    def test_explicit_manual_and_architecture_intent_route_early(self) -> None:
        manual = manual_scope.review_request(mode="manual", task="Fix it", paths=["demo.py"])
        assert manual["route"] == "manual"
        assert manual["reasons"][0]["kind"] == "manual_requested"
        architecture = manual_scope.review_request(
            mode="standard", task="Refactor the public API interface", paths=["demo.py"],
        )
        assert architecture["route"] == "manual"
        assert architecture["reasons"][0]["kind"] == "architecture_intent"

    @pytest.mark.parametrize("path", ["config/settings.toml", "src/schema.py", "src/interface.py"])
    def test_configuration_input_is_conservative_manual_signal(self, path: str) -> None:
        report = manual_scope.review_request(mode="standard", task="Fix it", paths=[path])
        assert report["route"] == "manual"
        assert report["paths"] == [path]

    def test_single_file_candidate_stays_automatic(self) -> None:
        report = manual_scope.review_candidate({"files": [{"path": "demo.py", "kind": "modify"}]})
        assert report["route"] == "automatic"

    @pytest.mark.parametrize("entries,reason", [
        ([{"path": "a.py", "kind": "modify"}, {"path": "b.py", "kind": "modify"}], "multi_file_patch"),
        ([{"path": "new.py", "kind": "create"}], "file_topology"),
        ([{"path": "src/schema/user.py", "kind": "modify"}], "architecture_path"),
    ])
    def test_candidate_needing_human_design_is_not_approval_eligible(self, entries: list[dict], reason: str) -> None:
        report = manual_scope.review_candidate({"files": entries})
        assert report["route"] == "manual"
        assert reason in {item["kind"] for item in report["reasons"]}
        assert report["approval_eligible"] is False
        assert report["sandbox_repair_run"] is False


class TestManualLifecycle:
    def test_manual_request_never_calls_model_or_worker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = main.stage_job(main.CreateJobRequest(
            task="Redesign the architecture", mode="manual",
            files=[main.JobFile(path="demo.py", content="x = 1\n")],
        ))
        monkeypatch.setattr(main, "run_worker_phase", lambda *args: pytest.fail("worker must not run"))
        monkeypatch.setattr(main, "call_openrouter", lambda *args: pytest.fail("model must not run"))

        main.run_preapproval(job_id)

        status = main.read_status(job_id)
        assert status["status"] == "failed"
        assert status["outcome"] == "manual_required"
        assert status["error_code"] == "FLARE-609"
        assert status["manual_review"]["stage"] == "request"
        assert status["manual_review"]["candidate_diff_seen"] is False
        assert not (main.job_dir(job_id) / "model.patch").exists()
        assert not (main.job_dir(job_id) / "preflight_result.json").exists()
        assert main.get_manual_handoff(job_id)["candidate_diff"] is None
        with pytest.raises(main.InvalidJobStateTransitionError):
            main.approve_job(job_id, main.JobDecisionRequest(revision=status["revision"]))

    def test_multi_file_diff_stops_before_repair_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix both bugs", files=[
                main.JobFile(path="a.py", content="x = 1\n"),
                main.JobFile(path="b.py", content="x = 1\n"),
            ],
        ))
        diff = _change("a.py") + _change("b.py")
        main.write_text(main.job_dir(job_id) / "model.patch", diff)
        monkeypatch.setattr(main, "MAX_REPAIR_FILES", 1)
        phases: list[str] = []

        def fake_phase(candidate: str, phase: str, deadline: float) -> dict:
            phases.append(phase)
            if phase != "preflight":
                pytest.fail("L5 candidate reached a repair sandbox")
            result = {"job_id": candidate, "phase": phase, "files": []}
            main.write_json(main.job_dir(candidate) / "preflight_result.json", result)
            return result

        monkeypatch.setattr(main, "run_worker_phase", fake_phase)
        main.run_preapproval(job_id)

        status = main.read_status(job_id)
        assert status["status"] == "failed"
        assert status["outcome"] == "manual_required"
        assert status["error_code"] == "FLARE-609"
        assert status["manual_review"]["stage"] == "candidate"
        assert status["manual_review"]["paths"] == ["a.py", "b.py"]
        assert phases == ["preflight"]
        assert not (main.job_dir(job_id) / "test_patch_result.json").exists()
        assert main.read_json(main.job_dir(job_id) / "manual_review.json") == status["manual_review"]
        assert main.get_manual_handoff(job_id)["candidate_diff"] == diff
        assert status["locks_held"] is False
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "test-token")
        client = TestClient(main.app)
        assert client.get(f"/jobs/{job_id}/manual").status_code == 401
        authorized = client.get(f"/jobs/{job_id}/manual", headers={"Authorization": "Bearer test-token"})
        assert authorized.status_code == 200
        assert authorized.json()["candidate_diff"] == diff
