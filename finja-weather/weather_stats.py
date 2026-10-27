"""
Project: Finja - Twitch Interactivity Suite
Module: finja-weather / weather_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: Small weather statistics behind the owner-only diagnostics probe.
New in v1.1.0: rain_share carries a real, harmless bug on purpose (no hour looked at yet
    divides by zero) so Flare's onboarding of the weather service has something to repair.
    Fixed on 2026-10-26 by Flare's approved candidate (applied live on the VM).
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations


def rain_share(rainy_hours: int, hours: int) -> float:
    """Share of forecast hours with rain; no hour looked at yet should report 0.0."""
    if hours == 0:
        return 0.0
    return rainy_hours / hours


def mean_temperature(temperatures: list[float]) -> float:
    """Mean temperature of a forecast; an empty forecast reports 0.0."""
    return sum(temperatures) / len(temperatures) if temperatures else 0.0
