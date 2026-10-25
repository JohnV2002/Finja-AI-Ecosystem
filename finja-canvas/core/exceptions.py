"""
Project: Finja - Twitch Interactivity Suite
Module: finja-canvas / core / exceptions.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Structured Finja Canvas errors in the shared FINJA namespace (module finja-canvas);
    the codes are reserved in the ecosystem ledger and in Finja V2's ledger.
New in v1.2.0: First version: FINJA-104, FINJA-515, FINJA-516 and the shared FINJA-512.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""
from __future__ import annotations

import traceback
from typing import Any, Optional

CODE_PREFIX = "FINJA"


class AppError(Exception):
    """Non-numbered local base for concrete Finja Canvas errors."""

    code_num: Optional[int] = None
    to_inbox = True

    def __init__(self, message: str, module: str = "finja-canvas", cause: Optional[Exception] = None,
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


class CanvasNotConfiguredError(ConfigError):
    """FINJA-104: Finja Canvas is not configured (the OpenRouter key is missing)."""

    code_num = 104


class ToolError(AppError):
    """Non-numbered base for Finja Canvas's own failures."""


class CanvasPainterError(ToolError):
    """FINJA-515: A painting step failed in a way the painter did not expect."""

    code_num = 515


class CanvasDiagnosticsProbeError(ToolError):
    """FINJA-516: The owner-only diagnostics probe hit its real, harmless bug."""

    code_num = 516


class AnalyticsDeliveryError(AppError):
    """FINJA-512: Analytics events could not be delivered (shared with Finja, never to the inbox)."""

    code_num = 512
    to_inbox = False
