"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  test_sender_and_flare.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: The generated Python sender and the contract's `flare` block.

  New in v1.1.0:
    - Proves the generated sender is standalone, off by default, privacy-safe and
      accepted by the canonical event validator, and that the flare block matches
      Flare's profile limits

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from analytics_contract.cli import main as cli_main  # noqa: E402
from analytics_contract.contract import build_contract, validate_contract, write_contract  # noqa: E402
from analytics_contract.events import validate_event  # noqa: E402
from analytics_contract.flare import default_flare_block, validate_flare_block  # noqa: E402
from analytics_contract.models import ProjectProfile  # noqa: E402
from analytics_contract.sender import SenderError, render_sender, write_sender  # noqa: E402

ENV = {"ANALYTICS_ENABLED": "true", "ANALYTICS_ENDPOINT": "http://analytics-collector:8080",
       "ANALYTICS_TOKEN": "ingest-token"}


class Collector:
    def __init__(self, *statuses: int) -> None:
        self.statuses = list(statuses)
        self.batches: list[dict] = []

    def __call__(self, url, body, headers, timeout):
        self.batches.append(json.loads(body))
        return self.statuses.pop(0) if self.statuses else 202


class FakeSampler:
    def cpu_percent(self, now=None):
        return 3.5

    def rss_bytes(self):
        return 52_000_000


class GeneratedProject(unittest.TestCase):
    """A throwaway project with a contract, a generated sender and a module that fails for real."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "pyproject.toml").write_text('[project]\nname = "demo-app"\n', encoding="utf-8")
        (self.root / "error_contract.json").write_text("{}", encoding="utf-8")
        write_contract(self.root)
        self.target = write_sender(self.root, language="python", out="demo/analytics_sender.py",
                                   project_name="Demo App", version="2.3.4")
        spec = importlib.util.spec_from_file_location(f"generated_{id(self)}", self.target)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module  # dataclasses look their module up, as with a normal import
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.module)
        (self.root / "demo" / "logic.py").write_text(
            "class AppError(Exception):\n"
            "    code = 'DEMO-502'\n"
            "    module = 'logic'\n\n"
            "def divide(a, b):\n"
            "    try:\n"
            "        return a / b\n"
            "    except ZeroDivisionError as exc:\n"
            "        raise AppError('broken') from exc\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"logic_{id(self)}", self.root / "demo" / "logic.py")
        self.logic = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.logic)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def sender(self, collector: Collector | None = None, env: dict | None = None):
        config, problem = self.module.AnalyticsConfig.from_environment(self.root, env or ENV, version="2.3.4")
        self.assertIsNone(problem)
        self.problems: list[dict] = []
        return self.module.AnalyticsSender(config, root=self.root, transport=collector or Collector(),
                                           sampler=FakeSampler(), on_failure=self.problems.append,
                                           clock=lambda: 0.0)

    def raised(self):
        try:
            self.logic.divide(1, 0)
        except self.logic.AppError as exc:
            return exc
        self.fail("divide did not raise")


class TestGeneratedFile(GeneratedProject):
    def test_it_is_standalone_and_carries_the_project_header(self) -> None:
        text = self.target.read_text(encoding="utf-8")
        self.assertIn("Project: Demo App", text)
        self.assertIn("Version: 2.3.4", text)
        self.assertIn("Module: demo.analytics_sender", text)
        body = text.split('"""', 2)[2]
        self.assertNotIn("import analytics_contract", body)  # no runtime dependency on the tool
        self.assertNotIn("from analytics_contract", body)
        # Projects run the Error Contract gate over this file: no broad catch may come with it.
        self.assertNotIn("except Exception", body)
        self.assertNotIn("except:", body)
        self.assertNotIn("AI-Coding Tooling", text)

    def test_off_by_default_does_nothing(self) -> None:
        config, problem = self.module.AnalyticsConfig.from_environment(self.root, {})
        self.assertFalse(config.enabled)
        self.assertIsNone(problem)
        off = self.module.AnalyticsSender(config, root=self.root, transport=lambda *a: self.fail("network"))

        def sink(error):
            return error

        self.assertIs(off.fan_out(sink), sink)
        self.assertIsNone(off.record_exception(self.raised()))
        off.start()
        self.assertIsNone(off._thread)

    def test_project_id_comes_from_the_contract(self) -> None:
        self.assertEqual(self.sender().config.project_id, "demo-app")

    def test_misconfiguration_stays_off_with_a_reason(self) -> None:
        config, problem = self.module.AnalyticsConfig.from_environment(self.root, {**ENV, "ANALYTICS_TOKEN": ""})
        self.assertFalse(config.enabled)
        self.assertIn("token", problem)


class TestEvents(GeneratedProject):
    def test_a_live_exception_becomes_one_canonical_error_event(self) -> None:
        sender = self.sender()
        event = sender.record_exception(self.raised())
        self.assertIsNotNone(event)
        self.assertEqual(validate_event(event), [])  # the tool's own validator agrees
        self.assertEqual(event["error"]["code"], "DEMO-502")
        self.assertEqual(event["error"]["affected_file"], "demo/logic.py")
        self.assertEqual(event["error"]["line"], 7)
        text = json.dumps(event)
        self.assertNotIn("broken", text)
        self.assertNotIn(str(self.root), text)

    def test_the_same_exception_counts_once(self) -> None:
        sender = self.sender()
        exc = self.raised()
        self.assertIsNotNone(sender.record_exception(exc))
        self.assertIsNone(sender.record_exception(exc))

    def test_every_new_occurrence_counts_even_when_ids_are_reused(self) -> None:
        import gc

        sender = self.sender()
        counted = 0
        for _ in range(5):
            exc = self.raised()
            counted += sender.record_exception(exc) is not None
            del exc
            gc.collect()  # lets the next exception take the same id
        self.assertEqual(counted, 5)

    def test_a_dashboard_error_with_expired_credentials_needs_a_person(self) -> None:
        sender = self.sender()
        trace = (f'Traceback (most recent call last):\n  File "{self.root / "demo" / "logic.py"}", '
                 "line 7, in divide\nRuntimeError: x")
        event = sender.record_dashboard_error({"code": "DEMO-503", "module": "tool:spotify",
                                               "cause": "RuntimeError: HTTP 401 Unauthorized",
                                               "traceback": trace, "message": "secret"})
        self.assertTrue(event["error"]["fingerprint"].startswith("env-auth-"))
        self.assertEqual(event["module"], "tool-spotify")
        self.assertEqual(validate_event(event), [])

    def test_the_log_handler_reports_coded_exceptions(self) -> None:
        sender = self.sender()
        logger = logging.getLogger(f"demo-{id(self)}")
        logger.propagate = False
        logger.addHandler(self.module.AnalyticsLogHandler(sender))
        try:
            self.logic.divide(1, 0)
        except self.logic.AppError:
            logger.exception("divide failed")
        self.assertEqual(sender.queued(), 1)

    def test_delivery_retries_with_the_same_ids_then_succeeds(self) -> None:
        collector = Collector(503)
        clock = {"now": 0.0}
        config, _ = self.module.AnalyticsConfig.from_environment(self.root, ENV)
        sender = self.module.AnalyticsSender(config, root=self.root, transport=collector, sampler=FakeSampler(),
                                             clock=lambda: clock["now"])
        sender.record_exception(self.raised())
        sender.sample_resources()
        self.assertEqual(sender.flush_once(), 0)
        clock["now"] = 10.0
        self.assertEqual(sender.flush_once(), 3)  # error, CPU, RAM
        self.assertEqual(collector.batches[0], collector.batches[1])
        for event in collector.batches[1]["events"]:
            self.assertEqual(validate_event(event), [])


class TestSenderCommand(unittest.TestCase):
    def test_only_known_languages_and_versions(self) -> None:
        with self.assertRaises(SenderError):
            render_sender(language="kotlin", project_name="X", module="x", version="1.0.0")
        with self.assertRaises(SenderError):
            render_sender(language="python", project_name="X", module="x", version="1.0")

    def test_never_outside_the_project_and_never_over_a_file_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SenderError):
                write_sender(tmp, language="python", out="../escape.py", project_name="X", version="1.0.0")
            write_sender(tmp, language="python", out=None, project_name="X", version="1.0.0")
            with self.assertRaises(SenderError):
                write_sender(tmp, language="python", out=None, project_name="X", version="1.0.0")
            write_sender(tmp, language="python", out=None, project_name="X", version="7.8.9", force=True)
            self.assertIn("Version: 7.8.9", (Path(tmp) / "analytics_sender.py").read_text(encoding="utf-8"))

    def test_cli_writes_the_sender(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = cli_main(["sender", tmp, "--project-name", "Demo", "--version", "1.0.0"])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "analytics_sender.py").is_file())
            self.assertEqual(cli_main(["sender", tmp, "--lang", "go", "--project-name", "D", "--version", "1.0.0"]), 1)


class TestFlareBlock(unittest.TestCase):
    def test_new_contracts_carry_a_valid_flare_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Dockerfile").write_text("FROM python:3.14-slim\n", encoding="utf-8")
            write_contract(tmp)
            self.assertEqual(validate_contract(tmp), [])
            block = json.loads((Path(tmp) / "analytics_contract.json").read_text(encoding="utf-8"))["flare"]
            self.assertEqual(block["apply"], "host_agent")
            self.assertEqual(block["signals"]["errors"]["operator_fingerprint_prefixes"], ["env-"])

    def test_apps_that_cannot_be_updated_in_place_are_analysis_only(self) -> None:
        game = ProjectProfile(root=".", project_id="game", languages=["csharp"], runtimes=["render_loop"])
        self.assertEqual(default_flare_block(game)["apply"], "analysis_only")
        android = ProjectProfile(root=".", project_id="app", languages=["kotlin"], runtimes=[])
        self.assertEqual(default_flare_block(android)["apply"], "analysis_only")

    def test_limits_match_flare(self) -> None:
        block = default_flare_block(ProjectProfile(root=".", project_id="x"))
        self.assertEqual(validate_flare_block(block), [])
        bad = json.loads(json.dumps(block))
        bad["apply"] = "deploy"
        bad["signals"]["errors"]["min_count"] = 0
        bad["signals"]["resources"][0]["aggregation"] = "sum"
        bad["signals"]["resources"].append(dict(bad["signals"]["resources"][1]))
        bad["signals"]["cooldown_minutes"] = 1
        bad["check_label"] = "**bold**"
        problems = " ".join(validate_flare_block(bad))
        for words in ("flare.apply", "min_count", "aggregation", "repeats", "cooldown", "check_label"):
            self.assertIn(words, problems)

    def test_old_contracts_without_flare_stay_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            contract = build_contract(tmp)
            contract.pop("flare")
            (Path(tmp) / "analytics_contract.json").write_text(json.dumps(contract), encoding="utf-8")
            self.assertEqual(validate_contract(tmp), [])


if __name__ == "__main__":
    unittest.main()
