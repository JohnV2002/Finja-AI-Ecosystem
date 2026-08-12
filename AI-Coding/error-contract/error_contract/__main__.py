"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/__main__.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description:
    python -m error_contract entrypoint.

  New in v1.0.0:
    • Production release packaging for public GitHub
    • Cross-project engine, ambient hooks, global code ledger
    • See repository README.md / INSTALL.md / AMBIENT.md

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from .cli import main

raise SystemExit(main())
