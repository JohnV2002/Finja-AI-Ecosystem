"""
Project: Finja - Twitch Interactivity Suite
Module: finja-web-crawler / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 2.2.0
Description: The owner-only probe, structured error reports and which failures reach Flare
    (our own bugs) or stay in the log (external search backends, slow sites). Lives next to the
    code (not in tests/) because it needs pytest and FastAPI.
New in v2.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the Apache License 2.0.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
TOKEN = "probe-" + "p" * 16

import crawler_reporting  # noqa: E402
import main  # noqa: E402
import research_orchestrator as orchestrator  # noqa: E402
from analytics_sender import AnalyticsConfig, AnalyticsSender  # noqa: E402
from core.exceptions import (  # noqa: E402
    CrawlerApiUnexpectedError,
    CrawlerDiagnosticsProbeError,
    CrawlSpawnError,
    SearchBackendError,
)


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(crawler_reporting.analytics, "record_exception", lambda error: seen.append(error))
    monkeypatch.setattr(crawler_reporting, "_last_reported", {})
    return seen


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8080",
               "ANALYTICS_TOKEN": "ingest-token"}, version="2.2.0")
    assert problem is None and config.project_id == "finja-web-crawler"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_probe_is_hidden_without_the_token(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAWLER_PROBE_TOKEN", raising=False)
    client = TestClient(orchestrator.app, raise_server_exceptions=False)
    assert client.get("/diagnostics/probe", params={"token": "x"}).status_code == 404
    monkeypatch.setenv("CRAWLER_PROBE_TOKEN", TOKEN)
    assert client.get("/diagnostics/probe", params={"token": "wrong"}).status_code == 404
    assert reported == []


def test_probe_reports_the_real_bug(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAWLER_PROBE_TOKEN", TOKEN)
    client = TestClient(orchestrator.app, raise_server_exceptions=False)
    response = client.get("/diagnostics/probe", params={"token": TOKEN})
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-534"
    assert isinstance(reported[0], CrawlerDiagnosticsProbeError)


def test_a_failing_search_backend_is_logged_but_never_sent_to_flare(reported, monkeypatch) -> None:
    broken = MagicMock(side_effect=RuntimeError("tor exit blocked"))
    monkeypatch.setattr(main, "DDGS", broken)
    assert main.ddg_search("finja", 3) == []
    assert isinstance(reported[0], SearchBackendError) and reported[0].code == "FINJA-531"
    assert _sender().record_exception(reported[0]) is None  # to_inbox=False: no event for Flare


def test_an_unexpected_search_failure_is_reported(reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "EXPECTED_BEARER_TOKEN", None)
    monkeypatch.setattr(main, "_sanitize_query", MagicMock(side_effect=ValueError("bad state")))
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post("/search", json={"query": "finja", "count": 3})
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-533"
    assert isinstance(reported[0], CrawlerApiUnexpectedError) and isinstance(reported[0].cause, ValueError)


@pytest.fixture()
def spawner(reported):
    with patch("docker.from_env", return_value=MagicMock()):
        sys.modules.pop("crawl_spawner", None)
        module = importlib.import_module("crawl_spawner")
    return module


def test_a_docker_failure_is_our_bug_and_reaches_flare(spawner, reported, monkeypatch) -> None:
    from docker.errors import DockerException

    monkeypatch.setattr(spawner, "_start_worker", MagicMock(side_effect=DockerException("socket gone")))
    client = TestClient(spawner.app, raise_server_exceptions=False)
    assert client.post("/crawl", json={"url": "https://example.org"}).status_code == 502
    assert [e.code for e in reported] == ["FINJA-532"] and isinstance(reported[0], CrawlSpawnError)


def test_a_slow_site_is_not_reported(spawner, reported, monkeypatch) -> None:
    monkeypatch.setattr(spawner, "_start_worker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(spawner, "_wait_for_worker", MagicMock())
    monkeypatch.setattr(spawner, "_cleanup_worker", MagicMock())
    monkeypatch.setattr(spawner.requests, "post", MagicMock(side_effect=requests.Timeout("site too slow")))
    client = TestClient(spawner.app, raise_server_exceptions=False)
    assert client.post("/crawl", json={"url": "https://example.org"}).status_code == 502
    assert reported == []


def test_analytics_is_off_without_the_switch() -> None:
    assert crawler_reporting.analytics.enabled is False


def test_the_probe_error_points_flare_at_crawler_stats() -> None:
    sender = _sender()
    try:
        try:
            orchestrator.crawl_success_rate(0, 0)
        except ZeroDivisionError as exc:
            raise CrawlerDiagnosticsProbeError("probe", module="finja-web-crawler") from exc
    except CrawlerDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event["error"]["code"] == "FINJA-534" and event["error"]["affected_file"] == "crawler_stats.py"
