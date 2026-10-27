"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / events.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Validate the stable language-neutral analytics event envelope.

  New in v1.0.1:
    - Separates delivery IDs from fingerprints and bounds tags/extensions

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Iterable


KINDS = {"counter", "gauge", "timing", "event", "error"}
OUTCOMES = {"success", "failure", "cancelled", "unknown"}
ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
FINGERPRINT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EXTENSION_KEY = re.compile(r"^x_[a-z][a-z0-9_]{0,62}$")
DEFAULT_ALLOWED_TAGS = {"environment", "version", "component", "operation", "outcome"}
TOP_LEVEL_FIELDS = {
    "schema_version", "event_id", "timestamp", "project_id", "module",
    "event_name", "kind", "outcome", "value", "unit", "duration_ms",
    "error", "tags", "extensions",
}
ERROR_FIELDS = {"code", "fingerprint", "affected_file", "line"}
SENSITIVE_KEY_PARTS = {
    "email", "ip", "path", "prompt", "query", "request_id", "secret",
    "source", "stack", "token", "url", "user", "username",
}


def _unsafe_key(name: str) -> bool:
    parts = {part for part in re.split(r"[^a-z0-9]+", name.lower()) if part}
    return bool(parts.intersection(SENSITIVE_KEY_PARTS))


def _validate_scalar(value: Any, label: str, problems: list[str]) -> None:
    if not isinstance(value, (str, int, float, bool)) or value is None:
        problems.append(f"{label} must be a string, number, or boolean")
    elif isinstance(value, str) and (len(value) > 128 or "\n" in value or "\r" in value):
        problems.append(f"{label} string must be one line and at most 128 characters")


def validate_event(
    event: dict[str, Any],
    *,
    allowed_tags: Iterable[str] | None = None,
) -> list[str]:
    problems: list[str] = []
    if not isinstance(event, dict):
        return ["event must be an object"]
    unknown = set(event).difference(TOP_LEVEL_FIELDS)
    if unknown:
        problems.append(f"event contains unknown fields: {', '.join(sorted(unknown))}")
    required = ("schema_version", "event_id", "timestamp", "project_id", "event_name", "kind")
    for key in required:
        if not event.get(key):
            problems.append(f"missing {key}")
    if event.get("schema_version") != "1.0":
        problems.append("schema_version must be 1.0")
    if event.get("kind") not in KINDS:
        problems.append(f"kind must be one of {sorted(KINDS)}")
    if event.get("outcome") is not None and event.get("outcome") not in OUTCOMES:
        problems.append(f"outcome must be one of {sorted(OUTCOMES)}")
    event_id = str(event.get("event_id") or "")
    if len(event_id) > 128:
        problems.append("event_id must be at most 128 characters")

    tags = event.get("tags")
    tag_allowlist = set(allowed_tags or DEFAULT_ALLOWED_TAGS)
    if tags is not None and not isinstance(tags, dict):
        problems.append("tags must be an object")
    elif isinstance(tags, dict):
        if len(tags) > 16:
            problems.append("tags may contain at most 16 entries")
        disallowed = set(tags).difference(tag_allowlist)
        if disallowed:
            problems.append(f"tags are not allowlisted: {', '.join(sorted(disallowed))}")
        for key, value in tags.items():
            _validate_scalar(value, f"tags.{key}", problems)

    extensions = event.get("extensions")
    if extensions is not None and not isinstance(extensions, dict):
        problems.append("extensions must be an object")
    elif isinstance(extensions, dict):
        if len(extensions) > 8:
            problems.append("extensions may contain at most 8 entries")
        for key, value in extensions.items():
            if not EXTENSION_KEY.fullmatch(key) or _unsafe_key(key):
                problems.append(f"unsafe extension key: {key}")
            _validate_scalar(value, f"extensions.{key}", problems)

    error = event.get("error")
    if event.get("kind") == "error" and not isinstance(error, dict):
        problems.append("error events require an error object")
    if isinstance(error, dict):
        unknown_error = set(error).difference(ERROR_FIELDS)
        if unknown_error:
            problems.append(f"error contains unknown fields: {', '.join(sorted(unknown_error))}")
        code = str(error.get("code") or "")
        if not ERROR_CODE.fullmatch(code):
            problems.append("error.code must be a structured PREFIX-number code")
        fingerprint = str(error.get("fingerprint") or "")
        if not FINGERPRINT.fullmatch(fingerprint):
            problems.append("error.fingerprint must be a stable privacy-safe identifier")
        affected = str(error.get("affected_file") or "")
        normalized = affected.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if not affected:
            problems.append("error.affected_file is required")
        elif pure.is_absolute() or ":" in normalized or ".." in pure.parts:
            problems.append("error.affected_file must be project-relative")
    return problems


def validate_batch(
    events: list[dict[str, Any]],
    *,
    allowed_tags: Iterable[str] | None = None,
) -> list[str]:
    """Validate the same batch at producer and collector boundaries."""
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        return ["event batch must contain between 1 and 100 events"]
    problems: list[str] = []
    seen: set[str] = set()
    for index, event in enumerate(events):
        for problem in validate_event(event, allowed_tags=allowed_tags):
            problems.append(f"events[{index}]: {problem}")
        event_id = str(event.get("event_id") or "") if isinstance(event, dict) else ""
        if event_id and event_id in seen:
            problems.append(f"events[{index}]: duplicate event_id in batch")
        seen.add(event_id)
    return problems

