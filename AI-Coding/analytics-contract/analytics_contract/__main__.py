"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics_contract / __main__.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Python module entry point for Analytics Contract.

  New in v1.0.0:
    - Exposes the CLI through python -m analytics_contract

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())

