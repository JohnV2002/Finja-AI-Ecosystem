"""
======================================================================
      Flare (Finja Agentic Code) – L1 Diagnosis (static, offline)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / worker
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    - First version: L1 is a contract, not a JSON dump.

----------------------------------------------------------------------

  L1 is Flare's first look at a job: cheap, purely static, and
  trustworthy enough for `patching` and `approval` to lean on.

  Three rules define L1, and every one of them is a reliability
  property rather than a feature:

    1. It NEVER executes the submitted code. No pytest, no node, no
       imports of workspace modules. Running a stranger's code is a
       different risk class and belongs to a higher capability level.
    2. It is DETERMINISTIC. Same workspace in, byte-identical
       diagnosis out: files are walked in sorted order and findings are
       sorted by (path, line, column, check).
    3. It is HONEST about its own blind spots. A file nobody can check
       is reported in `undiagnosed`, and a check that could not run is
       reported in `checks_skipped`. Silence never means "clean".

  Findings carry a `check` id such as `python.syntax`, deliberately NOT
  a FLARE-xxx code: that namespace belongs to the exceptions Finja shows
  a user, and filling it with lint rules would make the public error
  contract meaningless.

  Runs inside the offline worker sandbox, so stdlib only. PyYAML is used
  when the image happens to carry it and reported as skipped when not.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

SCHEMA_VERSION = 1

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

CHECK_PYTHON_SYNTAX = "python.syntax"
CHECK_PYTHON_RELATIVE_IMPORT = "python.relative_import"
CHECK_JSON_PARSE = "json.parse"
CHECK_TOML_PARSE = "toml.parse"
CHECK_YAML_PARSE = "yaml.parse"
CHECK_TEXT_ENCODING = "text.encoding"

# Extensions a checker actually understands. Everything else the
# orchestrator allows is reported as undiagnosed rather than passed over.
PYTHON_SUFFIXES = frozenset({".py"})
JSON_SUFFIXES = frozenset({".json"})
TOML_SUFFIXES = frozenset({".toml"})
YAML_SUFFIXES = frozenset({".yml", ".yaml"})

# Prose and markup: no stdlib parser gives a trustworthy verdict, and a
# made-up one would be exactly the false confidence L1 must not create.
UNCHECKABLE_SUFFIXES = frozenset({".md", ".txt", ".css", ".html"})
# JavaScript needs a real parser; python:3.14-slim carries no node.
NEEDS_TOOLING_SUFFIXES = frozenset({".js", ".ts", ".tsx", ".jsx"})

MAX_FINDINGS = 200


def _load_yaml_module():
    """PyYAML if the image has it; L1 reports the gap instead of guessing."""
    try:
        import yaml
    except ImportError:
        return None
    return yaml


def _finding(path: str, check: str, severity: str, message: str,
             line: int | None = None, column: int | None = None,
             truncated: bool = False) -> dict:
    finding = {
        "path": path,
        "check": check,
        "severity": severity,
        "message": message,
        "line": line,
        "column": column,
    }
    if truncated:
        # ast stops at the first SyntaxError, so a clean-looking rest of
        # the file is not evidence of anything. Say so instead of implying
        # the file holds exactly one problem.
        finding["truncated"] = True
    return finding


def _read_text(path: Path) -> tuple[str | None, dict | None]:
    """Decode strictly; an undecodable file is a finding, not a silent fallback."""
    rel = path.name
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, _finding(rel, CHECK_TEXT_ENCODING, SEVERITY_ERROR,
                              f"File could not be read: {type(exc).__name__}")
    if b"\x00" in raw:
        return None, _finding(rel, CHECK_TEXT_ENCODING, SEVERITY_ERROR,
                              "File contains NUL bytes and is not text")
    try:
        return raw.decode("utf-8-sig"), None
    except UnicodeDecodeError as exc:
        return None, _finding(rel, CHECK_TEXT_ENCODING, SEVERITY_ERROR,
                              f"File is not valid UTF-8 at byte {exc.start}")


def _check_python(rel: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return [_finding(rel, CHECK_PYTHON_SYNTAX, SEVERITY_ERROR,
                         exc.msg or "Invalid Python syntax",
                         line=exc.lineno, column=exc.offset, truncated=True)]
    except ValueError as exc:
        # e.g. source containing null bytes that slipped past the byte check
        return [_finding(rel, CHECK_PYTHON_SYNTAX, SEVERITY_ERROR,
                         f"Python source could not be parsed: {exc}")]
    return _check_relative_imports(rel, tree)


def _relative_import_target(rel: str, node: ast.ImportFrom) -> str:
    """Resolve `from ..pkg import x` to a workspace-relative module path."""
    base = Path(rel).parent
    for _ in range(node.level - 1):
        base = base.parent
    if node.module:
        base = base.joinpath(*node.module.split("."))
    return base.as_posix()


def _check_relative_imports(rel: str, tree: ast.AST) -> list[dict]:
    """
    Only RELATIVE imports are checked, and that restriction is the point:
    a missing third-party package cannot be told apart from an uninstalled
    one inside an offline sandbox, so flagging `import requests` would be
    a false positive. A relative import, by contrast, must resolve inside
    the workspace -- if it does not, the code is broken no matter what the
    environment looks like.
    """
    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        target = _relative_import_target(rel, node)
        findings.append(_finding(
            rel, CHECK_PYTHON_RELATIVE_IMPORT, SEVERITY_WARNING,
            f"Relative import resolves to '{target}', which is not in the submitted files",
            line=node.lineno, column=node.col_offset + 1,
        ))
    return findings


def _resolve_relative_imports(findings: list[dict], known: frozenset[str]) -> list[dict]:
    """Drop relative-import findings whose target was staged after all."""
    kept: list[dict] = []
    for finding in findings:
        if finding["check"] != CHECK_PYTHON_RELATIVE_IMPORT:
            kept.append(finding)
            continue
        target = finding["message"].split("'")[1]
        if f"{target}.py" in known or f"{target}/__init__.py" in known:
            continue
        kept.append(finding)
    return kept


def _check_json(rel: str, text: str) -> list[dict]:
    try:
        json.loads(text)
    except ValueError as exc:
        line = getattr(exc, "lineno", None)
        column = getattr(exc, "colno", None)
        return [_finding(rel, CHECK_JSON_PARSE, SEVERITY_ERROR,
                         getattr(exc, "msg", str(exc)), line=line, column=column)]
    return []


def _check_toml(rel: str, text: str) -> list[dict]:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [_finding(rel, CHECK_TOML_PARSE, SEVERITY_ERROR, str(exc))]
    return []


def _check_yaml(rel: str, text: str, yaml_module) -> list[dict]:
    try:
        yaml_module.safe_load(text)
    except yaml_module.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        message = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        return [_finding(rel, CHECK_YAML_PARSE, SEVERITY_ERROR, message,
                         line=(mark.line + 1) if mark else None,
                         column=(mark.column + 1) if mark else None)]
    return []


def _sort_key(finding: dict) -> tuple:
    return (
        finding["path"],
        finding["line"] if isinstance(finding["line"], int) else -1,
        finding["column"] if isinstance(finding["column"], int) else -1,
        finding["check"],
    )


def diagnose(workspace: Path) -> dict:
    """Run every applicable static check and return the L1 contract."""
    yaml_module = _load_yaml_module()
    checks_run = [
        CHECK_TEXT_ENCODING, CHECK_PYTHON_SYNTAX,
        CHECK_PYTHON_RELATIVE_IMPORT, CHECK_JSON_PARSE, CHECK_TOML_PARSE,
    ]
    checks_skipped: list[dict] = []
    if yaml_module is None:
        checks_skipped.append({
            "check": CHECK_YAML_PARSE,
            "reason": "PyYAML is not installed in the worker image",
        })
    else:
        checks_run.append(CHECK_YAML_PARSE)

    files = sorted(
        (path for path in workspace.rglob("*")
         if path.is_file() and not path.name.endswith(".orig")),
        key=lambda path: path.relative_to(workspace).as_posix(),
    )
    known = frozenset(path.relative_to(workspace).as_posix() for path in files)

    findings: list[dict] = []
    undiagnosed: list[dict] = []
    diagnosed = 0

    for path in files:
        rel = path.relative_to(workspace).as_posix()
        suffix = path.suffix.lower()

        if suffix in NEEDS_TOOLING_SUFFIXES:
            undiagnosed.append({"path": rel, "reason": "no JavaScript parser in the offline sandbox"})
            continue
        if suffix in UNCHECKABLE_SUFFIXES:
            undiagnosed.append({"path": rel, "reason": "prose or markup; no trustworthy static check"})
            continue
        if suffix in YAML_SUFFIXES and yaml_module is None:
            undiagnosed.append({"path": rel, "reason": "PyYAML is not installed in the worker image"})
            continue
        if suffix not in PYTHON_SUFFIXES | JSON_SUFFIXES | TOML_SUFFIXES | YAML_SUFFIXES:
            undiagnosed.append({"path": rel, "reason": f"no checker for '{suffix or path.name}'"})
            continue

        text, problem = _read_text(path)
        if problem is not None:
            problem["path"] = rel
            findings.append(problem)
            diagnosed += 1
            continue

        diagnosed += 1
        if suffix in PYTHON_SUFFIXES:
            findings.extend(_check_python(rel, text))
        elif suffix in JSON_SUFFIXES:
            findings.extend(_check_json(rel, text))
        elif suffix in TOML_SUFFIXES:
            findings.extend(_check_toml(rel, text))
        elif suffix in YAML_SUFFIXES:
            findings.extend(_check_yaml(rel, text, yaml_module))

    findings = _resolve_relative_imports(findings, known)
    findings.sort(key=_sort_key)
    truncated_findings = len(findings) > MAX_FINDINGS
    if truncated_findings:
        findings = findings[:MAX_FINDINGS]

    counts = {
        SEVERITY_ERROR: sum(1 for f in findings if f["severity"] == SEVERITY_ERROR),
        SEVERITY_WARNING: sum(1 for f in findings if f["severity"] == SEVERITY_WARNING),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "executes_code": False,
        "deterministic": True,
        "checks_run": sorted(checks_run),
        "checks_skipped": sorted(checks_skipped, key=lambda entry: entry["check"]),
        "files_seen": len(files),
        "files_diagnosed": diagnosed,
        "undiagnosed": undiagnosed,
        "findings": findings,
        "findings_truncated": truncated_findings,
        "counts": counts,
        "verdict": "blocked" if counts[SEVERITY_ERROR] else "clean",
    }


def syntax_findings(diagnosis: dict) -> list[dict]:
    """
    Back-compatible view for the orchestrator's existing syntax gate, which
    predates L1 and must keep working unchanged.
    """
    return [
        {
            "path": finding["path"],
            "line": finding["line"],
            "offset": finding["column"],
            "message": finding["message"],
        }
        for finding in diagnosis["findings"]
        if finding["check"] == CHECK_PYTHON_SYNTAX
    ]
