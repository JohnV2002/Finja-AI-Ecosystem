"""
======================================================================
         Flare (Finja Agentic Code) - Structured Errors
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0

  New in v1.11.0:
    - Adds FLARE-610/611 for invalid or privacy-unsafe incident envelopes.
    - Adds FLARE-612 for plain job submissions refused by the input
      exclusion gate (secrets, .env, tokens, diary/memory data).
    - Adds FLARE-613 for submissions refused by the rate limiter and
      FLARE-614 for approvals withdrawn by the quest supervisor.
    - Adds FLARE-502 for container commands outside the worker allowlist
      (the write boundary, core/exec_guard.py).

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

======================================================================
"""
from __future__ import annotations

CODE_PREFIX = "FLARE"


def set_code_prefix(prefix: str) -> None:
    """Override the public prefix for tests or embedded deployments."""
    global CODE_PREFIX
    CODE_PREFIX = (prefix or "APP").strip().upper()


class AppError(Exception):
    """Base class for public FLARE error codes."""

    code_num = None

    def __init__(self, message: str = '', module: str = 'unknown', **kw):
        self.module = module
        self.context = dict(kw)
        super().__init__(message)

    @property
    def code(self) -> str:
        if self.code_num is None:
            raise TypeError("AppError base classes do not own an error code")
        return f"{CODE_PREFIX}-{self.code_num}"

    def for_status(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self), "module": self.module}

# --- FLARE-200 [llm] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class ModelRequestRetriesExhaustedError(AppError):
    code_num = 200
    def __init__(self, message: str = 'Model request retries exhausted', **kw):
        super().__init__(message, module=kw.pop('module', 'llm'), **kw)

# --- FLARE-500 [tool] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class WorkerExecutionTimedOutError(AppError):
    code_num = 500
    def __init__(self, message: str = 'Worker execution timed out', **kw):
        super().__init__(message, module=kw.pop('module', 'tool'), **kw)

# --- FLARE-600 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class JobCancelledError(AppError):
    code_num = 600
    def __init__(self, message: str = 'Job was cancelled', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-800 [host] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class JobRecoveryError(AppError):
    code_num = 800
    def __init__(self, message: str = 'Persisted job state could not be recovered', **kw):
        super().__init__(message, module=kw.pop('module', 'host'), **kw)

# --- FLARE-100 [config] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class RuntimeConfigurationError(AppError):
    code_num = 100
    def __init__(self, message: str = 'Flare runtime configuration is invalid', **kw):
        super().__init__(message, module=kw.pop('module', 'config'), **kw)

# --- FLARE-501 [tool] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class WorkerExecutionError(AppError):
    code_num = 501
    def __init__(self, message: str = 'Worker execution failed', **kw):
        super().__init__(message, module=kw.pop('module', 'tool'), **kw)

# --- FLARE-900 [unexpected] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class UnexpectedJobError(AppError):
    code_num = 900
    def __init__(self, message: str = 'Unexpected job execution failure', **kw):
        super().__init__(message, module=kw.pop('module', 'unexpected'), **kw)

# --- FLARE-601 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class IdempotencyConflictError(AppError):
    code_num = 601
    def __init__(self, message: str = 'Idempotency key conflicts with an existing job', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-801 [host] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class JobPersistenceError(AppError):
    code_num = 801
    def __init__(self, message: str = 'Job state could not be persisted', **kw):
        super().__init__(message, module=kw.pop('module', 'host'), **kw)

# --- FLARE-602 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class InvalidJobStateTransitionError(AppError):
    code_num = 602
    def __init__(self, message: str = 'Job status transition is not allowed', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-603 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class ActiveJobLimitReachedError(AppError):
    code_num = 603
    def __init__(self, message: str = 'Active Flare job limit reached', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-604 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class ResourceLockError(AppError):
    code_num = 604
    def __init__(self, message: str = 'Repository or file lock operation failed', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-605 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class InvalidJobRequestError(AppError):
    code_num = 605
    def __init__(self, message: str = 'Job request validation failed', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-606 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class RepairPatchRejectedError(AppError):
    code_num = 606
    def __init__(self, message: str = 'Proposed repair diff is malformed or targets a path outside the submitted payload', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-607 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class RepairPatchTooLargeError(AppError):
    code_num = 607
    def __init__(self, message: str = 'Proposed repair diff exceeds the allowed repair scope', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-608 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class HotfixApprovalGateError(AppError):
    code_num = 608
    def __init__(self, message: str = 'Hotfix approval requires repeated passing sandbox tests', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-609 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class ManualReviewRequiredError(AppError):
    code_num = 609
    def __init__(self, message: str = 'Change requires human-led multi-file or architecture review', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-610 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class InvalidIncidentEnvelopeError(AppError):
    code_num = 610
    def __init__(self, message: str = 'Incident envelope is invalid or uses an unsupported version', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-611 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class IncidentPrivacyViolationError(AppError):
    code_num = 611
    def __init__(self, message: str = 'Incident envelope contains sensitive or unredacted data', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-612 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class SensitiveInputRejectedError(AppError):
    code_num = 612
    def __init__(self, message: str = 'Submitted files or task contain secrets, credentials or private data and were refused before staging', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-613 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class RequestRateLimitedError(AppError):
    code_num = 613
    def __init__(self, message: str = 'Too many submissions in a short time; the sender must wait before sending again', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-614 [pipeline] owner=finja-agentic-code module= ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class ApprovalExpiredError(AppError):
    code_num = 614
    def __init__(self, message: str = 'Candidate was not approved in time and was withdrawn; resubmit it if it is still wanted', **kw):
        super().__init__(message, module=kw.pop('module', 'pipeline'), **kw)

# --- FLARE-502 [tool] owner=finja-agentic-code module=tool ---
# Ledger-reserved: do not reuse this number under prefix FLARE
class DirectWriteRefusedError(AppError):
    code_num = 502
    def __init__(self, message: str = 'Refused to run a container command outside the worker allowlist; Flare never writes to a running container', **kw):
        super().__init__(message, module=kw.pop('module', 'tool'), **kw)
