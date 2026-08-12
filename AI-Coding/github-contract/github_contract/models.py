"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / models
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Shared dataclasses for scan findings and module profile.

  New in v1.1.0:
    - Added a neutral default target-project label

  New in v1.0.1:
    - Module version alignment; data models are unchanged

  New in v1.0.0:
    - Initial production release

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    rule: str
    severity: str  # critical | high | medium | low | info
    path: str
    line: int
    message: str
    suggestion: str = ""
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleProfile:
    root: str
    is_git: bool = False
    is_githubish: bool = False
    module_name: str = ""
    project_label: str = "J. Apps Project"
    declared_version: str = ""  # from pyproject / package / majority vote
    versions_found: dict[str, int] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
