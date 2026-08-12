"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/install_skills.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Install skills, ALWAYS ACTIVE rules, and lifecycle hooks for agents.

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
import re
import shutil
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_SRC = PLUGIN_ROOT / "skill-pack" / "error-contract"
ALWAYS_ACTIVE_SRC = SKILL_SRC / "ALWAYS_ACTIVE.md"
RULES_SRC = SKILL_SRC / "rules" / "error-contract.md"
HOOKS_TEMPLATE = PLUGIN_ROOT / "hooks" / "error-contract.json"

BEGIN = "<!-- ERROR_CONTRACT_BEGIN -->"
END = "<!-- ERROR_CONTRACT_END -->"


def _home() -> Path:
    return Path.home()


def target_dirs() -> dict[str, Path]:
    return {
        "grok": _home() / ".grok" / "skills" / "error-contract",
        "codex": _home() / ".codex" / "skills" / "error-contract",
        "claude": _home() / ".claude" / "skills" / "error-contract",
    }


def _copy_tree(src: Path, dst: Path) -> list[str]:
    written: list[str] = []
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for p in dst.rglob("*"):
        if p.is_file():
            written.append(str(p))
    return written


def always_active_block(engine_root: str) -> str:
    if ALWAYS_ACTIVE_SRC.is_file():
        text = ALWAYS_ACTIVE_SRC.read_text(encoding="utf-8-sig")
    else:
        text = f"""{BEGIN}
# Error Contract - ALWAYS ACTIVE
ENGINE_ROOT: __ENGINE_ROOT__
Never print/console.log errors. resolve -> onboard -> structured PREFIX-xxx.
{END}
"""
    return text.replace("__ENGINE_ROOT__", engine_root).strip() + "\n"


def upsert_marked_section(path: Path, block: str) -> str:
    """Insert or replace the ERROR_CONTRACT marked section. Always updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    block = block.strip() + "\n"
    if not path.is_file():
        path.write_text(block, encoding="utf-8")
        return "wrote"

    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    # Prefer HTML markers
    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        re.DOTALL,
    )
    # Use callable replacement - block paths contain Windows backslashes
    # which re.sub would treat as invalid escape sequences.
    def _repl(_m: re.Match[str]) -> str:
        return block.rstrip()

    if pattern.search(text):
        new_text = pattern.sub(_repl, text)
        if not new_text.endswith("\n"):
            new_text += "\n"
        path.write_text(new_text, encoding="utf-8")
        return "updated"

    # Legacy section without markers (first install from older pointer)
    legacy = re.compile(
        r"(?ms)^## Error Contract \(global\).*?(?=^## |\Z)"
    )
    if legacy.search(text):
        new_text = legacy.sub(_repl, text)
        path.write_text(new_text.rstrip() + "\n", encoding="utf-8")
        return "replaced-legacy"

    path.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    return "appended"


def install_grok_rules(engine_root: str) -> dict[str, str]:
    """~/.grok/rules/*.md is always scanned into context (stronger than skills)."""
    rules_dir = _home() / ".grok" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    dst = rules_dir / "error-contract.md"
    if RULES_SRC.is_file():
        text = RULES_SRC.read_text(encoding="utf-8-sig")
    else:
        text = "# Error Contract\nUse structured PREFIX-xxx errors. Run error-contract preflight.\n"
    text = text.replace("__ENGINE_ROOT__", engine_root)
    dst.write_text(text, encoding="utf-8")
    # Claude rules dir if present/compat
    claude_rules = _home() / ".claude" / "rules"
    claude_rules.mkdir(parents=True, exist_ok=True)
    cdst = claude_rules / "error-contract.md"
    cdst.write_text(text, encoding="utf-8")
    return {"grok": str(dst), "claude": str(cdst)}


def _write_hook_launcher(dir_path: Path, engine_root: str, name: str = "error-contract-hook.cmd") -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    launcher = dir_path / name
    # Prefer `py -3` on Windows when available via PATH; fall back to python
    launcher.write_text(
        f"""@echo off
set "PYTHONPATH={engine_root};%PYTHONPATH%"
where py >nul 2>&1 && (
  py -3 -m error_contract.hooks_runner %*
  exit /b %ERRORLEVEL%
)
python -m error_contract.hooks_runner %*
exit /b %ERRORLEVEL%
""",
        encoding="utf-8",
    )
    return launcher


def install_grok_hooks(engine_root: str) -> dict[str, str]:
    """Grok global hooks: SessionStart / PostToolUse / Stop."""
    hooks_dir = _home() / ".grok" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    if HOOKS_TEMPLATE.is_file():
        raw = HOOKS_TEMPLATE.read_text(encoding="utf-8-sig")
    else:
        raw = "{}"
    raw = raw.replace("__ENGINE_ROOT__", engine_root.replace("\\", "\\\\"))
    launcher = _write_hook_launcher(hooks_dir, engine_root)
    data = json.loads(raw) if raw.strip() else {"hooks": {}}
    for event, groups in list((data.get("hooks") or {}).items()):
        for group in groups:
            for h in group.get("hooks") or []:
                if h.get("type") == "command":
                    arg = {
                        "SessionStart": "session_start",
                        "PostToolUse": "post_tool_use",
                        "Stop": "stop",
                    }.get(event, event.lower())
                    h["command"] = f'"{launcher}" {arg}'
                    h.pop("env", None)
    dst = hooks_dir / "error-contract.json"
    dst.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"hooks_json": str(dst), "launcher": str(launcher)}


def install_codex_hooks(engine_root: str) -> dict[str, str]:
    """Codex-native hooks via ~/.codex/hooks.json (official discovery path).

    Codex 0.147+ (features.hooks stable=true):
      - SessionStart: stdout additionalContext -> developer context
      - PostToolUse matcher apply_patch|Edit|Write -> dirty files
      - Stop: {decision:block, reason} continues agent (no hookSpecificOutput!)

    Hooks must be trusted once via Codex `/hooks` UI before they run.
    """
    codex_home = _home() / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    scripts = codex_home / "hooks"
    scripts.mkdir(parents=True, exist_ok=True)
    launcher = _write_hook_launcher(scripts, engine_root, "error-contract-hook.cmd")

    template = PLUGIN_ROOT / "hooks" / "codex-hooks.json"
    if template.is_file():
        data = json.loads(template.read_text(encoding="utf-8-sig"))
    else:
        data = {"hooks": {}}

    # Absolute Windows-safe launcher commands (session cwd is project, not codex home)
    for event, groups in list((data.get("hooks") or {}).items()):
        for group in groups:
            for h in group.get("hooks") or []:
                if h.get("type") != "command":
                    continue
                arg = {
                    "SessionStart": "session_start",
                    "PostToolUse": "post_tool_use",
                    "Stop": "stop",
                }.get(event, "stop")
                # Codex: command can be string; commandWindows optional override
                cmd = f'"{launcher}" {arg}'
                h["command"] = cmd
                h["commandWindows"] = cmd
                h.pop("env", None)

    dst = codex_home / "hooks.json"
    # Merge carefully: if user already has hooks.json, only replace our EC block
    # by rewriting whole file if it's ours (description marker) or merging events.
    existing: dict[str, Any] = {}
    if dst.is_file():
        try:
            existing = json.loads(dst.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            existing = {}
    if existing.get("description", "").startswith("Error Contract ambient"):
        # full replace our file
        final = data
        status = "replaced"
    elif existing.get("hooks"):
        # merge our events into existing
        final = existing
        final.setdefault("hooks", {})
        for ev, groups in (data.get("hooks") or {}).items():
            # drop previous EC handlers (command contains error-contract-hook)
            old = final["hooks"].get(ev) or []
            kept = []
            for g in old:
                hs = []
                for h in g.get("hooks") or []:
                    c = str(h.get("command") or h.get("commandWindows") or "")
                    if "error-contract" not in c.lower():
                        hs.append(h)
                if hs:
                    ng = dict(g)
                    ng["hooks"] = hs
                    kept.append(ng)
            final["hooks"][ev] = kept + groups
        status = "merged"
    else:
        final = data
        status = "wrote"

    final["description"] = (
        "Error Contract ambient: preflight on SessionStart, dirty on apply_patch, "
        "gate on Stop (Codex-native). Trust via /hooks once."
    )
    dst.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")

    # Ensure features.hooks stays enabled (don't clobber whole config)
    cfg = codex_home / "config.toml"
    cfg_note = "unchanged"
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8-sig", errors="ignore")
        if re.search(r"(?m)^\s*hooks\s*=\s*false\b", text):
            cfg_note = "WARNING: features.hooks=false - set hooks=true"
        elif "[features]" in text and re.search(r"(?m)^\s*hooks\s*=\s*true\b", text):
            cfg_note = "hooks=true already"
        elif "[features]" in text:
            # append hooks = true under features if missing
            if not re.search(r"(?m)^\s*hooks\s*=", text):
                text2 = re.sub(
                    r"(?m)^(\[features\]\s*)$",
                    r"\1\nhooks = true  # error-contract ambient\n",
                    text,
                    count=1,
                )
                if text2 != text:
                    cfg.write_text(text2, encoding="utf-8")
                    cfg_note = "added hooks=true under [features]"
                else:
                    cfg_note = "features present; ensure hooks=true"
        else:
            cfg.write_text(
                text.rstrip()
                + "\n\n[features]\nhooks = true  # error-contract ambient\n",
                encoding="utf-8",
            )
            cfg_note = "appended [features] hooks=true"
    else:
        cfg.write_text(
            "# minimal config for Error Contract ambient hooks\n[features]\nhooks = true\n",
            encoding="utf-8",
        )
        cfg_note = "created config.toml with hooks=true"

    return {
        "hooks_json": str(dst),
        "launcher": str(launcher),
        "merge": status,
        "config": cfg_note,
        "trust_note": "Open Codex /hooks and trust Error Contract hooks once",
    }


def install_skills(
    *,
    engines: list[str] | None = None,
    write_global_agents: bool = True,
    engine_root: str | Path | None = None,
    always_active: bool = True,
    install_hooks: bool = True,
    install_rules: bool = True,
) -> dict[str, Any]:
    """Copy skill-pack + always-active rules + Grok hooks for ambient enforcement."""
    if not SKILL_SRC.is_dir():
        raise FileNotFoundError(f"Skill pack missing: {SKILL_SRC}")

    engine_root = str(Path(engine_root or PLUGIN_ROOT).resolve())
    wanted = set(engines or ["grok", "codex", "claude"])
    results: dict[str, Any] = {
        "engine_root": engine_root,
        "skills": {},
        "globals": {},
        "always_active": always_active,
    }

    targets = target_dirs()
    for name, dst in targets.items():
        if name not in wanted:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        files = _copy_tree(SKILL_SRC, dst)
        path_file = dst / "ENGINE_ROOT.txt"
        path_file.write_text(engine_root + "\n", encoding="utf-8")
        results["skills"][name] = {"dir": str(dst), "files": len(files) + 1}

    if write_global_agents and always_active:
        block = always_active_block(engine_root)
        globals_map = {
            "grok": _home() / ".grok" / "AGENTS.md",
            "codex": _home() / ".codex" / "AGENTS.md",
            "claude": _home() / ".claude" / "CLAUDE.md",
        }
        for name, gpath in globals_map.items():
            if name not in wanted:
                continue
            status = upsert_marked_section(gpath, block)
            results["globals"][name] = {"path": str(gpath), "status": status}

        always_copy = _home() / ".error_contract" / "ALWAYS_ACTIVE.md"
        always_copy.parent.mkdir(parents=True, exist_ok=True)
        always_copy.write_text(block, encoding="utf-8")
        results["always_active_file"] = str(always_copy)

    if install_rules and ("grok" in wanted or "claude" in wanted):
        results["rules"] = install_grok_rules(engine_root)
    if install_hooks:
        results["hooks"] = {}
        if "grok" in wanted:
            results["hooks"]["grok"] = install_grok_hooks(engine_root)
        if "codex" in wanted:
            results["hooks"]["codex"] = install_codex_hooks(engine_root)

    hint = _home() / ".error_contract" / "ENGINE_ROOT.txt"
    hint.parent.mkdir(parents=True, exist_ok=True)
    hint.write_text(engine_root + "\n", encoding="utf-8")
    results["hint_file"] = str(hint)
    return results


def format_install(result: dict[str, Any]) -> str:
    lines = [
        "=== error-contract ambient install ===",
        f"Engine : {result.get('engine_root')}",
        f"Hint   : {result.get('hint_file')}",
        f"Always : {result.get('always_active')}  ({result.get('always_active_file', '-')})",
        "",
        "Skills (optional deep-dive / slash):",
    ]
    for k, v in (result.get("skills") or {}).items():
        lines.append(f"  {k}: {v.get('dir')} ({v.get('files')} files)")
    lines.append("")
    lines.append("ALWAYS ACTIVE globals:")
    for k, v in (result.get("globals") or {}).items():
        lines.append(f"  {k}: [{v.get('status')}] {v.get('path')}")
    if result.get("rules"):
        lines.append("")
        lines.append("Grok/Claude rules (auto-injected every session):")
        for k, v in result["rules"].items():
            lines.append(f"  {k}: {v}")
    if result.get("hooks"):
        lines.append("")
        lines.append("Lifecycle hooks:")
        for eng, meta in result["hooks"].items():
            lines.append(f"  [{eng}]")
            if isinstance(meta, dict):
                for k, v in meta.items():
                    lines.append(f"    {k}: {v}")
            else:
                lines.append(f"    {meta}")
        lines.append("  Grok: /hooks -> reload (r) or new session")
        lines.append("  Codex: /hooks -> review & trust Error Contract hooks once")
    lines.append("")
    lines.append("Ambient CLI: error-contract preflight . | gate . | slap .")
    return "\n".join(lines) + "\n"
