"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / scanner
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Scan for missing headers, version drift, secret leaks, README gaps.

  New in v1.1.0:
    - Made diagnostics target-project neutral

  New in v1.0.1:
    - Detect absolute PC paths in docs without flagging public /users/ URLs
    - Cover Finja source/config types and skip generated contract state

  New in v1.0.0:
    - Header presence per source type
    - Module-wide version equality (MAJOR.FEATURES.BUGS)
    - Secret / private-path leak heuristics
    - README license/support block checks

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import re
from pathlib import Path

from .detect import SKIP, detect_module
from .headers import extract_version, has_ecosystem_header
from .models import Finding, ModuleProfile, SEVERITY_ORDER

SOURCE_SUFFIX = {
    ".py",
    ".bat",
    ".cmd",
    ".html",
    ".htm",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
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

SOURCE_NAMES = {
    "dockerfile",
    "makefile",
}

# skip pure data / generated
SKIP_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "shape_template.json",
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "Private key material must never be committed",
    ),
    (
        "aws_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "Looks like AWS access key id",
    ),
    (
        "generic_api_key_assign",
        re.compile(
            r"(?i)(api[_-]?key|secret[_-]?key|client_secret|access_token|auth_token)\s*[=:]\s*['\"][^'\"]{12,}['\"]"
        ),
        "Hard-coded secret assignment — use env / .env (gitignored)",
    ),
    (
        "bearer_literal",
        # real tokens only — not prose "Bearer token" documentation
        re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]{20,}=*"),
        "Bearer token literal",
    ),
    (
        "oauth_password",
        re.compile(r"(?i)oauth:[a-z0-9]{20,}"),
        "Twitch-style oauth: token literal",
    ),
    (
        "connection_string",
        re.compile(r"(?i)(mongodb(\+srv)?://|postgres://|mysql://)[^\s'\"]+"),
        "Database connection string with credentials?",
    ),
]

PRIVATE_PATH_RE = re.compile(
    r"(?i)(?<![A-Z0-9])[A-Z]:[\\/]|"
    r"\\\\[A-Z0-9._-]+[\\/]|"
    r"(?<![A-Z0-9:/.])/(?:users|home)/[A-Z0-9._-]+(?:[\\/]|$)|"
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b|"
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|"
    r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"
)

PRIVATE_PATH_ALLOW_HINTS = (
    "path/to",
    "path\\to",
    "<repo-path>",
    "<project-path>",
    "your/path",
    "your\\path",
    "%userprofile%",
    "$env:userprofile",
    "$home",
    "${home}",
    "path.home",
)

# allow example placeholders
ALLOW_SECRET_HINTS = (
    "example",
    "changeme",
    "your_",
    "xxx",
    "placeholder",
    "dummy",
    "notasecret",
    "sk-...",
    "paste",
)


def scan_module(
    root: str | Path,
    *,
    expected_version: str = "",
    profile: ModuleProfile | None = None,
    require_headers: bool | None = None,
) -> tuple[ModuleProfile, list[Finding]]:
    root_p = Path(root).expanduser().resolve()
    profile = profile or detect_module(root_p)
    findings: list[Finding] = []

    # When is this contract mandatory?
    github_mode = profile.is_git or profile.is_githubish or bool(
        require_headers
    )
    if require_headers is False:
        github_mode = False
    if require_headers is None and not github_mode:
        # still soft-scan if README exists (ecosystem module)
        github_mode = "readme" in profile.signals

    target_ver = (expected_version or profile.declared_version or "").strip()
    versions_in_files: dict[str, list[str]] = {}

    for path in _iter_files(root_p):
        rel = _rel(root_p, path)
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue

        # secrets always (skip our own pattern-definition files)
        if not rel.replace("\\", "/").endswith("github_contract/scanner.py"):
            findings.extend(_scan_secrets(rel, text))
            findings.extend(_scan_private_paths(rel, text))

        if path.name.lower() in {"readme.md"}:
            findings.extend(_scan_readme(rel, text, github_mode))

        if not _is_source(path):
            continue
        if path.name in SKIP_NAMES:
            continue

        # headers
        if github_mode and not has_ecosystem_header(text, path):
            findings.append(
                Finding(
                    rule="missing_header",
                    severity="high" if profile.is_githubish or profile.is_git else "medium",
                    path=rel,
                    line=1,
                    message="Missing ecosystem file header (Project/Author/Version/Copyright)",
                    suggestion="Add banner header; Version MUST match module version MAJOR.FEATURES.BUGS",
                )
            )

        ver = extract_version(text)
        if ver:
            versions_in_files.setdefault(ver, []).append(rel)

    # version unity
    if target_ver:
        for ver, files in versions_in_files.items():
            if ver != target_ver:
                for f in files[:30]:
                    findings.append(
                        Finding(
                            rule="version_drift",
                            severity="critical",
                            path=f,
                            line=0,
                            message=(
                                f"File Version {ver} != module version {target_ver} "
                                f"(scheme: MAJOR.FEATURES.BUGS — same in EVERY module file)"
                            ),
                            suggestion=(
                                f"Set Version: {target_ver} in this file. "
                                "Changelog/New-in lines may differ per file."
                            ),
                        )
                    )
        # files with header missing version while others have target
        if github_mode and versions_in_files:
            for path in _iter_files(root_p):
                if not _is_source(path):
                    continue
                rel = _rel(root_p, path)
                try:
                    text = path.read_text(encoding="utf-8-sig", errors="ignore")
                except OSError:
                    continue
                if has_ecosystem_header(text, path) and not extract_version(text):
                    findings.append(
                        Finding(
                            rule="header_missing_version",
                            severity="high",
                            path=rel,
                            line=1,
                            message="Header present but no Version: x.y.z field",
                            suggestion=f"Add Version: {target_ver}",
                        )
                    )
    elif len(versions_in_files) > 1 and github_mode:
        findings.append(
            Finding(
                rule="version_inconsistent",
                severity="critical",
                path=".",
                line=0,
                message=(
                    f"Multiple versions in module files: {sorted(versions_in_files.keys())}. "
                    "All files in a module must share ONE version (MAJOR.FEATURES.BUGS)."
                ),
                suggestion="Pick release version, bump all file headers + pyproject together",
            )
        )

    profile.versions_found = {k: len(v) for k, v in versions_in_files.items()}
    if target_ver:
        profile.declared_version = target_ver

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.path, f.line))
    return profile, findings


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP for part in p.parts):
            continue
        if p.name.endswith(".example") or p.name.endswith(".example.json"):
            continue
        yield p


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _is_source(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_SUFFIX or path.name.lower() in SOURCE_NAMES


def _scan_secrets(rel: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    # skip docs that only mention patterns
    if rel.lower().endswith((".md", ".txt")) and "example" in text[:200].lower():
        pass
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if any(a in low for a in ALLOW_SECRET_HINTS):
            continue
        if line.strip().startswith("#") and "example" in low:
            continue
        for rule, pat, msg in SECRET_PATTERNS:
            if pat.search(line):
                out.append(
                    Finding(
                        rule=rule,
                        severity="critical",
                        path=rel,
                        line=i,
                        message=msg,
                        snippet=line.strip()[:160],
                        suggestion="Move to env / private/ / secrets manager; never commit",
                    )
                )
    return out


def _scan_private_paths(rel: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    if rel.lower().endswith((".md",)):
        # docs often show example paths — only flag strong machine markers
        for i, line in enumerate(text.splitlines(), 1):
            if PRIVATE_PATH_RE.search(line):
                low = line.lower()
                if any(hint in low for hint in PRIVATE_PATH_ALLOW_HINTS):
                    continue
                out.append(
                    Finding(
                        rule="private_path",
                        severity="medium",
                        path=rel,
                        line=i,
                        message="Machine-specific path in docs — prefer placeholders",
                        snippet=line.strip()[:160],
                        suggestion="Use path/to/... or env-based examples",
                    )
                )
        return out
    for i, line in enumerate(text.splitlines(), 1):
        if PRIVATE_PATH_RE.search(line):
            low = line.lower()
            if any(hint in low for hint in PRIVATE_PATH_ALLOW_HINTS):
                continue
            out.append(
                Finding(
                    rule="private_path",
                    severity="high",
                    path=rel,
                    line=i,
                    message="Possible private machine path / LAN IP in source",
                    snippet=line.strip()[:160],
                    suggestion="No personal paths in production/GitHub trees",
                )
            )
    return out


def _scan_readme(rel: str, text: str, github_mode: bool) -> list[Finding]:
    out: list[Finding] = []
    if not github_mode:
        return out
    low = text.lower()
    if "license" not in low and "mit" not in low:
        out.append(
            Finding(
                rule="readme_missing_license",
                severity="medium",
                path=rel,
                line=0,
                message="README missing License section",
                suggestion="Add ## License with MIT (c) J. Apps + link to LICENSE",
            )
        )
    if "support" not in low and "jappshome" not in low and "contact@" not in low:
        out.append(
            Finding(
                rule="readme_missing_support",
                severity="low",
                path=rel,
                line=0,
                message="README missing Support & Contact block",
                suggestion="Add Email / Website / Buy Me a Coffee (J. Apps standard)",
            )
        )
    if not re.search(r"\bv?\d+\.\d+\.\d+\b", text[:3000]):
        out.append(
            Finding(
                rule="readme_missing_version",
                severity="medium",
                path=rel,
                line=0,
                message="README should state module version (MAJOR.FEATURES.BUGS)",
                suggestion="Title like: # Finja Weather API v1.0.0",
            )
        )
    return out


def format_findings(findings: list[Finding], *, max_n: int = 60) -> str:
    if not findings:
        return "OK: no GitHub-Contract violations.\n"
    lines = [f"Findings: {len(findings)}", ""]
    for f in findings[:max_n]:
        loc = f"{f.path}:{f.line}" if f.line else f.path
        lines.append(f"[{f.severity.upper():<8}] {f.rule} @ {loc}")
        lines.append(f"  {f.message}")
        if f.snippet:
            lines.append(f"  > {f.snippet[:180]}")
        if f.suggestion:
            lines.append(f"  -> {f.suggestion}")
        lines.append("")
    if len(findings) > max_n:
        lines.append(f"... +{len(findings) - max_n} more")
    return "\n".join(lines) + "\n"
