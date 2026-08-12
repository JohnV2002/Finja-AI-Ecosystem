"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / cli
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: CLI for detect, scan, check-version, preflight, install-skills.

  New in v1.1.0:
    - Added explicit target-project labels for generated headers

  New in v1.0.1:
    - Added --license-path for repository-root README license links

  New in v1.0.0:
    - Initial production CLI

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detect import detect_module
from .headers import (
    build_batch_header,
    build_html_header,
    build_python_header,
    build_readme_footer,
)
from .install_skills import format_install, install_skills
from .scanner import format_findings, scan_module


def _print(msg: str) -> None:
    sys.stdout.write(msg if msg.endswith("\n") else msg + "\n")


def cmd_detect(args: argparse.Namespace) -> int:
    prof = detect_module(args.path)
    if args.json:
        _print(json.dumps(prof.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(f"Root     : {prof.root}")
        _print(f"Module   : {prof.module_name}")
        _print(f"Git      : {prof.is_git}   GitHubish: {prof.is_githubish}")
        _print(f"Version  : {prof.declared_version or '(unset)'}")
        _print(f"Signals  : {', '.join(prof.signals) or '-'}")
        if prof.versions_found:
            _print(f"In files : {prof.versions_found}")
        for n in prof.notes:
            _print(f"Note     : {n}")
        _print("")
        _print("Version scheme: MAJOR.FEATURES.BUGS  (e.g. 1.0.0)")
        _print("  1 = breaking / major   0 = features   0 = bugfixes")
        _print("Same version string in EVERY file of the module; changelog per file may differ.")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    prof, findings = scan_module(args.path, expected_version=args.version or "")
    if args.json:
        _print(
            json.dumps(
                {
                    "profile": prof.to_dict(),
                    "findings": [f.to_dict() for f in findings],
                    "count": len(findings),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        _print(f"=== GitHub Contract Scan ===")
        _print(f"Module : {prof.module_name}  version={prof.declared_version or '-'}")
        _print(f"Git/GH : {prof.is_git}/{prof.is_githubish}")
        _print(f"Hits   : {len(findings)}")
        _print("")
        _print(format_findings(findings, max_n=args.max))
    bad = [f for f in findings if f.severity in {"critical", "high"}]
    return 1 if bad else 0


def cmd_check_version(args: argparse.Namespace) -> int:
    ver = args.version or ""
    prof, findings = scan_module(args.path, expected_version=ver)
    drift = [f for f in findings if f.rule in {"version_drift", "version_inconsistent", "header_missing_version"}]
    if args.json:
        _print(json.dumps({"version": prof.declared_version, "drift": [f.to_dict() for f in drift]}, indent=2))
    else:
        _print(f"Target module version: {prof.declared_version or ver or '(detect)'}")
        _print(f"Versions in files: {prof.versions_found or '{}'}")
        if not drift:
            _print("OK: versions consistent (or no Version fields found).")
        else:
            _print(format_findings(drift, max_n=40))
    return 1 if drift else 0


def cmd_preflight(args: argparse.Namespace) -> int:
    prof = detect_module(args.path)
    root = Path(prof.root)
    d = root / ".github_contract"
    d.mkdir(exist_ok=True)
    text = (
        f"module={prof.module_name}\n"
        f"version={prof.declared_version}\n"
        f"git={prof.is_git} githubish={prof.is_githubish}\n"
        f"signals={prof.signals}\n"
        "scheme=MAJOR.FEATURES.BUGS (same in every file; changelog per-file ok)\n"
    )
    (d / "ACTIVE.md").write_text("# GitHub Contract preflight\n\n```\n" + text + "```\n", encoding="utf-8")
    if args.json:
        _print(json.dumps(prof.to_dict(), indent=2))
    else:
        _print(text)
        _print(f"Wrote {d / 'ACTIVE.md'}")
    return 0


def cmd_header(args: argparse.Namespace) -> int:
    kind = args.kind
    ver = args.version
    title = args.title or "Module File"
    module = args.module or "module / file"
    desc = args.description or title
    new_in = [x.strip() for x in (args.new_in or "").split(";") if x.strip()]
    if kind == "py":
        _print(build_python_header(title=title, module=module, version=ver, description=desc, new_in=new_in or None, project=args.project))
    elif kind == "bat":
        _print(build_batch_header(title=title, version=ver, description=desc, new_in=new_in or None, project=args.project))
    elif kind == "html":
        _print(build_html_header(title=title, version=ver, description=desc, new_in=new_in or None, project=args.project))
    elif kind == "readme-footer":
        _print(build_readme_footer(args.license_path))
    else:
        _print("Unknown kind")
        return 1
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    engines = [e.strip() for e in (args.engines or "grok,codex,claude").split(",") if e.strip()]
    result = install_skills(
        engines=engines,
        engine_root=args.engine_root or None,
        always_active=not args.no_always_active,
        install_hooks=not args.no_hooks,
    )
    if args.json:
        _print(json.dumps(result, indent=2, default=str))
    else:
        _print(format_install(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="github_contract",
        description="GitHub Contract — headers, module version MAJOR.FEATURES.BUGS, no-leak for public repos.",
    )
    p.add_argument("--version", action="version", version=f"github_contract {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_path(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("path", nargs="?", default=".", help="Module root")
        sp.add_argument("--json", action="store_true")

    d = sub.add_parser("detect", help="Detect git/GitHub context + version")
    add_path(d)
    d.set_defaults(func=cmd_detect)

    s = sub.add_parser("scan", help="Scan headers, version drift, secrets, README")
    add_path(s)
    s.add_argument("--version", default="", dest="version", help="Expected module version x.y.z")
    s.add_argument("--max", type=int, default=60)
    s.set_defaults(func=cmd_scan)

    cv = sub.add_parser("check-version", help="Only version unity check")
    add_path(cv)
    cv.add_argument("--version", default="", help="Expected version")
    cv.set_defaults(func=cmd_check_version)

    pf = sub.add_parser("preflight", help="Write .github_contract/ACTIVE.md")
    add_path(pf)
    pf.set_defaults(func=cmd_preflight)

    h = sub.add_parser("header", help="Print a standard header template")
    h.add_argument("--kind", choices=["py", "bat", "html", "readme-footer"], default="py")
    h.add_argument("--version", required=True, help="Module version e.g. 1.0.0")
    h.add_argument("--title", default="")
    h.add_argument("--module", default="")
    h.add_argument(
        "--project",
        default="J. Apps Project",
        help="Project or suite label written into the generated header",
    )
    h.add_argument("--description", default="")
    h.add_argument("--new-in", default="", help="Semicolon-separated New-in bullets")
    h.add_argument(
        "--license-path",
        default="../LICENSE",
        help="README-relative path to the repository-root LICENSE",
    )
    h.set_defaults(func=cmd_header)

    inst = sub.add_parser("install-skills", help="Install for Grok + Codex + Claude")
    inst.add_argument("--engines", default="grok,codex,claude")
    inst.add_argument("--engine-root", default="")
    inst.add_argument("--no-always-active", action="store_true")
    inst.add_argument("--no-hooks", action="store_true")
    inst.add_argument("--json", action="store_true")
    inst.set_defaults(func=cmd_install)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
