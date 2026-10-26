"""
Project: Finja - Twitch Interactivity Suite
Module: finja-weather / tests / test_weather_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: Unit tests for the weather statistics: plain unittest classes without heavy imports,
    so Flare's offline sandbox (unittest discovery) can run them next to weather_stats.py.
New in v1.1.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import unittest

from weather_stats import mean_temperature, rain_share


class RainShare(unittest.TestCase):
    def test_some_rainy_hours(self) -> None:
        self.assertEqual(rain_share(6, 24), 0.25)

    def test_rain_all_day(self) -> None:
        self.assertEqual(rain_share(24, 24), 1.0)


class MeanTemperature(unittest.TestCase):
    def test_empty_forecast(self) -> None:
        self.assertEqual(mean_temperature([]), 0.0)

    def test_several_hours(self) -> None:
        self.assertEqual(mean_temperature([10.0, 12.0, 14.0]), 12.0)


if __name__ == "__main__":
    unittest.main()
