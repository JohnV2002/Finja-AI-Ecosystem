"""
Project: Finja - Twitch Interactivity Suite
Module: finja-weather / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: The owner-only probe, structured error reports and which failures reach Flare
    (our own bugs, a missing key as a person's task) or stay in the log (provider outages).
    Lives next to the code (not in tests/) because it needs pytest and FastAPI.
New in v1.1.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import weather_api
from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import (
    WeatherApiUnexpectedError,
    WeatherDiagnosticsProbeError,
    WeatherNotConfiguredError,
    WeatherProviderFailedError,
)
from providers import WeatherNotConfiguredProviderError, WeatherProviderError

ROOT = Path(weather_api.__file__).resolve().parent
TOKEN = "probe-" + "p" * 16


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(weather_api.analytics, "record_exception", lambda error: seen.append(error))
    monkeypatch.setattr(weather_api, "_last_reported", {})
    return seen


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8080",
               "ANALYTICS_TOKEN": "ingest-token"}, version="1.1.0")
    assert problem is None and config.project_id == "finja-weather"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_probe_is_hidden_without_the_token(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEATHER_PROBE_TOKEN", raising=False)
    client = TestClient(weather_api.app, raise_server_exceptions=False)
    assert client.get("/diagnostics/probe", params={"token": "x"}).status_code == 404
    assert reported == []


def test_probe_reports_the_real_bug(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHER_PROBE_TOKEN", TOKEN)
    client = TestClient(weather_api.app, raise_server_exceptions=False)
    response = client.get("/diagnostics/probe", params={"token": TOKEN})
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-537"
    assert isinstance(reported[0], WeatherDiagnosticsProbeError)


def test_a_provider_outage_is_logged_but_never_sent_to_flare(reported) -> None:
    weather_api.report_provider_failure(WeatherProviderError("open-meteo request failed: timeout"), "current")
    assert isinstance(reported[0], WeatherProviderFailedError) and reported[0].code == "FINJA-535"
    assert _sender().record_exception(reported[0]) is None  # to_inbox=False


def test_a_missing_google_key_is_a_task_for_a_person(reported) -> None:
    try:
        raise WeatherNotConfiguredProviderError(
            "Weather is not configured: GOOGLE_WEATHER_API_KEY is missing (needed for pollen/air quality).")
    except WeatherNotConfiguredProviderError as exc:
        weather_api.report_provider_failure(exc, "pollen")
    error = reported[0]
    assert isinstance(error, WeatherNotConfiguredError) and error.code == "FINJA-108"
    event = _sender().record_exception(error)
    assert event is not None and event["error"]["fingerprint"].startswith("env-config-")


def test_an_unexpected_failure_is_reported(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(weather_api, "_m_snapshot", MagicMock(side_effect=RuntimeError("broken counters")))
    client = TestClient(weather_api.app, raise_server_exceptions=False)
    response = client.get("/stats")
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-536"
    assert isinstance(reported[0], WeatherApiUnexpectedError)


def test_analytics_is_off_without_the_switch() -> None:
    assert weather_api.analytics.enabled is False


def test_the_probe_error_points_flare_at_weather_stats() -> None:
    sender = _sender()
    try:
        try:
            weather_api.rain_share(0, 0)
        except ZeroDivisionError as exc:
            raise WeatherDiagnosticsProbeError("probe", module="finja-weather") from exc
    except WeatherDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event["error"]["code"] == "FINJA-537" and event["error"]["affected_file"] == "weather_stats.py"
