"""
Project: Finja - Twitch Interactivity Suite
Module: finja-canvas / canvas_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Small canvas statistics behind the owner-only diagnostics probe.
New in v1.2.0: average_motif_pixels carries a real, harmless bug on purpose (no finished
    motifs divides by zero) so Flare's onboarding of Finja Canvas has something to repair.
    Fixed on 2026-10-26 by Flare's approved candidate (applied live on the VM).
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

from collections.abc import Sequence


def average_motif_pixels(motif_sizes: Sequence[int]) -> float:
    """Mean pixels per finished motif; no finished motif yet should report 0.0."""
    if not motif_sizes:
        return 0.0
    return sum(motif_sizes) / len(motif_sizes)


def largest_motif_pixels(motif_sizes: Sequence[int]) -> int:
    """The biggest finished motif; none yet reports 0."""
    return max(motif_sizes, default=0)
