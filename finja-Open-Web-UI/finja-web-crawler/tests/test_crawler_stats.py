"""
Project: Finja - Twitch Interactivity Suite
Module: finja-web-crawler / tests / test_crawler_stats.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.2.0
Description: Unit tests for the research statistics: plain unittest classes without heavy
    imports, so Flare's offline sandbox (unittest discovery) can run them next to crawler_stats.py.
New in v2.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""

from __future__ import annotations

import unittest

from crawler_stats import crawl_success_rate, sources_per_research


class CrawlSuccessRate(unittest.TestCase):
    def test_some_crawls_succeeded(self) -> None:
        self.assertEqual(crawl_success_rate(3, 4), 0.75)

    def test_every_crawl_succeeded(self) -> None:
        self.assertEqual(crawl_success_rate(2, 2), 1.0)


class SourcesPerResearch(unittest.TestCase):
    def test_no_research_yet(self) -> None:
        self.assertEqual(sources_per_research(0, 0), 0.0)

    def test_sources_over_runs(self) -> None:
        self.assertEqual(sources_per_research(9, 3), 3.0)


if __name__ == "__main__":
    unittest.main()
