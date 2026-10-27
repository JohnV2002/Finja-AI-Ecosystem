"""
Project: Finja - Twitch Interactivity Suite
Module: finja-instagram / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: The owner-only probe, structured failure reports and the analytics switch of the
    Instagram API behave as Flare expects. Lives next to the code (not in tests/) because it
    needs pytest and FastAPI, which Flare's unittest sandbox does not have.
New in v1.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import instagram_api
from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import (
    InstagramApiUnexpectedError,
    InstagramChromeUnreachableError,
    InstagramCookiesInvalidError,
    InstagramDiagnosticsProbeError,
)

ROOT = Path(instagram_api.__file__).resolve().parent
TOKEN = "probe-" + "p" * 16


def _playwright(connect: AsyncMock) -> MagicMock:
    instance = MagicMock()
    instance.chromium.connect_over_cdp = connect
    instance.stop = AsyncMock()
    manager = MagicMock()
    manager.start = AsyncMock(return_value=instance)
    return manager


def _browser(page: MagicMock) -> MagicMock:
    context = MagicMock()
    context.pages = [page]
    context.add_cookies = AsyncMock()
    browser = MagicMock()
    browser.contexts = [context]
    browser.is_connected = MagicMock(return_value=True)
    browser.close = AsyncMock()
    return browser


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(instagram_api.analytics, "record_exception", lambda error: seen.append(error))
    return seen


@pytest.fixture()
def page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(instagram_api, "COOKIES_JSON", str(tmp_path / "missing.json"))
    monkeypatch.setattr(instagram_api, "COOKIES_TXT", str(tmp_path / "missing.txt"))
    page = MagicMock()
    page.url = "about:blank"
    page.title = AsyncMock(return_value="")
    return page


@pytest.fixture()
def client(page: MagicMock):
    with patch("instagram_api.async_playwright", return_value=_playwright(AsyncMock(return_value=_browser(page)))):
        with TestClient(instagram_api.app, raise_server_exceptions=False) as test_client:
            yield test_client


def test_probe_is_hidden_without_the_token(client, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSTAGRAM_PROBE_TOKEN", raising=False)
    assert client.get("/diagnostics/probe", params={"token": "anything"}).status_code == 404
    monkeypatch.setenv("INSTAGRAM_PROBE_TOKEN", TOKEN)
    assert client.get("/diagnostics/probe").status_code == 404
    assert client.get("/diagnostics/probe", params={"token": "wrong"}).status_code == 404
    assert reported == []


def test_probe_is_quiet_after_flares_fix(client, reported, monkeypatch: pytest.MonkeyPatch) -> None:
    """Flare's approved fix (2026-10-26): no Reel seen yet now reports 0.0 instead of crashing."""
    monkeypatch.setenv("INSTAGRAM_PROBE_TOKEN", TOKEN)
    response = client.get("/diagnostics/probe", params={"token": TOKEN})
    assert response.status_code == 200 and response.json() == {"probe": "like_rate", "value": 0.0}
    assert reported == []


def test_an_unexpected_endpoint_failure_is_reported_with_its_cause(client, page, reported) -> None:
    page.title = AsyncMock(side_effect=RuntimeError("page crashed"))
    response = client.get("/status")
    assert response.status_code == 500 and response.json()["error"]["code"] == "FINJA-518"
    assert isinstance(reported[0], InstagramApiUnexpectedError)
    assert isinstance(reported[0].cause, RuntimeError)


def test_an_unreadable_cookie_file_is_reported_and_skipped(tmp_path: Path, reported, monkeypatch) -> None:
    broken = tmp_path / "cookies.json"
    broken.write_text("{not json", encoding="utf-8")
    assert instagram_api._load_cookies_json(str(broken)) == []
    assert len(reported) == 1 and isinstance(reported[0], InstagramCookiesInvalidError)
    assert reported[0].context == {"format": "json", "problem": "JSONDecodeError"}


def test_chrome_unreachable_is_reported_before_the_api_stops(page, reported, monkeypatch) -> None:
    from playwright.async_api import Error as PlaywrightError

    monkeypatch.setattr(instagram_api.asyncio, "sleep", AsyncMock())
    failing = AsyncMock(side_effect=PlaywrightError("connect ECONNREFUSED"))
    with patch("instagram_api.async_playwright", return_value=_playwright(failing)):
        with pytest.raises(InstagramChromeUnreachableError):
            with TestClient(instagram_api.app):
                pass
    assert [error.code for error in reported] == ["FINJA-517"]


def test_analytics_is_off_without_the_switch() -> None:
    assert instagram_api.analytics.enabled is False


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8080",
               "ANALYTICS_TOKEN": "ingest-token"}, version="1.2.0")
    assert problem is None and config.project_id == "finja-instagram"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_an_error_inside_reel_stats_points_flare_at_it() -> None:
    sender = _sender()
    try:
        try:
            instagram_api.like_rate(1, None)
        except TypeError as exc:
            raise InstagramDiagnosticsProbeError("probe", probe="like_rate") from exc
    except InstagramDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event is not None and event["error"]["affected_file"] == "reel_stats.py"


def test_a_broken_cookie_file_gets_an_env_fingerprint_so_flare_asks_a_person(tmp_path: Path, monkeypatch) -> None:
    sender = _sender()
    events: list = []
    monkeypatch.setattr(instagram_api.analytics, "record_exception",
                        lambda error: events.append(sender.record_exception(error)))
    broken = tmp_path / "cookies.txt"
    broken.write_text(".instagram.com\tTRUE\t/\tTRUE\tnot-a-number\tsessionid\tx\n", encoding="utf-8")
    assert instagram_api._load_cookies_txt(str(broken)) == []
    assert events and events[0]["error"]["code"] == "FINJA-105"
    assert events[0]["error"]["fingerprint"].startswith("env-config-")
