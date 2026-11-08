"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/exclusions.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.4.0
  Description:
    Per-project scan exclusions. Every entry needs a reason, and every
    scan reports what it excluded, so nothing disappears silently.

  New in v1.4.0:
    • scan_exclude list in the project's error_contract.json
    • Entries without a reason are rejected and reported as findings
    • Per-entry match counts, including entries that match nothing

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILE = "error_contract.json"
CONFIG_KEY = "scan_exclude"


@dataclass
class ExcludeRule:
    """One accepted scan_exclude entry."""

    path: str
    reason: str
    matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "reason": self.reason, "matched": list(self.matched)}


@dataclass
class ExclusionConfig:
    """Accepted rules plus the entries that were rejected, with why."""

    source: str = ""
    rules: list[ExcludeRule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def excluded_count(self) -> int:
        return sum(len(rule.matched) for rule in self.rules)

    def match(self, rel_path: str) -> ExcludeRule | None:
        """Return the first rule that matches a project-relative POSIX path."""
        for rule in self.rules:
            if glob_match(rule.path, rel_path):
                rule.matched.append(rel_path)
                return rule
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "excluded_files": self.excluded_count,
            "rules": [rule.to_dict() for rule in self.rules],
            "errors": list(self.errors),
        }


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path glob: ``**`` spans folders, ``*`` and ``?`` stay inside one."""
    pattern = pattern.strip().replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    if pattern.endswith("/"):
        pattern += "**"
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("".join(out) + r"\Z", re.IGNORECASE)


def glob_match(pattern: str, rel_path: str) -> bool:
    return bool(_glob_regex(pattern).match(rel_path.replace("\\", "/")))


def parse_exclusions(raw: Any, source: str = CONFIG_FILE) -> ExclusionConfig:
    """Validate a raw scan_exclude value. Invalid entries are rejected, never applied."""
    config = ExclusionConfig(source=source)
    if raw is None:
        return config
    if not isinstance(raw, list):
        config.errors.append(f"{source}: '{CONFIG_KEY}' must be a list of {{path, reason}} objects")
        return config
    for index, entry in enumerate(raw):
        label = f"{source}: {CONFIG_KEY}[{index}]"
        if not isinstance(entry, dict):
            config.errors.append(f"{label} must be an object with 'path' and 'reason'")
            continue
        path = entry.get("path")
        reason = entry.get("reason")
        if not isinstance(path, str) or not path.strip():
            config.errors.append(f"{label} has no 'path' glob")
            continue
        if not isinstance(reason, str) or not reason.strip():
            config.errors.append(f"{label} ('{path.strip()}') has no 'reason' - rejected, file stays scanned")
            continue
        normalized = path.strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in normalized.split("/"):
            config.errors.append(f"{label} ('{normalized}') must be relative to the project root")
            continue
        config.rules.append(ExcludeRule(path=normalized, reason=" ".join(reason.split())))
    return config


def load_exclusions(root: str | Path) -> ExclusionConfig:
    """Read scan_exclude from <root>/error_contract.json. Missing file or key means no exclusions."""
    path = Path(root) / CONFIG_FILE
    if not path.is_file():
        return ExclusionConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        config = ExclusionConfig(source=CONFIG_FILE)
        config.errors.append(f"{CONFIG_FILE} unreadable, no exclusions applied: {exc}")
        return config
    if not isinstance(data, dict):
        return ExclusionConfig()
    return parse_exclusions(data.get(CONFIG_KEY), CONFIG_FILE)


def format_exclusions(config: ExclusionConfig | None) -> list[str]:
    """Human lines for scan/slap output. Empty when nothing is configured."""
    if config is None or (not config.rules and not config.errors):
        return []
    lines = [
        f"Excluded: {config.excluded_count} file(s) by {len(config.rules)} rule(s) "
        f"in {config.source}:{CONFIG_KEY}"
    ]
    for rule in config.rules:
        count = len(rule.matched)
        stale = "  !! matches nothing - remove or fix the glob" if count == 0 else ""
        lines.append(f"  - {rule.path} ({count} file(s)): {rule.reason}{stale}")
    for error in config.errors:
        lines.append(f"  !! {error}")
    return lines
