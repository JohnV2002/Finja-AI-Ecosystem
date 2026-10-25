"""
Project: Finja - Twitch Interactivity Suite
Module: finja-music-docker-spotify / listening_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.0
Description: Small listening statistics behind the owner-only diagnostics probe.
New in 1.3.0: average_listen_seconds carries a real, harmless bug on purpose (no finished
    song yet divides by zero) so Flare's onboarding of Finja Music Docker has something
    to repair. Do not fix it by hand; Flare's candidate fixes it after John's approval.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

from collections.abc import Sequence


def average_listen_seconds(durations: Sequence[float]) -> float:
    """Mean listening time per finished song; no finished song yet should report 0.0."""
    return sum(durations) / len(durations)


def longest_listen_seconds(durations: Sequence[float]) -> float:
    """The longest listening time; none yet reports 0.0."""
    return max(durations, default=0.0)
