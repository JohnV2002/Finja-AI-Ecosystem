"""
Project: Finja - Twitch Interactivity Suite
Module: finja-instagram / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Structured Finja Instagram errors in the shared FINJA namespace (module finja-instagram);
    the codes are reserved in the ecosystem ledger and in Finja V2's ledger.
New in v1.2.0: First version: FINJA-105, FINJA-517, FINJA-518, FINJA-519 and the shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional

CODE_PREFIX = "FINJA"


class AppError(Exception):
    """Non-numbered local base for concrete Finja Instagram errors."""

    code_num: Optional[int] = None
    to_inbox = True

    def __init__(self, message: str, module: str = "finja-instagram", cause: Optional[Exception] = None,
                 **context: Any) -> None:
        self.module = module
        self.context = context
        self.cause = cause
        super().__init__(message)

    @property
    def code(self) -> str:
        if self.code_num is None:
            raise TypeError("AppError is an abstract base; raise a numbered subclass")
        return f"{CODE_PREFIX}-{self.code_num}"

    def for_dashboard(self) -> dict[str, Any]:
        target = self.cause if self.cause is not None else self
        trace = ""
        if getattr(target, "__traceback__", None) is not None:
            trace = "".join(traceback.format_exception(type(target), target, target.__traceback__, limit=4))
        return {"code": self.code, "message": str(self), "module": self.module, "context": self.context,
                "cause": f"{type(self.cause).__name__}: {self.cause}" if self.cause else None,
                "traceback": trace, "to_inbox": self.to_inbox}


class ConfigError(AppError):
    """Non-numbered base for missing or invalid settings."""


class InstagramCookiesInvalidError(ConfigError):
    """FINJA-105: The Instagram cookie file is not configured correctly (it cannot be read)."""

    code_num = 105


class ToolError(AppError):
    """Non-numbered base for Finja Instagram's own failures."""


class InstagramChromeUnreachableError(ToolError):
    """FINJA-517: The API could not reach its headless Chrome over CDP at startup."""

    code_num = 517


class InstagramApiUnexpectedError(ToolError):
    """FINJA-518: An API request failed in a way the endpoint did not expect."""

    code_num = 518


class InstagramDiagnosticsProbeError(ToolError):
    """FINJA-519: The owner-only diagnostics probe hit its real, harmless bug."""

    code_num = 519


class AnalyticsDeliveryError(AppError):
    """FINJA-512: Analytics events could not be delivered (shared with Finja, never to the inbox)."""

    code_num = 512
    to_inbox = False
