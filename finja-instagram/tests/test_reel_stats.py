"""
Project: Finja - Twitch Interactivity Suite
Module: finja-instagram / tests / test_reel_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Unit tests for the Reel statistics: plain unittest classes without heavy imports,
    so Flare's offline sandbox (unittest discovery) can run them next to reel_stats.py.
New in v1.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from reel_stats import like_rate, reels_per_minute


class LikeRate(unittest.TestCase):
    def test_some_reels_liked(self) -> None:
        self.assertEqual(like_rate(3, 12), 0.25)

    def test_every_reel_liked(self) -> None:
        self.assertEqual(like_rate(5, 5), 1.0)


class ReelsPerMinute(unittest.TestCase):
    def test_no_time_awake_yet(self) -> None:
        self.assertEqual(reels_per_minute(0, 0), 0.0)

    def test_reels_over_time(self) -> None:
        self.assertEqual(reels_per_minute(30, 10), 3.0)


if __name__ == "__main__":
    unittest.main()
