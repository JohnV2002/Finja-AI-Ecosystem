"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / hooks_runner
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.1
  Description: SessionStart preflight context + Stop gate for GitHub Contract.

  New in v1.1.0:
    - Aligned hook context with the cross-project plugin identity

  New in v1.0.1:
    - Module version alignment; hook behavior is unchanged

  New in v1.0.0:
    - Dual harness snake_case (Codex) / camelCase (Grok)

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .detect import detect_module
from .scanner import scan_module


def _read() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _g(ev: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in ev and ev[k] is not None:
            return ev[k]
    return default


def _cwd(ev: dict[str, Any]) -> Path:
    for k in ("cwd", "workspaceRoot", "workspace_root"):
        v = ev.get(k)
        if v:
            return Path(str(v)).resolve()
    return Path.cwd().resolve()


def handle_session_start(ev: dict[str, Any]) -> int:
    root = _cwd(ev)
    try:
        prof = detect_module(root)
    except Exception:
        return 0
    if not (prof.is_git or prof.is_githubish or "readme" in prof.signals):
        return 0
    brief = (
        f"[GitHub Contract preflight]\n"
        f"root={prof.root}\n"
        f"module={prof.module_name} version={prof.declared_version or '(unset)'}\n"
        f"git={prof.is_git} githubish={prof.is_githubish} signals={','.join(prof.signals)}\n"
        f"RULES: ecosystem headers on all source files; ONE module version "
        f"MAJOR.FEATURES.BUGS in every file (changelog may differ); "
        f"no secrets/private paths; README License+Support+version.\n"
        f"Run: github-contract scan . --version {prof.declared_version or 'X.Y.Z'}"
    )
    # write active note
    try:
        d = root / ".github_contract"
        d.mkdir(exist_ok=True)
        (d / "ACTIVE.md").write_text("# GitHub Contract\n\n```\n" + brief + "\n```\n", encoding="utf-8")
    except OSError:
        pass
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": brief,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


def handle_stop(ev: dict[str, Any]) -> int:
    reason = str(_g(ev, "reason", default="") or "")
    if reason in {"channel_closed", "shutdown", "other"}:
        return 0
    root = _cwd(ev)
    try:
        prof, findings = scan_module(root)
    except Exception as e:
        sys.stderr.write(f"github-contract gate error: {e}\n")
        return 0
    if not (prof.is_git or prof.is_githubish):
        return 0
    bad = [f for f in findings if f.severity in {"critical", "high"}]
    if not bad:
        return 0
    # only block if there were recent edits? keep simple: block on critical always in git repos
    crit = [f for f in bad if f.severity == "critical"]
    if not crit:
        # high alone: soft — still block a few (missing headers storm)
        if len(bad) < 3:
            return 0
    lines = [
        f"GitHub Contract gate: {len(bad)} high/critical issue(s) in {prof.module_name}.",
        f"Module version target: {prof.declared_version or '(unset)'} (MAJOR.FEATURES.BUGS — same in EVERY file).",
        "",
    ]
    for f in bad[:15]:
        loc = f"{f.path}:{f.line}" if f.line else f.path
        lines.append(f"- [{f.severity}] {f.rule} @ {loc}: {f.message}")
    lines.append("")
    lines.append("Fix before finishing. CLI: github-contract scan .")
    sys.stdout.write(
        json.dumps({"decision": "block", "reason": "\n".join(lines)}, ensure_ascii=False)
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    ev = _read()
    name = (argv[0] if argv else str(_g(ev, "hook_event_name", "hookEventName", default=""))).lower()
    name = name.replace("-", "_")
    if name in {"session_start", "sessionstart"}:
        return handle_session_start(ev)
    if name in {"stop", "subagent_stop", "subagentstop"}:
        return handle_stop(ev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
