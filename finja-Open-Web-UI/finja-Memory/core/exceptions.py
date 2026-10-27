"""
Project: Finja - Twitch Interactivity Suite
Module: finja-cloud-memory / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 4.5.1
Description: Structured FINJA errors of the memory server (module finja-memory).
New in 4.5.0: First version: FINJA-107 not configured, FINJA-528 memory file storage,
    FINJA-529 unexpected request, FINJA-530 diagnostics probe, shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.

Structured errors used locally by finja-Memory.

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

# --- FINJA-107 [config] owner=finja-memory module=finja-memory ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MemoryNotConfiguredError(AppError):
    code_num = 107
    def __init__(self, message: str = 'The memory server is not configured (a key or setting is missing).', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-memory'), **kw)

# --- FINJA-528 [tool] owner=finja-memory module=finja-memory ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MemoryStorageError(AppError):
    code_num = 528
    def __init__(self, message: str = 'Reading or writing a memory file failed.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-memory'), **kw)

# --- FINJA-529 [tool] owner=finja-memory module=finja-memory ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MemoryApiUnexpectedError(AppError):
    code_num = 529
    def __init__(self, message: str = 'A memory server request failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-memory'), **kw)

# --- FINJA-530 [tool] owner=finja-memory module=finja-memory ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MemoryDiagnosticsProbeError(AppError):
    code_num = 530
    def __init__(self, message: str = 'Memory server diagnostics probe hit a real bug.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-memory'), **kw)


# --- FINJA-512 [analytics] shared with Finja (ledger owner: analytics) ---
class AnalyticsDeliveryError(AppError):
    """Analytics events could not be delivered (never to the inbox)."""

    code_num = 512
    to_inbox = False

    def __init__(self, message: str = "Analytics events could not be delivered.", **kw):
        super().__init__(message, module=kw.pop("module", "finja-memory"), **kw)
