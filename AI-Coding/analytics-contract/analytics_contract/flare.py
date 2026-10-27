"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / flare.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: The `flare` block of a project contract: how Flare's signal gateway,
               repair cards and apply path treat this project.

  New in v1.1.0:
    - First version: defaults from detection and the same limits Flare enforces

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import re
from typing import Any

from .models import ProjectProfile

APPLY_MODES = ("host_agent", "self_install", "analysis_only")
OPERATIONS = ("observe", "diagnose", "repair")
AGGREGATIONS = ("avg", "max", "p95", "p99")  # what Flare's ResourceSignalRule accepts
_PREFIX = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_METRIC = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_LABEL = re.compile(r"^[^`*_~|<>@#\r\n]+$")
# Runtimes that cannot be updated in place on a server: report and diagnose, never install.
_ANALYSIS_ONLY_RUNTIMES = {"render_loop", "android", "mobile", "desktop"}
_ANALYSIS_ONLY_LANGUAGES = {"kotlin", "java", "csharp", "cpp"}


def default_flare_block(profile: ProjectProfile) -> dict[str, Any]:
    """Safe starting values; the human tunes them in the contract, Flare's profile follows."""
    analysis_only = bool(set(profile.runtimes) & _ANALYSIS_ONLY_RUNTIMES) or (
        "docker" not in profile.runtimes and bool(set(profile.languages) & _ANALYSIS_ONLY_LANGUAGES)
    )
    return {
        "signals": {
            "errors": {
                "enabled": True,
                "min_count": 3,
                "window_minutes": 15,
                "operation": "repair",
                "operator_fingerprint_prefixes": ["env-"],
            },
            "resources": [
                {"metric": "system.cpu.usage", "aggregation": "p95", "threshold": 85, "window_minutes": 10},
                {"metric": "system.memory.usage", "aggregation": "max", "threshold": 1073741824,
                 "window_minutes": 10},
            ],
            "cooldown_minutes": 360,
        },
        "apply": "analysis_only" if analysis_only else "host_agent",
        "activation_label": "Neustart & Healthcheck",
        "check_label": "Healthcheck",
    }


def _int_between(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def validate_flare_block(block: Any) -> list[str]:
    """The limits Flare's ProjectProfile enforces, so a contract never produces a profile Flare rejects."""
    if not isinstance(block, dict):
        return ["flare must be an object"]
    problems: list[str] = []
    unknown = set(block) - {"signals", "apply", "activation_label", "check_label"}
    if unknown:
        problems.append(f"flare has unknown fields: {', '.join(sorted(unknown))}")
    if block.get("apply") not in APPLY_MODES:
        problems.append(f"flare.apply must be one of {', '.join(APPLY_MODES)}")
    for key, low, high in (("activation_label", 3, 40), ("check_label", 3, 24)):
        value = block.get(key)
        if value is not None and (not isinstance(value, str) or not low <= len(value) <= high
                                  or not _LABEL.fullmatch(value)):
            problems.append(f"flare.{key} must be {low}-{high} plain characters")
    signals = block.get("signals")
    if not isinstance(signals, dict):
        return problems + ["flare.signals must be an object"]
    errors = signals.get("errors")
    if errors is not None:
        if not isinstance(errors, dict):
            problems.append("flare.signals.errors must be an object")
        else:
            if not _int_between(errors.get("min_count", 3), 1, 10_000):
                problems.append("flare.signals.errors.min_count must be 1-10000")
            if not _int_between(errors.get("window_minutes", 15), 1, 1440):
                problems.append("flare.signals.errors.window_minutes must be 1-1440")
            if errors.get("operation", "repair") not in OPERATIONS:
                problems.append(f"flare.signals.errors.operation must be one of {', '.join(OPERATIONS)}")
            prefixes = errors.get("operator_fingerprint_prefixes", [])
            if not isinstance(prefixes, list) or len(prefixes) > 8 \
                    or any(not isinstance(item, str) or not _PREFIX.fullmatch(item) for item in prefixes):
                problems.append("flare.signals.errors.operator_fingerprint_prefixes must be up to 8 short slugs")
    resources = signals.get("resources", [])
    if not isinstance(resources, list) or len(resources) > 16:
        problems.append("flare.signals.resources must be a list of up to 16 rules")
    else:
        seen: set[tuple[str, str]] = set()
        for index, rule in enumerate(resources):
            label = f"flare.signals.resources[{index}]"
            if not isinstance(rule, dict):
                problems.append(f"{label} must be an object")
                continue
            if not _METRIC.fullmatch(str(rule.get("metric") or "")):
                problems.append(f"{label}.metric is invalid")
            if rule.get("aggregation") not in AGGREGATIONS:
                problems.append(f"{label}.aggregation must be one of {', '.join(AGGREGATIONS)}")
            threshold = rule.get("threshold")
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold <= 0:
                problems.append(f"{label}.threshold must be a positive number")
            key = (str(rule.get("metric")), str(rule.get("aggregation")))
            if key in seen:
                problems.append(f"{label} repeats metric and aggregation")
            seen.add(key)
            if not _int_between(rule.get("window_minutes", 10), 1, 1440):
                problems.append(f"{label}.window_minutes must be 1-1440")
    if not _int_between(signals.get("cooldown_minutes", 360), 5, 10_080):
        problems.append("flare.signals.cooldown_minutes must be 5-10080")
    return problems
