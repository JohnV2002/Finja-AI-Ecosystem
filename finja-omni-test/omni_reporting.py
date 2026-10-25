"""
======================================================================
         Finja Omni Test – Error Reporting
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / omni_reporting
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  One place for structured error reports of all Omni scripts: a log
  line with the FINJA code and, when ANALYTICS_ENABLED is set in .env,
  an error event to the Analytics Collector (which hands repeated
  errors to Flare). Off by default: no thread, no network.

 New in v1.1.0:
  First version.
======================================================================
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")  # before the sender reads ANALYTICS_* (see.py/quatsch.py load it too)

from analytics_sender import AnalyticsConfig, AnalyticsSender  # noqa: E402
from core.exceptions import AnalyticsDeliveryError, AppError, OmniModelError  # noqa: E402

VERSION = "1.1.0"
LOGGER = logging.getLogger("finja_omni")
if not logging.getLogger().handlers:  # scripts without their own logging setup still show the line
    logging.basicConfig(level=logging.INFO, format="[omni] %(message)s")
_last_reported: dict[str, float] = {}


def _report_analytics_problem(problem: dict) -> None:
    error = AnalyticsDeliveryError(str(problem.get("message") or "analytics delivery failed"),
                                   reason=problem.get("reason"), retry=problem.get("retry"))
    LOGGER.warning("%s %s context=%s", error.code, error, error.context)


_config, _problem = AnalyticsConfig.from_environment(ROOT, version=VERSION)
analytics = AnalyticsSender(_config, root=ROOT, on_failure=_report_analytics_problem)


def start() -> None:
    """Long-running scripts (live.py, bubble.py) call this once at startup."""
    if _problem:
        _report_analytics_problem({"message": "analytics stays off", "reason": _problem})
    analytics.start()


def stop() -> None:
    analytics.stop()


def as_app_error(exc: BaseException, message: str, **context) -> AppError:
    """Structured errors stay as they are; anything else becomes a model-call error with its cause."""
    return exc if isinstance(exc, AppError) else OmniModelError(message, cause=exc, **context)


def report_failure(error: AppError, flush: bool = False) -> None:
    """One structured log line and, when analytics is on, one error.occurrence event.

    Short-lived command-line scripts pass flush=True so the event leaves before they exit.
    """
    LOGGER.error("%s %s context=%s", error.code, error, error.context)
    if analytics.record_exception(error) is not None and flush:
        analytics.flush_once()


def report_throttled(error: AppError, every_s: float = 60.0) -> None:
    """Same code and cause type at most once per minute, so a 3 s loop cannot flood the log."""
    cause = getattr(error, "cause", None)
    key = f"{error.code}:{type(cause).__name__ if cause else ''}"
    now = time.time()
    if now - _last_reported.get(key, 0.0) >= every_s:
        _last_reported[key] = now
        report_failure(error)
