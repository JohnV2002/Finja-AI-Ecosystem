# Testing Documentation for Finja AI Ecosystem

## Overview

This document describes the testing infrastructure for the Finja AI Ecosystem. The project consists of independent, modular microservices. Therefore, testing is performed on a **per-module basis** within their respective directories rather than using a global setup. Each module ships its own Pytest suite, and every CI workflow is **path-scoped** so a change in one module only triggers that module's checks — never the whole repo.

## Test Structure

```text
Finja-AI-Ecosystem/
├── finja-chat/
│   ├── test_command_bridge.py          # VPet command bridge (Flask)
│   ├── test_spotify_request_server.py  # Spotify song-request server
│   └── test_batch_files.py             # Startup .bat integrity checks
├── finja-youtube/
│   ├── test_youtube_api.py             # Shorts API (cookies + endpoints, mocked Chrome)
│   ├── test_autopilot.py               # Autopilot loop + Brain/Discord stubs
│   └── test_docker_config.py           # Dockerfile/Compose/.dockerignore sanity
├── finja-instagram/
│   ├── test_instagram_api.py           # Reels API (cookies JSON+TXT + endpoints)
│   ├── test_autopilot.py               # Cookie injection + buffer-buster retries
│   └── test_docker_config.py           # Dockerfile/Compose sanity + naming disambiguation
├── finja-weather/
│   ├── test_weather_api.py             # Auth, cache, consensus merge, error mapping
│   ├── test_providers.py               # WMO mapping, Open-Meteo/Google parsing
│   ├── test_docker_config.py           # Dockerfile/Compose sanity
│   └── test_weather.py                 # (manual smoke test against a running instance)
├── finja-agentic-code/
│   ├── test_orchestrator.py            # Path validation, AES-GCM transport, auth, endpoints
│   ├── test_worker.py                  # Syntax check, file snapshot, patch application
│   └── test_agentic_job.py             # (manual smoke test against a running orchestrator)
├── finja-Open-Web-UI/
│   ├── finja-Memory/
│   │   ├── test_memory_server.py       # FastAPI endpoints, CRUD, Auth
│   │   └── test_adaptive_memory.py     # OpenWebUI plugin filter logic
│   └── finja-web-crawler/
│       ├── test_web_crawler.py         # DDG/Google-over-Tor search & fallback logic
│       ├── test_crawl_worker.py        # Sandboxed per-URL page reader (SSRF guards)
│       └── test_research_orchestrator.py # Search + crawl + rank orchestration
└── Finja-music/
    ├── finja-everything-in-once/
    │   ├── test_music_resources.py     # OBS HTML/helper/batch integrity
    │   └── test_music_webserver.py     # Endpoints, HTML, security (path traversal, XSS)
    └── finja-music-docker-spotify/
        └── test_music_app.py           # KB indexing, scoring, endpoints (mocked Spotify)
```

## Running Tests Locally

Because of the modular ecosystem architecture, navigate into the specific module directory to run its tests. A note on `httpx2`: recent Starlette releases require it for `fastapi.testclient.TestClient`, so it is included where FastAPI is used.

### 💬 Finja Chat

```bash
cd finja-chat
pip install pytest pytest-cov pytest-mock httpx2
pip install flask flask-cors fastapi uvicorn pydantic spotipy python-dotenv httpx

# Spotify tests need mock credentials in the environment:
export SPOTIPY_CLIENT_ID=test_client_id
export SPOTIPY_CLIENT_SECRET=test_client_secret
export SPOTIPY_REDIRECT_URI=http://localhost:8888/callback

pytest test_command_bridge.py test_spotify_request_server.py test_batch_files.py -v
```

### 📺 Finja YouTube

```bash
cd finja-youtube
pip install pytest pytest-cov pytest-mock pyyaml httpx2
pip install -r requirements.txt   # playwright package only; no browser binaries needed (Chrome is mocked)

pytest test_youtube_api.py test_autopilot.py test_docker_config.py -v
```

### 📸 Finja Instagram

```bash
cd finja-instagram
pip install pytest pytest-cov pytest-mock pyyaml httpx2
pip install -r requirements.txt

pytest test_instagram_api.py test_autopilot.py test_docker_config.py -v
```

### 🌦️ Finja Weather

```bash
cd finja-weather
pip install pytest pytest-cov pytest-mock pyyaml httpx2
pip install -r requirements.txt

pytest test_weather_api.py test_providers.py test_docker_config.py -v
# test_weather.py is a manual smoke test — run it only against a live instance.
```

### 🔥 Finja Agentic Code (Flare)

```bash
cd finja-agentic-code
pip install pytest httpx2
pip install -r orchestrator/requirements.txt

pytest test_orchestrator.py test_worker.py -v
# test_agentic_job.py is a manual smoke test — needs a running orchestrator + Docker.
```

### 🧠 Memory Module

```bash
cd finja-Open-Web-UI/finja-Memory
pip install -r requirements.txt
pip install pytest httpx httpx2 pytest-asyncio aiohttp numpy scikit-learn rapidfuzz

pytest test_memory_server.py test_adaptive_memory.py -v
```

### 🌐 Web Crawler

```bash
cd finja-Open-Web-UI/finja-web-crawler
pip install -r requirements.txt
pip install pytest httpx httpx2

pytest test_web_crawler.py test_crawl_worker.py test_research_orchestrator.py -v
```

### 🎵 Music — All-in-One Engine

```bash
cd Finja-music/finja-everything-in-once
pip install pytest pytest-cov pytest-mock httpx2

pytest test_music_resources.py test_music_webserver.py -v
```

### 🎵 Music — Docker Spotify API

```bash
cd Finja-music/finja-music-docker-spotify
pip install pytest pytest-cov pytest-mock httpx httpx2
pip install -r requirements.txt

pytest test_music_app.py -v
```

## GitHub Actions Workflows

Every workflow is **path-scoped**: a Pull Request or Push only triggers the checks for the module(s) it actually touched (plus the workflow file itself). A change elsewhere — including a root-level README edit — does not trigger unrelated modules.

### Test workflows (Pytest)

| Workflow | Module | Python |
|----------|--------|--------|
| `finja-chat-tests.yml` | finja-chat | 3.9 / 3.10 / 3.11 |
| `finja-youtube-tests.yml` | finja-youtube | 3.11 |
| `finja-instagram-tests.yml` | finja-instagram | 3.11 |
| `finja-weather-tests.yml` | finja-weather | 3.12 |
| `finja-music-everything-in-once.yml` | Finja-music/finja-everything-in-once | 3.9 / 3.10 / 3.11 |
| `finja-music-docker-spotify.yml` | Finja-music/finja-music-docker-spotify | 3.10 / 3.11 |
| `finja-agentic-code-tests.yml` | finja-agentic-code | 3.11 |
| `memory-tests.yml` | finja-Open-Web-UI/finja-Memory | 3.11 |
| `web-crawler-tests.yml` | finja-Open-Web-UI/finja-web-crawler | 3.12 |

> **Note on Python versions:** modules that ship a Dockerfile pin the CI matrix to their image's base version (e.g. weather → 3.12, youtube/instagram → 3.11). Modules that run on whatever Python the user has installed (e.g. chat) test a wider matrix.

### Docker build checks (no Pytest — just verify the image builds)

`finja-youtube-docker-build.yml`, `finja-instagram-docker-build.yml`,
`finja-weather-docker-build.yml`, `finja-agentic-code-docker-build.yml`
(builds both orchestrator + worker), `music-docker-build.yml`,
`memory-build.yml` (also live-pings the container), `web-crawler-build.yml`,
and `ocr-build.yml`.

## Writing New Tests

If you contribute to a module, please observe the following Pytest conventions:

### Fixture Usage & FastAPI
Most Finja API components rely on FastAPI. Always use `fastapi.testclient.TestClient`.

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
Never run active network requests against external APIs (DDGS, Google, Spotify, OpenRouter, Ollama, a Docker daemon, a real browser/CDP session) in automated pipelines — mock them with `unittest.mock.patch` or `pytest-mock`. This keeps the suites fast, deterministic, and free of IP blocks / rate limits.

```python
from unittest.mock import patch

@patch('main.ddg_search')
def test_fallback_logic(mock_ddg):
    mock_ddg.return_value = [{"title": "Mock", "link": "http://mock"}]
    # Assert your internal logic using the mock
```

### Manual smoke tests vs. unit tests
Some modules ship a `test_*.py` that is a **manual smoke test** (hits a live, running service and just prints) rather than a Pytest suite — e.g. `finja-weather/test_weather.py` and `finja-agentic-code/test_agentic_job.py`. These are intentionally **not** run in CI; only the real Pytest suites are.

## Support

For test-related issues:
- Check GitHub Actions execution logs
- Ensure all Python dependencies for the specific module are installed
- Contact: contact@jappshome.de

---
**Built with ❤️ by J. Apps**
*"Quality code deserves quality tests"*
