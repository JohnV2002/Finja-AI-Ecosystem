"""
======================================================================
      Flare (Finja Agentic Code) – Submission Rate Limiting
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / core
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Token buckets that turn away a runaway sender cheaply.

  New in v1.11.0:
    - First version: a flood is refused before it reaches the expensive
      part of a submission, instead of after.

----------------------------------------------------------------------

  Why this exists, with the measurement behind it: refusing a submission
  is not free. A new job request runs a duplicate lookup and a quest count,
  and both read the status of EVERY job folder on disk. Measured on a
  throwaway stack, a request that ends in "429, the questboard is full"
  cost 16 ms with an empty history, 229 ms with 100 jobs, 880 ms with 400
  and 2.1 s with 1000, all inside one lock. A sender stuck in a loop gets
  more expensive to survive the older the system gets.

  A token bucket in front of that work caps how many requests may reach it
  at all. Everything past the budget is answered in microseconds.

  Design points:

    * Fail soft. The limiter is arithmetic on three numbers under one lock.
      It does no I/O, takes no other lock, allocates nothing per request and
      clamps a clock that jumps backwards, so there is no way for it to wedge
      the pipeline. A limiter that cannot decide must let the request
      through, so every path here ends in an answer.
    * Human actions are never limited. Approve, reject, cancel and delete are
      not routed through here, so a flood of submissions cannot starve the
      one person who has to approve something.
    * One bucket per kind of submission, not one for everything. Incident
      reports legitimately arrive in bursts from a flapping monitor, jobs do
      not, and neither should be able to eat the other's budget.
    * In memory only. A restart refills the buckets. That is acceptable for
      a guard against loops, and it keeps this free of disk state.
    * Callers are not told which bucket drained or how it is configured
      beyond the wait time.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable


class TokenBucket:
    """
    `capacity` tokens, refilled at `per_minute / 60` tokens per second.

    Starts full, so a quiet sender can burst up to `capacity` at once.
    """

    def __init__(self, capacity: int, per_minute: float, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = max(1, int(capacity))
        self.refill_per_second = max(per_minute, 0.0) / 60.0
        self._clock = clock
        self._tokens = float(self.capacity)
        self._stamp = clock()
        self._lock = threading.Lock()

    def take(self) -> tuple[bool, int]:
        """Spend one token. Returns (allowed, seconds_to_wait_when_refused)."""
        with self._lock:
            now = self._clock()
            # A clock that steps backwards must never mint or burn tokens.
            elapsed = max(0.0, now - self._stamp)
            self._stamp = max(self._stamp, now)
            self._tokens = min(float(self.capacity), self._tokens + elapsed * self.refill_per_second)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True, 0
            if self.refill_per_second <= 0.0:
                return False, 60
            return False, max(1, math.ceil((1.0 - self._tokens) / self.refill_per_second))

    def reset(self) -> None:
        with self._lock:
            self._tokens = float(self.capacity)
            self._stamp = self._clock()


class RateLimiter:
    """A fixed set of named buckets, so each kind of traffic has its own budget."""

    def __init__(self, buckets: dict[str, TokenBucket]) -> None:
        self._buckets = dict(buckets)

    def take(self, name: str) -> tuple[bool, int]:
        bucket = self._buckets.get(name)
        if bucket is None:
            # An unknown name is a wiring mistake, never a reason to refuse.
            return True, 0
        return bucket.take()

    def reset(self) -> None:
        for bucket in self._buckets.values():
            bucket.reset()

    def describe(self) -> dict[str, dict[str, float]]:
        return {
            name: {"burst": bucket.capacity, "per_minute": round(bucket.refill_per_second * 60.0, 3)}
            for name, bucket in sorted(self._buckets.items())
        }
