"""
Project: Finja - Twitch Interactivity Suite
Module: finja-cloud-memory / memory_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 4.5.0
Description: Small memory statistics behind the owner-only diagnostics probe.
New in 4.5.0: average_memory_importance carries a real, harmless bug on purpose (no memory
    yet divides by zero) so Flare's onboarding of the memory server has something to repair.
    Do not fix it by hand; Flare's candidate fixes it after John's approval.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""

from __future__ import annotations

from collections.abc import Sequence


def average_memory_importance(importances: Sequence[float]) -> float:
    """Mean importance of a user's memories; a user without memories should report 0.0."""
    return sum(importances) / len(importances)


def memories_per_day(count: int, days: float) -> float:
    """Stored memories per day; no time yet reports 0.0."""
    return count / days if days > 0 else 0.0
