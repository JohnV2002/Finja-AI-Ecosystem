"""
======================================================================
      Flare (Finja Agentic Code) – Changeset, Diff and Backup Manifest
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Everything a receiver needs to apply a candidate, check it,
               and undo it, as one verifiable record.

  New in v1.11.0:
    - First version: the unified diff, its exact inverse, before/after hashes
      and the test evidence travel together, with checks a receiver can run.

----------------------------------------------------------------------

  Who applies what. Flare never writes to Finja's tree, by design: the
  "applying" state of a job is the sandbox applying the approved diff to its
  own copy, to verify it. The change reaches production only when Finja
  applies it. So the rollback story for production cannot live in Flare. What
  Flare can do is hand over a record that makes Finja's apply safe and
  reversible, and that is what this is:

    * the unified diff of the change, so an approver reviews a diff and not a
      pile of whole files (until now only the manual route exposed one);
    * its exact inverse, so the change can be undone byte for byte;
    * before and after hashes for every changed file;
    * the test evidence for the candidate and, once finished, for the result
      after the apply;
    * a backup manifest: what the live files must hash to before applying,
      what they must hash to afterwards, and what they must hash to again
      after a rollback.

  Where the diff comes from. It is computed from the submitted input and the
  candidate, not copied from the model's diff. A model's hunk headers are
  often only approximately right and rely on patch searching for the spot;
  the difference between two known texts has exact line numbers and applies
  strictly. The model's own diff is tied in by its hash, as provenance.
  The inverse is the same computation with the two sides swapped, not a text
  transformation, so it is exact by construction.

  What it costs. difflib is quadratic in the worst case. Measured on a
  throwaway stack, a file of 100 lines repeated with a small shift costs 0.35 s
  at 20,000 lines and grows with the square. So the diff is only produced
  within a budget of 20,000 lines in total; past it the changeset says so and
  still carries the hashes, which is all a receiver needs to verify a
  replacement. Files with huge numbers of identical lines get a valid but
  larger-than-minimal diff, which is difflib's own trade-off.

  The checks at the bottom are the reference for a receiver: compare the live
  files against the hashes before applying, after applying, before a rollback
  and after one. Flare cannot run them, since it never sees the live files.

  Pure logic. No filesystem, no network.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import difflib
import hashlib
from collections.abc import Iterable, Mapping

SCHEMA_VERSION = 1
DIFF_FORMAT = "unified, paths without prefix (patch -p0)"
DEV_NULL = "/dev/null"
CONTEXT_LINES = 3
MAX_DIFF_LINES = 20_000
MAX_DIFF_BYTES = 1_000_000
NO_NEWLINE_MARKER = "\\ No newline at end of file\n"

STATE_AWAITING = "awaiting_approval"
STATE_COMPLETED = "completed"

PROCEDURE = {
    "apply": [
        "Hash each live file. Every changed file must hash to its before_sha256 (a file Flare "
        "created must not exist yet). If any differs, the file changed after it was analysed: stop.",
        "Apply diff.unified, or write the delivered content. Write to a temporary file and replace "
        "atomically; never edit in place.",
        "Hash each live file again. Every changed file must hash to its after_sha256 "
        "(a file Flare deleted must be gone). If any differs, roll back at once.",
    ],
    "rollback": [
        "Hash each live file. Every changed file must still hash to its after_sha256. If one "
        "differs, someone changed it since: do not roll back blindly.",
        "Apply reverse_diff.unified.",
        "Hash each live file. Every changed file must hash to its before_sha256 again "
        "(a file Flare created must be gone).",
    ],
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lines(text: str) -> list[str]:
    """
    Split on "\\n" only, keeping it. str.splitlines also splits on form feeds,
    vertical tabs and Unicode separators that patch does not treat as line
    breaks, which would make a diff disagree with the tool applying it. A
    carriage return stays on its line, so CRLF files diff and apply as they are.
    """
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _file_diff(path: str, before: str | None, after: str | None) -> tuple[str, int, int, int]:
    """Unified diff of one file with its counts: (text, added, removed, hunks)."""
    old = _lines(before) if before is not None else []
    new = _lines(after) if after is not None else []
    stream = difflib.unified_diff(
        old, new,
        path if before is not None else DEV_NULL,
        path if after is not None else DEV_NULL,
        n=CONTEXT_LINES,
    )
    out: list[str] = []
    added = removed = hunks = 0
    for index, line in enumerate(stream):
        if index < 2 or line.startswith("@@"):
            out.append(line if line.endswith("\n") else line + "\n")
            hunks += 1 if line.startswith("@@") else 0
            continue
        # A final line without its newline would run into the next one. The
        # marker is how unified diffs say "this line has no line break".
        out.append(line if line.endswith("\n") else line + "\n" + NO_NEWLINE_MARKER)
        if line[0] == "+":
            added += 1
        elif line[0] == "-":
            removed += 1
    return "".join(out), added, removed, hunks


def _index(files: Iterable[object] | None) -> dict[str, str]:
    entries: dict[str, str] = {}
    if not isinstance(files, (list, tuple)):
        return entries
    for entry in files:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) \
                and isinstance(entry.get("content"), str):
            entries[entry["path"]] = entry["content"]
    return entries


def unified_diff(base: Mapping[str, str], candidate: Mapping[str, str]) -> dict:
    """
    The unified diff that turns `base` into `candidate`, for every file that
    differs, in path order. Within the line budget only.
    """
    changed = [path for path in sorted(set(base) | set(candidate)) if base.get(path) != candidate.get(path)]
    lines = sum(len(_lines(base[p])) for p in changed if p in base) \
        + sum(len(_lines(candidate[p])) for p in changed if p in candidate)
    size = sum(len(base[p]) for p in changed if p in base) + sum(len(candidate[p]) for p in changed if p in candidate)
    if lines > MAX_DIFF_LINES or size > MAX_DIFF_BYTES:
        return {"unified": None, "files": [], "skipped": {
            "reason": "too_large_to_diff", "lines": lines, "bytes": size,
            "limit_lines": MAX_DIFF_LINES, "limit_bytes": MAX_DIFF_BYTES,
        }}

    parts: list[str] = []
    stats: list[dict] = []
    for path in changed:
        text, added, removed, hunks = _file_diff(path, base.get(path), candidate.get(path))
        parts.append(text)
        stats.append({"path": path, "added": added, "removed": removed, "hunks": hunks,
                      # An empty file created or deleted has no hunk to carry it.
                      "carried": bool(text)})
    return {"unified": "".join(parts), "files": stats, "skipped": None}


def _diff_block(base: Mapping[str, str], candidate: Mapping[str, str]) -> dict:
    result = unified_diff(base, candidate)
    text = result["unified"]
    return {
        "format": DIFF_FORMAT,
        "unified": text,
        "sha256": _sha(text) if text is not None else None,
        "bytes": len(text.encode("utf-8")) if text is not None else None,
        "files": result["files"],
        "lines_added": sum(f["added"] for f in result["files"]),
        "lines_removed": sum(f["removed"] for f in result["files"]),
        "skipped": result["skipped"],
    }


def _evidence_summary(evidence: object) -> dict | None:
    if not isinstance(evidence, dict):
        return None
    keys = ("runner", "python_version", "status", "tests_run", "source_sha256", "output_sha256", "runner_sha256")
    return {key: evidence.get(key) for key in keys}


def build_changeset(*, job_id: str, state: str, base_files: Iterable[object] | None,
                    candidate_files: Iterable[object] | None, manifest: Mapping,
                    candidate_evidence: object = None, applied_evidence: object = None,
                    approval: Mapping | None = None, model_patch_sha256: str | None = None) -> dict:
    """
    Assemble the record. `manifest` is the per-file hash manifest of the job
    result, so the hashes here and there are one set of numbers.
    """
    base = _index(base_files)
    candidate = _index(candidate_files)
    forward = _diff_block(base, candidate)
    inverse = _diff_block(candidate, base)

    before_after = []
    for entry in manifest.get("files", []):
        if entry.get("status") == "unchanged":
            continue
        before_after.append({
            "path": entry["path"], "status": entry["status"],
            "before_sha256": entry.get("base_sha256"), "after_sha256": entry.get("candidate_sha256"),
            "before_bytes": entry.get("base_bytes"), "after_bytes": entry.get("candidate_bytes"),
        })

    restorable = forward["unified"] is not None
    backup_files = [{
        "path": entry["path"],
        "currently_expected_sha256": entry["after_sha256"],
        "restore_to_sha256": entry["before_sha256"],
        "restore": ("delete_file" if entry["before_sha256"] is None else "apply_reverse_diff")
        if restorable else "unavailable_diff_skipped",
    } for entry in before_after]

    reproducible = None
    if applied_evidence is not None and candidate_evidence is not None:
        reproducible = _evidence_summary(candidate_evidence) == _evidence_summary(applied_evidence)

    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "state": state,
        "approved": state == STATE_COMPLETED,
        "approval": dict(approval) if approval else None,
        "diff": forward,
        "reverse_diff": inverse,
        "before_after": before_after,
        "tests": {
            "candidate": _evidence_summary(candidate_evidence),
            "after_apply": _evidence_summary(applied_evidence),
            "reproducible": reproducible,
        },
        "backup_manifest": {
            "schema_version": SCHEMA_VERSION,
            "base_bundle_sha256": manifest.get("base_bundle_sha256"),
            "restore_target_bundle_sha256": manifest.get("base_bundle_sha256"),
            "candidate_bundle_sha256": manifest.get("candidate_bundle_sha256"),
            "reverse_diff_sha256": inverse["sha256"],
            "files": backup_files,
        },
        "procedure": PROCEDURE,
        "provenance": {
            "diff_basis": "difference between the submitted input and the candidate, not the model's diff",
            "model_patch_sha256": model_patch_sha256,
        },
    }


def _live_index(live_files: Iterable[object] | Mapping[str, str] | None) -> dict[str, str]:
    if isinstance(live_files, Mapping):
        return {str(path): content for path, content in live_files.items() if isinstance(content, str)}
    return _index(live_files)


def check_state(changeset: Mapping, live_files: Iterable[object] | Mapping[str, str] | None,
                *, expect: str) -> list[dict]:
    """
    Compare the live files with one side of the changeset. Returns the problems,
    an empty list meaning every changed file is exactly where it should be.

    expect="before"  before applying, and after a rollback
    expect="after"   after applying, and before a rollback

    A file whose expected hash is None must be absent. Files the changeset does
    not mention are not looked at: this is about the change, not the tree.
    """
    if expect not in {"before", "after"}:
        raise ValueError("expect must be 'before' or 'after'")
    key = f"{expect}_sha256"
    live = _live_index(live_files)
    problems: list[dict] = []
    for entry in changeset.get("before_after", []):
        path, wanted = entry["path"], entry.get(key)
        if wanted is None:
            if path in live:
                problems.append({"kind": "unexpected_present", "path": path})
        elif path not in live:
            problems.append({"kind": "missing", "path": path})
        elif _sha(live[path]) != wanted:
            problems.append({"kind": "digest_mismatch", "path": path})
    return problems
