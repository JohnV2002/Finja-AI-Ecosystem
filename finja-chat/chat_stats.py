"""
Project: Finja Chat System
Module: finja-chat / chat_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.5.0
Description: Small song-request statistics behind the owner-only diagnostics probe.
New in v2.5.0: average_wait_seconds carries a real, harmless bug on purpose (an empty
    queue divides by zero) so Flare's onboarding of Finja Chat has something to repair.
    Fixed on 2026-10-27 by Flare's approved candidate (applied live on the VM).
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

from collections.abc import Sequence


def average_wait_seconds(waits: Sequence[float]) -> float:
    """Mean seconds a request waited in the queue; an empty queue should report 0.0."""
    if len(waits) == 0:
        return 0.0
    return sum(waits) / len(waits)


def longest_wait_seconds(waits: Sequence[float]) -> float:
    """The longest wait in the queue; an empty queue reports 0.0."""
    return max(waits, default=0.0)
