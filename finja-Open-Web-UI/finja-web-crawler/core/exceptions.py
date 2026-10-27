"""
Project: Finja - Twitch Interactivity Suite
Module: finja-web-crawler / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.2.0
Description: Structured FINJA errors of the web crawler (module finja-web-crawler).
New in v2.2.0: First version: FINJA-531 search backend (logged only), FINJA-532 crawl worker
    spawn, FINJA-533 unexpected request, FINJA-534 diagnostics probe, shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.

Structured errors used locally by finja-web-crawler.

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

# --- FINJA-531 [tool] owner=finja-web-crawler module=finja-web-crawler ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class SearchBackendError(AppError):
    code_num = 531
    to_inbox = False  # DuckDuckGo/Tor/Google trouble is external: logged with its code, not sent to Flare
    def __init__(self, message: str = 'A search backend (DuckDuckGo or the Google fallback) failed.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-web-crawler'), **kw)

# --- FINJA-532 [tool] owner=finja-web-crawler module=finja-web-crawler ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class CrawlSpawnError(AppError):
    code_num = 532
    def __init__(self, message: str = 'Starting or reaching a short-lived crawl worker failed.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-web-crawler'), **kw)

# --- FINJA-533 [tool] owner=finja-web-crawler module=finja-web-crawler ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class CrawlerApiUnexpectedError(AppError):
    code_num = 533
    def __init__(self, message: str = 'A web crawler request failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-web-crawler'), **kw)

# --- FINJA-534 [tool] owner=finja-web-crawler module=finja-web-crawler ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class CrawlerDiagnosticsProbeError(AppError):
    code_num = 534
    def __init__(self, message: str = 'Web crawler diagnostics probe hit a real bug.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-web-crawler'), **kw)


# --- FINJA-512 [analytics] shared with Finja (ledger owner: analytics) ---
class AnalyticsDeliveryError(AppError):
    """Analytics events could not be delivered (never to the inbox)."""

    code_num = 512
    to_inbox = False

    def __init__(self, message: str = "Analytics events could not be delivered.", **kw):
        super().__init__(message, module=kw.pop("module", "finja-web-crawler"), **kw)
