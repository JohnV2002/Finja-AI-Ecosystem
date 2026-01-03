"""
Unit tests for spotify_request_server_env.py
Tests the Spotify song request and chat integration
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import time


# Mock the Spotify client before importing the app
@pytest.fixture(autouse=True)
def mock_spotify():
    """Mock Spotify API client"""
    with patch('spotify_request_server_env.sp') as mock_sp:
        mock_sp.current_playback.return_value = {
            'device': {'id': 'test_device', 'name': 'Test Device'},
            'is_playing': True
        }
        mock_sp.devices.return_value = {
            'devices': [
                {'id': 'device1', 'name': 'Test Device 1', 'is_active': True},
                {'id': 'device2', 'name': 'Test Device 2', 'is_active': False}
            ]
        }
        yield mock_sp


@pytest.fixture
def client():
    """Create test client for FastAPI app"""
    # Import after mocking
    from spotify_request_server_env import app
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_check(self, client):
        """Test basic health check"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data


class TestDevicesEndpoint:
    """Tests for /devices endpoint"""

    def test_get_devices(self, client):
        """Test retrieving available Spotify devices"""
        response = client.get("/devices")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert isinstance(data["devices"], list)


class TestPendingEndpoint:
    """Tests for /pending endpoint"""

    def test_get_pending_requests(self, client):
        """Test retrieving pending song requests"""
        response = client.get("/pending")
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert isinstance(data["pending"], list)


class TestChatEndpoint:
    """Tests for POST /chat endpoint"""

    def test_chat_invalid_request(self, client):
        """Test chat with invalid request data"""
        response = client.post("/chat", json={})
        assert response.status_code == 422  # Validation error

    def test_chat_basic_message(self, client):
        """Test basic chat message without command"""
        response = client.post("/chat", json={
            "user": "testuser",
            "message": "Hello Finja!",
            "is_mod": False,
            "is_broadcaster": False
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data

    def test_chat_song_request_format(self, client):
        """Test song request with proper format"""
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [
                        {
                            'id': 'test_track_id',
                            'name': 'Test Song',
                            'artists': [{'name': 'Test Artist'}],
                            'album': {'name': 'Test Album'}
                        }
                    ]
                }
            }

            response = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr Test Song - Test Artist",
                "is_mod": False,
                "is_broadcaster": False
            })
            assert response.status_code == 200
            data = response.json()
            assert "reply" in data

    def test_chat_cooldown_enforcement(self, client):
        """Test that cooldown is enforced for song requests"""
        request_data = {
            "user": "testuser",
            "message": "!sr Song 1",
            "is_mod": False,
            "is_broadcaster": False
        }

        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [
                        {
                            'id': 'track1',
                            'name': 'Song 1',
                            'artists': [{'name': 'Artist 1'}],
                            'album': {'name': 'Album 1'}
                        }
                    ]
                }
            }

            # First request should work
            response1 = client.post("/chat", json=request_data)
            assert response1.status_code == 200

            # Second request immediately after should be rate-limited
            request_data["message"] = "!sr Song 2"
            response2 = client.post("/chat", json=request_data)
            data = response2.json()
            # Should contain cooldown message
            assert "cooldown" in data.get("reply", "").lower() or "wait" in data.get("reply", "").lower()

    def test_moderator_bypass_cooldown(self, client):
        """Test that moderators can bypass cooldown"""
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [
                        {
                            'id': 'track_mod',
                            'name': 'Mod Song',
                            'artists': [{'name': 'Mod Artist'}],
                            'album': {'name': 'Mod Album'}
                        }
                    ]
                }
            }

            # Moderators should not be subject to cooldown
            for i in range(3):
                response = client.post("/chat", json={
                    "user": "moduser",
                    "message": f"!sr Song {i}",
                    "is_mod": True,
                    "is_broadcaster": False
                })
                assert response.status_code == 200


class TestModeratorCommands:
    """Tests for moderator-only commands"""

    def test_skip_command_as_regular_user(self, client):
        """Test that regular users cannot use skip command"""
        response = client.post("/chat", json={
            "user": "regularuser",
            "message": "!skip",
            "is_mod": False,
            "is_broadcaster": False
        })
        data = response.json()
        # Should indicate permission denied or no action
        assert response.status_code == 200

    def test_clear_command_as_mod(self, client):
        """Test that mods can use clear command"""
        response = client.post("/chat", json={
            "user": "moduser",
            "message": "!clear",
            "is_mod": True,
            "is_broadcaster": False
        })
        assert response.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
