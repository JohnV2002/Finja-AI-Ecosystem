#!/usr/bin/env python3
"""
======================================================================
                  Finja Startup Script - Sanity Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Validates that Windows startup scripts exist and 
               reference the correct Python entry points.

  Note: These tests do NOT execute the batch files (which would block),
        but inspect their content to ensure integrity.

----------------------------------------------------------------------    
    
  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os
import pytest

# Define paths relative to this test file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class TestStartupScripts:
    """
    Checks integrity of Windows batch files (.bat).
    """

    def test_server_startup_script_integrity(self):
        """
        Validates 'start_server_with_env.bat'.
        
        Checks:
        1. File exists
        2. References the correct python server file
        """
        bat_path = os.path.join(BASE_DIR, "start_server_with_env.bat")
        
        # 1. Check existence
        assert os.path.exists(bat_path), "start_server_with_env.bat missing!"
        
        # 2. Check content logic
        with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
            
            # Must invoke python
            assert "python" in content, "Script does not call Python"
            
            # Must target the spotify server
            assert "spotify_request_server_env.py" in content, \
                "Script does not launch spotify_request_server_env.py"

    def test_static_server_script_integrity(self):
        """
        Validates 'start_static_server.bat'.
        
        Checks:
        1. File exists
        2. Starts a simple HTTP server (usually python -m http.server)
        """
        bat_path = os.path.join(BASE_DIR, "start_static_server.bat")
        
        # 1. Check existence
        assert os.path.exists(bat_path), "start_static_server.bat missing!"
        
        # 2. Check content logic
        with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
            
            # Should invoke python's http.server module or similar
            # Checking for 'http.server' covers 'python -m http.server'
            assert "http.server" in content or "python" in content, \
                "Script does not appear to start a Python web server"

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--color=yes'])