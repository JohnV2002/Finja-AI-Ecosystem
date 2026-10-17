#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Incident Envelope Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Contract, minimization, and fail-closed privacy tests.

  New in v1.11.0:
    - Pins the redacted Finja-to-Flare incident envelope v1.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

======================================================================
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from core.incident_envelope import IncidentEnvelope, validate_incident_envelope
from core.exceptions import IncidentPrivacyViolationError, InvalidIncidentEnvelopeError


def _envelope(content: str = "x = 1\n") -> dict:
    return {
        "envelope_version": 1,
        "incident_id": "123e4567-e89b-42d3-a456-426614174000",
        "observed_at": "2026-10-17T15:00:00Z",
        "origin": "finja",
        "component": "finja-chat",
        "repository": "finja-neural-network",
        "mode": "standard",
        "error_kind": "SyntaxError",
        "error_code": None,
        "summary": "A submitted module failed Python syntax checking.",
        "frames": [{"path": "demo.py", "line": 1, "symbol": "run"}],
        "files": [{"path": "demo.py", "content": content,
                   "sha256": hashlib.sha256(content.encode()).hexdigest()}],
        "redaction": {"policy": "finja-flare-redaction-v1",
                      "source_minimized": True, "sensitive_values_removed": True},
    }


def test_valid_envelope_has_portable_versioned_json_schema() -> None:
    raw = _envelope()
    envelope = validate_incident_envelope(raw)
    assert envelope.envelope_version == 1
    assert envelope.files[0].path == "demo.py"
    assert raw == _envelope()
    schema = IncidentEnvelope.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "redaction" in schema["required"]
    assert schema["properties"]["envelope_version"]["const"] == 1
    frozen = json.loads((Path(__file__).parent / "contracts" / "incident-envelope-v1.schema.json").read_text(encoding="utf-8"))
    assert frozen == schema


def test_documented_example_validates() -> None:
    document = (Path(__file__).parent / "contracts" / "INCIDENT_ENVELOPE.md").read_text(encoding="utf-8")
    example = json.loads(document.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert validate_incident_envelope(example).incident_id == example["incident_id"]


@pytest.mark.parametrize("change", [
    {"envelope_version": 2},
    {"incident_id": "not-a-uuid"},
    {"observed_at": "2026-10-17T15:00:00+02:00"},
    {"origin": "user"},
    {"mode": "auto-apply"},
    {"raw_logs": "never allowed"},
])
def test_invalid_or_extra_top_level_fields_are_rejected(change: dict) -> None:
    raw = _envelope()
    raw.update(change)
    with pytest.raises(InvalidIncidentEnvelopeError) as caught:
        validate_incident_envelope(raw)
    assert caught.value.code == "FLARE-610"
    assert "never allowed" not in str(caught.value)


@pytest.mark.parametrize("path", ["../private.py", "/" + "home/user/demo.py", "C:" + chr(92) + "Users" + chr(92) + "x" + chr(92) + "demo.py", "private/demo.py", "secrets/token.py"])
def test_file_paths_must_be_relative_source_paths(path: str) -> None:
    raw = _envelope()
    raw["files"][0]["path"] = path
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(raw)


def test_duplicate_paths_and_wrong_source_hash_are_rejected() -> None:
    raw = _envelope()
    raw["files"].append(deepcopy(raw["files"][0]))
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(raw)
    raw["files"][1]["path"] = "DEMO.py"
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(raw)
    raw["files"].pop()
    raw["files"][0]["sha256"] = "0" * 64
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(raw)


def test_source_bundle_is_bounded_by_utf8_bytes() -> None:
    content = "é" * 35_000  # 70,000 bytes despite only 35,000 characters.
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(_envelope(content))


def test_raw_multiline_traceback_does_not_fit_summary() -> None:
    raw = _envelope()
    raw["summary"] = "Runtime error\nTraceback details"
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(raw)


@pytest.mark.parametrize("content", [
    'Authorization: Bearer abcdefghijklmnop\n',
    'password = "definitely-a-secret"\n',
    'callback = "https://alice:password@example.invalid/hook"\n',
    'path = "C:' + chr(92) + 'Users' + chr(92) + 'person' + chr(92) + 'code.py"\n',
    'path = "/srv/finja/private.py"\n',
    'email = "person@example.invalid"\n',
    'url = "https://example.invalid/api?token=abc123"\n',
    '-----BEGIN ' + 'PRIVATE KEY-----\n',
    'data = "\x00hidden"\n',
])
def test_obvious_sensitive_source_is_rejected_without_echo(content: str) -> None:
    raw = _envelope(content)
    with pytest.raises(IncidentPrivacyViolationError) as caught:
        validate_incident_envelope(raw)
    assert caught.value.code == "FLARE-611"
    assert content.strip() not in str(caught.value)


def test_sensitive_summary_is_rejected_despite_redaction_attestation() -> None:
    raw = _envelope()
    raw["summary"] = "Runtime failure at /" + "home/person/private.py"
    with pytest.raises(IncidentPrivacyViolationError):
        validate_incident_envelope(raw)


def test_explicit_redaction_marker_can_replace_a_sensitive_literal() -> None:
    raw = _envelope('password = "<redacted>"\n')
    assert validate_incident_envelope(raw).files[0].content == 'password = "<redacted>"\n'


def test_redaction_attestation_is_required_but_not_trusted_alone() -> None:
    raw = _envelope()
    raw["redaction"]["sensitive_values_removed"] = False
    with pytest.raises(InvalidIncidentEnvelopeError):
        validate_incident_envelope(raw)
