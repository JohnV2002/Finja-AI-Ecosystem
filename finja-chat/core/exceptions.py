"""
======================================================================
                    Finja AI Ecosystem
======================================================================

  Project: Finja AI Ecosystem
  Module:  finja-chat / core/exceptions.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.4.1
  Description:
    Structured runtime errors owned and used by the Finja Chat module.

  New in v2.4.1:
    - Version aligned; existing Twitch security error codes are unchanged

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import traceback
from typing import Any, Optional

CODE_PREFIX = "FINJA"


def set_code_prefix(prefix: str) -> None:
    """Set the shared namespace branding without changing code ownership."""
    global CODE_PREFIX
    CODE_PREFIX = (prefix or "FINJA").strip().upper()


class AppError(Exception):
    """Non-numbered local base for concrete Finja Chat errors."""

    code_num: Optional[int] = None
    to_inbox = True

    def __init__(
        self,
        message: str,
        module: str = "finja-chat",
        cause: Optional[Exception] = None,
        **context: Any,
    ) -> None:
        self.module = module
        self.context = context
        self.cause = cause
        super().__init__(message)

    @property
    def code(self) -> str:
        if self.code_num is None:
            raise TypeError("Only concrete error classes own FINJA codes")
        return f"{CODE_PREFIX}-{self.code_num}"

    def for_dashboard(self) -> dict[str, Any]:
        target = self.cause if self.cause is not None else self
        trace = ""
        if getattr(target, "__traceback__", None) is not None:
            trace = "".join(
                traceback.format_exception(type(target), target, target.__traceback__, limit=4)
            )
        return {
            "code": self.code,
            "message": str(self),
            "module": self.module,
            "context": self.context,
            "cause": f"{type(self.cause).__name__}: {self.cause}" if self.cause else None,
            "traceback": trace,
            "to_inbox": self.to_inbox,
        }


class SessionError(AppError):
    """Non-numbered base for session and authentication failures."""


class TwitchDeviceAuthorizationFailedError(SessionError):
    """FINJA-404: Twitch Device Code authorization could not complete."""

    code_num = 404


class TwitchAccessTokenRefreshError(SessionError):
    """FINJA-405: Twitch rejected or could not complete token rotation."""

    code_num = 405


class TwitchChatReconnectRecoveryError(SessionError):
    """FINJA-406: Chat could not reconnect after credential recovery."""

    code_num = 406
