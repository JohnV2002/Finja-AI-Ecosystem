"""
Project: Finja - Twitch Interactivity Suite
Module: finja-omni-test / test_flare_onboarding.py
Author: J. Apps (JohnV2002 / Sodakiller1)
Version: 1.1.0
Description: The probe, structured error reports and the analytics switch of the Omni sandbox
    behave as Flare expects. Lives next to the code (not in tests/) because it needs pytest.
New in v1.1.0: First version.
Copyright (c) 2026 J. Apps. Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import omni_reporting
import probe
import quatsch
import see
from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import OmniDiagnosticsProbeError, OmniModelError, OmniNotConfiguredError, OmniPipelineError

ROOT = Path(omni_reporting.__file__).resolve().parent


@pytest.fixture()
def reported(monkeypatch: pytest.MonkeyPatch) -> list:
    seen: list = []
    monkeypatch.setattr(omni_reporting.analytics, "record_exception", lambda error: seen.append(error))
    monkeypatch.setattr(omni_reporting, "_last_reported", {})
    return seen


def test_probe_reports_the_real_bug_and_exits_1(reported) -> None:
    assert probe.main() == 1
    assert len(reported) == 1 and isinstance(reported[0], OmniDiagnosticsProbeError)
    assert isinstance(reported[0].__cause__, ZeroDivisionError)


def test_loop_errors_are_reported_at_most_once_a_minute(reported) -> None:
    for _ in range(5):
        omni_reporting.report_throttled(OmniPipelineError("ocr", cause=RuntimeError("model busy"), step="ocr"))
    assert len(reported) == 1


def test_foreign_errors_become_model_errors_and_structured_ones_stay() -> None:
    wrapped = omni_reporting.as_app_error(TimeoutError("slow"), "The vision model call failed", backend="local")
    assert isinstance(wrapped, OmniModelError) and isinstance(wrapped.cause, TimeoutError)
    original = OmniNotConfiguredError("not configured")
    assert omni_reporting.as_app_error(original, "ignored") is original


def test_missing_openrouter_key_is_finja_106(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(see, "OPENROUTER_KEY", "")
    with pytest.raises(OmniNotConfiguredError) as caught:
        see.see_openrouter("aGVsbG8=")
    assert caught.value.code == "FINJA-106"
    monkeypatch.setattr(quatsch, "OPENROUTER_KEY", "")
    with pytest.raises(OmniNotConfiguredError):
        quatsch.ask("context", "question")


def test_analytics_is_off_without_the_switch() -> None:
    assert omni_reporting.analytics.enabled is False


def _sender() -> AnalyticsSender:
    config, problem = AnalyticsConfig.from_environment(
        ROOT, {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://192.0.2.10:8081",
               "ANALYTICS_TOKEN": "ingest-token"}, version="1.1.0")
    assert problem is None and config.project_id == "finja-omni-test"
    return AnalyticsSender(config, root=ROOT, transport=MagicMock(return_value=202), sampler=MagicMock())


def test_a_missing_key_gets_an_env_fingerprint_so_flare_asks_a_person(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = _sender()
    monkeypatch.setattr(see, "OPENROUTER_KEY", "")
    try:
        see.see_openrouter("aGVsbG8=")
    except OmniNotConfiguredError as error:
        event = sender.record_exception(error)
    assert event is not None and event["error"]["code"] == "FINJA-106"
    assert event["error"]["fingerprint"].startswith("env-config-")


def test_the_probe_error_points_flare_at_omni_stats() -> None:
    sender = _sender()
    try:
        try:
            probe.average_ocr_confidence([])
        except ZeroDivisionError as exc:
            raise OmniDiagnosticsProbeError("probe", probe="average_ocr_confidence") from exc
    except OmniDiagnosticsProbeError as error:
        event = sender.record_exception(error)
    assert event["error"]["code"] == "FINJA-527" and event["error"]["affected_file"] == "omni_stats.py"
