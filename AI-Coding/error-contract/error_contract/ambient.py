"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/ambient.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Preflight, baseline gate, session dirty tracking for ambient enforcement.

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

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .detect import detect_project
from .models import Finding, ScanReport
from .registry import resolve_project
from .scanner import scan_project

CODE_MARKERS = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "requirements.txt",
    "setup.py",
    "Pipfile",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
    ".git",
    "core/exceptions.py",
    "exceptions.py",
    "ERROR_CONTRACT.md",
    "contracts/error_contract.json",
    "contracts/error_contract.module.json",
)

EDIT_TOOLS = {
    "search_replace",
    "write",
    "Write",
    "Edit",
    "MultiEdit",
    "str_replace",
    "apply_patch",
    "create_file",
    "delete_file",
}


def is_code_project(root: str | Path) -> bool:
    """Fail-soft: random TEMP / Downloads junk must not look like a repo."""
    root = Path(root)
    if not root.is_dir():
        return False
    # Never treat common non-project homes as code (unless they have real markers)
    noise_names = {"temp", "tmp", "downloads", "desktop", "appdata", "cache"}
    # Strong project markers first
    strong = (
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "composer.json",
        "requirements.txt",
        "setup.py",
        "Pipfile",
        "pom.xml",
        "build.gradle",
        "CMakeLists.txt",
        ".git",
        "core/exceptions.py",
        "exceptions.py",
        "ERROR_CONTRACT.md",
        "contracts/error_contract.json",
        "contracts/error_contract.module.json",
        "AGENTS.md",
        "CLAUDE.md",
    )
    for name in strong:
        if (root / name).exists():
            return True
    # Weak: src-like layout with source files (not bare TEMP dumps)
    try:
        for sub in ("src", "app", "lib", "core", "packages", "backend", "frontend"):
            d = root / sub
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cs"}:
                        return True
                    break
        # Root-level sources only if not a known noise directory name
        if root.name.lower() in noise_names or "temp" in root.as_posix().lower().replace("\\", "/"):
            return False
        src_count = 0
        for p in root.iterdir():
            if p.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cs"}:
                src_count += 1
                if src_count >= 2:
                    return True
    except OSError:
        return False
    return False


def project_cache_dir(root: Path) -> Path:
    d = root / ".error_contract"
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_state_path(session_id: str = "") -> Path:
    base = Path.home() / ".error_contract" / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    sid = session_id or os.environ.get("GROK_SESSION_ID") or "default"
    # safe filename
    h = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16]
    return base / f"{h}.json"


def load_session_state(session_id: str = "") -> dict[str, Any]:
    path = session_state_path(session_id)
    if not path.is_file():
        return {
            "session_id": session_id or os.environ.get("GROK_SESSION_ID") or "default",
            "dirty": False,
            "edited_files": [],
            "preflight": None,
            "gate_blocks": 0,
            "updated_at": 0,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "session_id": session_id or "default",
            "dirty": False,
            "edited_files": [],
            "preflight": None,
            "gate_blocks": 0,
            "updated_at": 0,
        }


def save_session_state(state: dict[str, Any], session_id: str = "") -> Path:
    path = session_state_path(session_id or state.get("session_id") or "")
    state["updated_at"] = time.time()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def finding_key(f: Finding | dict[str, Any]) -> str:
    if isinstance(f, Finding):
        return f"{f.rule}|{f.path}|{f.line}|{f.message}"
    return f"{f.get('rule')}|{f.get('path')}|{f.get('line')}|{f.get('message')}"


def baseline_path(root: Path) -> Path:
    return project_cache_dir(root) / "baseline.json"


def load_baseline(root: Path) -> set[str]:
    p = baseline_path(root)
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return set(data.get("keys") or [])
    except (OSError, json.JSONDecodeError):
        return set()


def save_baseline(root: Path, report: ScanReport) -> Path:
    keys = sorted(finding_key(f) for f in report.findings)
    p = baseline_path(root)
    p.write_text(
        json.dumps(
            {
                "prefix": report.profile.prefix,
                "count": len(keys),
                "keys": keys,
                "saved_at": time.time(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def preflight(root: str | Path, *, session_id: str = "", quiet: bool = False) -> dict[str, Any]:
    """Resolve project + write ACTIVE.md; soft-skip non-code dirs."""
    root_p = Path(root).expanduser().resolve()
    result: dict[str, Any] = {
        "ok": True,
        "path": str(root_p),
        "is_code_project": is_code_project(root_p),
        "status": "skip",
        "brief": "",
    }
    if not result["is_code_project"]:
        result["brief"] = "not a code project - error-contract ambient skip"
        return result

    resolved = resolve_project(root_p)
    if resolved["status"] == "exempt":
        brief = (
            "ERROR CONTRACT PREFLIGHT\n"
            f"project: {root_p.name}\n"
            "status: exempt\n"
            f"reason: {resolved['reason']}\n"
            "ACTION: onboarding and automatic gate skipped"
        )
        state = load_session_state(session_id)
        state["preflight"] = {
            "path": str(root_p),
            "status": "exempt",
            "prefix": "",
            "resolved": resolved,
            "exceptions_path": "",
            "active_md": "",
        }
        state["workspace_root"] = str(root_p)
        save_session_state(state, session_id)
        result.update(status="exempt", brief=brief, resolved=resolved)
        return result

    profile = detect_project(
        root_p,
        prefix=resolved.get("effective_prefix") or "",
    )
    if resolved["status"] == "known":
        profile.prefix = resolved["effective_prefix"]
        if profile.taxonomy:
            profile.taxonomy.prefix = profile.prefix

    brief_lines = [
        f"ERROR CONTRACT PREFLIGHT",
        f"project: {root_p.name}",
        f"status: {resolved['status']}",
        f"prefix: {profile.prefix}",
    ]
    if resolved["status"] == "known":
        proj = resolved["project"]
        brief_lines += [
            f"id: {proj.get('id')}",
            f"mode: {proj.get('mode')}",
            f"parent: {proj.get('parent_id') or '-'}",
            f"owners: {','.join(proj.get('owners') or []) or '-'}",
            f"ecosystem: {','.join(proj.get('ecosystem') or []) or '-'}",
            f"module_default: {proj.get('module_default') or '-'}",
        ]
    else:
        brief_lines += [
            "ACTION: needs_onboard - ask human before inventing codes",
            f"suggested_prefix: {resolved.get('suggested_prefix')}",
            f"suggested_id: {resolved.get('suggested_id')}",
        ]
    def local_display(value: str) -> str:
        if not value:
            return "(none)"
        try:
            return Path(value).resolve().relative_to(root_p).as_posix()
        except ValueError:
            return Path(value).name

    brief_lines += [
        f"exceptions: {local_display(profile.exceptions_path)}",
        f"contract: {local_display(profile.contract_path)}",
        f"detected: {', '.join(profile.detected_systems) or '-'}",
        "",
        "RULES: no print/console as error path; use AppError + PREFIX-xxx;",
        "broad except must wrap UnexpectedError or dedicated code;",
        "after edits: ambient gate runs slap (new findings only).",
    ]
    brief = "\n".join(brief_lines)

    # Write project-local ACTIVE brief (agents can read; hooks enforce)
    active = project_cache_dir(root_p) / "ACTIVE.md"
    active.write_text(
        "# Error Contract - session preflight (auto)\n\n```\n" + brief + "\n```\n",
        encoding="utf-8",
    )

    # Seed baseline if missing (existing debt becomes baseline, not a gate)
    if not baseline_path(root_p).is_file() and resolved["status"] == "known":
        try:
            report = scan_project(root_p, prefix=profile.prefix, include_info=False)
            save_baseline(root_p, report)
            brief_lines.append(f"baseline: seeded ({len(report.findings)} existing findings)")
            brief = "\n".join(brief_lines)
            active.write_text(
                "# Error Contract - session preflight (auto)\n\n```\n" + brief + "\n```\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    state = load_session_state(session_id)
    state["preflight"] = {
        "path": str(root_p),
        "status": resolved["status"],
        "prefix": profile.prefix,
        "resolved": resolved if resolved["status"] == "known" else {
            "status": "needs_onboard",
            "suggested_prefix": resolved.get("suggested_prefix"),
            "suggested_id": resolved.get("suggested_id"),
        },
        "exceptions_path": profile.exceptions_path,
        "active_md": str(active),
    }
    state["workspace_root"] = str(root_p)
    save_session_state(state, session_id)

    result.update(
        {
            "status": resolved["status"],
            "prefix": profile.prefix,
            "brief": brief,
            "active_md": str(active),
            "resolved": resolved,
            "profile": {
                "exceptions_path": profile.exceptions_path,
                "contract_path": profile.contract_path,
                "detected": profile.detected_systems,
            },
        }
    )
    return result


def mark_edit(
    *,
    path: str = "",
    tool_name: str = "",
    session_id: str = "",
    workspace_root: str = "",
) -> dict[str, Any]:
    state = load_session_state(session_id)
    if tool_name and tool_name not in EDIT_TOOLS and tool_name not in {
        "run_terminal_command",  # may edit via shell; only mark if path given
        "Bash",
    }:
        # Only track known edit tools; shell alone without path is ignored
        if tool_name not in EDIT_TOOLS:
            return {"dirty": state.get("dirty", False), "tracked": False}

    if tool_name in EDIT_TOOLS or path:
        state["dirty"] = True
        if path:
            # normalize relative-ish
            p = path.replace("\\", "/")
            files = list(state.get("edited_files") or [])
            if p not in files:
                files.append(p)
            state["edited_files"] = files[-200:]
        if workspace_root:
            state["workspace_root"] = workspace_root
        save_session_state(state, session_id)
        return {"dirty": True, "tracked": True, "files": state.get("edited_files")}
    return {"dirty": state.get("dirty", False), "tracked": False}


def gate(
    root: str | Path,
    *,
    session_id: str = "",
    only_edited: bool = True,
    include_info: bool = False,
    max_report: int = 20,
) -> dict[str, Any]:
    """Compare current scan vs baseline; optionally filter to edited files.

    Returns ok=True if no NEW actionable findings.
    """
    root_p = Path(root).expanduser().resolve()
    out: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "path": str(root_p),
        "new_findings": [],
        "existing_debt": 0,
        "scanned": 0,
    }
    if not is_code_project(root_p):
        out["skipped"] = True
        out["reason"] = "not_code_project"
        return out

    state = load_session_state(session_id)
    if not state.get("dirty"):
        out["skipped"] = True
        out["reason"] = "no_edits_this_session"
        return out

    pref = ""
    resolved = resolve_project(root_p)
    if resolved["status"] == "exempt":
        out["skipped"] = True
        out["reason"] = "error_contract_exempt"
        return out
    if resolved["status"] == "known":
        pref = resolved["effective_prefix"]
    else:
        # Prefer this cwd's detect/taxonomy; only reuse session preflight if same root
        same_root = (state.get("workspace_root") or "").replace("\\", "/").lower() == str(
            root_p
        ).replace("\\", "/").lower()
        if same_root and state.get("preflight", {}).get("prefix"):
            pref = state["preflight"]["prefix"]
        else:
            try:
                prof = detect_project(root_p)
                pref = prof.prefix or ""
            except Exception:
                pref = ""

    report = scan_project(root_p, prefix=pref, include_info=include_info)
    # drop pure info
    findings = [f for f in report.findings if f.severity in {"critical", "high", "medium"}]
    out["scanned"] = len(findings)

    # Empty baseline file is valid (0 debt) - only seed when missing on disk
    if not baseline_path(root_p).is_file():
        save_baseline(root_p, report)
        out["skipped"] = True
        out["reason"] = "baseline_seeded"
        out["existing_debt"] = len(findings)
        state["dirty"] = False
        save_session_state(state, session_id)
        return out

    base = load_baseline(root_p)
    edited = [e.replace("\\", "/") for e in (state.get("edited_files") or [])]
    new: list[Finding] = []
    for f in findings:
        key = finding_key(f)
        if key in base:
            continue
        if only_edited and edited:
            fp = f.path.replace("\\", "/")
            if not any(
                fp == e
                or fp.endswith("/" + e.lstrip("./"))
                or e.endswith(fp)
                or fp.endswith(e)
                or e in fp
                for e in edited
            ):
                continue
        new.append(f)

    out["existing_debt"] = sum(1 for f in findings if finding_key(f) in base)
    out["new_findings"] = [f.to_dict() for f in new[:max_report]]
    out["new_count"] = len(new)
    out["prefix"] = report.profile.prefix
    out["edited_files"] = edited

    if new:
        out["ok"] = False
        out["summary"] = _format_new(new, report.profile.prefix, max_report)
    else:
        out["ok"] = True
        # clean: clear dirty so we don't re-gate forever
        state["dirty"] = False
        # optionally absorb remaining? no - keep baseline; agent can snapshot
        save_session_state(state, session_id)
    return out


def _format_new(findings: list[Finding], prefix: str, limit: int) -> str:
    lines = [
        f"Error Contract gate: {len(findings)} NEW violation(s) vs baseline (prefix={prefix}).",
        "Fix these before declaring the task complete (or justify + update baseline).",
        "",
    ]
    for f in findings[:limit]:
        loc = f"{f.path}:{f.line}" if f.line else f.path
        lines.append(f"- [{f.severity}] {f.rule} @ {loc}: {f.message}")
        if f.suggestion:
            lines.append(f"  -> {f.suggestion}")
    if len(findings) > limit:
        lines.append(f"... +{len(findings) - limit} more")
    lines.append("")
    lines.append("Commands: error-contract slap . | error-contract gate . | error-contract baseline .")
    return "\n".join(lines)


def format_preflight(result: dict[str, Any]) -> str:
    if not result.get("is_code_project"):
        return f"preflight: skip ({result.get('brief')})\n"
    return (result.get("brief") or "") + "\n"


def format_gate(result: dict[str, Any]) -> str:
    if result.get("skipped"):
        return f"gate: skip ({result.get('reason')})\n"
    if result.get("ok"):
        return (
            f"gate: OK - no new violations "
            f"(scanned={result.get('scanned')}, baseline_debt={result.get('existing_debt')})\n"
        )
    return (result.get("summary") or "gate: FAIL") + "\n"
