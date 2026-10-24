"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / detect.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
  Description: Detect project identity, languages, runtimes, and useful metrics.

  New in v1.0.0:
    - Detects Error Contract collection points and project-specific metrics

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import MetricRecommendation, ProjectProfile


SKIP = {
    ".git", ".analytics_contract", ".error_contract", ".github_contract",
    "node_modules", "vendor", ".venv", "venv", "dist", "build",
    "__pycache__", ".pytest_cache", "coverage", "logs",
}

LANGUAGES = {
    ".py": "python", ".php": "php", ".js": "javascript",
    ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".cs": "csharp",
    ".java": "java", ".go": "go", ".rs": "rust", ".cpp": "cpp",
    ".cc": "cpp", ".c": "c", ".rb": "ruby", ".kt": "kotlin",
    ".swift": "swift", ".dart": "dart", ".lua": "lua",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "project"


def _project_id(root: Path) -> str:
    package = root / "package.json"
    if package.is_file():
        try:
            name = json.loads(package.read_text(encoding="utf-8-sig")).get("name")
            if name:
                return _slug(str(name).split("/")[-1])
        except (OSError, json.JSONDecodeError):
            pass
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8-sig", errors="ignore")
            match = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)', text)
            if match:
                return _slug(match.group(1))
        except OSError:
            pass
    return _slug(root.name)


def _analytics_exemption(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return ""
    try:
        text = pyproject.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return ""
    section = re.search(
        r"(?ms)^\s*\[tool\.analytics-contract\]\s*$\n(.*?)(?=^\s*\[|\Z)",
        text,
    )
    if not section or not re.search(r"(?im)^\s*exempt\s*=\s*true\s*(?:#.*)?$", section.group(1)):
        return ""
    reason = re.search(r'(?im)^\s*reason\s*=\s*["\']([^"\']+)["\']', section.group(1))
    return reason.group(1).strip() if reason else "Project explicitly opts out of analytics instrumentation."


def _files(root: Path, limit: int = 5000):
    count = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        yield path
        count += 1
        if count >= limit:
            return


def _is_runtime_input(path: Path) -> bool:
    ignored_parts = {"tests", "test", "examples", "schemas", "skill-pack", "docs"}
    if any(part.lower() in ignored_parts for part in path.parts):
        return False
    name = path.name.lower()
    if name.startswith("test_") or ".test." in name or ".spec." in name:
        return False
    manifests = {
        "package.json", "composer.json", "pyproject.toml", "requirements.txt",
        "cargo.toml", "go.mod", "dockerfile", "docker-compose.yml",
        "docker-compose.yaml", "compose.yml", "compose.yaml",
    }
    return path.suffix.lower() in LANGUAGES or name in manifests


def _metric(name: str, kind: str, unit: str, reason: str, source: str):
    return MetricRecommendation(name, kind, unit, reason, source)


def detect_project(path: str | Path) -> ProjectProfile:
    root = Path(path).expanduser().resolve()
    paths = list(_files(root))
    languages = sorted({LANGUAGES[p.suffix.lower()] for p in paths if p.suffix.lower() in LANGUAGES})
    names = {p.name.lower() for p in paths}
    profile = ProjectProfile(str(root), _project_id(root), languages=languages)
    exemption = _analytics_exemption(root)
    if exemption:
        profile.exempt = True
        profile.exemption_reason = exemption
        return profile

    samples: list[str] = []
    for file in paths:
        if not _is_runtime_input(file):
            continue
        try:
            samples.append(file.read_text(encoding="utf-8-sig", errors="ignore")[:20000])
        except OSError:
            continue
        if sum(map(len, samples)) >= 1_500_000:
            break
    blob = "\n".join(samples).lower()

    profile.error_contract = (root / "error_contract.json").is_file() or "app_error" in blob or "apperror" in blob
    profile.error_inbox = any(token in blob for token in ("for_dashboard", "errorinbox", "error_inbox", "to_inbox"))
    if profile.error_contract:
        profile.signals.append("error_contract")
    if profile.error_inbox:
        profile.signals.append("error_inbox")

    profile.recommendations.extend([
        _metric("app.lifecycle", "event", "event", "Know when the application starts and stops.", "baseline"),
        _metric("operation.duration", "timing", "ms", "Measure relevant user, API, job, and pipeline boundaries.", "baseline"),
        _metric("operation.outcome", "counter", "count", "Compare successful and failed operations.", "baseline"),
    ])
    if profile.error_contract or profile.error_inbox:
        profile.recommendations.append(
            _metric("error.occurrence", "error", "count", "Reuse structured Error Contract events without double counting.", "error_contract")
        )

    if "dockerfile" in names or any(name.startswith("docker-compose") or name.startswith("compose.") for name in names):
        profile.runtimes.append("docker")
        profile.signals.append("docker")
        profile.recommendations.extend([
            _metric("system.cpu.usage", "gauge", "percent", "Detect sustained container CPU pressure.", "docker"),
            _metric("system.memory.usage", "gauge", "bytes", "Detect memory growth and container pressure.", "docker"),
            _metric("container.restart", "counter", "count", "Expose crash and restart loops.", "docker"),
        ])

    if any(token in blob for token in ("fastapi", "flask", "express(", "http_response_code", "asp.net", "springframework")) or "php" in languages:
        profile.runtimes.append("web_api")
        profile.signals.append("web_api")
        profile.recommendations.extend([
            _metric("http.request", "counter", "count", "Measure traffic by safe route template and outcome.", "web_api"),
            _metric("http.request.duration", "timing", "ms", "Find slow request paths.", "web_api"),
        ])

    if any(token in blob for token in ("pygame", "requestanimationframe", "unityengine", "godot", "frame_time", "fps")):
        profile.runtimes.append("render_loop")
        profile.signals.append("render_loop")
        profile.recommendations.extend([
            _metric("render.fps", "gauge", "fps", "Measure visible rendering performance.", "render_loop"),
            _metric("render.frame.duration", "timing", "ms", "Locate frame-time spikes.", "render_loop"),
        ])

    if any(token in blob for token in ("sqlalchemy", "mysqli", "pdo(", "postgres", "mongodb", "sqlite3", "entityframework")):
        profile.signals.append("database")
        profile.recommendations.extend([
            _metric("database.operation", "counter", "count", "Measure database outcomes without recording query text.", "database"),
            _metric("database.operation.duration", "timing", "ms", "Find slow database boundaries without leaking SQL.", "database"),
        ])

    if any(token in blob for token in ("celery", "bullmq", "queue", "worker", "backgroundjob")):
        profile.runtimes.append("worker")
        profile.signals.append("worker")
        profile.recommendations.extend([
            _metric("job.outcome", "counter", "count", "Measure completed and failed jobs.", "worker"),
            _metric("job.duration", "timing", "ms", "Find slow background work.", "worker"),
            _metric("queue.depth", "gauge", "count", "Detect growing backlogs where available.", "worker"),
        ])

    if any(token in blob for token in ("openai", "anthropic", "ollama", "transformers", "litellm", "llm")):
        profile.signals.append("ai_model")
        profile.recommendations.extend([
            _metric("model.request", "counter", "count", "Measure model outcomes without logging prompts.", "ai_model"),
            _metric("model.request.duration", "timing", "ms", "Compare provider and model latency.", "ai_model"),
        ])

    profile.runtimes = sorted(set(profile.runtimes))
    unique: dict[str, MetricRecommendation] = {}
    for item in profile.recommendations:
        unique[item.name] = item
    profile.recommendations = list(unique.values())
    return profile

