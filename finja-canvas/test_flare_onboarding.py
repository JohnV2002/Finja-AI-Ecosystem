"""
Project: Finja - Twitch Interactivity Suite
Module: finja-canvas / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.2.0
Description: The canvas server's owner-only probe, the painter's structured failure reports
    and the analytics switch behave as Flare expects. Lives next to the code (not in tests/)
    because it needs pytest, which Flare's unittest sandbox does not have.
New in v1.2.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import server
from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import CanvasDiagnosticsProbeError, CanvasNotConfiguredError, CanvasPainterError

ROOT = Path(server.__file__).resolve().parent
TOKEN = "probe-" + "p" * 16


@pytest.fixture()
def canvas_server(monkeypatch: pytest.MonkeyPatch):
    recorded: list = []
    monkeypatch.setattr(server.analytics, "record_exception", lambda error: recorded.append(error))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.NoCacheHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", recorded
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_probe_is_hidden_without_a_token(canvas_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, recorded = canvas_server
    monkeypatch.delenv("CANVAS_PROBE_TOKEN", raising=False)
    assert _get(f"{base}/diagnostics/probe?token=anything")[0] == 404
    monkeypatch.setenv("CANVAS_PROBE_TOKEN", TOKEN)
    assert _get(f"{base}/diagnostics/probe")[0] == 404
    assert _get(f"{base}/diagnostics/probe?token=wrong")[0] == 404
    assert recorded == []


def test_probe_reports_the_real_bug(canvas_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, recorded = canvas_server
    monkeypatch.setenv("CANVAS_PROBE_TOKEN", TOKEN)
    status, body = _get(f"{base}/diagnostics/probe?token={TOKEN}")
    assert status == 500 and json.loads(body)["error"]["code"] == "FINJA-516"
    assert len(recorded) == 1 and isinstance(recorded[0], CanvasDiagnosticsProbeError)
    assert isinstance(recorded[0].__cause__, ZeroDivisionError)


def test_the_canvas_page_is_still_served(canvas_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _ = canvas_server
    monkeypatch.chdir(ROOT)
    status, body = _get(f"{base}/index.html")
    assert status == 200 and b"<html" in body.lower()


def test_analytics_is_off_without_the_switch() -> None:
    assert server.analytics.enabled is False


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://analytics-collector:8080",
               "ANALYTICS_TOKEN": "ingest-token"}, version="1.2.0")
    assert problem is None and config.project_id == "finja-canvas"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_the_probe_error_points_flare_at_canvas_stats() -> None:
    sender = _sender()
    try:
        try:
            server.average_motif_pixels([])
        except ZeroDivisionError as exc:
            raise CanvasDiagnosticsProbeError("probe", probe="average_motif_pixels") from exc
    except CanvasDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event is not None and event["error"]["code"] == "FINJA-516"
    assert event["error"]["affected_file"] == "canvas_stats.py"


def test_a_painter_failure_keeps_its_cause() -> None:
    sender = _sender()
    try:
        {}["missing"]
    except KeyError as exc:
        event = sender.record_exception(CanvasPainterError("A painting step failed unexpectedly", cause=exc))
    assert event is not None and event["error"]["code"] == "FINJA-515"
    assert event["error"]["affected_file"] == "test_flare_onboarding.py"


def test_a_missing_key_gets_an_env_fingerprint_so_flare_asks_a_person() -> None:
    sender = _sender()
    try:
        raise CanvasNotConfiguredError("Finja Canvas is not configured: OPENROUTER_API_KEY is missing",
                                       setting="OPENROUTER_API_KEY")
    except CanvasNotConfiguredError as error:
        event = sender.record_exception(error)
    assert event is not None and event["error"]["fingerprint"].startswith("env-")


def test_painter_without_a_key_reports_and_exits_1() -> None:
    try:  # the painter imports the SVG renderer, which needs the native Cairo library (in the image)
        import cairosvg  # noqa: F401
        import dotenv  # noqa: F401
        import PIL  # noqa: F401
        import requests  # noqa: F401
    except (ImportError, OSError) as missing:
        pytest.skip(f"painter dependencies are not installed here: {missing}")
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
           "OPENROUTER_API_KEY": "", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, "painter.py"], cwd=ROOT, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 1
    assert "FINJA-104" in result.stderr
