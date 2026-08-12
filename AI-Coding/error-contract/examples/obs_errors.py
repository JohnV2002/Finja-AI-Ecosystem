"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  examples/obs_errors.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Demo: module-local OBS errors reserved in the global FINJA ledger.

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

try:
    from core.exceptions import AppError  # type: ignore
except ImportError:

    class AppError(Exception):
        code_num = 900

        def __init__(self, message: str = "", module: str = "unknown", **kw):
            self.module = module
            super().__init__(message)


# --- FINJA-504 [tool] owner=obs-bridge module=obs ---
# Ledger-reserved: do not reuse this number under prefix FINJA
class ObsWebsocketDownError(AppError):
    code_num = 504

    def __init__(self, message: str = "obs websocket down", **kw):
        super().__init__(message, module=kw.pop("module", "obs"), **kw)
