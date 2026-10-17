"""
======================================================================
      Flare (Finja Agentic Code) – L5 Manual Scope Policy
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Conservative routing for multi-file and architectural work.

  New in v1.11.0:
    - Keeps L5 changes out of the automated repair/approval pipeline.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

======================================================================
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

SCHEMA_VERSION = 1

# These are signals, not a semantic architecture detector. A caller can always
# select manual mode for a change whose architecture impact is not visible in
# paths or task wording.
ARCHITECTURE_INTENT_RE = re.compile(
    r"\b(?:architecture|architectural|architektur|schema|schemas|migration|"
    r"migrations|interface|interfaces|schnittstelle|schnittstellen|"
    r"refactor|refactoring|refaktor|multi[ -]?file|mehrere dateien|"
    r"public api|öffentliche api)\b",
    re.IGNORECASE,
)
ARCHITECTURE_PARTS = frozenset({
    "schema", "schemas", "migration", "migrations", "interface", "interfaces",
    "contract", "contracts", "config", "configuration", "api",
})
ARCHITECTURE_NAMES = frozenset({"__init__.py", "package.json", "pyproject.toml"})
ARCHITECTURE_STEMS = frozenset({"schema", "migration", "interface", "config", "settings", "api"})
ARCHITECTURE_SUFFIXES = frozenset({".json", ".yml", ".yaml", ".toml"})


def _architecture_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return parsed.name.lower() in ARCHITECTURE_NAMES \
        or parsed.stem.lower() in ARCHITECTURE_STEMS \
        or parsed.suffix.lower() in ARCHITECTURE_SUFFIXES \
        or any(part.lower() in ARCHITECTURE_PARTS for part in parsed.parts[:-1])


def _report(stage: str, reasons: list[dict], paths: list[str]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "route": "manual" if reasons else "automatic",
        "reasons": reasons,
        "paths": sorted(set(paths)),
        "candidate_diff_seen": stage == "candidate",
        "sandbox_repair_run": False,
        "approval_eligible": False if reasons else None,
    }


def review_request(*, mode: str, task: str, paths: list[str]) -> dict:
    """Classify explicit architecture intent before model or worker activity."""
    reasons = []
    if mode == "manual":
        reasons.append({"kind": "manual_requested", "detail": "Human-led change requested"})
    if ARCHITECTURE_INTENT_RE.search(task):
        reasons.append({"kind": "architecture_intent", "detail": "Task describes architectural or multi-file work"})
    sensitive = sorted({path for path in paths if _architecture_path(path)})
    if sensitive:
        reasons.append({"kind": "architecture_input", "detail": "Submitted architecture/configuration files require human review"})
    return _report("request", reasons, sensitive)


def review_candidate(repair_report: dict) -> dict:
    """Classify the parsed L2 diff before any repair sandbox or approval."""
    entries = repair_report.get("files", [])
    if not isinstance(entries, list):
        entries = []
    paths = [entry["path"] for entry in entries if isinstance(entry, dict) and isinstance(entry.get("path"), str)]
    reasons = []
    if len(set(paths)) > 1:
        reasons.append({"kind": "multi_file_patch", "detail": "Candidate changes more than one file"})
    if any(isinstance(entry, dict) and entry.get("kind") in {"create", "delete"} for entry in entries):
        reasons.append({"kind": "file_topology", "detail": "Candidate creates or deletes a file"})
    if any(_architecture_path(path) for path in paths):
        reasons.append({"kind": "architecture_path", "detail": "Candidate changes an architecture/configuration path"})
    return _report("candidate", reasons, paths)
