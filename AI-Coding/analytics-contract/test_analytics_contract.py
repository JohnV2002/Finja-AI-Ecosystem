"""
======================================================================
                         Analytics Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  analytics-contract / test_analytics_contract.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
  Description: Regression tests for detection, safe defaults, and event schema.

  New in v1.0.1:
    - Covers idempotency, fingerprints, tag limits, and safe extensions

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analytics_contract.contract import build_contract, validate_contract, write_contract
from analytics_contract.detect import detect_project
from analytics_contract.events import validate_batch, validate_event


MODULE_ROOT = Path(__file__).resolve().parent


class SchemaTests(unittest.TestCase):
    def test_public_json_schemas_parse(self) -> None:
        schemas = MODULE_ROOT / "schemas"
        for name in ("event.schema.json", "contract.schema.json"):
            with self.subTest(name=name):
                data = json.loads((schemas / name).read_text(encoding="utf-8"))
                self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_openapi_exposes_fixed_health_ingest_and_query_routes(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        api = yaml.safe_load((MODULE_ROOT / "schemas" / "api.openapi.yaml").read_text(encoding="utf-8"))
        self.assertEqual(api["openapi"], "3.1.0")
        self.assertEqual(api["info"]["version"], "1.0.0")
        self.assertTrue({"/v1/health", "/v1/events", "/v1/query"}.issubset(api["paths"]))


class DetectionTests(unittest.TestCase):
    def test_contract_tooling_can_explicitly_skip_self_instrumentation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pyproject.toml").write_text(
                "[project]\nname = \"analytics-tool\"\n"
                "\n[tool.analytics-contract]\n"
                "exempt = true\n"
                "reason = \"Contract tooling must not instrument itself.\"\n",
                encoding="utf-8",
            )
            (root / "detector.py").write_text("FPS Docker queue OpenAI\n", encoding="utf-8")
            profile = detect_project(root)
            self.assertTrue(profile.exempt)
            self.assertEqual(profile.runtimes, [])
            self.assertEqual(profile.recommendations, [])

    def test_detects_php_docker_error_inbox_and_relevant_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Main-Website"
            root.mkdir()
            (root / "Dockerfile").write_text("FROM php:8.3\n", encoding="utf-8")
            (root / "index.php").write_text(
                "<?php $inbox = new ErrorInbox(); http_response_code(200); ?>",
                encoding="utf-8",
            )
            (root / "error_contract.json").write_text("{}\n", encoding="utf-8")

            profile = detect_project(root)
            names = {item.name for item in profile.recommendations}
            self.assertIn("php", profile.languages)
            self.assertIn("docker", profile.runtimes)
            self.assertTrue(profile.error_contract)
            self.assertTrue(profile.error_inbox)
            self.assertIn("system.cpu.usage", names)
            self.assertIn("system.memory.usage", names)
            self.assertIn("http.request.duration", names)
            self.assertIn("error.occurrence", names)

    def test_detects_render_metrics_without_requiring_a_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "game.py").write_text("import pygame\n", encoding="utf-8")
            profile = detect_project(root)
            names = {item.name for item in profile.recommendations}
            self.assertIn("render.fps", names)
            self.assertIn("render.frame.duration", names)

    def test_docs_tests_and_schemas_do_not_create_runtime_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "app.py").write_text("def main():\n    return 0\n", encoding="utf-8")
            (root / "README.md").write_text("FPS queue OpenAI database PHP\n", encoding="utf-8")
            (root / "test_fake.py").write_text("import pygame\n", encoding="utf-8")
            schema = root / "schemas"
            schema.mkdir()
            (schema / "api.yaml").write_text("description: worker queue FPS\n", encoding="utf-8")

            profile = detect_project(root)
            self.assertEqual(profile.runtimes, [])
            self.assertEqual(profile.signals, [])


class ContractTests(unittest.TestCase):
    def test_new_contract_is_disabled_and_fail_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            contract = build_contract(temp)
            self.assertFalse(contract["analytics"]["enabled"])
            self.assertTrue(contract["analytics"]["fail_silent"])
            self.assertIsNone(contract["analytics"]["endpoint"])
            self.assertEqual(contract["analytics"]["endpoint_env"], "ANALYTICS_ENDPOINT")
            self.assertEqual(contract["protocol"], {"event_schema": "1.0", "api_major": 1})

    def test_init_creates_contract_but_no_debt_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target, written = write_contract(root)
            self.assertTrue(written)
            self.assertTrue(target.is_file())
            self.assertFalse((root / ".analytics_contract" / "baseline.json").exists())

    def test_init_does_not_overwrite_human_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "analytics_contract.json"
            target.write_text('{"human": true}\n', encoding="utf-8")
            _, written = write_contract(root)
            self.assertFalse(written)
            self.assertEqual(json.loads(target.read_text()), {"human": True})

    def test_validation_rejects_non_silent_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            contract = build_contract(root)
            contract["analytics"]["fail_silent"] = False
            (root / "analytics_contract.json").write_text(json.dumps(contract), encoding="utf-8")
            self.assertIn("analytics.fail_silent must remain true", validate_contract(root))

    def test_validation_rejects_unreviewed_tag_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            contract = build_contract(root)
            contract["privacy"]["allowed_tags"].append("user_id")
            (root / "analytics_contract.json").write_text(json.dumps(contract), encoding="utf-8")
            self.assertIn(
                "privacy.allowed_tags contains an unsafe or unknown tag",
                validate_contract(root),
            )


class EventTests(unittest.TestCase):
    def _event(self) -> dict:
        return {
            "schema_version": "1.0",
            "event_id": "evt-1",
            "timestamp": "2026-10-20T12:00:00Z",
            "project_id": "finja-chat",
            "module": "auth",
            "event_name": "token.refresh",
            "kind": "error",
            "outcome": "failure",
            "error": {
                "code": "FINJA-406",
                "fingerprint": "finja-406-token-refresh",
                "affected_file": "auth/token_refresh.py",
                "line": 84,
            },
        }

    def test_structured_error_event_is_valid(self) -> None:
        self.assertEqual(validate_event(self._event()), [])

    def test_absolute_affected_file_is_rejected(self) -> None:
        event = self._event()
        separator = chr(47)
        event["error"]["affected_file"] = f"C:{separator}Users{separator}name{separator}project{separator}auth.py"
        self.assertIn("error.affected_file must be project-relative", validate_event(event))

    def test_source_and_stacktrace_are_rejected(self) -> None:
        event = self._event()
        event["error"]["source_code"] = "secret source"
        event["error"]["stacktrace"] = "private path"
        problems = validate_event(event)
        self.assertTrue(any("unknown fields" in problem for problem in problems))

    def test_retry_and_new_occurrence_identity_are_distinct(self) -> None:
        first = self._event()
        second = self._event()
        second["event_id"] = "evt-2"
        self.assertEqual(validate_batch([first, second]), [])

        retry = self._event()
        problems = validate_batch([first, retry])
        self.assertTrue(any("duplicate event_id" in problem for problem in problems))

    def test_unallowlisted_high_cardinality_tag_is_rejected(self) -> None:
        event = self._event()
        event["tags"] = {"environment": "production", "user_id": "1234"}
        self.assertTrue(any("not allowlisted" in problem for problem in validate_event(event)))

    def test_safe_bounded_extension_is_accepted(self) -> None:
        event = self._event()
        event["extensions"] = {"x_cache_state": "cold"}
        self.assertEqual(validate_event(event), [])

    def test_sensitive_extension_name_is_rejected(self) -> None:
        event = self._event()
        event["extensions"] = {"x_user_token": "nope"}
        self.assertTrue(any("unsafe extension key" in problem for problem in validate_event(event)))

    def test_unknown_top_level_field_is_rejected(self) -> None:
        event = self._event()
        event["secret"] = "nope"
        self.assertTrue(any("unknown fields" in problem for problem in validate_event(event)))


if __name__ == "__main__":
    unittest.main()

