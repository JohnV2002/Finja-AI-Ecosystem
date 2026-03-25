# Testing Documentation for Finja AI Ecosystem

## Overview

This document describes the testing infrastructure for the Finja AI Ecosystem. The project consists of independent, modular microservices. Therefore, testing is performed on a **per-module basis** within their respective directories rather than using a global setup. We employ comprehensive unit tests, integration tests, and automated CI/CD pipelines.

## Test Structure

```text
Finja-AI-Ecosystem/
├── finja-chat/
│   ├── test_command_bridge.py          # Tests for VPet command bridge
│   └── test_spotify_request_server.py  # Tests for Spotify integration
├── finja-Open-Web-UI/
│   ├── finja-Memory/
│   │   ├── test_memory_server.py       # FastAPI endpoints, CRUD, Auth
│   │   └── test_adaptive_memory.py     # OpenWebUI plugin Filter logic
│   └── finja-web-crawler/
│       └── test_web_crawler.py         # DDG/Google scraping & fallback logic
├── Finja-music/
│   └── finja-everthing-in-once/
│       └── test_music_webserver.py     # Tests for music engine
└── .github/workflows/
    ├── finja-chat-tests.yml            # Chat module CI/CD
    ├── memory-tests.yml                # Memory module CI/CD
    ├── web-crawler-tests.yml           # Web Crawler CI/CD
    ├── music-engine-tests.yml          # Music engine CI/CD
    ├── code-quality.yml                # Linting & security
    ├── memory-build.yml                # Docker build for Memory
    ├── ocr-build.yml                   # Docker build for OCR
    └── web-crawler-build.yml           # Docker build for Web Crawler
```

## Running Tests Locally

Because of the modular ecosystem architecture, you must navigate into the specific module directory to run its tests.

### 🧠 Memory Module Tests

This suite tests the FastAPI memory backend and the OpenWebUI Adaptive Memory plugin.

```bash
cd finja-Open-Web-UI/finja-Memory

# Install dependencies (including test libraries)
pip install -r requirements.txt
pip install pytest httpx pytest-asyncio aiohttp numpy scikit-learn rapidfuzz

# Run the test suite
pytest test_memory_server.py test_adaptive_memory.py -v
```

### 🌐 Web Crawler Tests

This suite tests the hybrid DuckDuckGo/Google search crawler, fallback logic, and token authentication.

```bash
cd finja-Open-Web-UI/finja-web-crawler

# Install dependencies
pip install -r requirements.txt
pip install pytest httpx

# Run the test suite
pytest test_web_crawler.py -v
```

### 💬 Finja Chat Tests

```bash
cd finja-chat
pip install -r requirements.txt
pip install pytest

pytest test_command_bridge.py -v
pytest test_spotify_request_server.py -v
```

### 🎵 Music Engine Tests

```bash
cd Finja-music/finja-everthing-in-once
pip install -r requirements.txt
pip install pytest

pytest test_music_webserver.py -v
```

## GitHub Actions Workflows

We use rigorous CI/CD to protect the main branch. Any Pull Request or Push to `main` or `dev` triggers automated tests isolated to the modified module.

1. **Memory Tests** (`memory-tests.yml`)
   - Triggers on modifications to `finja-Open-Web-UI/finja-Memory/**`
   - Executes Pytest suite using Python 3.11.

2. **Web Crawler Tests** (`web-crawler-tests.yml`)
   - Triggers on modifications to `finja-Open-Web-UI/finja-web-crawler/**`
   - Executes Pytest suite using Python 3.12.

3. **Finja Chat Tests** (`finja-chat-tests.yml`)
   - Tests Command Bridge and Spotify integrations.

4. **Code Quality Checks** (`code-quality.yml`)
   - Checks code using flake8, black, isort, bandit, and safety.

5. **Docker Build Checks**
   - Verification builds (`memory-build.yml`, `web-crawler-build.yml`, etc.) are triggered to ensure container compilation succeeds.

## Writing New Tests

If you contribute to a module, please observe the following Pytest conventions:

### Fixture Usage & FastAPI
Modern Finja API components (like Memory and Crawler) rely heavily on FastAPI. Always use `fastapi.testclient.TestClient`.

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}

def test_secure_endpoint(auth_headers):
    response = client.get("/secure", headers=auth_headers)
    assert response.status_code == 200
```

### Mocking External Dependencies
Never run active network requests against external APIs (like DDGS, Google, or Spotify) in automated pipelines to avoid IP blocks and rate limits. Mock them using `unittest.mock.patch` or `pytest-mock`.

```python
from unittest.mock import patch

@patch('main.ddg_search')
def test_fallback_logic(mock_ddg):
    mock_ddg.return_value = [{"title": "Mock", "link": "http://mock"}]
    # Assert your internal logic using the mock
```

## Support

For test-related issues:
- Check GitHub Actions execution logs
- Ensure all Python dependencies for the specific module are installed
- Contact: contact@jappshome.de

---
**Built with ❤️ by J. Apps**
*"Quality code deserves quality tests"*
