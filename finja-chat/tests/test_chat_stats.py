"""
Project: Finja Chat System
Module: tests / test_chat_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.5.0
Description: Unit tests for the queue statistics: unittest classes without web frameworks,
    so Flare's offline sandbox (unittest discovery) can run them next to chat_stats.py.
New in v2.5.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from chat_stats import average_wait_seconds, longest_wait_seconds


class AverageWait(unittest.TestCase):
    def test_average_of_a_filled_queue(self) -> None:
        self.assertEqual(average_wait_seconds([10.0, 20.0, 30.0]), 20.0)

    def test_average_of_a_single_request(self) -> None:
        self.assertEqual(average_wait_seconds([42.0]), 42.0)


class LongestWait(unittest.TestCase):
    def test_longest_wait_of_an_empty_queue(self) -> None:
        self.assertEqual(longest_wait_seconds([]), 0.0)

    def test_longest_wait_of_a_filled_queue(self) -> None:
        self.assertEqual(longest_wait_seconds([3.0, 9.0, 4.0]), 9.0)


if __name__ == "__main__":
    unittest.main()
