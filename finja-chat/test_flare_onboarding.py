"""
Project: Finja Chat System
Module: finja-chat / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.5.0
Description: The song server starts without Spotify credentials, reports unexpected failures
    with structured codes, and its owner-only probe and analytics behave as Flare expects.
New in v2.5.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

server = importlib.import_module("spotify_request_server_env")

from analytics_sender import AnalyticsConfig, AnalyticsSender  # noqa: E402
from core.exceptions import SongRequestUnexpectedError, SpotifyNotConfiguredError  # noqa: E402

ROOT = Path(server.__file__).resolve().parent


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(server, "report_failure", lambda error: seen.append(error))
    return seen


def test_spotify_is_only_set_up_when_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    lazy = server._LazySpotify()
    with pytest.raises(SpotifyNotConfiguredError) as caught:
        lazy.devices()
    assert caught.value.code == "FINJA-103" and "nicht konfiguriert" in str(caught.value)


def test_a_missing_configuration_keeps_answering_and_is_reported(reported, monkeypatch) -> None:
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    monkeypatch.setattr(server, "sp", server._LazySpotify())
    assert server.list_devices() == []
    assert reported and reported[0].code == "FINJA-513"
    assert isinstance(reported[0].cause, SpotifyNotConfiguredError)


def test_probe_is_hidden_without_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINJA_CHAT_PROBE_TOKEN", "probe-" + "p" * 16)
    client = TestClient(server.app, raise_server_exceptions=False)
    assert client.get("/diagnostics/probe").status_code == 404
    assert client.get("/diagnostics/probe", params={"token": "wrong"}).status_code == 404


def test_probe_reports_the_real_bug(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    token = "probe-" + "p" * 16
    monkeypatch.setenv("FINJA_CHAT_PROBE_TOKEN", token)
    client = TestClient(server.app, raise_server_exceptions=False)
    response = client.get("/diagnostics/probe", params={"token": token})
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-514"
    assert [error.code for error in reported] == ["FINJA-514"]


def test_analytics_is_off_without_the_switch() -> None:
    assert server.analytics.enabled is False


def test_a_missing_setting_gets_an_env_fingerprint_so_flare_asks_a_person() -> None:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://analytics-collector:8080",
               "ANALYTICS_TOKEN": "ingest-token"})
    assert problem is None and config.project_id == "finja-chat"
    sender = AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())
    with patch.dict("os.environ", {"SPOTIPY_CLIENT_ID": ""}):
        try:
            server._LazySpotify().devices()  # raises inside the server, as in production
        except SpotifyNotConfiguredError as missing:
            try:
                raise SongRequestUnexpectedError("Device list failed", operation="devices", cause=missing) from missing
            except SongRequestUnexpectedError as error:
                event = sender.record_exception(error)
    assert event is not None and event["error"]["fingerprint"].startswith("env-config-")
    assert event["error"]["affected_file"] == "spotify_request_server_env.py"
