"""
Project: Finja - Twitch Interactivity Suite
Module: finja-cloud-memory / tests / test_memory_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 4.5.1
Description: Unit tests for the memory statistics: plain unittest classes without heavy imports,
    so Flare's offline sandbox (unittest discovery) can run them next to memory_stats.py.
New in 4.5.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""

from __future__ import annotations

import unittest

from memory_stats import average_memory_importance, memories_per_day


class AverageMemoryImportance(unittest.TestCase):
    def test_several_memories(self) -> None:
        self.assertAlmostEqual(average_memory_importance([0.2, 0.4, 0.6]), 0.4)

    def test_one_memory(self) -> None:
        self.assertEqual(average_memory_importance([0.9]), 0.9)


class MemoriesPerDay(unittest.TestCase):
    def test_no_time_yet(self) -> None:
        self.assertEqual(memories_per_day(0, 0), 0.0)

    def test_memories_over_time(self) -> None:
        self.assertEqual(memories_per_day(30, 3), 10.0)


if __name__ == "__main__":
    unittest.main()
