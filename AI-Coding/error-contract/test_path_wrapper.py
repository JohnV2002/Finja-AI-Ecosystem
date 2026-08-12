"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error-contract / test_path_wrapper.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.1
  Description: Regression tests for safe PATH-wrapper installation.

  New in v1.0.0:
    - Ensure installation never writes machine paths into the repository

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from error_contract.path_wrapper import install_path_wrapper


PLUGIN_ROOT = Path(__file__).resolve().parent


class PathWrapperRegressionTests(unittest.TestCase):
    def test_install_does_not_rewrite_repository_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "engine"
            repo_bin = engine / "bin"
            repo_bin.mkdir(parents=True)
            launcher = repo_bin / "error-contract.cmd"
            launcher.write_text("repository sentinel\n", encoding="utf-8")

            user_bins = [root / "user-bin-a", root / "user-bin-b", root / "user-bin-c"]
            with (
                patch("error_contract.path_wrapper._home", return_value=root / "home"),
                patch(
                    "error_contract.path_wrapper.preferred_bin_dirs",
                    return_value=user_bins,
                ),
                patch(
                    "error_contract.path_wrapper.ensure_user_path_contains",
                    return_value={"status": "test"},
                ),
            ):
                result = install_path_wrapper(engine)

            self.assertEqual(
                launcher.read_text(encoding="utf-8"), "repository sentinel\n"
            )
            self.assertNotIn(str(launcher), result["written"])

    def test_codex_skill_starts_with_yaml_frontmatter(self) -> None:
        skill = PLUGIN_ROOT / "skill-pack" / "error-contract" / "SKILL.md"
        data = skill.read_bytes()
        self.assertTrue(data.startswith((b"---\n", b"---\r\n")))
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main()
