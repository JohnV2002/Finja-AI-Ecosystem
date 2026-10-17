#!/usr/bin/env python3
"""
======================================================================
      Flare (Finja Agentic Code) – Incident Routing Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Tests for core/incident_routing.py and POST /incidents.

               Every routing rule is a claim about what Flare does with an
               error, so the rules are pinned one by one, including the
               ones that decide what must NOT happen: a provider timeout
               must not open a quest, and a catch-all code must not be
               "repaired" as if it were a defect.

  Needs neither Docker nor OpenRouter.

  New in v1.11.0:
    • First version, alongside the routing layer itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_MODULE_ROOT = Path(__file__).parent
sys.path.insert(0, str(_MODULE_ROOT))
sys.path.insert(0, str(_MODULE_ROOT / "orchestrator" / "app"))

import main  # noqa: E402
from core import incident_routing as routing  # noqa: E402
from core.exceptions import JobPersistenceError  # noqa: E402
from core.incident_envelope import validate_incident_envelope  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

NOW = datetime(2026, 10, 17, 16, 0, 0, tzinfo=UTC).timestamp()
AWS_LIKE = "AKIA" + "ABCDEFGHIJKLMNOP"


def _stamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _incident_id(index: int) -> str:
    # The last UUID group is 12 hex digits; 10 fixed ones plus a 2-digit counter.
    return f"123e4567-e89b-42d3-a456-4266141740{index:02d}"


def _envelope(*, code: str | None = "FINJA-999", kind: str = "TimeoutError",
              component: str = "finja-chat", at: float = NOW, index: int = 0,
              mode: str = "standard", path: str = "demo.py", symbol: str | None = "run",
              line: int = 1, frames: bool = True, content: str = "x = 1\n") -> dict:
    return {
        "envelope_version": 1,
        "incident_id": _incident_id(index),
        "observed_at": _stamp(at),
        "origin": "finja",
        "component": component,
        "repository": "finja-neural-network",
        "mode": mode,
        "error_kind": kind,
        "error_code": code,
        "summary": "A pipeline stage failed.",
        "frames": [{"path": path, "line": line, "symbol": symbol}] if frames else [],
        "files": [{"path": path, "content": content,
                   "sha256": hashlib.sha256(content.encode()).hexdigest()}],
        "redaction": {"policy": "finja-flare-redaction-v1",
                      "source_minimized": True, "sensitive_values_removed": True},
    }


class _Store:
    """In-memory stand-in for the ledger file; round-trips through JSON like the real one."""

    def __init__(self) -> None:
        self.state = None

    def load(self):
        return None if self.state is None else json.loads(json.dumps(self.state))

    def save(self, payload: dict) -> None:
        self.state = json.loads(json.dumps(payload))


def _ledger(store: _Store | None = None, **kwargs) -> routing.IncidentLedger:
    store = store or _Store()
    kwargs.setdefault("clock", lambda: NOW)
    return routing.IncidentLedger(store.load, store.save, **kwargs)


def _route(env: dict, ledger: routing.IncidentLedger, **kwargs) -> dict:
    return routing.route(validate_incident_envelope(env), ledger, **kwargs)


def _kinds(decision: dict) -> list[str]:
    return [reason["kind"] for reason in decision["reasons"]]


# ==============================================================================
# Category comes from the code number
# ==============================================================================

class TestCategories:

    @pytest.mark.parametrize("code,expected", [
        ("FINJA-99", None), ("FINJA-100", "config"), ("FINJA-199", "config"),
        ("FINJA-200", "llm"), ("FINJA-299", "llm"), ("FINJA-300", "memory"),
        ("FINJA-400", "session"), ("FINJA-500", "tool"), ("FINJA-600", "pipeline"),
        ("FINJA-700", None), ("FINJA-800", "host"), ("FINJA-899", "host"),
        ("FINJA-900", "unexpected"), ("FINJA-999", "unexpected"),
        ("FINJA-1000", "privacy"), ("FINJA-1100", "injection"),
        ("FINJA-1199", "injection"), ("FINJA-1200", None),
        (None, None), ("", None), ("NOPE", None), ("FINJA-abc", None),
        ("FLARE-501", "tool"), ("OMNI-999", "unexpected"),
    ])
    def test_code_number_decides_the_band(self, code: str | None, expected: str | None) -> None:
        assert routing.category_for(code) == expected

    def test_the_mirrored_table_matches_the_public_legend(self) -> None:
        """
        The container cannot read the root legend, so the ranges are mirrored.
        This is the only thing that stops the mirror from going stale.
        """
        legend_path = _MODULE_ROOT.parent / "error_contract.json"
        if not legend_path.exists():
            pytest.skip("root error legend is not part of this checkout")
        legend = json.loads(legend_path.read_text(encoding="utf-8"))
        mirrored = {name: (low, high) for name, low, high in routing.CATEGORY_RANGES}
        for namespace, info in legend["namespaces"].items():
            published = {}
            for name, category in info.get("categories", {}).items():
                low, high = category["range"].split("-")
                published[name] = (int(low), int(high))
            assert published == mirrored, f"{namespace} ranges differ from the mirrored table"


class TestTransientKinds:

    @pytest.mark.parametrize("kind", [
        "TimeoutError", "asyncio.TimeoutError", "httpx.ReadTimeout", "ConnectionResetError",
        "socket.timeout", "RateLimitError", "aiohttp.ServerDisconnectedError",
    ])
    def test_transient(self, kind: str) -> None:
        assert routing.is_transient_kind(kind) is True

    @pytest.mark.parametrize("kind", [
        "KeyError", "ValueError", "SyntaxError", "AttributeError",
        "TimeoutErrorHandler", "MyTimeoutErrors",
    ])
    def test_not_transient(self, kind: str) -> None:
        assert routing.is_transient_kind(kind) is False


# ==============================================================================
# Fingerprint
# ==============================================================================

class TestFingerprint:

    def _fp(self, **kwargs) -> str:
        return routing.fingerprint_of(validate_incident_envelope(_envelope(**kwargs)))[0]

    def test_a_moved_line_is_the_same_defect(self) -> None:
        """Editing a file shifts line numbers; a fix attempt must not make the error look new."""
        assert self._fp(line=3) == self._fp(line=300)

    @pytest.mark.parametrize("change", [
        {"component": "finja-music"}, {"code": "FINJA-210"}, {"kind": "KeyError"},
        {"path": "other.py"}, {"symbol": "other_function"},
    ])
    def test_a_different_defect_is_a_different_fingerprint(self, change: dict) -> None:
        assert self._fp(**change) != self._fp()

    def test_the_incident_id_is_not_part_of_it(self) -> None:
        assert self._fp(index=1) == self._fp(index=2)

    def test_without_frames_the_first_file_decides(self) -> None:
        assert self._fp(frames=False, path="a.py") != self._fp(frames=False, path="b.py")

    def test_it_is_short_and_hex(self) -> None:
        assert len(self._fp()) == 16
        int(self._fp(), 16)


# ==============================================================================
# The ledger
# ==============================================================================

class TestLedger:

    def _observe(self, ledger, at: float, index: int = 0) -> dict:
        envelope = validate_incident_envelope(_envelope(at=at, index=index))
        fingerprint, identity = routing.fingerprint_of(envelope)
        return ledger.observe(fingerprint, identity, incident_id=envelope.incident_id,
                              observed_at=envelope.observed_at)

    def test_sightings_inside_the_window_are_counted(self) -> None:
        ledger = _ledger()
        self._observe(ledger, NOW - 1200, 1)
        self._observe(ledger, NOW - 600, 2)
        assert self._observe(ledger, NOW, 3)["episodes_in_window"] == 3

    def test_old_sightings_fall_out_of_the_window_but_stay_in_the_total(self) -> None:
        ledger = _ledger(window_seconds=3600)
        self._observe(ledger, NOW - 7200, 1)
        self._observe(ledger, NOW - 5400, 2)
        seen = self._observe(ledger, NOW, 3)
        assert seen["episodes_in_window"] == 1
        assert seen["total"] == 3

    def test_replaying_the_same_observation_counts_once(self) -> None:
        ledger = _ledger()
        self._observe(ledger, NOW, 1)
        replay = self._observe(ledger, NOW, 1)
        assert replay["duplicate"] is True
        assert replay["total"] == 1
        assert replay["episodes_in_window"] == 1

    def test_the_same_incident_at_another_time_is_a_new_sighting(self) -> None:
        ledger = _ledger()
        self._observe(ledger, NOW - 60, 1)
        assert self._observe(ledger, NOW, 1)["total"] == 2

    def test_a_far_future_timestamp_cannot_poison_the_window(self) -> None:
        ledger = _ledger()
        seen = self._observe(ledger, NOW + 10 * 86400, 1)
        assert seen["last_seen_at"] == _stamp(NOW + routing.FUTURE_SKEW_SECONDS)

    def test_the_replay_memory_is_bounded_but_the_total_is_not(self) -> None:
        store = _Store()
        ledger = _ledger(store, max_replay_keys=5)
        for index in range(8):
            self._observe(ledger, NOW - 60 + index, index)
        record = next(iter(store.state["records"].values()))
        assert len(record["seen_keys"]) == 5
        assert record["total"] == 8

    def test_the_ledger_is_bounded_and_evicts_the_least_recently_seen(self) -> None:
        store = _Store()
        ledger = _ledger(store, max_fingerprints=3)
        for index, component in enumerate(["a", "b", "c", "d"]):
            envelope = validate_incident_envelope(_envelope(component=component, at=NOW - 100 + index, index=index))
            fingerprint, identity = routing.fingerprint_of(envelope)
            ledger.observe(fingerprint, identity, incident_id=envelope.incident_id,
                           observed_at=envelope.observed_at)
        components = {record["component"] for record in store.state["records"].values()}
        assert components == {"b", "c", "d"}

    def test_a_record_tracking_an_open_quest_is_never_evicted(self) -> None:
        store = _Store()
        ledger = _ledger(store, max_fingerprints=2)
        first = validate_incident_envelope(_envelope(component="a", at=NOW - 500, index=1))
        fp, identity = routing.fingerprint_of(first)
        ledger.observe(fp, identity, incident_id=first.incident_id, observed_at=first.observed_at)
        ledger.attach_quest(fp, "a" * 32)
        for index, component in enumerate(["b", "c", "d"], start=2):
            env = validate_incident_envelope(_envelope(component=component, at=NOW - 100 + index, index=index))
            fingerprint, ident = routing.fingerprint_of(env)
            ledger.observe(fingerprint, ident, incident_id=env.incident_id, observed_at=env.observed_at)
        assert fp in store.state["records"]

    def test_state_survives_a_new_ledger_instance(self) -> None:
        store = _Store()
        self._observe(_ledger(store), NOW - 60, 1)
        assert self._observe(_ledger(store), NOW, 2)["episodes_in_window"] == 2

    @pytest.mark.parametrize("state", [
        "garbage", ["list"], {"ledger_version": 99, "records": {}},
        {"ledger_version": routing.LEDGER_VERSION, "records": "no"},
    ])
    def test_an_unreadable_ledger_fails_closed_as_flare_801(self, state) -> None:
        store = _Store()
        store.state = state
        with pytest.raises(JobPersistenceError) as excinfo:
            self._observe(_ledger(store), NOW, 1)
        assert excinfo.value.code == "FLARE-801"

    def test_attaching_and_fixing_an_unknown_error_is_refused_quietly(self) -> None:
        ledger = _ledger()
        assert ledger.attach_quest("deadbeefdeadbeef", "a" * 32) is False
        assert ledger.record_fix("deadbeefdeadbeef") is False

    def test_a_recorded_fix_splits_before_from_after(self) -> None:
        ledger = _ledger()
        seen = self._observe(ledger, NOW - 600, 1)
        ledger.attach_quest(seen["fingerprint"], "b" * 32)
        assert ledger.record_fix(seen["fingerprint"], completed_at=NOW - 300) is True

        after = self._observe(ledger, NOW, 2)
        assert after["observed_after_fix"] is True
        assert after["fix_attempts"] == 1
        assert after["open_job_id"] is None, "a landed fix closes the quest link"


# ==============================================================================
# The routing rules
# ==============================================================================

class TestRouting:

    def test_the_catch_all_timeout_is_observed_twice_then_classified(self) -> None:
        """The case this layer exists for: FINJA-999 wrapping a TimeoutError."""
        ledger = _ledger()
        first = _route(_envelope(at=NOW - 1200, index=1), ledger)
        second = _route(_envelope(at=NOW - 600, index=2), ledger)
        third = _route(_envelope(at=NOW, index=3), ledger)

        assert first["route"] == second["route"] == "observe"
        assert third["route"] == "classify"
        assert "recurring" in _kinds(third)
        assert "catch_all_code" in _kinds(third)

    def test_a_deterministic_error_under_the_catch_all_is_classified_at_once(self) -> None:
        decision = _route(_envelope(kind="KeyError"), _ledger())
        assert decision["route"] == "classify"
        assert decision["category"] == "unexpected"
        assert decision["transient_kind"] is False

    def test_the_catch_all_is_never_routed_as_a_plain_repair(self) -> None:
        for kind in ("KeyError", "ValueError", "AttributeError"):
            assert _route(_envelope(kind=kind, component=kind), _ledger())["route"] != "repair"

    def test_a_provider_timeout_opens_nothing_until_it_recurs(self) -> None:
        ledger = _ledger()
        routes = [_route(_envelope(code="FINJA-210", at=NOW - 600 + i * 120, index=i), ledger)["route"]
                  for i in range(3)]
        assert routes == ["observe", "observe", "repair"]

    def test_external_categories_are_gated_even_for_a_non_transient_kind(self) -> None:
        """llm and tool failures usually start outside the code, whatever they are called."""
        assert _route(_envelope(code="FINJA-210", kind="ValueError"), _ledger())["route"] == "observe"
        assert _route(_envelope(code="FINJA-510", kind="KeyError"), _ledger())["route"] == "observe"

    def test_a_syntax_error_is_repaired_at_once(self) -> None:
        decision = _route(_envelope(code=None, kind="SyntaxError"), _ledger())
        assert decision["route"] == "repair"
        assert decision["category"] is None
        assert decision["category_source"] is None

    def test_a_transient_kind_without_a_code_still_waits_for_recurrence(self) -> None:
        ledger = _ledger()
        assert _route(_envelope(code=None, kind="ConnectionResetError", index=1, at=NOW - 240), ledger)["route"] == "observe"
        assert _route(_envelope(code=None, kind="ConnectionResetError", index=2, at=NOW - 120), ledger)["route"] == "observe"
        assert _route(_envelope(code=None, kind="ConnectionResetError", index=3, at=NOW), ledger)["route"] == "repair"

    def test_a_code_outside_every_band_is_treated_as_unclassified_repair(self) -> None:
        decision = _route(_envelope(code="FINJA-700", kind="KeyError"), _ledger())
        assert decision["route"] == "repair"
        assert decision["category"] is None

    @pytest.mark.parametrize("code,category", [
        ("FINJA-310", "memory"), ("FINJA-410", "session"), ("FINJA-610", "pipeline"),
        ("FINJA-1010", "privacy"), ("FINJA-1110", "injection"),
    ])
    def test_sensitive_areas_are_never_touched_automatically(self, code: str, category: str) -> None:
        decision = _route(_envelope(code=code, kind="KeyError"), _ledger())
        assert decision["route"] == "manual"
        assert decision["category"] == category
        assert _kinds(decision) == ["sensitive_area"]

    @pytest.mark.parametrize("code", ["FINJA-110", "FINJA-810"])
    def test_environment_conditions_are_not_source_defects(self, code: str) -> None:
        decision = _route(_envelope(code=code, kind="KeyError"), _ledger())
        assert decision["route"] == "operator"
        assert _kinds(decision) == ["not_a_source_defect"]

    def test_a_human_request_outranks_every_other_rule(self) -> None:
        for code in ("FINJA-110", "FINJA-210", "FINJA-999", None):
            decision = _route(_envelope(code=code, mode="manual", component=str(code)), _ledger())
            assert decision["route"] == "manual", code
            assert _kinds(decision) == ["manual_requested"]

    def test_the_threshold_is_configurable(self) -> None:
        ledger = _ledger()
        assert _route(_envelope(index=1, at=NOW - 120), ledger, threshold=2)["route"] == "observe"
        assert _route(_envelope(index=2, at=NOW), ledger, threshold=2)["route"] == "classify"

    def test_a_replay_never_pushes_an_error_over_the_threshold(self) -> None:
        ledger = _ledger()
        decisions = [_route(_envelope(index=1, at=NOW), ledger) for _ in range(6)]
        assert {decision["route"] for decision in decisions} == {"observe"}
        assert decisions[-1]["recurrence"]["total"] == 1

    def test_sightings_older_than_the_window_do_not_count(self) -> None:
        ledger = _ledger(window_seconds=3600)
        _route(_envelope(index=1, at=NOW - 7200), ledger)
        _route(_envelope(index=2, at=NOW - 7000), ledger)
        assert _route(_envelope(index=3, at=NOW), ledger)["route"] == "observe"

    def test_every_sighting_is_counted_even_when_the_route_is_not_repair(self) -> None:
        ledger = _ledger()
        for index in range(3):
            decision = _route(_envelope(code="FINJA-410", kind="KeyError", index=index, at=NOW - 10 + index), ledger)
        assert decision["route"] == "manual"
        assert decision["recurrence"]["total"] == 3


class TestQuestTracking:

    def _seen(self, ledger) -> str:
        return _route(_envelope(kind="KeyError", index=1, at=NOW - 600), ledger)["fingerprint"]

    def test_an_error_with_an_active_quest_is_tracked_not_reopened(self) -> None:
        ledger = _ledger()
        fingerprint = self._seen(ledger)
        ledger.attach_quest(fingerprint, "c" * 32)
        decision = _route(_envelope(kind="KeyError", index=2, at=NOW), ledger, is_job_active=lambda job_id: True)
        assert decision["route"] == "tracked"
        assert decision["would_open_job"] is False

    def test_a_finished_quest_does_not_block_a_new_sighting(self) -> None:
        ledger = _ledger()
        fingerprint = self._seen(ledger)
        ledger.attach_quest(fingerprint, "c" * 32)
        decision = _route(_envelope(kind="KeyError", index=2, at=NOW), ledger, is_job_active=lambda job_id: False)
        assert decision["route"] == "classify"

    def test_the_active_check_is_asked_about_the_recorded_job(self) -> None:
        ledger = _ledger()
        fingerprint = self._seen(ledger)
        ledger.attach_quest(fingerprint, "d" * 32)
        asked = []
        _route(_envelope(kind="KeyError", index=2, at=NOW), ledger,
               is_job_active=lambda job_id: asked.append(job_id) or False)
        assert asked == ["d" * 32]


class TestFixFeedback:

    def _fixed(self, ledger, times: int) -> str:
        fingerprint = _route(_envelope(kind="KeyError", index=1, at=NOW - 9000), ledger)["fingerprint"]
        for attempt in range(times):
            ledger.record_fix(fingerprint, completed_at=NOW - 8000 + attempt * 100)
        return fingerprint

    def test_returning_after_one_fix_is_flagged_but_still_automatic(self) -> None:
        ledger = _ledger()
        self._fixed(ledger, 1)
        decision = _route(_envelope(kind="KeyError", index=2, at=NOW), ledger)
        assert decision["route"] == "classify"
        assert "regression_after_fix" in _kinds(decision)

    def test_a_fix_that_did_not_hold_goes_to_a_human(self) -> None:
        ledger = _ledger()
        self._fixed(ledger, 2)
        decision = _route(_envelope(kind="KeyError", index=2, at=NOW), ledger)
        assert decision["route"] == "manual"
        assert _kinds(decision) == ["fix_did_not_hold"]

    def test_the_limit_is_configurable(self) -> None:
        ledger = _ledger()
        self._fixed(ledger, 1)
        decision = _route(_envelope(kind="KeyError", index=2, at=NOW), ledger, max_fix_attempts=1)
        assert decision["route"] == "manual"

    def test_a_sighting_from_before_the_fix_is_not_a_regression(self) -> None:
        ledger = _ledger()
        self._fixed(ledger, 2)
        decision = _route(_envelope(kind="KeyError", index=3, at=NOW - 20000), ledger)
        assert "fix_did_not_hold" not in _kinds(decision)


class TestDecisionShape:

    def test_a_decision_never_opens_a_job(self) -> None:
        for kind in ("KeyError", "TimeoutError", "SyntaxError"):
            decision = _route(_envelope(kind=kind, component=kind), _ledger())
            assert decision["opens_job"] is False

    @pytest.mark.parametrize("code,kind,would_open", [
        ("FINJA-999", "KeyError", True), (None, "SyntaxError", True),
        ("FINJA-999", "TimeoutError", False), ("FINJA-410", "KeyError", False),
        ("FINJA-110", "KeyError", False),
    ])
    def test_would_open_job_reflects_the_route(self, code, kind, would_open) -> None:
        assert _route(_envelope(code=code, kind=kind), _ledger())["would_open_job"] is would_open

    def test_every_route_has_a_next_step(self) -> None:
        assert set(routing.NEXT_STEPS) == {
            routing.ROUTE_OBSERVE, routing.ROUTE_OPERATOR, routing.ROUTE_CLASSIFY,
            routing.ROUTE_REPAIR, routing.ROUTE_MANUAL, routing.ROUTE_TRACKED,
        }

    def test_the_decision_carries_no_envelope_text(self) -> None:
        """The summary and the source are untrusted data and must not travel onward as instructions."""
        env = _envelope(content="def secret_function_name():\n    return 1\n")
        env["summary"] = "UNIQUE-SUMMARY-MARKER"
        text = json.dumps(_route(env, _ledger()))
        assert "UNIQUE-SUMMARY-MARKER" not in text
        assert "secret_function_name" not in text


# ==============================================================================
# POST /incidents
# ==============================================================================

def _live(offset_seconds: float) -> float:
    return datetime.now(UTC).timestamp() - offset_seconds


class TestIncidentEndpoint:

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "")
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "")
        monkeypatch.setattr(main, "INCIDENT_RECURRENCE_THRESHOLD", 3)
        monkeypatch.setattr(main, "INCIDENT_RECURRENCE_WINDOW_SECONDS", 3600)
        with main.ACTIVE_JOBS_LOCK:
            main.ACTIVE_JOBS.clear()
        self.jobs = tmp_path / "jobs"
        self.client = TestClient(main.app)

    def _post(self, envelope: dict, **headers):
        return self.client.post("/incidents", json=envelope, headers=headers)

    def _job_folders(self) -> list[str]:
        if not self.jobs.exists():
            return []
        return [entry.name for entry in self.jobs.iterdir() if main.JOB_ID_RE.fullmatch(entry.name)]

    def test_the_catch_all_timeout_escalates_on_the_third_sighting(self) -> None:
        routes = [
            self._post(_envelope(at=_live(1200 - index * 300), index=index)).json()["route"]
            for index in range(3)
        ]
        assert routes == ["observe", "observe", "classify"]

    def test_the_response_carries_capacity_and_the_decision(self) -> None:
        body = self._post(_envelope(kind="KeyError", at=_live(10))).json()
        assert body["route"] == "classify"
        assert body["opens_job"] is False
        assert body["capacity"] == {"active_quests": 0, "max_active_quests": main.MAX_ACTIVE_JOBS, "has_room": True}

    def test_it_creates_no_job_and_leaves_recovery_alone(self) -> None:
        for index in range(4):
            self._post(_envelope(kind="KeyError", at=_live(100 - index), index=index))
        assert self._job_folders() == []
        assert (self.jobs / ".incidents" / "ledger.json").exists()
        assert main.recover_incomplete_jobs() == 0

    def test_a_replay_is_idempotent(self) -> None:
        envelope = _envelope(at=_live(30), index=1)
        self._post(envelope)
        again = self._post(envelope).json()
        assert again["recurrence"]["duplicate"] is True
        assert again["recurrence"]["total"] == 1

    def test_the_threshold_comes_from_the_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "INCIDENT_RECURRENCE_THRESHOLD", 2)
        first = self._post(_envelope(at=_live(240), index=1)).json()["route"]
        second = self._post(_envelope(at=_live(0), index=2)).json()["route"]
        assert (first, second) == ("observe", "classify")

    def test_an_unsupported_version_is_a_400_with_flare_610(self) -> None:
        envelope = _envelope(at=_live(10))
        envelope["envelope_version"] = 2
        response = self._post(envelope)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "FLARE-610"

    def test_an_unknown_field_is_refused(self) -> None:
        envelope = _envelope(at=_live(10))
        envelope["raw_traceback"] = "anything"
        assert self._post(envelope).status_code == 400

    def test_sensitive_content_is_a_422_with_flare_611_and_is_not_echoed(self) -> None:
        response = self._post(_envelope(at=_live(10), content=f'KEY = "{AWS_LIKE}"\n'))
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "FLARE-611"
        assert AWS_LIKE not in response.text

    def test_a_refused_envelope_is_not_recorded(self) -> None:
        self._post(_envelope(at=_live(10), content=f'KEY = "{AWS_LIKE}"\n'))
        assert not (self.jobs / ".incidents" / "ledger.json").exists()

    def test_a_secret_named_file_in_the_bundle_is_refused(self) -> None:
        response = self._post(_envelope(at=_live(10), path="secrets.json", frames=False))
        assert response.status_code == 400

    def test_authentication_applies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "ORCHESTRATOR_AUTH_TOKEN", "route-test-token")
        envelope = _envelope(at=_live(10))
        assert self._post(envelope).status_code == 401
        assert self._post(envelope, Authorization="Bearer route-test-token").status_code == 200

    def test_the_response_repeats_no_envelope_text(self) -> None:
        envelope = _envelope(at=_live(10), content="def unique_function_marker():\n    return 1\n")
        envelope["summary"] = "UNIQUE-SUMMARY-MARKER"
        text = self._post(envelope).text
        assert "UNIQUE-SUMMARY-MARKER" not in text
        assert "unique_function_marker" not in text

    def test_an_unreadable_ledger_is_a_structured_flare_801_not_a_bare_500(self) -> None:
        (self.jobs / ".incidents").mkdir(parents=True)
        (self.jobs / ".incidents" / "ledger.json").write_text("not json at all", encoding="utf-8")
        response = self._post(_envelope(at=_live(10)))
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "FLARE-801"

    def test_an_encrypted_request_is_opened_and_the_ledger_is_encrypted_at_rest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "incident-test-transport-key")
        sealed = main.seal_json(_envelope(at=_live(10)))
        assert self.client.post("/incidents", json=sealed).status_code == 200
        ledger_bytes = (self.jobs / ".incidents" / "ledger.json").read_bytes()
        assert main.is_encrypted_bytes(ledger_bytes) is True

    def test_the_response_is_sealed_when_the_sender_asks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main, "CODE_AGENT_TRANSPORT_KEY", "incident-test-transport-key")
        sealed = main.seal_json(_envelope(at=_live(10)))
        response = self.client.post("/incidents", json=sealed, headers={"X-Finja-Code-Accept-Encrypted": "1"})
        assert response.json()["encrypted"] is True
        assert main.open_json(response.json())["route"] in {"observe", "classify"}


class TestEpisodes:
    """
    Recurrence counts episodes, not raw sightings. Measured before this
    existed: five reports spread over one minute turned a provider timeout
    into a quest at the third, 24 seconds in. A retry storm or a flapping
    monitor then escalated itself, which is the opposite of "keeps coming
    back". NOW sits on a slot boundary, so slot arithmetic here is exact.
    """

    def test_five_reports_across_one_minute_are_one_episode_and_never_escalate(self) -> None:
        ledger = _ledger()
        decisions = [_route(_envelope(index=i, at=NOW - 60 + i * 12), ledger) for i in range(5)]

        assert {decision["route"] for decision in decisions} == {"observe"}
        last = decisions[-1]["recurrence"]
        assert last["episodes_in_window"] == 1
        assert last["sightings_in_episode"] == 5
        assert last["total"] == 5, "every sighting is still counted, just not as a separate episode"

    def test_the_same_reports_spread_over_separate_minutes_do_escalate(self) -> None:
        """The other half: dropping the rate cannot also drop real recurrence."""
        ledger = _ledger()
        routes = [_route(_envelope(index=i, at=NOW - 600 + i * 120), ledger)["route"] for i in range(3)]
        assert routes == ["observe", "observe", "classify"]

    def test_a_monitor_that_never_stops_still_escalates(self) -> None:
        """
        A fixed slot, not "close to the previous event": a monitor firing every
        90 seconds must not be able to extend one episode forever.
        """
        ledger = _ledger()
        routes = [_route(_envelope(index=k, at=NOW - 600 + k * 90), ledger)["route"] for k in range(7)]
        assert routes[:2] == ["observe", "observe"]
        assert routes[2] == "classify"

    def test_a_sender_firing_every_second_for_an_hour_keeps_its_history_and_stays_small(self) -> None:
        store = _Store()
        ledger = _ledger(store)
        decisions = []
        for second in range(3600):
            decisions.append(_route(_envelope(index=second % 90, at=NOW - 3600 + second), ledger))

        record = next(iter(store.state["records"].values()))
        assert record["total"] == 3600
        assert len(record["slots"]) <= 3600 // 60 + 3, "slot numbers, not timestamps: size follows the window"
        assert decisions[0]["route"] == "observe"
        assert decisions[-1]["route"] == "classify", "a fast flapper must not push its own history out and go quiet"
        assert decisions[-1]["recurrence"]["episodes_in_window"] >= 3

    def test_slots_older_than_any_window_are_forgotten_so_a_record_cannot_grow_forever(self) -> None:
        """
        The one above never reaches the horizon: window and duration are both an
        hour, so nothing is old enough to drop. Here the window is ten minutes
        and the sender keeps going for two hours.
        """
        store = _Store()
        ledger = _ledger(store, window_seconds=600)
        for step in range(240):
            self._record_at(ledger, NOW - 7200 + step * 30, step)

        record = next(iter(store.state["records"].values()))
        assert record["total"] == 240
        assert len(record["slots"]) <= 600 // 60 + 3, "slots past the window must be dropped"
        assert max(record["slots"]) == int((NOW - 30) // 60), "the newest slot must survive the pruning"

    def _record_at(self, ledger, at: float, index: int) -> None:
        envelope = validate_incident_envelope(_envelope(at=at, index=index % 90))
        fingerprint, identity = routing.fingerprint_of(envelope)
        ledger.observe(fingerprint, identity, incident_id=f"{index:08x}-e89b-42d3-a456-426614174000",
                       observed_at=envelope.observed_at)

    def test_two_reports_either_side_of_a_slot_boundary_are_two_episodes(self) -> None:
        """Documented granularity: the slots are fixed, so a burst may straddle one boundary."""
        ledger = _ledger()
        _route(_envelope(index=1, at=NOW - 1), ledger)
        assert _route(_envelope(index=2, at=NOW + 1), ledger)["recurrence"]["episodes_in_window"] == 2

    def test_a_straddling_burst_cannot_reach_a_threshold_of_three(self) -> None:
        ledger = _ledger()
        decisions = [_route(_envelope(index=i, at=NOW - 30 + i * 12), ledger) for i in range(6)]
        assert max(d["recurrence"]["episodes_in_window"] for d in decisions) <= 2
        assert {d["route"] for d in decisions} == {"observe"}

    def test_an_old_report_arriving_late_does_not_disturb_the_current_episode(self) -> None:
        ledger = _ledger()
        _route(_envelope(index=1, at=NOW), ledger)
        _route(_envelope(index=2, at=NOW - 1800), ledger)
        assert _route(_envelope(index=3, at=NOW), ledger)["recurrence"]["sightings_in_episode"] == 2

    def test_the_episode_length_is_configurable(self) -> None:
        ledger = _ledger(episode_seconds=600)
        decisions = [_route(_envelope(index=i, at=NOW - 500 + i * 120), ledger) for i in range(4)]
        assert {d["recurrence"]["episodes_in_window"] for d in decisions} <= {1, 2}

    def test_the_response_says_how_it_counted(self) -> None:
        recurrence = _route(_envelope(), _ledger())["recurrence"]
        assert recurrence["episode_seconds"] == routing.DEFAULT_EPISODE_SECONDS
        assert "count_in_window" not in recurrence, "the old name counted sightings and would mislead"


class TestLedgerMigration:

    def test_a_version_1_ledger_is_folded_into_episodes(self) -> None:
        envelope = validate_incident_envelope(_envelope(at=NOW))
        fingerprint, identity = routing.fingerprint_of(envelope)
        store = _Store()
        store.state = {"ledger_version": 1, "records": {fingerprint: {
            **identity, "first_seen": NOW - 1200, "last_seen": NOW - 600, "total": 2,
            "events": [NOW - 1200, NOW - 600], "seen_keys": [], "open_job_id": None,
            "fix_attempts": 0, "last_fix_at": None,
        }}}

        seen = _ledger(store).observe(fingerprint, identity, incident_id=envelope.incident_id,
                                      observed_at=envelope.observed_at)

        assert seen["episodes_in_window"] == 3, "two migrated sightings in two slots plus the new one"
        assert store.state["ledger_version"] == routing.LEDGER_VERSION
        assert "events" not in store.state["records"][fingerprint]

    def test_a_malformed_version_1_record_still_fails_closed(self) -> None:
        store = _Store()
        store.state = {"ledger_version": 1, "records": {"abc": "not a record"}}
        with pytest.raises(JobPersistenceError):
            _ledger(store).observe("abc", {}, incident_id=_incident_id(1), observed_at=_stamp(NOW))


class TestNotification:
    """
    Whether a person should be told is its own question, with its own cooldown.
    The same error must not be announced over and over; a change is news.
    """

    COOLDOWN = 1800

    def _setup(self):
        clock = [NOW]
        store = _Store()
        ledger = _ledger(store, clock=lambda: clock[0], notify_cooldown_seconds=self.COOLDOWN)
        return ledger, clock, store

    def test_a_route_nobody_acts_on_never_sends(self) -> None:
        ledger, _, _ = self._setup()
        notice = _route(_envelope(index=1), ledger)["notify"]
        assert notice == {"send": False, "reason": "no_message_for_route", "until": None}

    def test_the_first_actionable_decision_sends(self) -> None:
        ledger, _, _ = self._setup()
        notice = _route(_envelope(kind="KeyError"), ledger)["notify"]
        assert notice["send"] is True
        assert notice["reason"] == "first_notice"
        assert notice["until"] == _stamp(NOW + self.COOLDOWN)

    @pytest.mark.parametrize("code,route", [("FINJA-110", "operator"), ("FINJA-410", "manual")])
    def test_operator_and_manual_routes_are_worth_a_message(self, code: str, route: str) -> None:
        ledger, _, _ = self._setup()
        decision = _route(_envelope(code=code, kind="KeyError"), ledger)
        assert decision["route"] == route
        assert decision["notify"]["send"] is True

    def test_the_same_route_inside_the_cooldown_is_suppressed(self) -> None:
        ledger, clock, _ = self._setup()
        _route(_envelope(kind="KeyError", index=1, at=NOW - 600), ledger)
        clock[0] = NOW + 120
        notice = _route(_envelope(kind="KeyError", index=2, at=NOW + 120), ledger)["notify"]

        assert notice["send"] is False
        assert notice["reason"] == "suppressed_by_cooldown"
        assert notice["until"] == _stamp(NOW + self.COOLDOWN)

    def test_after_the_cooldown_it_may_be_announced_again(self) -> None:
        ledger, clock, _ = self._setup()
        _route(_envelope(kind="KeyError", index=1, at=NOW - 600), ledger)
        clock[0] = NOW + self.COOLDOWN + 1
        notice = _route(_envelope(kind="KeyError", index=2, at=NOW + self.COOLDOWN + 1), ledger)["notify"]
        assert notice["send"] is True
        assert notice["reason"] == "cooldown_elapsed"

    def test_a_changed_route_is_news_whatever_the_cooldown_says(self) -> None:
        ledger, clock, _ = self._setup()
        assert _route(_envelope(kind="KeyError", index=1, at=NOW - 600), ledger)["notify"]["send"] is True
        clock[0] = NOW + 10
        decision = _route(_envelope(kind="KeyError", index=2, at=NOW + 10, mode="manual"), ledger)

        assert decision["route"] == "manual"
        assert decision["notify"]["send"] is True
        assert decision["notify"]["reason"] == "route_changed"

    def test_an_escalation_after_silent_counting_is_announced(self) -> None:
        """observe never sends, so the sighting that finally escalates is the first message."""
        ledger, _, _ = self._setup()
        decisions = [_route(_envelope(index=i, at=NOW - 600 + i * 120), ledger) for i in range(3)]
        assert [d["notify"]["send"] for d in decisions] == [False, False, True]
        assert decisions[2]["route"] == "classify"

    def test_a_replay_never_notifies(self) -> None:
        ledger, _, _ = self._setup()
        envelope = _envelope(kind="KeyError", index=1)
        assert _route(envelope, ledger)["notify"]["send"] is True
        replay = _route(envelope, ledger)["notify"]
        assert replay["send"] is False
        assert replay["reason"] == "duplicate_replay"

    def test_asking_twice_does_not_send_twice(self) -> None:
        ledger, _, _ = self._setup()
        decision = _route(_envelope(kind="KeyError", index=1), ledger)
        again = ledger.notify_decision(decision["fingerprint"], decision["route"], duplicate=False)
        assert again["send"] is False
        assert again["reason"] == "suppressed_by_cooldown"

    def test_a_landed_fix_makes_a_return_news_again(self) -> None:
        ledger, clock, _ = self._setup()
        first = _route(_envelope(kind="KeyError", index=1, at=NOW - 600), ledger)
        ledger.record_fix(first["fingerprint"], completed_at=NOW - 300)
        clock[0] = NOW + 10
        again = _route(_envelope(kind="KeyError", index=2, at=NOW + 10), ledger)
        assert again["notify"]["send"] is True
        assert again["notify"]["reason"] == "first_notice"

    def test_an_unknown_fingerprint_sends_nothing(self) -> None:
        ledger, _, _ = self._setup()
        notice = ledger.notify_decision("deadbeefdeadbeef", "classify", duplicate=False)
        assert notice == {"send": False, "reason": "unknown_fingerprint", "until": None}

    def test_the_cooldown_is_configurable(self) -> None:
        clock = [NOW]
        ledger = _ledger(_Store(), clock=lambda: clock[0], notify_cooldown_seconds=10)
        _route(_envelope(kind="KeyError", index=1, at=NOW - 600), ledger)
        clock[0] = NOW + 11
        assert _route(_envelope(kind="KeyError", index=2, at=NOW + 11), ledger)["notify"]["send"] is True


class TestRoutingConfiguration:

    def test_the_defaults_match_the_documented_policy(self) -> None:
        assert routing.DEFAULT_THRESHOLD == 3
        assert routing.DEFAULT_WINDOW_SECONDS == 3600
        assert routing.DEFAULT_MAX_FIX_ATTEMPTS == 2
        assert routing.DEFAULT_EPISODE_SECONDS == 60
        assert routing.DEFAULT_NOTIFY_COOLDOWN_SECONDS == 3600
