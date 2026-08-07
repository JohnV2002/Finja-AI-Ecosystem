#!/usr/bin/env python3
"""
Compile every requirements.in in the monorepo via pip-compile (pip-tools).

Opt-in model:
  - Only directories that contain requirements.in are compiled.
  - Generated requirements.txt is written next to the .in file.
  - CI can run this and then `git diff --exit-code` to catch forgotten compiles.

Usage:
  python tools/compile_all_requirements.py
  python tools/compile_all_requirements.py --upgrade
  python tools/compile_all_requirements.py --check   # compile to temp + compare (no write)

Requires: pip install pip-tools
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "Not Maintained",
    "__pycache__",
    "node_modules",
}


def find_inputs(repo: Path) -> list[Path]:
    found = []
    for path in repo.rglob("requirements.in"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        found.append(path)
    return sorted(found)


def compile_one(inp: Path, *, upgrade: bool, check: bool) -> int:
    out = inp.with_name("requirements.txt")
    cmd = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        str(inp),
        "--output-file",
        str(out) if not check else str(inp.with_suffix(".compiled.tmp")),
        "--resolver=backtracking",
        "--allow-unsafe",
        "--quiet",
    ]
    if upgrade:
        cmd.append("--upgrade")
    # hashes optional — enable later with --generate-hashes when ready
    print(f"  compiling {inp}")

    tmp_out = None
    if check:
        tmp_out = inp.with_name(".requirements.compiled.tmp")
        cmd[cmd.index("--output-file") + 1] = str(tmp_out)

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("ERROR: pip-tools not installed. Run: pip install pip-tools", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pip-compile failed for {inp} (exit {e.returncode})", file=sys.stderr)
        return e.returncode or 1

    if check:
        assert tmp_out is not None
        if not out.is_file():
            print(f"FAIL: {out} missing (run compile without --check first)", file=sys.stderr)
            tmp_out.unlink(missing_ok=True)
            return 1
        generated = tmp_out.read_text(encoding="utf-8", errors="replace")
        existing = out.read_text(encoding="utf-8", errors="replace")
        tmp_out.unlink(missing_ok=True)
        # Compare package pins only (ignore header comments / timestamps)
        def pins(text: str) -> set[str]:
            lines = set()
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                lines.add(s)
            return lines

        if pins(generated) != pins(existing):
            print(f"FAIL: {out} is out of date vs {inp}", file=sys.stderr)
            return 1
        print(f"  OK {out}")
    else:
        print(f"  wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if requirements.txt would change",
    )
    args = parser.parse_args(argv)

    repo = (args.root or Path(__file__).resolve().parent.parent).resolve()
    inputs = find_inputs(repo)
    if not inputs:
        print("No requirements.in files found — nothing to compile (opt-in).")
        print("To adopt: copy a module's direct deps into requirements.in, then re-run.")
        return 0

    print(f"Found {len(inputs)} requirements.in file(s)")
    rc = 0
    for inp in inputs:
        code = compile_one(inp, upgrade=args.upgrade, check=args.check)
        if code != 0:
            rc = code
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
