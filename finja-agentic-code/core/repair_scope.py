"""
======================================================================
      Flare (Finja Agentic Code) – L2 Repair Scope (diff review)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    - Keeps the L2 validity bound separate from L5's manual-only routing.

----------------------------------------------------------------------

  L2 is Flare's hands: it drafts a repair diff and stops there. The
  stopping was already true -- a candidate is only ever applied inside a
  disposable worker, and the real apply waits for a revision-bound
  approval. What was missing is the other half of the promise.

  "Keep changes minimal" used to live only as a sentence in the model
  prompt, with nothing measuring it: a five-hundred-line rewrite across
  every file would have sailed through to the sandbox. This module turns
  that sentence into a reviewed bound, between the model call and the
  test phase, so an over-reaching candidate is refused before any worker
  touches it.

  Three levels of strictness, on purpose:

    * Paths are HARD. A diff may only touch files that came in the
      payload, plus new files inside it. GNU patch happens to refuse
      `..` and absolute targets today, but that is a property of the
      binary, not a promise Flare makes -- so Flare makes it here.
    * Size is POLICY. The limits are deliberately env-tunable: they
      encode what counts as "minimal" for this deployment, not a law of
      nature.
    * Evidence is REPORTED, never enforced. A legitimate fix may well
      touch a file L1 had no finding for, so pointing that out helps a
      reviewer while refusing it would just block honest repairs.

  Pure logic: no FastAPI, no filesystem, no network. Everything it needs
  arrives as arguments so it can be tested directly.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import re
from pathlib import Path

from core.exceptions import RepairPatchRejectedError, RepairPatchTooLargeError

SCHEMA_VERSION = 1

DEV_NULL = "/dev/null"
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")
CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".css",
    ".html", ".yml", ".yaml", ".toml", ".txt",
})
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

KIND_MODIFY = "modify"
KIND_CREATE = "create"
KIND_DELETE = "delete"

VIOLATION_MALFORMED = "malformed"
VIOLATION_UNSAFE_PATH = "unsafe_path"
VIOLATION_UNKNOWN_PATH = "unknown_path"
VIOLATION_PREFIXED_PATH = "prefixed_path"
VIOLATION_TOO_MANY_FILES = "too_many_files"
VIOLATION_TOO_MANY_LINES = "too_many_lines"

# Violations that mean "this diff is not usable", as opposed to
# "this diff is bigger than policy allows".
REJECT_VIOLATIONS = frozenset({
    VIOLATION_MALFORMED, VIOLATION_UNSAFE_PATH,
    VIOLATION_UNKNOWN_PATH, VIOLATION_PREFIXED_PATH,
})


def _header_path(line: str, marker: str) -> str:
    """Strip the marker and the optional trailing timestamp of a diff header."""
    raw = line[len(marker):].strip()
    return raw.split("\t")[0].strip()


def path_is_safe(path: str) -> bool:
    """
    Same rule as the orchestrator's payload path validation, restated for
    diff targets. test_repair_scope.py cross-checks the two against one
    shared table so they cannot drift apart.
    """
    if not path or "\\" in path or path.startswith("/") or path.startswith("."):
        return False
    if not SAFE_PATH_RE.fullmatch(path):
        return False
    return not any(part in {".", ".."} for part in path.split("/")) \
        and Path(path).suffix.lower() in CODE_EXTENSIONS


def _parse_unified_diff(diff: str) -> list[dict]:
    """Parse the complete patch, including every hunk and its declared size."""
    changes: list[dict] = []
    lines = diff.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- ") or index + 1 >= len(lines) \
                or not lines[index + 1].startswith("+++ "):
            raise ValueError("Patch contains text outside a unified-diff file section")
        old_path = _header_path(lines[index], "--- ")
        new_path = _header_path(lines[index + 1], "+++ ")
        if old_path == DEV_NULL and new_path == DEV_NULL:
            raise ValueError("Patch section has no target file")
        if new_path == DEV_NULL:
            kind, path = KIND_DELETE, old_path
        elif old_path == DEV_NULL:
            kind, path = KIND_CREATE, new_path
        else:
            kind, path = KIND_MODIFY, new_path
        current = {
            "path": path, "old_path": old_path, "new_path": new_path,
            "kind": kind, "added": 0, "removed": 0, "hunks": [],
        }
        index += 2
        if index >= len(lines) or not HUNK_RE.match(lines[index]):
            raise ValueError("Patch section has no valid hunk")
        while index < len(lines) and lines[index].startswith("@@ "):
            match = HUNK_RE.match(lines[index])
            if match is None:
                raise ValueError("Patch contains an invalid hunk header")
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            current["hunks"].append({
                    "old_start": old_start,
                    "old_end": old_start + max(old_count, 1) - 1,
            })
            index += 1
            old_seen = new_seen = 0
            while old_seen < old_count or new_seen < new_count:
                if index >= len(lines):
                    raise ValueError("Patch hunk ends before its declared line counts")
                prefix = lines[index][:1]
                if prefix == " ":
                    old_seen += 1
                    new_seen += 1
                elif prefix == "-":
                    old_seen += 1
                    current["removed"] += 1
                elif prefix == "+":
                    new_seen += 1
                    current["added"] += 1
                else:
                    raise ValueError("Patch hunk contains an invalid line")
                if old_seen > old_count or new_seen > new_count:
                    raise ValueError("Patch hunk exceeds its declared line counts")
                index += 1
            if index < len(lines) and lines[index] == r"\ No newline at end of file":
                index += 1
        changes.append(current)
        if index < len(lines) and not lines[index].startswith("--- "):
            raise ValueError("Patch contains text after a completed hunk")
    return changes


def parse_unified_diff(diff: str) -> list[dict]:
    """Return complete file changes, or no changes for an unusable diff."""
    try:
        return _parse_unified_diff(diff)
    except ValueError:
        return []


def _evidence_for(change: dict, findings: list[dict]) -> dict:
    """Which L1 findings does this file change actually sit on top of?"""
    file_findings = [
        finding for finding in findings
        if finding.get("path") == change["path"] or finding.get("path") == change["old_path"]
    ]
    addressed = []
    for finding in file_findings:
        line = finding.get("line")
        if not isinstance(line, int):
            continue
        for hunk in change["hunks"]:
            if hunk["old_start"] <= line <= hunk["old_end"]:
                addressed.append({"check": finding.get("check"), "line": line})
                break
    return {
        "findings_on_file": len(file_findings),
        "findings_inside_hunks": addressed,
    }


def review_repair_patch(diff: str, *, payload_paths: frozenset[str],
                        diagnosis: dict | None = None,
                        max_files: int = 5, max_lines: int = 200) -> dict:
    """Review a candidate diff without applying anything. Returns the L2 report."""
    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "applied": False,
        "files": [],
        "files_touched": 0,
        "lines_changed": 0,
        "limits": {"max_files": max_files, "max_lines": max_lines},
        "violations": [],
        "files_without_evidence": [],
        "findings_addressed": 0,
        "verdict": "clean",
    }
    if not diff.strip():
        report["verdict"] = "empty"
        return report

    try:
        changes = _parse_unified_diff(diff)
    except ValueError as exc:
        report["violations"].append({
            "kind": VIOLATION_MALFORMED,
            "detail": str(exc),
        })
        report["verdict"] = "rejected"
        return report

    findings = (diagnosis or {}).get("findings", []) or []
    lines_changed = 0

    seen_paths: set[str] = set()
    for change in changes:
        path = change["path"]
        entry = {
            "path": path,
            "kind": change["kind"],
            "added": change["added"],
            "removed": change["removed"],
            "hunks": len(change["hunks"]),
        }
        lines_changed += change["added"] + change["removed"]

        for header_path in (change["old_path"], change["new_path"]):
            if header_path == DEV_NULL:
                continue
            if not path_is_safe(header_path):
                report["violations"].append({
                    "kind": VIOLATION_UNSAFE_PATH, "path": header_path,
                    "detail": "Diff header contains an unsafe relative path",
                })
            elif header_path.split("/")[0] in {"a", "b"} and header_path not in payload_paths:
                report["violations"].append({
                    "kind": VIOLATION_PREFIXED_PATH, "path": header_path,
                    "detail": "Diff uses a git-style path prefix with patch -p0",
                })
        if change["kind"] == KIND_MODIFY and change["old_path"] != change["new_path"]:
            report["violations"].append({
                "kind": VIOLATION_MALFORMED, "path": path,
                "detail": "A file modification must use the same old and new path",
            })
        if path in seen_paths:
            report["violations"].append({
                "kind": VIOLATION_MALFORMED, "path": path,
                "detail": "Patch repeats a file section",
            })
        seen_paths.add(path)

        if not path_is_safe(path):
            # A git-style a/ b/ pair is safe but still wrong under -p0, so it
            # gets its own violation: the operator needs to know the model used
            # the wrong prefix convention, not that it attacked the sandbox.
            kind = VIOLATION_PREFIXED_PATH if path.split("/")[0] in {"a", "b"} \
                else VIOLATION_UNSAFE_PATH
            report["violations"].append({
                "kind": kind, "path": path,
                "detail": "Diff target is not a safe relative path inside the payload",
            })
        elif path.split("/")[0] in {"a", "b"} and path not in payload_paths:
            report["violations"].append({
                "kind": VIOLATION_PREFIXED_PATH, "path": path,
                "detail": "Diff uses git-style a/ and b/ prefixes, which cannot apply with patch -p0",
            })
        elif change["kind"] != KIND_CREATE and path not in payload_paths:
            report["violations"].append({
                "kind": VIOLATION_UNKNOWN_PATH, "path": path,
                "detail": "Diff modifies a file that was not part of the submitted payload",
            })

        evidence = _evidence_for(change, findings)
        entry.update(evidence)
        report["findings_addressed"] += len(evidence["findings_inside_hunks"])
        if evidence["findings_on_file"] == 0:
            report["files_without_evidence"].append(path)
        report["files"].append(entry)

    report["files_touched"] = len(changes)
    report["lines_changed"] = lines_changed

    if len(changes) > max_files:
        report["violations"].append({
            "kind": VIOLATION_TOO_MANY_FILES,
            "detail": f"Diff touches {len(changes)} files; the repair scope allows {max_files}",
        })
    if lines_changed > max_lines:
        report["violations"].append({
            "kind": VIOLATION_TOO_MANY_LINES,
            "detail": f"Diff changes {lines_changed} lines; the repair scope allows {max_lines}",
        })

    kinds = {violation["kind"] for violation in report["violations"]}
    if kinds & REJECT_VIOLATIONS:
        report["verdict"] = "rejected"
    elif kinds:
        report["verdict"] = "too_large"
    return report


def enforce(report: dict) -> None:
    """Turn a failed review into the structured code Finja shows the user."""
    verdict = report.get("verdict")
    if verdict not in {"rejected", "too_large"}:
        return
    details = "; ".join(
        violation.get("detail", violation.get("kind", "?"))
        for violation in report.get("violations", [])
    )
    if verdict == "rejected":
        raise RepairPatchRejectedError(f"Repair diff was refused: {details}")
    raise RepairPatchTooLargeError(f"Repair diff exceeds the allowed scope: {details}")
