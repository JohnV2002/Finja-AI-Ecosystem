#!/usr/bin/env python3
"""
======================================================================
              Finja YouTube Shorts – Autopilot Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-youtube / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Tests for autopilot.py -- the prototype autonomous
               browsing loop. The Brain/Discord placeholder functions
               are real unit tests; the autopilot() loop itself
               connects to a live Chrome/CDP session and runs forever
               (while True), so it's covered by structural/content
               checks instead (same approach as test_batch_files.py),
               not execution.

  New in v1.0.0:
    • Initial test suite for autopilot.py
    • ask_brain() / send_to_discord() placeholder unit tests
    • Structural sanity checks for the autopilot() loop (crash safety
      net, human-like watch-time delay, next-video navigation)

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os

import pytest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ==============================================================================
# ask_brain() Tests
# ==============================================================================

class TestAskBrain:
    """
    ask_brain() is a stubbed placeholder (a coin flip) meant to be replaced
    with a real Vision-LLM call later. These tests lock in today's behavior
    so a future edit to the stub doesn't silently break its call signature.
    """

    def test_returns_a_boolean(self) -> None:
        from autopilot import ask_brain

        result = ask_brain("Some Title", "@SomeChannel", "base64screenshotdata")
        assert isinstance(result, bool)

    def test_respects_mocked_random_choice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import autopilot

        monkeypatch.setattr(autopilot.random, "choice", lambda seq: True)
        assert autopilot.ask_brain("t", "c", "b64") is True

        monkeypatch.setattr(autopilot.random, "choice", lambda seq: False)
        assert autopilot.ask_brain("t", "c", "b64") is False

    def test_accepts_empty_metadata_without_crashing(self) -> None:
        from autopilot import ask_brain

        result = ask_brain("", "", "")
        assert isinstance(result, bool)


# ==============================================================================
# send_to_discord() Tests
# ==============================================================================

class TestSendToDiscord:
    """
    send_to_discord() is a stubbed placeholder (just prints) meant to be
    replaced with a real webhook POST later.
    """

    def test_does_not_raise(self) -> None:
        from autopilot import send_to_discord

        send_to_discord("https://www.youtube.com/shorts/abc123")

    def test_prints_the_video_url(self, capsys: pytest.CaptureFixture) -> None:
        from autopilot import send_to_discord

        send_to_discord("https://www.youtube.com/shorts/xyz789")

        captured = capsys.readouterr()
        assert "xyz789" in captured.out


# ==============================================================================
# autopilot() Structural Sanity Checks
# ==============================================================================

class TestAutopilotLoopStructure:
    """
    autopilot() connects to a live Chrome/CDP session and runs an infinite
    'while True' loop -- not unit-testable without refactoring the
    prototype. These checks inspect the source for the safety-relevant
    parts of the loop instead of executing it (same approach used for the
    startup batch scripts in finja-chat's test_batch_files.py).
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

    def test_watches_each_video_like_a_human(self, source: str) -> None:
        """A fixed/near-zero watch time would look bot-like -- must stay randomized."""
        assert "random.randint(10, 18)" in source

    def test_advances_to_next_short(self, source: str) -> None:
        assert 'keyboard.press("ArrowDown")' in source

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
