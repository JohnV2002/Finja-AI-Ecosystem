#!/usr/bin/env python3
"""
Find / strip UTF-8 BOMs (U+FEFF / ef bb bf) in text sources.

Why: a leading BOM breaks `ast.parse` (and some tools), which made
dependency_guard miss real imports (e.g. pygame in mouth.py).

Usage:
  python tools/fix_bom.py                 # scan, print, exit 1 if any BOM
  python tools/fix_bom.py --fix           # rewrite files without BOM
  python tools/fix_bom.py --check          # CI mode: fail if BOM found (no write)
  python tools/fix_bom.py --root . --ext py,md,yml

Exit codes:
  0 = clean (or fixed successfully with --fix)
  1 = BOM found (--check / default report) or fix failed
  2 = usage / path error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Set

UTF8_BOM = b"\xef\xbb\xbf"

DEFAULT_EXTS = {
    "py",
    "pyi",
    "md",
    "txt",
    "yml",
    "yaml",
    "toml",
    "json",
    "cfg",
    "ini",
    "env",
    "example",
    "html",
    "css",
    "js",
    "ts",
    "tsx",
    "jsx",
    "sh",
    "bat",
    "ps1",
    "rhai",
    "csv",
    "svg",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".tox",
    "dist",
    "build",
    "gallery",
    "test_frames",
    "Not Maintained",
    ".claude",
}


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.startswith(".")


def iter_files(root: Path, exts: Set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(should_skip_dir(part) for part in path.parts):
            continue
        # extension: ".env.example" -> treat last suffix, also bare "Dockerfile" skip
        suf = path.suffix.lstrip(".").lower()
        if suf in exts or path.name.lower() in {
            "dockerfile",
            "makefile",
            "requirements.txt",
            "license",
            "notice",
        }:
            yield path
        elif path.name.endswith(".txt") or path.name.endswith(".in"):
            yield path


def has_bom(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(3)
        return head == UTF8_BOM
    except OSError:
        return False


def strip_bom(path: Path) -> bool:
    """Return True if a BOM was removed."""
    try:
        data = path.read_bytes()
    except OSError as e:
        print(f"  ERROR read {path}: {e}", file=sys.stderr)
        return False
    if not data.startswith(UTF8_BOM):
        return False
    try:
        path.write_bytes(data[len(UTF8_BOM) :])
    except OSError as e:
        print(f"  ERROR write {path}: {e}", file=sys.stderr)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find/strip UTF-8 BOMs in source files")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: parent of tools/)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite files without BOM",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: exit 1 if any BOM remains (no write unless combined with --fix)",
    )
    parser.add_argument(
        "--ext",
        type=str,
        default=",".join(sorted(DEFAULT_EXTS)),
        help="Comma-separated extensions (no dots)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = (args.root or Path(__file__).resolve().parent.parent).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    exts = {e.strip().lstrip(".").lower() for e in args.ext.split(",") if e.strip()}
    found: List[Path] = []

    for path in sorted(iter_files(root, exts)):
        if has_bom(path):
            found.append(path)

    if not found:
        print("BOM check: clean (no UTF-8 BOM found)")
        return 0

    print(f"BOM check: {len(found)} file(s) with UTF-8 BOM:")
    for path in found:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"  • {rel}")

    if args.fix:
        ok = 0
        for path in found:
            if strip_bom(path):
                ok += 1
                try:
                    rel = path.relative_to(root)
                except ValueError:
                    rel = path
                print(f"  fixed: {rel}")
        remaining = [p for p in found if has_bom(p)]
        if remaining:
            print(f"BOM check: {len(remaining)} still have BOM after fix", file=sys.stderr)
            return 1
        print(f"BOM check: fixed {ok} file(s)")
        return 0

    # report / CI check without fix
    if args.check or not args.fix:
        print("Hint: run  python tools/fix_bom.py --fix  to strip them")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
