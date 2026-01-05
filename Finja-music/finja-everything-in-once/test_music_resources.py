#!/usr/bin/env python3
"""
======================================================================
                  Finja Music Ecosystem - Resource Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0

  ✨ New in 1.1.0:
    • Complete English documentation
    • Comprehensive endpoint tests
    • HTML functionality tests
    • Helper script tests
    • Mock server for isolated testing
    • Path validation security tests

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os
import pytest
import py_compile

# Base directory for relative paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class TestMusicResources:
    """
    Validates static resources and helper scripts.
    """

    # ==========================================================================
    # 1. OBS HTML Files Tests
    # ==========================================================================
    def test_obs_html_files_exist(self):
        """
        Verifies that all required OBS HTML overlays exist.
        """
        obs_dir = os.path.join(BASE_DIR, "OBSHTML")
        required_files = [
            "ArtistNotSure.html",
            "Musik.html",
            "Sodakiller_NowPlaying_MDR.html",
            "Sodakiller_NowPlaying_RTL_Bright.html",
            "Sodakiller_NowPlaying_Spotify.html",
            "Sodakiller_NowPlaying_TFM_Bright.html"
        ]

        assert os.path.isdir(obs_dir), "OBSHTML directory is missing!"

        for filename in required_files:
            file_path = os.path.join(obs_dir, filename)
            assert os.path.exists(file_path), f"Missing OBS Overlay: {filename}"

    # ==========================================================================
    # 2. Helper Scripts Syntax Tests (MDR & RTL)
    # ==========================================================================
    def test_rtl_helper_syntax(self):
        """
        Checks if RTL89 helper scripts are valid Python.
        """
        rtl_dir = os.path.join(BASE_DIR, "RTLHilfe")
        scripts = ["rtl89_cdp_nowplaying.py", "rtl_repeat_counter.py"]

        assert os.path.isdir(rtl_dir), "RTLHilfe directory is missing!"

        for script in scripts:
            path = os.path.join(rtl_dir, script)
            assert os.path.exists(path), f"Missing script: {script}"
            # Try to compile to check for syntax errors
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                pytest.fail(f"Syntax error in {script}: {e}")

    def test_mdr_helper_syntax(self):
        """
        Checks if MDR helper scripts are valid Python.
        """
        mdr_dir = os.path.join(BASE_DIR, "MDRHilfe")
        script = "mdr_nowplaying.py"
        
        path = os.path.join(mdr_dir, script)
        assert os.path.exists(path), f"Missing script: {script}"
        
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"Syntax error in {script}: {e}")

    # ==========================================================================
    # 3. Batch Files Integrity Tests
    # ==========================================================================
    def test_batch_files_integrity(self):
        """
        Checks if .bat files exist and reference Python.
        """
        # List of batch files to check -> (Directory, Filename)
        batch_files = [
            (".", "start_server.bat"),
            ("RTLHilfe", "start_rtl_cdp.bat"),
            ("MDRHilfe", "start_mdr_nowplaying.bat")
        ]

        for directory, filename in batch_files:
            path = os.path.join(BASE_DIR, directory, filename)
            assert os.path.exists(path), f"Missing batch file: {directory}/{filename}"
            
            # Check content
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                # Assuming these scripts should start python scripts
                # We check for 'python' keyword to ensure they do something meaningful
                assert "python" in content, f"{filename} does not appear to call Python"

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--color=yes'])