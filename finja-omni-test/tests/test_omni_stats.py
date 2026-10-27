"""
Project: Finja - Twitch Interactivity Suite
Module: finja-omni-test / tests / test_omni_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: Unit tests for the observation statistics: plain unittest classes without heavy
    imports, so Flare's offline sandbox (unittest discovery) can run them next to omni_stats.py.
New in v1.1.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from omni_stats import average_ocr_confidence, frames_per_minute


class AverageOcrConfidence(unittest.TestCase):
    def test_several_lines(self) -> None:
        self.assertAlmostEqual(average_ocr_confidence([0.8, 0.9, 1.0]), 0.9)

    def test_one_line(self) -> None:
        self.assertEqual(average_ocr_confidence([0.85]), 0.85)


class FramesPerMinute(unittest.TestCase):
    def test_no_time_observed_yet(self) -> None:
        self.assertEqual(frames_per_minute(0, 0), 0.0)

    def test_frames_over_time(self) -> None:
        self.assertEqual(frames_per_minute(30, 10), 3.0)


if __name__ == "__main__":
    unittest.main()
