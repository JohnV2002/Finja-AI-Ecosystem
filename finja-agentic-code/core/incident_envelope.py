"""
======================================================================
      Flare (Finja Agentic Code) – Redacted Incident Envelope
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Versioned, minimal Finja-to-Flare incident data contract.

  New in v1.11.0:
    - Validates the redacted incident envelope before job creation.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

======================================================================
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core import privacy_gate
from core.exceptions import IncidentPrivacyViolationError, InvalidIncidentEnvelopeError
from core.repair_scope import path_is_safe

ENVELOPE_VERSION = 1
REDACTION_POLICY = "finja-flare-redaction-v1"
MAX_FILES = 5
MAX_FILE_SOURCE_BYTES = 60_000
MAX_TOTAL_SOURCE_BYTES = 120_000

UUID4_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SYMBOL_RE = r"^[A-Za-z_][A-Za-z0-9_.<>-]{0,119}$"
CODE_RE = r"^[A-Z][A-Z0-9]{1,15}-[0-9]{3,5}$"
SHA256_RE = r"^[0-9a-f]{64}$"
SLUG_RE = r"^[A-Za-z0-9._-]+$"
DENIED_SOURCE_PARTS = frozenset({
    "private", "secrets", "credentials", "userdata", "user_data",
    "logs", "backups", "downloads",
})

# Pattern checks are defense in depth, not proof that arbitrary code contains
# no private data. The sender must still remove sensitive material before
# building an envelope. Never echo matched input back in an error response.
SENSITIVE_PATTERNS = privacy_gate.UNIVERSAL_CREDENTIAL_PATTERNS + (
    # Envelope-only strictness on top of the shared credential shapes. The
    # plain intake path uses a narrower bearer rule so that the words
    # "Bearer authentication" in a comment do not refuse a whole job; an
    # envelope is already redacted by its sender, so here any bearer-looking
    # token is treated as a leak.
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.IGNORECASE),
    re.compile(r"[A-Za-z]:[\\/]|\\\\[A-Za-z0-9._-]+\\|/(?:home|Users|root|mnt|srv|opt|var|etc|app)/[^\s/]+"),
    re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"),
    # Bounded to the real limits of an address (64-character local part). The
    # unbounded form is tried from every character of a long run of word
    # characters and is quadratic; without a leading \b a longer run is still
    # caught through its last 64 characters.
    re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}\b"),
    re.compile(r"\b\d{15,22}\b"),
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
)
REDACTED_LITERAL_RE = re.compile(r"(['\"])(?:<redacted>|REDACTED)\1", re.IGNORECASE)


class StrictEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RedactionAttestation(StrictEnvelopeModel):
    policy: Literal["finja-flare-redaction-v1"]
    source_minimized: Literal[True]
    sensitive_values_removed: Literal[True]


class IncidentFrame(StrictEnvelopeModel):
    path: str = Field(min_length=1, max_length=240)
    line: int = Field(ge=1)
    symbol: str | None = Field(default=None, max_length=120, pattern=SYMBOL_RE)


class IncidentFile(StrictEnvelopeModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=60_000)
    sha256: str = Field(pattern=SHA256_RE)


class IncidentEnvelope(StrictEnvelopeModel):
    envelope_version: Literal[1]
    incident_id: str = Field(pattern=UUID4_RE)
    observed_at: str = Field(min_length=20, max_length=40)
    origin: Literal["finja"]
    component: str = Field(min_length=1, max_length=80, pattern=SLUG_RE)
    repository: str = Field(min_length=1, max_length=80, pattern=SLUG_RE)
    mode: Literal["standard", "hotfix", "manual"]
    error_kind: str = Field(min_length=1, max_length=120, pattern=SYMBOL_RE)
    error_code: str | None = Field(default=None, pattern=CODE_RE)
    summary: str = Field(min_length=1, max_length=500)
    frames: list[IncidentFrame] = Field(default_factory=list, max_length=8)
    files: list[IncidentFile] = Field(min_length=1, max_length=MAX_FILES)
    redaction: RedactionAttestation


def _has_sensitive_data(value: str) -> bool:
    cleaned = REDACTED_LITERAL_RE.sub('""', value)
    return any(ord(char) < 32 and char not in "\n\t" for char in cleaned) \
        or any(pattern.search(cleaned) for pattern in SENSITIVE_PATTERNS)


def _source_path_allowed(path: str) -> bool:
    return path_is_safe(path) and not any(
        part.lower() in DENIED_SOURCE_PARTS for part in path.split("/")
    ) and privacy_gate.path_violation(path) is None


def validate_incident_envelope(raw: object) -> IncidentEnvelope:
    """Fail closed without reflecting the offending incident data to Finja."""
    try:
        envelope = IncidentEnvelope.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise InvalidIncidentEnvelopeError() from exc

    if not UTC_RE.fullmatch(envelope.observed_at):
        raise InvalidIncidentEnvelopeError("Incident timestamp must be UTC RFC3339")
    try:
        datetime.fromisoformat(envelope.observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidIncidentEnvelopeError("Incident timestamp is invalid") from exc

    paths: set[str] = set()
    for frame in envelope.frames:
        if not _source_path_allowed(frame.path):
            raise InvalidIncidentEnvelopeError("Incident frame path must be relative source code")
    if any(char in envelope.summary for char in ("\n", "\r", "\t")):
        raise InvalidIncidentEnvelopeError("Incident summary must be one line")
    if sum(len(item.content.encode("utf-8")) for item in envelope.files) > MAX_TOTAL_SOURCE_BYTES:
        raise InvalidIncidentEnvelopeError("Incident source bundle exceeds its size limit")
    for item in envelope.files:
        folded_path = item.path.casefold()
        if not _source_path_allowed(item.path) or folded_path in paths:
            raise InvalidIncidentEnvelopeError("Incident file paths must be unique relative source paths")
        paths.add(folded_path)
        if len(item.content.encode("utf-8")) > MAX_FILE_SOURCE_BYTES:
            raise InvalidIncidentEnvelopeError("Incident source file exceeds its size limit")
        if hashlib.sha256(item.content.encode("utf-8")).hexdigest() != item.sha256:
            raise InvalidIncidentEnvelopeError("Incident source digest does not match")

    text_fields = [envelope.summary]
    text_fields.extend(item.symbol for item in envelope.frames if item.symbol is not None)
    text_fields.extend(item.content for item in envelope.files)
    if any(_has_sensitive_data(value) for value in text_fields):
        raise IncidentPrivacyViolationError()
    return envelope
