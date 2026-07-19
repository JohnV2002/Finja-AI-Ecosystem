#!/usr/bin/env python3
"""
======================================================================
             Finja Instagram Reels – API Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Unit tests for the container API (instagram_api.py) --
               cookie parsing (JSON + Netscape TXT) and all REST
               endpoints, with the Chrome/Playwright connection fully
               mocked (no real browser or CDP connection needed).

  New in v1.0.0:
    • Initial test suite for finja-instagram
    • Cookie-loading tests for both JSON and Netscape TXT formats,
      including the JSON-first-then-TXT-fallback behavior of
      _load_cookies()
    • Endpoint tests for /health, /status, /wakeup, /sleep, /scroll,
      /like
    • Error-path coverage: channel scrape failure, missing like
      button, wakeup/sleep idempotency (already_awake/already_sleeping)

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
# JSON Cookie Loading Tests (pure function -- no mocking needed)
# ==============================================================================

class TestLoadCookiesJson:
    """Tests for _load_cookies_json(): browser-export JSON -> Playwright format."""

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        from instagram_api import _load_cookies_json

        assert _load_cookies_json(str(tmp_path / "does_not_exist.json")) == []

    def test_invalid_json_returns_empty_list(self, tmp_path: Path) -> None:
        """A corrupt export must not crash the container -- just skip it."""
        from instagram_api import _load_cookies_json

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("{not valid json", encoding="utf-8")

        assert _load_cookies_json(str(cookie_file)) == []

    def test_basic_cookie_conversion(self, tmp_path: Path) -> None:
        from instagram_api import _load_cookies_json

        raw = [{
            "name": "sessionid",
            "value": "abc123",
            "domain": ".instagram.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "no_restriction",
            "expirationDate": 1999999999.9,
        }]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        cookie = _load_cookies_json(str(cookie_file))[0]
        assert cookie["name"] == "sessionid"
        assert cookie["domain"] == ".instagram.com"
        assert cookie["secure"] is True
        assert cookie["sameSite"] == "None"  # no_restriction -> None
        # Instagram's loader int()s the expiry (unlike YouTube's, which keeps the float)
        assert cookie["expires"] == 1999999999
        assert isinstance(cookie["expires"], int)

    def test_skips_cookies_with_partition_key(self, tmp_path: Path) -> None:
        from instagram_api import _load_cookies_json

        raw = [
            {"name": "a", "value": "1", "domain": ".instagram.com", "partitionKey": {}},
            {"name": "b", "value": "2", "domain": ".instagram.com"},
        ]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        result = _load_cookies_json(str(cookie_file))
        assert len(result) == 1
        assert result[0]["name"] == "b"

    @pytest.mark.parametrize("raw_value,expected", [
        ("unspecified", "None"),
        ("no_restriction", "None"),
        ("lax", "Lax"),
        ("strict", "Strict"),
        ("", "None"),
    ])
    def test_same_site_mapping(self, tmp_path: Path, raw_value: str, expected: str) -> None:
        from instagram_api import _load_cookies_json

        raw = [{"name": "c", "value": "v", "domain": ".instagram.com", "sameSite": raw_value}]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        assert _load_cookies_json(str(cookie_file))[0]["sameSite"] == expected


# ==============================================================================
# Netscape TXT Cookie Loading Tests (pure function -- no mocking needed)
# ==============================================================================

class TestLoadCookiesTxt:
    """Tests for _load_cookies_txt(): Netscape cookie file -> Playwright format."""

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        from instagram_api import _load_cookies_txt

        assert _load_cookies_txt(str(tmp_path / "does_not_exist.txt")) == []

    def test_parses_valid_netscape_line(self, tmp_path: Path) -> None:
        from instagram_api import _load_cookies_txt

        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text(
            ".instagram.com\tTRUE\t/\tTRUE\t1999999999\tsessionid\tabc123\n",
            encoding="utf-8",
        )

        result = _load_cookies_txt(str(cookie_file))
        assert len(result) == 1
        cookie = result[0]
        assert cookie["name"] == "sessionid"
        assert cookie["value"] == "abc123"
        assert cookie["domain"] == ".instagram.com"
        assert cookie["secure"] is True
        assert cookie["expires"] == 1999999999

    def test_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        from instagram_api import _load_cookies_txt

        content = (
            "# Netscape HTTP Cookie File\n"
            "\n"
            ".instagram.com\tTRUE\t/\tFALSE\t0\tcsrftoken\txyz\n"
        )
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text(content, encoding="utf-8")

        result = _load_cookies_txt(str(cookie_file))
        assert len(result) == 1
        assert result[0]["name"] == "csrftoken"
        assert result[0]["secure"] is False

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        """A line with fewer than 7 tab-separated fields is skipped, not crashed on."""
        from instagram_api import _load_cookies_txt

        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("too\tfew\tfields\n", encoding="utf-8")

        assert _load_cookies_txt(str(cookie_file)) == []

    def test_zero_expiry_is_omitted(self, tmp_path: Path) -> None:
        """A session cookie (expires=0) should not get an 'expires' key."""
        from instagram_api import _load_cookies_txt

        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text(".instagram.com\tTRUE\t/\tTRUE\t0\tsession\tval\n", encoding="utf-8")

        assert "expires" not in _load_cookies_txt(str(cookie_file))[0]


# ==============================================================================
# Combined _load_cookies(): JSON-first, TXT-fallback
# ==============================================================================

class TestLoadCookiesCombined:
    """Tests for _load_cookies(): tries JSON first, falls back to TXT."""

    def test_prefers_json_when_both_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from instagram_api import _load_cookies

        json_file = tmp_path / "cookies.json"
        json_file.write_text(json.dumps([{"name": "from_json", "value": "1", "domain": ".instagram.com"}]), encoding="utf-8")
        txt_file = tmp_path / "cookies.txt"
        txt_file.write_text(".instagram.com\tTRUE\t/\tTRUE\t0\tfrom_txt\t2\n", encoding="utf-8")

        monkeypatch.setattr("instagram_api.COOKIES_JSON", str(json_file))
        monkeypatch.setattr("instagram_api.COOKIES_TXT", str(txt_file))

        result = _load_cookies()
        assert len(result) == 1
        assert result[0]["name"] == "from_json"

    def test_falls_back_to_txt_when_json_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from instagram_api import _load_cookies

        txt_file = tmp_path / "cookies.txt"
        txt_file.write_text(".instagram.com\tTRUE\t/\tTRUE\t0\tfrom_txt\t2\n", encoding="utf-8")

        monkeypatch.setattr("instagram_api.COOKIES_JSON", str(tmp_path / "missing.json"))
        monkeypatch.setattr("instagram_api.COOKIES_TXT", str(txt_file))

        result = _load_cookies()
        assert len(result) == 1
        assert result[0]["name"] == "from_txt"

    def test_returns_empty_when_neither_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from instagram_api import _load_cookies

        monkeypatch.setattr("instagram_api.COOKIES_JSON", str(tmp_path / "missing.json"))
        monkeypatch.setattr("instagram_api.COOKIES_TXT", str(tmp_path / "missing.txt"))

        assert _load_cookies() == []


# ==============================================================================
# Fixtures: fully mocked Chrome/Playwright connection
# ==============================================================================

def _make_mock_page(url: str = "about:blank", title: str = "Instagram") -> MagicMock:
    """Builds a MagicMock standing in for a Playwright Page."""
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value=title)

    async def _goto(target_url, **kwargs):
        page.url = target_url

    page.goto = AsyncMock(side_effect=_goto)
    page.screenshot = AsyncMock(return_value=b"fake-jpeg-bytes")
    page.keyboard.press = AsyncMock()
    page.mouse.click = AsyncMock()
    page.evaluate = AsyncMock(return_value="DefaultChannel")

    popup_button = MagicMock()
    popup_button.is_visible = AsyncMock(return_value=False)
    popup_button.click = AsyncMock()
    popup_locator = MagicMock()
    popup_locator.first = popup_button
    page.locator = MagicMock(return_value=popup_locator)

    return page


@pytest.fixture
def mock_playwright_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """
    Mocks async_playwright() so the FastAPI lifespan never touches a real
    Chrome/CDP connection. Yields the mocked Page for endpoint assertions.
    """
    # No cookie files -> lifespan takes the "no cookies" branch, keeping
    # tests independent of any real cookie files on disk.
    monkeypatch.setattr("instagram_api.COOKIES_JSON", str(tmp_path / "missing_cookies.json"))
    monkeypatch.setattr("instagram_api.COOKIES_TXT", str(tmp_path / "missing_cookies.txt"))

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

    with patch("instagram_api.async_playwright", return_value=pw_context_manager):
        yield page


@pytest.fixture
def client(mock_playwright_env: MagicMock) -> TestClient:
    """FastAPI TestClient with a mocked Chrome connection (lifespan-safe)."""
    from instagram_api import app

    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# Health Endpoint Tests
# ==============================================================================

class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_reports_connected_browser(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["browser_connected"] is True


# ==============================================================================
# Status Endpoint Tests
# ==============================================================================

class TestStatusEndpoint:
    """Tests for GET /status."""

    def test_status_reports_asleep_by_default(self, client: TestClient) -> None:
        """The container starts on about:blank -- not 'awake' until /wakeup is called."""
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "about:blank"
        assert data["awake"] is False

    def test_status_reports_awake_after_wakeup(self, client: TestClient) -> None:
        client.post("/wakeup")
        response = client.get("/status")

        data = response.json()
        assert data["awake"] is True
        assert "instagram.com" in data["url"]


# ==============================================================================
# Wakeup Endpoint Tests
# ==============================================================================

class TestWakeupEndpoint:
    """Tests for POST /wakeup."""

    def test_wakeup_navigates_to_instagram(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        response = client.post("/wakeup")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "awake"
        assert "instagram.com" in data["url"]
        mock_playwright_env.goto.assert_called_once()
        mock_playwright_env.mouse.click.assert_called_once()

    def test_wakeup_is_idempotent(self, client: TestClient) -> None:
        """Calling /wakeup a second time while already awake is a no-op, not a re-navigation."""
        client.post("/wakeup")
        response = client.post("/wakeup")

        assert response.status_code == 200
        assert response.json()["status"] == "already_awake"


# ==============================================================================
# Sleep Endpoint Tests
# ==============================================================================

class TestSleepEndpoint:
    """Tests for POST /sleep."""

    def test_sleep_is_a_noop_when_already_asleep(self, client: TestClient) -> None:
        response = client.post("/sleep")

        assert response.status_code == 200
        assert response.json()["status"] == "already_sleeping"

    def test_sleep_returns_to_about_blank_after_wakeup(self, client: TestClient) -> None:
        client.post("/wakeup")
        response = client.post("/sleep")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sleeping"
        assert data["url"] == "about:blank"


# ==============================================================================
# Scroll Endpoint Tests
# ==============================================================================

class TestScrollEndpoint:
    """Tests for POST /scroll."""

    def test_scroll_returns_channel_and_screenshot(self, client: TestClient) -> None:
        response = client.post("/scroll")

        assert response.status_code == 200
        data = response.json()
        assert data["channel"] == "DefaultChannel"
        assert data["screenshot_b64"]
        base64.b64decode(data["screenshot_b64"])  # must be valid base64

    def test_scroll_detects_url_change_as_scrolled(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        async def _press(key):
            if key == "ArrowDown":
                mock_playwright_env.url = "https://www.instagram.com/reels/xyz456/"

        mock_playwright_env.keyboard.press = AsyncMock(side_effect=_press)

        response = client.post("/scroll")

        assert response.json()["scrolled"] is True

    def test_scroll_reports_not_scrolled_when_url_unchanged(self, client: TestClient) -> None:
        """A stuck/buffering Reel (URL doesn't change) is reported, not silently ignored."""
        response = client.post("/scroll")

        assert response.json()["scrolled"] is False

    def test_scroll_handles_channel_scrape_error(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        mock_playwright_env.evaluate = AsyncMock(side_effect=Exception("boom"))

        response = client.post("/scroll")

        assert response.status_code == 200
        assert response.json()["channel"] == "Unknown"


# ==============================================================================
# Like Endpoint Tests
# ==============================================================================

class TestLikeEndpoint:
    """Tests for POST /like."""

    def test_like_clicks_visible_heart(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        mock_playwright_env.evaluate = AsyncMock(return_value={"liked": True, "method": "button"})

        response = client.post("/like")

        assert response.status_code == 200
        data = response.json()
        assert data["liked"] is True
        assert data["method"] == "button"

    def test_like_returns_false_when_no_button_found(self, client: TestClient, mock_playwright_env: MagicMock) -> None:
        mock_playwright_env.evaluate = AsyncMock(return_value={"liked": False})

        response = client.post("/like")

        assert response.status_code == 200
        data = response.json()
        assert data["liked"] is False
        assert "reason" in data


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with verbose output when executed directly.

    Usage:
        python test_instagram_api.py

    Or with pytest:
        pytest test_instagram_api.py -v
    """
    pytest.main([__file__, "-v", "--color=yes"])
