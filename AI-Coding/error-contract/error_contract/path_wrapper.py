"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/path_wrapper.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    Install global error-contract PATH shim (Windows .cmd / Unix shell).

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

import os
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _home() -> Path:
    return Path.home()


def preferred_bin_dirs() -> list[Path]:
    """Dirs we install into. Prefer ones already on PATH."""
    path_env = os.environ.get("Path") or os.environ.get("PATH") or ""
    on_path = {p.lower().rstrip("\\/") for p in path_env.split(os.pathsep) if p}

    candidates = [
        _home() / ".error_contract" / "bin",
        _home() / ".grok" / "bin",
        _home() / ".local" / "bin",
        _home() / "bin",
    ]
    # Order: on PATH first, then our home dir
    ranked: list[Path] = []
    for c in candidates:
        key = str(c).lower().rstrip("\\/")
        if key in on_path:
            ranked.append(c)
    for c in candidates:
        if c not in ranked:
            ranked.append(c)
    return ranked


def _cmd_script(engine_root: str) -> str:
    # %* forwards all args; set PYTHONPATH so -m error_contract always resolves
    return f"""@echo off
setlocal
set "ERROR_CONTRACT_ENGINE={engine_root}"
if exist "%USERPROFILE%\\.error_contract\\ENGINE_ROOT.txt" (
  set /p ERROR_CONTRACT_ENGINE=<"%USERPROFILE%\\.error_contract\\ENGINE_ROOT.txt"
)
set "PYTHONPATH=%ERROR_CONTRACT_ENGINE%;%PYTHONPATH%"
python -m error_contract %*
exit /b %ERRORLEVEL%
"""


def _ps1_script(engine_root: str) -> str:
    return f"""# error-contract shim - always-on CLI without cd into the plugin repo
$engine = "{engine_root}"
$hint = Join-Path $env:USERPROFILE ".error_contract\\ENGINE_ROOT.txt"
if (Test-Path $hint) {{
  $line = (Get-Content -Path $hint -TotalCount 1 -ErrorAction SilentlyContinue)
  if ($line) {{ $engine = $line.Trim() }}
}}
$env:PYTHONPATH = if ($env:PYTHONPATH) {{ "$engine;$env:PYTHONPATH" }} else {{ $engine }}
python -m error_contract @args
exit $LASTEXITCODE
"""


def _sh_script(engine_root: str) -> str:
    return f"""#!/usr/bin/env bash
# error-contract shim
ENGINE="{engine_root}"
HINT="${{HOME}}/.error_contract/ENGINE_ROOT.txt"
if [[ -f "$HINT" ]]; then
  ENGINE="$(head -n 1 "$HINT" | tr -d '\\r')"
fi
export PYTHONPATH="${{ENGINE}}${{PYTHONPATH:+:$PYTHONPATH}}"
exec python -m error_contract "$@"
"""


def ensure_user_path_contains(bin_dir: Path) -> dict[str, Any]:
    """Append bin_dir to the user PATH on Windows if missing."""
    if os.name != "nt":
        return {"status": "skip-non-windows", "dir": str(bin_dir)}
    try:
        import winreg  # type: ignore
    except ImportError:
        return {"status": "skip-no-winreg", "dir": str(bin_dir)}

    key_path = r"Environment"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""
        parts = [p for p in current.split(";") if p]
        norm = {p.lower().rstrip("\\/") for p in parts}
        target = str(bin_dir)
        if target.lower().rstrip("\\/") in norm:
            return {"status": "already-on-path", "dir": target}
        new_val = (current.rstrip(";") + ";" + target) if current else target
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_val)
    # Broadcast is best-effort; new shells pick it up
    return {"status": "added-to-user-path", "dir": target, "note": "Open a new terminal for PATH"}


def install_path_wrapper(engine_root: str | Path | None = None) -> dict[str, Any]:
    engine_root = str(Path(engine_root or PLUGIN_ROOT).resolve())
    hint = _home() / ".error_contract" / "ENGINE_ROOT.txt"
    hint.parent.mkdir(parents=True, exist_ok=True)
    hint.write_text(engine_root + "\n", encoding="utf-8")

    written: list[str] = []
    bins = preferred_bin_dirs()
    primary = bins[0]
    primary.mkdir(parents=True, exist_ok=True)

    # Always write into primary + any already-on-PATH bins (max 3)
    targets: list[Path] = []
    for b in bins[:3]:
        if b not in targets:
            targets.append(b)

    for b in targets:
        b.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            cmd = b / "error-contract.cmd"
            cmd.write_text(_cmd_script(engine_root), encoding="utf-8")
            written.append(str(cmd))
            ps1 = b / "error-contract.ps1"
            ps1.write_text(_ps1_script(engine_root), encoding="utf-8")
            written.append(str(ps1))
        else:
            sh = b / "error-contract"
            sh.write_text(_sh_script(engine_root), encoding="utf-8")
            sh.chmod(0o755)
            written.append(str(sh))

    path_result = ensure_user_path_contains(primary)

    return {
        "engine_root": engine_root,
        "primary_bin": str(primary),
        "written": written,
        "path": path_result,
        "invoke": "error-contract resolve .",
        "python": sys.executable,
    }


def format_path_install(result: dict[str, Any]) -> str:
    lines = [
        "=== error-contract PATH wrapper ===",
        f"Engine : {result.get('engine_root')}",
        f"Bin    : {result.get('primary_bin')}",
        f"PATH   : {result.get('path')}",
        "",
        "Written:",
    ]
    for w in result.get("written") or []:
        lines.append(f"  {w}")
    lines.append("")
    lines.append("Usage (any directory, no cd):")
    lines.append("  error-contract resolve .")
    lines.append("  error-contract slap .")
    lines.append("  error-contract ensure . --scaffold")
    note = (result.get("path") or {}).get("note")
    if note:
        lines.append(f"Note: {note}")
    return "\n".join(lines) + "\n"
