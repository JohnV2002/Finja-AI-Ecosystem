"""
======================================================================
               Web Crawler API – Test Suite
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-web-crawler
  Author: J. Apps (JohnV2002 / Sodakiller1)

----------------------------------------------------------------------
  Description:
    Real unit tests for the Web Crawler using pytest and FastAPI
    TestClient. It mocks external search engines (DDGS and requests)
    to verify internal router and fallback logic securely.
======================================================================
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# IMPORTANT: We must patch the environment variable BEFORE importing main, 
# or we patch the module variable directly.
from main import app, SearchResult
import main

# Force the expected token for tests
main.EXPECTED_BEARER_TOKEN = "test-bearer-token-12345"

client = TestClient(app)

@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-bearer-token-12345"}

class TestAuthentication:
    """Tests for API authentication via Bearer Token."""

    def test_missing_bearer_token(self):
        """Test that requests without a bearer token are rejected."""
        response = client.post("/search", json={"query": "test", "count": 5})
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"

    def test_invalid_bearer_token(self):
        """Test that requests with an invalid bearer token are rejected."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = client.post("/search", json={"query": "test", "count": 5}, headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"

    @patch('main.ddg_search')
    def test_valid_bearer_token(self, mock_ddg, auth_headers):
        """Test that requests with a valid bearer token are accepted."""
        mock_ddg.return_value = [SearchResult(link="https://test.com", title="Test", snippet="Test")]
        response = client.post("/search", json={"query": "test", "count": 1}, headers=auth_headers)
        assert response.status_code == 200

class TestSearchLogic:
    """Tests for the hybrid external search endpoint and its fallback mechanism."""

    @patch('main.ddg_search')
    def test_ddgs_search_success(self, mock_ddg, auth_headers):
        """Test DuckDuckGo returns the full requested count of results without triggering fallback."""
        mock_results = [
            SearchResult(link=f"https://test.com/{i}", title=f"Title {i}", snippet="Snippet")
            for i in range(3)
        ]
        mock_ddg.return_value = mock_results

        response = client.post("/search", json={"query": "python", "count": 3}, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["title"] == "Title 0"
        
        # Verify the mock was called correctly
        mock_ddg.assert_called_once_with("python", 3)

    @patch('main.ddg_search')
    @patch('main.google_crawler')
    def test_fallback_triggered(self, mock_google, mock_ddg, auth_headers):
        """Test fallback triggered when DuckDuckGo returns fewer results than requested."""
        # DDG returns only 1 result, but we ask for 3
        mock_ddg.return_value = [SearchResult(link="https://ddg.com", title="DDG", snippet="DDG")]
        
        # Google should be called for the remaining 2 results (3 - 1 = 2)
        mock_google.return_value = [
            SearchResult(link="https://google.com/1", title="G1", snippet="G1"),
            SearchResult(link="https://google.com/2", title="G2", snippet="G2")
        ]

        response = client.post("/search", json={"query": "test fallback", "count": 3}, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        
        # Ensure order: DDG results first, then Google results seamlessly appended
        assert data[0]["title"] == "DDG"
        assert data[1]["title"] == "G1"
        assert data[2]["title"] == "G2"

        # Verify google_crawler was called requesting exactly 2 results (the deficit)
        mock_google.assert_called_once_with("test fallback", 2)

    @patch('main.ddg_search')
    @patch('main.google_crawler')
    def test_tabby_cat_fallback_ultimate(self, mock_google, mock_ddg, auth_headers):
        """Test the absolute ultimate fallback when both engines return absolutely nothing."""
        # Both engines fail to provide results
        mock_ddg.return_value = []
        mock_google.return_value = []

        response = client.post("/search", json={"query": "impossible query", "count": 5}, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        
        # Tabby Cat logic expected here
        assert "Tabby Cat Fallback" in data[0]["title"]
        assert data[0]["link"] == "https://en.wikipedia.org/wiki/Tabby_cat"
        assert "I couldn't find anything" in data[0]["snippet"]

class TestDataModels:
    """Tests for validating Data Model Edge Cases"""
    
    @patch('main.ddg_search')
    def test_search_missing_query_field(self, mock_ddg, auth_headers):
        """Test API behavior when query is missing from JSON payload."""
        response = client.post("/search", json={"count": 5}, headers=auth_headers)
        # Should raise a Pydantic Validation Error since query is required
        assert response.status_code == 422 
        
    @patch('main.ddg_search')
    def test_search_missing_count_field(self, mock_ddg, auth_headers):
        """Test API behavior when count is missing from JSON payload."""
        response = client.post("/search", json={"query": "python"}, headers=auth_headers)
        # Should raise a Pydantic Validation Error since count is currently required and has no default
        assert response.status_code == 422 

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
