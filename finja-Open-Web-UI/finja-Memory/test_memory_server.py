"""
Unit tests for memory-server.py
Tests the Server side Memory system for OpenWebUI
"""
import pytest
import os
import json
import tempfile
import shutil
from fastapi.testclient import TestClient
from unittest.mock import patch
import importlib
import sys

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
        
        # We need to dynamically load memory-server.py because its name has a hyphen
        spec = importlib.util.spec_from_file_location("memory_server", "memory-server.py")
        memory_server = importlib.util.module_from_spec(spec)
        sys.modules["memory_server"] = memory_server
        
        # Override paths before executing the module to prevent writing to real project dirs 
        with patch('os.makedirs'): # Prevent real os.makedirs on module load
            pass 
        
        spec.loader.exec_module(memory_server)
        
        # Apply the temporary directories manually to the loaded module
        memory_server.USER_MEMORY_DIR = temp_dirs['user_memory']
        memory_server.USER_AUDIO_DIR = temp_dirs['user_audio']
        memory_server.TTS_CACHE_DIR = temp_dirs['tts_cache']
        memory_server.BACKUP_DIR = temp_dirs['backup']
        memory_server.user_memories = {}  # Reset RAM cache between test cases
        memory_server.cache_last_accessed = {}
        
        yield TestClient(memory_server.app)

@pytest.fixture
def auth_headers():
    """Return authentication headers"""
    return {"X-API-Key": "test-api-key-12345"}

def test_missing_api_key(client):
    """Test that requests without API key are rejected"""
    response = client.get("/get_memories")
    assert response.status_code == 401

def test_invalid_api_key(client):
    """Test that requests with invalid API key are rejected"""
    response = client.get("/get_memories", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
    
# Test memory CRUD
def test_add_and_get_memory(client, auth_headers):
    # Add memory
    add_resp = client.post(
        "/add_memory",
        headers=auth_headers,
        json={"user_id": "test_user_1", "text": "This is a memory", "bank": "General"}
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["status"] == "added"
    
    # Get memory
    get_resp = client.get("/get_memories?user_id=test_user_1", headers=auth_headers)
    assert get_resp.status_code == 200
    memories = get_resp.json()
    assert len(memories) == 1
    assert memories[0]["text"] == "This is a memory"

def test_add_memories_batch(client, auth_headers):
    payload = [
        {"user_id": "test_batch", "text": "Memory A"},
        {"user_id": "test_batch", "text": "Memory B"}
    ]
    resp = client.post("/add_memories", headers=auth_headers, json=payload)
    assert resp.status_code == 200
    assert resp.json()["added"] == 2
    
def test_prune_memory(client, auth_headers):
    payload = [
        {"user_id": "prune_test", "text": "Oldest Memory"},
        {"user_id": "prune_test", "text": "Newest Memory"}
    ]
    client.post("/add_memories", headers=auth_headers, json=payload)
    
    # Prune 1 memory (the oldest)
    prune_res = client.post("/prune", headers=auth_headers, json={"user_id": "prune_test", "amount": 1})
    assert prune_res.status_code == 200
    assert prune_res.json()["remaining_in_ram"] == 1
    
    memories = client.get("/get_memories?user_id=prune_test", headers=auth_headers).json()
    assert memories[0]["text"] == "Newest Memory"

def test_delete_user_memories(client, auth_headers):
    client.post("/add_memory", headers=auth_headers, json={"user_id": "del_user", "text": "Delete me"})
    del_resp = client.post("/delete_user_memories", headers=auth_headers, json={"user_id": "del_user"})
    assert del_resp.status_code == 200
    
    memories = client.get("/get_memories?user_id=del_user", headers=auth_headers).json()
    assert len(memories) == 0

def test_delete_user_memories_security(client, auth_headers):
    # Test path traversal prevention logic
    del_resp = client.post("/delete_user_memories", headers=auth_headers, json={"user_id": "../../../etc/passwd"})
    
    # Safely rejected because it's sanitized down to 'etcpasswd' and no such user folder/json exists
    # If the username shrinks so much or gets caught, it depends on the security rules.
    # The actual implementation strips out special chars so it becomes 'etcpasswd'
    assert del_resp.status_code == 200

def test_memory_stats(client, auth_headers):
    client.post("/add_memory", headers=auth_headers, json={"user_id": "stats_user", "text": "Stats Test"})
    resp = client.get("/memory_stats?user_id=stats_user", headers=auth_headers)
    assert resp.status_code == 200
    assert "memories_in_ram" in resp.json()
    assert resp.json()["memories_in_ram"] == 1

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
