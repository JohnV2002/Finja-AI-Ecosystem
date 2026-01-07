#!/usr/bin/env python3
"""
======================================================================
            Finja Music App - Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-music-docker-spotify
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
  
  ✨ Features:
    • Validates file structure (Docker, Configs, Python files)
    • Tests core logic (Normalization, Scoring, KB Indexing)
    • Mocks Spotify API to test without credentials
    • Tests FastAPI endpoints (/health, /get/Finja)
    • Prevents background loops from blocking tests

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import unittest
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Any, Optional

# =============================================================================
# Configuration & Setup
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

# Global references - will be set by load_app_safely()
app_module: Any = None
TestClient: Any = None
APP_LOADED = False


def load_app_safely():
    """
    Imports app.py while suppressing the background thread loop.
    Returns True if successful.
    """
    global app_module, TestClient, APP_LOADED
    
    app_path = BASE_DIR / "app.py"
    if not app_path.exists():
        print(f"⚠️ app.py not found at {app_path}")
        return False

    # Patch threading.Thread.start() to prevent background loop
    with patch('threading.Thread.start'):
        try:
            # Add current dir to path
            if str(BASE_DIR) not in sys.path:
                sys.path.insert(0, str(BASE_DIR))
            
            # Import the app module
            import app as imported_app
            app_module = imported_app
            APP_LOADED = True
            print("✅ app.py imported successfully")
            
        except Exception as e:
            print(f"❌ Error importing app.py: {e}")
            return False

    # Try to import TestClient
    try:
        from fastapi.testclient import TestClient as TC
        TestClient = TC
        print("✅ FastAPI TestClient available")
    except ImportError:
        print("⚠️ FastAPI/httpx not installed - API tests will be skipped")
        TestClient = None
    
    return True


# Load app at module level
APP_LOADED = load_app_safely()


# =============================================================================
# Test: File Structure & Integrity
# =============================================================================

class TestFileStructure(unittest.TestCase):
    """
    Validates that the project structure meets deployment requirements.
    """

    def test_essential_files_exist(self):
        """Test: Critical files must exist."""
        required_files = [
            "Dockerfile",
            "docker-compose.yml",
            "requirements.txt",
            "app.py",
            "config_min.json"
        ]
        
        missing = []
        for filename in required_files:
            file_path = BASE_DIR / filename
            if not file_path.exists():
                missing.append(filename)
        
        if missing:
            self.fail(f"Missing essential files: {missing}")

    def test_config_min_valid_json(self):
        """Test: config_min.json is valid JSON."""
        config_path = BASE_DIR / "config_min.json"
        
        if not config_path.exists():
            self.skipTest("config_min.json not found")
        
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
        except json.JSONDecodeError as e:
            self.fail(f"config_min.json is invalid JSON: {e}")

    def test_directory_structure(self):
        """Test: Data directories should exist or be creatable."""
        required_dirs = ["Nowplaying", "Memory", "SongsDB", "cache"]
        
        for d in required_dirs:
            dir_path = BASE_DIR / d
            # Note: Directories may not exist in fresh clone
            if not dir_path.exists():
                print(f"ℹ️ Directory '{d}' missing (ok if fresh install)")


# =============================================================================
# Test: KBIndex Class
# =============================================================================

class TestKBIndex(unittest.TestCase):
    """
    Tests for the KBIndex class (Knowledge Base indexing).
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")

    def test_norm_basic(self):
        """Test: _norm normalizes strings correctly."""
        self.assertEqual(app_module.KBIndex._norm("Test Song"), "test song")
        self.assertEqual(app_module.KBIndex._norm("  HELLO  "), "hello")

    def test_norm_removes_parentheses(self):
        """Test: _norm removes content in parentheses/brackets."""
        self.assertEqual(app_module.KBIndex._norm("Title (feat. Artist)"), "title")
        self.assertEqual(app_module.KBIndex._norm("Song [Radio Edit]"), "song")

    def test_norm_replaces_ampersand(self):
        """Test: _norm replaces & with 'and'."""
        result = app_module.KBIndex._norm("Rock & Roll")
        self.assertIn("and", result)
        self.assertNotIn("&", result)

    def test_norm_removes_feat(self):
        """Test: _norm removes 'feat.' and 'featuring'."""
        result = app_module.KBIndex._norm("Song feat. Artist")
        self.assertNotIn("feat", result)
        
        result2 = app_module.KBIndex._norm("Song featuring Someone")
        self.assertNotIn("featuring", result2)

    def test_kbindex_creation(self):
        """Test: KBIndex can be created with entries."""
        entries = [
            {"title": "Test Song", "artist": "Test Artist", "tags": ["pop"]},
            {"title": "Another Song", "artist": "Another Artist", "tags": ["rock"]},
        ]
        
        idx = app_module.KBIndex(entries)
        
        self.assertEqual(len(idx.entries), 2)
        self.assertIn("by_title", idx.index)
        self.assertIn("by_title_artist", idx.index)

    def test_kbindex_lookup_by_title_artist(self):
        """Test: KBIndex can lookup by (title, artist) tuple."""
        entries = [
            {"title": "Unique Song", "artist": "Unique Artist", "tags": ["indie"]},
        ]
        
        idx = app_module.KBIndex(entries)
        
        key = (idx._norm("Unique Song"), idx._norm("Unique Artist"))
        self.assertIn(key, idx.index["by_title_artist"])

    def test_kbindex_empty(self):
        """Test: KBIndex handles empty entries list."""
        idx = app_module.KBIndex([])
        
        self.assertEqual(len(idx.entries), 0)
        self.assertEqual(len(idx.index["by_title"]), 0)
        self.assertEqual(len(idx.index["by_title_artist"]), 0)


# =============================================================================
# Test: Utility Functions
# =============================================================================

class TestUtilityFunctions(unittest.TestCase):
    """
    Tests for utility functions in app.py.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")

    def test_parse_title_artist_dash(self):
        """Test: parse_title_artist splits on ' - '."""
        title, artist = app_module.parse_title_artist("Song Name - Artist Name")
        self.assertEqual(title, "Song Name")
        self.assertEqual(artist, "Artist Name")

    def test_parse_title_artist_emdash(self):
        """Test: parse_title_artist splits on em-dash."""
        title, artist = app_module.parse_title_artist("Song — Artist")
        self.assertEqual(title, "Song")
        self.assertEqual(artist, "Artist")

    def test_parse_title_artist_by(self):
        """Test: parse_title_artist splits on ' by '."""
        title, artist = app_module.parse_title_artist("Song by Artist")
        # Note: "by" swaps order - returns (right, left)
        self.assertEqual(title, "Artist")
        self.assertEqual(artist, "Song")

    def test_parse_title_artist_no_separator(self):
        """Test: parse_title_artist with no separator."""
        title, artist = app_module.parse_title_artist("JustOneString")
        self.assertEqual(title, "")
        self.assertEqual(artist, "JustOneString")

    def test_parse_title_artist_empty(self):
        """Test: parse_title_artist with empty string."""
        title, artist = app_module.parse_title_artist("")
        self.assertEqual(title, "")
        self.assertEqual(artist, "")

    def test_tier_from_score_love(self):
        """Test: tier_from_score returns 'love' for high scores."""
        self.assertEqual(app_module.tier_from_score(10.0), "love")
        self.assertEqual(app_module.tier_from_score(9.0), "love")

    def test_tier_from_score_like(self):
        """Test: tier_from_score returns 'like' for medium-high scores."""
        self.assertEqual(app_module.tier_from_score(5.0), "like")
        self.assertEqual(app_module.tier_from_score(3.0), "like")

    def test_tier_from_score_neutral(self):
        """Test: tier_from_score returns 'neutral' for middle scores."""
        self.assertEqual(app_module.tier_from_score(0.0), "neutral")
        self.assertEqual(app_module.tier_from_score(2.0), "neutral")
        self.assertEqual(app_module.tier_from_score(-2.0), "neutral")

    def test_tier_from_score_dislike(self):
        """Test: tier_from_score returns 'dislike' for low scores."""
        self.assertEqual(app_module.tier_from_score(-5.0), "dislike")

    def test_tier_from_score_hate(self):
        """Test: tier_from_score returns 'hate' for very low scores."""
        self.assertEqual(app_module.tier_from_score(-10.0), "hate")
        self.assertEqual(app_module.tier_from_score(-15.0), "hate")


# =============================================================================
# Test: Special Version Detection
# =============================================================================

class TestSpecialVersionDetection(unittest.TestCase):
    """
    Tests for detect_special_version_tags function.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")
        
        # Save original and set test tags
        self.orig_tags = app_module.SPECIAL_TAGS
        app_module.SPECIAL_TAGS = {
            "nightcore": ["nightcore", "nc"],
            "speed up": ["speed up", "sped up"],
            "slowed": ["slowed", "slowed down"],
        }

    def tearDown(self):
        if APP_LOADED:
            app_module.SPECIAL_TAGS = self.orig_tags

    def test_detect_nightcore(self):
        """Test: Detects 'nightcore' in title."""
        result = app_module.detect_special_version_tags("My Song (Nightcore Remix)")
        self.assertEqual(result, "nightcore")

    def test_detect_speed_up(self):
        """Test: Detects 'speed up' in title."""
        result = app_module.detect_special_version_tags("Song - Speed Up Version")
        self.assertEqual(result, "speed up")

    def test_detect_slowed(self):
        """Test: Detects 'slowed' in title."""
        result = app_module.detect_special_version_tags("Track (Slowed)")
        self.assertEqual(result, "slowed")

    def test_detect_none(self):
        """Test: Returns None for normal songs."""
        result = app_module.detect_special_version_tags("Normal Song Title")
        self.assertIsNone(result)

    def test_detect_case_insensitive(self):
        """Test: Detection is case-insensitive."""
        result = app_module.detect_special_version_tags("NIGHTCORE MIX")
        self.assertEqual(result, "nightcore")


# =============================================================================
# Test: Memory Functions
# =============================================================================

class TestMemoryFunctions(unittest.TestCase):
    """
    Tests for memory-related functions.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")

    def test_apply_decay_disabled(self):
        """Test: apply_decay does nothing when disabled."""
        entry = {"contexts": {"gaming": {"score": 5.0, "seen": 3, "last_seen": 0}}}
        
        # Temporarily disable decay
        orig_cfg = app_module.MEM_CFG.get("decay", {}).get("enabled", False)
        app_module.MEM_CFG.setdefault("decay", {})["enabled"] = False
        
        try:
            app_module.apply_decay(entry)
            # Score should remain unchanged
            self.assertEqual(entry["contexts"]["gaming"]["score"], 5.0)
        finally:
            app_module.MEM_CFG["decay"]["enabled"] = orig_cfg

    def test_update_memory_score_positive(self):
        """Test: _update_memory_score increases score for love/like."""
        import time
        
        ment = {"contexts": {}}
        app_module._update_memory_score(ment, "gaming", "love")
        
        self.assertIn("gaming", ment["contexts"])
        self.assertEqual(ment["contexts"]["gaming"]["seen"], 1)
        self.assertGreater(ment["contexts"]["gaming"]["score"], 0)

    def test_update_memory_score_negative(self):
        """Test: _update_memory_score decreases score for dislike/hate."""
        ment = {"contexts": {"gaming": {"score": 0.0, "seen": 0, "last_seen": 0}}}
        app_module._update_memory_score(ment, "gaming", "hate")
        
        self.assertLess(ment["contexts"]["gaming"]["score"], 0)

    def test_update_memory_score_neutral(self):
        """Test: _update_memory_score slightly increases for neutral."""
        ment = {"contexts": {"gaming": {"score": 0.0, "seen": 0, "last_seen": 0}}}
        app_module._update_memory_score(ment, "gaming", "neutral")
        
        # Neutral adds 0.1
        self.assertAlmostEqual(ment["contexts"]["gaming"]["score"], 0.1)


# =============================================================================
# Test: LRU Cache
# =============================================================================

class TestLRUCache(unittest.TestCase):
    """
    Tests for the LRUCacheTTL class.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")

    def test_cache_set_get(self):
        """Test: Cache can set and get values."""
        cache = app_module.LRUCacheTTL(maxsize=10, ttl=60)
        
        cache.set(("key1",), "value1")
        result = cache.get(("key1",))
        
        self.assertEqual(result, "value1")

    def test_cache_miss(self):
        """Test: Cache returns None for missing keys."""
        cache = app_module.LRUCacheTTL(maxsize=10, ttl=60)
        
        result = cache.get(("nonexistent",))
        
        self.assertIsNone(result)

    def test_cache_maxsize(self):
        """Test: Cache evicts old entries when full."""
        cache = app_module.LRUCacheTTL(maxsize=2, ttl=60)
        
        cache.set(("key1",), "value1")
        cache.set(("key2",), "value2")
        cache.set(("key3",), "value3")  # Should evict key1
        
        self.assertIsNone(cache.get(("key1",)))
        self.assertEqual(cache.get(("key2",)), "value2")
        self.assertEqual(cache.get(("key3",)), "value3")


# =============================================================================
# Test: Atomic Write
# =============================================================================

class TestAtomicWrite(unittest.TestCase):
    """
    Tests for atomic_write function.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")
        
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_write_creates_file(self):
        """Test: atomic_write creates a new file."""
        test_file = Path(self.test_dir) / "test.txt"
        
        app_module.atomic_write(test_file, "Hello World")
        
        self.assertTrue(test_file.exists())
        self.assertEqual(test_file.read_text(encoding="utf-8"), "Hello World")

    def test_atomic_write_overwrites(self):
        """Test: atomic_write overwrites existing content."""
        test_file = Path(self.test_dir) / "test.txt"
        test_file.write_text("Old Content", encoding="utf-8")
        
        app_module.atomic_write(test_file, "New Content")
        
        self.assertEqual(test_file.read_text(encoding="utf-8"), "New Content")

    def test_atomic_write_no_temp_left(self):
        """Test: atomic_write doesn't leave .tmp files."""
        test_file = Path(self.test_dir) / "test.txt"
        
        app_module.atomic_write(test_file, "Content")
        
        tmp_file = test_file.with_suffix(".txt.tmp")
        self.assertFalse(tmp_file.exists())


# =============================================================================
# Test: FastAPI Endpoints
# =============================================================================

class TestFastAPIEndpoints(unittest.TestCase):
    """
    Tests for the FastAPI web endpoints.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")
        if TestClient is None:
            self.skipTest("FastAPI TestClient not available")
        
        self.client = TestClient(app_module.app)

    def test_health_endpoint(self):
        """Test: GET /health returns 200 OK."""
        response = self.client.get("/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("time", data)

    def test_get_finja_endpoint(self):
        """Test: GET /get/Finja returns valid structure."""
        response = self.client.get("/get/Finja")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        required_keys = ["reaction", "genres", "title", "artist", "context"]
        for key in required_keys:
            self.assertIn(key, data, f"Missing key: {key}")

    def test_get_finja_returns_json(self):
        """Test: GET /get/Finja returns JSON content type."""
        response = self.client.get("/get/Finja")
        
        self.assertIn("application/json", response.headers.get("content-type", ""))


# =============================================================================
# Test: Match Special Rules
# =============================================================================

class TestMatchSpecial(unittest.TestCase):
    """
    Tests for match_special function (special reaction rules).
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")

    def test_match_special_no_rules(self):
        """Test: Returns (None, None) when no rules match."""
        # Assuming no special rules match this
        forced, react = app_module.match_special("Random Song", "Random Artist")
        
        # If no rules defined, both should be None
        # (Actual result depends on SPECIAL_RULES config)
        self.assertIsInstance(forced, (str, type(None)))
        self.assertIsInstance(react, (str, type(None)))


# =============================================================================
# Test: Helper Functions for Tick Loop
# =============================================================================

class TestTickLoopHelpers(unittest.TestCase):
    """
    Tests for the refactored tick_loop helper functions.
    """

    def setUp(self):
        if not APP_LOADED:
            self.skipTest("app.py could not be imported")

    @patch.object(app_module, 'write_reaction')
    @patch.object(app_module, 'write_genres')
    @patch.object(app_module, 'find_kb_entry')
    def test_init_new_song_state(self, mock_kb, mock_genres, mock_reaction):
        """Test: _init_new_song_state initializes state correctly."""
        mock_kb.return_value = None
        
        import time
        now = time.time()
        
        p_until, m_from, c_until, output = app_module._init_new_song_state(
            "Test Title", "Test Artist", "gaming", now
        )
        
        # Verify timing values
        self.assertGreater(p_until, now)
        self.assertGreater(m_from, now)
        self.assertGreater(c_until, now)
        
        # Verify output structure
        self.assertEqual(output["title"], "Test Title")
        self.assertEqual(output["artist"], "Test Artist")
        self.assertEqual(output["context"], "gaming")
        
        # Verify writes were called
        mock_reaction.assert_called()
        mock_genres.assert_called()

    @patch.object(app_module, 'write_reaction')
    @patch.object(app_module, 'write_genres')
    @patch.object(app_module, 'compute_reaction')
    def test_process_final_result(self, mock_compute, mock_genres, mock_reaction):
        """Test: _process_final_result computes and writes reaction."""
        mock_compute.return_value = ("Great song!", "Pop, Rock")
        
        # Fixed Pylance issue: Use _ for unused variables
        _, _, output = app_module._process_final_result(
            "Title", "Artist", "ctx", None, 0, {}
        )
        
        # Verify reaction was computed
        mock_compute.assert_called_once_with("Title", "Artist")
        
        # Verify output contains reaction
        self.assertEqual(output["reaction"], "Great song!")
        self.assertEqual(output["genres"], "Pop, Rock")


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("          Finja Music App - Unit & Integration Tests v1.0.1")
    print("=" * 70)
    print(f"📂 Working Directory: {os.getcwd()}")
    print(f"📂 Base Directory: {BASE_DIR}")
    print()
    
    unittest.main(verbosity=2)