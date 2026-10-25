"""
Project: Finja - Twitch Interactivity Suite
Module: finja-everything-in-once / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.0
Description: The owner-only probe, structured failure reports and the analytics switch of the
    music web server behave as Flare expects. Lives next to the code (not in tests/) because it
    needs pytest and the full server module, which Flare's unittest sandbox does not load.
New in 1.3.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import json
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import webserver
from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import MusicDiagnosticsProbeError, MusicRequestUnexpectedError, SpotifyAccessTokenRefreshError

ROOT = Path(webserver.__file__).resolve().parent
TOKEN = "probe-" + "p" * 16


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(webserver.analytics, "record_exception", lambda error: seen.append(error))
    return seen


@pytest.fixture()
def base_url(reported):
    httpd = socketserver.TCPServer(("127.0.0.1", 0), webserver.MyHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_probe_is_hidden_without_a_token(base_url, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUSIC_PROBE_TOKEN", raising=False)
    assert _get(f"{base_url}/diagnostics/probe?token=anything")[0] == 404
    monkeypatch.setenv("MUSIC_PROBE_TOKEN", TOKEN)
    assert _get(f"{base_url}/diagnostics/probe")[0] == 404
    assert _get(f"{base_url}/diagnostics/probe?token=wrong")[0] == 404
    assert reported == []


def test_probe_reports_the_real_bug(base_url, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUSIC_PROBE_TOKEN", TOKEN)
    status, body = _get(f"{base_url}/diagnostics/probe?token={TOKEN}")
    assert status == 500 and json.loads(body)["message"] == "FINJA-521"
    assert len(reported) == 1 and isinstance(reported[0], MusicDiagnosticsProbeError)
    assert isinstance(reported[0].__cause__, ZeroDivisionError)


def test_an_unexpected_get_failure_is_reported_with_its_cause(base_url, reported, monkeypatch) -> None:
    def broken(_handler):
        raise RuntimeError("queue file vanished")

    monkeypatch.setattr(webserver, "_handle_get_artist_not_sure_entries", broken)
    status, body = _get(f"{base_url}/get_artist_not_sure_entries")
    assert status == 500 and json.loads(body)["message"] == "FINJA-520"
    assert isinstance(reported[0], MusicRequestUnexpectedError)
    assert isinstance(reported[0].cause, RuntimeError)
    assert reported[0].context == {"endpoint": "/get_artist_not_sure_entries"}


def test_an_unexpected_post_failure_no_longer_leaks_the_exception_text(base_url, reported, monkeypatch) -> None:
    def broken(*_args):
        raise OSError("the secret songs database is locked")

    monkeypatch.setattr(webserver, "process_artist_not_sure_action", broken)
    payload = json.dumps({"action": "confirm", "observed_title": "a", "observed_artist": "b",
                          "kb_title": "a", "kb_artist": "b"}).encode()
    request = urllib.request.Request(f"{base_url}/artist_not_sure_action", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=5)
        status, body = 200, b""
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    assert status == 500 and b"secret" not in body and json.loads(body)["message"] == "FINJA-520"
    assert isinstance(reported[0].cause, OSError)


def test_static_overlays_are_still_served(base_url) -> None:
    status, body = _get(f"{base_url}/Musik.html")
    assert status == 200 and b"<html" in body.lower()


def test_analytics_is_off_without_the_switch() -> None:
    assert webserver.analytics.enabled is False


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8081",
               "ANALYTICS_TOKEN": "ingest-token"}, version="1.3.0")
    assert problem is None and config.project_id == "finja-everything-in-once"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_the_probe_error_points_flare_at_music_stats() -> None:
    sender = _sender()
    try:
        try:
            webserver.repeat_rate(0, 0)
        except ZeroDivisionError as exc:
            raise MusicDiagnosticsProbeError("probe", probe="repeat_rate") from exc
    except MusicDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event is not None and event["error"]["code"] == "FINJA-521"
    assert event["error"]["affected_file"] == "music_stats.py"


def test_a_revoked_spotify_grant_gets_an_env_fingerprint_so_flare_asks_a_person() -> None:
    sender = _sender()
    try:
        raise SpotifyAccessTokenRefreshError("Spotify rejected the refresh token (invalid_grant).",
                                             oauth_error="invalid_grant", reauthorization_required=True)
    except SpotifyAccessTokenRefreshError as error:
        event = sender.record_exception(error)
    assert event is not None and event["error"]["code"] == "FINJA-407"
    assert event["error"]["fingerprint"].startswith("env-auth-")
