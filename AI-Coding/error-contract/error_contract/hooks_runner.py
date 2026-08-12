"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/hooks_runner.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Dual-harness hooks for Grok (camelCase) and Codex (snake_case).

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

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .ambient import (
    EDIT_TOOLS,
    gate,
    is_code_project,
    load_session_state,
    mark_edit,
    preflight,
    save_session_state,
)

# Codex apply_patch path markers
_PATCH_FILE_RE = re.compile(
    r"^\*\*\* (?:Update|Add|Delete|Rename) File: (.+)$",
    re.MULTILINE,
)


def _read_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))


def _g(event: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Read first present key (camelCase or snake_case)."""
    for k in keys:
        if k in event and event[k] is not None:
            return event[k]
    return default


def _workspace(event: dict[str, Any]) -> Path:
    for key in (
        "cwd",
        "workspaceRoot",
        "workspace_root",
        "CLAUDE_PROJECT_DIR",
    ):
        v = event.get(key)
        if v:
            try:
                return Path(str(v)).resolve()
            except OSError:
                return Path(str(v))
    wr = (
        os.environ.get("GROK_WORKSPACE_ROOT")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("CODEX_CWD")
    )
    if wr:
        return Path(wr).resolve()
    return Path.cwd().resolve()


def _session_id(event: dict[str, Any]) -> str:
    return str(_g(event, "session_id", "sessionId", default="") or "")


def _is_codex(event: dict[str, Any]) -> bool:
    """Heuristic: Codex uses snake_case hook_event_name + session_id."""
    if "hook_event_name" in event or "session_id" in event:
        return True
    if os.environ.get("CODEX_HOME") and not os.environ.get("GROK_HOOK_EVENT"):
        # weak signal - prefer payload shape
        pass
    return False


def _tool_name(event: dict[str, Any]) -> str:
    return str(_g(event, "tool_name", "toolName", default="") or "")


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    tin = _g(event, "tool_input", "toolInput", default={})
    return tin if isinstance(tin, dict) else {}


def _paths_from_tool(tool: str, tin: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for k in (
        "path",
        "file_path",
        "target_file",
        "filePath",
        "file",
        "targetFile",
    ):
        v = tin.get(k)
        if v:
            paths.append(str(v).replace("\\", "/"))
    # Codex apply_patch: tool_input.command holds the patch body
    cmd = tin.get("command")
    if isinstance(cmd, str) and (
        tool in {"apply_patch", "Edit", "Write", "Bash"} or "***" in cmd
    ):
        for m in _PATCH_FILE_RE.finditer(cmd):
            paths.append(m.group(1).strip().replace("\\", "/"))
        # also simple "path" lines in unified patches
        for m in re.finditer(r"(?m)^\+\+\+ [ab]/(.+)$", cmd):
            p = m.group(1).strip()
            if p != "/dev/null":
                paths.append(p.replace("\\", "/"))
    # dedupe
    out: list[str] = []
    for p in paths:
        if p and p not in out:
            out.append(p)
    return out


def _is_edit_tool(tool: str) -> bool:
    if not tool:
        return False
    if tool in EDIT_TOOLS:
        return True
    if tool in {"apply_patch", "Edit", "Write", "MultiEdit", "Bash"}:
        # Bash only if we extracted patch paths later
        return tool != "Bash"
    # MCP write-ish
    low = tool.lower()
    if "write" in low or "edit" in low or "patch" in low:
        return True
    return False


def handle_session_start(event: dict[str, Any]) -> int:
    root = _workspace(event)
    sid = _session_id(event)
    if not is_code_project(root):
        return 0
    try:
        result = preflight(root, session_id=sid)
    except Exception:
        return 0

    # Build brief for model context
    brief = ""
    try:
        state = load_session_state(sid)
        p = state.get("preflight") or {}
        if p:
            brief = (
                f"[Error Contract preflight]\n"
                f"status={p.get('status')} prefix={p.get('prefix')}\n"
                f"exceptions={p.get('exceptions_path') or '-'}\n"
                f"active={p.get('active_md')}\n"
                f"Use structured PREFIX-xxx errors; no print/console as error path.\n"
                f"If needs_onboard: ask human before inventing a prefix.\n"
                f"After edits, Stop gate runs error-contract gate (new findings only)."
            )
        elif result.get("brief"):
            brief = result["brief"][:2000]
    except Exception:
        brief = ""

    if not brief:
        return 0

    # Codex: JSON additionalContext OR plain text both inject as developer context.
    # Prefer JSON for structure. Grok may ignore SessionStart stdout - file still written.
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": brief,
            }
        }
    )
    return 0


def handle_post_tool_use(event: dict[str, Any]) -> int:
    tool = _tool_name(event)
    tin = _tool_input(event)
    paths = _paths_from_tool(tool, tin)

    # Codex apply_patch always relevant; Bash only if patch paths found
    if tool == "Bash" and not paths:
        return 0
    if not _is_edit_tool(tool) and not paths:
        return 0

    sid = _session_id(event)
    root = str(_workspace(event))
    try:
        if paths:
            for p in paths:
                mark_edit(
                    path=p,
                    tool_name="apply_patch" if tool in {"apply_patch", "Edit", "Write"} else tool,
                    session_id=sid,
                    workspace_root=root,
                )
        else:
            mark_edit(
                path="",
                tool_name=tool if tool in EDIT_TOOLS else "search_replace",
                session_id=sid,
                workspace_root=root,
            )
    except Exception:
        pass
    return 0


def handle_stop(event: dict[str, Any]) -> int:
    # Grok: reason == end_turn; Codex Stop fires at turn end (matcher ignored).
    # Codex session-end is SessionEnd, not Stop - so Stop here is turn gate.
    reason = str(_g(event, "reason", default="") or "")
    # Grok session-end fires Stop with channel_closed/shutdown - skip those
    if reason in {"channel_closed", "shutdown", "other"}:
        return 0

    root = _workspace(event)
    sid = _session_id(event)
    if not is_code_project(root):
        return 0

    state = load_session_state(sid)
    if state.get("gate_blocks", 0) >= 3:
        return 0
    stop_active = bool(_g(event, "stop_hook_active", "stopHookActive", default=False))
    if stop_active and state.get("gate_blocks", 0) >= 2:
        return 0

    if not state.get("preflight") or state.get("workspace_root") != str(root):
        try:
            preflight(root, session_id=sid)
            state = load_session_state(sid)
        except Exception:
            pass

    if not state.get("dirty"):
        return 0

    try:
        result = gate(root, session_id=sid, only_edited=True)
    except Exception as e:
        sys.stderr.write(f"error-contract gate error: {e}\n")
        return 0

    if result.get("skipped") or result.get("ok"):
        return 0

    state = load_session_state(sid)
    state["gate_blocks"] = int(state.get("gate_blocks") or 0) + 1
    save_session_state(state, sid)

    reason_text = result.get("summary") or (
        "Error Contract: new violations vs baseline. Fix before finishing."
    )
    # Codex + Grok both accept this shape. Do NOT add hookSpecificOutput on Stop (Codex rejects).
    _emit({"decision": "block", "reason": reason_text})
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    event = _read_stdin()
    name = ""
    if argv:
        name = argv[0].strip().lower().replace("-", "_")
    if not name:
        name = str(
            _g(event, "hook_event_name", "hookEventName", default="") or ""
        ).lower()
    name = name.replace("pretooluse", "pre_tool_use")
    mapping = {
        "sessionstart": "session_start",
        "session_start": "session_start",
        "posttooluse": "post_tool_use",
        "post_tool_use": "post_tool_use",
        "stop": "stop",
        "subagentstop": "stop",
        "subagent_stop": "stop",
    }
    name = mapping.get(name, name)

    if name == "session_start":
        return handle_session_start(event)
    if name == "post_tool_use":
        return handle_post_tool_use(event)
    if name == "stop":
        return handle_stop(event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
