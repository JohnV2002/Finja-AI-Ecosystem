"""
Project: Finja - Twitch Interactivity Suite
Module: finja-music-docker-spotify / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.3.1
Description: Spotify login expiry (FINJA-408), rate limits, the owner-only probe, structured
    failure reports and the re-login helper behave as expected. Lives next to the code (not in
    tests/) because it needs pytest and FastAPI, which Flare's unittest sandbox does not have.
New in 1.3.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
with patch("threading.Thread.start"):  # no background Spotify loop in tests
    app_module = importlib.import_module("app")

import spotify_reauth  # noqa: E402
from analytics_sender import AnalyticsConfig, AnalyticsSender  # noqa: E402
from core.exceptions import (  # noqa: E402
    MusicDockerApiUnexpectedError,
    MusicDockerDiagnosticsProbeError,
    MusicDockerLoopError,
    SpotifyReauthorizationRequiredError,
)

TOKEN = "probe-" + "p" * 16


def _response(status: int, body: dict | None = None, headers: dict | None = None) -> MagicMock:
    response = MagicMock(status_code=status, headers=headers or {})
    response.json.return_value = body or {}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}", response=response)
    return response


@pytest.mark.parametrize("value", ["fixture-credential-" + "x" * 24, "invalid_scope\nfixture-private-value", "unexpected_error"])
def test_unknown_oauth_error_never_reaches_logs(credentials, monkeypatch, capsys, value):
    response = _response(400, {"error": value})
    monkeypatch.setattr(app_module.requests, "post", lambda *args, **kwargs: response)
    with pytest.raises(requests.HTTPError):
        app_module.refresh_token()
    output = capsys.readouterr().out
    assert value not in output
    assert "unrecognized_oauth_error" in output


@pytest.mark.parametrize("name", ["invalid_grant", "invalid_client", "invalid_request", "invalid_scope", "unauthorized_client", "unsupported_grant_type", "server_error", "temporarily_unavailable"])
def test_oauth_error_classifier_preserves_supported_names(name):
    assert app_module._oauth_error(_response(400, {"error": name})) == name


@pytest.mark.parametrize("body", [{}, {"error": None}, {"error": 123}, [], "unexpected body"])
def test_oauth_error_classifier_handles_other_response_shapes(body):
    response = MagicMock()
    response.json.return_value = body
    assert app_module._oauth_error(response) == ""


def test_oauth_error_classifier_handles_invalid_json():
    response = MagicMock()
    response.json.side_effect = ValueError("not json")
    assert app_module._oauth_error(response) == ""


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(app_module.analytics, "record_exception", lambda error: seen.append(error))
    monkeypatch.setattr(app_module, "_last_reported", {})
    return seen


@pytest.fixture()
def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(app_module, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(app_module, "SPOTIFY_REFRESH_TOKEN", "refresh")


def test_a_revoked_login_is_finja_408(credentials) -> None:
    revoked = _response(400, {"error": "invalid_grant", "error_description": "Refresh token revoked"})
    with patch.object(app_module.requests, "post", return_value=revoked):
        with pytest.raises(SpotifyReauthorizationRequiredError) as caught:
            app_module.refresh_token()
    assert caught.value.code == "FINJA-408"
    assert caught.value.context["reason"] == "reauthorization_needed"
    assert "Refresh token revoked" not in str(caught.value)  # Spotify's body is never echoed


def test_missing_credentials_are_finja_408_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "SPOTIFY_REFRESH_TOKEN", "")
    with pytest.raises(SpotifyReauthorizationRequiredError) as caught:
        app_module.refresh_token()
    assert caught.value.context["reason"] == "not_configured"


def test_three_quick_tries_then_a_quiet_retry(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list = []
    monkeypatch.setattr(app_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(app_module, "_reauth_failures", 0)
    for _ in range(4):
        app_module._on_reauthorization_needed(SpotifyReauthorizationRequiredError("expired", reason="reauthorization_needed"))
    assert sleeps == [60, 60, app_module.REAUTH_RETRY_S, app_module.REAUTH_RETRY_S]
    assert len(reported) == 4 and app_module.SPOTIFY_STATE["status"] == "reauthorization_needed"


def test_rate_limits_wait_for_retry_after(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list = []
    monkeypatch.setattr(app_module.time, "sleep", sleeps.append)
    limited = _response(429, headers={"Retry-After": "42"})
    app_module._on_spotify_http_error(requests.HTTPError("429", response=limited))
    huge = _response(429, headers={"Retry-After": "99999"})
    app_module._on_spotify_http_error(requests.HTTPError("429", response=huge))
    assert sleeps == [42, app_module.MAX_RETRY_AFTER_S] and reported == []


def test_an_expired_access_token_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "ACCESS_TOKEN", "old")
    app_module._on_spotify_http_error(requests.HTTPError("401", response=_response(401)))
    assert app_module.ACCESS_TOKEN == ""


def test_loop_failures_are_reported_at_most_once_a_minute(reported) -> None:
    for _ in range(5):
        app_module.report_throttled(MusicDockerLoopError("loop", cause=ValueError("bad")))
    assert len(reported) == 1 and isinstance(reported[0], MusicDockerLoopError)


@pytest.fixture()
def client():
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_health_shows_the_spotify_state(client) -> None:
    body = client.get("/health").json()
    assert body["ok"] is True and "status" in body["spotify"]


def test_probe_is_hidden_without_the_token(client, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUSIC_DOCKER_PROBE_TOKEN", raising=False)
    assert client.get("/diagnostics/probe", params={"token": "x"}).status_code == 404
    monkeypatch.setenv("MUSIC_DOCKER_PROBE_TOKEN", TOKEN)
    assert client.get("/diagnostics/probe", params={"token": "wrong"}).status_code == 404
    assert reported == []


def test_probe_is_quiet_after_flares_fix(client, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    """Flare's approved fix (2026-10-27): no finished song now reports 0.0 instead of crashing."""
    monkeypatch.setenv("MUSIC_DOCKER_PROBE_TOKEN", TOKEN)
    response = client.get("/diagnostics/probe", params={"token": TOKEN})
    assert response.status_code == 200 and response.json() == {"probe": "average_listen_seconds", "value": 0.0}
    assert reported == []


def test_an_unexpected_request_failure_is_reported(client, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "KB", None)  # /get/songs needs the index
    response = client.get("/get/songs")
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-523"
    assert isinstance(reported[0], MusicDockerApiUnexpectedError)


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8080",
               "ANALYTICS_TOKEN": "ingest-token"}, version="1.3.1")
    assert problem is None and config.project_id == "finja-music-docker-spotify"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_an_expired_login_gets_an_env_fingerprint_so_flare_asks_a_person(credentials) -> None:
    sender = _sender()
    revoked = _response(400, {"error": "invalid_grant"})
    with patch.object(app_module.requests, "post", return_value=revoked):
        try:
            app_module.refresh_token()
        except SpotifyReauthorizationRequiredError as error:
            event = sender.record_exception(error)
    assert event is not None and event["error"]["code"] == "FINJA-408"
    assert event["error"]["fingerprint"].startswith("env-")


def test_an_error_inside_listening_stats_points_flare_at_it() -> None:
    sender = _sender()
    try:
        try:
            app_module.average_listen_seconds([None])
        except TypeError as exc:
            raise MusicDockerDiagnosticsProbeError("probe", probe="average_listen_seconds") from exc
    except MusicDockerDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event["error"]["affected_file"] == "listening_stats.py"


def test_reauth_helper_replaces_only_the_refresh_token(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("SPOTIFY_CLIENT_ID=a\nSPOTIFY_CLIENT_SECRET=b\nSPOTIFY_REFRESH_TOKEN=old\nOTHER=1\n", encoding="utf-8")
    spotify_reauth.set_env_value(env, "SPOTIFY_REFRESH_TOKEN", "new")
    assert spotify_reauth.read_env(env) == {"SPOTIFY_CLIENT_ID": "a", "SPOTIFY_CLIENT_SECRET": "b",
                                            "SPOTIFY_REFRESH_TOKEN": "new", "OTHER": "1"}


@pytest.mark.skipif(sys.platform != "win32", reason="the Hidden attribute exists on Windows only")
def test_reauth_helper_can_write_a_hidden_env_file(tmp_path: Path) -> None:
    import ctypes

    env = tmp_path / ".env"
    env.write_text("SPOTIFY_REFRESH_TOKEN=old\n", encoding="utf-8")
    assert ctypes.windll.kernel32.SetFileAttributesW(str(env), 0x2)  # FILE_ATTRIBUTE_HIDDEN
    spotify_reauth.set_env_value(env, "SPOTIFY_REFRESH_TOKEN", "new")
    assert spotify_reauth.read_env(env) == {"SPOTIFY_REFRESH_TOKEN": "new"}
    assert ctypes.windll.kernel32.GetFileAttributesW(str(env)) & 0x2  # still hidden


def test_reauth_helper_updates_the_all_in_one_config(tmp_path: Path) -> None:
    config = tmp_path / "config_spotify.json"
    config.write_text(json.dumps({"output": "x", "spotify": {"client_id": "a", "refresh_token": "old"}}), encoding="utf-8")
    spotify_reauth.set_all_in_one_token(config, "new")
    assert json.loads(config.read_text(encoding="utf-8")) == {"output": "x", "spotify": {"client_id": "a", "refresh_token": "new"}}
