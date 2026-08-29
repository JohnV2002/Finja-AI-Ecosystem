"""
Project: Finja - Twitch Interactivity Suite
Module: finja-everything-in-once / structured exceptions
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.1
Description: Structured FINJA error types owned by the music module.
New in 1.2.1: Added FINJA-407 for Spotify access-token refresh failures.
Copyright (c) 2026 J. Apps — MIT License

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

# --- FINJA-407 [session] owner=finja-everything-in-once module=finja_music ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class SpotifyAccessTokenRefreshError(AppError):
    code_num = 407
    def __init__(self, message: str = 'Spotify rejected or could not refresh the user access token.', **kw):
        super().__init__(message, module=kw.pop('module', 'finja_music'), **kw)

