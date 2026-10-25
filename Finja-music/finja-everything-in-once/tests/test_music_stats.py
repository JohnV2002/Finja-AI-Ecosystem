"""
Project: Finja - Twitch Interactivity Suite
Module: finja-everything-in-once / tests / test_music_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.0
Description: Unit tests for the play statistics: plain unittest classes without heavy imports,
    so Flare's offline sandbox (unittest discovery) can run them next to music_stats.py.
New in 1.3.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from music_stats import repeat_rate, songs_per_hour


class RepeatRate(unittest.TestCase):
    def test_some_repeats(self) -> None:
        self.assertEqual(repeat_rate(2, 8), 0.25)

    def test_only_repeats(self) -> None:
        self.assertEqual(repeat_rate(4, 4), 1.0)


class SongsPerHour(unittest.TestCase):
    def test_no_time_on_air_yet(self) -> None:
        self.assertEqual(songs_per_hour(0, 0), 0.0)

    def test_songs_over_time(self) -> None:
        self.assertEqual(songs_per_hour(30, 2), 15.0)


if __name__ == "__main__":
    unittest.main()
