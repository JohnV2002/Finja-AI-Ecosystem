"""
Project: Finja - Twitch Interactivity Suite
Module: finja-music-docker-spotify / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.1
Description: Structured FINJA errors of the Docker music service (module finja-music-docker).
New in 1.3.0: First version: FINJA-408 Spotify reauthorization, FINJA-522 polling loop,
    FINJA-523 unexpected request, FINJA-524 diagnostics probe, shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.

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

# --- FINJA-408 [session] owner=finja-music-docker-spotify module=finja-music-docker ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class SpotifyReauthorizationRequiredError(AppError):
    code_num = 408
    def __init__(self, message: str = 'Spotify login expired or was revoked; reauthorization is needed.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-music-docker'), **kw)

# --- FINJA-522 [tool] owner=finja-music-docker-spotify module=finja-music-docker ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MusicDockerLoopError(AppError):
    code_num = 522
    def __init__(self, message: str = 'The Spotify polling loop failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-music-docker'), **kw)

# --- FINJA-523 [tool] owner=finja-music-docker-spotify module=finja-music-docker ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MusicDockerApiUnexpectedError(AppError):
    code_num = 523
    def __init__(self, message: str = 'A Finja Music Docker request failed unexpectedly.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-music-docker'), **kw)

# --- FINJA-524 [tool] owner=finja-music-docker-spotify module=finja-music-docker ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class MusicDockerDiagnosticsProbeError(AppError):
    code_num = 524
    def __init__(self, message: str = 'Finja Music Docker diagnostics probe hit a real bug.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja-music-docker'), **kw)


# --- FINJA-512 [analytics] shared with Finja (ledger owner: analytics) ---
class AnalyticsDeliveryError(AppError):
    """Analytics events could not be delivered (never to the inbox)."""

    code_num = 512
    to_inbox = False

    def __init__(self, message: str = "Analytics events could not be delivered.", **kw):
        super().__init__(message, module=kw.pop("module", "finja-music-docker"), **kw)
