"""
Project: Finja - Twitch Interactivity Suite
Module: finja-web-crawler / crawler_reporting.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.2.0
Description: One place for structured error reports of the crawler services (search proxy,
    research orchestrator, crawl spawner): a log line with the FINJA code and, when
    ANALYTICS_ENABLED is set, an error event to the Analytics Collector, which hands repeated
    errors to Flare. Off by default: no thread, no network.
New in v2.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import AnalyticsDeliveryError, AppError

ROOT = Path(__file__).resolve().parent
VERSION = "2.2.0"
LOGGER = logging.getLogger("finja.crawler_errors")
_last_reported: dict[str, float] = {}


def _report_analytics_problem(problem: dict[str, Any]) -> None:
    error = AnalyticsDeliveryError(str(problem.get("message") or "analytics delivery failed"),
                                   reason=problem.get("reason"), retry=problem.get("retry"))
    LOGGER.warning("%s %s context=%s", error.code, error, error.context)


_config, _problem = AnalyticsConfig.from_environment(ROOT, version=VERSION)
analytics = AnalyticsSender(_config, root=ROOT, on_failure=_report_analytics_problem)


def start() -> None:
    """Each long-running service calls this once at startup."""
    if _problem:
        _report_analytics_problem({"message": "analytics stays off", "reason": _problem})
    analytics.start()


def stop() -> None:
    analytics.stop()


def report_failure(error: AppError) -> None:
    """One structured log line and, unless the code is log-only, one error.occurrence event."""
    LOGGER.error("%s %s context=%s", error.code, error, error.context)
    analytics.record_exception(error)  # skips codes with to_inbox=False (e.g. FINJA-531)


def report_throttled(error: AppError, every_s: float = 60.0) -> None:
    """Same code and cause type at most once per minute, so a burst of failures cannot flood the log."""
    cause = getattr(error, "cause", None)
    key = f"{error.code}:{type(cause).__name__ if cause else ''}"
    now = time.time()
    if now - _last_reported.get(key, 0.0) >= every_s:
        _last_reported[key] = now
        report_failure(error)
