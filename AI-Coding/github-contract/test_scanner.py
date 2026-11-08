"""
======================================================================
                         GitHub Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  github-contract / test_scanner
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.2.0
  Description: Regression tests for headers and private-path detection.

  New in v1.2.0:
    - Cover binary skipping, .gitignore handling and the non-git fallback

  New in v1.1.0:
    - Verify explicit target-project labels in generated headers

  New in v1.0.1:
    - Protect Finja HTML headers from false missing-header reports
    - Detect absolute PC paths without mistaking public API URLs for paths

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from github_contract.headers import (
    build_html_header,
    build_readme_footer,
    has_ecosystem_header,
)
from github_contract.scanner import scan_module
from github_contract.detect import _has_github_remote


FINJA_HTML_HEADER = """<!--
Project: Finja - Twitch Interactivity Suite
Author: JohnV2002 (J. Apps / Sodakiller1)
Version: 1.0.1
Description: Finja browser source.
New in 1.0.1: Scanner regression fixture.
Copyright (c) 2026 J. Apps
Licensed under the MIT License.
-->
"""


class HeaderRegressionTests(unittest.TestCase):
    def test_finja_html_banner_is_recognized(self) -> None:
        self.assertTrue(
            has_ecosystem_header(FINJA_HTML_HEADER, Path("overlay.html"))
        )

    def test_headerless_html_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# Demo v1.0.1\n\n## License\nMIT\n\n## Support\nJ. Apps\n",
                encoding="utf-8",
            )
            (root / "overlay.html").write_text("<html></html>\n", encoding="utf-8")
            _, findings = scan_module(
                root, expected_version="1.0.1", require_headers=True
            )
            self.assertTrue(
                any(
                    item.rule == "missing_header" and item.path == "overlay.html"
                    for item in findings
                )
            )

    def test_readme_footer_uses_repository_license_path(self) -> None:
        footer = build_readme_footer("../../LICENSE")
        self.assertIn("[`LICENSE`](../../LICENSE)", footer)

    def test_generated_header_uses_explicit_target_project(self) -> None:
        header = build_html_header(
            title="Finja Overlay",
            version="2.3.0",
            description="OBS browser source",
            project="Finja - Twitch Interactivity Suite",
        )
        self.assertIn("Project: Finja - Twitch Interactivity Suite", header)
        self.assertNotIn("Project: J. Apps - AI-Coding Tooling", header)


class PrivatePathRegressionTests(unittest.TestCase):
    def test_absolute_windows_project_path_is_reported_in_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            separator = chr(92)
            private_path = f"Z:{separator}Bilder{separator}Streaming{separator}private-project"
            (root / "README.md").write_text(
                f"# Demo v1.0.1\n\ncd {private_path}\n"
                "\n## License\nMIT\n\n## Support\nJ. Apps\n",
                encoding="utf-8",
            )
            _, findings = scan_module(root, expected_version="1.0.1")
            self.assertTrue(any(item.rule == "private_path" for item in findings))

    def test_public_users_api_urls_are_not_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# Demo v1.0.1\n\n## License\nMIT\n\n## Support\nJ. Apps\n",
                encoding="utf-8",
            )
            (root / "overlay.html").write_text(
                FINJA_HTML_HEADER
                + '<script>fetch("https://7tv.io/v3/users/twitch/123")</script>\n',
                encoding="utf-8",
            )
            _, findings = scan_module(
                root, expected_version="1.0.1", require_headers=True
            )
            self.assertFalse(any(item.rule == "private_path" for item in findings))


PRIVATE_BYTES = b"Z:" + bytes([92]) + b"Users" + bytes([92]) + b"someone" + bytes([92]) + b"file"
README = "# Demo v1.0.1\n\n## License\nMIT\n\n## Support\nJ. Apps\n"


class BinaryAndIgnoreRegressionTests(unittest.TestCase):
    def _private_paths(self, root: Path) -> set[str]:
        _, findings = scan_module(root, expected_version="1.0.1")
        return {item.path for item in findings if item.rule == "private_path"}

    def test_binary_extensions_are_not_read_as_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(README, encoding="utf-8")
            for name in ("logo.png", "font.woff2", "tool.exe", "doc.pdf"):
                (root / name).write_bytes(b"junk " + PRIVATE_BYTES + b" junk")
            self.assertEqual(self._private_paths(root), set())

    def test_nul_byte_marks_unknown_extension_as_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(README, encoding="utf-8")
            (root / "blob.dat").write_bytes(b"\x00\x01" + PRIVATE_BYTES)
            (root / "notes.txt").write_bytes(PRIVATE_BYTES)
            self.assertEqual(self._private_paths(root), {"notes.txt"})

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_gitignored_files_are_skipped_inside_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("secret-stuff/\n", encoding="utf-8")
            (root / "README.md").write_text(README, encoding="utf-8")
            (root / "secret-stuff").mkdir()
            (root / "secret-stuff" / "notes.txt").write_bytes(PRIVATE_BYTES)
            (root / "kept.txt").write_bytes(PRIVATE_BYTES)
            profile, findings = scan_module(root, expected_version="1.0.1")
            paths = {item.path for item in findings if item.rule == "private_path"}
            self.assertEqual(paths, {"kept.txt"})
            self.assertIn("files:git", profile.signals)

    def test_filesystem_walk_outside_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(README, encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "notes.txt").write_bytes(PRIVATE_BYTES)
            profile, _ = scan_module(root, expected_version="1.0.1")
            if "files:git" in profile.signals:
                self.skipTest("temp directory lives inside a git repository")
            self.assertIn("files:walk", profile.signals)
            self.assertEqual(self._private_paths(root), {"sub/notes.txt"})


class GitHubRemoteRegressionTests(unittest.TestCase):
    def test_real_github_remote_forms_are_recognized(self) -> None:
        for remote in (
            "https://github.com/J-Apps/demo.git",
            "ssh://git@github.com/J-Apps/demo.git",
            "git@github.com:J-Apps/demo.git",
        ):
            with self.subTest(remote=remote):
                self.assertTrue(_has_github_remote(f"[remote \"origin\"]\nurl = {remote}\n"))

    def test_github_substrings_outside_exact_host_are_rejected(self) -> None:
        for remote in (
            "https://github.com.evil.example/J-Apps/demo.git",
            "https://evil.example/github.com/J-Apps/demo.git",
            "https://evil.example/?next=github.com",
        ):
            with self.subTest(remote=remote):
                self.assertFalse(_has_github_remote(f"[remote \"origin\"]\nurl = {remote}\n"))


if __name__ == "__main__":
    unittest.main()
