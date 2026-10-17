#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Quest Supervisor Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Tests for core/supervisor.py (the plan) and for how the
               orchestrator carries it out.

               The properties worth pinning are the ones that make an
               unattended supervisor safe: it never withdraws a candidate
               nobody was warned about, it never writes to a job's status for
               a reminder (that would invalidate the approval button), it
               re-checks before acting because a person may have decided in
               the meantime, and one bad sweep does not end the loop.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the supervisor itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import healthcheck  # noqa: E402
import main  # noqa: E402
from core import supervisor as sup  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HOUR = 3600.0
POLICY = sup.Policy(remind_seconds=24 * HOUR, expire_seconds=72 * HOUR, notice_seconds=HOUR,
                    orphan_seconds=120, max_resumes=2, hung_seconds=1800)
NOW = 10_000_000.0
EMPTY_MEMORY = {"reminded": {}, "resumes": {}}


def _view(**kwargs: object) -> sup.JobView:
    base: dict = {"job_id": "a" * 32, "status": "awaiting_approval", "status_changed_at": NOW}
    base.update(kwargs)
    return sup.JobView(**base)


def _plan(*views: sup.JobView, now: float = NOW) -> tuple[list[sup.Action], list[sup.Attention]]:
    return sup.plan(list(views), now, POLICY)


def _kinds(actions: list[sup.Action]) -> list[str]:
    return [action.kind for action in actions]


# ==============================================================================
# The plan: approvals
# ==============================================================================
class TestPlanApprovals:
    def test_a_fresh_candidate_is_left_alone_but_shown(self) -> None:
        actions, attention = _plan(_view(status_changed_at=NOW - HOUR))
        assert actions == []
        assert [(a.kind, a.waited_seconds) for a in attention] == [(sup.ATTENTION_AWAITING, HOUR)]
        assert attention[0].expires_in_seconds == 71 * HOUR

    def test_reminds_once_the_remind_age_is_reached(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 24 * HOUR))
        assert [(a.kind, a.reason) for a in actions] == [(sup.ACTION_REMIND, "approval_unanswered")]

    def test_just_below_the_remind_age_does_nothing(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 24 * HOUR + 1))
        assert actions == []

    def test_does_not_remind_again_before_the_interval(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 30 * HOUR, reminded_at=NOW - 6 * HOUR))
        assert actions == []

    def test_reminds_again_after_the_interval(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 60 * HOUR, reminded_at=NOW - 24 * HOUR))
        assert _kinds(actions) == [sup.ACTION_REMIND]

    def test_never_withdraws_without_a_reminder_first(self) -> None:
        # Flare was down for a week: everything is far past its limit on the first sweep.
        actions, _ = _plan(_view(status_changed_at=NOW - 7 * 24 * HOUR))
        assert [(a.kind, a.reason) for a in actions] == [(sup.ACTION_REMIND, "notice_before_withdrawal")]

    def test_waits_out_the_notice_period(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 80 * HOUR, reminded_at=NOW - HOUR + 1))
        assert actions == []

    def test_withdraws_after_the_notice_period(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 80 * HOUR, reminded_at=NOW - HOUR))
        assert [(a.kind, a.reason) for a in actions] == [(sup.ACTION_EXPIRE, "approval_wait_exceeded")]

    def test_expiry_boundary_is_inclusive(self) -> None:
        below, _ = _plan(_view(status_changed_at=NOW - 72 * HOUR + 1, reminded_at=NOW - 5 * HOUR))
        at, _ = _plan(_view(status_changed_at=NOW - 72 * HOUR, reminded_at=NOW - 5 * HOUR))
        assert below == []
        assert _kinds(at) == [sup.ACTION_EXPIRE]

    def test_unknown_start_time_is_never_acted_on(self) -> None:
        actions, attention = _plan(_view(status_changed_at=None, reminded_at=0.0))
        assert actions == []
        assert attention[0].waited_seconds is None

    def test_a_clock_stepping_backwards_never_causes_an_action(self) -> None:
        actions, attention = _plan(_view(status_changed_at=NOW + 10 * HOUR))
        assert actions == []
        assert attention[0].waited_seconds == 0.0


# ==============================================================================
# The plan: executing quests
# ==============================================================================
class TestPlanExecuting:
    def _executing(self, **kwargs: object) -> sup.JobView:
        base: dict = {"status": "patching", "status_changed_at": NOW - 600, "heartbeat_at": NOW - 600}
        base.update(kwargs)
        return _view(**base)

    def test_a_running_thread_is_left_alone(self) -> None:
        actions, attention = _plan(self._executing(thread_alive=True, heartbeat_at=NOW - 10))
        assert actions == [] and attention == []

    def test_a_silent_but_live_thread_is_reported_never_acted_on(self) -> None:
        actions, attention = _plan(self._executing(thread_alive=True, heartbeat_at=NOW - 1800))
        assert actions == []
        assert [a.kind for a in attention] == [sup.ATTENTION_HUNG]

    def test_a_young_quest_without_thread_gets_the_benefit_of_the_doubt(self) -> None:
        actions, attention = _plan(self._executing(heartbeat_at=NOW - 119))
        assert actions == [] and attention == []

    def test_an_orphan_is_resumed(self) -> None:
        actions, attention = _plan(self._executing(heartbeat_at=NOW - 120))
        assert [(a.kind, a.reason) for a in actions] == [(sup.ACTION_RESUME, "thread_missing")]
        assert [a.kind for a in attention] == [sup.ATTENTION_ORPHANED]

    def test_resumes_are_capped_then_the_quest_is_failed(self) -> None:
        last, _ = _plan(self._executing(resumes=1))
        spent, _ = _plan(self._executing(resumes=2))
        assert _kinds(last) == [sup.ACTION_RESUME]
        assert [(a.kind, a.reason) for a in spent] == [(sup.ACTION_FAIL, "resumes_exhausted")]

    def test_missing_heartbeat_falls_back_to_the_status_change(self) -> None:
        actions, _ = _plan(self._executing(heartbeat_at=None, status_changed_at=NOW - 500))
        assert _kinds(actions) == [sup.ACTION_RESUME]

    @pytest.mark.parametrize("status", ["completed", "failed", "rolled_back", "nonsense"])
    def test_finished_or_unknown_statuses_are_ignored(self, status: str) -> None:
        actions, attention = _plan(_view(status=status, status_changed_at=NOW - 100 * HOUR))
        assert actions == [] and attention == []

    def test_awaiting_approval_is_never_treated_as_an_orphan(self) -> None:
        actions, _ = _plan(_view(status_changed_at=NOW - 5, heartbeat_at=NOW - 10_000))
        assert actions == []

    def test_plan_is_deterministic_and_ordered_by_job_id(self) -> None:
        views = [self._executing(job_id=c * 32, heartbeat_at=NOW - 500) for c in "cab"]
        first = sup.plan(views, NOW, POLICY)
        second = sup.plan(list(reversed(views)), NOW, POLICY)
        assert first == second
        assert [a.job_id for a in first[0]] == ["a" * 32, "b" * 32, "c" * 32]


# ==============================================================================
# The orchestrator carrying the plan out
# ==============================================================================
class Board:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.started: list[str] = []
        monkeypatch.setattr(main, "start_job_thread", lambda job_id: self.started.append(job_id) or True)

    @staticmethod
    def _request() -> "main.CreateJobRequest":
        return main.CreateJobRequest(task="Fix it", files=[main.JobFile(path="demo.py", content="x = 1\n")])

    def awaiting(self, waited: float = 0.0) -> tuple[str, dict]:
        job_id = main.stage_job(self._request())
        for step in ("analysing", "patching", "testing"):
            main.write_status(job_id, step)
        status = main.write_status(job_id, "awaiting_approval", result={"files": []}, approval_required=True)
        self.age(job_id, changed=waited)
        return job_id, status

    def executing(self, silent: float = 0.0, status: str = "patching") -> str:
        job_id = main.stage_job(self._request())
        main.write_status(job_id, "analysing")
        if status != "analysing":
            main.write_status(job_id, status)
        self.age(job_id, changed=silent, heartbeat=silent)
        return job_id

    @staticmethod
    def age(job_id: str, *, changed: float | None = None, heartbeat: float | None = None) -> None:
        """Pretend the status changed / the last heartbeat happened this many seconds ago."""
        path = main.status_path(job_id)
        doc = main.read_json(path)
        now = datetime.now(UTC)
        if changed is not None:
            doc["status_changed_at"] = (now - timedelta(seconds=changed)).isoformat()
        if heartbeat is not None:
            doc["heartbeat_at"] = (now - timedelta(seconds=heartbeat)).isoformat()
        main.write_json(path, doc)


@pytest.fixture
def board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Board:
    monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
    monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(main, "SUPERVISOR_POLICY", POLICY)
    monkeypatch.setattr(main, "SUPERVISOR_STATE", main._new_supervisor_state())
    monkeypatch.setattr(main, "SUPERVISOR_THREAD", None)
    return Board(monkeypatch)


class TestSweepApprovals:
    def test_a_reminder_does_not_touch_the_job_status(self, board: Board) -> None:
        job_id, awaiting = board.awaiting(waited=30 * HOUR)
        before = main.status_path(job_id).read_bytes()

        result = main.supervisor_sweep()

        assert result["executed"] == 1
        assert main.status_path(job_id).read_bytes() == before
        assert main.read_status(job_id)["revision"] == awaiting["revision"]
        event = main.get_supervisor()["events"][-1]
        assert (event["kind"], event["job_id"], event["executed"]) == (sup.ACTION_REMIND, job_id, True)

    def test_the_approval_button_still_works_after_a_reminder(self, board: Board) -> None:
        job_id, awaiting = board.awaiting(waited=30 * HOUR)
        main.supervisor_sweep()

        approved = main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))

        assert approved["status"] == "applying"

    def test_a_reminder_is_not_repeated_on_the_next_sweep(self, board: Board) -> None:
        board.awaiting(waited=30 * HOUR)
        first = main.supervisor_sweep()
        second = main.supervisor_sweep()
        assert (first["executed"], second["executed"]) == (1, 0)

    def test_reminder_memory_survives_a_restart(self, board: Board, monkeypatch: pytest.MonkeyPatch) -> None:
        board.awaiting(waited=30 * HOUR)
        main.supervisor_sweep()
        monkeypatch.setattr(main, "SUPERVISOR_STATE", main._new_supervisor_state())  # a fresh process
        assert main.supervisor_sweep()["executed"] == 0

    def test_withdrawal_needs_a_reminder_and_then_the_notice_period(self, board: Board) -> None:
        job_id, _ = board.awaiting(waited=80 * HOUR)

        main.supervisor_sweep()
        assert main.read_status(job_id)["status"] == "awaiting_approval"  # only warned

        main.supervisor_sweep(now=time.time() + HOUR - 5)
        assert main.read_status(job_id)["status"] == "awaiting_approval"  # notice not over

        main.supervisor_sweep(now=time.time() + HOUR + 5)
        final = main.read_status(job_id)
        assert final["status"] == "rolled_back"
        assert final["error_code"] == "FLARE-614"
        assert final["outcome"] == "approval_expired"
        assert final["waited_seconds"] >= 72 * 3600
        assert final["result"]["files"] == [{"path": "demo.py", "content": "x = 1\n"}]

    def test_withdrawal_frees_the_slot_that_blocked_new_work(
        self, board: Board, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "MAX_ACTIVE_JOBS", 1)
        monkeypatch.setattr(main, "DEDUPE_WINDOW_SECONDS", 0)
        job_id, _ = board.awaiting(waited=80 * HOUR)
        client = TestClient(main.app)
        body = {"task": "Another", "files": [{"path": "other.py", "content": "y = 2\n"}]}
        assert client.post("/jobs", json=body).status_code == 429

        main.supervisor_sweep()
        main.supervisor_sweep(now=time.time() + HOUR + 5)

        assert main.read_status(job_id)["status"] == "rolled_back"
        assert client.post("/jobs", json=body).status_code < 300

    def test_a_person_deciding_in_the_meantime_wins_the_race(self, board: Board) -> None:
        job_id, awaiting = board.awaiting(waited=80 * HOUR)
        stale_plan = sup.Action(sup.ACTION_EXPIRE, job_id, "approval_wait_exceeded", 80 * HOUR)
        main.approve_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))

        executed = main._supervisor_execute(stale_plan, {"reminded": {}, "resumes": {}}, time.time())

        assert executed is False
        assert main.read_status(job_id)["status"] == "applying"

    def test_an_expiry_planned_on_old_numbers_is_rechecked(self, board: Board) -> None:
        job_id, _ = board.awaiting(waited=HOUR)  # actually young
        stale_plan = sup.Action(sup.ACTION_EXPIRE, job_id, "approval_wait_exceeded", 80 * HOUR)

        assert main._supervisor_execute(stale_plan, {"reminded": {}, "resumes": {}}, time.time()) is False
        assert main.read_status(job_id)["status"] == "awaiting_approval"


    def test_an_expiry_never_touches_a_quest_that_is_not_awaiting_approval(self, board: Board) -> None:
        job_id = board.executing(silent=80 * HOUR)  # old enough, but it is working, not waiting
        stale_plan = sup.Action(sup.ACTION_EXPIRE, job_id, "approval_wait_exceeded", 80 * HOUR)

        assert main._supervisor_execute(stale_plan, {"reminded": {}, "resumes": {}}, time.time()) is False
        assert main.read_status(job_id)["status"] == "patching"

    def test_the_withdrawal_is_forgotten_by_the_memory(self, board: Board) -> None:
        board.awaiting(waited=80 * HOUR)
        main.supervisor_sweep()
        main.supervisor_sweep(now=time.time() + HOUR + 5)
        assert main._load_supervisor_memory()["reminded"] == {}


class TestSweepOrphans:
    def test_a_resume_planned_for_a_job_that_got_a_thread_meanwhile_is_dropped(self, board: Board) -> None:
        job_id = board.executing(silent=600)
        stale_plan = sup.Action(sup.ACTION_RESUME, job_id, "thread_missing", 600)
        memory = {"reminded": {}, "resumes": {}}
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.add(job_id)
        try:
            assert main._supervisor_execute(stale_plan, memory, time.time()) is False
        finally:
            with main.ACTIVE_JOBS_LOCK:
                main.ACTIVE_JOBS.discard(job_id)
        assert board.started == [] and memory["resumes"] == {}

    def test_resume_counts_leave_the_memory_with_the_job(self, board: Board) -> None:
        job_id = board.executing(silent=600)
        main.supervisor_sweep()
        assert main._load_supervisor_memory()["resumes"] == {job_id: 1}
        main.write_status(job_id, "failed", error_code="FLARE-800")
        main.supervisor_sweep()
        assert main._load_supervisor_memory()["resumes"] == {}

    def test_an_orphan_is_resumed_and_counted(self, board: Board) -> None:
        job_id = board.executing(silent=600)

        main.supervisor_sweep()

        assert board.started == [job_id]
        assert main._load_supervisor_memory()["resumes"] == {job_id: 1}

    def test_a_job_with_a_live_thread_is_not_resumed(self, board: Board) -> None:
        job_id = board.executing(silent=600)
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.add(job_id)
        try:
            main.supervisor_sweep()
        finally:
            with main.ACTIVE_JOBS_LOCK:
                main.ACTIVE_JOBS.discard(job_id)
        assert board.started == []

    def test_a_quest_that_keeps_dying_is_rolled_back_with_the_recovery_code(self, board: Board) -> None:
        job_id = board.executing(silent=600)

        for _ in range(POLICY.max_resumes):
            main.supervisor_sweep()
        assert main.read_status(job_id)["status"] == "patching"
        main.supervisor_sweep()

        final = main.read_status(job_id)
        assert len(board.started) == POLICY.max_resumes
        assert final["status"] == "rolled_back"
        assert final["error_code"] == "FLARE-800"
        assert final["outcome"] == "orphaned"

    def test_a_young_quest_is_not_touched(self, board: Board) -> None:
        board.executing(silent=5)
        assert main.supervisor_sweep()["planned"] == 0

    def test_a_hung_but_alive_job_shows_on_the_board_and_is_not_touched(self, board: Board) -> None:
        job_id = board.executing(silent=5000)
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.add(job_id)
        try:
            result = main.supervisor_sweep()
        finally:
            with main.ACTIVE_JOBS_LOCK:
                main.ACTIVE_JOBS.discard(job_id)
        assert result["planned"] == 0
        assert main.get_supervisor()["board"][0]["attention"] == sup.ATTENTION_HUNG
        assert main.read_status(job_id)["status"] == "patching"


class TestSweepRobustness:
    def test_finished_jobs_leave_the_memory(self, board: Board) -> None:
        job_id, awaiting = board.awaiting(waited=30 * HOUR)
        main.supervisor_sweep()
        assert job_id in main._load_supervisor_memory()["reminded"]

        main.reject_job(job_id, main.JobDecisionRequest(revision=awaiting["revision"]))
        main.supervisor_sweep()

        assert main._load_supervisor_memory()["reminded"] == {}

    def test_the_memory_folder_is_not_mistaken_for_a_job(self, board: Board) -> None:
        board.awaiting(waited=30 * HOUR)
        main.supervisor_sweep()
        assert main._supervisor_memory_path().exists()
        assert main.stale_active_job_count() == 0
        assert main.recover_incomplete_jobs() == 0
        assert main.supervisor_sweep()["open_quests"] == 1

    def test_unreadable_memory_starts_empty_and_the_sweep_still_works(self, board: Board) -> None:
        board.awaiting(waited=30 * HOUR)
        main.supervisor_sweep()
        main._supervisor_memory_path().write_bytes(b"{ not json")

        assert main._load_supervisor_memory() == EMPTY_MEMORY
        assert main.supervisor_sweep()["executed"] == 1  # reminded again: nothing lost but a repeat

    def test_one_quest_that_cannot_be_handled_does_not_stop_the_others(
        self, board: Board, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = board.executing(silent=600)
        second = board.executing(silent=600)
        broken = min(first, second)

        def flaky(job_id: str) -> bool:
            if job_id == broken:
                raise OSError("no threads left")
            board.started.append(job_id)
            return True

        monkeypatch.setattr(main, "start_job_thread", flaky)
        result = main.supervisor_sweep()

        assert result["failed"] == 1
        assert board.started == [max(first, second)]
        assert main.get_supervisor()["errors"] == 1

    def test_the_loop_survives_a_failing_sweep(self, board: Board, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def explode() -> dict:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return {}

        monkeypatch.setattr(main, "supervisor_sweep", explode)
        monkeypatch.setattr(main, "SUPERVISOR_ENABLED", True)
        monkeypatch.setattr(main, "SUPERVISOR_INTERVAL_SECONDS", 0.01)
        assert main.start_supervisor() is True
        try:
            deadline = time.time() + 5
            while len(calls) < 3 and time.time() < deadline:
                time.sleep(0.01)
        finally:
            main.stop_supervisor()

        assert len(calls) >= 3
        assert main.SUPERVISOR_STATE["errors"] == 1
        assert not main.SUPERVISOR_THREAD.is_alive()

    def test_start_is_idempotent_and_disabled_means_no_thread(
        self, board: Board, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert main.start_supervisor() is False  # disabled by the test default
        assert main.SUPERVISOR_THREAD is None
        monkeypatch.setattr(main, "SUPERVISOR_ENABLED", True)
        monkeypatch.setattr(main, "SUPERVISOR_INTERVAL_SECONDS", 3600)
        assert main.start_supervisor() is True
        try:
            assert main.start_supervisor() is False
            assert sum(t.name == "flare-supervisor" for t in threading.enumerate()) == 1
        finally:
            main.stop_supervisor()


class TestLiveness:
    def test_not_stalled_when_disabled_or_never_started(self, board: Board) -> None:
        assert main.supervisor_status()["stalled"] is False

    def test_a_dead_thread_is_stalled(self, board: Board, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "SUPERVISOR_ENABLED", True)
        main.SUPERVISOR_STATE["started_at"] = time.time()
        status = main.supervisor_status()
        assert (status["running"], status["stalled"]) == (False, True)

    def test_a_sweep_that_stopped_finishing_is_stalled(
        self, board: Board, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "SUPERVISOR_ENABLED", True)
        monkeypatch.setattr(main, "SUPERVISOR_INTERVAL_SECONDS", 60)
        stop = threading.Event()
        thread = threading.Thread(target=stop.wait, daemon=True)
        thread.start()
        monkeypatch.setattr(main, "SUPERVISOR_THREAD", thread)
        try:
            main.SUPERVISOR_STATE["started_at"] = time.time() - 1000
            main.SUPERVISOR_STATE["last_sweep_finished_at"] = time.time() - 170
            assert main.supervisor_status()["stalled"] is False
            main.SUPERVISOR_STATE["last_sweep_finished_at"] = time.time() - 190
            assert main.supervisor_status()["stalled"] is True
        finally:
            stop.set()


class TestEndpoints:
    def test_health_carries_the_supervisor_block(self, board: Board) -> None:
        block = TestClient(main.app).get("/health").json()["supervisor"]
        assert {"enabled", "running", "stalled", "sweeps", "errors", "open_quests"} <= set(block)

    def test_supervisor_endpoint_requires_the_token(self, board: Board, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = "t" + "oken-for-tests"
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", secret)
        client = TestClient(main.app)
        assert client.get("/supervisor").status_code == 401
        assert client.get("/supervisor", headers={"Authorization": "Bearer " + secret}).status_code == 200

    def test_board_lists_waiting_candidates_with_time_left(self, board: Board) -> None:
        job_id, _ = board.awaiting(waited=10 * HOUR)
        main.supervisor_sweep()
        body = TestClient(main.app).get("/supervisor").json()
        entry = body["board"][0]
        assert entry["job_id"] == job_id and entry["attention"] == sup.ATTENTION_AWAITING
        assert 62 * 3600 - 60 <= entry["expires_in_seconds"] <= 62 * 3600
        assert body["policy"]["approval_expire_seconds"] == 72 * 3600

    def test_event_log_is_bounded(self, board: Board) -> None:
        action = sup.Action(sup.ACTION_REMIND, "a" * 32, "approval_unanswered", 1.0)
        for _ in range(main.SUPERVISOR_EVENT_LIMIT + 25):
            main._supervisor_record(action, executed=True)
        assert len(main.get_supervisor()["events"]) == main.SUPERVISOR_EVENT_LIMIT


class TestConfiguration:
    def test_remind_must_come_before_expiry(self) -> None:
        code = "import sys; sys.path[:0] = [%r, %r]; import main" % (
            str(_MODULE_ROOT), str(_MODULE_ROOT / "orchestrator" / "app"))
        env = dict(os.environ, SUPERVISOR_APPROVAL_REMIND_SECONDS="100", SUPERVISOR_APPROVAL_EXPIRE_SECONDS="50")
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode != 0
        assert "SUPERVISOR_APPROVAL_REMIND_SECONDS" in result.stderr


class TestHealthProbe:
    def test_healthy(self) -> None:
        document = {"ok": True, "supervisor": {"enabled": True, "stalled": False}}
        assert healthcheck.evaluate(document) == (True, "ok")

    def test_a_stalled_supervisor_makes_the_container_unhealthy(self) -> None:
        healthy, reason = healthcheck.evaluate({"ok": True, "supervisor": {"enabled": True, "stalled": True}})
        assert healthy is False and "stalled" in reason

    def test_a_disabled_supervisor_is_not_a_failure(self) -> None:
        assert healthcheck.evaluate({"ok": True, "supervisor": {"enabled": False, "stalled": True}})[0] is True

    @pytest.mark.parametrize("document", [None, [], "ok", {}, {"ok": False, "supervisor": {}}, {"ok": True}])
    def test_malformed_or_failing_documents_are_unhealthy(self, document: object) -> None:
        assert healthcheck.evaluate(document)[0] is False

    @pytest.mark.parametrize(("stalled", "expected"), [(False, 0), (True, 1)])
    def test_exit_code_follows_the_served_document(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, stalled: bool, expected: int
    ) -> None:
        body = json.dumps({"ok": True, "supervisor": {"enabled": True, "stalled": stalled}}).encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.setenv("HEALTHCHECK_URL", f"http://127.0.0.1:{server.server_port}/health")
            assert healthcheck.main() == expected
        finally:
            server.shutdown()
            server.server_close()
        assert ("stalled" in capsys.readouterr().err) is stalled

    def test_unreachable_endpoint_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setenv("HEALTHCHECK_URL", "http://127.0.0.1:1/health")
        assert healthcheck.main() == 1
        assert "unhealthy" in capsys.readouterr().err
