"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  examples/fake-omni/core/exceptions.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Demo: module_under_parent style FINJA-branded exceptions.

  New in v1.0.0:
    • Production release packaging for public GitHub
    • Cross-project engine, ambient hooks, global code ledger
    • See repository README.md / INSTALL.md / AMBIENT.md

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import traceback
from typing import Any, Optional

CODE_PREFIX = "FINJA"  # Boot: set_code_prefix("FINJA")


def set_code_prefix(prefix: str) -> None:
    """Setzt das Branding der Error-Codes (z.B. 'FINJA' -> FINJA-601)."""
    global CODE_PREFIX
    CODE_PREFIX = (prefix or "APP").strip().upper()


class AppError(Exception):
    """Basis fuer alle strukturierten Fehler."""

    code_num: int = 900
    to_inbox: bool = True

    def __init__(
        self,
        message: str,
        module: str = "unknown",
        cause: Optional[Exception] = None,
        **context: Any,
    ) -> None:
        self.module = module
        self.context = context
        self.cause = cause
        parts = [message]
        if module != "unknown":
            parts.append(f"[module={module}]")
        if context:
            parts.append("[" + ", ".join(f"{k}={v}" for k, v in context.items()) + "]")
        if cause:
            parts.append(f"(caused by {type(cause).__name__}: {cause})")
        self.full_message = " ".join(parts)
        super().__init__(self.full_message)

    @property
    def code(self) -> str:
        return f"{CODE_PREFIX}-{self.code_num}"

    def short(self) -> str:
        return f"[{self.code}] {self.args[0] if self.args else 'Unknown error'}"

    def for_dashboard(self) -> dict[str, Any]:
        exc_for_tb = self.cause if self.cause is not None else self
        tb = ""
        if getattr(exc_for_tb, "__traceback__", None) is not None:
            tb = "".join(
                traceback.format_exception(
                    type(exc_for_tb), exc_for_tb, exc_for_tb.__traceback__, limit=4
                )
            )
        return {
            "code": self.code,
            "message": str(self),
            "module": self.module,
            "context": self.context,
            "cause": f"{type(self.cause).__name__}: {self.cause}" if self.cause else None,
            "traceback": tb,
            "to_inbox": self.to_inbox,
        }


# --- 1xx CONFIG ---------------------------------------------------------
class ConfigError(AppError):
    code_num = 100

    def __init__(self, message: str, key: Optional[str] = None, **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "config"), key=key, **kw)


class EnvError(ConfigError):
    code_num = 101

    def __init__(self, var_name: str, **kw: Any) -> None:
        super().__init__(
            f"Missing .env variable: {var_name}",
            key=var_name,
            hint=f"Add {var_name}=... to .env",
            **kw,
        )


# --- 2xx LLM ------------------------------------------------------------
class LLMError(AppError):
    code_num = 200

    def __init__(self, message: str, model: str = "unknown", **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "llm"), model=model, **kw)


class LLMTimeoutError(LLMError):
    code_num = 201


# --- 4xx SESSION / AUTH -------------------------------------------------
class SessionError(AppError):
    code_num = 400

    def __init__(self, message: str, **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "session"), **kw)


class AuthError(SessionError):
    code_num = 401


# --- 5xx TOOL -----------------------------------------------------------
class ToolError(AppError):
    code_num = 500

    def __init__(self, message: str, tool_name: Optional[str] = None, **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "tools"), tool_name=tool_name, **kw)


class ToolExecutionError(ToolError):
    code_num = 502


# --- 6xx PIPELINE / GUARD -----------------------------------------------
class PipelineError(AppError):
    code_num = 600

    def __init__(self, message: str, node: Optional[str] = None, **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "pipeline"), node=node, **kw)


class GuardError(PipelineError):
    code_num = 601

    def __init__(self, message: str, **kw: Any) -> None:
        super().__init__(message, node="guard", **kw)


# --- 8xx HOST -----------------------------------------------------------
class HostError(AppError):
    code_num = 800

    def __init__(self, message: str, **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "system"), **kw)


# --- 9xx UNEXPECTED -----------------------------------------------------
class UnexpectedError(AppError):
    code_num = 999

    def __init__(self, cause: Exception, module: str = "unknown", **kw: Any) -> None:
        super().__init__(f"Unexpected {type(cause).__name__}", module=module, cause=cause, **kw)


# --- 10xx / 11xx FIREWALL -----------------------------------------------
class PrivacyError(AppError):
    code_num = 1000
    to_inbox = False

    def __init__(self, message: str, **kw: Any) -> None:
        super().__init__(message, module=kw.pop("module", "privacy_guard"), **kw)


class PromptInjectionError(AppError):
    code_num = 1100
    to_inbox = False

    def __init__(self, surface: str = "unknown", **kw: Any) -> None:
        super().__init__(
            f"Prompt injection detected in '{surface}'",
            module=kw.pop("module", "prompt_guard"),
            surface=surface,
            **kw,
        )
