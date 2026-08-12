"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / install_skills
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.1
  Description: Install skill + ALWAYS ACTIVE rules + hooks for Grok/Codex/Claude.

  New in v1.1.0:
    - Ships the cross-project AI-Coding identity to every agent

  New in v1.0.1:
    - Aligned installed package metadata with the bugfix release

  New in v1.0.0:
    - Parity with error-contract install pattern

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
SKILL_SRC = PLUGIN_ROOT / "skill-pack" / "github-contract"
ALWAYS_ACTIVE_SRC = SKILL_SRC / "ALWAYS_ACTIVE.md"
RULES_SRC = SKILL_SRC / "rules" / "github-contract.md"
BEGIN = "<!-- GITHUB_CONTRACT_BEGIN -->"
END = "<!-- GITHUB_CONTRACT_END -->"


def _home() -> Path:
    return Path.home()


def target_dirs() -> dict[str, Path]:
    return {
        "grok": _home() / ".grok" / "skills" / "github-contract",
        "codex": _home() / ".codex" / "skills" / "github-contract",
        "claude": _home() / ".claude" / "skills" / "github-contract",
    }


def _copy_tree(src: Path, dst: Path) -> int:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return sum(1 for p in dst.rglob("*") if p.is_file())


def always_active_block(engine_root: str) -> str:
    if ALWAYS_ACTIVE_SRC.is_file():
        text = ALWAYS_ACTIVE_SRC.read_text(encoding="utf-8-sig")
    else:
        text = f"""{BEGIN}
# GitHub Contract - ALWAYS ACTIVE
When in git/GitHub/public modules: headers + unified version MAJOR.FEATURES.BUGS + no secret leaks.
ENGINE_ROOT: __ENGINE_ROOT__
{END}
"""
    return text.replace("__ENGINE_ROOT__", engine_root).strip() + "\n"


def upsert_marked_section(path: Path, block: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = block.strip() + "\n"
    if not path.is_file():
        path.write_text(block, encoding="utf-8")
        return "wrote"
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)

    def _repl(_m: re.Match[str]) -> str:
        return block.rstrip()

    if pattern.search(text):
        path.write_text(pattern.sub(_repl, text).rstrip() + "\n", encoding="utf-8")
        return "updated"
    path.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    return "appended"


def _launcher(dir_path: Path, engine_root: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    launcher = dir_path / "github-contract-hook.cmd"
    launcher.write_text(
        f"""@echo off
set "PYTHONPATH={engine_root};%PYTHONPATH%"
where py >nul 2>&1 && (
  py -3 -m github_contract.hooks_runner %*
  exit /b %ERRORLEVEL%
)
python -m github_contract.hooks_runner %*
exit /b %ERRORLEVEL%
""",
        encoding="utf-8",
    )
    return launcher


def install_grok_hooks(engine_root: str) -> dict[str, str]:
    hooks_dir = _home() / ".grok" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    launcher = _launcher(hooks_dir, engine_root)
    data = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{launcher}" session_start',
                            "timeout": 45,
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{launcher}" stop',
                            "timeout": 120,
                        }
                    ]
                }
            ],
        }
    }
    # merge into file if error-contract already there — separate file name
    dst = hooks_dir / "github-contract.json"
    dst.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"hooks_json": str(dst), "launcher": str(launcher)}


def install_codex_hooks(engine_root: str) -> dict[str, str]:
    codex = _home() / ".codex"
    scripts = codex / "hooks"
    scripts.mkdir(parents=True, exist_ok=True)
    launcher = _launcher(scripts, engine_root)
    entry = {
        "description": "GitHub Contract ambient (headers/version/no-leak). Trust via /hooks.",
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{launcher}" session_start',
                            "commandWindows": f'"{launcher}" session_start',
                            "statusMessage": "GitHub Contract preflight",
                            "timeout": 45,
                            "additionalContextLimit": 4000,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{launcher}" stop',
                            "commandWindows": f'"{launcher}" stop',
                            "statusMessage": "GitHub Contract gate",
                            "timeout": 120,
                        }
                    ]
                }
            ],
        },
    }
    dst = codex / "hooks-github-contract.json"
    # Codex discovers hooks.json next to config — merge into hooks.json
    main = codex / "hooks.json"
    if main.is_file():
        try:
            existing = json.loads(main.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            existing = {"hooks": {}}
        hooks = existing.setdefault("hooks", {})
        # strip previous github-contract handlers
        for ev in list(hooks.keys()):
            groups = hooks[ev] or []
            kept = []
            for g in groups:
                hs = [
                    h
                    for h in (g.get("hooks") or [])
                    if "github-contract" not in str(h.get("command") or "").lower()
                ]
                if hs:
                    ng = dict(g)
                    ng["hooks"] = hs
                    kept.append(ng)
            hooks[ev] = kept
        for ev, groups in entry["hooks"].items():
            hooks.setdefault(ev, []).extend(groups)
        if "GitHub Contract" not in str(existing.get("description") or ""):
            existing["description"] = (
                (existing.get("description") or "") + " + GitHub Contract ambient"
            ).strip(" +")
        main.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        status = "merged-hooks.json"
    else:
        main.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        status = "wrote-hooks.json"
    dst.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")

    cfg = codex / "config.toml"
    cfg_note = "unchanged"
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8-sig", errors="ignore")
        if not re.search(r"(?m)^\s*hooks\s*=\s*true\b", text):
            if "[features]" in text and not re.search(r"(?m)^\s*hooks\s*=", text):
                text = re.sub(
                    r"(?m)^(\[features\]\s*)$",
                    r"\1\nhooks = true  # github-contract ambient\n",
                    text,
                    count=1,
                )
                cfg.write_text(text, encoding="utf-8")
                cfg_note = "hooks=true ensured"
            elif "[features]" not in text:
                cfg.write_text(
                    text.rstrip() + "\n\n[features]\nhooks = true\n", encoding="utf-8"
                )
                cfg_note = "appended features.hooks"
    return {
        "hooks_json": str(main),
        "launcher": str(launcher),
        "merge": status,
        "config": cfg_note,
        "trust_note": "Codex CLI: /hooks and trust GitHub Contract hooks",
    }


def install_skills(
    *,
    engines: list[str] | None = None,
    engine_root: str | Path | None = None,
    always_active: bool = True,
    install_hooks: bool = True,
) -> dict[str, Any]:
    if not SKILL_SRC.is_dir():
        raise FileNotFoundError(f"Missing skill pack: {SKILL_SRC}")
    engine_root = str(Path(engine_root or PLUGIN_ROOT).resolve())
    wanted = set(engines or ["grok", "codex", "claude"])
    results: dict[str, Any] = {
        "engine_root": engine_root,
        "skills": {},
        "globals": {},
        "version": "1.1.1",
    }

    for name, dst in target_dirs().items():
        if name not in wanted:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        n = _copy_tree(SKILL_SRC, dst)
        (dst / "ENGINE_ROOT.txt").write_text(engine_root + "\n", encoding="utf-8")
        results["skills"][name] = {"dir": str(dst), "files": n + 1}

    if always_active:
        block = always_active_block(engine_root)
        globals_map = {
            "grok": _home() / ".grok" / "AGENTS.md",
            "codex": _home() / ".codex" / "AGENTS.md",
            "claude": _home() / ".claude" / "CLAUDE.md",
        }
        for name, gpath in globals_map.items():
            if name not in wanted:
                continue
            results["globals"][name] = {
                "path": str(gpath),
                "status": upsert_marked_section(gpath, block),
            }
        # rules
        if RULES_SRC.is_file() and "grok" in wanted:
            rd = _home() / ".grok" / "rules"
            rd.mkdir(parents=True, exist_ok=True)
            (rd / "github-contract.md").write_text(
                RULES_SRC.read_text(encoding="utf-8-sig"), encoding="utf-8"
            )
            results["rules"] = str(rd / "github-contract.md")
        if RULES_SRC.is_file() and "claude" in wanted:
            rd = _home() / ".claude" / "rules"
            rd.mkdir(parents=True, exist_ok=True)
            (rd / "github-contract.md").write_text(
                RULES_SRC.read_text(encoding="utf-8-sig"), encoding="utf-8"
            )

    if install_hooks:
        results["hooks"] = {}
        if "grok" in wanted:
            results["hooks"]["grok"] = install_grok_hooks(engine_root)
        if "codex" in wanted:
            results["hooks"]["codex"] = install_codex_hooks(engine_root)

    hint = _home() / ".github_contract" / "ENGINE_ROOT.txt"
    hint.parent.mkdir(parents=True, exist_ok=True)
    hint.write_text(engine_root + "\n", encoding="utf-8")
    results["hint_file"] = str(hint)

    # PATH shim
    for b in (
        _home() / ".grok" / "bin",
        _home() / ".github_contract" / "bin",
        _home() / ".local" / "bin",
    ):
        b.mkdir(parents=True, exist_ok=True)
        cmd = b / "github-contract.cmd"
        cmd.write_text(
            f"""@echo off
setlocal
set "ENGINE={engine_root}"
if exist "%USERPROFILE%\\.github_contract\\ENGINE_ROOT.txt" (
  set /p ENGINE=<"%USERPROFILE%\\.github_contract\\ENGINE_ROOT.txt"
)
set "PYTHONPATH=%ENGINE%;%PYTHONPATH%"
python -m github_contract %*
exit /b %ERRORLEVEL%
""",
            encoding="utf-8",
        )
    results["path_cmd"] = str(_home() / ".grok" / "bin" / "github-contract.cmd")
    return results


def format_install(result: dict[str, Any]) -> str:
    lines = [
        "=== github-contract ambient install ===",
        f"Version: {result.get('version')}",
        f"Engine : {result.get('engine_root')}",
        f"Hint   : {result.get('hint_file')}",
        f"PATH   : {result.get('path_cmd')}",
        "",
        "Skills:",
    ]
    for k, v in (result.get("skills") or {}).items():
        lines.append(f"  {k}: {v.get('dir')}")
    lines.append("")
    lines.append("ALWAYS ACTIVE globals:")
    for k, v in (result.get("globals") or {}).items():
        lines.append(f"  {k}: [{v.get('status')}] {v.get('path')}")
    if result.get("hooks"):
        lines.append("")
        lines.append("Hooks:")
        for eng, meta in result["hooks"].items():
            lines.append(f"  [{eng}] {meta}")
        lines.append("  Codex: /hooks -> trust GitHub Contract once")
        lines.append("  Grok: new session or /hooks reload")
    lines.append("")
    lines.append("CLI: github-contract preflight . | scan . | check-version .")
    return "\n".join(lines) + "\n"
