"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / contract.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
  Description: Create and validate the public project analytics contract.

  New in v1.0.1:
    - Pins event/API compatibility and validates the reviewed tag allowlist

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .detect import detect_project
from .events import DEFAULT_ALLOWED_TAGS


CONTRACT_FILE = "analytics_contract.json"


def build_contract(path: str | Path) -> dict[str, Any]:
    profile = detect_project(path)
    return {
        "schema_version": "1.0",
        "protocol": {
            "event_schema": "1.0",
            "api_major": 1,
        },
        "project": {
            "id": profile.project_id,
            "languages": profile.languages,
            "runtimes": profile.runtimes,
        },
        "analytics": {
            "enabled": False,
            "endpoint": None,
            "endpoint_env": "ANALYTICS_ENDPOINT",
            "auth_token_env": "ANALYTICS_TOKEN",
            "timeout_ms": 750,
            "fail_silent": True,
            "queue": {"max_events": 1000, "batch_size": 100, "drop_oldest": True},
        },
        "error_integration": {
            "detected": profile.error_contract or profile.error_inbox,
            "mode": "error_contract" if profile.error_contract else "none",
            "reuse_error_event": True,
            "include_affected_file": True,
            "file_path_mode": "project_relative",
            "include_source": False,
            "include_stacktrace": False,
        },
        "privacy": {
            "allow_personal_data": False,
            "allow_secrets": False,
            "allow_prompts": False,
            "allow_absolute_paths": False,
            "allowed_tags": ["environment", "version", "component", "operation", "outcome"],
        },
        "metrics": {item.name: item.to_dict() for item in profile.recommendations},
    }


def write_contract(path: str | Path, *, force: bool = False) -> tuple[Path, bool]:
    root = Path(path).expanduser().resolve()
    target = root / CONTRACT_FILE
    if target.exists() and not force:
        return target, False
    target.write_text(json.dumps(build_contract(root), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target, True


def validate_contract(path: str | Path) -> list[str]:
    target = Path(path).expanduser().resolve() / CONTRACT_FILE
    if not target.is_file():
        return [f"missing {CONTRACT_FILE}"]
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid contract JSON: {exc}"]

    problems: list[str] = []
    analytics = data.get("analytics") or {}
    integration = data.get("error_integration") or {}
    privacy = data.get("privacy") or {}
    if data.get("schema_version") != "1.0":
        problems.append("schema_version must be 1.0")
    protocol = data.get("protocol") or {}
    if protocol.get("event_schema") != "1.0" or protocol.get("api_major") != 1:
        problems.append("protocol must select event_schema 1.0 and api_major 1")
    if not isinstance(analytics.get("enabled"), bool):
        problems.append("analytics.enabled must be true or false")
    if analytics.get("fail_silent") is not True:
        problems.append("analytics.fail_silent must remain true")
    if not analytics.get("endpoint_env") and not analytics.get("endpoint"):
        problems.append("endpoint_env or endpoint must be configured")
    if integration.get("file_path_mode") != "project_relative":
        problems.append("error file paths must be project_relative")
    if integration.get("include_source") is not False:
        problems.append("error source contents must not be transmitted")
    if privacy.get("allow_secrets") is not False:
        problems.append("secrets must never be allowed in analytics")
    if privacy.get("allow_absolute_paths") is not False:
        problems.append("absolute paths must never be allowed in analytics")
    allowed_tags = privacy.get("allowed_tags")
    if not isinstance(allowed_tags, list) or not allowed_tags:
        problems.append("privacy.allowed_tags must be a non-empty list")
    elif len(allowed_tags) != len(set(allowed_tags)):
        problems.append("privacy.allowed_tags must not contain duplicates")
    elif any(not isinstance(tag, str) or tag not in DEFAULT_ALLOWED_TAGS for tag in allowed_tags):
        problems.append("privacy.allowed_tags contains an unsafe or unknown tag")
    return problems


def load_allowed_tags(path: str | Path) -> set[str]:
    """Return the project's reviewed tag allowlist, or the safe default."""
    target = Path(path).expanduser().resolve() / CONTRACT_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
        configured = data.get("privacy", {}).get("allowed_tags")
    except (OSError, json.JSONDecodeError, AttributeError):
        return set(DEFAULT_ALLOWED_TAGS)
    if not isinstance(configured, list):
        return set(DEFAULT_ALLOWED_TAGS)
    safe = {tag for tag in configured if isinstance(tag, str) and tag in DEFAULT_ALLOWED_TAGS}
    return safe or set(DEFAULT_ALLOWED_TAGS)

