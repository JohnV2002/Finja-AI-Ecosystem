"""
Project: Finja - Twitch Interactivity Suite
Module: finja-weather / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: Structured FINJA errors of the weather service (module finja-weather).
New in v1.1.0: First version: FINJA-108 not configured, FINJA-535 provider failure (logged only),
    FINJA-536 unexpected request, FINJA-537 diagnostics probe, shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.

Structured errors used locally by finja-weather.

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

# --- FINJA-108 [config] owner=finja-weather module=finja-weather ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class WeatherNotConfiguredError(AppError):
    code_num = 108
    def __init__(self, message: str = 'The weather service is not configured (a key or setting is missing).', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-weather'), **kw)

# --- FINJA-535 [tool] owner=finja-weather module=finja-weather ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class WeatherProviderFailedError(AppError):
    code_num = 535
    to_inbox = False  # Open-Meteo/Google trouble is external: logged with its code, not sent to Flare
    def __init__(self, message: str = 'A weather provider (Open-Meteo or Google) failed.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-weather'), **kw)

# --- FINJA-536 [tool] owner=finja-weather module=finja-weather ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class WeatherApiUnexpectedError(AppError):
    code_num = 536
    def __init__(self, message: str = 'A weather request failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-weather'), **kw)

# --- FINJA-537 [tool] owner=finja-weather module=finja-weather ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class WeatherDiagnosticsProbeError(AppError):
    code_num = 537
    def __init__(self, message: str = 'Weather diagnostics probe hit a real bug.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-weather'), **kw)


# --- FINJA-512 [analytics] shared with Finja (ledger owner: analytics) ---
class AnalyticsDeliveryError(AppError):
    """Analytics events could not be delivered (never to the inbox)."""

    code_num = 512
    to_inbox = False

    def __init__(self, message: str = "Analytics events could not be delivered.", **kw):
        super().__init__(message, module=kw.pop("module", "finja-weather"), **kw)
