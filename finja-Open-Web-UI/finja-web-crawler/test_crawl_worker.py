"""
======================================================================
            Finja Web Crawler – Crawl Worker Test Suite
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
    Finja Crawl Worker tests. Network calls are mocked; the worker
    contract stays testable offline.
======================================================================
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import crawl_worker
from crawl_worker import app


client = TestClient(app)


class FakeStreamResponse:
    """Small streaming response mock for requests.get."""

    def __init__(self, body: bytes, url: str = "https://example.com/page", content_type: str = "text/html"):
        self.status_code = 200
        self.url = url
        self.headers = {"Content-Type": content_type}
        self._body = body

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=16_384):
        yield self._body


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "finja-crawl-worker"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://localhost",
        "http://10.0.0.1",
        "ftp://example.com/file",
    ],
)
def test_private_or_unsupported_targets_blocked(url):
    response = client.post("/crawl", json={"url": url, "max_chars": 1000})
    assert response.status_code in {400, 403, 422}


@patch("crawl_worker.socket.getaddrinfo")
@patch("crawl_worker.requests.get")
def test_crawl_extracts_sanitized_text(mock_get, mock_getaddrinfo):
    mock_getaddrinfo.return_value = [(None, None, None, None, ("93.184.216.34", 443))]
    mock_get.return_value = FakeStreamResponse(
        b"""
        <html>
          <head><title>Example Page</title><script>alert(1)</script></head>
          <body>
            <main>
              <h1>Hello Research</h1>
              <p>This is useful page text.</p>
              <form><input value="secret"></form>
            </main>
          </body>
        </html>
        """
    )

    response = client.post("/crawl", json={"url": "https://example.com/page", "max_chars": 2000})

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Example Page"
    assert "Hello Research" in data["text"]
    assert "This is useful page text." in data["text"]
    assert "alert" not in data["text"]
    assert "secret" not in data["text"]


@patch("crawl_worker._crawl_slots")
def test_busy_worker_returns_429(mock_slots):
    mock_slots.acquire.return_value = False

    response = client.post("/crawl", json={"url": "https://example.com/page", "max_chars": 1000})

    assert response.status_code == 429
