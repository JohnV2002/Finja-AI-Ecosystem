"""
======================================================================
      Flare (Finja Agentic Code) – Source Manifest and Minimality
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: SHA-256 identity for the source Flare handles, and a
               measurement of how little of it was needed.

  New in v1.11.0:
    - First version: every result names the exact bytes it is about, and an
      incident reports how much of what it carried was actually relevant.

----------------------------------------------------------------------

  What already existed, so this is not mistaken for the first hash: the
  incident envelope verifies a SHA-256 for every file it carries, and the
  sandbox compares a digest of the whole workspace before approval and after
  the apply, so a diff or an input swapped in between is already caught
  (FLARE-501, "Approved candidate differed from its sandbox test evidence").
  Both were checked by experiment before this was written.

  What was missing is on the way OUT. A result handed back to Finja carried
  `path` and `content` and nothing that said which input a candidate came
  from. Two things follow from a hash that names it:

    * Finja can refuse to apply a candidate to a file that is no longer the
      one that was analysed. Flare cannot do this check: it never sees the
      live file, by design. It can only state, exactly, which bytes it
      started from (`base_sha256`) so the owner of the live file can compare.
    * An approver is shown what actually changes (modified, created,
      deleted, lines added and removed) instead of a block of content.

  Hashes are over the UTF-8 content exactly as it was transmitted. When the
  sender redacted before sending, they identify the redacted copy, and the
  envelope says so: `sha256` there is "computed over the UTF-8 content AFTER
  redaction". A hash of the unredacted original is not Flare's to know.

  The second half measures minimality. Flare cannot fetch a file by hash,
  since it has no access to Finja's tree, and an envelope that carries only
  an excerpt is a wire-contract change (v2, since v1 is strict). What it can
  do inside v1 is say how much of what it was sent no stack frame points at,
  so the sender can see its own excess. This reports and never refuses: a
  repair may legitimately need a helper that is on no stack.

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

import hashlib
from collections.abc import Iterable, Mapping

from core.incident_envelope import MAX_TOTAL_SOURCE_BYTES, IncidentEnvelope

SCHEMA_VERSION = 1
ALGORITHM = "sha256"
HASHED_OVER = "UTF-8 content exactly as transmitted"

STATUS_UNCHANGED = "unchanged"
STATUS_MODIFIED = "modified"
STATUS_LINE_ENDINGS = "line_endings_only"
STATUS_CREATED = "created"
STATUS_DELETED = "deleted"
STATUS_UNKNOWN = "unknown"

MAX_FRAME_LINES_LISTED = 8


def file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def bundle_sha256(digests: Mapping[str, str]) -> str:
    """
    One digest for a set of files, from their paths and their own digests.

    Sorted by path, so the order a sender listed them in does not matter, and
    length-prefixed, so ("a", "bc") and ("ab", "c") cannot collide.
    """
    outer = hashlib.sha256()
    for path in sorted(digests):
        raw_path = path.encode("utf-8")
        outer.update(len(raw_path).to_bytes(4, "big"))
        outer.update(raw_path)
        outer.update(bytes.fromhex(digests[path]))
    return outer.hexdigest()


def _index(files: Iterable[object] | None) -> dict[str, str]:
    """path -> content for well-formed entries; anything else is skipped, not guessed at."""
    entries: dict[str, str] = {}
    # A result written by a broken worker may hold anything under `files`. The
    # manifest is information about a job, so it must never be the thing that
    # fails one: only a real list is read, everything else is an empty input.
    if not isinstance(files, (list, tuple)):
        return entries
    for entry in files:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) \
                and isinstance(entry.get("content"), str):
            entries[entry["path"]] = entry["content"]
    return entries


def _line_stats(repair_report: object) -> dict[str, tuple[int, int]]:
    """Added and removed lines per file, from the L2 review that already counted them."""
    stats: dict[str, tuple[int, int]] = {}
    entries = repair_report.get("files") if isinstance(repair_report, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            stats[entry["path"]] = (int(entry.get("added") or 0), int(entry.get("removed") or 0))
    return stats


def build_manifest(base_files: Iterable[object] | None, candidate_files: Iterable[object] | None,
                   *, repair_report: object = None) -> dict:
    """
    Describe a candidate against the input it was made from.

    Line counts are taken from the review that already parsed the diff, not
    recomputed here: a diff of two 300,000-character files is not something
    to run on a request path.
    """
    # None means "the input is not available", which is different from an
    # empty input. Treating a missing base as empty would call every file
    # "created", a confident statement about something that was never checked.
    base_known = isinstance(base_files, (list, tuple))
    base = _index(base_files)
    candidate = _index(candidate_files)
    lines = _line_stats(repair_report)

    entries: list[dict] = []
    counts = {STATUS_UNCHANGED: 0, STATUS_MODIFIED: 0, STATUS_LINE_ENDINGS: 0,
              STATUS_CREATED: 0, STATUS_DELETED: 0, STATUS_UNKNOWN: 0}
    for path in sorted(set(base) | set(candidate)):
        before, after = base.get(path), candidate.get(path)
        if not base_known:
            status = STATUS_UNKNOWN
        elif before is None:
            status = STATUS_CREATED
        elif after is None:
            status = STATUS_DELETED
        elif before == after:
            status = STATUS_UNCHANGED
        elif before.replace("\r\n", "\n") == after.replace("\r\n", "\n"):
            # Identical but for line endings. Reported as its own status so a
            # receiver can tell a whole-file rewrite from an edit and decline
            # to apply the former.
            status = STATUS_LINE_ENDINGS
        else:
            status = STATUS_MODIFIED
        counts[status] += 1
        entry = {
            "path": path,
            "status": status,
            "base_sha256": file_sha256(before) if before is not None else None,
            "candidate_sha256": file_sha256(after) if after is not None else None,
            "base_bytes": len(before.encode("utf-8")) if before is not None else None,
            "candidate_bytes": len(after.encode("utf-8")) if after is not None else None,
        }
        if path in lines:
            entry["lines_added"], entry["lines_removed"] = lines[path]
        entries.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "hashed_over": HASHED_OVER,
        "base_known": base_known,
        "files": entries,
        "summary": {"files": len(entries), **counts},
        "base_bundle_sha256": bundle_sha256({e["path"]: e["base_sha256"] for e in entries if e["base_sha256"]}),
        "candidate_bundle_sha256": bundle_sha256(
            {e["path"]: e["candidate_sha256"] for e in entries if e["candidate_sha256"]}
        ),
    }


def verify_files(manifest: Mapping, files: Iterable[object] | None) -> list[dict]:
    """
    The check a receiver runs before it trusts a candidate. Returns the
    problems found, an empty list meaning the files are exactly the ones the
    manifest describes. Written out here so the algorithm has one reference.
    """
    problems: list[dict] = []
    held = _index(files)
    expected: dict[str, str] = {}
    for entry in manifest.get("files", []):
        if entry.get("candidate_sha256"):
            expected[entry["path"]] = entry["candidate_sha256"]
    for path, digest in expected.items():
        if path not in held:
            problems.append({"kind": "missing", "path": path})
        elif file_sha256(held[path]) != digest:
            problems.append({"kind": "digest_mismatch", "path": path})
    for path in held:
        if path not in expected:
            problems.append({"kind": "unexpected", "path": path})
    if not problems and bundle_sha256({p: file_sha256(c) for p, c in held.items()}) \
            != manifest.get("candidate_bundle_sha256"):
        problems.append({"kind": "bundle_mismatch", "path": None})
    return problems


def _line_count(content: str) -> int:
    return content.count("\n") + (1 if content and not content.endswith("\n") else 0)


def profile_bundle(envelope: IncidentEnvelope) -> dict:
    """
    How much of what an incident carried does a stack frame point at?

    Informational. It names the excess and refuses nothing, because a repair
    may need a helper that is on no stack, and because the contract cannot
    yet carry less than a whole file.
    """
    frame_lines: dict[str, list[int]] = {}
    for frame in envelope.frames:
        frame_lines.setdefault(frame.path, []).append(frame.line)

    sent = {item.path for item in envelope.files}
    files = []
    total_bytes = 0
    for item in envelope.files:
        size = len(item.content.encode("utf-8"))
        total_bytes += size
        lines = sorted(set(frame_lines.get(item.path, [])))
        files.append({
            "path": item.path,
            "bytes": size,
            "lines": _line_count(item.content),
            "referenced_by_frames": bool(lines),
            "frame_lines": lines[:MAX_FRAME_LINES_LISTED],
        })

    # Without any frame there is nothing to measure relevance against, so no
    # file is called unreferenced: listing all of them would be noise.
    unreferenced = [f["path"] for f in files if not f["referenced_by_frames"]] if envelope.frames else []
    if not envelope.frames:
        verdict = "unjudged"
    elif unreferenced:
        verdict = "has_unreferenced_files"
    else:
        verdict = "minimal"
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "files": files,
        "total_bytes": total_bytes,
        "limit_bytes": MAX_TOTAL_SOURCE_BYTES,
        "fill_ratio": round(total_bytes / MAX_TOTAL_SOURCE_BYTES, 3),
        "unreferenced_files": unreferenced,
        "frames_without_source": sorted(path for path in frame_lines if path not in sent),
    }
