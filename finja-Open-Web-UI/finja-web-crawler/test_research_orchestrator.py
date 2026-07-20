"""
======================================================================
        Finja Web Crawler – Research Orchestrator Test Suite
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-web-crawler / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
  Description:
    Finja Research Orchestrator tests. These cover the mother service
    contract without touching the network.
======================================================================
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import research_orchestrator as orchestrator
from research_orchestrator import app


orchestrator.EXPECTED_BEARER_TOKEN = "test-bearer-token-12345"
orchestrator.CRAWL_WORKER_URL = ""

client = TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-bearer-token-12345"}


class FakeResponse:
    """Small requests.Response stand-in for mocked POST calls."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class TestResearchAuth:
    """Authentication tests."""

    def test_search_requires_bearer_token(self):
        response = client.post("/search", json={"query": "anime", "count": 2})
        assert response.status_code == 401

    def test_invalid_bearer_token_rejected(self):
        response = client.post(
            "/search",
            json={"query": "anime", "count": 2},
            headers={"Authorization": "Bearer nope"},
        )
        assert response.status_code == 401


class TestResearchOrchestrator:
    """Search, crawl, and research behavior."""

    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["service"] == "finja-research-orchestrator"

    @patch("research_orchestrator.requests.post")
    def test_search_proxies_and_dedupes_results(self, mock_post, auth_headers):
        mock_post.return_value = FakeResponse([
            {"link": "https://example.com/a", "title": "A", "snippet": "First"},
            {"link": "https://example.com/a", "title": "A duplicate", "snippet": "Second"},
            {"link": "https://example.com/b", "title": "B", "snippet": "Third"},
        ])

        response = client.post("/search", json={"query": "test", "count": 3}, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "search-proxy"
        assert len(data["results"]) == 2
        assert data["results"][0]["rank"] == 1
        assert data["results"][1]["rank"] == 2

    def test_crawl_requires_worker(self, auth_headers):
        response = client.post(
            "/crawl",
            json={"url": "https://example.com", "max_chars": 1000},
            headers=auth_headers,
        )
        assert response.status_code == 503
        assert "Crawl worker is not configured" in response.json()["detail"]

    @patch("research_orchestrator.requests.post")
    def test_research_falls_back_to_snippets_without_worker(self, mock_post, auth_headers):
        mock_post.return_value = FakeResponse([
            {"link": "https://example.com/a", "title": "A", "snippet": "Snippet A"},
            {"link": "https://example.com/b", "title": "B", "snippet": "Snippet B"},
        ])

        response = client.post(
            "/research",
            json={"query": "new anime", "count": 2, "crawl_top_n": 2},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["crawl_enabled"] is False
        assert len(data["sources"]) == 2
        assert data["sources"][0]["source_quality"] == "snippet_only"
        assert "crawl_worker_not_configured" in data["notes"][0]
        assert "Snippet A" in data["research_context"]
