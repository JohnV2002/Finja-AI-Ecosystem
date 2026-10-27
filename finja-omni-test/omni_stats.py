"""
======================================================================
         Finja Omni Test – Observation Statistics
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / omni_stats
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Small observation statistics behind the diagnostics probe.

 New in v1.1.0:
  average_ocr_confidence carries a real, harmless bug on purpose (no
  OCR line yet divides by zero) so Flare's onboarding of Finja Omni has
  something to repair. Fixed on 2026-10-26 with Flare's approved
  candidate (applied to the repo; Omni runs from this folder).
======================================================================
"""
from __future__ import annotations

from collections.abc import Sequence


def average_ocr_confidence(confidences: Sequence[float]) -> float:
    """Mean OCR confidence of a frame; a frame without OCR lines should report 0.0."""
    return sum(confidences) / len(confidences) if confidences else 0.0


def frames_per_minute(frames: int, minutes: float) -> float:
    """Saved frames per minute; no time observed yet reports 0.0."""
    return frames / minutes if minutes > 0 else 0.0
