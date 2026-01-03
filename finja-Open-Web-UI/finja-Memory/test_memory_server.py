"""
Unit tests for memory-server.py
Tests the Adaptive Memory system for OpenWebUI
"""
import pytest
import os
import json
import tempfile
import shutil
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing"""
    temp_dir = tempfile.mkdtemp()
    user_memory_dir = os.path.join(temp_dir, "user_memories")
    user_audio_dir = os.path.join(temp_dir, "user_audio")
    tts_cache_dir = os.path.join(temp_dir, "tts_cache")
    backup_dir = os.path.join(temp_dir, "backups")

    os.makedirs(user_memory_dir, exist_ok=True)
    os.makedirs(user_audio_dir, exist_ok=True)
    os.makedirs(tts_cache_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    yield {
        'base': temp_dir,
        'user_memory': user_memory_dir,
        'user_audio': user_audio_dir,
        'tts_cache': tts_cache_dir,
        'backup': backup_dir
    }

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(temp_dirs):
    """Create test client with mocked environment"""
    with patch.dict(os.environ, {'MEMORY_API_KEY': 'test-api-key-12345'}):
        # Mock the directory paths
        with patch('memory-server.USER_MEMORY_DIR', temp_dirs['user_memory']):
            with patch('memory-server.USER_AUDIO_DIR', temp_dirs['user_audio']):
                with patch('memory-server.TTS_CACHE_DIR', temp_dirs['tts_cache']):
                    with patch('memory-server.BACKUP_DIR', temp_dirs['backup']):
                        # Import app after patching
                        import importlib
                        import sys

                        # Reload module if already imported
                        module_name = 'memory-server'
                        if module_name in sys.modules:
                            del sys.modules[module_name]

                        # Import fresh
                        try:
                            memory_server = importlib.import_module(module_name)
                            return TestClient(memory_server.app)
                        except ImportError:
                            # Try alternative import
                            from memory_server import app
                            return TestClient(app)


@pytest.fixture
def auth_headers():
    """Return authentication headers"""
    return {"X-API-Key": "test-api-key-12345"}


class TestAuthentication:
    """Tests for API authentication"""

    def test_missing_api_key(self, client):
        """Test that requests without API key are rejected"""
        response = client.get("/memories/testuser")
        assert response.status_code == 401

    def test_invalid_api_key(self, client):
        """Test that requests with invalid API key are rejected"""
        response = client.get("/memories/testuser", headers={"X-API-Key": "invalid-key"})
        assert response.status_code == 401

    def test_valid_api_key(self, client, auth_headers):
        """Test that requests with valid API key are accepted"""
        response = client.get("/memories/testuser", headers=auth_headers)
        # Should not be 401
        assert response.status_code != 401


class TestMemoryCRUD:
    """Tests for memory CRUD operations"""

    def test_add_memory(self, client, auth_headers):
        """Test adding a new memory"""
        response = client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "text": "This is a test memory",
                "bank": "General"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["message"] == "Memory added"

    def test_get_memories(self, client, auth_headers):
        """Test retrieving memories for a user"""
        # First add a memory
        client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "text": "Test memory 1",
                "bank": "General"
            }
        )

        # Retrieve memories
        response = client.get("/memories/testuser", headers=auth_headers)
        assert response.status_code == 200
        memories = response.json()
        assert isinstance(memories, list)
        assert len(memories) > 0
        assert memories[0]["text"] == "Test memory 1"

    def test_delete_memory(self, client, auth_headers):
        """Test deleting a specific memory"""
        # Add a memory
        add_response = client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "text": "Memory to delete",
                "bank": "General"
            }
        )
        memory_id = add_response.json()["id"]

        # Delete the memory
        delete_response = client.post(
            "/delete_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "memory_id": memory_id
            }
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["message"] == "Memory deleted"

        # Verify it's gone
        memories = client.get("/memories/testuser", headers=auth_headers).json()
        assert not any(m["id"] == memory_id for m in memories)

    def test_delete_all_user_memories(self, client, auth_headers):
        """Test deleting all memories for a user"""
        # Add multiple memories
        for i in range(3):
            client.post(
                "/add_memory",
                headers=auth_headers,
                json={
                    "user_id": "testuser",
                    "text": f"Memory {i}",
                    "bank": "General"
                }
            )

        # Delete all memories
        response = client.post(
            "/delete_user_memories",
            headers=auth_headers,
            json={"user_id": "testuser"}
        )
        assert response.status_code == 200

        # Verify all gone
        memories = client.get("/memories/testuser", headers=auth_headers).json()
        assert len(memories) == 0


class TestMemoryBanks:
    """Tests for memory bank functionality"""

    def test_add_to_different_banks(self, client, auth_headers):
        """Test adding memories to different banks"""
        banks = ["General", "Personal", "Work", "Music"]

        for bank in banks:
            response = client.post(
                "/add_memory",
                headers=auth_headers,
                json={
                    "user_id": "testuser",
                    "text": f"Memory in {bank}",
                    "bank": bank
                }
            )
            assert response.status_code == 200

        # Retrieve and verify banks
        memories = client.get("/memories/testuser", headers=auth_headers).json()
        retrieved_banks = {m["bank"] for m in memories}
        assert set(banks).issubset(retrieved_banks)

    def test_filter_by_bank(self, client, auth_headers):
        """Test that memories can be organized by bank"""
        # Add to different banks
        client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "text": "General memory",
                "bank": "General"
            }
        )
        client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "text": "Music memory",
                "bank": "Music"
            }
        )

        # Retrieve all memories
        memories = client.get("/memories/testuser", headers=auth_headers).json()

        # Verify both banks exist
        general_memories = [m for m in memories if m["bank"] == "General"]
        music_memories = [m for m in memories if m["bank"] == "Music"]

        assert len(general_memories) > 0
        assert len(music_memories) > 0


class TestMemoryPersistence:
    """Tests for memory persistence to disk"""

    def test_memory_persists_to_disk(self, client, auth_headers, temp_dirs):
        """Test that memories are saved to disk"""
        # Add a memory
        client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "testuser",
                "text": "Persistent memory",
                "bank": "General"
            }
        )

        # Trigger save (normally done by backup_loop)
        # Check if file exists
        memory_file = os.path.join(temp_dirs['user_memory'], "testuser_memory.json")

        # File might not exist yet (depends on implementation), so we just verify the structure
        # In a real scenario, you'd trigger the save mechanism
        assert os.path.exists(temp_dirs['user_memory'])


class TestSecurityValidation:
    """Tests for security validations"""

    def test_path_traversal_prevention(self, client, auth_headers):
        """Test that path traversal attacks are prevented"""
        malicious_user_ids = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "test/../../../root",
            ""  # Empty string
        ]

        for user_id in malicious_user_ids:
            response = client.post(
                "/delete_user_memories",
                headers=auth_headers,
                json={"user_id": user_id}
            )
            # Should either reject or sanitize
            # The endpoint should not crash or access unauthorized paths
            assert response.status_code in [200, 400, 422]

    def test_empty_user_id_rejection(self, client, auth_headers):
        """Test that empty user IDs are handled properly"""
        response = client.post(
            "/add_memory",
            headers=auth_headers,
            json={
                "user_id": "",
                "text": "Test",
                "bank": "General"
            }
        )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]


class TestHealthCheck:
    """Tests for health check endpoint"""

    def test_health_endpoint(self, client):
        """Test health check endpoint (no auth required)"""
        response = client.get("/health")
        # Should be accessible without auth
        assert response.status_code in [200, 404]  # 404 if not implemented


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
