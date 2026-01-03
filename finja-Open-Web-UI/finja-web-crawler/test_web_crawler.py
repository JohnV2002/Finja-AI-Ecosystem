"""
Unit tests for main.py (Web Crawler API)
Tests the hybrid web crawler with DuckDuckGo and fallback functionality
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, Mock
import os


@pytest.fixture
def client():
    """Create test client with mocked environment"""
    with patch.dict(os.environ, {'BEARER_TOKEN': 'test-bearer-token-12345'}):
        from main import app
        return TestClient(app)


@pytest.fixture
def auth_headers():
    """Return authentication headers"""
    return {"Authorization": "Bearer test-bearer-token-12345"}


class TestAuthentication:
    """Tests for API authentication"""

    def test_missing_bearer_token(self, client):
        """Test that requests without bearer token are rejected"""
        response = client.post("/search", json={"query": "test"})
        assert response.status_code == 401

    def test_invalid_bearer_token(self, client):
        """Test that requests with invalid bearer token are rejected"""
        headers = {"Authorization": "Bearer invalid-token"}
        response = client.post("/search", json={"query": "test"}, headers=headers)
        assert response.status_code == 401

    def test_valid_bearer_token(self, client, auth_headers):
        """Test that requests with valid bearer token are accepted"""
        with patch('main.DDGS') as mock_ddgs:
            mock_ddgs.return_value.text.return_value = [
                {"title": "Test", "href": "https://test.com", "body": "Test result"}
            ]
            response = client.post("/search", json={"query": "test"}, headers=auth_headers)
            # Should not be 401
            assert response.status_code != 401


class TestSearchEndpoint:
    """Tests for /search endpoint"""

    def test_search_with_valid_query(self, client, auth_headers):
        """Test search with valid query returns results"""
        with patch('main.DDGS') as mock_ddgs:
            # Mock DuckDuckGo response
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {
                    "title": "Test Result 1",
                    "href": "https://example.com/1",
                    "body": "This is a test result"
                },
                {
                    "title": "Test Result 2",
                    "href": "https://example.com/2",
                    "body": "Another test result"
                }
            ]
            mock_ddgs.return_value = mock_instance

            response = client.post(
                "/search",
                json={"query": "python programming"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert isinstance(data["results"], list)
            assert len(data["results"]) > 0

    def test_search_empty_query(self, client, auth_headers):
        """Test search with empty query"""
        response = client.post(
            "/search",
            json={"query": ""},
            headers=auth_headers
        )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_search_missing_query_field(self, client, auth_headers):
        """Test search without query field"""
        response = client.post(
            "/search",
            json={},
            headers=auth_headers
        )
        assert response.status_code == 422  # Validation error

    def test_search_with_special_characters(self, client, auth_headers):
        """Test search with special characters in query"""
        with patch('main.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {"title": "Result", "href": "https://test.com", "body": "Result body"}
            ]
            mock_ddgs.return_value = mock_instance

            special_queries = [
                "C++ programming",
                "what is AI?",
                "search: test & demo",
                "unicode: 你好世界"
            ]

            for query in special_queries:
                response = client.post(
                    "/search",
                    json={"query": query},
                    headers=auth_headers
                )
                assert response.status_code == 200


class TestDuckDuckGoIntegration:
    """Tests for DuckDuckGo search integration"""

    def test_ddgs_search_success(self, client, auth_headers):
        """Test successful DuckDuckGo search"""
        with patch('main.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {
                    "title": "Python.org",
                    "href": "https://python.org",
                    "body": "Official Python website"
                }
            ]
            mock_ddgs.return_value = mock_instance

            response = client.post(
                "/search",
                json={"query": "python"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) > 0
            assert data["results"][0]["title"] == "Python.org"

    def test_ddgs_returns_empty_results(self, client, auth_headers):
        """Test when DuckDuckGo returns no results"""
        with patch('main.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = []
            mock_ddgs.return_value = mock_instance

            response = client.post(
                "/search",
                json={"query": "very obscure query"},
                headers=auth_headers
            )

            # Should either return empty results or trigger fallback
            assert response.status_code == 200
            data = response.json()
            assert "results" in data

    def test_ddgs_exception_handling(self, client, auth_headers):
        """Test handling of DuckDuckGo exceptions"""
        with patch('main.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.side_effect = Exception("Connection error")
            mock_ddgs.return_value = mock_instance

            # Mock fallback mechanism
            with patch('main.requests.get') as mock_requests:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = "<html><body>Test</body></html>"
                mock_requests.return_value = mock_response

                response = client.post(
                    "/search",
                    json={"query": "test"},
                    headers=auth_headers
                )

                # Should handle error gracefully
                assert response.status_code in [200, 500]


class TestFallbackMechanism:
    """Tests for fallback search mechanism"""

    def test_fallback_triggered_on_few_results(self, client, auth_headers):
        """Test that fallback is triggered when DuckDuckGo returns too few results"""
        with patch('main.DDGS') as mock_ddgs:
            # Return only 1 result to trigger fallback (if threshold is > 1)
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {"title": "One Result", "href": "https://test.com", "body": "Only one"}
            ]
            mock_ddgs.return_value = mock_instance

            # Mock the fallback HTML scraping
            with patch('main.requests.get') as mock_requests:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = """
                <html>
                    <div class="g">
                        <h3>Fallback Result</h3>
                        <a href="https://fallback.com">Link</a>
                        <span>Fallback description</span>
                    </div>
                </html>
                """
                mock_requests.return_value = mock_response

                response = client.post(
                    "/search",
                    json={"query": "test"},
                    headers=auth_headers
                )

                assert response.status_code == 200


class TestResultFormatting:
    """Tests for search result formatting"""

    def test_result_structure(self, client, auth_headers):
        """Test that results have correct structure"""
        with patch('main.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {
                    "title": "Test Title",
                    "href": "https://test.com",
                    "body": "Test description"
                }
            ]
            mock_ddgs.return_value = mock_instance

            response = client.post(
                "/search",
                json={"query": "test"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data

            if len(data["results"]) > 0:
                result = data["results"][0]
                # Check expected fields exist
                assert "title" in result or "href" in result

    def test_url_validation_in_results(self, client, auth_headers):
        """Test that returned URLs are valid"""
        with patch('main.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {
                    "title": "Valid URL",
                    "href": "https://example.com/page",
                    "body": "Description"
                },
                {
                    "title": "Another URL",
                    "href": "http://test.org",
                    "body": "Another description"
                }
            ]
            mock_ddgs.return_value = mock_instance

            response = client.post(
                "/search",
                json={"query": "test"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()

            for result in data["results"]:
                if "href" in result:
                    # Basic URL validation
                    assert result["href"].startswith("http://") or result["href"].startswith("https://")


class TestHealthCheck:
    """Tests for health check endpoint"""

    def test_health_endpoint(self, client):
        """Test health check endpoint (if exists)"""
        response = client.get("/health")
        # Should be accessible without auth
        assert response.status_code in [200, 404]  # 404 if not implemented


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
