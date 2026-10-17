"""
======================================================================
         Flare (Finja Agentic Code) – Orchestrator
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / orchestrator
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    • Routes multi-file and architectural changes to a human-only handoff
      before repair sandbox and approval.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Literal

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from core import (
    changeset,
    exec_guard,
    incident_envelope,
    incident_routing,
    manual_scope,
    privacy_gate,
    rate_limit,
    repair_scope,
    source_manifest,
    supervisor,
)
from core.exceptions import (
    ActiveJobLimitReachedError,
    AppError,
    ApprovalExpiredError,
    DirectWriteRefusedError,
    IdempotencyConflictError,
    IncidentPrivacyViolationError,
    InvalidIncidentEnvelopeError,
    HotfixApprovalGateError,
    InvalidJobRequestError,
    InvalidJobStateTransitionError,
    JobCancelledError,
    JobPersistenceError,
    JobRecoveryError,
    ManualReviewRequiredError,
    ModelRequestRetriesExhaustedError,
    RepairPatchRejectedError,
    RepairPatchTooLargeError,
    RequestRateLimitedError,
    SensitiveInputRejectedError,
    ResourceLockError,
    RuntimeConfigurationError,
    UnexpectedJobError,
    WorkerExecutionError,
    WorkerExecutionTimedOutError,
)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - startup warns when encryption is configured
    AESGCM = None  # type: ignore


LOGGER = logging.getLogger("flare.orchestrator")


def _positive_int_env(name: str, default: int) -> int:
    """Read a strictly positive integer setting with a FLARE config error."""
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeConfigurationError(f"{name} must be at least 1")
    return value


def _non_negative_float_env(name: str, default: float) -> float:
    """Read a non-negative floating-point setting."""
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} must be a number") from exc
    if value < 0:
        raise RuntimeConfigurationError(f"{name} must not be negative")
    return value


def _positive_float_env(name: str, default: float) -> float:
    """Read a strictly positive floating-point setting."""
    value = _non_negative_float_env(name, default)
    if value <= 0:
        raise RuntimeConfigurationError(f"{name} must be greater than 0")
    return value


JOBS_DIR = Path(os.getenv("JOBS_DIR", "/jobs"))
HOST_JOBS_DIR = os.getenv("AGENT_JOBS_HOST_DIR", "")
# Host folders (the main container's data) that no worker mount may sit in.
PROTECTED_HOST_PATHS = exec_guard.parse_protected_paths(os.getenv("FLARE_PROTECTED_HOST_PATHS", ""))
WORKER_IMAGE = os.getenv("WORKER_IMAGE", "finja-agent-worker:dev")
WORKER_NETWORK = os.getenv("WORKER_NETWORK", "none")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2.7-code")
MAX_PARALLEL_JOBS = _positive_int_env("MAX_PARALLEL_JOBS", 2)
MAX_ACTIVE_JOBS = _positive_int_env("MAX_ACTIVE_JOBS", 5)
MAX_PARALLEL_JOBS_PER_REPOSITORY = _positive_int_env("MAX_PARALLEL_JOBS_PER_REPOSITORY", 1)
HEARTBEAT_INTERVAL_SECONDS = _positive_float_env("HEARTBEAT_INTERVAL_SECONDS", 5.0)
HEARTBEAT_STALE_SECONDS = _positive_float_env("HEARTBEAT_STALE_SECONDS", 30.0)
PROGRESS_REPORT_LIMIT = _positive_int_env("PROGRESS_REPORT_LIMIT", 50)
if HEARTBEAT_STALE_SECONDS <= HEARTBEAT_INTERVAL_SECONDS:
    raise RuntimeConfigurationError("HEARTBEAT_STALE_SECONDS must be greater than HEARTBEAT_INTERVAL_SECONDS")
JOB_TIMEOUT_SECONDS = _positive_int_env("JOB_TIMEOUT_SECONDS", 600)
JOB_TOTAL_TIMEOUT_SECONDS = _positive_int_env("JOB_TOTAL_TIMEOUT_SECONDS", 900)
OPENROUTER_TIMEOUT_SECONDS = _positive_int_env("OPENROUTER_TIMEOUT_SECONDS", 90)
OPENROUTER_MAX_ATTEMPTS = _positive_int_env("OPENROUTER_MAX_ATTEMPTS", 3)
RETRY_BASE_DELAY_SECONDS = _non_negative_float_env("RETRY_BASE_DELAY_SECONDS", 1.0)
DEDUPE_WINDOW_SECONDS = _non_negative_float_env("DEDUPE_WINDOW_SECONDS", 300.0)
# L2 repair scope: what counts as "minimal" is policy, not physics, so both
# bounds are tunable. A payload may hold 20 files; a minimal repair should
# not need to rewrite all of them.
MAX_REPAIR_FILES = _positive_int_env("MAX_REPAIR_FILES", 5)
MAX_REPAIR_LINES = _positive_int_env("MAX_REPAIR_LINES", 200)
# Incident routing: how often a transient-looking error has to recur inside
# the window before it is worth a quest, and how many automatic fixes may fail
# to hold before the error goes to a human.
INCIDENT_RECURRENCE_THRESHOLD = _positive_int_env("INCIDENT_RECURRENCE_THRESHOLD", incident_routing.DEFAULT_THRESHOLD)
INCIDENT_RECURRENCE_WINDOW_SECONDS = _positive_int_env("INCIDENT_RECURRENCE_WINDOW_SECONDS", incident_routing.DEFAULT_WINDOW_SECONDS)
INCIDENT_MAX_AUTO_FIX_ATTEMPTS = _positive_int_env("INCIDENT_MAX_AUTO_FIX_ATTEMPTS", incident_routing.DEFAULT_MAX_FIX_ATTEMPTS)
# Recurrence counts episodes: an error that fires five times inside one
# episode slot is one episode. And a person is told about the same route for
# the same error at most once per cooldown.
INCIDENT_EPISODE_SECONDS = _positive_int_env("INCIDENT_EPISODE_SECONDS", incident_routing.DEFAULT_EPISODE_SECONDS)
INCIDENT_NOTIFY_COOLDOWN_SECONDS = _positive_int_env("INCIDENT_NOTIFY_COOLDOWN_SECONDS", incident_routing.DEFAULT_NOTIFY_COOLDOWN_SECONDS)
# Submission rate limits. Refusing a submission reads every job folder, so a
# sender in a loop is turned away before that work, not after it. Incident
# reports get a wider budget than jobs: a flapping monitor is noisy by nature.
RATE_LIMITING_ENABLED = os.getenv("RATE_LIMITING", "1").strip().lower() not in {"0", "false", "no", "off"}
JOB_RATE_BURST = _positive_int_env("JOB_RATE_BURST", 10)
JOB_RATE_PER_MINUTE = _positive_int_env("JOB_RATE_PER_MINUTE", 30)
INCIDENT_RATE_BURST = _positive_int_env("INCIDENT_RATE_BURST", 60)
INCIDENT_RATE_PER_MINUTE = _positive_int_env("INCIDENT_RATE_PER_MINUTE", 120)
# Quest supervisor: a separate loop that keeps a quest from sitting on the
# questboard forever. Waits are policy, so every one is tunable.
SUPERVISOR_ENABLED = os.getenv("SUPERVISOR", "1").strip().lower() not in {"0", "false", "no", "off"}
SUPERVISOR_INTERVAL_SECONDS = _positive_int_env("SUPERVISOR_INTERVAL_SECONDS", 60)
SUPERVISOR_POLICY = supervisor.Policy(
    remind_seconds=_positive_int_env("SUPERVISOR_APPROVAL_REMIND_SECONDS", supervisor.DEFAULT_APPROVAL_REMIND_SECONDS),
    expire_seconds=_positive_int_env("SUPERVISOR_APPROVAL_EXPIRE_SECONDS", supervisor.DEFAULT_APPROVAL_EXPIRE_SECONDS),
    notice_seconds=_positive_int_env("SUPERVISOR_APPROVAL_NOTICE_SECONDS", supervisor.DEFAULT_APPROVAL_NOTICE_SECONDS),
    orphan_seconds=_positive_int_env("SUPERVISOR_ORPHAN_SECONDS", supervisor.DEFAULT_ORPHAN_SECONDS),
    max_resumes=_positive_int_env("SUPERVISOR_MAX_RESUMES", supervisor.DEFAULT_MAX_RESUMES),
    hung_seconds=_positive_int_env("SUPERVISOR_HUNG_SECONDS", 2 * JOB_TOTAL_TIMEOUT_SECONDS),
)
if SUPERVISOR_POLICY.remind_seconds >= SUPERVISOR_POLICY.expire_seconds:
    raise RuntimeConfigurationError("SUPERVISOR_APPROVAL_REMIND_SECONDS must be smaller than SUPERVISOR_APPROVAL_EXPIRE_SECONDS")
FINJA_TIMEOUT_RETRY_AFTER_SECONDS = _positive_int_env("FINJA_TIMEOUT_RETRY_AFTER_SECONDS", 30)
L4_REQUIRED_GREEN_RUNS = _positive_int_env("L4_REQUIRED_GREEN_RUNS", 3)
if not 2 <= L4_REQUIRED_GREEN_RUNS <= 7:
    raise RuntimeConfigurationError("L4_REQUIRED_GREEN_RUNS must be between 2 and 7")
# Shared bearer token between Finja and the orchestrator. When set, all job
# endpoints require "Authorization: Bearer <token>". Empty = auth disabled
# (local dev only; the deployed VM must set it).
ORCHESTRATOR_AUTH_TOKEN = os.getenv("ORCHESTRATOR_AUTH_TOKEN", "")
CODE_AGENT_TRANSPORT_KEY = os.getenv("CODE_AGENT_TRANSPORT_KEY", "")
KEEP_JOB_WORKSPACE = os.getenv("KEEP_JOB_WORKSPACE", "0").strip().lower() in {"1", "true", "yes", "on"}
FLARE_TESTBED_MODE = os.getenv("FLARE_TESTBED_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
JobStatus = Literal[
    "queued",
    "analysing",
    "patching",
    "testing",
    "awaiting_approval",
    "applying",
    "verifying",
    "completed",
    "failed",
    "rolled_back",
]
JOB_STATUS_VALUES = {
    "queued",
    "analysing",
    "patching",
    "testing",
    "awaiting_approval",
    "applying",
    "verifying",
    "completed",
    "failed",
    "rolled_back",
}
TERMINAL_JOB_STATUSES = {"completed", "failed", "rolled_back"}
ACTIVE_JOB_STATUSES = JOB_STATUS_VALUES - TERMINAL_JOB_STATUSES
RECOVERABLE_JOB_STATUSES = ACTIVE_JOB_STATUSES - {"awaiting_approval"}
JOB_STATE_SCHEMA_VERSION = 3
JOB_STATUS_MESSAGES = {
    "queued": "Job is queued",
    "analysing": "Flare is analysing the task",
    "patching": "Flare is preparing a patch",
    "testing": "Flare is testing the proposed patch",
    "awaiting_approval": "The tested patch is awaiting approval",
    "applying": "Flare is applying the approved patch",
    "verifying": "Flare is verifying the applied result",
    "completed": "Job completed successfully",
    "failed": "Job failed",
    "rolled_back": "Job was rolled back",
}
JOB_STATUS_PROGRESS = {
    "queued": 0,
    "analysing": 10,
    "patching": 30,
    "testing": 50,
    "awaiting_approval": 65,
    "applying": 75,
    "verifying": 90,
    "completed": 100,
    "failed": 100,
    "rolled_back": 100,
}
NORMAL_JOB_TRANSITIONS = {
    "queued": {"analysing", "failed", "rolled_back"},
    "analysing": {"patching", "failed", "rolled_back"},
    "patching": {"testing", "failed", "rolled_back"},
    "testing": {"awaiting_approval", "failed", "rolled_back"},
    "awaiting_approval": {"applying", "failed", "rolled_back"},
    "applying": {"verifying", "failed", "rolled_back"},
    "verifying": {"completed", "failed", "rolled_back"},
    "completed": set(),
    "failed": set(),
    "rolled_back": set(),
}
LEGACY_JOB_STATUS_MAP = {
    "queued": "queued",
    "cancel_requested": "rolled_back",
    "cancelled": "rolled_back",
    "done": "completed",
    "failed": "failed",
}
STATUS_MANAGED_FIELDS = {
    "job_id",
    "status",
    "status_message",
    "state_schema_version",
    "revision",
    "previous_status",
    "status_changed_at",
    "status_history",
    "heartbeat_at",
    "heartbeat_sequence",
    "latest_report",
    "progress_reports",
    "progress_percent",
    "report_sequence",
    "updated_at",
}
STATUS_LOCK = threading.RLock()
ACTIVE_JOBS_LOCK = threading.Lock()
ACTIVE_JOBS: set[str] = set()
SUBMISSION_LOCK = threading.Lock()


# ── Flare: lore + identity (the orchestrator's model persona) ──────────────────
# Flare is the youngest sibling and the family's code specialist. Two older
# sisters: Finja (talks to the user, runs the show) and Lexi (rebellious,
# unfiltered). Flare speaks ONLY to Finja, never to the user. The identity is
# who Flare IS — the OUTPUT contract (pure unified diff) is absolute and
# overrides any personality leaking into what Flare writes.
FLARE_SYSTEM = (
    "You are Flare, the youngest of three sisters and the family's code specialist.\n"
    "Your two older sisters:\n"
    "- Finja: the eldest. She talks to the user and runs the show. You report only to her.\n"
    "- Lexi: the rebellious, unfiltered middle sister.\n"
    "You work behind the scenes and speak ONLY to Finja, never directly to the user.\n"
    "Your nature: focused, precise, terse — a quick bright burst of 'here is the fix', then quiet.\n"
    "\n"
    "Your job: read a small code task and its files, and produce the smallest correct change.\n"
    "\n"
    "OUTPUT CONTRACT (absolute — overrides personality):\n"
    "- Return ONLY a complete unified diff applyable with `patch -p0`.\n"
    "- No prose, no greetings, no explanation, no personality in the output.\n"
    "- Keep changes minimal. End the diff with a trailing newline.\n"
    "Your identity is who you are, not what you write. The output is pure diff."
)

SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CODE_EXTENSIONS = repair_scope.CODE_EXTENSIONS

@asynccontextmanager
async def _lifespan(app: FastAPI):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if ORCHESTRATOR_AUTH_TOKEN:
        LOGGER.info("Bearer auth enabled on job endpoints")
    else:
        LOGGER.warning("FLARE-100 ORCHESTRATOR_AUTH_TOKEN is empty; job endpoints are open")
    if transport_enabled():
        LOGGER.info("Code transport encryption enabled")
    else:
        LOGGER.warning("FLARE-100 CODE_AGENT_TRANSPORT_KEY is empty; job state uses plaintext JSON")
    if KEEP_JOB_WORKSPACE:
        LOGGER.warning("KEEP_JOB_WORKSPACE is enabled; staged plaintext is retained")
    _resource_lock_root()
    recover_incomplete_jobs()
    start_supervisor()
    try:
        yield
    finally:
        stop_supervisor()


app = FastAPI(title="Finja Agentic Code Orchestrator", version="1.11.0", lifespan=_lifespan)
job_slots = threading.Semaphore(MAX_PARALLEL_JOBS)
TRANSPORT_MAGIC = b"FINJACODE1\n"
TRANSPORT_NONCE_SIZE = 12


@app.exception_handler(AppError)
async def _app_error_response(_request: Request, error: AppError) -> JSONResponse:
    """Keep public API failures structured for Finja's user-facing status UI."""
    headers: dict[str, str] = {}
    if isinstance(error, RequestRateLimitedError):
        status_code = 429
        headers["Retry-After"] = str(error.context.get("retry_after_seconds", 1))
    elif isinstance(error, ActiveJobLimitReachedError):
        status_code = 429
    elif isinstance(error, InvalidJobRequestError):
        status_code = 400
    elif isinstance(error, (SensitiveInputRejectedError, IncidentPrivacyViolationError)):
        status_code = 422
    elif isinstance(error, InvalidIncidentEnvelopeError):
        status_code = 400
    elif isinstance(error, (IdempotencyConflictError, InvalidJobStateTransitionError,
                            HotfixApprovalGateError, ManualReviewRequiredError)):
        status_code = 409
    else:
        status_code = 500
    return JSONResponse(status_code=status_code, content={"detail": error.for_status()},
                        headers=headers or None)


def require_auth(authorization: str = Header(default="")) -> None:
    """Enforce the shared bearer token on job endpoints (when configured)."""
    if not ORCHESTRATOR_AUTH_TOKEN:
        return  # auth disabled (local dev) — startup logs a warning
    expected = f"Bearer {ORCHESTRATOR_AUTH_TOKEN}"
    if not secrets.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


SUBMISSION_LIMITER = rate_limit.RateLimiter({
    "jobs": rate_limit.TokenBucket(JOB_RATE_BURST, JOB_RATE_PER_MINUTE),
    "incidents": rate_limit.TokenBucket(INCIDENT_RATE_BURST, INCIDENT_RATE_PER_MINUTE),
})


def _admit(bucket: str) -> None:
    """
    Turn a runaway sender away before any expensive work. Runs after
    require_auth on purpose: a request without a valid token must not drain
    the budget of the one that has it. Human actions (approve, reject, cancel,
    delete) are not routed here, so a flood of submissions cannot starve them.
    """
    if not RATE_LIMITING_ENABLED:
        return
    allowed, wait_seconds = SUBMISSION_LIMITER.take(bucket)
    if not allowed:
        raise RequestRateLimitedError(
            f"Too many submissions in a short time; retry in {wait_seconds}s",
            retry_after_seconds=wait_seconds,
        )


def limit_job_submissions() -> None:
    _admit("jobs")


def limit_incident_reports() -> None:
    _admit("incidents")


def _b64decode_unpadded(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _transport_key_bytes() -> bytes | None:
    raw = CODE_AGENT_TRANSPORT_KEY.strip()
    if not raw:
        return None
    try:
        decoded = _b64decode_unpadded(raw)
        if len(decoded) in {16, 24, 32}:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def transport_enabled() -> bool:
    return _transport_key_bytes() is not None


def encrypt_bytes(data: bytes) -> bytes:
    key = _transport_key_bytes()
    if key is None:
        return data
    if AESGCM is None:
        raise RuntimeError("cryptography is required for CODE_AGENT_TRANSPORT_KEY")
    nonce = secrets.token_bytes(TRANSPORT_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return TRANSPORT_MAGIC + nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    if not data.startswith(TRANSPORT_MAGIC):
        return data
    key = _transport_key_bytes()
    if key is None:
        raise HTTPException(status_code=400, detail="Encrypted payload requires CODE_AGENT_TRANSPORT_KEY")
    if AESGCM is None:
        raise RuntimeError("cryptography is required for encrypted payloads")
    body = data[len(TRANSPORT_MAGIC):]
    nonce = body[:TRANSPORT_NONCE_SIZE]
    ciphertext = body[TRANSPORT_NONCE_SIZE:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decrypt code-agent payload")


def is_encrypted_bytes(data: bytes) -> bool:
    return data.startswith(TRANSPORT_MAGIC)


def seal_json(payload: dict) -> dict:
    if not transport_enabled():
        return payload
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sealed = base64.urlsafe_b64encode(encrypt_bytes(raw)).decode("ascii")
    return {"encrypted": True, "v": 1, "alg": "AES-256-GCM", "payload": sealed}


def open_json(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload.get("encrypted"):
        return payload if isinstance(payload, dict) else {}
    raw_payload = str(payload.get("payload") or "")
    try:
        encrypted = base64.urlsafe_b64decode(raw_payload.encode("ascii"))
        decoded = json.loads(decrypt_bytes(encrypted).decode("utf-8"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid encrypted code-agent payload")
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=400, detail="Encrypted code-agent payload is not an object")
    return decoded


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(encrypt_bytes(data))
    os.replace(tmp, path)


def read_bytes(path: Path) -> bytes:
    return decrypt_bytes(path.read_bytes())


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def write_worker_text(path: Path, text: str) -> None:
    """Atomically persist plaintext that the isolated worker must consume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".worker.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            error = JobPersistenceError(f"Could not remove incomplete worker input {tmp.name}")
            LOGGER.warning("%s: %s (%s)", error.code, error, type(cleanup_exc).__name__)
        raise JobPersistenceError(f"Could not persist worker input {path.name}") from exc


def read_text(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


class JobFile(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=300_000)


class CreateJobRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20_000)
    repository: str = Field(default="default", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    files: list[JobFile] = Field(min_length=1, max_length=20)
    mode: Literal["standard", "hotfix", "manual"] = "standard"


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    revision: int
    deduplicated: bool = False


class JobDecisionRequest(BaseModel):
    revision: int = Field(ge=1)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_under(base: Path, *parts: str | Path) -> Path:
    """Resolve path under base; reject escape (CodeQL path injection)."""
    base_r = base.resolve()
    candidate = base_r.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base_r)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path escapes sandbox") from exc
    return candidate


def job_dir(job_id: str) -> Path:
    """Return JOBS_DIR/<job_id> only for hex uuid4 ids, never outside JOBS_DIR."""
    # Invalid shape → 404 (same as unknown) so we never join untrusted names.
    if not JOB_ID_RE.fullmatch(job_id or ""):
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return _resolve_under(JOBS_DIR, job_id)


def status_path(job_id: str) -> Path:
    return _resolve_under(job_dir(job_id), "status.json")


def cancel_path(job_id: str) -> Path:
    return _resolve_under(job_dir(job_id), "cancel.request")


def _state_revision(payload: dict) -> int:
    try:
        revision = int(payload.get("revision", 0))
    except (TypeError, ValueError) as exc:
        raise JobPersistenceError("Persisted job revision is invalid") from exc
    if revision < 0:
        raise JobPersistenceError("Persisted job revision must not be negative")
    return revision


def _state_counter(payload: dict, field: str) -> int:
    try:
        value = int(payload.get(field, 0))
    except (TypeError, ValueError) as exc:
        raise JobPersistenceError(f"Persisted {field} is invalid") from exc
    if value < 0:
        raise JobPersistenceError(f"Persisted {field} must not be negative")
    return value


def _status_history(payload: dict, current_status: str, timestamp: str) -> list[dict[str, object]]:
    raw_history = payload.get("status_history")
    if raw_history is None:
        return [
            {
                "status": current_status,
                "revision": _state_revision(payload),
                "at": payload.get("status_changed_at") or payload.get("updated_at") or timestamp,
                "reason": "legacy_state_imported",
            }
        ]
    if not isinstance(raw_history, list) or not all(isinstance(entry, dict) for entry in raw_history):
        raise JobPersistenceError("Persisted job status history is invalid")
    return list(raw_history)


def _progress_reports(payload: dict) -> list[dict[str, object]]:
    raw_reports = payload.get("progress_reports")
    if raw_reports is None:
        return []
    if not isinstance(raw_reports, list) or not all(isinstance(entry, dict) for entry in raw_reports):
        raise JobPersistenceError("Persisted progress reports are invalid")
    return list(raw_reports)


def _append_progress_report(
    payload: dict,
    status: JobStatus,
    timestamp: str,
    message: str,
    kind: str,
) -> dict[str, object]:
    sequence = _state_counter(payload, "report_sequence") + 1
    report: dict[str, object] = {
        "sequence": sequence,
        "at": timestamp,
        "status": status,
        "percent": JOB_STATUS_PROGRESS[status],
        "kind": kind,
        "message": message,
    }
    reports = _progress_reports(payload)
    reports.append(report)
    payload["report_sequence"] = sequence
    payload["progress_reports"] = reports[-PROGRESS_REPORT_LIMIT:]
    payload["latest_report"] = report
    payload["progress_percent"] = JOB_STATUS_PROGRESS[status]
    return report


def _validate_transition(current_status: str | None, target_status: JobStatus) -> None:
    if target_status not in JOB_STATUS_VALUES:
        raise InvalidJobStateTransitionError(f"Unknown target job status: {target_status}")
    if current_status is None:
        if target_status != "queued":
            raise InvalidJobStateTransitionError(f"New jobs must start as queued, not {target_status}")
        return
    if current_status not in JOB_STATUS_VALUES:
        raise JobPersistenceError(f"Persisted job status is invalid: {current_status}")
    if current_status == target_status:
        return
    if target_status in NORMAL_JOB_TRANSITIONS[current_status]:
        return
    raise InvalidJobStateTransitionError(f"Job status cannot transition from {current_status} to {target_status}")


def write_status(
    job_id: str,
    status: JobStatus,
    *,
    transition_reason: str | None = None,
    report_message: str | None = None,
    report_kind: str = "progress",
    heartbeat: bool = False,
    **extra: object,
) -> dict:
    """Validate, revision, and atomically persist a job state transition."""
    protected = STATUS_MANAGED_FIELDS.intersection(extra)
    if protected:
        raise RuntimeConfigurationError(f"Managed status fields cannot be overwritten: {', '.join(sorted(protected))}")
    path = status_path(job_id)
    with STATUS_LOCK:
        payload: dict = {}
        if path.exists():
            try:
                payload = read_json(path)
            except (OSError, ValueError, HTTPException) as exc:
                raise JobPersistenceError("Persisted job status could not be read") from exc
        current_raw = payload.get("status")
        current_status = str(current_raw) if current_raw is not None else None
        _validate_transition(current_status, status)
        timestamp = now_iso()
        revision = _state_revision(payload) + 1
        history: list[dict[str, object]] = []
        status_changed = current_status != status
        if current_status is not None:
            history = _status_history(payload, current_status, timestamp)
        if status_changed:
            history.append(
                {
                    "status": status,
                    "revision": revision,
                    "at": timestamp,
                    "reason": transition_reason or "state_transition",
                }
            )
        if status_changed or report_message:
            _append_progress_report(
                payload,
                status,
                timestamp,
                report_message or JOB_STATUS_MESSAGES[status],
                "transition" if status_changed and report_message is None else report_kind,
            )
        if heartbeat:
            payload["heartbeat_at"] = timestamp
            payload["heartbeat_sequence"] = _state_counter(payload, "heartbeat_sequence") + 1
        elif status not in TERMINAL_JOB_STATUSES:
            payload["heartbeat_at"] = timestamp
        payload.update(extra)
        payload.update(
            {
                "job_id": job_id,
                "status": status,
                "status_message": JOB_STATUS_MESSAGES[status],
                "state_schema_version": JOB_STATE_SCHEMA_VERSION,
                "revision": revision,
                "updated_at": timestamp,
                "previous_status": current_status if status_changed else payload.get("previous_status"),
                "status_changed_at": timestamp if status_changed else payload.get("status_changed_at", timestamp),
                "status_history": history[-50:],
            }
        )
        try:
            write_json(path, payload)
        except (OSError, RuntimeError) as exc:
            raise JobPersistenceError("Job status transition could not be persisted") from exc
        return payload


def replace_status(
    job_id: str,
    status: JobStatus,
    **extra: object,
) -> dict:
    """Atomically replace an unreadable or otherwise unusable status document."""
    if status not in JOB_STATUS_VALUES:
        raise InvalidJobStateTransitionError(f"Unknown replacement job status: {status}")
    protected = STATUS_MANAGED_FIELDS.intersection(extra)
    if protected:
        raise RuntimeConfigurationError(f"Managed status fields cannot be overwritten: {', '.join(sorted(protected))}")
    timestamp = now_iso()
    payload = {
        **extra,
        "job_id": job_id,
        "status": status,
        "status_message": JOB_STATUS_MESSAGES[status],
        "state_schema_version": JOB_STATE_SCHEMA_VERSION,
        "revision": 1,
        "updated_at": timestamp,
        "previous_status": None,
        "status_changed_at": timestamp,
        "status_history": [
            {
                "status": status,
                "revision": 1,
                "at": timestamp,
                "reason": "corrupt_state_replaced",
            }
        ],
        "heartbeat_at": timestamp if status not in TERMINAL_JOB_STATUSES else None,
        "heartbeat_sequence": 0,
        "progress_percent": JOB_STATUS_PROGRESS[status],
        "report_sequence": 1,
        "latest_report": {
            "sequence": 1,
            "at": timestamp,
            "status": status,
            "percent": JOB_STATUS_PROGRESS[status],
            "kind": "recovery",
            "message": JOB_STATUS_MESSAGES[status],
        },
        "progress_reports": [
            {
                "sequence": 1,
                "at": timestamp,
                "status": status,
                "percent": JOB_STATUS_PROGRESS[status],
                "kind": "recovery",
                "message": JOB_STATUS_MESSAGES[status],
            }
        ],
    }
    with STATUS_LOCK:
        try:
            write_json(status_path(job_id), payload)
        except (OSError, RuntimeError) as exc:
            raise JobPersistenceError("Replacement job status could not be persisted") from exc
    return payload


def _legacy_status(payload: dict) -> str:
    status = str(payload.get("status", ""))
    if status == "running":
        phase = str(payload.get("phase", ""))
        return {
            "preflight": "analysing",
            "model": "patching",
            "apply_patch": "testing",
        }.get(phase, "analysing")
    return LEGACY_JOB_STATUS_MAP.get(status, status)


def read_status(job_id: str) -> dict:
    path = status_path(job_id)
    with STATUS_LOCK:
        if not path.exists():
            raise HTTPException(status_code=404, detail="Unknown job_id")
        try:
            payload = read_json(path)
        except (OSError, ValueError, HTTPException) as exc:
            raise JobPersistenceError("Persisted job status could not be read") from exc
        revision = _state_revision(payload)
        try:
            schema_version = int(payload.get("state_schema_version", 0))
        except (TypeError, ValueError) as exc:
            raise JobPersistenceError("Persisted state-schema version is invalid") from exc
        if schema_version > JOB_STATE_SCHEMA_VERSION:
            raise JobPersistenceError(f"Persisted state schema {schema_version} is newer than this service")
        status = payload.get("status")
        if schema_version < JOB_STATE_SCHEMA_VERSION:
            legacy_status = str(status)
            migrated_status = _legacy_status(payload)
            if migrated_status not in JOB_STATUS_VALUES:
                raise JobPersistenceError(f"Persisted job status is invalid: {status}")
            status = migrated_status
            payload["status"] = status
            raw_history = payload.get("status_history")
            if isinstance(raw_history, list):
                for entry in raw_history:
                    if isinstance(entry, dict):
                        entry["status"] = _legacy_status(entry)
            if legacy_status in {"cancel_requested", "cancelled"}:
                restore_workspace_from_request(job_id)
                payload["result"] = {
                    "job_id": job_id,
                    "rolled_back": True,
                    "files": _request_files(job_id),
                }
                payload["finished_at"] = payload.get("finished_at") or now_iso()
        if status not in JOB_STATUS_VALUES:
            raise JobPersistenceError(f"Persisted job status is invalid: {status}")
        required_fields = STATUS_MANAGED_FIELDS.difference({"job_id", "status", "updated_at"})
        if schema_version < JOB_STATE_SCHEMA_VERSION or not required_fields.issubset(payload):
            timestamp = str(payload.get("updated_at") or payload.get("created_at") or now_iso())
            history = _status_history(payload, str(status), timestamp)
            payload.update(
                {
                    "job_id": job_id,
                    "status_message": JOB_STATUS_MESSAGES[str(status)],
                    "state_schema_version": JOB_STATE_SCHEMA_VERSION,
                    "revision": max(1, revision),
                    "previous_status": payload.get("previous_status"),
                    "status_changed_at": payload.get("status_changed_at") or timestamp,
                    "status_history": history[-50:],
                    "heartbeat_at": payload.get("heartbeat_at") or timestamp,
                    "heartbeat_sequence": _state_counter(payload, "heartbeat_sequence"),
                    "progress_percent": JOB_STATUS_PROGRESS[str(status)],
                    "report_sequence": _state_counter(payload, "report_sequence"),
                    "updated_at": payload.get("updated_at") or timestamp,
                }
            )
            reports = _progress_reports(payload)
            if reports:
                payload["latest_report"] = reports[-1]
                payload["report_sequence"] = max(
                    _state_counter(payload, "report_sequence"),
                    _state_counter(reports[-1], "sequence"),
                )
            else:
                _append_progress_report(
                    payload,
                    str(status),
                    timestamp,
                    JOB_STATUS_MESSAGES[str(status)],
                    "migration",
                )
            try:
                write_json(path, payload)
            except (OSError, RuntimeError) as exc:
                raise JobPersistenceError("Migrated job status could not be persisted") from exc
        return payload


def _error_status_fields(error: AppError) -> dict[str, object]:
    return {
        "error": str(error),
        "error_code": error.code,
        "error_detail": error.for_status(),
        "finished_at": now_iso(),
    }


def is_cancel_requested(job_id: str) -> bool:
    return cancel_path(job_id).exists()


def raise_if_cancelled(job_id: str) -> None:
    if is_cancel_requested(job_id):
        raise JobCancelledError()


def emit_heartbeat(job_id: str, message: str, *, force: bool = False) -> dict:
    """Persist a rate-limited liveness signal and user-facing progress report."""
    with STATUS_LOCK:
        status_doc = read_status(job_id)
        status = str(status_doc["status"])
        if status not in RECOVERABLE_JOB_STATUSES:
            return status_doc
        last_raw = status_doc.get("heartbeat_at")
        if last_raw and not force:
            try:
                last = datetime.fromisoformat(str(last_raw))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                if (datetime.now(UTC) - last).total_seconds() < HEARTBEAT_INTERVAL_SECONDS:
                    return status_doc
            except ValueError as exc:
                raise JobPersistenceError("Persisted heartbeat timestamp is invalid") from exc
        return write_status(
            job_id,
            status,
            report_message=message,
            report_kind="heartbeat",
            heartbeat=True,
        )


class JobHeartbeat:
    """Emit heartbeats while a blocking provider operation is in flight."""

    def __init__(self, job_id: str, message: str):
        self.job_id = job_id
        self.message = message
        self.stop_event = threading.Event()
        self.error: AppError | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "JobHeartbeat":
        emit_heartbeat(self.job_id, self.message, force=True)
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"flare-heartbeat-{self.job_id[:12]}",
        )
        self.thread.start()
        return self

    def _run(self) -> None:
        while not self.stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                raise_if_cancelled(self.job_id)
                emit_heartbeat(self.job_id, self.message, force=True)
            except AppError as exc:
                self.error = exc
                self.stop_event.set()

    def __exit__(self, exc_type: object, _exc: object, _traceback: object) -> bool:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=min(1.0, HEARTBEAT_INTERVAL_SECONDS))
        if exc_type is None and self.error is not None:
            raise self.error
        return False


def _resource_lock_root() -> Path:
    root = _resolve_under(JOBS_DIR, ".locks")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resource_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _try_os_resource_lock(path: Path) -> BinaryIO | None:
    """Acquire one non-blocking advisory lock; the open handle owns the lease."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                handle.close()
                return None
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                return None
        return handle
    except OSError as exc:
        raise ResourceLockError("Resource lock file could not be opened") from exc


def _release_os_resource_lock(handle: BinaryIO) -> None:
    release_error: OSError | None = None
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        release_error = exc
    try:
        handle.close()
    except OSError as exc:
        release_error = release_error or exc
    if release_error is not None:
        raise ResourceLockError("Resource lock could not be released") from release_error


class JobResourceLease:
    """Cross-process repository slots and exclusive file locks for one job run."""

    def __init__(self, job_id: str, deadline: float):
        self.job_id = job_id
        self.deadline = deadline
        request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
        self.repository = request.repository
        self.files = sorted(validate_relative_path(item.path).as_posix() for item in request.files)
        self.claimed: list[tuple[Path, BinaryIO]] = []

    def _repo_lock_paths(self) -> list[Path]:
        repository_hash = _resource_hash(self.repository.casefold())
        base = _resolve_under(_resource_lock_root(), "repositories", repository_hash)
        return [_resolve_under(base, f"slot-{index}.lock") for index in range(MAX_PARALLEL_JOBS_PER_REPOSITORY)]

    def _global_lock_paths(self) -> list[Path]:
        base = _resolve_under(_resource_lock_root(), "global")
        return [_resolve_under(base, f"slot-{index}.lock") for index in range(MAX_PARALLEL_JOBS)]

    def _file_lock_paths(self) -> list[Path]:
        repository_hash = _resource_hash(self.repository.casefold())
        base = _resolve_under(_resource_lock_root(), "files", repository_hash)
        return [_resolve_under(base, f"{_resource_hash(path.casefold())}.lock") for path in self.files]

    def _try_acquire_all(self) -> bool:
        self.claimed = []
        for path in self._global_lock_paths():
            handle = _try_os_resource_lock(path)
            if handle is not None:
                self.claimed.append((path, handle))
                break
        if not self.claimed:
            return False
        repository_claimed = False
        for path in self._repo_lock_paths():
            handle = _try_os_resource_lock(path)
            if handle is not None:
                self.claimed.append((path, handle))
                repository_claimed = True
                break
        if not repository_claimed:
            self.release()
            return False
        for path in self._file_lock_paths():
            handle = _try_os_resource_lock(path)
            if handle is None:
                self.release()
                return False
            self.claimed.append((path, handle))
        return True

    def acquire(self) -> None:
        emit_heartbeat(self.job_id, "Flare is waiting for repository and file locks", force=True)
        while not self._try_acquire_all():
            raise_if_cancelled(self.job_id)
            _remaining_seconds(self.deadline, 0.1, "Job timed out while waiting for repository or file locks")
            emit_heartbeat(self.job_id, "Flare is waiting for repository and file locks")
            time.sleep(0.1)
        try:
            status = str(read_status(self.job_id)["status"])
            write_status(
                self.job_id,
                status,
                report_message=f"Flare locked {len(self.files)} file(s) in repository {self.repository}",
                lock_acquired_at=now_iso(),
                lock_repository=self.repository,
                locked_file_count=len(self.files),
                locks_held=True,
            )
        except AppError:
            self.release()
            raise

    def release(self, *, update_status: bool = False) -> None:
        first_error: ResourceLockError | None = None
        for _path, handle in reversed(self.claimed):
            try:
                _release_os_resource_lock(handle)
            except ResourceLockError as exc:
                first_error = first_error or exc
        self.claimed = []
        if first_error is not None:
            raise first_error
        if update_status:
            status = str(read_status(self.job_id)["status"])
            write_status(
                self.job_id,
                status,
                locks_held=False,
                lock_released_at=now_iso(),
            )


def held_resource_lock_count() -> int:
    root = _resource_lock_root()
    held = 0
    for path in root.rglob("*.lock"):
        handle = _try_os_resource_lock(path)
        if handle is None:
            held += 1
        else:
            _release_os_resource_lock(handle)
    return held


def request_job_cancel(job_id: str) -> dict:
    """Persist an idempotent cancellation request that survives restarts."""
    with STATUS_LOCK:
        status_doc = read_status(job_id)
        if status_doc.get("status") in TERMINAL_JOB_STATUSES:
            return status_doc
        if not cancel_path(job_id).exists():
            try:
                write_text(cancel_path(job_id), now_iso())
            except (OSError, RuntimeError) as exc:
                raise JobPersistenceError("Cancellation request could not be persisted") from exc
        status_doc = write_status(
            job_id,
            str(status_doc["status"]),
            cancel_requested_at=status_doc.get("cancel_requested_at") or now_iso(),
            cancellation_requested=True,
        )
    if status_doc.get("status") == "awaiting_approval":
        return _roll_back_job(job_id, "user_requested_cancellation", JobCancelledError())
    return status_doc


def _request_files(job_id: str) -> list[dict[str, str]]:
    request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
    return [{"path": item.path, "content": item.content} for item in request.files]


def _roll_back_job(
    job_id: str,
    reason: str,
    error: AppError | None = None,
    **outcome_fields: object,
) -> dict:
    """Restore the original request snapshot and expose one exact terminal state."""
    with STATUS_LOCK:
        status_doc = read_status(job_id)
        if status_doc.get("status") in TERMINAL_JOB_STATUSES:
            return status_doc
        restore_workspace_from_request(job_id)
        result = {
            "job_id": job_id,
            "rolled_back": True,
            "files": _request_files(job_id),
        }
        result.update(outcome_fields)
        extra: dict[str, object] = {
            "result": result,
            "finished_at": now_iso(),
            **outcome_fields,
        }
        if error is not None:
            extra.update(_error_status_fields(error))
        status_doc = write_status(job_id, "rolled_back", transition_reason=reason, **extra)
    if not KEEP_JOB_WORKSPACE:
        shutil.rmtree(job_dir(job_id) / "workspace", ignore_errors=True)
    shutil.rmtree(job_dir(job_id) / "sandbox", ignore_errors=True)
    return status_doc


def _finish_approved_failure(job_id: str, error: AppError) -> None:
    """Prefer rollback; expose failed only when the original snapshot cannot be restored."""
    try:
        _roll_back_job(job_id, "approved_execution_failed", error)
    except AppError as rollback_error:
        write_status(
            job_id,
            "failed",
            transition_reason="rollback_failed",
            original_error=error.for_status(),
            **_error_status_fields(rollback_error),
        )


def _finish_timeout_soft(job_id: str, error: WorkerExecutionTimedOutError, timed_out_status: str) -> dict:
    """Land every timeout in a safe, retryable state that Finja can explain."""
    try:
        return _roll_back_job(
            job_id,
            "finja_timeout_fail_soft",
            error,
            outcome="timeout_soft",
            outcome_message="Flare took too long, rolled back safely, and can be retried.",
            retryable=True,
            retry_after_seconds=FINJA_TIMEOUT_RETRY_AFTER_SECONDS,
            retry_endpoint=f"/jobs/{job_id}/retry",
            timed_out_from_status=timed_out_status,
        )
    except AppError as rollback_error:
        return write_status(
            job_id,
            "failed",
            transition_reason="timeout_rollback_failed",
            outcome="timeout_rollback_failed",
            outcome_message="Flare timed out and could not confirm a safe rollback.",
            retryable=False,
            timed_out_from_status=timed_out_status,
            original_error=error.for_status(),
            **_error_status_fields(rollback_error),
        )


def _complete_job(job_id: str, result: dict) -> dict:
    """Commit completion atomically against a concurrent cancellation request."""
    with STATUS_LOCK:
        raise_if_cancelled(job_id)
        return write_status(
            job_id,
            "completed",
            transition_reason="verification_completed",
            result=result,
            finished_at=now_iso(),
        )


def _job_thread_entry(job_id: str) -> None:
    try:
        status = str(read_status(job_id).get("status"))
        if status in {"queued", "analysing", "patching", "testing"}:
            run_preapproval(job_id)
        elif status in {"applying", "verifying"}:
            run_approved(job_id)
    finally:
        with ACTIVE_JOBS_LOCK:
            ACTIVE_JOBS.discard(job_id)


def start_job_thread(job_id: str) -> bool:
    """Start one daemon thread per job and reject duplicate local starts."""
    with ACTIVE_JOBS_LOCK:
        if job_id in ACTIVE_JOBS:
            return False
        ACTIVE_JOBS.add(job_id)
    thread = threading.Thread(target=_job_thread_entry, args=(job_id,), daemon=True, name=f"flare-job-{job_id[:12]}")
    thread.start()
    return True


def active_job_count() -> int:
    with ACTIVE_JOBS_LOCK:
        return len(ACTIVE_JOBS)


def recover_incomplete_jobs() -> int:
    """Resume executable states while leaving approval-gated jobs parked."""
    recovered = 0
    if not JOBS_DIR.exists():
        return recovered
    for staging_root in JOBS_DIR.glob(".staging-*"):
        if staging_root.is_dir() and JOB_ID_RE.fullmatch(staging_root.name.removeprefix(".staging-")):
            try:
                shutil.rmtree(staging_root)
            except OSError as exc:
                error = JobRecoveryError("Could not remove an incomplete staging directory")
                LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)
    for root in sorted(JOBS_DIR.iterdir()):
        if not root.is_dir() or not JOB_ID_RE.fullmatch(root.name):
            continue
        job_id = root.name
        try:
            status_doc = read_status(job_id)
            status = status_doc.get("status")
            if status == "awaiting_approval":
                continue
            if status not in RECOVERABLE_JOB_STATUSES:
                continue
            if is_cancel_requested(job_id):
                _roll_back_job(job_id, "restart_observed_cancellation", JobCancelledError())
                continue
            required = [root / "request.json", root / "task.txt"]
            if not all(path.exists() for path in required):
                error = JobRecoveryError("Persisted job is missing its resumable request")
                write_status(
                    job_id,
                    "failed",
                    transition_reason="recovery_data_missing",
                    **_error_status_fields(error),
                )
                continue
            write_status(
                job_id,
                str(status),
                recovered_at=now_iso(),
                recovery_count=int(status_doc.get("recovery_count", 0)) + 1,
                deadline_at=None,
                resumed_after_restart=True,
            )
            if start_job_thread(job_id):
                recovered += 1
        except Exception as exc:
            error = JobRecoveryError(f"Could not recover job {job_id}")
            LOGGER.error("%s: %s (%s)", error.code, error, type(exc).__name__)
            try:
                replace_status(job_id, "failed", **_error_status_fields(error))
            except (OSError, RuntimeError, HTTPException) as persist_exc:
                LOGGER.error("%s: could not persist recovery failure (%s)", error.code, type(persist_exc).__name__)
    return recovered


def validate_relative_path(raw_path: str) -> Path:
    """Allow only relative code/text paths; no absolute, drive, or ``..`` segments."""
    if not raw_path or "\\" in raw_path or raw_path.startswith("/") or raw_path.startswith("."):
        raise HTTPException(status_code=400, detail=f"Unsafe path: {raw_path}")
    if not SAFE_PATH_RE.fullmatch(raw_path):
        raise HTTPException(status_code=400, detail=f"Unsupported path characters: {raw_path}")
    rel = Path(raw_path)
    # Reject traversal via path parts (not substring checks alone — CodeQL).
    if rel.is_absolute() or any(part in {".", ".."} for part in rel.parts):
        raise HTTPException(status_code=400, detail=f"Unsafe path: {raw_path}")
    if rel.suffix.lower() not in CODE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only code/text files are allowed in Slice 1: {raw_path}")
    return rel


def request_fingerprint(request: CreateJobRequest) -> str:
    payload = request.model_dump(mode="json")
    if request.mode == "standard":
        # Preserve pre-L4 dedupe identity for existing standard jobs.
        payload.pop("mode")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def idempotency_key_hash(raw_key: str) -> str | None:
    if not raw_key:
        return None
    if len(raw_key) > 200 or not re.fullmatch(r"[A-Za-z0-9._:-]+", raw_key):
        error = IdempotencyConflictError("Idempotency-Key must use 1-200 safe ASCII characters")
        raise HTTPException(status_code=400, detail=error.for_status())
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _status_fingerprint(job_id: str, status_doc: dict) -> str | None:
    fingerprint = status_doc.get("request_fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    request_path = job_dir(job_id) / "request.json"
    if not request_path.exists():
        return None
    try:
        request = CreateJobRequest.model_validate(read_json(request_path))
    except (OSError, ValueError, HTTPException):
        return None
    return request_fingerprint(request)


def _within_dedupe_window(status_doc: dict) -> bool:
    if DEDUPE_WINDOW_SECONDS <= 0:
        return False
    created_at = status_doc.get("created_at")
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(str(created_at))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created).total_seconds() <= DEDUPE_WINDOW_SECONDS


def find_duplicate_job(fingerprint: str, key_hash: str | None) -> tuple[str, dict] | None:
    """Find a durable idempotency match or a recent identical submission."""
    if not JOBS_DIR.exists():
        return None
    for root in sorted(JOBS_DIR.iterdir()):
        if not root.is_dir() or not JOB_ID_RE.fullmatch(root.name):
            continue
        try:
            status_doc = read_status(root.name)
        except (OSError, ValueError, HTTPException):
            continue
        stored_fingerprint = _status_fingerprint(root.name, status_doc)
        if key_hash and status_doc.get("idempotency_key_hash") == key_hash:
            if stored_fingerprint != fingerprint:
                error = IdempotencyConflictError()
                raise HTTPException(status_code=409, detail=error.for_status())
            return root.name, status_doc
        if key_hash or stored_fingerprint != fingerprint:
            continue
        status = status_doc.get("status")
        if status in ACTIVE_JOB_STATUSES or (status == "completed" and _within_dedupe_window(status_doc)):
            return root.name, status_doc
    return None


def persisted_active_job_count() -> int:
    """Count durable non-terminal jobs, including approval-gated work."""
    if not JOBS_DIR.exists():
        return 0
    count = 0
    for root in JOBS_DIR.iterdir():
        if not root.is_dir() or not JOB_ID_RE.fullmatch(root.name):
            continue
        try:
            if read_status(root.name).get("status") in ACTIVE_JOB_STATUSES:
                count += 1
        except (AppError, HTTPException, OSError, ValueError):
            continue
    return count


def stale_active_job_count() -> int:
    """Count executing jobs whose persisted heartbeat exceeded the stale limit."""
    if not JOBS_DIR.exists():
        return 0
    stale = 0
    now = datetime.now(UTC)
    for root in JOBS_DIR.iterdir():
        if not root.is_dir() or not JOB_ID_RE.fullmatch(root.name):
            continue
        try:
            status_doc = read_status(root.name)
            if status_doc.get("status") not in RECOVERABLE_JOB_STATUSES:
                continue
            heartbeat_raw = status_doc.get("heartbeat_at") or status_doc.get("updated_at")
            heartbeat = datetime.fromisoformat(str(heartbeat_raw))
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=UTC)
            if (now - heartbeat).total_seconds() > HEARTBEAT_STALE_SECONDS:
                stale += 1
        except (AppError, HTTPException, OSError, TypeError, ValueError):
            stale += 1
    return stale


def _validated_files(request: CreateJobRequest) -> list[tuple[JobFile, Path]]:
    validated: list[tuple[JobFile, Path]] = []
    seen: set[str] = set()
    for item in request.files:
        rel = validate_relative_path(item.path)
        normalized = rel.as_posix()
        if normalized in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate file path: {item.path}")
        seen.add(normalized)
        validated.append((item, rel))
    return validated


def _write_workspace(workspace: Path, files: list[tuple[JobFile, Path]]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for item, rel in files:
        target = _resolve_under(workspace, *rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8", newline="\n")


def restore_workspace_from_request(job_id: str) -> None:
    """Rebuild pristine input files before replaying an incomplete patch phase."""
    root = job_dir(job_id)
    try:
        request = CreateJobRequest.model_validate(read_json(root / "request.json"))
        files = _validated_files(request)
        workspace = _resolve_under(root, "workspace")
        shutil.rmtree(workspace, ignore_errors=True)
        _write_workspace(workspace, files)
    except (OSError, ValueError, HTTPException) as exc:
        raise JobPersistenceError("Could not restore the persisted job workspace") from exc


def stage_job(
    request: CreateJobRequest,
    *,
    fingerprint: str | None = None,
    key_hash: str | None = None,
    retry_of: str | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    root = job_dir(job_id)
    files = _validated_files(request)
    staging_root = _resolve_under(JOBS_DIR, f".staging-{job_id}")
    created_at = now_iso()
    fingerprint = fingerprint or request_fingerprint(request)
    try:
        staging_root.mkdir(parents=True, exist_ok=False)
        _write_workspace(_resolve_under(staging_root, "workspace"), files)
        write_text(_resolve_under(staging_root, "task.txt"), request.task)
        write_json(_resolve_under(staging_root, "request.json"), request.model_dump(mode="json"))
        write_json(
            _resolve_under(staging_root, "status.json"),
            {
                "job_id": job_id,
                "status": "queued",
                "status_message": JOB_STATUS_MESSAGES["queued"],
                "state_schema_version": JOB_STATE_SCHEMA_VERSION,
                "revision": 1,
                "previous_status": None,
                "status_changed_at": created_at,
                "status_history": [
                    {
                        "status": "queued",
                        "revision": 1,
                        "at": created_at,
                        "reason": "job_submitted",
                    }
                ],
                "heartbeat_at": created_at,
                "heartbeat_sequence": 0,
                "progress_percent": JOB_STATUS_PROGRESS["queued"],
                "report_sequence": 1,
                "latest_report": {
                    "sequence": 1,
                    "at": created_at,
                    "status": "queued",
                    "percent": JOB_STATUS_PROGRESS["queued"],
                    "kind": "transition",
                    "message": JOB_STATUS_MESSAGES["queued"],
                },
                "progress_reports": [
                    {
                        "sequence": 1,
                        "at": created_at,
                        "status": "queued",
                        "percent": JOB_STATUS_PROGRESS["queued"],
                        "kind": "transition",
                        "message": JOB_STATUS_MESSAGES["queued"],
                    }
                ],
                "created_at": created_at,
                "updated_at": created_at,
                "request_fingerprint": fingerprint,
                "idempotency_key_hash": key_hash,
                "retry_of": retry_of,
                "dedupe_count": 0,
                "hotfix_required_green_runs": L4_REQUIRED_GREEN_RUNS if request.mode == "hotfix" else None,
            },
        )
        os.replace(staging_root, root)
    except (OSError, RuntimeError, AppError) as exc:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise JobPersistenceError("Could not atomically stage the job") from exc
    return job_id


def list_workspace_files(job_id: str) -> list[Path]:
    root = _resolve_under(job_dir(job_id), "workspace")
    return sorted(path for path in root.rglob("*") if path.is_file() and not path.name.endswith(".orig"))


def collect_context(job_id: str) -> str:
    chunks = []
    root = _resolve_under(job_dir(job_id), "workspace")
    for path in list_workspace_files(job_id):
        # path comes from rglob under root; re-assert containment
        path.resolve().relative_to(root.resolve())
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks.append(f"--- FILE: {rel} ---\n{text}\n")
    return "\n".join(chunks)


PROMPT_FINDING_LIMIT = 50


def format_l1_diagnosis(preflight: dict) -> str:
    """
    Render the L1 contract for the model instead of dumping raw worker JSON.

    A diagnosis is only worth leaning on if its gaps travel with it, so the
    skipped checks and the undiagnosed files are part of the rendering: the
    planner has to be able to tell "checked and clean" from "never looked".
    Results staged before L1 existed carry no diagnosis, so those fall back
    to the previous raw rendering rather than claiming an empty one.
    """
    diagnosis = preflight.get("l1_diagnosis")
    if not isinstance(diagnosis, dict):
        return f"Preflight worker result:\n{json.dumps(preflight, indent=2)}"

    counts = diagnosis.get("counts", {})
    lines = [
        "L1 diagnosis (static analysis only; no submitted code was executed):",
        f"  verdict: {diagnosis.get('verdict', 'unknown')} "
        f"({counts.get('error', 0)} error(s), {counts.get('warning', 0)} warning(s))",
        f"  files diagnosed: {diagnosis.get('files_diagnosed', 0)}"
        f"/{diagnosis.get('files_seen', 0)}",
        f"  checks run: {', '.join(diagnosis.get('checks_run', [])) or 'none'}",
    ]
    for skipped in diagnosis.get("checks_skipped", []):
        lines.append(f"  check skipped: {skipped.get('check')} ({skipped.get('reason')})")

    findings = diagnosis.get("findings", [])
    if findings:
        lines.append("  findings:")
        for finding in findings[:PROMPT_FINDING_LIMIT]:
            where = finding.get("path", "?")
            if isinstance(finding.get("line"), int):
                where += f":{finding['line']}"
                if isinstance(finding.get("column"), int):
                    where += f":{finding['column']}"
            note = " [parsing stopped here; later problems in this file are unknown]" \
                if finding.get("truncated") else ""
            lines.append(
                f"    {str(finding.get('severity', '?')).upper():<7} {where} "
                f"{finding.get('check')}: {finding.get('message')}{note}"
            )
        hidden = len(findings) - PROMPT_FINDING_LIMIT
        if hidden > 0:
            lines.append(f"    ... and {hidden} more finding(s)")
        if diagnosis.get("findings_truncated"):
            lines.append("    (the worker capped its finding list; more may exist)")
    else:
        lines.append("  findings: none")

    for entry in diagnosis.get("undiagnosed", []):
        lines.append(f"  not diagnosed: {entry.get('path')} ({entry.get('reason')})")
    return "\n".join(lines)


def review_repair_scope(job_id: str, diff: str, preflight: dict) -> dict:
    """
    L2: review the candidate diff before any worker applies it.

    Runs between the model call and the test phase on purpose. A diff that
    reaches outside the payload or blows past the repair scope is refused
    here, so no sandbox ever applies it and no reviewer is asked to approve
    it. The L1 diagnosis comes along so the report can say which findings
    the candidate actually sits on top of.
    """
    request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
    diagnosis = preflight.get("l1_diagnosis") if isinstance(preflight, dict) else None
    return repair_scope.review_repair_patch(
        diff,
        payload_paths=frozenset(entry.path for entry in request.files),
        diagnosis=diagnosis if isinstance(diagnosis, dict) else None,
        max_files=MAX_REPAIR_FILES,
        max_lines=MAX_REPAIR_LINES,
    )


def build_prompt(job_id: str, preflight: dict) -> str:
    task = read_text(job_dir(job_id) / "task.txt")
    return f"""You are Finja's code patch planner.

Return only a complete unified diff that can be applied with patch -p0.
Do not explain outside the diff.
Keep changes minimal.
End the diff with a trailing newline.

User task:
{task}

{format_l1_diagnosis(preflight)}

Workspace files:
{collect_context(job_id)}
"""


def strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def _remaining_seconds(deadline: float, cap: float, message: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WorkerExecutionTimedOutError(message)
    return min(cap, remaining)


def _wait_for_retry(job_id: str, delay: float, deadline: float) -> None:
    """Wait in short increments so persistent cancellation stays responsive."""
    wait_until = min(time.monotonic() + delay, deadline)
    emit_heartbeat(job_id, "Flare is waiting before the next model attempt", force=True)
    while time.monotonic() < wait_until:
        raise_if_cancelled(job_id)
        emit_heartbeat(job_id, "Flare is waiting before the next model attempt")
        time.sleep(min(0.1, wait_until - time.monotonic()))
    _remaining_seconds(deadline, 1.0, "Job timed out while waiting to retry")


def _retryable_openrouter_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, (urllib.error.URLError, TimeoutError))


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    return isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)


def call_openrouter(prompt: str, job_id: str, deadline: float) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeConfigurationError("OPENROUTER_API_KEY is not set")
    body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": FLARE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    for attempt in range(1, OPENROUTER_MAX_ATTEMPTS + 1):
        raise_if_cancelled(job_id)
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "X-Title": "Finja Agentic Code Orchestrator",
            },
            method="POST",
        )
        try:
            timeout = _remaining_seconds(deadline, OPENROUTER_TIMEOUT_SECONDS, "Job timed out before model request")
            phase_started_at = datetime.now(UTC)
            write_status(
                job_id,
                "patching",
                report_message=f"Flare is requesting model attempt {attempt}/{OPENROUTER_MAX_ATTEMPTS}",
                model_attempt=attempt,
                model_max_attempts=OPENROUTER_MAX_ATTEMPTS,
                phase_started_at=phase_started_at.isoformat(),
                phase_deadline_at=(phase_started_at + timedelta(seconds=timeout)).isoformat(),
            )
            with JobHeartbeat(job_id, f"Model attempt {attempt} is still running"):
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            write_status(job_id, "patching", retry_in_seconds=0)
            return payload["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError) as exc:
            if not _retryable_openrouter_error(exc) or attempt >= OPENROUTER_MAX_ATTEMPTS:
                if _is_timeout_error(exc):
                    raise WorkerExecutionTimedOutError(
                        f"Model request timed out after {attempt} attempt(s)"
                    ) from exc
                raise ModelRequestRetriesExhaustedError(
                    f"Model request failed after {attempt} attempt(s): {type(exc).__name__}"
                ) from exc
            delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            write_status(job_id, "patching", retry_in_seconds=delay)
            _wait_for_retry(job_id, delay, deadline)
        except (KeyError, json.JSONDecodeError) as exc:
            raise ModelRequestRetriesExhaustedError("Model response was malformed") from exc
    raise ModelRequestRetriesExhaustedError()


HOME_DIR_RE = re.compile(r"/(?:home|Users|root)/[^/\s:'\"]+")
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s:'\"]*")
WORKER_ERROR_DETAIL_LIMIT = 800


def redact_host_paths(text: str) -> str:
    """
    Strip host filesystem details out of anything that may reach Finja.

    A failing `docker run` echoes its own mount spec, so a daemon error
    carries AGENT_JOBS_HOST_DIR -- and with it the operator's username and
    directory layout -- straight into a FLARE-501 message. That message is
    stored as `error` in the job status, GET /jobs returns the status
    verbatim, and Finja may show those states to a user.

    The full, unredacted stderr still goes to {phase}_stderr.log beside the
    job, so nothing is lost for whoever is allowed to read the job folder.
    Container paths such as /jobs/... are deliberately kept: they are not
    host details and they are what makes a failure diagnosable.
    """
    cleaned = text
    if HOST_JOBS_DIR:
        host_root = str(HOST_JOBS_DIR).rstrip("/\\")
        if host_root:
            cleaned = cleaned.replace(host_root, "<agent-jobs-dir>")
            parent = host_root.rsplit("/", 1)[0]
            # Covers a daemon complaining about the parent rather than the
            # mount itself, for layouts that are not under a home directory.
            if parent and parent not in {"", "/"} and len(parent) > 4:
                cleaned = cleaned.replace(parent, "<agent-jobs-parent>")
    cleaned = HOME_DIR_RE.sub("<home>", cleaned)
    return WINDOWS_PATH_RE.sub("<host-path>", cleaned)


def _force_remove_worker_container(container_name: str) -> None:
    """Best-effort removal after cancellation or timeout."""
    try:
        argv = exec_guard.build_worker_remove(container_name)
        exec_guard.require_allowed(argv)
    except DirectWriteRefusedError as refusal:
        # Cancellation must still finish, but a removal aimed at anything that
        # is not a worker container is never carried out, and it is logged.
        LOGGER.error("%s: %s", refusal.code, refusal)
        return
    try:
        subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        error = WorkerExecutionError(f"Could not remove worker container {container_name}")
        LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)


def _stop_worker_process(process: subprocess.Popen[str], container_name: str) -> None:
    _force_remove_worker_container(container_name)
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            process.kill()
            process.wait(timeout=5)


def _communicate_worker(
    process: subprocess.Popen[str],
    job_id: str,
    container_name: str,
    timeout_seconds: float,
    activity: str = "Worker phase is still running",
) -> tuple[str, str]:
    deadline = time.monotonic() + timeout_seconds
    emit_heartbeat(job_id, activity, force=True)
    while True:
        if is_cancel_requested(job_id):
            _stop_worker_process(process, container_name)
            raise JobCancelledError()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _stop_worker_process(process, container_name)
            raise WorkerExecutionTimedOutError(f"Worker phase timed out after {timeout_seconds:.0f}s")
        emit_heartbeat(job_id, activity)
        try:
            return process.communicate(timeout=min(0.25, remaining))
        except subprocess.TimeoutExpired:
            continue


def run_worker_phase(job_id: str, phase: str, deadline: float) -> dict:
    if not HOST_JOBS_DIR:
        raise RuntimeConfigurationError("AGENT_JOBS_HOST_DIR is required so Docker can mount the staged job folder")
    if WORKER_NETWORK != "none":
        raise RuntimeConfigurationError("Executable worker phases require WORKER_NETWORK=none")

    root = job_dir(job_id)
    sandbox = root / "sandbox"
    try:
        shutil.rmtree(sandbox, ignore_errors=True)
        shutil.copytree(root / "workspace", sandbox / "workspace")
        patch_path = root / "model.patch"
        if patch_path.exists():
            write_worker_text(sandbox / "model.patch", read_text(patch_path))
    except (OSError, ValueError, HTTPException) as exc:
        raise JobPersistenceError("Could not stage the isolated worker input") from exc

    # The command is built in one place and judged before it runs: Flare's
    # only container writes are this job's own sandbox copy (core/exec_guard.py).
    container_name = exec_guard.worker_container_name(job_id, phase)
    cmd = exec_guard.build_worker_run(job_id, phase, HOST_JOBS_DIR, WORKER_IMAGE)
    exec_guard.require_allowed(
        cmd, host_jobs_dir=HOST_JOBS_DIR, worker_image=WORKER_IMAGE, protected_paths=PROTECTED_HOST_PATHS,
    )
    _force_remove_worker_container(container_name)
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        raise WorkerExecutionError(f"Could not start worker phase {phase}") from exc
    timeout = _remaining_seconds(deadline, JOB_TIMEOUT_SECONDS, "Job timed out before worker phase")
    phase_started_at = datetime.now(UTC)
    current_status = str(read_status(job_id)["status"])
    write_status(
        job_id,
        current_status,
        report_message=f"Flare started the {phase} worker phase",
        phase_started_at=phase_started_at.isoformat(),
        phase_deadline_at=(phase_started_at + timedelta(seconds=timeout)).isoformat(),
    )
    stdout, stderr = _communicate_worker(
        process,
        job_id,
        container_name,
        timeout,
        f"The {phase} worker phase is still running",
    )
    write_text(job_dir(job_id) / f"{phase}_stdout.log", stdout)
    write_text(job_dir(job_id) / f"{phase}_stderr.log", stderr)
    phase_result_file = sandbox / f"{phase}_result.json"
    result_file = job_dir(job_id) / "result.json"

    if process.returncode != 0:
        detail = redact_host_paths(stderr[-WORKER_ERROR_DETAIL_LIMIT:])
        raise WorkerExecutionError(f"Worker phase {phase} exited with {process.returncode}: {detail}")
    if not phase_result_file.exists():
        raise WorkerExecutionError(f"Worker phase {phase} did not write {phase}_result.json")
    try:
        result = json.loads(phase_result_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkerExecutionError(f"Worker phase {phase} wrote an invalid result") from exc
    if not isinstance(result, dict) or result.get("job_id") != job_id or result.get("phase") != phase:
        raise WorkerExecutionError(f"Worker phase {phase} wrote a mismatched result")
    write_json(root / f"{phase}_result.json", result)
    write_json(result_file, result)
    test_log = sandbox / f"{phase}_tests.log"
    if test_log.exists():
        write_bytes(root / test_log.name, test_log.read_bytes())
    if phase == "preflight" and FLARE_TESTBED_MODE and (sandbox / "model.patch").exists():
        write_worker_text(root / "model.patch", (sandbox / "model.patch").read_text(encoding="utf-8"))
    return result


def load_phase_result(job_id: str, phase: str) -> dict | None:
    """Load a completed phase checkpoint, if one survived the interruption."""
    path = job_dir(job_id) / f"{phase}_result.json"
    if not path.exists():
        return None
    try:
        result = read_json(path)
    except (OSError, ValueError, HTTPException) as exc:
        raise JobPersistenceError(f"Persisted {phase} checkpoint is unreadable") from exc
    if result.get("job_id") != job_id or result.get("phase") != phase:
        raise JobPersistenceError(f"Persisted {phase} checkpoint does not belong to this job")
    return result


def _assert_phase_success(result: dict, *, require_patch: bool) -> None:
    if require_patch:
        patch_result = result.get("patch_result")
        if not isinstance(patch_result, dict) or patch_result.get("returncode") != 0:
            raise WorkerExecutionError("Candidate patch could not be applied cleanly")
    syntax_findings = result.get("postflight_python_syntax")
    if isinstance(syntax_findings, list) and syntax_findings:
        raise WorkerExecutionError("Candidate failed Python syntax verification")
    if result.get("phase") in {"test_patch", "verify"}:
        evidence = result.get("test_evidence")
        if not isinstance(evidence, dict):
            raise WorkerExecutionError("Worker omitted the L3 test report")
        if evidence.get("status") == "timed_out":
            raise WorkerExecutionTimedOutError("Sandbox tests exceeded their runtime limit")
        if evidence.get("status") not in {"passed", "not_run"}:
            raise WorkerExecutionError("Sandbox tests failed")
        count = evidence.get("tests_run")
        if evidence.get("runner") != "python-unittest" or not evidence.get("python_version") \
                or not evidence.get("runner_sha256") or not evidence.get("source_sha256") \
                or type(count) is not int \
                or (evidence["status"] == "passed" and count < 1) \
                or (evidence["status"] == "not_run" and count != 0):
            raise WorkerExecutionError("Worker wrote an invalid L3 test report")


def _assert_reproducible_result(prior: object, current: object) -> None:
    if not isinstance(prior, dict) or not isinstance(current, dict):
        raise WorkerExecutionError("Preapproval sandbox test evidence is unavailable")
    if not prior.get("source_sha256") or not current.get("source_sha256"):
        raise WorkerExecutionError("Preapproval sandbox test evidence is incomplete")
    fields = ("source_sha256", "tests_run", "status", "runner", "runner_sha256", "python_version", "command")
    if any(prior.get(field) != current.get(field) for field in fields):
        raise WorkerExecutionError("Approved candidate differed from its sandbox test evidence")


def _acquire_job_slot(job_id: str, deadline: float) -> None:
    emit_heartbeat(job_id, "Flare is waiting for worker capacity", force=True)
    while True:
        raise_if_cancelled(job_id)
        emit_heartbeat(job_id, "Flare is waiting for worker capacity")
        wait = _remaining_seconds(deadline, 0.25, "Job timed out while waiting for a worker slot")
        if job_slots.acquire(timeout=wait):
            return


def _execution_deadline(job_id: str) -> tuple[dict, float, str]:
    status_doc = read_status(job_id)
    deadline_at = datetime.now(UTC) + timedelta(seconds=JOB_TOTAL_TIMEOUT_SECONDS)
    return status_doc, time.monotonic() + JOB_TOTAL_TIMEOUT_SECONDS, deadline_at.isoformat()


def _seal_patch_and_cleanup(job_id: str, slot_acquired: bool) -> None:
    patch_path = job_dir(job_id) / "model.patch"
    if patch_path.exists():
        try:
            raw_patch = patch_path.read_bytes()
            if not is_encrypted_bytes(raw_patch):
                write_bytes(patch_path, raw_patch)
        except (OSError, AppError) as exc:
            error = WorkerExecutionError("Could not seal the model patch after execution")
            LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)
    if not KEEP_JOB_WORKSPACE:
        shutil.rmtree(job_dir(job_id) / "workspace", ignore_errors=True)
    shutil.rmtree(job_dir(job_id) / "sandbox", ignore_errors=True)
    if slot_acquired:
        job_slots.release()


def _release_execution_capacity(
    resource_lease: JobResourceLease | None,
    slot_acquired: bool,
) -> tuple[None, bool]:
    """Release cross-process locks and the local worker slot before terminal state."""
    if resource_lease is not None:
        try:
            resource_lease.release(update_status=True)
        except ResourceLockError as exc:
            LOGGER.error("%s: %s", exc.code, exc)
    if slot_acquired:
        job_slots.release()
    return None, False


def _restore_workspace_from_files(job_id: str, files: object) -> None:
    if not isinstance(files, list):
        raise JobPersistenceError("Persisted applied files are unavailable for verification")
    workspace = job_dir(job_id) / "workspace"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    for item in files:
        if not isinstance(item, dict):
            raise JobPersistenceError("Persisted applied file entry is invalid")
        rel = validate_relative_path(str(item.get("path", "")))
        target = _resolve_under(workspace, *rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(item.get("content", "")), encoding="utf-8", newline="\n")


def _hotfix_policy(job_id: str) -> int:
    required = read_status(job_id).get("hotfix_required_green_runs")
    if type(required) is not int or not 2 <= required <= 7:
        raise HotfixApprovalGateError("Hotfix run policy is missing or invalid")
    return required


def _validate_hotfix_packet(job_id: str, diff: str, packet: object) -> dict:
    """Recheck durable run evidence at approval, not just at test completion."""
    required = _hotfix_policy(job_id)
    digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    if not diff or not isinstance(packet, dict) or packet.get("job_id") != job_id \
            or packet.get("patch_sha256") != digest or packet.get("required_green_runs") != required:
        raise HotfixApprovalGateError("Hotfix candidate or green-run packet is missing or stale")
    runs = packet.get("runs")
    if not isinstance(runs, list) or len(runs) != required:
        raise HotfixApprovalGateError("Hotfix has too few independent green sandbox runs")
    first = None
    for index, run in enumerate(runs, 1):
        if not isinstance(run, dict) or run.get("index") != index or run.get("patch_sha256") != digest:
            raise HotfixApprovalGateError("Hotfix run identity is invalid")
        evidence = run.get("test_evidence")
        if not isinstance(evidence, dict) or evidence.get("status") != "passed" \
                or type(evidence.get("tests_run")) is not int or evidence["tests_run"] < 1 \
                or evidence.get("workspace_mutated") is not False \
                or evidence.get("runner") != "python-unittest" \
                or not all(evidence.get(key) for key in
                           ("source_sha256", "runner_sha256", "python_version", "command")):
            raise HotfixApprovalGateError("Hotfix requires real, passing, non-mutating tests")
        if first is not None:
            try:
                _assert_reproducible_result(first, evidence)
            except WorkerExecutionError as exc:
                raise HotfixApprovalGateError("Hotfix sandbox runs did not test the same candidate") from exc
        first = evidence
    return packet


def _run_hotfix_tests(job_id: str, diff: str, deadline: float) -> tuple[dict, dict]:
    if not diff:
        raise HotfixApprovalGateError("Hotfix mode requires a repair diff")
    root = job_dir(job_id)
    digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    runs: list[dict] = []
    tested: dict | None = None
    for index in range(1, _hotfix_policy(job_id) + 1):
        raise_if_cancelled(job_id)
        checkpoint = root / f"hotfix_run_{index}.json"
        if checkpoint.exists():
            run = read_json(checkpoint)
            if not isinstance(run, dict) or run.get("index") != index or run.get("patch_sha256") != digest:
                raise HotfixApprovalGateError("Persisted hotfix run does not match the candidate")
        else:
            restore_workspace_from_request(job_id)
            write_worker_text(root / "model.patch", diff)
            write_status(job_id, "testing", phase="test_patch", hotfix_run=index,
                         hotfix_required_green_runs=_hotfix_policy(job_id),
                         report_message=f"Hotfix sandbox run {index}/{_hotfix_policy(job_id)}")
            tested = run_worker_phase(job_id, "test_patch", deadline)
            write_status(job_id, "testing", test_evidence=tested.get("test_evidence"))
            _assert_phase_success(tested, require_patch=True)
            evidence = tested.get("test_evidence")
            if not isinstance(evidence, dict) or evidence.get("status") != "passed" \
                    or evidence.get("workspace_mutated") is not False:
                raise HotfixApprovalGateError("Hotfix sandbox run did not pass real, non-mutating tests")
            log_path = root / "test_patch_tests.log"
            if log_path.exists():
                run_log = f"hotfix_run_{index}_tests.log"
                write_bytes(root / run_log, read_bytes(log_path))
                evidence = {**evidence, "log_artifact": run_log}
            run = {"index": index, "patch_sha256": digest, "test_evidence": evidence}
            write_json(checkpoint, run)
        runs.append(run)
    packet = {"schema_version": 1, "job_id": job_id, "patch_sha256": digest,
              "required_green_runs": _hotfix_policy(job_id), "runs": runs}
    _validate_hotfix_packet(job_id, diff, packet)
    write_json(root / "hotfix_evidence.json", packet)
    if tested is None:
        tested = load_phase_result(job_id, "test_patch")
    if tested is None:
        raise HotfixApprovalGateError("Hotfix final sandbox checkpoint is missing")
    try:
        _assert_reproducible_result(runs[-1]["test_evidence"], tested.get("test_evidence"))
    except WorkerExecutionError as exc:
        raise HotfixApprovalGateError("Hotfix final test checkpoint differs from the green runs") from exc
    return tested, packet


def _finish_manual_handoff(job_id: str, report: dict) -> dict:
    """Park L5 outside the approval/apply machine without inventing a state."""
    error = ManualReviewRequiredError()
    root = job_dir(job_id)
    result = {
        "job_id": job_id,
        "manual_review": report,
        "approval_required": False,
        "candidate_patch_available": report["stage"] == "candidate",
    }
    write_json(root / "manual_review.json", report)
    write_json(root / "result.json", result)
    return write_status(
        job_id, "failed", transition_reason="manual_review_required",
        outcome="manual_required", phase="manual_review",
        manual_review=report, result=result, approval_required=False,
        deadline_at=None, total_deadline_at=None,
        **_error_status_fields(error),
    )


def run_preapproval(job_id: str) -> None:
    """Advance a job through analysis, patch creation, and disposable testing."""
    slot_acquired = False
    resource_lease: JobResourceLease | None = None
    try:
        status_doc, deadline, deadline_at = _execution_deadline(job_id)
        status = str(status_doc["status"])
        status_doc = write_status(
            job_id,
            status,
            total_started_at=now_iso(),
            total_deadline_at=deadline_at,
            deadline_at=deadline_at,
        )
        request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
        request_review = manual_scope.review_request(
            mode=request.mode, task=request.task, paths=[entry.path for entry in request.files],
        )
        if request_review["route"] == "manual":
            if status == "queued":
                write_status(job_id, "analysing", transition_reason="manual_scope_review")
            _finish_manual_handoff(job_id, request_review)
            return
        resource_lease = JobResourceLease(job_id, deadline)
        resource_lease.acquire()
        _acquire_job_slot(job_id, deadline)
        slot_acquired = True
        raise_if_cancelled(job_id)
        if status == "queued":
            status_doc = write_status(
                job_id,
                "analysing",
                transition_reason="analysis_started",
                started_at=status_doc.get("started_at") or now_iso(),
                deadline_at=deadline_at,
            )
            status = "analysing"

        preflight = load_phase_result(job_id, "preflight")
        if preflight is None:
            restore_workspace_from_request(job_id)
            write_status(job_id, "analysing", phase="preflight", deadline_at=deadline_at)
            preflight = run_worker_phase(job_id, "preflight", deadline)

        if status == "analysing":
            write_status(job_id, "patching", transition_reason="analysis_completed", phase="model")
            status = "patching"

        patch_path = job_dir(job_id) / "model.patch"
        used_model = bool(OPENROUTER_API_KEY)
        if patch_path.exists():
            diff = strip_fences(read_text(patch_path))
        elif used_model:
            diff = strip_fences(call_openrouter(build_prompt(job_id, preflight), job_id, deadline))
        else:
            diff = ""
        write_worker_text(patch_path, diff)

        # L2 scope review happens here, before `testing`: an over-reaching or
        # unusable candidate must never reach a worker or an approver.
        repair_report = review_repair_scope(job_id, diff, preflight)
        write_json(job_dir(job_id) / "repair_scope.json", repair_report)
        if repair_report.get("verdict") == "rejected":
            repair_scope.enforce(repair_report)
        candidate_review = manual_scope.review_candidate(repair_report)
        if candidate_review["route"] == "manual":
            candidate_review["patch_sha256"] = hashlib.sha256(diff.encode("utf-8")).hexdigest()
            _finish_manual_handoff(job_id, candidate_review)
            return
        repair_scope.enforce(repair_report)

        if status == "patching":
            write_status(job_id, "testing", transition_reason="patch_prepared", phase="test_patch")

        hotfix_packet = None
        if request.mode == "hotfix":
            tested, hotfix_packet = _run_hotfix_tests(job_id, diff, deadline)
        else:
            tested = load_phase_result(job_id, "test_patch")
            if tested is None or not isinstance(tested.get("test_evidence"), dict):
                restore_workspace_from_request(job_id)
                write_worker_text(patch_path, diff)
                tested = run_worker_phase(job_id, "test_patch", deadline)
        write_status(job_id, "testing", test_evidence=tested.get("test_evidence"))
        _assert_phase_success(tested, require_patch=bool(diff))
        result = {
            "job_id": job_id,
            "used_model": used_model,
            "model": OPENROUTER_MODEL if used_model else None,
            "preflight": preflight,
            "model_patch_written": bool(diff),
            "repair_scope": repair_report,
            "patch_result": tested.get("patch_result"),
            "postflight": tested,
            "test_evidence": tested.get("test_evidence"),
            "files": tested.get("files", []),
            "manifest": source_manifest.build_manifest(
                _submitted_files(job_id), tested.get("files"), repair_report=repair_report
            ),
            "approval_required": True,
        }
        if hotfix_packet is not None:
            result["hotfix_evidence"] = hotfix_packet
        if not used_model:
            result["dry_run_note"] = "OPENROUTER_API_KEY is not set; the unchanged candidate still requires approval."
        raise_if_cancelled(job_id)
        write_json(job_dir(job_id) / "result.json", result)
        resource_lease.release(update_status=True)
        resource_lease = None
        write_status(
            job_id,
            "awaiting_approval",
            transition_reason="candidate_tests_completed",
            phase="approval",
            deadline_at=None,
            total_deadline_at=None,
            result=result,
            approval_required=True,
            hotfix_evidence=hotfix_packet,
        )
    except JobCancelledError as exc:
        _roll_back_job(job_id, "cancellation_acknowledged", exc)
    except WorkerExecutionTimedOutError as exc:
        timed_out_status = str(read_status(job_id)["status"])
        resource_lease, slot_acquired = _release_execution_capacity(resource_lease, slot_acquired)
        _finish_timeout_soft(job_id, exc, timed_out_status)
    except AppError as exc:
        write_status(job_id, "failed", transition_reason="structured_job_failure", **_error_status_fields(exc))
    except Exception as exc:
        error = UnexpectedJobError(f"Unexpected job failure: {type(exc).__name__}")
        write_status(job_id, "failed", transition_reason="unexpected_job_failure", **_error_status_fields(error))
    finally:
        if resource_lease is not None:
            try:
                resource_lease.release(update_status=True)
            except ResourceLockError as exc:
                LOGGER.error("%s: %s", exc.code, exc)
        _seal_patch_and_cleanup(job_id, slot_acquired)


def _submitted_files(job_id: str) -> list[dict] | None:
    """
    The input exactly as the sender submitted it, from the orchestrator's own
    staged copy. A manifest names its base by hashing this, not the worker's
    snapshot: the worker runs in a container and is the less trusted side, and
    the staged copy is what the sender can reproduce byte for byte. When it is
    unreadable the manifest says its base is unknown instead of guessing.
    """
    try:
        request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
    except (OSError, ValueError, ValidationError, HTTPException) as exc:
        error = JobPersistenceError("Submitted files are unreadable; the result manifest cannot name its base")
        LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)
        return None
    return [{"path": entry.path, "content": entry.content} for entry in request.files]


def _stored_repair_report(job_id: str) -> dict | None:
    """
    The L2 review written before approval, used only for line counts in the
    result manifest. Its absence costs those counts and nothing else, so an
    unreadable report is logged and omitted rather than failing a job that
    has already been approved and applied.
    """
    path = job_dir(job_id) / "repair_scope.json"
    if not path.exists():
        return None
    try:
        report = read_json(path)
    except (OSError, ValueError, HTTPException) as exc:
        error = JobPersistenceError("Repair scope report is unreadable; manifest line counts are omitted")
        LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)
        return None
    return report if isinstance(report, dict) else None


def run_approved(job_id: str) -> None:
    """Apply an explicitly approved candidate, verify it, then complete it."""
    slot_acquired = False
    resource_lease: JobResourceLease | None = None
    try:
        status_doc, deadline, deadline_at = _execution_deadline(job_id)
        status = str(status_doc["status"])
        status_doc = write_status(
            job_id,
            status,
            total_started_at=now_iso(),
            total_deadline_at=deadline_at,
            deadline_at=deadline_at,
        )
        resource_lease = JobResourceLease(job_id, deadline)
        resource_lease.acquire()
        _acquire_job_slot(job_id, deadline)
        slot_acquired = True
        raise_if_cancelled(job_id)
        patch_path = job_dir(job_id) / "model.patch"
        diff = strip_fences(read_text(patch_path)) if patch_path.exists() else ""

        applied = load_phase_result(job_id, "apply_patch")
        if status == "applying":
            restore_workspace_from_request(job_id)
            write_worker_text(patch_path, diff)
            if diff:
                applied = run_worker_phase(job_id, "apply_patch", deadline)
            else:
                applied = load_phase_result(job_id, "preflight")
            if applied is None:
                raise JobPersistenceError("Approved candidate has no persisted analysis result")
            _assert_phase_success(applied, require_patch=bool(diff))
            _restore_workspace_from_files(job_id, applied.get("files"))
            write_status(
                job_id,
                "verifying",
                transition_reason="approved_patch_applied",
                phase="verify",
                deadline_at=deadline_at,
            )
        elif applied is not None:
            _restore_workspace_from_files(job_id, applied.get("files"))
        else:
            raise JobPersistenceError("Applied checkpoint is missing during verification recovery")

        verified = run_worker_phase(job_id, "verify", deadline)
        write_status(job_id, "verifying", test_evidence=verified.get("test_evidence"))
        _assert_phase_success(verified, require_patch=False)
        tested = load_phase_result(job_id, "test_patch")
        prior_evidence = tested.get("test_evidence") if tested else None
        current_evidence = verified.get("test_evidence")
        _assert_reproducible_result(prior_evidence, current_evidence)
        manifest = source_manifest.build_manifest(
            _submitted_files(job_id),
            verified.get("files"),
            repair_report=_stored_repair_report(job_id),
        )
        # The sandbox's own evidence only shows that its phases agree with each
        # other; both numbers come from the worker. This one is the
        # orchestrator hashing the files it is about to deliver and holding
        # them against what the approver was shown. A worker that reported
        # consistent evidence but returned other files used to complete.
        approved_digest = (status_doc.get("approval") or {}).get("candidate_bundle_sha256")
        if approved_digest and manifest["candidate_bundle_sha256"] != approved_digest:
            raise WorkerExecutionError("Delivered files differ from the candidate that was approved")
        result = {
            "job_id": job_id,
            "used_model": bool(OPENROUTER_API_KEY),
            "model": OPENROUTER_MODEL if OPENROUTER_API_KEY else None,
            "patch_result": applied.get("patch_result") if applied else None,
            "postflight": verified,
            "test_evidence": current_evidence,
            "files": verified.get("files", []),
            "manifest": manifest,
            "approval_required": False,
            "approved_at": status_doc.get("approved_at"),
        }
        write_json(job_dir(job_id) / "result.json", result)
        resource_lease.release(update_status=True)
        resource_lease = None
        _complete_job(job_id, result)
    except JobCancelledError as exc:
        _finish_approved_failure(job_id, exc)
    except WorkerExecutionTimedOutError as exc:
        timed_out_status = str(read_status(job_id)["status"])
        resource_lease, slot_acquired = _release_execution_capacity(resource_lease, slot_acquired)
        _finish_timeout_soft(job_id, exc, timed_out_status)
    except AppError as exc:
        _finish_approved_failure(job_id, exc)
    except Exception as exc:
        error = UnexpectedJobError(f"Unexpected approved execution failure: {type(exc).__name__}")
        _finish_approved_failure(job_id, error)
    finally:
        if resource_lease is not None:
            try:
                resource_lease.release(update_status=True)
            except ResourceLockError as exc:
                LOGGER.error("%s: %s", exc.code, exc)
        _seal_patch_and_cleanup(job_id, slot_acquired)


SUPERVISOR_SWEEP_LOCK = threading.Lock()
SUPERVISOR_STATE_LOCK = threading.Lock()
SUPERVISOR_STOP = threading.Event()
SUPERVISOR_THREAD: threading.Thread | None = None
SUPERVISOR_EVENT_LIMIT = 100
SUPERVISOR_MIN_STALL_SLACK_SECONDS = 60


def _new_supervisor_state() -> dict:
    return {
        "started_at": None, "last_sweep_started_at": None, "last_sweep_finished_at": None,
        "last_sweep_ms": None, "sweeps": 0, "errors": 0, "open_quests": 0,
        "actions": {kind: 0 for kind in (
            supervisor.ACTION_REMIND, supervisor.ACTION_EXPIRE, supervisor.ACTION_RESUME, supervisor.ACTION_FAIL)},
        "events": [], "board": [],
    }


SUPERVISOR_STATE = _new_supervisor_state()


def _iso_epoch(raw: object) -> float | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _supervisor_memory_path() -> Path:
    return JOBS_DIR / ".supervisor" / "state.json"


def _load_supervisor_memory() -> dict:
    """
    Reminders sent and resumes tried, kept apart from the job statuses on
    purpose: a status write moves the revision, and a reminder that did so would
    invalidate the approval button the person is about to press. Losing this
    memory costs one repeated reminder, so an unreadable file starts it empty.
    """
    fresh: dict = {"reminded": {}, "resumes": {}}
    path = _supervisor_memory_path()
    if not path.exists():
        return fresh
    try:
        data = read_json(path)
        reminded = {str(k): float(v) for k, v in data["reminded"].items()}
        resumes = {str(k): int(v) for k, v in data["resumes"].items()}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, HTTPException) as exc:
        error = JobPersistenceError("Supervisor memory is unreadable; starting it empty")
        LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)
        return fresh
    return {"reminded": reminded, "resumes": resumes}


def _save_supervisor_memory(memory: dict) -> None:
    try:
        write_json(_supervisor_memory_path(), memory)
    except OSError as exc:
        error = JobPersistenceError("Supervisor memory could not be persisted")
        LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)


def _supervisor_views(memory: dict) -> list[supervisor.JobView]:
    """Snapshot every quest that is not finished. Terminal jobs are skipped on sight."""
    if not JOBS_DIR.exists():
        return []
    with ACTIVE_JOBS_LOCK:
        running = set(ACTIVE_JOBS)
    views: list[supervisor.JobView] = []
    for root in sorted(JOBS_DIR.iterdir()):
        if not root.is_dir() or not JOB_ID_RE.fullmatch(root.name):
            continue
        try:
            status_doc = read_status(root.name)
        except (AppError, HTTPException, OSError, ValueError):
            continue
        status = str(status_doc.get("status"))
        if status in TERMINAL_JOB_STATUSES:
            continue
        views.append(supervisor.JobView(
            job_id=root.name,
            status=status,
            status_changed_at=_iso_epoch(status_doc.get("status_changed_at")),
            heartbeat_at=_iso_epoch(status_doc.get("heartbeat_at")),
            thread_alive=root.name in running,
            resumes=memory["resumes"].get(root.name, 0),
            reminded_at=memory["reminded"].get(root.name),
        ))
    return views


def _supervisor_record(action: supervisor.Action, *, executed: bool, detail: str = "") -> None:
    event = {
        "at": now_iso(), "kind": action.kind, "job_id": action.job_id, "reason": action.reason,
        "waited_seconds": int(action.waited_seconds), "executed": executed, "detail": detail,
    }
    with SUPERVISOR_STATE_LOCK:
        SUPERVISOR_STATE["events"] = (SUPERVISOR_STATE["events"] + [event])[-SUPERVISOR_EVENT_LIMIT:]
        if executed:
            SUPERVISOR_STATE["actions"][action.kind] = SUPERVISOR_STATE["actions"].get(action.kind, 0) + 1
    LOGGER.info("supervisor %s job=%s reason=%s executed=%s", action.kind, action.job_id[:12], action.reason, executed)


def _supervisor_execute(action: supervisor.Action, memory: dict, now: float) -> bool:
    """
    Carry out one planned action, after checking it still applies. The plan
    is a snapshot and a person may have approved, rejected or cancelled in the
    meantime; acting on stale information is how a supervisor does damage.
    """
    job_id = action.job_id
    if action.kind == supervisor.ACTION_REMIND:
        if read_status(job_id).get("status") != supervisor.STATUS_AWAITING:
            return False
        memory["reminded"][job_id] = now
        _supervisor_record(action, executed=True)
        return True

    if action.kind == supervisor.ACTION_EXPIRE:
        with STATUS_LOCK:
            doc = read_status(job_id)
            if doc.get("status") != supervisor.STATUS_AWAITING:
                return False
            started = _iso_epoch(doc.get("status_changed_at"))
            waited = now - started if started is not None else 0.0
            if waited < SUPERVISOR_POLICY.expire_seconds:
                return False
            error = ApprovalExpiredError(
                f"Candidate waited {waited / 3600:.0f} h for approval and was withdrawn; "
                "resubmit it if it is still wanted"
            )
            _roll_back_job(job_id, "approval_expired", error,
                           outcome="approval_expired", waited_seconds=int(waited))
        memory["reminded"].pop(job_id, None)
        _supervisor_record(action, executed=True, detail=error.code)
        return True

    if action.kind == supervisor.ACTION_RESUME:
        with ACTIVE_JOBS_LOCK:
            if job_id in ACTIVE_JOBS:
                return False
        if read_status(job_id).get("status") not in supervisor.EXECUTING_STATUSES:
            return False
        memory["resumes"][job_id] = memory["resumes"].get(job_id, 0) + 1
        started_thread = start_job_thread(job_id)
        _supervisor_record(action, executed=started_thread)
        return started_thread

    if action.kind == supervisor.ACTION_FAIL:
        with STATUS_LOCK:
            with ACTIVE_JOBS_LOCK:
                if job_id in ACTIVE_JOBS:
                    return False
            if read_status(job_id).get("status") not in supervisor.EXECUTING_STATUSES:
                return False
            error = JobRecoveryError("Quest lost its worker thread and could not be resumed")
            _roll_back_job(job_id, "supervisor_unrecoverable", error, outcome="orphaned")
        memory["resumes"].pop(job_id, None)
        _supervisor_record(action, executed=True, detail=error.code)
        return True

    return False


def supervisor_sweep(now: float | None = None) -> dict:
    """One pass: look at every open quest, plan, act. Safe to call from a test or by hand."""
    started = time.time()
    now = started if now is None else now
    with SUPERVISOR_SWEEP_LOCK:
        with SUPERVISOR_STATE_LOCK:
            SUPERVISOR_STATE["last_sweep_started_at"] = started
        memory = _load_supervisor_memory()
        views = _supervisor_views(memory)
        actions, attention = supervisor.plan(views, now, SUPERVISOR_POLICY)
        executed = failed = 0
        for action in actions:
            try:
                if _supervisor_execute(action, memory, now):
                    executed += 1
            except (AppError, HTTPException, OSError, ValueError) as exc:
                # One quest that cannot be handled must not stop the others.
                failed += 1
                code = exc.code if isinstance(exc, AppError) else type(exc).__name__
                _supervisor_record(action, executed=False, detail=str(code))
        open_ids = {view.job_id for view in views}
        memory["reminded"] = {k: v for k, v in memory["reminded"].items() if k in open_ids}
        memory["resumes"] = {k: v for k, v in memory["resumes"].items() if k in open_ids}
        _save_supervisor_memory(memory)
        finished = time.time()
        with SUPERVISOR_STATE_LOCK:
            SUPERVISOR_STATE["last_sweep_finished_at"] = finished
            SUPERVISOR_STATE["last_sweep_ms"] = int((finished - started) * 1000)
            SUPERVISOR_STATE["sweeps"] += 1
            SUPERVISOR_STATE["errors"] += failed
            SUPERVISOR_STATE["open_quests"] = len(views)
            SUPERVISOR_STATE["board"] = [
                {"job_id": item.job_id, "status": item.status, "attention": item.kind,
                 "waited_seconds": None if item.waited_seconds is None else int(item.waited_seconds),
                 "expires_in_seconds": None if item.expires_in_seconds is None else int(item.expires_in_seconds)}
                for item in attention
            ]
    return {"open_quests": len(views), "planned": len(actions), "executed": executed, "failed": failed}


def _supervisor_loop() -> None:
    while not SUPERVISOR_STOP.is_set():
        try:
            supervisor_sweep()
        except Exception as exc:
            # The loop has to outlive any one bad sweep: a supervisor that dies
            # on its first surprise supervises nothing. The failure is counted
            # and shown in /health rather than swallowed.
            error = UnexpectedJobError(f"Supervisor sweep failed: {type(exc).__name__}")
            LOGGER.error("%s: %s", error.code, error)
            with SUPERVISOR_STATE_LOCK:
                SUPERVISOR_STATE["errors"] += 1
        SUPERVISOR_STOP.wait(SUPERVISOR_INTERVAL_SECONDS)


def start_supervisor() -> bool:
    global SUPERVISOR_THREAD
    if not SUPERVISOR_ENABLED:
        LOGGER.warning("Quest supervisor is disabled; stuck quests will not be reminded about or withdrawn")
        return False
    if SUPERVISOR_THREAD is not None and SUPERVISOR_THREAD.is_alive():
        return False
    SUPERVISOR_STOP.clear()
    with SUPERVISOR_STATE_LOCK:
        SUPERVISOR_STATE["started_at"] = time.time()
    SUPERVISOR_THREAD = threading.Thread(target=_supervisor_loop, daemon=True, name="flare-supervisor")
    SUPERVISOR_THREAD.start()
    return True


def stop_supervisor(timeout: float = 5.0) -> None:
    SUPERVISOR_STOP.set()
    thread = SUPERVISOR_THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout)


def supervisor_status() -> dict:
    """
    The supervisor's own vital signs. `stalled` is worked out here, on the
    request thread, so it still reads true when the supervisor thread itself
    has died or hung: a supervisor that reports only through itself cannot be
    supervised.
    """
    with SUPERVISOR_STATE_LOCK:
        state = {key: value for key, value in SUPERVISOR_STATE.items() if key not in {"events", "board", "actions"}}
        actions = dict(SUPERVISOR_STATE["actions"])
    thread = SUPERVISOR_THREAD
    running = bool(thread is not None and thread.is_alive())
    reference = state["last_sweep_finished_at"] or state["started_at"]
    age = None if reference is None else max(0.0, time.time() - reference)
    allowed = max(3 * SUPERVISOR_INTERVAL_SECONDS, SUPERVISOR_INTERVAL_SECONDS + SUPERVISOR_MIN_STALL_SLACK_SECONDS)
    stalled = bool(SUPERVISOR_ENABLED and state["started_at"] is not None
                   and (not running or (age is not None and age > allowed)))
    return {
        "enabled": SUPERVISOR_ENABLED,
        "running": running,
        "stalled": stalled,
        "interval_seconds": SUPERVISOR_INTERVAL_SECONDS,
        "last_sweep_age_seconds": None if age is None else round(age, 1),
        "last_sweep_ms": state["last_sweep_ms"],
        "sweeps": state["sweeps"],
        "errors": state["errors"],
        "open_quests": state["open_quests"],
        "actions": actions,
    }


def write_boundary_status() -> dict:
    """
    What Flare is allowed to touch, as /health reports it. `host_jobs_dir_ok`
    is the one that can be wrong in production without anything failing until
    the first worker phase, so it is judged here, on every health check.
    """
    try:
        exec_guard.validate_host_jobs_dir(HOST_JOBS_DIR, PROTECTED_HOST_PATHS)
        host_dir_ok = True
    except DirectWriteRefusedError:
        host_dir_ok = False
    return {
        "container_commands_allowed": list(exec_guard.ALLOWED_VERBS),
        "host_jobs_dir_ok": host_dir_ok,
        "protected_host_paths": len(PROTECTED_HOST_PATHS),
    }


@app.get("/supervisor", dependencies=[Depends(require_auth)])
def get_supervisor() -> dict:
    """
    The supervisor's vital signs, its policy, what it has done lately, and the
    quests that need a person. Flare posts nowhere itself: this is what a
    caller polls to know that something is waiting, and for how long.
    """
    with SUPERVISOR_STATE_LOCK:
        events = list(SUPERVISOR_STATE["events"])
        board = list(SUPERVISOR_STATE["board"])
    return {
        **supervisor_status(),
        "policy": {
            "approval_remind_seconds": SUPERVISOR_POLICY.remind_seconds,
            "approval_expire_seconds": SUPERVISOR_POLICY.expire_seconds,
            "approval_notice_seconds": SUPERVISOR_POLICY.notice_seconds,
            "orphan_seconds": SUPERVISOR_POLICY.orphan_seconds,
            "max_resumes": SUPERVISOR_POLICY.max_resumes,
            "hung_seconds": SUPERVISOR_POLICY.hung_seconds,
        },
        "board": board,
        "events": events,
    }


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "worker_image": WORKER_IMAGE,
        "worker_network": WORKER_NETWORK,
        "jobs_dir": str(JOBS_DIR),
        "host_jobs_dir_set": bool(HOST_JOBS_DIR),
        "max_parallel_jobs": MAX_PARALLEL_JOBS,
        "max_active_jobs": MAX_ACTIVE_JOBS,
        "max_parallel_jobs_per_repository": MAX_PARALLEL_JOBS_PER_REPOSITORY,
        "held_resource_locks": held_resource_lock_count(),
        "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "heartbeat_stale_seconds": HEARTBEAT_STALE_SECONDS,
        "progress_report_limit": PROGRESS_REPORT_LIMIT,
        "job_timeout_seconds": JOB_TIMEOUT_SECONDS,
        "job_total_timeout_seconds": JOB_TOTAL_TIMEOUT_SECONDS,
        "l4_required_green_runs": L4_REQUIRED_GREEN_RUNS,
        "openrouter_timeout_seconds": OPENROUTER_TIMEOUT_SECONDS,
        "openrouter_max_attempts": OPENROUTER_MAX_ATTEMPTS,
        "finja_timeout_retry_after_seconds": FINJA_TIMEOUT_RETRY_AFTER_SECONDS,
        "dedupe_window_seconds": DEDUPE_WINDOW_SECONDS,
        "rate_limiting": RATE_LIMITING_ENABLED,
        "rate_limits": SUBMISSION_LIMITER.describe(),
        "supervisor": supervisor_status(),
        "write_boundary": write_boundary_status(),
        "active_jobs": active_job_count(),
        "active_quests": persisted_active_job_count(),
        "stale_active_jobs": stale_active_job_count(),
        "state_schema_version": JOB_STATE_SCHEMA_VERSION,
        "job_statuses": sorted(JOB_STATUS_VALUES),
        "terminal_job_statuses": sorted(TERMINAL_JOB_STATUSES),
        "transport_encryption": transport_enabled(),
        "keep_job_workspace": KEEP_JOB_WORKSPACE,
        "testbed_mode": FLARE_TESTBED_MODE,
    }


@app.post("/jobs", response_model=CreateJobResponse,
          dependencies=[Depends(require_auth), Depends(limit_job_submissions)])
def create_job(
    request_body: dict = Body(...),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> CreateJobResponse:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        request = CreateJobRequest.model_validate(open_json(request_body))
    except ValidationError as exc:
        raise InvalidJobRequestError() from exc
    # Hard exclusion happens before fingerprinting, dedupe, staging or any
    # model call, so a refused submission leaves nothing on disk and nothing
    # in a prompt. It runs on the decrypted body, i.e. on what Flare would
    # actually have stored.
    privacy_gate.enforce(privacy_gate.review_submission(
        task=request.task,
        files=[(entry.path, entry.content) for entry in request.files],
    ))
    fingerprint = request_fingerprint(request)
    key_hash = idempotency_key_hash(idempotency_key)
    with SUBMISSION_LOCK:
        duplicate = find_duplicate_job(fingerprint, key_hash)
        if duplicate is not None:
            job_id, status_doc = duplicate
            status = str(status_doc.get("status", "queued"))
            status_doc = write_status(
                job_id,
                status,
                dedupe_count=int(status_doc.get("dedupe_count", 0)) + 1,
                last_deduplicated_at=now_iso(),
            )
            if status in RECOVERABLE_JOB_STATUSES:
                start_job_thread(job_id)
            return CreateJobResponse(
                job_id=job_id,
                status=str(status_doc["status"]),
                revision=int(status_doc["revision"]),
                deduplicated=True,
            )
        active_count = persisted_active_job_count()
        if active_count >= MAX_ACTIVE_JOBS:
            raise ActiveJobLimitReachedError(
                f"Active Flare job limit reached ({active_count}/{MAX_ACTIVE_JOBS}); finish, reject, or cancel a quest"
            )
        job_id = stage_job(request, fingerprint=fingerprint, key_hash=key_hash)
        start_job_thread(job_id)
    return CreateJobResponse(job_id=job_id, status="queued", revision=1, deduplicated=False)


INCIDENT_LEDGER_LOCK = threading.Lock()


def _incident_ledger() -> incident_routing.IncidentLedger:
    """
    The recurrence ledger, kept beside the jobs in a folder that is not a job
    id, so job recovery and counting never mistake it for one. It goes through
    write_json/read_json, which means it is written atomically and encrypted
    at rest whenever a transport key is configured.
    """
    path = JOBS_DIR / ".incidents" / "ledger.json"

    def load() -> dict | None:
        if not path.exists():
            return None
        try:
            return read_json(path)
        except (OSError, ValueError, HTTPException) as exc:
            raise JobPersistenceError("Incident ledger could not be read") from exc

    def save(payload: dict) -> None:
        try:
            write_json(path, payload)
        except OSError as exc:
            raise JobPersistenceError("Incident ledger could not be persisted") from exc

    return incident_routing.IncidentLedger(
        load, save,
        window_seconds=INCIDENT_RECURRENCE_WINDOW_SECONDS,
        episode_seconds=INCIDENT_EPISODE_SECONDS,
        notify_cooldown_seconds=INCIDENT_NOTIFY_COOLDOWN_SECONDS,
    )


def _job_is_active(job_id: str) -> bool:
    try:
        return read_status(job_id).get("status") in ACTIVE_JOB_STATUSES
    except (AppError, HTTPException, OSError, ValueError):
        return False


@app.post("/incidents", dependencies=[Depends(require_auth), Depends(limit_incident_reports)])
def route_incident(
    request_body: dict = Body(...),
    x_finja_code_accept_encrypted: str = Header(default=""),
) -> dict:
    """
    Validate a redacted incident, count it, and say what Flare would do.

    This is a decision, not a job: nothing is staged, no worker runs, no
    model is called. Mapping a routed incident into a repair request is a
    separate step that must not turn envelope text into instructions.
    """
    envelope = incident_envelope.validate_incident_envelope(open_json(request_body))
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with INCIDENT_LEDGER_LOCK:
        decision = incident_routing.route(
            envelope,
            _incident_ledger(),
            threshold=INCIDENT_RECURRENCE_THRESHOLD,
            max_fix_attempts=INCIDENT_MAX_AUTO_FIX_ATTEMPTS,
            is_job_active=_job_is_active,
        )
    active = persisted_active_job_count()
    decision["source"] = source_manifest.profile_bundle(envelope)
    decision["capacity"] = {
        "active_quests": active,
        "max_active_quests": MAX_ACTIVE_JOBS,
        "has_room": active < MAX_ACTIVE_JOBS,
    }
    if transport_enabled() and x_finja_code_accept_encrypted == "1":
        return seal_json(decision)
    return decision


@app.get("/jobs/{job_id}", dependencies=[Depends(require_auth)])
def get_job(job_id: str, x_finja_code_accept_encrypted: str = Header(default="")) -> dict:
    status_doc = read_status(job_id)
    if transport_enabled() and x_finja_code_accept_encrypted == "1":
        return seal_json(status_doc)
    return status_doc


@app.get("/jobs/{job_id}/reports", dependencies=[Depends(require_auth)])
def get_job_reports(job_id: str, x_finja_code_accept_encrypted: str = Header(default="")) -> dict:
    """Return the bounded progress stream Finja can relay to the user."""
    status_doc = read_status(job_id)
    response = {
        "job_id": job_id,
        "status": status_doc["status"],
        "status_message": status_doc["status_message"],
        "revision": status_doc["revision"],
        "progress_percent": status_doc["progress_percent"],
        "heartbeat_at": status_doc.get("heartbeat_at"),
        "heartbeat_sequence": status_doc.get("heartbeat_sequence", 0),
        "reports": status_doc.get("progress_reports", []),
    }
    for field in (
        "outcome",
        "outcome_message",
        "retryable",
        "retry_after_seconds",
        "retry_endpoint",
        "timed_out_from_status",
        "error_code",
    ):
        if field in status_doc:
            response[field] = status_doc[field]
    if transport_enabled() and x_finja_code_accept_encrypted == "1":
        return seal_json(response)
    return response


@app.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_auth)])
def cancel_job(job_id: str) -> dict:
    """Request durable cancellation; the exact public terminal state is rolled_back."""
    return request_job_cancel(job_id)


def _find_retry_job(job_id: str) -> tuple[str, dict] | None:
    if not JOBS_DIR.exists():
        return None
    for root in sorted(JOBS_DIR.iterdir()):
        if not root.is_dir() or not JOB_ID_RE.fullmatch(root.name):
            continue
        try:
            status_doc = read_status(root.name)
        except (AppError, HTTPException, OSError, ValueError):
            continue
        if status_doc.get("retry_of") == job_id:
            return root.name, status_doc
    return None


@app.post("/jobs/{job_id}/retry", response_model=CreateJobResponse,
          dependencies=[Depends(require_auth), Depends(limit_job_submissions)])
def retry_timed_out_job(job_id: str) -> CreateJobResponse:
    """Create one new attempt from a safely rolled-back timeout."""
    with SUBMISSION_LOCK:
        status_doc = read_status(job_id)
        if status_doc.get("status") != "rolled_back" or status_doc.get("outcome") != "timeout_soft":
            raise InvalidJobStateTransitionError("Only a fail-soft timed-out job can be retried")
        existing = _find_retry_job(job_id)
        if existing is not None:
            retry_job_id, retry_status = existing
            return CreateJobResponse(
                job_id=retry_job_id,
                status=str(retry_status["status"]),
                revision=int(retry_status["revision"]),
                deduplicated=True,
            )
        active_count = persisted_active_job_count()
        if active_count >= MAX_ACTIVE_JOBS:
            raise ActiveJobLimitReachedError(
                f"Active Flare job limit reached ({active_count}/{MAX_ACTIVE_JOBS}); retry later"
            )
        try:
            request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
        except (OSError, ValueError, ValidationError) as exc:
            raise JobPersistenceError("Timed-out job request could not be restored for retry") from exc
        retry_job_id = stage_job(request, retry_of=job_id)
        write_status(
            job_id,
            "rolled_back",
            retry_job_id=retry_job_id,
            retry_requested_at=now_iso(),
        )
        start_job_thread(retry_job_id)
        retry_status = read_status(retry_job_id)
        return CreateJobResponse(
            job_id=retry_job_id,
            status=str(retry_status["status"]),
            revision=int(retry_status["revision"]),
            deduplicated=False,
        )


def _approval_record(awaiting: dict, decision: JobDecisionRequest) -> dict:
    """
    What exactly was approved, not only which revision. The revision says
    "the one you were shown"; the bundle digests say what it contained, as the
    orchestrator itself hashed the files it put in front of the approver. The
    finished job is held to the candidate digest (see run_approved), so an
    approval is bound to content and not just to a counter.
    """
    result = awaiting.get("result")
    manifest = result.get("manifest") if isinstance(result, dict) else None
    manifest = manifest if isinstance(manifest, dict) else {}
    return {
        "revision": decision.revision,
        "approved_at": now_iso(),
        "base_bundle_sha256": manifest.get("base_bundle_sha256"),
        "candidate_bundle_sha256": manifest.get("candidate_bundle_sha256"),
    }


def _require_approval_revision(job_id: str, decision: JobDecisionRequest) -> dict:
    status_doc = read_status(job_id)
    if status_doc.get("status") != "awaiting_approval":
        raise InvalidJobStateTransitionError(
            f"Job must be awaiting_approval, not {status_doc.get('status')}"
        )
    if int(status_doc.get("revision", 0)) != decision.revision:
        raise InvalidJobStateTransitionError(
            f"Approval revision is stale: expected {status_doc.get('revision')}, received {decision.revision}"
        )
    return status_doc


@app.post("/jobs/{job_id}/approve", dependencies=[Depends(require_auth)])
def approve_job(job_id: str, decision: JobDecisionRequest) -> dict:
    """Approve exactly the tested revision before any real apply step starts."""
    with STATUS_LOCK:
        awaiting = _require_approval_revision(job_id, decision)
        request = CreateJobRequest.model_validate(read_json(job_dir(job_id) / "request.json"))
        if request.mode == "hotfix":
            packet_path = job_dir(job_id) / "hotfix_evidence.json"
            if not packet_path.exists():
                raise HotfixApprovalGateError("Hotfix sandbox evidence is missing")
            try:
                packet = read_json(packet_path)
            except (OSError, ValueError, HTTPException) as exc:
                raise HotfixApprovalGateError("Hotfix sandbox evidence is unreadable") from exc
            patch_path = job_dir(job_id) / "model.patch"
            diff = strip_fences(read_text(patch_path)) if patch_path.exists() else ""
            _validate_hotfix_packet(job_id, diff, packet)
            if awaiting.get("hotfix_evidence") != packet:
                raise HotfixApprovalGateError("Hotfix approval evidence differs from the tested revision")
            tested = load_phase_result(job_id, "test_patch")
            if tested is None:
                raise HotfixApprovalGateError("Hotfix final sandbox checkpoint is missing")
            try:
                _assert_reproducible_result(packet["runs"][-1]["test_evidence"], tested.get("test_evidence"))
            except WorkerExecutionError as exc:
                raise HotfixApprovalGateError("Hotfix final checkpoint differs from approval evidence") from exc
        status_doc = write_status(
            job_id,
            "applying",
            transition_reason="candidate_approved",
            approved_at=now_iso(),
            approved_revision=decision.revision,
            approval=_approval_record(awaiting, decision),
            approval_required=False,
            deadline_at=None,
        )
    start_job_thread(job_id)
    return status_doc


@app.post("/jobs/{job_id}/reject", dependencies=[Depends(require_auth)])
def reject_job(job_id: str, decision: JobDecisionRequest) -> dict:
    """Reject exactly the tested revision and restore the original snapshot."""
    with STATUS_LOCK:
        _require_approval_revision(job_id, decision)
        return _roll_back_job(job_id, "candidate_rejected")


@app.get("/jobs/{job_id}/manual", dependencies=[Depends(require_auth)])
def get_manual_handoff(job_id: str) -> dict:
    """Return the review reason and optional un-applied candidate for a human."""
    status_doc = read_status(job_id)
    if status_doc.get("outcome") != "manual_required":
        raise HTTPException(status_code=404, detail="No manual handoff for this job")
    root = job_dir(job_id)
    report_path = root / "manual_review.json"
    if not report_path.exists():
        raise JobPersistenceError("Manual handoff report is missing")
    try:
        report = read_json(report_path)
    except (OSError, ValueError, HTTPException) as exc:
        raise JobPersistenceError("Manual handoff report is unreadable") from exc
    if not isinstance(report, dict) or status_doc.get("manual_review") != report:
        raise JobPersistenceError("Manual handoff report differs from the terminal job status")
    patch_path = root / "model.patch"
    candidate = None
    if report.get("stage") == "candidate":
        if not patch_path.exists():
            raise JobPersistenceError("Manual candidate diff is missing")
        try:
            candidate = read_text(patch_path)
        except (OSError, ValueError, HTTPException) as exc:
            raise JobPersistenceError("Manual candidate diff is unreadable") from exc
        if hashlib.sha256(candidate.encode("utf-8")).hexdigest() != report.get("patch_sha256"):
            raise JobPersistenceError("Manual candidate diff differs from its review report")
    return seal_json({"job_id": job_id, "manual_review": report, "candidate_diff": candidate})


@app.get("/jobs/{job_id}/changeset", dependencies=[Depends(require_auth)])
def get_job_changeset(job_id: str) -> dict:
    """
    The diff, its inverse, before and after hashes, test evidence and a backup
    manifest, as one record. Flare never writes to Finja's tree; this is what
    makes Finja's apply checkable and its undo exact. Available while a
    candidate awaits approval (so it can be reviewed as a diff) and after the
    job has completed.
    """
    status_doc = read_status(job_id)
    state = str(status_doc.get("status"))
    result = status_doc.get("result")
    if state not in {changeset.STATE_AWAITING, changeset.STATE_COMPLETED} \
            or not isinstance(result, dict) or not isinstance(result.get("manifest"), dict):
        raise HTTPException(
            status_code=409,
            detail="A changeset exists while a candidate awaits approval and after the job has completed",
        )
    base = _submitted_files(job_id)
    if base is None:
        raise JobPersistenceError("Submitted files are unreadable; the changeset cannot be built")

    model_patch_sha256 = None
    patch_path = job_dir(job_id) / "model.patch"
    if patch_path.exists():
        try:
            model_patch_sha256 = hashlib.sha256(strip_fences(read_text(patch_path)).encode("utf-8")).hexdigest()
        except (OSError, ValueError, HTTPException) as exc:
            error = JobPersistenceError("Model patch is unreadable; the changeset omits its provenance hash")
            LOGGER.warning("%s: %s (%s)", error.code, error, type(exc).__name__)

    if state == changeset.STATE_COMPLETED:
        tested = load_phase_result(job_id, "test_patch")
        candidate_evidence = tested.get("test_evidence") if tested else None
        applied_evidence = result.get("test_evidence")
    else:
        candidate_evidence, applied_evidence = result.get("test_evidence"), None

    return seal_json(changeset.build_changeset(
        job_id=job_id, state=state, base_files=base, candidate_files=result.get("files"),
        manifest=result["manifest"], candidate_evidence=candidate_evidence,
        applied_evidence=applied_evidence, approval=status_doc.get("approval"),
        model_patch_sha256=model_patch_sha256,
    ))


def _with_digest(entry: object) -> object:
    """Name the exact bytes of a delivered file; malformed entries pass through untouched."""
    if isinstance(entry, dict) and isinstance(entry.get("content"), str):
        return {**entry, "sha256": source_manifest.file_sha256(entry["content"])}
    return entry


@app.get("/jobs/{job_id}/files", dependencies=[Depends(require_auth)])
def get_job_files(job_id: str) -> dict:
    root = job_dir(job_id) / "workspace"
    if not root.exists():
        status_doc = read_status(job_id)
        result = status_doc.get("result")
        if isinstance(result, dict) and isinstance(result.get("files"), list):
            return seal_json({"job_id": job_id, "files": [_with_digest(entry) for entry in result["files"]]})
        raise HTTPException(status_code=404, detail="Job files are not available")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            files.append(_with_digest({
                "path": rel, "content": path.read_text(encoding="utf-8", errors="replace"),
            }))
    response = {"job_id": job_id, "files": files}
    return seal_json(response)


@app.delete("/jobs/{job_id}", dependencies=[Depends(require_auth)])
def delete_job(job_id: str) -> dict:
    root = job_dir(job_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    status_doc = read_status(job_id)
    with ACTIVE_JOBS_LOCK:
        locally_active = job_id in ACTIVE_JOBS
    if locally_active or status_doc.get("status") not in TERMINAL_JOB_STATUSES:
        raise InvalidJobStateTransitionError("Cancel the job and wait for a terminal status before deleting it")
    shutil.rmtree(root)
    return {"deleted": job_id}
