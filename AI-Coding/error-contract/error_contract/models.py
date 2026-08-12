"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/models.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Shared dataclasses: ErrorCode, Taxonomy, Finding, ScanReport.

  New in v1.0.0:
    • Production release packaging for public GitHub
    • Cross-project engine, ambient hooks, global code ledger
    • See repository README.md / INSTALL.md / AMBIENT.md

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# Shared numeric bands (Finja reference). Projects keep the ranges; only PREFIX changes.
DEFAULT_BANDS: dict[str, tuple[int, int, str]] = {
    "config": (100, 199, "Config / env / packages"),
    "llm": (200, 299, "LLM / providers"),
    "memory": (300, 399, "Memory / store / diary"),
    "session": (400, 499, "Session / auth / privileges"),
    "tool": (500, 599, "Tools / plugins"),
    "pipeline": (600, 699, "Pipeline / guard / safety / input"),
    "host": (800, 899, "Host / system / maintenance"),
    "unexpected": (900, 999, "Generic / unexpected (prefer dedicated codes)"),
    "privacy": (1000, 1099, "Privacy / output firewall (usually no inbox)"),
    "injection": (1100, 1199, "Prompt injection / input firewall (usually no inbox)"),
}


@dataclass
class ErrorCode:
    code_num: int
    class_name: str
    base_class: str = "AppError"
    band: str = ""
    message_hint: str = ""
    to_inbox: bool = True
    module_default: str = ""
    source_file: str = ""
    source_line: int = 0

    def branded(self, prefix: str) -> str:
        return f"{prefix.upper()}-{self.code_num}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Taxonomy:
    """Source-of-truth catalogue of structured error codes for one project."""

    prefix: str = "APP"
    source: str = ""  # path to exceptions.py or contract JSON
    codes: list[ErrorCode] = field(default_factory=list)
    bands: dict[str, tuple[int, int, str]] = field(default_factory=lambda: dict(DEFAULT_BANDS))
    has_app_error: bool = False
    has_set_code_prefix: bool = False
    style: str = "unknown"  # finja_app_error | json_contract | missing

    def by_num(self) -> dict[int, ErrorCode]:
        return {c.code_num: c for c in self.codes}

    def used_nums(self) -> set[int]:
        return {c.code_num for c in self.codes}

    def next_free(self, band: str) -> Optional[int]:
        info = self.bands.get(band)
        if not info:
            return None
        lo, hi, _ = info
        used = self.used_nums()
        # Prefer not to hand out pure century bases if already taken; scan whole band.
        for n in range(lo, hi + 1):
            if n not in used:
                return n
        return None

    def branded_list(self) -> list[dict[str, Any]]:
        out = []
        for c in sorted(self.codes, key=lambda x: x.code_num):
            d = c.to_dict()
            d["code"] = c.branded(self.prefix)
            out.append(d)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "source": self.source,
            "style": self.style,
            "has_app_error": self.has_app_error,
            "has_set_code_prefix": self.has_set_code_prefix,
            "bands": {
                k: {"lo": v[0], "hi": v[1], "label": v[2]} for k, v in self.bands.items()
            },
            "codes": self.branded_list(),
        }


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Finding:
    """One scanner hit: something that violates the error contract."""

    rule: str
    severity: str  # critical | high | medium | low | info
    path: str
    line: int
    message: str
    snippet: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectProfile:
    root: str
    prefix: str = "APP"
    taxonomy: Optional[Taxonomy] = None
    exceptions_path: str = ""
    contract_path: str = ""
    detected_systems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "prefix": self.prefix,
            "exceptions_path": self.exceptions_path,
            "contract_path": self.contract_path,
            "detected_systems": self.detected_systems,
            "notes": self.notes,
            "taxonomy": self.taxonomy.to_dict() if self.taxonomy else None,
        }


@dataclass
class ScanReport:
    profile: ProjectProfile
    findings: list[Finding] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.path, f.line),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "summary": self.counts(),
            "finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.sorted_findings()],
        }
