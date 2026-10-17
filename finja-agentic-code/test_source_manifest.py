#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Source Manifest Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Tests for core/source_manifest.py and where the orchestrator
               attaches it.

               Two things are pinned here. The hash algorithm is written out
               a second time, independently, because a receiver in another
               codebase has to reproduce it byte for byte. And the minimality
               profile is tested for what it must NOT do: it reports excess
               and never refuses, and it says "unjudged" instead of guessing
               when there is nothing to judge against.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the manifest itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import source_manifest as manifest_module  # noqa: E402
from core.incident_envelope import validate_incident_envelope  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ORIGINAL = "def add(a, b):\n    return a - b\n"
PATCHED = "def add(a, b):\n    return a + b\n"
GOOD_DIFF = (
    "--- demo.py\n+++ demo.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ==============================================================================
# The hash algorithm, written out independently
# ==============================================================================

class TestHashes:

    def test_a_file_digest_is_sha256_of_its_utf8_content(self) -> None:
        assert manifest_module.file_sha256("hello\n") == hashlib.sha256(b"hello\n").hexdigest()
        assert manifest_module.file_sha256("") == hashlib.sha256(b"").hexdigest()

    def test_multibyte_content_is_hashed_as_utf8_bytes(self) -> None:
        text = "größe = 'ä'\n"
        assert manifest_module.file_sha256(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_it_agrees_with_the_digest_the_incident_envelope_already_verifies(self) -> None:
        """One definition of "the digest of a file" across the whole contract."""
        content = "x = 1\n"
        envelope = validate_incident_envelope({
            "envelope_version": 1, "incident_id": "123e4567-e89b-42d3-a456-426614174000",
            "observed_at": "2026-10-17T15:00:00Z", "origin": "finja", "component": "finja-chat",
            "repository": "r", "mode": "standard", "error_kind": "KeyError", "error_code": None,
            "summary": "A stage failed.", "frames": [{"path": "demo.py", "line": 1, "symbol": "run"}],
            "files": [{"path": "demo.py", "content": content, "sha256": _sha(content)}],
            "redaction": {"policy": "finja-flare-redaction-v1", "source_minimized": True,
                          "sensitive_values_removed": True},
        })
        assert envelope.files[0].sha256 == manifest_module.file_sha256(envelope.files[0].content)

    def test_the_bundle_digest_follows_the_documented_algorithm(self) -> None:
        """
        sha256 over, for every path in sorted order: a 4-byte big-endian path
        length, the UTF-8 path, and the 32 raw bytes of the file digest.
        Reproduced here without calling the module, because a receiver in
        another language has to do exactly this.
        """
        digests = {"b.py": _sha("two"), "a.py": _sha("one")}
        outer = hashlib.sha256()
        for path in ("a.py", "b.py"):
            outer.update(len(path.encode()).to_bytes(4, "big"))
            outer.update(path.encode())
            outer.update(bytes.fromhex(digests[path]))
        assert manifest_module.bundle_sha256(digests) == outer.hexdigest()

    def test_the_order_files_were_listed_in_does_not_matter(self) -> None:
        one = {"a.py": _sha("1"), "b.py": _sha("2")}
        two = {"b.py": _sha("2"), "a.py": _sha("1")}
        assert manifest_module.bundle_sha256(one) == manifest_module.bundle_sha256(two)

    def test_renaming_a_file_changes_the_bundle(self) -> None:
        assert manifest_module.bundle_sha256({"a.py": _sha("x")}) != manifest_module.bundle_sha256({"b.py": _sha("x")})

    def test_swapping_two_contents_between_two_paths_changes_the_bundle(self) -> None:
        straight = {"a.py": _sha("1"), "b.py": _sha("2")}
        swapped = {"a.py": _sha("2"), "b.py": _sha("1")}
        assert manifest_module.bundle_sha256(straight) != manifest_module.bundle_sha256(swapped)

    def test_an_empty_bundle_has_a_defined_digest(self) -> None:
        assert manifest_module.bundle_sha256({}) == hashlib.sha256(b"").hexdigest()


# ==============================================================================
# Describing a candidate against its input
# ==============================================================================

class TestBuildManifest:

    def _manifest(self, base, candidate, **kwargs) -> dict:
        return manifest_module.build_manifest(base, candidate, **kwargs)

    def test_a_modified_file_names_both_sides(self) -> None:
        manifest = self._manifest([{"path": "demo.py", "content": ORIGINAL}],
                                  [{"path": "demo.py", "content": PATCHED}])
        entry = manifest["files"][0]
        assert entry["status"] == "modified"
        assert entry["base_sha256"] == _sha(ORIGINAL)
        assert entry["candidate_sha256"] == _sha(PATCHED)

    def test_every_status_is_recognised(self) -> None:
        base = [{"path": "same.py", "content": "s"}, {"path": "edit.py", "content": "1"},
                {"path": "gone.py", "content": "g"}]
        candidate = [{"path": "same.py", "content": "s"}, {"path": "edit.py", "content": "2"},
                     {"path": "new.py", "content": "n"}]
        manifest = self._manifest(base, candidate)

        statuses = {entry["path"]: entry["status"] for entry in manifest["files"]}
        assert statuses == {"same.py": "unchanged", "edit.py": "modified",
                            "gone.py": "deleted", "new.py": "created"}
        assert manifest["summary"] == {"files": 4, "unchanged": 1, "modified": 1, "line_endings_only": 0,
                                       "created": 1, "deleted": 1, "unknown": 0}

    def test_a_created_file_has_no_base_and_a_deleted_one_no_candidate(self) -> None:
        manifest = self._manifest([{"path": "gone.py", "content": "g"}], [{"path": "new.py", "content": "n"}])
        by_path = {entry["path"]: entry for entry in manifest["files"]}
        assert by_path["new.py"]["base_sha256"] is None and by_path["new.py"]["base_bytes"] is None
        assert by_path["gone.py"]["candidate_sha256"] is None and by_path["gone.py"]["candidate_bytes"] is None

    def test_a_file_that_differs_only_in_line_endings_has_its_own_status(self) -> None:
        """So a receiver can tell a whole-file rewrite from an edit and decline the former."""
        manifest = self._manifest([{"path": "a.py", "content": "x = 1\r\ny = 2\r\n"}],
                                  [{"path": "a.py", "content": "x = 1\ny = 2\n"}])
        entry = manifest["files"][0]
        assert entry["status"] == "line_endings_only"
        assert entry["base_sha256"] != entry["candidate_sha256"], "the bytes did change; the status says how"
        assert manifest["summary"]["line_endings_only"] == 1

    def test_a_real_edit_on_a_crlf_file_is_still_modified(self) -> None:
        manifest = self._manifest([{"path": "a.py", "content": "x = 1\r\n"}],
                                  [{"path": "a.py", "content": "x = 2\n"}])
        assert manifest["files"][0]["status"] == "modified"

    def test_an_unavailable_input_is_unknown_not_everything_created(self) -> None:
        """None means "could not be read"; an empty list means "there was nothing". They must not be confused."""
        unknown = self._manifest(None, [{"path": "a.py", "content": "x"}])
        assert unknown["base_known"] is False
        assert unknown["files"][0]["status"] == "unknown"
        assert unknown["files"][0]["base_sha256"] is None

        empty = self._manifest([], [{"path": "a.py", "content": "x"}])
        assert empty["base_known"] is True
        assert empty["files"][0]["status"] == "created"

    def test_sizes_are_utf8_bytes_not_characters(self) -> None:
        manifest = self._manifest([{"path": "a.py", "content": "ä"}], [{"path": "a.py", "content": "ää"}])
        assert manifest["files"][0]["base_bytes"] == 2
        assert manifest["files"][0]["candidate_bytes"] == 4

    def test_the_bundle_digests_move_only_when_their_side_moves(self) -> None:
        base = [{"path": "demo.py", "content": ORIGINAL}]
        first = self._manifest(base, [{"path": "demo.py", "content": PATCHED}])
        second = self._manifest(base, [{"path": "demo.py", "content": PATCHED + "# more\n"}])
        assert first["base_bundle_sha256"] == second["base_bundle_sha256"]
        assert first["candidate_bundle_sha256"] != second["candidate_bundle_sha256"]

    def test_the_result_does_not_depend_on_list_order(self) -> None:
        a = [{"path": "a.py", "content": "1"}, {"path": "b.py", "content": "2"}]
        b = list(reversed(a))
        assert self._manifest(a, a) == self._manifest(b, b)

    def test_line_counts_come_from_the_review_that_already_parsed_the_diff(self) -> None:
        report = {"files": [{"path": "demo.py", "added": 3, "removed": 2}]}
        manifest = self._manifest([{"path": "demo.py", "content": ORIGINAL}],
                                  [{"path": "demo.py", "content": PATCHED}], repair_report=report)
        assert manifest["files"][0]["lines_added"] == 3
        assert manifest["files"][0]["lines_removed"] == 2

    def test_without_a_review_there_are_simply_no_line_counts(self) -> None:
        manifest = self._manifest([{"path": "demo.py", "content": ORIGINAL}],
                                  [{"path": "demo.py", "content": PATCHED}])
        assert "lines_added" not in manifest["files"][0]

    @pytest.mark.parametrize("base,candidate", [
        (None, None), ([], []), ("not a list", 5),
        ([{"path": "a.py"}, {"content": "x"}, "junk", None, {"path": 1, "content": "x"}], []),
    ])
    def test_malformed_input_is_skipped_not_guessed_at(self, base, candidate) -> None:
        manifest = self._manifest(base, candidate)
        assert manifest["files"] == [] or all(isinstance(entry["path"], str) for entry in manifest["files"])

    def test_the_manifest_carries_no_file_content(self) -> None:
        secret_looking = "UNIQUE-CONTENT-MARKER"
        manifest = self._manifest([{"path": "a.py", "content": secret_looking}],
                                  [{"path": "a.py", "content": secret_looking + "!"}])
        assert secret_looking not in json.dumps(manifest)

    def test_it_states_what_the_hash_covers(self) -> None:
        manifest = self._manifest([], [])
        assert manifest["algorithm"] == "sha256"
        assert "transmitted" in manifest["hashed_over"]


class TestVerifyFiles:

    def _pair(self):
        files = [{"path": "demo.py", "content": PATCHED}, {"path": "util.py", "content": "u = 1\n"}]
        return manifest_module.build_manifest([], files), files

    def test_exactly_the_described_files_verify_clean(self) -> None:
        manifest, files = self._pair()
        assert manifest_module.verify_files(manifest, files) == []

    def test_a_changed_byte_is_a_digest_mismatch(self) -> None:
        manifest, files = self._pair()
        files[0] = {"path": "demo.py", "content": PATCHED + " "}
        assert {"kind": "digest_mismatch", "path": "demo.py"} in manifest_module.verify_files(manifest, files)

    def test_a_missing_file_is_reported(self) -> None:
        manifest, files = self._pair()
        assert {"kind": "missing", "path": "util.py"} in manifest_module.verify_files(manifest, files[:1])

    def test_an_extra_file_is_reported(self) -> None:
        manifest, files = self._pair()
        files.append({"path": "extra.py", "content": "e"})
        assert {"kind": "unexpected", "path": "extra.py"} in manifest_module.verify_files(manifest, files)


# ==============================================================================
# How little was needed
# ==============================================================================

def _envelope(*, files: dict[str, str], frames: list[tuple[str, int]]):
    return validate_incident_envelope({
        "envelope_version": 1, "incident_id": "123e4567-e89b-42d3-a456-426614174000",
        "observed_at": "2026-10-17T15:00:00Z", "origin": "finja", "component": "finja-chat",
        "repository": "r", "mode": "standard", "error_kind": "KeyError", "error_code": "FINJA-999",
        "summary": "A stage failed.",
        "frames": [{"path": path, "line": line, "symbol": "run"} for path, line in frames],
        "files": [{"path": path, "content": content, "sha256": _sha(content)} for path, content in files.items()],
        "redaction": {"policy": "finja-flare-redaction-v1", "source_minimized": True,
                      "sensitive_values_removed": True},
    })


class TestProfileBundle:

    def test_every_file_a_frame_points_at_is_minimal(self) -> None:
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": "x\n", "b.py": "y\n"},
                                                           frames=[("a.py", 1), ("b.py", 1)]))
        assert profile["verdict"] == "minimal"
        assert profile["unreferenced_files"] == []

    def test_a_file_no_frame_points_at_is_named(self) -> None:
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": "x\n", "extra.py": "y\n"},
                                                           frames=[("a.py", 1)]))
        assert profile["verdict"] == "has_unreferenced_files"
        assert profile["unreferenced_files"] == ["extra.py"]

    def test_without_frames_nothing_is_called_excess(self) -> None:
        """No frame, nothing to judge relevance against: say so instead of listing every file."""
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": "x\n", "b.py": "y\n"}, frames=[]))
        assert profile["verdict"] == "unjudged"
        assert profile["unreferenced_files"] == []

    def test_a_frame_whose_file_was_not_sent_is_reported(self) -> None:
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": "x\n"},
                                                           frames=[("a.py", 1), ("missing.py", 7)]))
        assert profile["frames_without_source"] == ["missing.py"]

    def test_sizes_and_the_fill_ratio_are_measured(self) -> None:
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": "x" * 1200 + "\n"}, frames=[("a.py", 1)]))
        assert profile["files"][0]["bytes"] == 1201
        assert profile["total_bytes"] == 1201
        assert profile["fill_ratio"] == round(1201 / profile["limit_bytes"], 3)

    @pytest.mark.parametrize("content,lines", [("a\nb\n", 2), ("a\nb", 2), ("", 0), ("\n", 1), ("a", 1)])
    def test_lines_are_counted_whether_or_not_the_last_one_ends_in_a_break(self, content, lines) -> None:
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": content}, frames=[("a.py", 1)]))
        assert profile["files"][0]["lines"] == lines

    def test_frame_lines_are_unique_sorted_and_capped(self) -> None:
        frames = [("a.py", n) for n in (5, 3, 5, 1)] + [("a.py", n) for n in range(10, 15)]
        profile = manifest_module.profile_bundle(_envelope(files={"a.py": "x\n"}, frames=frames[:8]))
        listed = profile["files"][0]["frame_lines"]
        assert listed == sorted(set(listed))
        assert len(listed) <= manifest_module.MAX_FRAME_LINES_LISTED

    def test_the_profile_carries_no_content_and_no_summary(self) -> None:
        envelope = _envelope(files={"a.py": "UNIQUE-CONTENT-MARKER = 1\n"}, frames=[("a.py", 1)])
        text = json.dumps(manifest_module.profile_bundle(envelope))
        assert "UNIQUE-CONTENT-MARKER" not in text
        assert "A stage failed." not in text


# ==============================================================================
# In the orchestrator
# ==============================================================================

_EVIDENCE = {
    "schema_version": 1, "runner": "python-unittest", "python_version": "3.14", "runner_sha256": "r" * 64,
    "command": ["python", "-m", "unittest"], "source_sha256": "s" * 64, "test_files": [],
    "tests_run": 0, "status": "not_run", "output_sha256": None, "log_artifact": None,
}


class TestManifestInResults:

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.clear()
        self.monkeypatch = monkeypatch

    def _run(self) -> tuple[str, dict, dict]:
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix add", repository="t", files=[main.JobFile(path="demo.py", content=ORIGINAL)]))
        job = main.job_dir(job_id)
        (job / "model.patch").write_text(GOOD_DIFF, encoding="utf-8", newline="\n")

        def fake_phase(jid: str, phase: str, deadline: float) -> dict:
            content = ORIGINAL if phase == "preflight" else PATCHED
            result = {"job_id": jid, "phase": phase,
                      "patch_result": None if phase == "preflight" else {"returncode": 0, "stdout": "", "stderr": ""},
                      "postflight_python_syntax": [], "files": [{"path": "demo.py", "content": content}],
                      "test_evidence": None if phase == "preflight" else dict(_EVIDENCE)}
            main.write_json(job / f"{phase}_result.json", result)
            return result

        self.monkeypatch.setattr(main, "run_worker_phase", fake_phase)
        main.run_preapproval(job_id)
        awaiting = main.read_status(job_id)
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        main.run_approved(job_id)
        return job_id, awaiting, main.read_status(job_id)

    def test_the_candidate_shown_for_approval_names_its_base_and_its_changes(self) -> None:
        _, awaiting, _ = self._run()
        assert awaiting["status"] == "awaiting_approval"

        manifest = awaiting["result"]["manifest"]
        entry = manifest["files"][0]
        assert entry["status"] == "modified"
        assert entry["base_sha256"] == _sha(ORIGINAL), "must be the bytes Finja submitted"
        assert entry["candidate_sha256"] == _sha(PATCHED)
        assert (entry["lines_added"], entry["lines_removed"]) == (1, 1)

    def test_the_finished_job_carries_a_manifest_a_receiver_can_verify(self) -> None:
        _, _, final = self._run()
        assert final["status"] == "completed"

        result = final["result"]
        assert manifest_module.verify_files(result["manifest"], result["files"]) == []
        assert result["manifest"]["files"][0]["base_sha256"] == _sha(ORIGINAL)

    def test_the_base_hash_names_what_was_submitted_not_what_was_tested(self) -> None:
        """After the apply the workspace holds the candidate; the base must still be the input."""
        _, _, final = self._run()
        entry = final["result"]["manifest"]["files"][0]
        assert entry["base_sha256"] == _sha(ORIGINAL)
        assert entry["base_sha256"] != entry["candidate_sha256"]

    def test_the_files_endpoint_names_the_bytes_of_every_file(self) -> None:
        job_id, _, _ = self._run()
        body = TestClient(main.app).get(f"/jobs/{job_id}/files").json()
        assert body["files"], "a finished job has files to deliver"
        for entry in body["files"]:
            assert entry["sha256"] == _sha(entry["content"])


class TestBaseComesFromTheStagedCopy:
    """
    The worker runs in a container and is the less trusted side, and it has
    been wrong about line endings before. The base a manifest names has to be
    what the sender can reproduce byte for byte: the orchestrator's own copy.
    """

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        self.monkeypatch = monkeypatch

    def test_the_base_hash_is_the_submitted_bytes_even_when_the_worker_altered_them(self) -> None:
        crlf = "def add(a, b):\r\n    return a - b\r\n"
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix add", repository="t", files=[main.JobFile(path="demo.py", content=crlf)]))
        job = main.job_dir(job_id)
        (job / "model.patch").write_text(GOOD_DIFF, encoding="utf-8", newline="\n")

        def lossy_worker(jid: str, phase: str, deadline: float) -> dict:
            # What the worker used to do: hand back text with the CRs gone.
            content = crlf.replace("\r\n", "\n") if phase == "preflight" else PATCHED
            result = {"job_id": jid, "phase": phase,
                      "patch_result": None if phase == "preflight" else {"returncode": 0, "stdout": "", "stderr": ""},
                      "postflight_python_syntax": [], "files": [{"path": "demo.py", "content": content}],
                      "test_evidence": None if phase == "preflight" else dict(_EVIDENCE)}
            main.write_json(job / f"{phase}_result.json", result)
            return result

        self.monkeypatch.setattr(main, "run_worker_phase", lossy_worker)
        main.run_preapproval(job_id)

        entry = main.read_status(job_id)["result"]["manifest"]["files"][0]
        assert entry["base_sha256"] == _sha(crlf), "the hash of what the sender sent, not of what the worker returned"
        assert entry["base_sha256"] != _sha(crlf.replace("\r\n", "\n"))

    def test_an_unreadable_staged_copy_makes_the_base_unknown_instead_of_empty(self) -> None:
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix add", repository="t", files=[main.JobFile(path="demo.py", content=ORIGINAL)]))
        assert main._submitted_files(job_id) == [{"path": "demo.py", "content": ORIGINAL}]

        (main.job_dir(job_id) / "request.json").unlink()
        assert main._submitted_files(job_id) is None

        manifest = manifest_module.build_manifest(
            main._submitted_files(job_id), [{"path": "demo.py", "content": PATCHED}])
        assert manifest["base_known"] is False
        assert manifest["files"][0]["status"] == "unknown"


@pytest.mark.skipif(shutil.which("patch") is None, reason="needs the patch program the worker image carries")
class TestUntouchedWindowsFileEndToEnd:
    """
    The bug this was found through, run through the real worker code as a
    process (no container): a job with one patched file and one UNTOUCHED file
    that has Windows line endings was rolled back at the apply with FLARE-501,
    "Approved candidate differed from its sandbox test evidence". The test and
    the verification disagreed about a file nothing had changed, because the
    snapshot the verification restores from had lost its carriage returns.
    """

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)

        def real_worker(job_id: str, phase: str, deadline: float) -> dict:
            env = {**os.environ, "JOBS_DIR": str(main.JOBS_DIR), "JOB_ID": job_id,
                   "JOB_PHASE": phase, "PYTHONPATH": str(_MODULE_ROOT / "worker")}
            completed = subprocess.run([sys.executable, str(_MODULE_ROOT / "worker" / "worker.py")],
                                       env=env, capture_output=True, text=True, timeout=120)
            if completed.returncode != 0:
                raise main.WorkerExecutionError(f"worker {phase}: {completed.stderr[-200:]}")
            return json.loads((main.job_dir(job_id) / f"{phase}_result.json").read_text(encoding="utf-8"))

        monkeypatch.setattr(main, "run_worker_phase", real_worker)

    def _job(self, other_content: str) -> dict:
        job_id = main.stage_job(main.CreateJobRequest(task="Fix add", repository="t", files=[
            main.JobFile(path="demo.py", content=ORIGINAL),
            main.JobFile(path="other.py", content=other_content),
        ]))
        (main.job_dir(job_id) / "model.patch").write_text(GOOD_DIFF, encoding="utf-8", newline="")
        main.run_preapproval(job_id)
        awaiting = main.read_status(job_id)
        assert awaiting["status"] == "awaiting_approval", awaiting.get("error")
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        main.run_approved(job_id)
        return main.read_status(job_id)

    def test_an_untouched_file_with_windows_line_endings_no_longer_fails_the_job(self) -> None:
        final = self._job("x = 1\r\ny = 2\r\n")
        assert final["status"] == "completed", (final.get("error_code"), final.get("error"))

    def test_the_manifest_calls_that_file_unchanged_and_names_its_exact_bytes(self) -> None:
        crlf = "x = 1\r\ny = 2\r\n"
        manifest = self._job(crlf)["result"]["manifest"]
        by_path = {entry["path"]: entry for entry in manifest["files"]}

        assert by_path["other.py"]["status"] == "unchanged"
        assert by_path["other.py"]["base_sha256"] == _sha(crlf)
        assert by_path["other.py"]["candidate_sha256"] == _sha(crlf)
        assert by_path["demo.py"]["status"] == "modified"

    def test_a_job_with_only_unix_line_endings_is_unaffected(self) -> None:
        assert self._job("x = 1\ny = 2\n")["status"] == "completed"


class TestManifestOnIncidents:

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        self.client = TestClient(main.app)

    def _body(self, files: dict[str, str], frames: list[tuple[str, int]]) -> dict:
        from datetime import UTC, datetime
        return {
            "envelope_version": 1, "incident_id": "123e4567-e89b-42d3-a456-426614174000",
            "observed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "origin": "finja",
            "component": "finja-chat", "repository": "r", "mode": "standard", "error_kind": "KeyError",
            "error_code": "FINJA-999", "summary": "A stage failed.",
            "frames": [{"path": path, "line": line, "symbol": "run"} for path, line in frames],
            "files": [{"path": p, "content": c, "sha256": _sha(c)} for p, c in files.items()],
            "redaction": {"policy": "finja-flare-redaction-v1", "source_minimized": True,
                          "sensitive_values_removed": True},
        }

    def test_the_decision_tells_the_sender_how_much_of_its_bundle_was_excess(self) -> None:
        response = self.client.post("/incidents", json=self._body(
            {"a.py": "x = 1\n", "extra.py": "y = 2\n"}, [("a.py", 1)]))
        assert response.status_code == 200
        source = response.json()["source"]
        assert source["verdict"] == "has_unreferenced_files"
        assert source["unreferenced_files"] == ["extra.py"]

    def test_it_reports_and_never_refuses(self) -> None:
        """Excess source is advice for the sender, not a reason to drop a real incident."""
        response = self.client.post("/incidents", json=self._body(
            {"a.py": "x = 1\n", "extra.py": "y = 2\n"}, [("a.py", 1)]))
        assert response.status_code == 200
        assert response.json()["route"] in {"observe", "classify", "repair"}

    def test_the_response_repeats_no_source(self) -> None:
        response = self.client.post("/incidents", json=self._body(
            {"a.py": "UNIQUE_CONTENT_MARKER = 1\n"}, [("a.py", 1)]))
        assert "UNIQUE_CONTENT_MARKER" not in response.text
