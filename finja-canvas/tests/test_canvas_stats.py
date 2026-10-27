"""
Project: Finja - Twitch Interactivity Suite
Module: finja-canvas / tests / test_canvas_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: Unit tests for the canvas statistics: plain unittest classes without heavy imports,
    so Flare's offline sandbox (unittest discovery) can run them next to canvas_stats.py.
New in v1.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from canvas_stats import average_motif_pixels, largest_motif_pixels


class AverageMotifPixels(unittest.TestCase):
    def test_average_of_several_motifs(self) -> None:
        self.assertEqual(average_motif_pixels([100, 200, 300]), 200.0)

    def test_average_of_a_single_motif(self) -> None:
        self.assertEqual(average_motif_pixels([42]), 42.0)


class LargestMotifPixels(unittest.TestCase):
    def test_largest_of_no_motif(self) -> None:
        self.assertEqual(largest_motif_pixels([]), 0)

    def test_largest_of_several_motifs(self) -> None:
        self.assertEqual(largest_motif_pixels([30, 90, 40]), 90)


if __name__ == "__main__":
    unittest.main()
