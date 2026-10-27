"""
Project: Finja - Twitch Interactivity Suite
Module: finja-everything-in-once / music_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.0
Description: Small play statistics behind the owner-only diagnostics probe.
New in 1.3.0: repeat_rate carries a real, harmless bug on purpose (no song played yet
    divides by zero) so Flare's onboarding of Finja Music has something to repair.
    Fixed on 2026-10-26 with Flare's approved candidate (applied to the repo and the live copy on the PC).
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations


def repeat_rate(repeats: int, plays: int) -> float:
    """Share of plays that were repeats; no song played yet should report 0.0."""
    if plays == 0:
        return 0.0
    return repeats / plays


def songs_per_hour(plays: int, hours: float) -> float:
    """How many songs played per hour; no time on air yet reports 0.0."""
    return plays / hours if hours > 0 else 0.0
