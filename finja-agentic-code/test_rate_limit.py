#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Submission Rate Limit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Tests for core/rate_limit.py and how the orchestrator uses it.

               The limiter exists because refusing a submission is not free
               (it reads every job folder), so the properties worth pinning
               are the ones that make it safe to leave on: it never blocks a
               human decision, a request without a valid token cannot drain
               the real sender's budget, a refusal stages nothing, and the
               limiter itself cannot wedge anything.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the rate limiter itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import rate_limit  # noqa: E402
from core.exceptions import RequestRateLimitedError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class _Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


# ==============================================================================
# The bucket
# ==============================================================================

class TestTokenBucket:

    def test_a_quiet_sender_may_burst_up_to_the_capacity(self) -> None:
        bucket = rate_limit.TokenBucket(3, 60, clock=_Clock())
        assert [bucket.take()[0] for _ in range(4)] == [True, True, True, False]

    def test_a_refusal_says_how_long_to_wait(self) -> None:
        clock = _Clock()
        bucket = rate_limit.TokenBucket(1, 60, clock=clock)
        bucket.take()
        assert bucket.take() == (False, 1)

        slow = rate_limit.TokenBucket(1, 6, clock=_Clock())
        slow.take()
        assert slow.take() == (False, 10), "6 per minute is one token every ten seconds"

    def test_tokens_come_back_over_time(self) -> None:
        clock = _Clock()
        bucket = rate_limit.TokenBucket(3, 60, clock=clock)
        for _ in range(3):
            bucket.take()
        clock.now += 2
        assert [bucket.take()[0] for _ in range(3)] == [True, True, False]

    def test_waiting_longer_never_banks_more_than_the_capacity(self) -> None:
        clock = _Clock()
        bucket = rate_limit.TokenBucket(3, 60, clock=clock)
        for _ in range(3):
            bucket.take()
        clock.now += 100_000
        assert [bucket.take()[0] for _ in range(5)] == [True, True, True, False, False]

    def test_a_clock_stepping_backwards_neither_mints_nor_burns_tokens(self) -> None:
        clock = _Clock()
        bucket = rate_limit.TokenBucket(2, 60, clock=clock)
        bucket.take()
        bucket.take()
        clock.now -= 100
        assert bucket.take()[0] is False, "going back in time must not refill the bucket"

        clock.now = 1000.0 + 1
        assert bucket.take()[0] is True, "one real second after the peak earns exactly one token"
        assert bucket.take()[0] is False, "and not the hundred the clock jumped through"

    def test_a_bucket_that_never_refills_still_answers(self) -> None:
        bucket = rate_limit.TokenBucket(1, 0, clock=_Clock())
        bucket.take()
        assert bucket.take() == (False, 60)

    def test_the_capacity_is_never_below_one(self) -> None:
        assert rate_limit.TokenBucket(0, 60, clock=_Clock()).capacity == 1

    def test_reset_refills_the_bucket(self) -> None:
        bucket = rate_limit.TokenBucket(2, 60, clock=_Clock())
        bucket.take()
        bucket.take()
        bucket.reset()
        assert bucket.take()[0] is True


class TestRateLimiter:

    def test_each_kind_of_traffic_has_its_own_budget(self) -> None:
        limiter = rate_limit.RateLimiter({
            "jobs": rate_limit.TokenBucket(1, 60, clock=_Clock()),
            "incidents": rate_limit.TokenBucket(2, 60, clock=_Clock()),
        })
        assert limiter.take("jobs")[0] is True
        assert limiter.take("jobs")[0] is False
        assert limiter.take("incidents")[0] is True, "a drained jobs budget must not touch incidents"

    def test_an_unknown_bucket_name_never_refuses(self) -> None:
        """A wiring mistake must not turn into an outage."""
        assert rate_limit.RateLimiter({}).take("typo") == (True, 0)

    def test_it_describes_its_configuration_without_its_state(self) -> None:
        limiter = rate_limit.RateLimiter({"jobs": rate_limit.TokenBucket(10, 30, clock=_Clock())})
        assert limiter.describe() == {"jobs": {"burst": 10, "per_minute": 30.0}}

    def test_reset_refills_every_bucket(self) -> None:
        limiter = rate_limit.RateLimiter({"jobs": rate_limit.TokenBucket(1, 60, clock=_Clock())})
        limiter.take("jobs")
        limiter.reset()
        assert limiter.take("jobs")[0] is True


# ==============================================================================
# In the orchestrator
# ==============================================================================

def _job_body(number: int) -> dict:
    return {"task": f"Fix the bug number {number}", "repository": "t",
            "files": [{"path": "demo.py", "content": "x = 1\n"}]}


def _incident_body(index: int) -> dict:
    content = "x = 1\n"
    return {
        "envelope_version": 1, "incident_id": f"123e4567-e89b-42d3-a456-4266141740{index:02d}",
        "observed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "origin": "finja", "component": "finja-chat", "repository": "r", "mode": "standard",
        "error_kind": "KeyError", "error_code": "FINJA-999", "summary": "A stage failed.",
        "frames": [{"path": "demo.py", "line": 1, "symbol": f"run{index}"}],
        "files": [{"path": "demo.py", "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}],
        "redaction": {"policy": "finja-flare-redaction-v1", "source_minimized": True,
                      "sensitive_values_removed": True},
    }


class TestSubmissionEndpoints:

    @pytest.fixture(autouse=True)
    def _limited(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.clock = _Clock()
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(main, "DEDUPE_WINDOW_SECONDS", 0)
        monkeypatch.setattr(main, "MAX_ACTIVE_JOBS", 50)
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: True)
        monkeypatch.setattr(main, "RATE_LIMITING_ENABLED", True)
        monkeypatch.setattr(main, "SUBMISSION_LIMITER", rate_limit.RateLimiter({
            "jobs": rate_limit.TokenBucket(3, 60, clock=self.clock),
            "incidents": rate_limit.TokenBucket(5, 60, clock=self.clock),
        }))
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.clear()
        self.jobs = tmp_path / "jobs"
        self.client = TestClient(main.app)

    def _folders(self) -> list[str]:
        if not self.jobs.exists():
            return []
        return [entry.name for entry in self.jobs.iterdir() if main.JOB_ID_RE.fullmatch(entry.name)]

    def _drain_jobs(self) -> list[str]:
        ids = []
        for number in range(3):
            response = self.client.post("/jobs", json=_job_body(number))
            assert response.status_code == 200
            ids.append(response.json()["job_id"])
        return ids

    # --- the refusal itself ---------------------------------------------------

    def test_a_sender_in_a_loop_is_turned_away_with_flare_613_and_retry_after(self) -> None:
        self._drain_jobs()
        refused = self.client.post("/jobs", json=_job_body(99))

        assert refused.status_code == 429
        assert refused.json()["detail"]["code"] == "FLARE-613"
        assert int(refused.headers["Retry-After"]) >= 1
        assert "retry in" in refused.json()["detail"]["message"]

    def test_a_refused_request_stages_nothing(self) -> None:
        self._drain_jobs()
        before = self._folders()
        self.client.post("/jobs", json=_job_body(99))
        assert self._folders() == before

    def test_the_sender_may_try_again_after_the_wait(self) -> None:
        self._drain_jobs()
        refused = self.client.post("/jobs", json=_job_body(50))
        self.clock.now += int(refused.headers["Retry-After"])
        assert self.client.post("/jobs", json=_job_body(51)).status_code == 200

    def test_a_full_questboard_is_a_different_429_with_no_retry_after(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Different remedy (finish a quest, not wait a few seconds), so a different code."""
        monkeypatch.setattr(main, "MAX_ACTIVE_JOBS", 1)
        assert self.client.post("/jobs", json=_job_body(1)).status_code == 200
        full = self.client.post("/jobs", json=_job_body(2))
        assert full.status_code == 429
        assert full.json()["detail"]["code"] == "FLARE-603"
        assert "Retry-After" not in full.headers

    def test_the_budget_is_charged_before_the_expensive_work(self) -> None:
        """A payload the privacy gate refuses still costs a token: refusing it is work too."""
        bad = {"task": "x", "repository": "t", "files": [{"path": "secrets.json", "content": "{}"}]}
        assert [self.client.post("/jobs", json=bad).status_code for _ in range(3)] == [422, 422, 422]
        assert self.client.post("/jobs", json=bad).status_code == 429

    # --- what must stay open --------------------------------------------------

    def test_a_drained_jobs_budget_does_not_touch_incident_reports(self) -> None:
        self._drain_jobs()
        assert self.client.post("/jobs", json=_job_body(99)).status_code == 429
        assert self.client.post("/incidents", json=_incident_body(1)).status_code == 200

    def test_a_drained_incident_budget_does_not_touch_jobs(self) -> None:
        for index in range(5):
            assert self.client.post("/incidents", json=_incident_body(index)).status_code == 200
        assert self.client.post("/incidents", json=_incident_body(9)).status_code == 429
        assert self.client.post("/jobs", json=_job_body(1)).status_code == 200

    def test_a_human_decision_is_never_rate_limited(self) -> None:
        """
        The point of leaving approve/reject/cancel out: a flood of submissions
        must not be able to starve the one person who has to decide something.
        """
        ids = self._drain_jobs()
        assert self.client.post("/jobs", json=_job_body(99)).status_code == 429

        assert self.client.get("/health").status_code == 200
        assert self.client.get(f"/jobs/{ids[0]}").status_code == 200
        assert self.client.get(f"/jobs/{ids[0]}/reports").status_code == 200
        for action in ("cancel", "approve", "reject"):
            response = self.client.post(f"/jobs/{ids[0]}/{action}", json={"revision": 1})
            assert response.status_code != 429, action

    def test_the_retry_endpoint_shares_the_jobs_budget(self) -> None:
        """It creates a job, so a loop of retries is the same flood."""
        statuses = [self.client.post(f"/jobs/{'a' * 32}/retry").status_code for _ in range(4)]
        assert statuses[:3] != [429, 429, 429]
        assert statuses[3] == 429

    # --- who may spend the budget ---------------------------------------------

    def test_requests_without_a_valid_token_cannot_drain_the_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "limit-test-token")
        for number in range(20):
            assert self.client.post("/jobs", json=_job_body(number)).status_code == 401

        headers = {"Authorization": "Bearer limit-test-token"}
        statuses = [self.client.post("/jobs", json=_job_body(100 + n), headers=headers).status_code for n in range(4)]
        assert statuses == [200, 200, 200, 429], "the real sender still has its full burst"

    # --- switching it off, and seeing it ---------------------------------------

    def test_it_can_be_switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "RATE_LIMITING_ENABLED", False)
        assert all(self.client.post("/jobs", json=_job_body(n)).status_code == 200 for n in range(8))

    def test_health_reports_the_limits_in_force(self) -> None:
        health = self.client.get("/health").json()
        assert health["rate_limiting"] is True
        assert health["rate_limits"] == {
            "incidents": {"burst": 5, "per_minute": 60.0},
            "jobs": {"burst": 3, "per_minute": 60.0},
        }

    def test_the_error_carries_the_wait_in_its_context(self) -> None:
        error = RequestRateLimitedError("slow down", retry_after_seconds=7)
        assert error.code == "FLARE-613"
        assert error.context["retry_after_seconds"] == 7
