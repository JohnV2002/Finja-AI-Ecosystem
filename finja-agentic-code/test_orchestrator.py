#!/usr/bin/env python3
"""
======================================================================
         Flare (Finja Agentic Code) – Orchestrator Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
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

  New in v1.0.0:
    • Initial pytest suite for the orchestrator

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import sys
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
        assert main.read_status(job_id)["status"] == "queued"

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


class TestJobsEndpointAuth:
    def test_post_jobs_requires_auth_when_configured(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "secret")
        response = client.post("/jobs", json={"task": "x", "files": [{"path": "a.py", "content": "b"}]})
        assert response.status_code == 401

    def test_post_jobs_rejects_unsafe_path(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        # Prevent a real worker thread from starting; we only exercise validation.
        monkeypatch.setattr(main, "run_worker", lambda job_id: None)
        response = client.post("/jobs", json={"task": "x", "files": [{"path": "../evil.py", "content": "b"}]})
        assert response.status_code == 400

    def test_post_jobs_happy_path_returns_job_id(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        # Stub out the background worker so no Docker is needed.
        monkeypatch.setattr(main, "run_worker", lambda job_id: None)
        response = client.post("/jobs", json={"task": "fix it", "files": [{"path": "demo.py", "content": "x=1\n"}]})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert len(data["job_id"]) == 32  # uuid4 hex

    def test_get_unknown_job_is_404(self, client: TestClient) -> None:
        response = client.get("/jobs/does-not-exist")
        assert response.status_code == 404


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--color=yes"])
