"""
Project: Finja - Twitch Interactivity Suite
Module: finja-music-docker-spotify / tests / test_listening_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.0
Description: Unit tests for the listening statistics: plain unittest classes without heavy
    imports, so Flare's offline sandbox (unittest discovery) can run them next to listening_stats.py.
New in 1.3.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from listening_stats import average_listen_seconds, longest_listen_seconds


class AverageListenSeconds(unittest.TestCase):
    def test_several_songs(self) -> None:
        self.assertEqual(average_listen_seconds([120.0, 180.0, 240.0]), 180.0)

    def test_one_song(self) -> None:
        self.assertEqual(average_listen_seconds([200.0]), 200.0)


class LongestListenSeconds(unittest.TestCase):
    def test_no_song_yet(self) -> None:
        self.assertEqual(longest_listen_seconds([]), 0.0)

    def test_several_songs(self) -> None:
        self.assertEqual(longest_listen_seconds([90.0, 300.0, 120.0]), 300.0)


if __name__ == "__main__":
    unittest.main()
