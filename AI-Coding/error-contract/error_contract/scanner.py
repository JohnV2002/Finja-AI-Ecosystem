"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/scanner.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Find contract violations: print/console, bare except, unstructured broad catches.

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

from .detect import SKIP_DIRS, detect_project, iter_files
from .models import Finding, ProjectProfile, ScanReport

# --- Python patterns -------------------------------------------------------
RE_PRINT = re.compile(r"\bprint\s*\(")
RE_PRINT_EXC = re.compile(
    r"print\s*\([^)]*\b(e|err|error|exc|exception|traceback)\b",
    re.IGNORECASE,
)
RE_LOGGER_EXC = re.compile(
    r"""(?:logger|logging|log)\.(?:debug|info|warning|error|exception|critical)\s*\(\s*['"][^'"]*%s"""
    % r"(?:%s|\{)"  # printf or format - weak
)
RE_LOG_EXCEPTION = re.compile(r"\b(?:logger|logging|log)\.exception\s*\(")
RE_BARE_EXCEPT = re.compile(r"^\s*except\s*:\s*(?:#.*)?$")
RE_EXCEPT_EXCEPTION = re.compile(
    r"^\s*except\s+\(?\s*Exception\b(?:\s+as\s+(\w+))?.*:\s*(?:#.*)?$"
)
RE_EXCEPT_BASE = re.compile(
    r"^\s*except\s+\(?\s*BaseException\b(?:\s+as\s+(\w+))?.*:\s*(?:#.*)?$"
)
RE_PASS = re.compile(r"^\s*pass\s*(?:#.*)?$")
RE_RAISE_UNEXPECTED = re.compile(r"\bUnexpectedError\s*\(")
RE_RAISE_APP = re.compile(r"\b(AppError|[A-Z][A-Za-z0-9]*Error)\s*\(")
RE_TRACEBACK_PRINT = re.compile(r"traceback\.(print_exc|print_exception)\s*\(")
RE_SYS_EXC_HOOK = re.compile(r"sys\.exc_info\s*\(")

# --- JS / TS patterns ------------------------------------------------------
RE_CONSOLE = re.compile(r"\bconsole\.(log|error|warn|debug|info)\s*\(")
RE_CONSOLE_EXC = re.compile(
    r"console\.(log|error|warn)\s*\([^)]*\b(e|err|error|ex|exception)\b",
    re.IGNORECASE,
)
RE_CATCH_ANY = re.compile(r"\bcatch\s*\(\s*(\w+)\s*\)")
RE_CATCH_EMPTY = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")

# generic http/status style dumps
RE_GENERIC_999 = re.compile(r"\b(999|code_num\s*=\s*999)\b")


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _snippet(lines: list[str], idx: int, radius: int = 0) -> str:
    if idx < 0 or idx >= len(lines):
        return ""
    if radius <= 0:
        return lines[idx].rstrip()
    lo = max(0, idx - radius)
    hi = min(len(lines), idx + radius + 1)
    return "\n".join(lines[lo:hi]).rstrip()


def _next_nonempty(lines: list[str], start: int, limit: int = 6) -> list[str]:
    out: list[str] = []
    i = start
    while i < len(lines) and len(out) < limit:
        s = lines[i]
        if s.strip():
            out.append(s)
        i += 1
        # stop if dedent-ish for except body: keep simple
        if out and i > start + 1 and not lines[i - 1].startswith((" ", "\t")):
            break
    return out


def scan_python_file(root: Path, path: Path, prefix: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return findings
    lines = text.splitlines()
    rel = _rel(root, path)

    # Skip our own package / pure tests of the engine if nested
    if "error_contract" in path.parts and "tests" not in path.parts:
        if path.name in {"scanner.py", "taxonomy.py", "detect.py", "cli.py", "scaffold.py"}:
            return findings

    for i, line in enumerate(lines):
        ln = i + 1
        stripped = line.strip()

        # console.log style does not apply; print
        if RE_PRINT.search(line):
            sev = "high" if RE_PRINT_EXC.search(line) else "medium"
            # allow prints in __main__ CLI scripts and obvious debug flags slightly softer
            if path.name in {"cli.py", "__main__.py"} or "if __name__" in text[: text.find(line) + 1 if line in text else 0]:
                sev = "low" if sev == "medium" else "medium"
            findings.append(
                Finding(
                    rule="raw_print",
                    severity=sev,
                    path=rel,
                    line=ln,
                    message="print() used - structured AppError / logger + code preferred",
                    snippet=stripped,
                    suggestion=(
                        f"Raise {prefix}-xxx AppError subclass or log with code, "
                        "e.g. logger.error('[%s] ...', err.code) / inbox.add(err.for_dashboard())"
                    ),
                )
            )

        if RE_TRACEBACK_PRINT.search(line):
            findings.append(
                Finding(
                    rule="traceback_print",
                    severity="high",
                    path=rel,
                    line=ln,
                    message="traceback.print_exc/print_exception - wrap as UnexpectedError or dedicated code",
                    snippet=stripped,
                    suggestion=f"except Exception as e: raise UnexpectedError(e, module='...')  # -> {prefix}-999",
                )
            )

        if RE_BARE_EXCEPT.match(line):
            findings.append(
                Finding(
                    rule="bare_except",
                    severity="critical",
                    path=rel,
                    line=ln,
                    message="bare 'except:' swallows BaseException (incl. KeyboardInterrupt)",
                    snippet=stripped,
                    suggestion="except Exception as e: ... and re-raise as structured AppError",
                )
            )

        m_exc = RE_EXCEPT_EXCEPTION.match(line) or RE_EXCEPT_BASE.match(line)
        if m_exc:
            var = m_exc.group(1) if m_exc.lastindex else None
            body = _next_nonempty(lines, i + 1, limit=8)
            body_txt = "\n".join(body)
            # pass / silent
            if any(RE_PASS.match(b) for b in body[:3]):
                findings.append(
                    Finding(
                        rule="swallowed_exception",
                        severity="critical",
                        path=rel,
                        line=ln,
                        message="broad except with pass - error disappears",
                        snippet=_snippet(lines, i) + " -> pass",
                        suggestion="Log structured error or re-raise AppError; never silent pass on Exception",
                    )
                )
            # print only
            elif any(RE_PRINT.search(b) for b in body):
                findings.append(
                    Finding(
                        rule="except_print",
                        severity="high",
                        path=rel,
                        line=ln,
                        message="except Exception + print - no structured code",
                        snippet=(stripped + " | " + body[0].strip())[:200],
                        suggestion=f"Wrap as UnexpectedError or dedicated {prefix}-xxx; send to inbox/dashboard",
                    )
                )
            # no AppError / UnexpectedError / raise in body
            elif body and not (
                RE_RAISE_APP.search(body_txt)
                or "for_dashboard" in body_txt
                or "UnexpectedError" in body_txt
                or re.search(r"\braise\b", body_txt)
                or RE_LOG_EXCEPTION.search(body_txt)
            ):
                # soften for pure resource cleanup patterns (close, unlink) if very short
                cleanup_only = all(
                    re.search(r"\b(close|unlink|remove|cleanup|release|disconnect)\b", b, re.I)
                    or RE_PASS.match(b)
                    for b in body[:4]
                )
                if not cleanup_only:
                    findings.append(
                        Finding(
                            rule="broad_except_unstructured",
                            severity="medium",
                            path=rel,
                            line=ln,
                            message="broad except without structured AppError / re-raise",
                            snippet=stripped,
                            suggestion=(
                                "Map known cases to dedicated codes; fallback "
                                f"UnexpectedError(cause) -> {prefix}-999"
                            ),
                        )
                    )

        if RE_RAISE_UNEXPECTED.search(line):
            # info: overuse of 999 is a smell when it's the only path
            findings.append(
                Finding(
                    rule="unexpected_999",
                    severity="info",
                    path=rel,
                    line=ln,
                    message=f"UnexpectedError ({prefix}-999) - OK as last resort; prefer dedicated codes for recurring cases",
                    snippet=stripped,
                    suggestion="If this path is common, propose a dedicated code in the right band",
                )
            )

    return findings


def scan_js_file(root: Path, path: Path, prefix: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return findings
    lines = text.splitlines()
    rel = _rel(root, path)

    for i, line in enumerate(lines):
        ln = i + 1
        stripped = line.strip()
        if RE_CONSOLE.search(line):
            sev = "high" if RE_CONSOLE_EXC.search(line) else "medium"
            findings.append(
                Finding(
                    rule="console_log",
                    severity=sev,
                    path=rel,
                    line=ln,
                    message="console.* used for (error) output - structured project error contract preferred",
                    snippet=stripped[:220],
                    suggestion=(
                        f"Use project error helper with {prefix}-xxx codes "
                        "(or shared logger that carries code/module/context)"
                    ),
                )
            )
        if RE_CATCH_EMPTY.search(line):
            findings.append(
                Finding(
                    rule="empty_catch",
                    severity="critical",
                    path=rel,
                    line=ln,
                    message="empty catch block",
                    snippet=stripped,
                    suggestion="Handle with structured error code or rethrow",
                )
            )
    # multi-line empty catch
    if re.search(r"catch\s*\([^)]*\)\s*\{\s*//[^\}]*\}", text):
        pass  # optional
    return findings


def scan_project(
    root: str | Path,
    *,
    prefix: str = "",
    profile: ProjectProfile | None = None,
    include_info: bool = True,
) -> ScanReport:
    root_p = Path(root).resolve()
    profile = profile or detect_project(root_p, prefix=prefix)
    pref = profile.prefix

    findings: list[Finding] = []

    # Structural findings
    if not profile.exceptions_path and not profile.contract_path:
        findings.append(
            Finding(
                rule="missing_taxonomy",
                severity="critical",
                path=".",
                line=0,
                message="No exceptions.py / error_contract.json Source of Truth",
                suggestion=(
                    f"Run: python -m error_contract scaffold \"{root_p}\" --prefix {pref} "
                    f"--name \"{root_p.name}\""
                ),
            )
        )
    elif profile.taxonomy and profile.taxonomy.style == "finja_app_error":
        if not profile.taxonomy.has_set_code_prefix:
            findings.append(
                Finding(
                    rule="missing_set_code_prefix",
                    severity="medium",
                    path=_rel(root_p, Path(profile.exceptions_path)) if profile.exceptions_path else ".",
                    line=0,
                    message="exceptions module has no set_code_prefix - branding stays generic",
                    suggestion="Add set_code_prefix() and call it at boot with project prefix",
                )
            )

    # Namespace registry is the Grundbuch: local numbered classes must agree.
    if profile.taxonomy:
        from .ledger import canonical_registry_path, check_local_against_ledger, load_namespace_ledger
        from .registry import resolve_project

        resolved = resolve_project(root_p)
        legend_path = canonical_registry_path(pref, root_p)
        if resolved.get("status") == "known" and legend_path.is_file():
            owner = resolved["project"].get("id") or ""
            ledger = load_namespace_ledger(pref, root_p)
            for issue in check_local_against_ledger(
                ledger,
                prefix=pref,
                local_codes=profile.taxonomy.codes,
                owner_id=owner,
            ):
                severity = issue["severity"]
                if issue["issue"] == "local_unregistered":
                    severity = "high"
                findings.append(
                    Finding(
                        rule=f"registry_{issue['issue']}",
                        severity=severity,
                        path=_rel(root_p, Path(profile.exceptions_path)) if profile.exceptions_path else ".",
                        line=0,
                        message=issue["message"],
                        suggestion="Use `error-contract create` or reconcile the repo-root error_contract.json legend.",
                    )
                )

    # File scans
    for path in iter_files(root_p, {".py"}, max_files=6000):
        findings.extend(scan_python_file(root_p, path, pref))
    for path in iter_files(root_p, {".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"}, max_files=4000):
        findings.extend(scan_js_file(root_p, path, pref))

    if not include_info:
        findings = [f for f in findings if f.severity != "info"]

    return ScanReport(profile=profile, findings=findings)
