"""
Project: Finja - Twitch Interactivity Suite
Module: finja-omni-test / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: Structured FINJA errors of the Omni test sandbox (owner vpet, module finja-omni-test).
New in v1.1.0: First version: FINJA-106 not configured, FINJA-525 pipeline step, FINJA-526 model
    call, FINJA-527 diagnostics probe, shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.

Structured errors used locally by finja-omni-test.

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

# --- FINJA-106 [config] owner=vpet module=finja-omni-test ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class OmniNotConfiguredError(AppError):
    code_num = 106
    def __init__(self, message: str = 'Finja Omni is not configured (a key or setting is missing).', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-omni-test'), **kw)

# --- FINJA-525 [tool] owner=vpet module=finja-omni-test ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class OmniPipelineError(AppError):
    code_num = 525
    def __init__(self, message: str = 'A capture or OCR step of the Omni pipeline failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-omni-test'), **kw)

# --- FINJA-526 [tool] owner=vpet module=finja-omni-test ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class OmniModelError(AppError):
    code_num = 526
    def __init__(self, message: str = 'A vision or chat model call failed.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-omni-test'), **kw)

# --- FINJA-527 [tool] owner=vpet module=finja-omni-test ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class OmniDiagnosticsProbeError(AppError):
    code_num = 527
    def __init__(self, message: str = 'Finja Omni diagnostics probe hit a real bug.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-omni-test'), **kw)


# --- FINJA-512 [analytics] shared with Finja (ledger owner: analytics) ---
class AnalyticsDeliveryError(AppError):
    """Analytics events could not be delivered (never to the inbox)."""

    code_num = 512
    to_inbox = False

    def __init__(self, message: str = "Analytics events could not be delivered.", **kw):
        super().__init__(message, module=kw.pop("module", "finja-omni-test"), **kw)
