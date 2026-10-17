"""
======================================================================
      Flare (Finja Agentic Code) – Incident Routing and Recurrence
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Decides what a validated incident should lead to.

  New in v1.11.0:
    - First version: FINJA-999 and recurring internal errors are routed
      by what they are, instead of every error becoming a repair quest.
    - Recurrence counts EPISODES, not raw sightings, and the decision says
      whether a human should be told, so a flapping monitor neither
      escalates itself nor floods the channel.

----------------------------------------------------------------------

  A validated incident envelope says WHAT failed. This module decides what
  Flare does about it, and the answer is rarely "generate a fix":

    observe   a transient failure below its recurrence threshold. Count it,
              open nothing. A provider timeout is not a code defect.
    operator  a config or host condition. A source diff will not fix an
              environment, so no repair quest is the right answer.
    classify  the catch-all code (the `unexpected` band, 900-999). The error
              contract itself says "prefer dedicated codes": a 999 has no
              classification yet, so the repair is introducing one at the
              frame, not guessing at a defect.
    repair    a deterministic defect with a dedicated code, or none.
    manual    sensitive areas (memory, session, guards, privacy, prompt
              injection), a human-requested change, or a fix that did not
              hold. Automation never touches these.
    tracked   a quest for this exact error is already open.

  The category comes from the CODE NUMBER, using the same ranges the public
  error legend publishes. The legend lives outside the container's build
  context, so the table is mirrored here and a test pins the two together.

  Recurrence is counted per FINGERPRINT (component, code, kind, top frame),
  never per incident id and never including the line number: lines move when
  code is edited, and the same defect must stay the same defect. A replay of
  the same observation is idempotent.

  What recurrence measures is EPISODES. Time is cut into short slots
  (INCIDENT_EPISODE_SECONDS, one minute by default) and an error that fires
  five times inside one slot is one episode seen five times. Without this a
  retry storm or a flapping monitor reaches "three sightings" in seconds and
  escalates itself: measured on this layer, five reports across one minute
  turned a provider timeout into a quest at the third. Fixed slots, rather
  than "close to the previous event", are deliberate: a monitor that fires
  every ninety seconds forever must still escalate, and chaining would let it
  extend a single episode indefinitely. Slots are also what keeps the ledger
  small: a record keeps slot numbers, not timestamps, so a sender firing once
  a second cannot push its own history out of a bounded list.

  Telling a human is a separate question from deciding, and it has its own
  cooldown. A decision says whether a message is warranted (`notify`): only
  for routes a person has to act on, only when the route is new or has
  changed, and otherwise at most once per cooldown. That is the whole of the
  anti-spam contract Flare can offer a caller; posting anywhere is the
  caller's business.

  Decision only. This module creates no job. A job adapter that maps an
  envelope into a repair request is a separate step, and it must not promote
  anything from an envelope's text into instructions.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.exceptions import JobPersistenceError
from core.incident_envelope import IncidentEnvelope

SCHEMA_VERSION = 1
LEDGER_VERSION = 2

ROUTE_OBSERVE = "observe"
ROUTE_OPERATOR = "operator"
ROUTE_CLASSIFY = "classify"
ROUTE_REPAIR = "repair"
ROUTE_MANUAL = "manual"
ROUTE_TRACKED = "tracked"

# Routes where a person has something to do. `observe` is counted silently
# and `tracked` is already in somebody's hands; neither warrants a message.
NOTIFY_ROUTES = frozenset({ROUTE_OPERATOR, ROUTE_CLASSIFY, ROUTE_REPAIR, ROUTE_MANUAL})

# Mirror of the ranges in the public error legend (error_contract.json). Both
# registered namespaces use identical ranges; test_incident_routing.py fails
# if the legend and this table ever disagree.
CATEGORY_RANGES = (
    ("config", 100, 199),
    ("llm", 200, 299),
    ("memory", 300, 399),
    ("session", 400, 499),
    ("tool", 500, 599),
    ("pipeline", 600, 699),
    ("host", 800, 899),
    ("unexpected", 900, 999),
    ("privacy", 1000, 1099),
    ("injection", 1100, 1199),
)
# Memory/diary stores, auth and privileges, guards and safety, the privacy
# firewall and the injection firewall. An automated patch must not decide
# anything in these.
SENSITIVE_CATEGORIES = frozenset({"memory", "session", "pipeline", "privacy", "injection"})
# Environment and host conditions, not source defects.
OPERATOR_CATEGORIES = frozenset({"config", "host"})
# Failures that usually originate outside the code: a provider, a tool.
EXTERNAL_CATEGORIES = frozenset({"llm", "tool"})
CATCH_ALL_CATEGORY = "unexpected"

TRANSIENT_KIND_RE = re.compile(
    r"(?:^|\.)(?:TimeoutError|timeout|ReadTimeout|ConnectTimeout|WriteTimeout|PoolTimeout"
    r"|ConnectionError|ConnectionResetError|ConnectionRefusedError|ConnectionAbortedError"
    r"|BrokenPipeError|ServerDisconnectedError|RemoteDisconnected|RateLimitError"
    r"|ServiceUnavailableError|TemporaryFailure)$"
)

DEFAULT_THRESHOLD = 3
DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_EPISODE_SECONDS = 60
DEFAULT_NOTIFY_COOLDOWN_SECONDS = 3600
DEFAULT_MAX_FIX_ATTEMPTS = 2
MAX_FINGERPRINTS = 500
MAX_REPLAY_KEYS = 50
MAX_SLOTS = 1500
FUTURE_SKEW_SECONDS = 300

NEXT_STEPS = {
    ROUTE_OBSERVE: "Counted only. Nothing is opened until the error recurs.",
    ROUTE_OPERATOR: "Not a source defect. Check the environment, configuration or host.",
    ROUTE_CLASSIFY: "Replace the catch-all code at the reported frame with a dedicated one.",
    ROUTE_REPAIR: "Eligible for the automatic repair path.",
    ROUTE_MANUAL: "Human-led. Automation does not change this area.",
    ROUTE_TRACKED: "A quest for this error is already open. Nothing new is started.",
}


def category_for(error_code: str | None) -> str | None:
    """Band for a code such as `FINJA-999`, by its number. None when unknown."""
    if not error_code or "-" not in error_code:
        return None
    try:
        number = int(error_code.rsplit("-", 1)[1])
    except ValueError:
        return None
    for name, low, high in CATEGORY_RANGES:
        if low <= number <= high:
            return name
    return None


def is_transient_kind(error_kind: str) -> bool:
    return bool(TRANSIENT_KIND_RE.search(error_kind))


def fingerprint_of(envelope: IncidentEnvelope) -> tuple[str, dict]:
    """
    Identify a recurring defect, stably.

    Line numbers are left out on purpose: editing a file moves them, and a
    fix that shifts a line must not make the same defect look new. The top
    frame decides the location, falling back to the first submitted file.
    """
    if envelope.frames:
        top = envelope.frames[0]
        location = f"{top.path}::{top.symbol or ''}"
    else:
        location = f"{envelope.files[0].path}::"
    parts = (envelope.component, envelope.error_code or "", envelope.error_kind, location)
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest, {
        "component": envelope.component,
        "error_code": envelope.error_code,
        "error_kind": envelope.error_kind,
        "location": location,
    }


def _epoch(observed_at: str) -> float:
    return datetime.fromisoformat(observed_at.replace("Z", "+00:00")).timestamp()


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class IncidentLedger:
    """
    Bounded, durable memory of what has been seen.

    Storage is injected as two callables so the orchestrator's own helpers
    (atomic writes, encryption at rest) are used and this module stays free
    of filesystem code. A ledger that cannot be read raises FLARE-801 rather
    than silently starting over: forgetting a recurrence is how a flapping
    error stays quiet.
    """

    def __init__(self, load: Callable[[], Any], save: Callable[[dict], None], *,
                 clock: Callable[[], float] = time.time,
                 window_seconds: int = DEFAULT_WINDOW_SECONDS,
                 episode_seconds: int = DEFAULT_EPISODE_SECONDS,
                 notify_cooldown_seconds: int = DEFAULT_NOTIFY_COOLDOWN_SECONDS,
                 max_fingerprints: int = MAX_FINGERPRINTS,
                 max_replay_keys: int = MAX_REPLAY_KEYS) -> None:
        self._load = load
        self._save = save
        self._clock = clock
        self.window_seconds = window_seconds
        self.episode_seconds = max(1, episode_seconds)
        self.notify_cooldown_seconds = notify_cooldown_seconds
        self.max_fingerprints = max_fingerprints
        self.max_replay_keys = max_replay_keys

    def _records(self) -> dict:
        state = self._load()
        if state is None:
            return {}
        if isinstance(state, dict) and state.get("ledger_version") == 1 \
                and isinstance(state.get("records"), dict):
            return self._migrate_v1(state["records"])
        if not isinstance(state, dict) or state.get("ledger_version") != LEDGER_VERSION \
                or not isinstance(state.get("records"), dict):
            raise JobPersistenceError("Incident ledger is unreadable or uses an unsupported version")
        return state["records"]

    def _migrate_v1(self, records: dict) -> dict:
        """
        Version 1 kept raw timestamps and counted sightings. Version 2 keeps
        slot numbers and counts episodes, so the timestamps are folded into
        slots. Nothing else changes, and nothing is lost that the new count
        could have used.
        """
        for record in records.values():
            if not isinstance(record, dict):
                raise JobPersistenceError("Incident ledger is unreadable or uses an unsupported version")
            events = record.pop("events", [])
            record["slots"] = sorted({int(stamp // self.episode_seconds) for stamp in events})[-MAX_SLOTS:]
            record.setdefault("current_slot", None)
            record.setdefault("notified", None)
        return records

    def _write(self, records: dict) -> None:
        if len(records) > self.max_fingerprints:
            # Evict the least recently seen, but never a record that still
            # tracks an open quest: losing that link would orphan the quest.
            evictable = sorted(
                (fp for fp, rec in records.items() if not rec.get("open_job_id")),
                key=lambda fp: records[fp].get("last_seen", 0.0),
            )
            for fp in evictable[:len(records) - self.max_fingerprints]:
                del records[fp]
        self._save({"ledger_version": LEDGER_VERSION, "records": records})

    def observe(self, fingerprint: str, identity: dict, *, incident_id: str,
                observed_at: str) -> dict:
        """Record one observation and describe the recurrence it belongs to."""
        now = self._clock()
        event_time = min(_epoch(observed_at), now + FUTURE_SKEW_SECONDS)
        slot = int(event_time // self.episode_seconds)
        key = hashlib.sha256(f"{incident_id}|{observed_at}".encode()).hexdigest()[:12]
        records = self._records()
        record = records.get(fingerprint)
        if record is None:
            record = {**identity, "first_seen": event_time, "last_seen": event_time,
                      "total": 0, "slots": [], "current_slot": None, "seen_keys": [],
                      "open_job_id": None, "fix_attempts": 0, "last_fix_at": None,
                      "notified": None}
            records[fingerprint] = record

        duplicate = key in record["seen_keys"]
        if not duplicate:
            record["total"] += 1
            slots = set(record["slots"])
            slots.add(slot)
            # Slots older than any window that could still include a current
            # event are dead weight. Keeping slot numbers instead of raw
            # timestamps is what bounds this however fast the sender fires.
            horizon = max(slots) - self.window_seconds // self.episode_seconds - 2
            record["slots"] = sorted(s for s in slots if s >= horizon)[-MAX_SLOTS:]
            current = record.get("current_slot")
            if current and current["index"] == slot:
                current["count"] += 1
            elif current is None or slot > current["index"]:
                record["current_slot"] = {"index": slot, "count": 1}
            record["seen_keys"] = (record["seen_keys"] + [key])[-self.max_replay_keys:]
            record["first_seen"] = min(record["first_seen"], event_time)
            record["last_seen"] = max(record["last_seen"], event_time)
            self._write(records)

        window_start = event_time - self.window_seconds
        episodes = sum(
            1 for s in record["slots"]
            if (s + 1) * self.episode_seconds > window_start and s * self.episode_seconds <= event_time
        )
        current = record.get("current_slot")
        in_episode = current["count"] if current and current["index"] == slot else 1
        last_fix = record.get("last_fix_at")
        return {
            "fingerprint": fingerprint,
            "episodes_in_window": episodes,
            "sightings_in_episode": in_episode,
            "window_seconds": self.window_seconds,
            "episode_seconds": self.episode_seconds,
            "total": record["total"],
            "first_seen_at": _iso(record["first_seen"]),
            "last_seen_at": _iso(record["last_seen"]),
            "duplicate": duplicate,
            "open_job_id": record.get("open_job_id"),
            "fix_attempts": record.get("fix_attempts", 0),
            "last_fix_at": _iso(last_fix),
            "observed_after_fix": last_fix is not None and event_time > last_fix,
        }

    def notify_decision(self, fingerprint: str, route: str, *, duplicate: bool) -> dict:
        """
        Should a person be told about this decision?

        Yes when the route is one a person acts on AND it is new for this
        error or has changed (an escalation is news), or when the cooldown
        since the last message has elapsed. A replay never notifies. Recording
        the message is part of the decision, so asking twice does not send
        twice.
        """
        if route not in NOTIFY_ROUTES:
            return {"send": False, "reason": "no_message_for_route", "until": None}
        if duplicate:
            return {"send": False, "reason": "duplicate_replay", "until": None}
        records = self._records()
        record = records.get(fingerprint)
        if record is None:
            return {"send": False, "reason": "unknown_fingerprint", "until": None}
        now = self._clock()
        last = record.get("notified")
        if last and last.get("route") == route and now - last["at"] < self.notify_cooldown_seconds:
            return {"send": False, "reason": "suppressed_by_cooldown",
                    "until": _iso(last["at"] + self.notify_cooldown_seconds)}
        if not last:
            reason = "first_notice"
        elif last.get("route") != route:
            reason = "route_changed"
        else:
            reason = "cooldown_elapsed"
        record["notified"] = {"route": route, "at": now}
        self._write(records)
        return {"send": True, "reason": reason, "until": _iso(now + self.notify_cooldown_seconds)}

    def attach_quest(self, fingerprint: str, job_id: str) -> bool:
        """Remember which quest was opened for this error. False if unknown."""
        records = self._records()
        if fingerprint not in records:
            return False
        records[fingerprint]["open_job_id"] = job_id
        self._write(records)
        return True

    def record_fix(self, fingerprint: str, *, completed_at: float | None = None) -> bool:
        """Mark a fix as landed, so later sightings count as "after the fix"."""
        records = self._records()
        if fingerprint not in records:
            return False
        record = records[fingerprint]
        record["fix_attempts"] = record.get("fix_attempts", 0) + 1
        record["last_fix_at"] = completed_at if completed_at is not None else self._clock()
        record["open_job_id"] = None
        # A fix that lands resets the conversation: if the error returns, that
        # is news again and must not be swallowed by an old cooldown.
        record["notified"] = None
        self._write(records)
        return True


def _decide(envelope: IncidentEnvelope, category: str | None, transient: bool,
            recurrence: dict, *, threshold: int, max_fix_attempts: int,
            is_job_active: Callable[[str], bool]) -> tuple[str, list[dict]]:
    """First matching rule wins, and every decision says why."""
    episodes = recurrence["episodes_in_window"]

    if envelope.mode == "manual":
        return ROUTE_MANUAL, [{"kind": "manual_requested",
                               "detail": "The sender asked for a human-led change"}]
    if category in SENSITIVE_CATEGORIES:
        return ROUTE_MANUAL, [{"kind": "sensitive_area",
                               "detail": f"Category '{category}' is never changed automatically"}]
    if category in OPERATOR_CATEGORIES:
        return ROUTE_OPERATOR, [{"kind": "not_a_source_defect",
                                 "detail": f"Category '{category}' describes the environment, not the code"}]

    open_job = recurrence.get("open_job_id")
    if open_job and is_job_active(open_job):
        return ROUTE_TRACKED, [{"kind": "quest_open",
                                "detail": "A quest for this error is still in progress"}]

    reasons: list[dict] = []
    if recurrence["fix_attempts"]:
        if recurrence["observed_after_fix"]:
            if recurrence["fix_attempts"] >= max_fix_attempts:
                return ROUTE_MANUAL, [{
                    "kind": "fix_did_not_hold",
                    "detail": f"The error returned after {recurrence['fix_attempts']} automatic fix(es)",
                }]
            reasons.append({"kind": "regression_after_fix",
                            "detail": "The error returned after an earlier fix"})

    gated = transient or category in EXTERNAL_CATEGORIES
    if gated and episodes < threshold:
        return ROUTE_OBSERVE, [{
            "kind": "below_recurrence_threshold",
            "detail": f"{episodes} of {threshold} episodes in the window; likely external or transient",
        }]
    if gated:
        reasons.append({"kind": "recurring",
                        "detail": f"{episodes} separate episodes within {recurrence['window_seconds']}s"})

    if category == CATCH_ALL_CATEGORY:
        reasons.append({"kind": "catch_all_code",
                        "detail": "The generic code has no classification; the repair is a dedicated code"})
        return ROUTE_CLASSIFY, reasons
    reasons.append({"kind": "dedicated_or_unclassified_defect",
                    "detail": "No rule keeps this away from the repair path"})
    return ROUTE_REPAIR, reasons


def route(envelope: IncidentEnvelope, ledger: IncidentLedger, *,
          threshold: int = DEFAULT_THRESHOLD,
          max_fix_attempts: int = DEFAULT_MAX_FIX_ATTEMPTS,
          is_job_active: Callable[[str], bool] = lambda job_id: False) -> dict:
    """Record the observation and decide. Never creates a job."""
    fingerprint, identity = fingerprint_of(envelope)
    category = category_for(envelope.error_code)
    transient = is_transient_kind(envelope.error_kind)
    recurrence = ledger.observe(
        fingerprint, identity,
        incident_id=envelope.incident_id, observed_at=envelope.observed_at,
    )
    decision, reasons = _decide(
        envelope, category, transient, recurrence,
        threshold=threshold, max_fix_attempts=max_fix_attempts, is_job_active=is_job_active,
    )
    notice = ledger.notify_decision(fingerprint, decision, duplicate=recurrence["duplicate"])
    return {
        "schema_version": SCHEMA_VERSION,
        "incident_id": envelope.incident_id,
        "fingerprint": fingerprint,
        "route": decision,
        "reasons": reasons,
        "next": NEXT_STEPS[decision],
        "category": category,
        "category_source": "code_range" if category else None,
        "transient_kind": transient,
        "mode": envelope.mode,
        "recurrence": {**recurrence, "threshold": threshold},
        "notify": notice,
        "would_open_job": decision in {ROUTE_CLASSIFY, ROUTE_REPAIR},
        "opens_job": False,
    }
