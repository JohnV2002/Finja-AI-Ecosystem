"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/report.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Human-readable scan / taxonomy reports.

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

from .models import ScanReport, Taxonomy


def format_taxonomy(tax: Taxonomy, *, limit: int = 0) -> str:
    lines = [
        f"Prefix : {tax.prefix}",
        f"Source : {tax.source or '(none)'}",
        f"Style  : {tax.style}",
        f"Codes  : {len(tax.codes)}",
        "",
        f"{'Code':<14} {'Num':>5} {'Class':<28} {'Band':<12} Inbox",
        "-" * 72,
    ]
    codes = sorted(tax.codes, key=lambda c: c.code_num)
    if limit and limit > 0:
        codes = codes[:limit]
    for c in codes:
        lines.append(
            f"{c.branded(tax.prefix):<14} {c.code_num:>5} {c.class_name:<28} {c.band:<12} "
            f"{'yes' if c.to_inbox else 'no'}"
        )
    return "\n".join(lines)


def format_scan(report: ScanReport, *, max_findings: int = 80) -> str:
    p = report.profile
    counts = report.counts()
    lines = [
        "=== Error Contract Scan ===",
        f"Root   : {p.root}",
        f"Prefix : {p.prefix}",
        f"SoT    : {p.exceptions_path or p.contract_path or '(missing)'}",
        f"Detect : {', '.join(p.detected_systems) or '-'}",
        f"Hits   : {len(report.findings)}  {counts}",
        "",
    ]
    if p.notes:
        lines.append("Notes:")
        for n in p.notes:
            lines.append(f"  - {n}")
        lines.append("")

    findings = report.sorted_findings()
    if max_findings and len(findings) > max_findings:
        show = findings[:max_findings]
        truncated = len(findings) - max_findings
    else:
        show = findings
        truncated = 0

    for f in show:
        loc = f"{f.path}:{f.line}" if f.line else f.path
        lines.append(f"[{f.severity.upper():<8}] {f.rule}  @ {loc}")
        lines.append(f"  {f.message}")
        if f.snippet:
            lines.append(f"  > {f.snippet[:200]}")
        if f.suggestion:
            lines.append(f"  -> {f.suggestion}")
        lines.append("")

    if truncated:
        lines.append(f"... {truncated} more findings (use --json or raise --max)")
    if not report.findings:
        lines.append("Clean: no contract violations found (within scanner rules).")
    return "\n".join(lines).rstrip() + "\n"
