"""
Project: Finja - Twitch Interactivity Suite
Module: finja-youtube / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Structured FINJA errors of the YouTube Shorts container (module finja-youtube).
New in v1.2.0: First version: FINJA-109 cookie file, FINJA-538 Chrome unreachable,
    FINJA-539 unexpected request, FINJA-540 diagnostics probe, shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.

Structured errors used locally by finja-youtube.

Numeric codes are reserved in the repository-root error_contract.json legend.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional

CODE_PREFIX = "FINJA"


def set_code_prefix(prefix: str) -> None:
    global CODE_PREFIX
    CODE_PREFIX = (prefix or "APP").strip().upper()


class AppError(Exception):
    """Non-numbered base; concrete module errors own the numeric codes."""

    code_num: Optional[int] = None
    to_inbox: bool = True

    def __init__(self, message: str, module: str = "unknown", cause: Optional[Exception] = None, **context: Any) -> None:
        self.module = module
        self.context = context
        self.cause = cause
        super().__init__(message)

    @property
    def code(self) -> str:
        if self.code_num is None:
            raise TypeError("AppError base classes do not own an error code")
        return f"{CODE_PREFIX}-{self.code_num}"

    def for_dashboard(self) -> dict[str, Any]:
        target = self.cause if self.cause is not None else self
        trace = ""
        if getattr(target, "__traceback__", None) is not None:
            trace = "".join(traceback.format_exception(type(target), target, target.__traceback__, limit=4))
        return {
            "code": self.code,
            "message": str(self),
            "module": self.module,
            "context": self.context,
            "cause": f"{type(self.cause).__name__}: {self.cause}" if self.cause else None,
            "traceback": trace,
            "to_inbox": self.to_inbox,
        }


# Add concrete module errors only through `error-contract create`.

# --- FINJA-109 [config] owner=finja-youtube module=finja-youtube ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class YouTubeCookiesInvalidError(AppError):
    code_num = 109
    def __init__(self, message: str = 'The YouTube cookie file could not be read.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-youtube'), **kw)

# --- FINJA-538 [tool] owner=finja-youtube module=finja-youtube ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class YouTubeChromeUnreachableError(AppError):
    code_num = 538
    def __init__(self, message: str = 'Finja YouTube could not reach its headless Chrome.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-youtube'), **kw)

# --- FINJA-539 [tool] owner=finja-youtube module=finja-youtube ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class YouTubeApiUnexpectedError(AppError):
    code_num = 539
    def __init__(self, message: str = 'A Finja YouTube API request failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-youtube'), **kw)

# --- FINJA-540 [tool] owner=finja-youtube module=finja-youtube ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class YouTubeDiagnosticsProbeError(AppError):
    code_num = 540
    def __init__(self, message: str = 'Finja YouTube diagnostics probe hit a real bug.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-youtube'), **kw)


# --- FINJA-512 [analytics] shared with Finja (ledger owner: analytics) ---
class AnalyticsDeliveryError(AppError):
    """Analytics events could not be delivered (never to the inbox)."""

    code_num = 512
    to_inbox = False

    def __init__(self, message: str = "Analytics events could not be delivered.", **kw):
        super().__init__(message, module=kw.pop("module", "finja-youtube"), **kw)
