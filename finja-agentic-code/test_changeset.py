#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Changeset Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Tests for core/changeset.py, the content-bound approval and
               GET /jobs/{id}/changeset.

               The centrepiece is a round trip: the forward diff applied to
               the submitted input gives the candidate, and the reverse diff
               applied to the candidate gives the input back, byte for byte.
               That is proven with a strict applier written in this file,
               independent of the production code, and cross-checked against
               the real patch program where it is installed.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the changeset itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import changeset as cs  # noqa: E402
from core import source_manifest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ORIGINAL = "def add(a, b):\n    return a - b\n"
PATCHED = "def add(a, b):\n    return a + b\n"
MODEL_DIFF = (
    "--- demo.py\n+++ demo.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ==============================================================================
# A strict applier, written independently of the production code
# ==============================================================================

def _split(text: str) -> list[str]:
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def apply_diff(files: dict[str, str], diff: str) -> dict[str, str]:
    """
    Apply a unified diff with no fuzz and no offset: every context and removed
    line must be exactly where the hunk header says. Hunk bodies are read by
    their declared line counts, so a content line that looks like a header
    cannot confuse it.
    """
    result = dict(files)
    lines = diff.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    index = 0
    while index < len(lines):
        assert lines[index].startswith("--- "), f"expected a file header, got {lines[index]!r}"
        source, target = lines[index][4:], lines[index + 1][4:]
        assert lines[index + 1].startswith("+++ ")
        index += 2
        old = _split(files[source]) if source != cs.DEV_NULL else []
        if source == cs.DEV_NULL:
            assert target not in files, "a diff that creates a file must not find it present"
        new: list[str] = []
        position = 0
        while index < len(lines) and lines[index].startswith("@@"):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[index])
            assert match, f"bad hunk header {lines[index]!r}"
            start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            index += 1
            begin = start - 1 if old_count else start
            new.extend(old[position:begin])
            position = begin
            seen_old = seen_new = 0
            while seen_old < old_count or seen_new < new_count:
                tag, text = lines[index][:1], lines[index][1:]
                index += 1
                terminated = True
                if index < len(lines) and lines[index].startswith("\\"):
                    terminated = False
                    index += 1
                full = text + ("\n" if terminated else "")
                if tag in {" ", "-"}:
                    assert position < len(old) and old[position] == full, \
                        f"context mismatch at old line {position + 1}: {old[position:position + 1]!r} vs {full!r}"
                    position += 1
                    seen_old += 1
                if tag in {" ", "+"}:
                    new.append(full)
                    seen_new += 1
        new.extend(old[position:])
        if target == cs.DEV_NULL:
            result.pop(source)
        else:
            result[target] = "".join(new)
    return result


CASES = {
    "edit in the middle": ("a\nb\nc\nd\ne\n", "a\nb\nX\nd\ne\n"),
    "insert at the start": ("a\nb\n", "new\na\nb\n"),
    "insert at the end": ("a\nb\n", "a\nb\nnew\n"),
    "delete lines": ("a\nb\nc\nd\n", "a\nd\n"),
    "two hunks far apart": ("\n".join(f"line {n}" for n in range(60)) + "\n",
                            "\n".join(("CHANGED" if n in (3, 55) else f"line {n}") for n in range(60)) + "\n"),
    "windows line endings": ("a\r\nb\r\nc\r\n", "a\r\nX\r\nc\r\n"),
    "no newline at the end, both sides": ("a\nb", "a\nB"),
    "newline added at the end": ("a\nb", "a\nb\n"),
    "newline removed at the end": ("a\nb\n", "a\nb"),
    "unicode": ("größe = 'ä'\n", "größe = 'ö'\n"),
    "tabs and trailing spaces": ("\tx = 1  \n", "\tx = 2  \n"),
    "a content line that looks like a header": ("--- not a header\n+++ nor this\n@@ -1 +1 @@\n",
                                                "--- not a header\n+++ changed\n@@ -1 +1 @@\n"),
    "form feed and unicode separators stay inside a line": ("a\x0cb\nc d\n", "a\x0cb\nC d\n"),
    "a very long line": ("x" * 50_000 + "\n", "x" * 50_000 + "y\n"),
    "file becomes empty": ("a\nb\n", ""),
    "file grows from empty": ("", "a\nb\n"),
}


class TestRoundTrip:

    @pytest.mark.parametrize("label", list(CASES))
    def test_forward_then_reverse_restores_every_byte(self, label: str) -> None:
        before, after = CASES[label]
        base, candidate = {"f.py": before}, {"f.py": after}
        forward = cs.unified_diff(base, candidate)["unified"]
        inverse = cs.unified_diff(candidate, base)["unified"]

        assert apply_diff(base, forward) == candidate, label
        assert apply_diff(candidate, inverse) == base, label

    def test_the_format_is_the_conventional_unified_diff_with_three_lines_of_context(self) -> None:
        """
        A round trip would pass with no context at all, which is a valid but
        worse diff: the context is what lets patch find the place and a person
        read the change. So the exact text is pinned.
        """
        diff = cs.unified_diff({"f.py": "a\nb\nc\nd\ne\nf\ng\n"}, {"f.py": "a\nb\nc\nX\ne\nf\ng\n"})["unified"]
        assert diff == (
            "--- f.py\n+++ f.py\n"
            "@@ -1,7 +1,7 @@\n"
            " a\n b\n c\n-d\n+X\n e\n f\n g\n"
        )

    def test_far_apart_changes_get_separate_hunks_with_their_own_context(self) -> None:
        lines = [f"line {n}\n" for n in range(40)]
        changed = list(lines)
        changed[2], changed[37] = "TOP\n", "BOTTOM\n"
        diff = cs.unified_diff({"f.py": "".join(lines)}, {"f.py": "".join(changed)})
        assert diff["files"][0]["hunks"] == 2
        assert diff["unified"].count("\n@@ ") == 2, "one header line per hunk"
        assert diff["unified"].startswith("--- f.py\n+++ f.py\n@@ ")
        assert apply_diff({"f.py": "".join(lines)}, diff["unified"]) == {"f.py": "".join(changed)}

    def test_a_created_file_round_trips(self) -> None:
        base, candidate = {"a.py": "x\n"}, {"a.py": "x\n", "new.py": "n = 1\n"}
        forward = cs.unified_diff(base, candidate)["unified"]
        assert "--- /dev/null\n+++ new.py\n" in forward
        assert apply_diff(base, forward) == candidate
        assert apply_diff(candidate, cs.unified_diff(candidate, base)["unified"]) == base

    def test_a_deleted_file_round_trips(self) -> None:
        base, candidate = {"a.py": "x\n", "old.py": "o = 1\n"}, {"a.py": "x\n"}
        forward = cs.unified_diff(base, candidate)["unified"]
        assert "--- old.py\n+++ /dev/null\n" in forward
        assert apply_diff(base, forward) == candidate
        assert apply_diff(candidate, cs.unified_diff(candidate, base)["unified"]) == base

    def test_several_files_in_one_diff(self) -> None:
        base = {"a.py": "1\n2\n", "b.py": "x\n", "same.py": "s\n"}
        candidate = {"a.py": "1\nTWO\n", "b.py": "x\ny\n", "same.py": "s\n", "c.py": "new\n"}
        forward = cs.unified_diff(base, candidate)
        assert [f["path"] for f in forward["files"]] == ["a.py", "b.py", "c.py"], "unchanged files are not in the diff"
        assert apply_diff(base, forward["unified"]) == candidate

    def test_the_counts_agree_with_what_the_diff_does(self) -> None:
        result = cs.unified_diff({"f.py": "a\nb\nc\n"}, {"f.py": "a\nX\nY\nc\n"})
        assert (result["files"][0]["added"], result["files"][0]["removed"]) == (2, 1)

    def test_nothing_changed_gives_an_empty_diff(self) -> None:
        result = cs.unified_diff({"f.py": "a\n"}, {"f.py": "a\n"})
        assert result["unified"] == "" and result["files"] == [] and result["skipped"] is None

    def test_the_diff_is_deterministic_and_independent_of_insertion_order(self) -> None:
        one = cs.unified_diff({"b.py": "1\n", "a.py": "1\n"}, {"b.py": "2\n", "a.py": "2\n"})
        two = cs.unified_diff({"a.py": "1\n", "b.py": "1\n"}, {"a.py": "2\n", "b.py": "2\n"})
        assert one == two

    @pytest.mark.skipif(shutil.which("patch") is None, reason="needs the patch program")
    @pytest.mark.parametrize("label", [
        "edit in the middle", "insert at the start", "insert at the end", "delete lines",
        "two hunks far apart", "no newline at the end, both sides", "newline added at the end",
        "newline removed at the end", "unicode", "tabs and trailing spaces", "file grows from empty",
    ])
    def test_the_real_patch_program_agrees(self, label: str, tmp_path: Path) -> None:
        """
        Cross-check against the tool the sandbox uses. Windows line endings are
        left out on purpose: patch rewrites them, which is the open question
        recorded in the README, and the strict applier above covers them.
        """
        before, after = CASES[label]
        target = tmp_path / "f.py"
        target.write_bytes(before.encode("utf-8"))
        diff_file = tmp_path / "forward.patch"
        diff_file.write_bytes(cs.unified_diff({"f.py": before}, {"f.py": after})["unified"].encode("utf-8"))
        run = subprocess.run(["patch", "--batch", "--no-backup-if-mismatch", "-p0", "-i", str(diff_file)],
                             cwd=tmp_path, capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        assert target.read_bytes() == after.encode("utf-8")

        back_file = tmp_path / "reverse.patch"
        back_file.write_bytes(cs.unified_diff({"f.py": after}, {"f.py": before})["unified"].encode("utf-8"))
        run = subprocess.run(["patch", "--batch", "--no-backup-if-mismatch", "-p0", "-i", str(back_file)],
                             cwd=tmp_path, capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        assert target.read_bytes() == before.encode("utf-8")


class TestBudget:

    def test_a_diff_within_the_budget_is_produced(self) -> None:
        base = {"f.py": "".join(f"{n}\n" for n in range(cs.MAX_DIFF_LINES // 2 - 5))}
        assert cs.unified_diff(base, {"f.py": base["f.py"] + "extra\n"})["unified"] is not None

    def test_past_the_budget_the_diff_is_skipped_with_a_reason(self) -> None:
        big = "".join(f"{n}\n" for n in range(cs.MAX_DIFF_LINES))
        result = cs.unified_diff({"f.py": big}, {"f.py": big + "extra\n"})
        assert result["unified"] is None
        assert result["skipped"]["reason"] == "too_large_to_diff"
        assert result["skipped"]["limit_lines"] == cs.MAX_DIFF_LINES

    def test_the_byte_budget_applies_too(self) -> None:
        wide = ("x" * 5000 + "\n") * 150
        result = cs.unified_diff({"f.py": wide}, {"f.py": wide + "extra\n"})
        assert result["skipped"] is not None and result["skipped"]["limit_bytes"] == cs.MAX_DIFF_BYTES

    def test_the_worst_case_inside_the_budget_stays_cheap(self) -> None:
        """
        Many line values each just under the 1 percent that difflib treats as
        noise is its quadratic case: 0.35 s at 20,000 lines when measured.
        """
        n = cs.MAX_DIFF_LINES // 2
        before = "".join(f"{i % 101}\n" for i in range(n))
        after = "".join(f"{(i + 3) % 101}\n" for i in range(n))
        started = time.perf_counter()
        result = cs.unified_diff({"f.py": before}, {"f.py": after})
        assert result["unified"] is not None
        assert time.perf_counter() - started < 5.0

    def test_refusing_an_oversized_diff_costs_almost_nothing(self) -> None:
        huge = "".join(f"{i % 101}\n" for i in range(cs.MAX_DIFF_LINES * 5))
        started = time.perf_counter()
        assert cs.unified_diff({"f.py": huge}, {"f.py": huge + "x\n"})["skipped"] is not None
        assert time.perf_counter() - started < 1.0, "the budget check must come before the expensive part"


# ==============================================================================
# The record
# ==============================================================================

def _manifest(base: dict[str, str], candidate: dict[str, str]) -> dict:
    to_list = lambda files: [{"path": p, "content": c} for p, c in files.items()]  # noqa: E731
    return source_manifest.build_manifest(to_list(base), to_list(candidate))


def _evidence(**overrides) -> dict:
    evidence = {"runner": "python-unittest", "python_version": "3.14", "status": "passed", "tests_run": 3,
                "source_sha256": "s" * 64, "output_sha256": "o" * 64, "runner_sha256": "r" * 64}
    evidence.update(overrides)
    return evidence


class TestBuildChangeset:

    def _build(self, base=None, candidate=None, **kwargs) -> dict:
        base = base if base is not None else {"demo.py": ORIGINAL, "keep.py": "k = 1\n"}
        candidate = candidate if candidate is not None else {"demo.py": PATCHED, "keep.py": "k = 1\n"}
        to_list = lambda files: [{"path": p, "content": c} for p, c in files.items()]  # noqa: E731
        kwargs.setdefault("state", cs.STATE_AWAITING)
        return cs.build_changeset(job_id="j1", base_files=to_list(base), candidate_files=to_list(candidate),
                                  manifest=_manifest(base, candidate), **kwargs)

    def test_it_carries_the_diff_its_inverse_and_the_hashes(self) -> None:
        record = self._build()
        assert record["diff"]["unified"] == cs.unified_diff({"demo.py": ORIGINAL}, {"demo.py": PATCHED})["unified"]
        assert record["diff"]["sha256"] == _sha(record["diff"]["unified"])
        assert record["reverse_diff"]["sha256"] == _sha(record["reverse_diff"]["unified"])
        assert (record["diff"]["lines_added"], record["diff"]["lines_removed"]) == (1, 1)

    def test_only_changed_files_are_listed_before_and_after(self) -> None:
        record = self._build()
        assert [e["path"] for e in record["before_after"]] == ["demo.py"]
        entry = record["before_after"][0]
        assert entry["before_sha256"] == _sha(ORIGINAL) and entry["after_sha256"] == _sha(PATCHED)

    def test_the_restore_target_is_the_original_bundle(self) -> None:
        record = self._build()
        backup = record["backup_manifest"]
        assert backup["restore_target_bundle_sha256"] == backup["base_bundle_sha256"]
        assert backup["candidate_bundle_sha256"] != backup["base_bundle_sha256"]
        assert backup["reverse_diff_sha256"] == record["reverse_diff"]["sha256"]

    def test_every_changed_file_says_how_to_restore_it(self) -> None:
        base = {"mod.py": "1\n", "gone.py": "g\n", "keep.py": "k\n"}
        candidate = {"mod.py": "2\n", "new.py": "n\n", "keep.py": "k\n"}
        by_path = {f["path"]: f for f in self._build(base, candidate)["backup_manifest"]["files"]}

        assert by_path["mod.py"]["restore"] == "apply_reverse_diff"
        assert by_path["new.py"]["restore"] == "delete_file" and by_path["new.py"]["restore_to_sha256"] is None
        assert by_path["gone.py"]["restore"] == "apply_reverse_diff", "the inverse of a deletion re-creates the file"
        assert "keep.py" not in by_path

    def test_the_inverse_of_a_deletion_recreates_the_file_exactly(self) -> None:
        base, candidate = {"gone.py": "g = 1\n"}, {}
        record = self._build(base, candidate)
        assert apply_diff(candidate, record["reverse_diff"]["unified"]) == base

    def test_a_skipped_diff_still_carries_the_hashes_and_says_the_restore_is_unavailable(self) -> None:
        big = "".join(f"{n}\n" for n in range(cs.MAX_DIFF_LINES))
        record = self._build({"big.py": big}, {"big.py": big + "x\n"})

        assert record["diff"]["unified"] is None and record["diff"]["skipped"]["reason"] == "too_large_to_diff"
        assert record["reverse_diff"]["sha256"] is None
        assert record["before_after"][0]["after_sha256"] == _sha(big + "x\n"), "a receiver can still verify a replacement"
        assert record["backup_manifest"]["files"][0]["restore"] == "unavailable_diff_skipped"

    def test_the_state_decides_whether_it_counts_as_approved(self) -> None:
        assert self._build(state=cs.STATE_AWAITING)["approved"] is False
        assert self._build(state=cs.STATE_COMPLETED)["approved"] is True

    def test_the_approval_record_and_provenance_are_passed_through(self) -> None:
        record = self._build(approval={"revision": 7}, model_patch_sha256="m" * 64)
        assert record["approval"] == {"revision": 7}
        assert record["provenance"]["model_patch_sha256"] == "m" * 64
        assert "not the model's diff" in record["provenance"]["diff_basis"]

    def test_the_test_evidence_is_summarised_not_copied(self) -> None:
        record = self._build(candidate_evidence=_evidence(extra_noise="x" * 1000))
        assert record["tests"]["candidate"]["tests_run"] == 3
        assert "extra_noise" not in record["tests"]["candidate"]
        assert record["tests"]["after_apply"] is None and record["tests"]["reproducible"] is None

    def test_after_the_apply_it_says_whether_the_evidence_reproduced(self) -> None:
        same = self._build(state=cs.STATE_COMPLETED, candidate_evidence=_evidence(), applied_evidence=_evidence())
        assert same["tests"]["reproducible"] is True
        different = self._build(state=cs.STATE_COMPLETED, candidate_evidence=_evidence(),
                                applied_evidence=_evidence(tests_run=4))
        assert different["tests"]["reproducible"] is False

    def test_the_procedure_is_part_of_the_record(self) -> None:
        procedure = self._build()["procedure"]
        assert set(procedure) == {"apply", "rollback"}
        assert any("before_sha256" in step for step in procedure["apply"])
        assert any("reverse_diff" in step for step in procedure["rollback"])

    def test_content_appears_only_inside_the_diffs(self) -> None:
        marker = "UNIQUE-UNTOUCHED-MARKER"
        record = self._build({"demo.py": ORIGINAL, "keep.py": f"{marker} = 1\n"},
                             {"demo.py": PATCHED, "keep.py": f"{marker} = 1\n"})
        assert marker not in json.dumps(record), "an untouched file's content must not travel"
        without_diffs = {k: v for k, v in record.items() if k not in {"diff", "reverse_diff"}}
        assert "return a" not in json.dumps(without_diffs), "outside the diffs there are only hashes and sizes"


class TestCheckState:
    """The reference checks a receiver runs, in the four places that matter."""

    def _record(self) -> dict:
        base = {"mod.py": "1\n", "gone.py": "g\n"}
        candidate = {"mod.py": "2\n", "new.py": "n\n"}
        to_list = lambda files: [{"path": p, "content": c} for p, c in files.items()]  # noqa: E731
        return cs.build_changeset(job_id="j", state=cs.STATE_AWAITING, base_files=to_list(base),
                                  candidate_files=to_list(candidate), manifest=_manifest(base, candidate))

    BEFORE = {"mod.py": "1\n", "gone.py": "g\n", "other.py": "untouched\n"}
    AFTER = {"mod.py": "2\n", "new.py": "n\n", "other.py": "untouched\n"}

    def test_the_live_tree_before_applying_is_clean(self) -> None:
        assert cs.check_state(self._record(), self.BEFORE, expect="before") == []

    def test_the_live_tree_after_applying_is_clean(self) -> None:
        assert cs.check_state(self._record(), self.AFTER, expect="after") == []

    def test_after_a_rollback_it_is_the_original_again(self) -> None:
        restored = apply_diff(self.AFTER, self._record()["reverse_diff"]["unified"])
        assert cs.check_state(self._record(), restored, expect="before") == []
        assert restored == self.BEFORE

    def test_the_whole_walk_through_apply_and_undo(self) -> None:
        record = self._record()
        live = dict(self.BEFORE)
        assert cs.check_state(record, live, expect="before") == []
        live = apply_diff(live, record["diff"]["unified"])
        assert cs.check_state(record, live, expect="after") == []
        live = apply_diff(live, record["reverse_diff"]["unified"])
        assert cs.check_state(record, live, expect="before") == []

    def test_a_file_edited_since_the_analysis_is_caught_before_applying(self) -> None:
        drifted = {**self.BEFORE, "mod.py": "1\n# someone edited this\n"}
        assert {"kind": "digest_mismatch", "path": "mod.py"} in cs.check_state(self._record(), drifted, expect="before")

    def test_a_file_that_should_not_exist_yet_is_caught(self) -> None:
        early = {**self.BEFORE, "new.py": "n\n"}
        assert {"kind": "unexpected_present", "path": "new.py"} in cs.check_state(self._record(), early, expect="before")

    def test_a_missing_file_is_caught(self) -> None:
        missing = {k: v for k, v in self.BEFORE.items() if k != "gone.py"}
        assert {"kind": "missing", "path": "gone.py"} in cs.check_state(self._record(), missing, expect="before")

    def test_a_deletion_that_did_not_happen_is_caught_after_applying(self) -> None:
        not_deleted = {**self.AFTER, "gone.py": "g\n"}
        # gone.py is expected absent after the apply
        assert {"kind": "unexpected_present", "path": "gone.py"} in cs.check_state(self._record(), not_deleted, expect="after")

    def test_a_tampered_result_is_caught_after_applying(self) -> None:
        tampered = {**self.AFTER, "mod.py": "2\n# injected\n"}
        assert {"kind": "digest_mismatch", "path": "mod.py"} in cs.check_state(self._record(), tampered, expect="after")

    def test_files_the_changeset_does_not_mention_are_not_looked_at(self) -> None:
        assert cs.check_state(self._record(), {**self.BEFORE, "other.py": "anything\n"}, expect="before") == []

    def test_a_list_of_entries_is_accepted_as_well_as_a_mapping(self) -> None:
        as_list = [{"path": p, "content": c} for p, c in self.BEFORE.items()]
        assert cs.check_state(self._record(), as_list, expect="before") == []

    def test_an_unknown_side_is_refused(self) -> None:
        with pytest.raises(ValueError):
            cs.check_state(self._record(), {}, expect="during")


# ==============================================================================
# In the orchestrator
# ==============================================================================

_EVIDENCE = {
    "schema_version": 1, "runner": "python-unittest", "python_version": "3.14", "runner_sha256": "r" * 64,
    "command": ["python", "-m", "unittest"], "source_sha256": "s" * 64, "test_files": [],
    "tests_run": 0, "status": "not_run", "output_sha256": None, "log_artifact": None,
}


class TestOrchestrator:

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
        self.client = TestClient(main.app)

    def _stage(self) -> tuple[str, Path]:
        job_id = main.stage_job(main.CreateJobRequest(
            task="Fix add", repository="t", files=[main.JobFile(path="demo.py", content=ORIGINAL)]))
        job = main.job_dir(job_id)
        (job / "model.patch").write_text(MODEL_DIFF, encoding="utf-8", newline="\n")
        return job_id, job

    def _worker(self, job: Path, *, delivered: str = PATCHED):
        def worker(jid: str, phase: str, deadline: float) -> dict:
            content = ORIGINAL if phase == "preflight" else (PATCHED if phase == "test_patch" else delivered)
            result = {"job_id": jid, "phase": phase,
                      "patch_result": None if phase == "preflight" else {"returncode": 0, "stdout": "", "stderr": ""},
                      "postflight_python_syntax": [], "files": [{"path": "demo.py", "content": content}],
                      "test_evidence": None if phase == "preflight" else dict(_EVIDENCE)}
            main.write_json(job / f"{phase}_result.json", result)
            return result
        return worker

    def _to_approval(self, **worker_kwargs) -> tuple[str, dict]:
        job_id, job = self._stage()
        self.monkeypatch.setattr(main, "run_worker_phase", self._worker(job, **worker_kwargs))
        main.run_preapproval(job_id)
        awaiting = main.read_status(job_id)
        assert awaiting["status"] == "awaiting_approval"
        return job_id, awaiting

    def _approve_and_finish(self, job_id: str, awaiting: dict) -> dict:
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        main.run_approved(job_id)
        return main.read_status(job_id)

    # --- the approval is bound to content --------------------------------------

    def test_the_approval_records_what_was_approved_not_only_the_revision(self) -> None:
        job_id, awaiting = self._to_approval()
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        approval = main.read_status(job_id)["approval"]

        manifest = awaiting["result"]["manifest"]
        assert approval["revision"] == awaiting["revision"]
        assert approval["candidate_bundle_sha256"] == manifest["candidate_bundle_sha256"]
        assert approval["base_bundle_sha256"] == manifest["base_bundle_sha256"]

    def test_a_faithful_run_still_completes(self) -> None:
        job_id, awaiting = self._to_approval()
        final = self._approve_and_finish(job_id, awaiting)
        assert final["status"] == "completed"

    def test_files_that_differ_from_what_was_approved_are_not_delivered(self) -> None:
        """
        A worker that reports consistent evidence but hands back other files.
        Before this check such a job completed, delivering content the approver
        never saw.
        """
        forged = "def add(a, b):\n    import os\n    return a + b\n"
        job_id, awaiting = self._to_approval(delivered=forged)
        final = self._approve_and_finish(job_id, awaiting)

        assert final["status"] == "rolled_back"
        assert final["error_code"] == "FLARE-501"
        assert "differ from the candidate that was approved" in final["error"]
        assert forged not in json.dumps(final.get("result", {}))

    def test_a_job_approved_before_this_existed_is_not_failed_by_it(self) -> None:
        """An in-flight job has no digests in its approval; the check must not strand it."""
        job_id, awaiting = self._to_approval()
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        status = main.read_status(job_id)
        legacy = {k: v for k, v in status["approval"].items() if not k.endswith("_sha256")}
        main.write_status(job_id, status["status"], approval=legacy)

        main.run_approved(job_id)
        assert main.read_status(job_id)["status"] == "completed"

    # --- the endpoint ------------------------------------------------------------

    def test_an_approver_can_review_a_diff_while_the_candidate_waits(self) -> None:
        job_id, _ = self._to_approval()
        body = self.client.get(f"/jobs/{job_id}/changeset").json()

        assert body["state"] == "awaiting_approval" and body["approved"] is False
        assert apply_diff({"demo.py": ORIGINAL}, body["diff"]["unified"]) == {"demo.py": PATCHED}
        assert body["tests"]["candidate"]["status"] == "not_run"

    def test_after_completion_it_names_the_approval_and_the_reproduced_tests(self) -> None:
        job_id, awaiting = self._to_approval()
        self._approve_and_finish(job_id, awaiting)
        body = self.client.get(f"/jobs/{job_id}/changeset").json()

        assert body["state"] == "completed" and body["approved"] is True
        assert body["approval"]["candidate_bundle_sha256"] == body["backup_manifest"]["candidate_bundle_sha256"]
        assert body["tests"]["reproducible"] is True
        assert body["tests"]["after_apply"]["runner"] == "python-unittest"

    def test_the_whole_apply_and_undo_cycle_works_from_the_endpoint_alone(self) -> None:
        job_id, awaiting = self._to_approval()
        self._approve_and_finish(job_id, awaiting)
        record = self.client.get(f"/jobs/{job_id}/changeset").json()

        live = {"demo.py": ORIGINAL}
        assert cs.check_state(record, live, expect="before") == []
        live = apply_diff(live, record["diff"]["unified"])
        assert cs.check_state(record, live, expect="after") == []
        live = apply_diff(live, record["reverse_diff"]["unified"])
        assert live == {"demo.py": ORIGINAL}
        assert cs.check_state(record, live, expect="before") == []

    def test_the_diff_is_computed_from_the_submitted_input_and_names_the_models_diff_by_hash(self) -> None:
        job_id, _ = self._to_approval()
        body = self.client.get(f"/jobs/{job_id}/changeset").json()
        assert body["provenance"]["model_patch_sha256"] == _sha(MODEL_DIFF)
        assert body["before_after"][0]["before_sha256"] == _sha(ORIGINAL)

    def test_it_is_not_available_before_there_is_a_candidate(self) -> None:
        job_id, _ = self._stage()
        response = self.client.get(f"/jobs/{job_id}/changeset")
        assert response.status_code == 409

    def test_it_is_not_available_for_a_rolled_back_job(self) -> None:
        job_id, awaiting = self._to_approval(delivered="def add(a, b):\n    return 0\n")
        assert self._approve_and_finish(job_id, awaiting)["status"] == "rolled_back"
        assert self.client.get(f"/jobs/{job_id}/changeset").status_code == 409

    def test_an_unknown_job_is_a_404(self) -> None:
        assert self.client.get(f"/jobs/{'a' * 32}/changeset").status_code in {404, 409}

    def test_authentication_applies(self) -> None:
        job_id, _ = self._to_approval()
        token = "changeset-" + "test-" + "token"
        self.monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", token)
        assert self.client.get(f"/jobs/{job_id}/changeset").status_code == 401
        ok = self.client.get(f"/jobs/{job_id}/changeset", headers={"Authorization": "Bearer " + token})
        assert ok.status_code == 200

    def test_it_is_sealed_when_transport_encryption_is_on(self) -> None:
        job_id, _ = self._to_approval()
        self.monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "changeset-transport-key")
        response = self.client.get(f"/jobs/{job_id}/changeset")
        assert response.json().get("encrypted") is True
        assert main.open_json(response.json())["job_id"] == job_id

    def test_an_unreadable_staged_input_is_a_structured_error_not_a_guess(self) -> None:
        job_id, _ = self._to_approval()
        (main.job_dir(job_id) / "request.json").unlink()
        response = self.client.get(f"/jobs/{job_id}/changeset")
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "FLARE-801"
