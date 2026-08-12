"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  test_namespace_registry.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Regression tests for canonical namespaces and minimal local scaffolds.

  New in v1.3.1:
    - Covers central ownership, path neutrality, and local-only manifests

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import json
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from error_contract.ledger import load_namespace_ledger, reserve_code
from error_contract.scaffold import scaffold_project
from error_contract.taxonomy import parse_exceptions_py
from error_contract.cli import main
from error_contract.docsgen import ensure_project_docs
from error_contract.ambient import preflight
from error_contract.registry import format_resolve, resolve_project


class NamespaceRegistryTests(unittest.TestCase):
    def test_contract_tooling_can_explicitly_skip_its_own_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pyproject.toml").write_text(
                "[project]\nname = \"contract-tool\"\n"
                "\n[tool.error-contract]\n"
                "exempt = true\n"
                "reason = \"Contract tooling must not contract itself.\"\n",
                encoding="utf-8",
            )

            result = resolve_project(root)
            self.assertEqual(result["status"], "exempt")
            self.assertIn("must not contract itself", result["reason"])
            self.assertIn("Project Resolve: EXEMPT", format_resolve(result))

            preflight_result = preflight(root, session_id="self-tooling-test")
            self.assertEqual(preflight_result["status"], "exempt")
            self.assertFalse((root / ".error_contract").exists())

    def test_finja_registry_owns_chat_codes_globally(self) -> None:
        ledger = load_namespace_ledger("FINJA", Path(__file__).resolve())
        self.assertEqual(ledger.get("FINJA", 406).owner_id, "finja-chat")
        result = reserve_code(
            ledger,
            prefix="FINJA",
            band="session",
            owner_id="finja-weather",
            code_num=406,
            persist=False,
        )
        self.assertFalse(result["ok"])

    def test_registry_contains_no_absolute_machine_paths(self) -> None:
        ledger = load_namespace_ledger("FINJA", Path(__file__).resolve())
        serialized = json.dumps(ledger.to_dict())
        self.assertNotIn(":\\", serialized)
        self.assertNotIn("\\\\", serialized)

    def test_scaffold_has_no_borrowed_numeric_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scaffold_project(root, prefix="FINJA", owner="finja-weather", module="finja-weather")
            taxonomy = parse_exceptions_py(root / "core" / "exceptions.py", prefix_hint="FINJA")
            self.assertEqual(taxonomy.codes, [])
            manifest = json.loads((root / "contracts" / "error_contract.module.json").read_text())
            self.assertEqual(manifest["implementations"], [])
            self.assertEqual(manifest["legend"], "error_contract.json")
            legend = json.loads((root / "error_contract.json").read_text())
            self.assertIn("FINJA", legend["namespaces"])
            self.assertFalse((root / "ERROR_CONTRACT.md").exists())

    def test_monorepo_root_legend_keeps_multiple_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / ".git").mkdir()
            scaffold_project(repo / "finja-chat", prefix="FINJA", owner="finja-chat")
            scaffold_project(repo / "milky", prefix="MILK", owner="milky")
            legend = json.loads((repo / "error_contract.json").read_text())
            self.assertEqual(set(legend["namespaces"]), {"FINJA", "MILK"})
            milk_manifest = json.loads(
                (repo / "milky" / "contracts" / "error_contract.module.json").read_text()
            )
            self.assertEqual(milk_manifest["legend"], "../error_contract.json")

    def test_ensure_imports_existing_module_codes_into_public_legend(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core = root / "core"
            core.mkdir()
            (core / "exceptions.py").write_text(
                "class AppError(Exception):\n"
                "    code_num = None\n\n"
                "class MilkBottleEmptyError(AppError):\n"
                "    code_num = 500\n",
                encoding="utf-8",
            )
            result = ensure_project_docs(root, prefix="MILK", force=True)
            self.assertEqual(result["status"], "ok")
            legend = json.loads((root / "error_contract.json").read_text())
            claim = legend["namespaces"]["MILK"]["codes"]["500"]
            self.assertEqual(claim["name"], "MilkBottleEmptyError")
            self.assertEqual(claim["source"], "core/exceptions.py")

    def test_project_can_define_and_use_a_1400_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(
                main(
                    [
                        "category",
                        str(root),
                        "brand_new_things",
                        "--prefix",
                        "FINJA",
                        "--range",
                        "1400-1499",
                        "--description",
                        "Future features without a predefined contract band",
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "create",
                        str(root),
                        "CompletelyNewThingError",
                        "--prefix",
                        "FINJA",
                        "--band",
                        "brand_new_things",
                        "--owner",
                        "finja-future",
                    ]
                ),
                0,
            )
            legend = json.loads((root / "error_contract.json").read_text())
            namespace = legend["namespaces"]["FINJA"]
            self.assertEqual(namespace["categories"]["brand_new_things"]["range"], "1400-1499")
            self.assertEqual(namespace["codes"]["1400"]["name"], "CompletelyNewThingError")

    def test_create_reserves_and_writes_local_class_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_home = os.environ.get("ERROR_CONTRACT_HOME")
            os.environ["ERROR_CONTRACT_HOME"] = str(root / "state")
            try:
                result = main(
                    [
                        "create",
                        str(root),
                        "DemoSessionError",
                        "--prefix",
                        "TEST",
                        "--band",
                        "session",
                        "--owner",
                        "demo",
                        "--module",
                        "demo",
                        "--message",
                        "demo failed",
                    ]
                )
            finally:
                if old_home is None:
                    os.environ.pop("ERROR_CONTRACT_HOME", None)
                else:
                    os.environ["ERROR_CONTRACT_HOME"] = old_home
            self.assertEqual(result, 0)
            taxonomy = parse_exceptions_py(root / "core" / "exceptions.py", prefix_hint="TEST")
            self.assertEqual([(code.code_num, code.class_name) for code in taxonomy.codes], [(400, "DemoSessionError")])
            manifest = json.loads((root / "contracts" / "error_contract.module.json").read_text())
            self.assertEqual(manifest["implementations"][0]["code"], "TEST-400")

    def test_create_rolls_back_registry_and_class_when_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_home = os.environ.get("ERROR_CONTRACT_HOME")
            os.environ["ERROR_CONTRACT_HOME"] = str(root / "state")
            try:
                with patch("error_contract.manifest.write_local_manifest", side_effect=OSError("disk full")):
                    result = main(
                        [
                            "create",
                            str(root),
                            "BrokenSessionError",
                            "--prefix",
                            "ROLLBACK",
                            "--band",
                            "session",
                            "--owner",
                            "demo",
                        ]
                    )
            finally:
                if old_home is None:
                    os.environ.pop("ERROR_CONTRACT_HOME", None)
                else:
                    os.environ["ERROR_CONTRACT_HOME"] = old_home
            self.assertEqual(result, 1)
            self.assertFalse((root / "core" / "exceptions.py").exists())
            self.assertFalse((root / "error_contract.json").exists())


if __name__ == "__main__":
    unittest.main()
