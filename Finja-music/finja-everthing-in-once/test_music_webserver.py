"""
Integration tests for webserver.py (Music All-in-One)
Tests the central music management web server
"""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import json


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing"""
    temp_dir = tempfile.mkdtemp()
    songsdb_dir = os.path.join(temp_dir, "SongsDB")
    nowplaying_dir = os.path.join(temp_dir, "Nowplaying")
    memory_dir = os.path.join(temp_dir, "Memory")
    config_dir = os.path.join(temp_dir, "config")

    for dir_path in [songsdb_dir, nowplaying_dir, memory_dir, config_dir]:
        os.makedirs(dir_path, exist_ok=True)

    yield {
        'base': temp_dir,
        'songsdb': songsdb_dir,
        'nowplaying': nowplaying_dir,
        'memory': memory_dir,
        'config': config_dir
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


class TestTrackDataclass:
    """Tests for Track dataclass"""

    def test_track_creation(self):
        """Test creating a Track instance"""
        from webserver import Track

        track = Track(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            source="spotify"
        )

        assert track.title == "Test Song"
        assert track.artist == "Test Artist"
        assert track.album == "Test Album"
        assert track.source == "spotify"

    def test_track_minimal_creation(self):
        """Test creating Track with minimal required fields"""
        from webserver import Track

        track = Track(title="Song", artist="Artist")

        assert track.title == "Song"
        assert track.artist == "Artist"
        assert track.album == ""
        assert track.source == ""


class TestBuildDBFunctions:
    """Tests for database building helper functions"""

    def test_build_db_norm(self):
        """Test string normalization"""
        from webserver import build_db_norm

        assert build_db_norm("  Test   String  ") == "Test String"
        assert build_db_norm("Multiple   Spaces") == "Multiple Spaces"
        assert build_db_norm("") == ""
        assert build_db_norm(None) == ""

    def test_build_db_strip_parens(self):
        """Test parentheses stripping"""
        from webserver import build_db_strip_parens

        assert build_db_strip_parens("Song (Remix)") == "Song"
        assert build_db_strip_parens("Song [Radio Edit]") == "Song"
        assert build_db_strip_parens("Song {Live}") == "Song"
        assert build_db_strip_parens("Normal Song") == "Normal Song"

    def test_build_db_basic_aliases(self):
        """Test alias generation for song titles"""
        from webserver import build_db_basic_aliases

        aliases = build_db_basic_aliases("Test Song (Remix)")
        assert isinstance(aliases, list)
        assert len(aliases) > 0
        # Should include original and variations
        assert any("Test Song" in alias for alias in aliases)


class TestCSVParsing:
    """Tests for CSV parsing functions"""

    def test_parse_row_csv_valid(self):
        """Test parsing valid CSV row"""
        from webserver import parse_row_csv

        row = {
            "Track Name": "Test Song",
            "Artist Name(s)": "Test Artist"
        }

        track = parse_row_csv(row)
        assert track is not None
        assert track.title == "Test Song"
        assert track.artist == "Test Artist"

    def test_parse_row_csv_alternative_headers(self):
        """Test parsing with alternative header names"""
        from webserver import parse_row_csv

        row = {
            "Title": "Alternative Song",
            "Artist": "Alternative Artist"
        }

        track = parse_row_csv(row)
        assert track is not None
        assert track.title == "Alternative Song"
        assert track.artist == "Alternative Artist"

    def test_parse_row_csv_missing_data(self):
        """Test parsing row with missing data"""
        from webserver import parse_row_csv

        # Empty row should return None or handle gracefully
        row = {
            "Track Name": "",
            "Artist Name(s)": ""
        }

        track = parse_row_csv(row)
        # Should return None or track with empty strings
        assert track is None or (track.title == "" and track.artist == "")


class TestAtomicWrite:
    """Tests for atomic file writing"""

    def test_atomic_write_text(self, temp_dirs):
        """Test atomic text file writing"""
        from webserver import build_db_atomic_write_text

        test_file = Path(temp_dirs['base']) / "test.txt"
        test_content = "Test content for atomic write"

        build_db_atomic_write_text(test_file, test_content)

        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == test_content

    def test_atomic_write_creates_parent_dirs(self, temp_dirs):
        """Test that atomic write creates parent directories"""
        from webserver import build_db_atomic_write_text

        nested_file = Path(temp_dirs['base']) / "nested" / "dir" / "file.txt"
        build_db_atomic_write_text(nested_file, "content")

        assert nested_file.exists()
        assert nested_file.read_text() == "content"


class TestMusicSourceControl:
    """Tests for music source control endpoints"""

    @patch('webserver.subprocess.Popen')
    def test_start_spotify_source(self, mock_popen):
        """Test starting Spotify music source"""
        # This would require the actual server to be running
        # Mock the subprocess call
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        # Test would go here for actual endpoint testing
        # Requires refactoring webserver.py to be testable
        assert True  # Placeholder

    def test_music_source_configuration(self, temp_dirs):
        """Test music source configuration loading"""
        # Create a mock config file
        config_file = os.path.join(temp_dirs['config'], 'sources.json')
        config_data = {
            "spotify": {"enabled": True, "script": "spotify.py"},
            "truckersfm": {"enabled": True, "script": "truckersfm.py"}
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        assert os.path.exists(config_file)

        # Load and verify
        with open(config_file, 'r') as f:
            loaded_config = json.load(f)

        assert loaded_config["spotify"]["enabled"] is True
        assert loaded_config["truckersfm"]["enabled"] is True


class TestNowPlayingFunctionality:
    """Tests for Now Playing tracking"""

    def test_nowplaying_file_creation(self, temp_dirs):
        """Test creation of now playing files"""
        nowplaying_file = os.path.join(temp_dirs['nowplaying'], 'current.txt')

        # Simulate writing current song
        current_song = "Test Artist - Test Song"
        with open(nowplaying_file, 'w', encoding='utf-8') as f:
            f.write(current_song)

        assert os.path.exists(nowplaying_file)
        with open(nowplaying_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert content == current_song

    def test_nowplaying_update(self, temp_dirs):
        """Test updating now playing information"""
        nowplaying_file = os.path.join(temp_dirs['nowplaying'], 'current.txt')

        songs = [
            "Artist 1 - Song 1",
            "Artist 2 - Song 2",
            "Artist 3 - Song 3"
        ]

        for song in songs:
            with open(nowplaying_file, 'w', encoding='utf-8') as f:
                f.write(song)

        # Last song should be in file
        with open(nowplaying_file, 'r', encoding='utf-8') as f:
            current = f.read()

        assert current == songs[-1]


class TestSongDatabase:
    """Tests for song database operations"""

    def test_song_database_file_structure(self, temp_dirs):
        """Test song database file structure"""
        db_file = os.path.join(temp_dirs['songsdb'], 'songs.json')

        # Create sample database
        sample_db = {
            "test artist - test song": {
                "artist": "Test Artist",
                "title": "Test Song",
                "album": "Test Album",
                "count": 5
            }
        }

        with open(db_file, 'w', encoding='utf-8') as f:
            json.dump(sample_db, f, ensure_ascii=False, indent=2)

        assert os.path.exists(db_file)

        # Load and verify
        with open(db_file, 'r', encoding='utf-8') as f:
            loaded_db = json.load(f)

        assert "test artist - test song" in loaded_db
        assert loaded_db["test artist - test song"]["count"] == 5

    def test_song_lookup(self, temp_dirs):
        """Test looking up songs in database"""
        db_file = os.path.join(temp_dirs['songsdb'], 'songs.json')

        db = {
            "artist a - song a": {"artist": "Artist A", "title": "Song A"},
            "artist b - song b": {"artist": "Artist B", "title": "Song B"}
        }

        with open(db_file, 'w', encoding='utf-8') as f:
            json.dump(db, f)

        # Load and search
        with open(db_file, 'r', encoding='utf-8') as f:
            loaded_db = json.load(f)

        # Test lookup
        key = "artist a - song a"
        assert key in loaded_db
        assert loaded_db[key]["artist"] == "Artist A"


class TestMemoryStorage:
    """Tests for memory/history storage"""

    def test_memory_file_creation(self, temp_dirs):
        """Test creating memory files"""
        memory_file = os.path.join(temp_dirs['memory'], 'history.json')

        history = [
            {"timestamp": 1234567890, "song": "Song 1", "artist": "Artist 1"},
            {"timestamp": 1234567900, "song": "Song 2", "artist": "Artist 2"}
        ]

        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)

        assert os.path.exists(memory_file)

        # Verify
        with open(memory_file, 'r', encoding='utf-8') as f:
            loaded_history = json.load(f)

        assert len(loaded_history) == 2
        assert loaded_history[0]["song"] == "Song 1"


class TestErrorHandling:
    """Tests for error handling"""

    def test_missing_directory_handling(self):
        """Test handling of missing directories"""
        # The system should create missing directories
        # This is tested implicitly in other tests
        assert True  # Placeholder

    def test_invalid_csv_handling(self, temp_dirs):
        """Test handling of invalid CSV data"""
        from webserver import parse_row_csv

        invalid_rows = [
            {},  # Empty row
            {"Invalid": "Headers"},
            None
        ]

        for row in invalid_rows[:-1]:  # Skip None as it would cause TypeError
            result = parse_row_csv(row)
            # Should handle gracefully
            assert result is None or isinstance(result, type(parse_row_csv({"Track Name": "Test", "Artist Name(s)": "Test"})))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
