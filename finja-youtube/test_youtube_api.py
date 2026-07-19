#!/usr/bin/env python3
"""
======================================================================
              Finja YouTube Shorts – API Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-youtube / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Unit tests for the container API (youtube_api.py) --
               cookie parsing and all REST endpoints, with the
               Chrome/Playwright connection fully mocked (no real
               browser or CDP connection needed to run these tests).

  New in v1.0.0:
    • Initial test suite for finja-youtube
    • Cookie-loading tests (Browser-export JSON -> Playwright format,
      sameSite mapping, partitionKey filtering, expiry handling)
    • Endpoint tests for /health, /ip, /status, /scroll, /like
    • Error-path coverage: metadata scrape failure, missing like
      button, unreachable VPN-IP services

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ==============================================================================
# Cookie Loading Tests (pure function -- no mocking needed)
# ==============================================================================

class TestLoadCookies:
    """
    Tests for _load_cookies(): converts a browser cookie export (JSON)
    into the cookie format Playwright's context.add_cookies() expects.
    """

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        """A non-existent cookie file should not raise -- just no cookies."""
        from youtube_api import _load_cookies

        result = _load_cookies(str(tmp_path / "does_not_exist.json"))
        assert result == []

    def test_basic_cookie_conversion(self, tmp_path: Path) -> None:
        """Full-featured cookie is translated field-for-field correctly."""
        from youtube_api import _load_cookies

        raw = [{
            "name": "SID",
            "value": "abc123",
            "domain": ".youtube.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "no_restriction",
            "expirationDate": 1999999999.0,
        }]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        result = _load_cookies(str(cookie_file))

        assert len(result) == 1
        cookie = result[0]
        assert cookie["name"] == "SID"
        assert cookie["value"] == "abc123"
        assert cookie["domain"] == ".youtube.com"
        assert cookie["secure"] is True
        assert cookie["httpOnly"] is True
        assert cookie["sameSite"] == "None"  # no_restriction -> None
        assert cookie["expires"] == 1999999999.0

    def test_skips_cookies_with_partition_key(self, tmp_path: Path) -> None:
        """Chrome's partitioned cookies aren't Playwright-compatible -- skip them."""
        from youtube_api import _load_cookies

        raw = [
            {"name": "a", "value": "1", "domain": ".youtube.com", "partitionKey": {}},
            {"name": "b", "value": "2", "domain": ".youtube.com"},
        ]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        result = _load_cookies(str(cookie_file))

        assert len(result) == 1
        assert result[0]["name"] == "b"

    def test_defaults_for_missing_optional_fields(self, tmp_path: Path) -> None:
        """A minimal cookie still gets sane defaults for the optional fields."""
        from youtube_api import _load_cookies

        raw = [{"name": "minimal", "value": "x", "domain": ".youtube.com"}]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        cookie = _load_cookies(str(cookie_file))[0]
        assert cookie["path"] == "/"
        assert cookie["secure"] is False
        assert cookie["httpOnly"] is False
        assert cookie["sameSite"] == "None"
        assert "expires" not in cookie

    @pytest.mark.parametrize("raw_value,expected", [
        ("unspecified", "None"),
        ("no_restriction", "None"),
        ("lax", "Lax"),
        ("strict", "Strict"),
        ("", "None"),
        ("something_unknown", "None"),
    ])
    def test_same_site_mapping(self, tmp_path: Path, raw_value: str, expected: str) -> None:
        """Every Chrome sameSite value maps to a valid Playwright value."""
        from youtube_api import _load_cookies

        raw = [{"name": "c", "value": "v", "domain": ".youtube.com", "sameSite": raw_value}]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        result = _load_cookies(str(cookie_file))
        assert result[0]["sameSite"] == expected

    def test_ignores_zero_expiration(self, tmp_path: Path) -> None:
        """expirationDate of 0 (session cookie) should not set 'expires'."""
        from youtube_api import _load_cookies

        raw = [{"name": "session", "value": "v", "domain": ".youtube.com", "expirationDate": 0}]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        result = _load_cookies(str(cookie_file))
        assert "expires" not in result[0]


# ==============================================================================
# Fixtures: fully mocked Chrome/Playwright connection
# ==============================================================================

def _make_mock_page(url: str = "https://m.youtube.com/shorts", title: str = "Test Video") -> MagicMock:
    """Builds a MagicMock standing in for a Playwright Page."""
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.goto = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fake-jpeg-bytes")
    page.keyboard.press = AsyncMock()
    page.evaluate = AsyncMock(return_value={"title": "Scraped Title", "channel": "@scraped_channel"})

    like_button = MagicMock()
    like_button.is_visible = AsyncMock(return_value=True)
    like_button.click = AsyncMock()
    locator = MagicMock()
    locator.first = like_button
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.fixture
def mock_playwright_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """
    Mocks async_playwright() so the FastAPI lifespan never touches a real
    Chrome/CDP connection. Yields the mocked Page for endpoint assertions.
    """
    # Point at a cookie file that doesn't exist so the lifespan takes the
    # "no cookies" branch -- keeps tests independent of any real cookies.json.
    monkeypatch.setattr("youtube_api.COOKIES_FILE", str(tmp_path / "missing_cookies.json"))

    page = _make_mock_page()
    context = MagicMock()
    context.pages = [page]
    context.new_page = AsyncMock(return_value=page)
    context.add_cookies = AsyncMock()

    browser = MagicMock()
    browser.contexts = [context]
    browser.is_connected = MagicMock(return_value=True)
    browser.close = AsyncMock()

    pw_instance = MagicMock()
    pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    pw_instance.stop = AsyncMock()

    pw_context_manager = MagicMock()
    pw_context_manager.start = AsyncMock(return_value=pw_instance)

    with patch("youtube_api.async_playwright", return_value=pw_context_manager):
        yield page


@pytest.fixture
def client(mock_playwright_env: MagicMock) -> TestClient:
    """FastAPI TestClient with a mocked Chrome connection (lifespan-safe)."""
    from youtube_api import app

    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# Health Endpoint Tests
# ==============================================================================

class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_reports_connected_browser(self, client: TestClient) -> None:
        """Health check reflects a live, connected browser."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["browser_connected"] is True
        assert data["current_url"]


# ==============================================================================
# Status Endpoint Tests
# ==============================================================================

class TestStatusEndpoint:
    """Tests for GET /status."""

    def test_status_returns_url_and_title(self, client: TestClient) -> None:
        """Status reflects the current page's URL and title."""
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "title" in data


# ==============================================================================
# Scroll Endpoint Tests
# ==============================================================================

class TestScrollEndpoint:
    """Tests for POST /scroll."""

    def test_scroll_returns_metadata_and_screenshot(self, client: TestClient) -> None:
        """A successful scroll returns title, channel, and a valid screenshot."""
        response = client.post("/scroll")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Scraped Title"
        assert data["channel"] == "@scraped_channel"
        assert data["screenshot_b64"]
        base64.b64decode(data["screenshot_b64"])  # must be valid base64

    def test_scroll_presses_arrow_down(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        """Scrolling advances to the next Short via ArrowDown."""
        client.post("/scroll")
        mock_playwright_env.keyboard.press.assert_called_with("ArrowDown")

    def test_scroll_handles_metadata_scrape_error(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        """A JS evaluate() failure degrades gracefully instead of crashing."""
        mock_playwright_env.evaluate = AsyncMock(side_effect=Exception("boom"))

        response = client.post("/scroll")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Scrape error"
        assert data["channel"] == "Scrape error"


# ==============================================================================
# Like Endpoint Tests
# ==============================================================================

class TestLikeEndpoint:
    """Tests for POST /like."""

    def test_like_clicks_visible_button(self, client: TestClient) -> None:
        """A visible like button gets clicked and reports success."""
        response = client.post("/like")

        assert response.status_code == 200
        data = response.json()
        assert data["liked"] is True

    def test_like_returns_false_when_no_button_found(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        """When every selector fails, /like reports failure instead of raising."""
        locator = MagicMock()
        locator.first.is_visible = AsyncMock(return_value=False)
        mock_playwright_env.locator = MagicMock(return_value=locator)

        response = client.post("/like")

        assert response.status_code == 200
        data = response.json()
        assert data["liked"] is False
        assert "reason" in data


# ==============================================================================
# VPN IP Endpoint Tests
# ==============================================================================

class TestIpEndpoint:
    """Tests for GET /ip (VPN tunnel verification)."""

    def test_ip_returns_vpn_ip_from_first_reachable_service(self, client: TestClient) -> None:
        """The first reachable IP service's result is returned."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"ip": "203.0.113.42"})

        with patch("youtube_api.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/ip")

        assert response.status_code == 200
        data = response.json()
        assert data["vpn_ip"] == "203.0.113.42"

    def test_ip_returns_error_when_all_services_unreachable(self, client: TestClient) -> None:
        """If every external IP service fails, the endpoint reports an error, not a crash."""
        with patch("youtube_api.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("network unreachable"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.get("/ip")

        assert response.status_code == 200
        data = response.json()
        assert data["vpn_ip"] is None
        assert "error" in data


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with verbose output when executed directly.

    Usage:
        python test_youtube_api.py

    Or with pytest:
        pytest test_youtube_api.py -v
    """
    pytest.main([__file__, "-v", "--color=yes"])
