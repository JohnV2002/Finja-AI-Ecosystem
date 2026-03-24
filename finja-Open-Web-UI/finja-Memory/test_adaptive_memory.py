import pytest
import importlib.util
import sys
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def adaptive_memory_plugin():
    """Dynamically load and instantiate the memory plugin Filter class."""
    spec = importlib.util.spec_from_file_location("adaptive_memory", "function-adaptive_memory_v4.py")
    plugin_module = importlib.util.module_from_spec(spec)
    sys.modules["adaptive_memory"] = plugin_module
    
    # Execute module first so its variables are defined
    spec.loader.exec_module(plugin_module)
    
    # Pre-mock heavy dependencies like SentenceTransformer to speed up tests and avoid downloads
    with patch.object(plugin_module, "_SENTENCE_TRANSFORMER_AVAILABLE", False, create=True), \
         patch.object(plugin_module, "SentenceTransformer", MagicMock(), create=True):
        
        # Instantiate Filter
        filter_instance = plugin_module.Filter()
        return filter_instance

def test_extract_text_from_content_string(adaptive_memory_plugin):
    """Test standard text extraction."""
    res = adaptive_memory_plugin._extract_text_from_content("Just a string")
    assert res == "Just a string"

def test_extract_text_from_content_list(adaptive_memory_plugin):
    """Test extraction from a multimodal list payload (e.g. from Vision models)."""
    payload = [
        {"type": "text", "text": "Part one"},
        {"type": "image_url", "image_url": "http://example.com/img.png"},
        {"type": "text", "text": "Part two"}
    ]
    res = adaptive_memory_plugin._extract_text_from_content(payload)
    assert res == "Part one\nPart two"

@pytest.mark.asyncio
async def test_check_memory_server_up(adaptive_memory_plugin):
    """Test memory server connection check when server is up."""
    # Mock aiohttp ClientSession
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        is_up = await adaptive_memory_plugin._check_memory_server(None)
        assert is_up is True
        
@pytest.mark.asyncio
async def test_check_memory_server_down(adaptive_memory_plugin):
    """Test memory server connection check when server is down."""
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        is_up = await adaptive_memory_plugin._check_memory_server(None)
        assert is_up is False

@pytest.mark.asyncio
async def test_is_duplicate_candidate_empty_list(adaptive_memory_plugin):
    """Should return False if there are no existing memories to check against."""
    res, _ = await adaptive_memory_plugin._is_duplicate_candidate({"content": "New memo"}, False, [], [], None)
    assert res is False

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
