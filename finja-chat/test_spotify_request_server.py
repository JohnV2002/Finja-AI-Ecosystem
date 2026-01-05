#!/usr/bin/env python3
"""
======================================================================
            Finja Spotify Request Server - Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.2.2
  Description: Unit tests for Spotify song request server.

  ✨ New in 2.2.2: -

  📜 New in 2.2.1:
    • Complete English documentation with docstrings
    • Improved test coverage for edge cases
    • Type hints for better IDE support
    • Better mocking of Spotify API
    • Additional validation tests
    • Tests for device selection logic
    • Tests for Finja reply messages

  📜 Changelog 2.1.0:
    • Initial test suite for song request server
    • Tests for health, devices, pending endpoints
    • Chat command validation tests
    • Cooldown enforcement tests
    • Moderator permission tests

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import time
from typing import Generator, Dict, Any


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture(autouse=True)
def mock_spotify() -> Generator:
    """
    Mock Spotify API client for all tests.
    
    Automatically mocks the Spotify client to avoid real API calls
    during testing. Provides default return values for common operations.
    
    Yields:
        Mock Spotify client instance
    """
    with patch('spotify_request_server_env.sp') as mock_sp:
        # Mock current playback
        mock_sp.current_playback.return_value = {
            'device': {'id': 'test_device', 'name': 'Test Device'},
            'is_playing': True
        }
        
        # Mock available devices
        mock_sp.devices.return_value = {
            'devices': [
                {
                    'id': 'device1',
                    'name': 'Test Device 1',
                    'is_active': True,
                    'type': 'Computer',
                    'volume_percent': 80
                },
                {
                    'id': 'device2',
                    'name': 'Test Device 2',
                    'is_active': False,
                    'type': 'Smartphone',
                    'volume_percent': 50
                }
            ]
        }
        
        # Mock track info
        mock_sp.track.return_value = {
            'id': 'test_track_id',
            'name': 'Test Song',
            'artists': [{'name': 'Test Artist'}],
            'album': {'name': 'Test Album'}
        }
        
        yield mock_sp


@pytest.fixture
def client() -> TestClient:
    """
    Create test client for FastAPI app.
    
    Imports the app after Spotify mocking is set up
    to ensure all imports use mocked dependencies.
    
    Returns:
        FastAPI TestClient instance
    """
    from spotify_request_server_env import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_cooldowns():
    """
    Reset cooldown state between tests.
    
    This fixture automatically runs before each test to ensure
    cooldowns from previous tests don't affect new tests.
    """
    from spotify_request_server_env import cooldown, pending, user_pending_count
    
    # Clear all state
    cooldown.clear()
    pending.clear()
    user_pending_count.clear()
    
    yield
    
    # Clean up after test
    cooldown.clear()
    pending.clear()
    user_pending_count.clear()


# ==============================================================================
# Health Endpoint Tests
# ==============================================================================

class TestHealthEndpoint:
    """
    Tests for /health endpoint.
    
    Verifies that the health check endpoint returns proper
    status information about the server.
    """

    def test_health_check_success(self, client: TestClient) -> None:
        """
        Test basic health check returns OK status.
        
        Verifies that the health endpoint is accessible and
        returns the expected response structure.
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "pending" in data

    def test_health_check_returns_pending_count(self, client: TestClient) -> None:
        """
        Test that health check includes pending request count.
        
        Verifies that the pending count is a valid integer.
        """
        response = client.get("/health")
        data = response.json()
        
        assert isinstance(data["pending"], int)
        assert data["pending"] >= 0


# ==============================================================================
# Devices Endpoint Tests
# ==============================================================================

class TestDevicesEndpoint:
    """
    Tests for /devices endpoint.
    
    Verifies that Spotify device listing works correctly.
    """

    def test_get_devices_success(self, client: TestClient) -> None:
        """
        Test retrieving available Spotify devices.
        
        Verifies that the endpoint returns a list of devices
        with proper structure.
        """
        response = client.get("/devices")
        
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert isinstance(data["devices"], list)

    def test_devices_have_required_fields(self, client: TestClient) -> None:
        """
        Test that device objects contain required fields.
        
        Verifies each device has id, name, type, is_active, and volume.
        """
        response = client.get("/devices")
        data = response.json()
        
        devices = data["devices"]
        if len(devices) > 0:
            device = devices[0]
            assert "id" in device
            assert "name" in device
            assert "type" in device
            assert "is_active" in device
            assert "volume" in device


# ==============================================================================
# Pending Endpoint Tests
# ==============================================================================

class TestPendingEndpoint:
    """
    Tests for /pending endpoint.
    
    Verifies that pending request listing works correctly.
    """

    def test_get_pending_requests_empty(self, client: TestClient) -> None:
        """
        Test retrieving pending requests when none exist.
        
        Verifies that the endpoint returns an empty list
        when no requests are pending.
        """
        response = client.get("/pending")
        
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert isinstance(data["pending"], list)

    def test_pending_request_structure(self, client: TestClient) -> None:
        """
        Test that pending requests have correct structure.
        
        Creates a request and verifies it appears in pending
        with all required fields.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [{
                        'uri': 'spotify:track:test123',
                        'name': 'Test Song',
                        'artists': [{'name': 'Test Artist'}]
                    }]
                }
            }
            
            # Create a pending request
            client.post("/chat", json={
                "user": "testuser",
                "message": "!sr Test Song",
                "is_mod": False,
                "is_broadcaster": False
            })
            
            # Check pending list
            response = client.get("/pending")
            data = response.json()
            
            if len(data["pending"]) > 0:
                request = data["pending"][0]
                assert "id" in request
                assert "title" in request
                assert "user" in request
                assert "ts" in request


# ==============================================================================
# Chat Endpoint Tests
# ==============================================================================

class TestChatEndpoint:
    """
    Tests for POST /chat endpoint.
    
    Verifies chat command processing and validation.
    """

    def test_chat_invalid_request_missing_fields(self, client: TestClient) -> None:
        """
        Test chat with missing required fields.
        
        Verifies that requests without required fields are rejected.
        """
        response = client.post("/chat", json={})
        assert response.status_code == 422  # Validation error

    def test_chat_basic_message_no_command(self, client: TestClient) -> None:
        """
        Test basic chat message without command.
        
        Verifies that non-command messages are handled gracefully.
        """
        response = client.post("/chat", json={
            "user": "testuser",
            "message": "Hello Finja!",
            "is_mod": False,
            "is_broadcaster": False
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "finja" in data

    def test_chat_unknown_command(self, client: TestClient) -> None:
        """
        Test unknown command is ignored.
        
        Verifies that unknown commands return empty response.
        """
        response = client.post("/chat", json={
            "user": "testuser",
            "message": "!unknowncommand",
            "is_mod": False,
            "is_broadcaster": False
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == ""
        assert data["finja"] == ""


# ==============================================================================
# Song Request Tests
# ==============================================================================

class TestSongRequests:
    """
    Tests for song request functionality.
    
    Verifies the complete flow of requesting and managing songs.
    """

    def test_song_request_valid_search(self, client: TestClient) -> None:
        """
        Test song request with valid search query.
        
        Verifies that a search query is processed and added to pending.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [{
                        'uri': 'spotify:track:abc123',
                        'name': 'Test Song',
                        'artists': [{'name': 'Test Artist'}]
                    }]
                }
            }
            mock_sp.track.return_value = {
                'name': 'Test Song',
                'artists': [{'name': 'Test Artist'}]
            }

            response = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr Test Song",
                "is_mod": False,
                "is_broadcaster": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "finja" in data
            assert "saved" in data["finja"].lower() or "taken" in data["finja"].lower()

    def test_song_request_spotify_uri(self, client: TestClient) -> None:
        """
        Test song request with direct Spotify URI.
        
        Verifies that Spotify URIs are handled correctly.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.track.return_value = {
                'name': 'Direct Song',
                'artists': [{'name': 'Direct Artist'}]
            }

            response = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr spotify:track:xyz789",
                "is_mod": False,
                "is_broadcaster": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "finja" in data

    def test_song_request_spotify_url(self, client: TestClient) -> None:
        """
        Test song request with Spotify URL.
        
        Verifies that Spotify URLs are parsed and processed.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.track.return_value = {
                'name': 'URL Song',
                'artists': [{'name': 'URL Artist'}]
            }

            response = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr https://open.spotify.com/track/abc123",
                "is_mod": False,
                "is_broadcaster": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "finja" in data

    def test_song_request_not_found(self, client: TestClient) -> None:
        """
        Test song request when no results found.
        
        Verifies that appropriate message is returned when
        search yields no results.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {'items': []}
            }

            response = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr NonexistentSongXYZ123",
                "is_mod": False,
                "is_broadcaster": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "finja" in data
            # Check for the actual "nohit" message from finja_reply
            assert "couldn't find" in data["finja"].lower() or "couldn't" in data["finja"].lower()


# ==============================================================================
# Cooldown Tests
# ==============================================================================

class TestCooldowns:
    """
    Tests for cooldown enforcement.
    
    Verifies that users are rate-limited appropriately.
    """

    def test_song_request_cooldown_enforcement(self, client: TestClient) -> None:
        """
        Test that cooldown is enforced for song requests.
        
        Verifies that a user cannot make multiple requests
        within the cooldown period.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [{
                        'uri': 'spotify:track:test',
                        'name': 'Song',
                        'artists': [{'name': 'Artist'}]
                    }]
                }
            }
            mock_sp.track.return_value = {
                'name': 'Song',
                'artists': [{'name': 'Artist'}]
            }

            # First request
            response1 = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr Song 1",
                "is_mod": False,
                "is_broadcaster": False
            })
            assert response1.status_code == 200

            # Second request immediately after (should be blocked)
            response2 = client.post("/chat", json={
                "user": "testuser",
                "message": "!sr Song 2",
                "is_mod": False,
                "is_broadcaster": False
            })
            
            data = response2.json()
            finja_msg = data.get("finja", "").lower()
            
            # Should contain cooldown message
            assert "cooldown" in finja_msg or "wait" in finja_msg or "breather" in finja_msg

    def test_moderator_bypass_cooldown(self, client: TestClient) -> None:
        """
        Test that moderators can bypass cooldown.
        
        Verifies that mods can make consecutive requests
        without waiting for cooldown.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [{
                        'uri': 'spotify:track:mod',
                        'name': 'Mod Song',
                        'artists': [{'name': 'Mod Artist'}]
                    }]
                }
            }
            mock_sp.track.return_value = {
                'name': 'Mod Song',
                'artists': [{'name': 'Mod Artist'}]
            }

            # Mods should not be subject to cooldown
            for i in range(3):
                response = client.post("/chat", json={
                    "user": "moduser",
                    "message": f"!sr Song {i}",
                    "is_mod": True,
                    "is_broadcaster": False
                })
                assert response.status_code == 200
                data = response.json()
                # Should not contain cooldown message
                assert "cooldown" not in data.get("finja", "").lower()

    def test_broadcaster_bypass_cooldown(self, client: TestClient) -> None:
        """
        Test that broadcaster can bypass cooldown.
        
        Verifies that the broadcaster has same privileges as mods.
        """
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [{
                        'uri': 'spotify:track:bc',
                        'name': 'BC Song',
                        'artists': [{'name': 'BC Artist'}]
                    }]
                }
            }
            mock_sp.track.return_value = {
                'name': 'BC Song',
                'artists': [{'name': 'BC Artist'}]
            }

            for i in range(2):
                response = client.post("/chat", json={
                    "user": "broadcaster",
                    "message": f"!sr Song {i}",
                    "is_mod": False,
                    "is_broadcaster": True
                })
                assert response.status_code == 200


# ==============================================================================
# Moderation Command Tests
# ==============================================================================

class TestModerationCommands:
    """
    Tests for moderator-only commands.
    
    Verifies that moderation commands require proper permissions.
    """

    def test_accept_command_permission_denied(self, client: TestClient) -> None:
        """
        Test that regular users cannot accept requests.
        
        Verifies that !accept is restricted to mods/broadcaster.
        """
        response = client.post("/chat", json={
            "user": "regularuser",
            "message": "!accept 1",
            "is_mod": False,
            "is_broadcaster": False
        })
        
        data = response.json()
        assert "only" in data.get("reply", "").lower() or "mods" in data.get("reply", "").lower()

    def test_deny_command_permission_denied(self, client: TestClient) -> None:
        """
        Test that regular users cannot deny requests.
        
        Verifies that !deny is restricted to mods/broadcaster.
        """
        response = client.post("/chat", json={
            "user": "regularuser",
            "message": "!deny 1",
            "is_mod": False,
            "is_broadcaster": False
        })
        
        data = response.json()
        assert "only" in data.get("reply", "").lower() or "mods" in data.get("reply", "").lower()

    def test_pending_list_permission_denied(self, client: TestClient) -> None:
        """
        Test that regular users cannot list pending requests.
        
        Verifies that !rq/!pending is restricted to mods/broadcaster.
        """
        response = client.post("/chat", json={
            "user": "regularuser",
            "message": "!rq",
            "is_mod": False,
            "is_broadcaster": False
        })
        
        data = response.json()
        assert "only" in data.get("reply", "").lower() or "mods" in data.get("reply", "").lower()

    def test_accept_command_as_mod(self, client: TestClient) -> None:
        """
        Test that mods can accept requests.
        
        Verifies that moderators have permission to use !accept.
        """
        # First create a pending request
        with patch('spotify_request_server_env.sp') as mock_sp:
            mock_sp.search.return_value = {
                'tracks': {
                    'items': [{
                        'uri': 'spotify:track:test',
                        'name': 'Test',
                        'artists': [{'name': 'Artist'}]
                    }]
                }
            }
            mock_sp.track.return_value = {
                'name': 'Test',
                'artists': [{'name': 'Artist'}]
            }
            mock_sp.add_to_queue.return_value = None

            client.post("/chat", json={
                "user": "viewer",
                "message": "!sr Test",
                "is_mod": False,
                "is_broadcaster": False
            })

            # Then try to accept it as mod
            response = client.post("/chat", json={
                "user": "moduser",
                "message": "!accept 1",
                "is_mod": True,
                "is_broadcaster": False
            })
            
            assert response.status_code == 200


# ==============================================================================
# Edge Case Tests
# ==============================================================================

class TestEdgeCases:
    """
    Tests for edge cases and error conditions.
    
    Verifies robust handling of unusual inputs.
    """

    def test_empty_song_request(self, client: TestClient) -> None:
        """
        Test song request without search query.
        
        Verifies that empty queries are handled gracefully.
        """
        response = client.post("/chat", json={
            "user": "testuser",
            "message": "!sr",
            "is_mod": False,
            "is_broadcaster": False
        })
        
        assert response.status_code == 200

    def test_invalid_accept_id(self, client: TestClient) -> None:
        """
        Test accept command with invalid ID format.
        
        Verifies that non-numeric IDs are rejected.
        """
        response = client.post("/chat", json={
            "user": "moduser",
            "message": "!accept abc",
            "is_mod": True,
            "is_broadcaster": False
        })
        
        data = response.json()
        assert "usage" in data.get("reply", "").lower()

    def test_accept_nonexistent_request(self, client: TestClient) -> None:
        """
        Test accepting a request that doesn't exist.
        
        Verifies appropriate error message for missing request.
        """
        response = client.post("/chat", json={
            "user": "moduser",
            "message": "!accept 999",
            "is_mod": True,
            "is_broadcaster": False
        })
        
        data = response.json()
        assert "not found" in data.get("reply", "").lower()


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == '__main__':
    """
    Run tests with verbose output when executed directly.
    
    Usage:
        python test_spotify_request_server.py
        
    Or with pytest:
        pytest test_spotify_request_server.py -v
    """
    pytest.main([__file__, '-v', '--color=yes'])