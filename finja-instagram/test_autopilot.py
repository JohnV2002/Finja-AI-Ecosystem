#!/usr/bin/env python3
"""
======================================================================
             Finja Instagram Reels – Autopilot Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Tests for autopilot.py -- the prototype autonomous
               browsing loop. load_instagram_cookies() and
               buffer_buster_jump() are real, synchronous, mockable
               functions and get full unit tests. The Brain/Discord
               placeholders get behavior-locking tests. The autopilot()
               loop itself connects to a live Chrome/CDP session and
               runs forever (while True), so it's covered by
               structural/content checks instead of execution (same
               approach as finja-chat's test_batch_files.py).

  New in v1.0.0:
    • Initial test suite for autopilot.py
    • load_instagram_cookies(): JSON -> Playwright cookie transform,
      missing-file handling, invalid-expiry discarding, sameSite
      validation, corrupt-file error handling
    • buffer_buster_jump(): retry-until-URL-changes logic, including
      the "Instagram stuck" give-up-after-3-retries path
    • ask_brain() / send_to_discord() placeholder unit tests
    • Structural sanity checks for the autopilot() loop

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ==============================================================================
# load_instagram_cookies() Tests
# ==============================================================================

class TestLoadInstagramCookies:
    """Tests for load_instagram_cookies(): JSON export -> Playwright cookies."""

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        from autopilot import load_instagram_cookies

        context = MagicMock()
        result = load_instagram_cookies(context, filepath=str(tmp_path / "missing.json"))

        assert result is False
        context.add_cookies.assert_not_called()

    def test_valid_cookies_are_injected(self, tmp_path: Path) -> None:
        from autopilot import load_instagram_cookies

        raw = [{
            "name": "sessionid",
            "value": "abc123",
            "domain": ".instagram.com",
            "path": "/",
            "expires": 1999999999.0,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        context = MagicMock()
        result = load_instagram_cookies(context, filepath=str(cookie_file))

        assert result is True
        context.add_cookies.assert_called_once()
        injected = context.add_cookies.call_args[0][0]
        assert len(injected) == 1
        cookie = injected[0]
        assert cookie["name"] == "sessionid"
        assert cookie["expires"] == 1999999999
        assert cookie["httpOnly"] is True
        assert cookie["sameSite"] == "Lax"

    def test_corrupt_json_returns_false(self, tmp_path: Path) -> None:
        from autopilot import load_instagram_cookies

        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("{not valid json", encoding="utf-8")

        context = MagicMock()
        result = load_instagram_cookies(context, filepath=str(cookie_file))

        assert result is False
        context.add_cookies.assert_not_called()

    def test_invalid_expiration_is_discarded(self, tmp_path: Path) -> None:
        """expires=None must not be sent to Playwright as literal -1."""
        from autopilot import load_instagram_cookies

        raw = [{"name": "a", "value": "v", "domain": ".instagram.com", "expires": None}]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        context = MagicMock()
        load_instagram_cookies(context, filepath=str(cookie_file))

        injected = context.add_cookies.call_args[0][0]
        assert "expires" not in injected[0]

    def test_invalid_same_site_is_dropped(self, tmp_path: Path) -> None:
        """An out-of-spec sameSite value must be dropped, not passed through raw."""
        from autopilot import load_instagram_cookies

        raw = [{"name": "a", "value": "v", "domain": ".instagram.com", "sameSite": "no_restriction"}]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(raw), encoding="utf-8")

        context = MagicMock()
        load_instagram_cookies(context, filepath=str(cookie_file))

        injected = context.add_cookies.call_args[0][0]
        assert "sameSite" not in injected[0]


# ==============================================================================
# buffer_buster_jump() Tests
# ==============================================================================

class TestBufferBusterJump:
    """Tests for buffer_buster_jump(): retries ArrowDown until the URL changes."""

    @pytest.fixture(autouse=True)
    def _no_real_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Retry logic is what's under test, not real timing -- skip the waits."""
        import autopilot
        monkeypatch.setattr(autopilot.time, "sleep", lambda seconds: None)

    def test_succeeds_on_first_press(self) -> None:
        from autopilot import buffer_buster_jump

        page = MagicMock()
        page.url = "https://www.instagram.com/reels/before/"

        def _press(key):
            page.url = "https://www.instagram.com/reels/after/"

        page.keyboard.press.side_effect = _press

        buffer_buster_jump(page)

        assert page.keyboard.press.call_count == 1
        assert page.url == "https://www.instagram.com/reels/after/"

    def test_retries_until_url_changes(self) -> None:
        from autopilot import buffer_buster_jump

        page = MagicMock()
        page.url = "https://www.instagram.com/reels/stuck/"
        call_count = {"n": 0}

        def _press(key):
            call_count["n"] += 1
            if call_count["n"] == 3:
                page.url = "https://www.instagram.com/reels/unstuck/"

        page.keyboard.press.side_effect = _press

        buffer_buster_jump(page)

        assert page.keyboard.press.call_count == 3
        assert page.url == "https://www.instagram.com/reels/unstuck/"

    def test_gives_up_after_three_retries(self) -> None:
        """If Instagram stays stuck, the function must return instead of looping forever."""
        from autopilot import buffer_buster_jump

        page = MagicMock()
        page.url = "https://www.instagram.com/reels/permanently_stuck/"
        # keyboard.press never changes page.url -> should give up, not hang

        buffer_buster_jump(page)

        # 1 initial press + 3 retries = 4 total
        assert page.keyboard.press.call_count == 4
        assert page.url == "https://www.instagram.com/reels/permanently_stuck/"


# ==============================================================================
# ask_brain() Tests
# ==============================================================================

class TestAskBrain:
    """
    ask_brain() is a stubbed placeholder (a coin flip) meant to be replaced
    with a real Vision-LLM call later.
    """

    def test_returns_a_boolean(self) -> None:
        from autopilot import ask_brain

        result = ask_brain("Some caption", "@SomeCreator", "base64screenshotdata")
        assert isinstance(result, bool)

    def test_respects_mocked_random_choice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import autopilot

        monkeypatch.setattr(autopilot.random, "choice", lambda seq: True)
        assert autopilot.ask_brain("t", "c", "b64") is True

        monkeypatch.setattr(autopilot.random, "choice", lambda seq: False)
        assert autopilot.ask_brain("t", "c", "b64") is False


# ==============================================================================
# send_to_discord() Tests
# ==============================================================================

class TestSendToDiscord:
    """send_to_discord() is a stubbed placeholder (just prints)."""

    def test_does_not_raise(self) -> None:
        from autopilot import send_to_discord

        send_to_discord("https://www.instagram.com/reels/abc123/")

    def test_prints_the_video_url(self, capsys: pytest.CaptureFixture) -> None:
        from autopilot import send_to_discord

        send_to_discord("https://www.instagram.com/reels/xyz789/")

        captured = capsys.readouterr()
        assert "xyz789" in captured.out


# ==============================================================================
# autopilot() Structural Sanity Checks
# ==============================================================================

class TestAutopilotLoopStructure:
    """
    autopilot() connects to a live Chrome/CDP session and runs an infinite
    'while True' loop -- not unit-testable without refactoring the
    prototype. These checks inspect the source instead of executing it.
    """

    @pytest.fixture(scope="class")
    def source(self) -> str:
        with open(os.path.join(BASE_DIR, "autopilot.py"), "r", encoding="utf-8") as f:
            return f.read()

    def test_has_crash_safety_net(self, source: str) -> None:
        assert "except Exception as error" in source, \
            "Autopilot loop has no top-level crash handler -- a connection " \
            "drop would kill the process instead of logging FINJA-203!"
        assert "FINJA-203" in source

    def test_watches_each_reel_like_a_human(self, source: str) -> None:
        assert "random.randint(10, 18)" in source

    def test_injects_cookies_before_the_loop_starts(self, source: str) -> None:
        assert "load_instagram_cookies(context)" in source

    def test_advances_via_buffer_buster(self, source: str) -> None:
        assert "buffer_buster_jump(page)" in source

    def test_asks_the_brain_before_liking(self, source: str) -> None:
        assert "ask_brain(" in source


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with verbose output when executed directly.

    Usage:
        python test_autopilot.py

    Or with pytest:
        pytest test_autopilot.py -v
    """
    pytest.main([__file__, "-v", "--color=yes"])
