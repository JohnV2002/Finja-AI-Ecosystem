"""
Project: Finja - Twitch Interactivity Suite
Module: finja-instagram / reel_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Small Reel statistics behind the owner-only diagnostics probe.
New in v1.2.0: like_rate carries a real, harmless bug on purpose (no Reel seen yet divides by
    zero) so Flare's onboarding of Finja Instagram has something to repair.
    Fixed on 2026-10-26 by Flare's approved candidate (applied live on the VM).
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations


def like_rate(liked: int, seen: int) -> float:
    """Share of seen Reels that were liked; no Reel seen yet should report 0.0."""
    return liked / seen if seen > 0 else 0.0


def reels_per_minute(seen: int, minutes: float) -> float:
    """How many Reels were watched per minute; no time awake yet reports 0.0."""
    return seen / minutes if minutes > 0 else 0.0
