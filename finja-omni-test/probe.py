"""
======================================================================
         Finja Omni Test – Diagnostics Probe
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / probe
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Owner-only test of the Flare path for a project without a server:
  runs the observation statistics on a frame without OCR lines (a real,
  harmless bug), reports FINJA-527 and exits 1. Run it three times
  within 15 minutes to get a Flare repair card.

    python probe.py

 New in v1.1.0:
  First version.
======================================================================
"""
from __future__ import annotations

import sys

import omni_reporting
from core.exceptions import OmniDiagnosticsProbeError
from omni_stats import average_ocr_confidence


def main() -> int:
    try:
        try:
            value = average_ocr_confidence([])
        except ZeroDivisionError as exc:
            raise OmniDiagnosticsProbeError("Diagnostics probe hit a real bug",
                                            probe="average_ocr_confidence") from exc
    except OmniDiagnosticsProbeError as error:
        omni_reporting.report_failure(error, flush=True)
        return 1
    print(f"probe ok: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
