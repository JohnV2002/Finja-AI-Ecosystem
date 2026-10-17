"""
======================================================================
      Flare (Finja Agentic Code) – Quest Supervisor (planning)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Decides what should happen to quests that nobody is
               looking after. Pure planning; it executes nothing.

  New in v1.11.0:
    - First version: a quest can no longer sit on the questboard forever.

----------------------------------------------------------------------

  The problem, measured. The questboard holds five quests, and a candidate
  waiting for approval counts as one. Nothing ever expired such a candidate
  or reminded anyone of it. Five unanswered approvals therefore refused every
  new submission, indefinitely, with FLARE-603: the first new error that
  Finja found would be turned away because someone had not clicked "approve"
  days ago. Separately, `stale_active_jobs` counted executing jobs whose
  heartbeat had stopped and reported the number in /health, but nothing
  acted on it; a job thread that died left its quest stuck and counted.

  Why a supervisor and why separate. Everything that watched a job lived in
  that job's own thread: its deadlines are enforced by the thread that is
  being timed. A quest nobody is running has nobody to enforce them. The
  supervisor is a separate loop with its own failure domain: it neither
  serves requests nor runs jobs, so a flood of one or a stuck job in the
  other cannot stop it, and it reports its own liveness so that it too can be
  supervised.

  What it will and will not do:

    * It reminds about an unanswered approval and, after a longer wait,
      withdraws it, which frees the slot. Both waits are policy, not law.
      A candidate is never withdrawn without a reminder having been out for
      a notice period first, so a restart after a long outage warns before
      it withdraws and does not wipe the board.
    * Flare posts nowhere. A reminder is an event a poller can read from
      /supervisor; whoever turns it into a message (Finja, a Discord bridge)
      is the one who actually gives notice. The withdrawal is the backstop
      for the case where nobody ever does.
    * It resumes a quest whose thread has died (the same resume the process
      start does), a bounded number of times, then rolls it back.
    * It only REPORTS a job whose thread is alive but silent. A thread cannot
      be killed from outside; the job's own deadlines remain in charge of it.
    * It never touches a quest that is moving, never a terminal one, and never
      writes to a job's status for a reminder: a status write moves the
      revision, and a reminder that did so would invalidate the approval
      button the person is about to click.

  This module is pure. It receives snapshots and returns actions; the
  orchestrator carries them out, under the same locks the endpoints use, and
  re-checks each one first, because the world moves between planning and
  acting.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

SCHEMA_VERSION = 1

STATUS_AWAITING = "awaiting_approval"
# Statuses in which a thread is supposed to be doing the work.
EXECUTING_STATUSES = frozenset({"queued", "analysing", "patching", "testing", "applying", "verifying"})

ACTION_REMIND = "remind_approval"
ACTION_EXPIRE = "expire_approval"
ACTION_RESUME = "resume_orphan"
ACTION_FAIL = "fail_orphan"

ATTENTION_AWAITING = "awaiting_approval"
ATTENTION_ORPHANED = "orphaned"
ATTENTION_HUNG = "hung"

DEFAULT_APPROVAL_REMIND_SECONDS = 24 * 3600
DEFAULT_APPROVAL_EXPIRE_SECONDS = 72 * 3600
DEFAULT_APPROVAL_NOTICE_SECONDS = 3600
DEFAULT_ORPHAN_SECONDS = 120
DEFAULT_MAX_RESUMES = 2
DEFAULT_HUNG_SECONDS = 1800


@dataclass(frozen=True)
class Policy:
    remind_seconds: float = DEFAULT_APPROVAL_REMIND_SECONDS
    expire_seconds: float = DEFAULT_APPROVAL_EXPIRE_SECONDS
    # A candidate is withdrawn only once a reminder has been out this long.
    notice_seconds: float = DEFAULT_APPROVAL_NOTICE_SECONDS
    orphan_seconds: float = DEFAULT_ORPHAN_SECONDS
    max_resumes: int = DEFAULT_MAX_RESUMES
    hung_seconds: float = DEFAULT_HUNG_SECONDS


@dataclass(frozen=True)
class JobView:
    """What the supervisor knows about one quest, as plain numbers."""

    job_id: str
    status: str
    # When the quest entered its current status, as an epoch. None if unknown.
    status_changed_at: float | None = None
    # The latest sign of life the job wrote, as an epoch. None if it never did.
    heartbeat_at: float | None = None
    # Whether this process has a thread running the job right now.
    thread_alive: bool = False
    resumes: int = 0
    reminded_at: float | None = None


@dataclass(frozen=True)
class Action:
    kind: str
    job_id: str
    reason: str
    waited_seconds: float


@dataclass(frozen=True)
class Attention:
    """A quest a person may need to look at, for the questboard overview."""

    job_id: str
    status: str
    kind: str
    waited_seconds: float | None
    expires_in_seconds: float | None = None


def _age(now: float, since: float | None) -> float | None:
    if since is None:
        return None
    # A clock that stepped backwards must not produce a negative wait.
    return max(0.0, now - since)


def plan(views: Iterable[JobView], now: float, policy: Policy) -> tuple[list[Action], list[Attention]]:
    """Return what to do and what to flag. Deterministic: same input, same plan."""
    actions: list[Action] = []
    attention: list[Attention] = []

    for view in sorted(views, key=lambda item: item.job_id):
        if view.status == STATUS_AWAITING:
            waited = _age(now, view.status_changed_at)
            if waited is None:
                # Without a start time nothing can be said about the wait, and
                # withdrawing a candidate on a guess would be worse than keeping it.
                attention.append(Attention(view.job_id, view.status, ATTENTION_AWAITING, None))
                continue
            attention.append(Attention(
                view.job_id, view.status, ATTENTION_AWAITING, waited,
                expires_in_seconds=max(0.0, policy.expire_seconds - waited),
            ))
            if waited >= policy.expire_seconds:
                # Never withdraw without notice, however long the wait is. If
                # Flare itself was down for days, every waiting candidate is
                # past its limit on the first sweep after the restart, and
                # nobody had a chance to answer while it was down.
                since_reminder = _age(now, view.reminded_at)
                if since_reminder is None:
                    actions.append(Action(ACTION_REMIND, view.job_id, "notice_before_withdrawal", waited))
                elif since_reminder >= policy.notice_seconds:
                    actions.append(Action(ACTION_EXPIRE, view.job_id, "approval_wait_exceeded", waited))
            elif waited >= policy.remind_seconds:
                since_reminder = _age(now, view.reminded_at)
                if since_reminder is None or since_reminder >= policy.remind_seconds:
                    actions.append(Action(ACTION_REMIND, view.job_id, "approval_unanswered", waited))
            continue

        if view.status not in EXECUTING_STATUSES:
            continue

        silence = _age(now, view.heartbeat_at if view.heartbeat_at is not None else view.status_changed_at)
        if view.thread_alive:
            if silence is not None and silence >= policy.hung_seconds:
                attention.append(Attention(view.job_id, view.status, ATTENTION_HUNG, silence))
            continue

        # No thread is running this quest. Give a young one the benefit of the
        # doubt: a thread is about to start, or a restart is still resuming it.
        if silence is None or silence < policy.orphan_seconds:
            continue
        attention.append(Attention(view.job_id, view.status, ATTENTION_ORPHANED, silence))
        if view.resumes < policy.max_resumes:
            actions.append(Action(ACTION_RESUME, view.job_id, "thread_missing", silence))
        else:
            actions.append(Action(ACTION_FAIL, view.job_id, "resumes_exhausted", silence))

    return actions, attention
