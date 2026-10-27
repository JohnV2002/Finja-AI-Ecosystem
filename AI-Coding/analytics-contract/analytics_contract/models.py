"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / models.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Detection and metric recommendation data models.

  New in v1.0.0:
    - Defines language-neutral project and metric profiles

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MetricRecommendation:
    name: str
    kind: str
    unit: str
    reason: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectProfile:
    root: str
    project_id: str
    languages: list[str] = field(default_factory=list)
    runtimes: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    error_contract: bool = False
    error_inbox: bool = False
    exempt: bool = False
    exemption_reason: str = ""
    recommendations: list[MetricRecommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["recommendations"] = [item.to_dict() for item in self.recommendations]
        return data

