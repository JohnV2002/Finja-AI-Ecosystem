"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / cli.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: CLI for detection, initialization, planning, and validation.

  New in v1.0.1:
    - Applies each project's reviewed tag allowlist during event validation

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .contract import load_allowed_tags, validate_contract, write_contract
from .detect import detect_project
from .events import validate_event
from .install_skills import install_skills
from .sender import SenderError, write_sender


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def cmd_detect(args: argparse.Namespace) -> int:
    profile = detect_project(args.path)
    if args.json:
        _print_json(profile.to_dict())
    else:
        print(f"Project : {profile.project_id}")
        if profile.exempt:
            print("Status  : EXEMPT")
            print(f"Reason  : {profile.exemption_reason}")
            return 0
        print(f"Languages: {', '.join(profile.languages) or '-'}")
        print(f"Runtimes : {', '.join(profile.runtimes) or '-'}")
        print(f"Error Contract/Inbox: {profile.error_contract}/{profile.error_inbox}")
        print("Metrics:")
        for metric in profile.recommendations:
            print(f"  - {metric.name:<28} {metric.kind:<8} {metric.reason}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    profile = detect_project(args.path)
    if profile.exempt:
        print(f"Skipped: {profile.project_id} is Analytics Contract exempt.")
        print(f"Reason : {profile.exemption_reason}")
        return 0
    target, written = write_contract(args.path, force=args.force)
    print(f"{'Created' if written else 'Kept'}: {target}")
    print("Analytics is OFF by default. The project remains runnable without a backend.")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    profile = detect_project(args.path)
    if profile.exempt:
        print(f"Analytics plan: skip ({profile.exemption_reason})")
        return 0
    print(f"=== Analytics plan: {profile.project_id} ===")
    print("1. Keep analytics.enabled=false until the human opts in.")
    print("2. Reuse Error Contract error events; never double-count them.")
    print("3. Instrument relevant boundaries in new or changed code, not every function.")
    print("4. Transport must be fail-silent, bounded, short-timeout, and non-recursive.")
    print("5. Send project-relative affected files; never source, secrets, prompts, or absolute paths.")
    print("Recommended metrics:")
    for metric in profile.recommendations:
        print(f"  - {metric.name}: {metric.reason}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    problems = validate_contract(args.path)
    if problems:
        print("Analytics Contract violations:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: analytics_contract.json follows schema 1.0 safety invariants.")
    return 0


def cmd_validate_event(args: argparse.Namespace) -> int:
    try:
        event = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid event JSON: {exc}")
        return 1
    problems = validate_event(event, allowed_tags=load_allowed_tags(args.project))
    if problems:
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: event follows Analytics Contract schema 1.0.")
    return 0


def cmd_sender(args: argparse.Namespace) -> int:
    try:
        target = write_sender(args.path, language=args.lang, out=args.out, project_name=args.project_name,
                              version=args.version, force=args.force)
    except SenderError as exc:
        print(f"Sender not written: {exc}")
        return 1
    print(f"Created: {target}")
    print("Off until ANALYTICS_ENABLED is set; wire record_dashboard_error / record_exception or")
    print("AnalyticsLogHandler into the project's error path and call start() at boot.")
    return 0


def cmd_install(_args: argparse.Namespace) -> int:
    _print_json(install_skills())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analytics-contract")
    parser.add_argument("--version", action="version", version=f"analytics_contract {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect", help="Detect project type and useful analytics")
    detect.add_argument("path", nargs="?", default=".")
    detect.add_argument("--json", action="store_true")
    detect.set_defaults(func=cmd_detect)

    init = sub.add_parser("init", help="Create disabled-by-default project contract")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    plan = sub.add_parser("plan", help="Explain instrumentation for this project")
    plan.add_argument("path", nargs="?", default=".")
    plan.set_defaults(func=cmd_plan)

    validate = sub.add_parser("validate", help="Validate project analytics contract")
    validate.add_argument("path", nargs="?", default=".")
    validate.set_defaults(func=cmd_validate)

    event = sub.add_parser("validate-event", help="Validate an event envelope JSON file")
    event.add_argument("file")
    event.add_argument("--project", default=".", help="Project whose tag allowlist applies")
    event.set_defaults(func=cmd_validate_event)

    sender = sub.add_parser("sender", help="Write the canonical analytics sender into a project")
    sender.add_argument("path", nargs="?", default=".")
    sender.add_argument("--lang", default="python", help="Template language (python)")
    sender.add_argument("--out", help="Target file inside the project (default analytics_sender.py)")
    sender.add_argument("--project-name", required=True, help="Project name for the file header")
    sender.add_argument("--version", required=True, help="Project version MAJOR.FEATURES.BUGS for the header")
    sender.add_argument("--force", action="store_true")
    sender.set_defaults(func=cmd_sender)

    install = sub.add_parser("install-skills", help="Install skills for Codex, Grok, and Claude")
    install.set_defaults(func=cmd_install)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))

