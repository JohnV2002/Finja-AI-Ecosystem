"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/detect.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Detect exception systems and project prefixes in a repository tree.

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

import re
from pathlib import Path
from typing import Iterable, Optional

from .models import ProjectProfile, Taxonomy
from .taxonomy import (
    finja_reference_taxonomy,
    merge_prefix_from_config,
    parse_contract_json,
    parse_exceptions_py,
)

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".idea",
    ".vs",
    ".next",
    "target",
    "bin",
    "obj",
}

EXCEPTION_CANDIDATES = (
    "exceptions.py",
    "errors.py",
    "error_codes.py",
    "error.py",
    "app_errors.py",
)

CONTRACT_CANDIDATES = (
    "error_contract.json",
    "error_contract.module.json",
    "errors.json",
    "taxonomy.json",
)


def iter_files(root: Path, suffixes: Iterable[str], max_files: int = 8000) -> list[Path]:
    out: list[Path] = []
    suf = tuple(suffixes)
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in suf:
            continue
        out.append(p)
        if len(out) >= max_files:
            break
    return out


def _find_named(root: Path, names: tuple[str, ...], max_hits: int = 40) -> list[Path]:
    hits: list[Path] = []
    lower_names = {n.lower() for n in names}
    # Prefer shallow, known locations first (fast path on large monorepos / NAS)
    preferred = [
        root / "core" / "exceptions.py",
        root / "exceptions.py",
        root / "src" / "exceptions.py",
        root / "app" / "exceptions.py",
        root / "contracts" / "error_contract.json",
        root / "contracts" / "error_contract.module.json",
        root / "error_contract.json",
    ]
    for p in preferred:
        if p.is_file() and p.name.lower() in lower_names:
            hits.append(p)
    if hits:
        return hits

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name.lower() in lower_names:
            hits.append(p)
            if len(hits) >= max_hits:
                break
    # Prefer core/exceptions.py style paths
    def score(path: Path) -> tuple[int, int, str]:
        s = 0
        parts = [x.lower() for x in path.parts]
        if "core" in parts:
            s -= 10
        if path.name.lower() == "exceptions.py":
            s -= 5
        return (s, len(path.parts), str(path).lower())

    return sorted(hits, key=score)


def _guess_prefix_from_sources(root: Path, tax: Optional[Taxonomy]) -> str:
    if tax and tax.prefix and tax.prefix != "APP":
        return tax.prefix
    # branded codes in tree
    counts: dict[str, int] = {}
    pattern = re.compile(r"\b([A-Z][A-Z0-9]{1,12})-(\d{2,4})\b")
    for p in iter_files(root, {".py", ".ts", ".js", ".tsx", ".jsx", ".md", ".json"}, max_files=2000):
        try:
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        for m in pattern.finditer(text):
            pref = m.group(1).upper()
            if pref in {"HTTP", "UTF", "ISO", "RFC", "CVE", "UUID", "SHA", "MD5"}:
                continue
            counts[pref] = counts.get(pref, 0) + 1
    if counts:
        return max(counts.items(), key=lambda kv: kv[1])[0]
    # folder name heuristic
    name = root.name.upper()
    for token in ("FINJA", "MILK", "AST", "FEUER", "MILKY", "ASTEROID"):
        if token in name:
            if token == "MILKY":
                return "MILK"
            if token == "ASTEROID":
                return "AST"
            return token
    return "APP"


def detect_project(root: str | Path, prefix: str = "") -> ProjectProfile:
    root = Path(root).resolve()
    profile = ProjectProfile(root=str(root))

    # 0) Dynamic registry (user-global) - beats path heuristics, no hard-coded project list
    registry_prefix = ""
    try:
        from .registry import load_registry

        reg = load_registry()
        hit = reg.match_path(root)
        if hit:
            registry_prefix = hit.effective_prefix(reg)
            profile.detected_systems.append(f"registry:{hit.id}")
            profile.notes.append(
                f"Registry: id={hit.id} mode={hit.mode} prefix={registry_prefix}"
                + (f" module={hit.module_default}" if hit.module_default else "")
            )
            if not prefix:
                prefix = registry_prefix
    except Exception as e:  # registry must never break detect
        profile.notes.append(f"Registry lookup skipped: {e}")

    # 1) JSON contract
    contract_hits = _find_named(root, CONTRACT_CANDIDATES)
    # also contracts/
    for sub in (root / "contracts", root / "error_contract", root / ".error_contract"):
        if sub.is_dir():
            for p in sub.glob("*.json"):
                contract_hits.append(p)

    # 2) exceptions.py style
    exc_hits = _find_named(root, EXCEPTION_CANDIDATES)

    taxonomy: Optional[Taxonomy] = None

    if exc_hits:
        best = exc_hits[0]
        profile.exceptions_path = str(best)
        try:
            taxonomy = parse_exceptions_py(best, prefix_hint=prefix)
            profile.detected_systems.append(f"finja_style:{best.name}")
        except OSError as e:
            profile.notes.append(f"Failed to read {best}: {e}")

    if contract_hits and taxonomy is None:
        best_c = contract_hits[0]
        profile.contract_path = str(best_c)
        try:
            taxonomy = parse_contract_json(best_c, prefix_hint=prefix)
            profile.detected_systems.append(f"json_contract:{best_c.name}")
        except (OSError, ValueError) as e:
            profile.notes.append(f"Failed to parse contract {best_c}: {e}")
    elif contract_hits:
        profile.contract_path = str(contract_hits[0])

    # 3) signals without full taxonomy (cheap sample; skip pure docs noise)
    py_files = iter_files(root, {".py"}, max_files=400)
    joined_sample = []
    for p in py_files[:40]:
        try:
            joined_sample.append(p.read_text(encoding="utf-8-sig", errors="ignore")[:3000])
        except OSError:
            pass
    blob = "\n".join(joined_sample)
    if "set_code_prefix" in blob:
        profile.detected_systems.append("set_code_prefix")
    if "for_dashboard" in blob:
        profile.detected_systems.append("for_dashboard")
    if "ErrorInbox" in blob or "error_inbox" in blob:
        profile.detected_systems.append("error_inbox")
    # Only flag real JS/TS console usage, not docstring mentions in .py
    js_files = iter_files(root, {".js", ".ts", ".tsx", ".jsx"}, max_files=80)
    js_blob = ""
    for p in js_files[:30]:
        try:
            js_blob += p.read_text(encoding="utf-8-sig", errors="ignore")[:2000]
        except OSError:
            pass
    if re.search(r"console\.(log|error|warn)", js_blob):
        profile.detected_systems.append("js_console")
    if re.search(r"\bprint\s*\(", blob):
        profile.detected_systems.append("python_print")

    if taxonomy is None:
        # No SoT - empty taxonomy with guessed/forced prefix
        taxonomy = Taxonomy(prefix=(prefix or "APP").upper(), source="", style="missing")
        profile.notes.append(
            "No structured exception Source-of-Truth found "
            "(exceptions.py / error_contract.json). Scaffold recommended."
        )
        profile.detected_systems.append("missing_taxonomy")
    else:
        if prefix:
            taxonomy.prefix = prefix.upper()
        else:
            taxonomy = merge_prefix_from_config(taxonomy, root)
            if taxonomy.prefix == "APP":
                taxonomy.prefix = _guess_prefix_from_sources(root, taxonomy)

    profile.prefix = (prefix or taxonomy.prefix or "APP").upper()
    taxonomy.prefix = profile.prefix
    profile.taxonomy = taxonomy

    # Finja special case: if we clearly are the Nervenzentrale, stamp FINJA
    root_u = root.as_posix().upper()
    if not prefix and ("NERVEN" in root_u or "FINJA" in root.name.upper()):
        if profile.prefix == "APP" and taxonomy.has_app_error:
            profile.prefix = "FINJA"
            taxonomy.prefix = "FINJA"
            profile.notes.append("Prefix defaulted to FINJA (path heuristic).")

    return profile


def load_taxonomy_for(root: str | Path, prefix: str = "", use_finja_builtin: bool = False) -> tuple[ProjectProfile, Taxonomy]:
    if use_finja_builtin:
        tax = finja_reference_taxonomy()
        if prefix:
            tax.prefix = prefix.upper()
        prof = ProjectProfile(root=str(Path(root).resolve()), prefix=tax.prefix, taxonomy=tax)
        prof.detected_systems.append("builtin:finja")
        return prof, tax
    prof = detect_project(root, prefix=prefix)
    assert prof.taxonomy is not None
    return prof, prof.taxonomy
