"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / detect
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Detect git / GitHub / public-production context for a tree.

  New in v1.1.0:
    - Reframed detection as cross-project AI-Coding tooling

  New in v1.0.1:
    - Discover all commentable source/config types used by Finja modules
    - Ignore generated Error Contract and GitHub Contract state

  New in v1.0.0:
    - is_git, GitHub remote, LICENSE, .github signals
    - Module name + declared version heuristics

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .headers import extract_version
from .models import ModuleProfile

SKIP = {
    ".git",
    ".hg",
    ".error_contract",
    ".github_contract",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "gallery",
    "cache",
}


def detect_module(root: str | Path) -> ModuleProfile:
    root_p = Path(root).expanduser().resolve()
    prof = ModuleProfile(root=str(root_p), module_name=root_p.name)

    if (root_p / ".git").exists():
        prof.is_git = True
        prof.signals.append("dot_git")

    # remote url
    cfg = root_p / ".git" / "config"
    if cfg.is_file():
        try:
            text = cfg.read_text(encoding="utf-8", errors="ignore")
            if "github.com" in text.lower():
                prof.is_githubish = True
                prof.signals.append("github_remote")
        except OSError:
            pass

    for name in ("LICENSE", "LICENSE.md", "SECURITY.md", "CONTRIBUTING.md"):
        if (root_p / name).is_file():
            prof.signals.append(name.lower())
    if (root_p / ".github").is_dir():
        prof.is_githubish = True
        prof.signals.append("dot_github")
    if (root_p / "README.md").is_file() or (root_p / "readme.md").is_file():
        prof.signals.append("readme")

    # parent monorepo git counts as public-capable
    parent = root_p.parent
    for _ in range(4):
        if (parent / ".git").exists():
            prof.is_git = True
            prof.signals.append("parent_git")
            pcfg = parent / ".git" / "config"
            if pcfg.is_file():
                try:
                    if "github.com" in pcfg.read_text(encoding="utf-8", errors="ignore").lower():
                        prof.is_githubish = True
                        prof.signals.append("parent_github_remote")
                except OSError:
                    pass
            break
        if parent.parent == parent:
            break
        parent = parent.parent

    # pyproject version
    pyproj = root_p / "pyproject.toml"
    if pyproj.is_file():
        try:
            t = pyproj.read_text(encoding="utf-8-sig", errors="ignore")
            m = re.search(r'(?m)^\s*version\s*=\s*["\'](\d+\.\d+\.\d+)["\']', t)
            if m:
                prof.declared_version = m.group(1)
                prof.signals.append("pyproject_version")
        except OSError:
            pass

    # package.json
    pkg = root_p / "package.json"
    if pkg.is_file() and not prof.declared_version:
        try:
            data = json.loads(pkg.read_text(encoding="utf-8-sig"))
            v = str(data.get("version") or "")
            if re.fullmatch(r"\d+\.\d+\.\d+", v):
                prof.declared_version = v
                prof.signals.append("package_json_version")
        except (OSError, json.JSONDecodeError):
            pass

    # sample headers for version majority
    versions: dict[str, int] = {}
    for p in _iter_source(root_p, max_files=400):
        try:
            text = p.read_text(encoding="utf-8-sig", errors="ignore")[:5000]
        except OSError:
            continue
        v = extract_version(text)
        if v:
            versions[v] = versions.get(v, 0) + 1
    prof.versions_found = dict(sorted(versions.items(), key=lambda kv: -kv[1]))
    if not prof.declared_version and prof.versions_found:
        prof.declared_version = next(iter(prof.versions_found))

    if prof.is_git or prof.is_githubish or "readme" in prof.signals:
        prof.notes.append(
            "GitHub-Contract applies: headers, unified module version "
            "MAJOR.FEATURES.BUGS, no secrets in public tree."
        )
    return prof


def _iter_source(root: Path, max_files: int = 500):
    suf = {
        ".py",
        ".bat",
        ".cmd",
        ".html",
        ".htm",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".ps1",
        ".sh",
        ".css",
        ".php",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".java",
        ".cs",
        ".go",
        ".rs",
        ".vue",
        ".svelte",
        ".yml",
        ".yaml",
        ".toml",
        ".svg",
    }
    n = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP for part in p.parts):
            continue
        if p.suffix.lower() not in suf and p.name.lower() not in {
            "dockerfile",
            "makefile",
        }:
            continue
        yield p
        n += 1
        if n >= max_files:
            break
