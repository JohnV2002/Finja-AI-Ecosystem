"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / install_skills.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
  Description: Install Analytics Contract skills and always-active agent rules.

  New in v1.0.0:
    - Installs shared guidance for Codex, Grok, and Claude

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PACK = PLUGIN_ROOT / "skill-pack" / "analytics-contract"
BEGIN = "<!-- ANALYTICS_CONTRACT_BEGIN -->"
END = "<!-- ANALYTICS_CONTRACT_END -->"


def _upsert(path: Path, block: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8-sig", errors="ignore") if path.is_file() else ""
    marked = f"{BEGIN}\n{block.rstrip()}\n{END}"
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        finish = text.index(END, start) + len(END)
        text = text[:start].rstrip() + "\n\n" + marked + text[finish:]
        status = "updated"
    else:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + marked + "\n"
        status = "added"
    path.write_text(text, encoding="utf-8")
    return status


def install_skills() -> dict[str, Any]:
    home = Path.home()
    destinations = {
        "codex": home / ".codex" / "skills" / "analytics-contract",
        "grok": home / ".grok" / "skills" / "analytics-contract",
        "claude": home / ".claude" / "skills" / "analytics-contract",
    }
    for destination in destinations.values():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(PACK, destination)

    rules = (PACK / "ALWAYS_ACTIVE.md").read_text(encoding="utf-8")
    globals_result = {
        "codex": _upsert(home / ".codex" / "AGENTS.md", rules),
        "grok": _upsert(home / ".grok" / "AGENTS.md", rules),
        "claude": _upsert(home / ".claude" / "CLAUDE.md", rules),
    }
    state = home / ".analytics_contract"
    state.mkdir(parents=True, exist_ok=True)
    (state / "ENGINE_ROOT.txt").write_text(str(PLUGIN_ROOT) + os.linesep, encoding="utf-8")
    return {
        "version": "1.0.1",
        "engine_root": str(PLUGIN_ROOT),
        "skills": {key: str(value) for key, value in destinations.items()},
        "globals": globals_result,
    }

