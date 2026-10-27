"""
Project: Finja - Twitch Interactivity Suite
Module: finja-web-crawler / crawler_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.2.0
Description: Small research statistics behind the owner-only diagnostics probe.
New in v2.2.0: crawl_success_rate carries a real, harmless bug on purpose (no crawl yet
    divides by zero) so Flare's onboarding of the web crawler has something to repair.
    Fixed on 2026-10-26 by Flare's approved candidate (applied live on the VM).
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""

from __future__ import annotations


def crawl_success_rate(succeeded: int, attempted: int) -> float:
    """Share of crawls that returned text; no crawl attempted yet should report 0.0."""
    return succeeded / attempted if attempted > 0 else 0.0


def sources_per_research(sources: int, researches: int) -> float:
    """Average sources per research run; no run yet reports 0.0."""
    return sources / researches if researches > 0 else 0.0
