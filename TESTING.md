# Testing Documentation for Finja AI Ecosystem

## Overview

This document describes the testing infrastructure for the Finja AI Ecosystem. The project now includes comprehensive unit tests, integration tests, and automated CI/CD pipelines.

## Test Structure

```
Finja-AI-Ecosystem/
├── finja-chat/
│   ├── test_command_bridge.py          # Tests for VPet command bridge
│   └── test_spotify_request_server.py  # Tests for Spotify integration
├── finja-Open-Web-UI/
│   ├── finja-Memory/
│   │   └── test_memory_server.py       # Tests for memory system
│   └── finja-web-crawler/
│       └── test_web_crawler.py         # Tests for web crawler
├── Finja-music/
│   └── finja-everthing-in-once/
│       └── test_music_webserver.py     # Tests for music engine
└── .github/workflows/
    ├── finja-chat-tests.yml            # Chat module CI/CD
    ├── openweb-ui-tests.yml            # OpenWebUI modules CI/CD
    ├── music-engine-tests.yml          # Music engine CI/CD
    ├── code-quality.yml                # Linting & security
    ├── comprehensive-tests.yml         # Full test suite
    ├── memory-build.yml                # Docker build for Memory
    ├── ocr-build.yml                   # Docker build for OCR
    └── web-crawler-build.yml           # Docker build for Web Crawler
```

## Running Tests Locally

### Prerequisites

```bash
# Install test dependencies
pip install -r test-requirements.txt
```

### Running Individual Test Suites

#### Finja Chat Tests
```bash
cd finja-chat
pytest test_command_bridge.py -v
pytest test_spotify_request_server.py -v
```

#### Memory Module Tests
```bash
cd finja-Open-Web-UI/finja-Memory
export MEMORY_API_KEY="test-api-key-12345"
pytest test_memory_server.py -v
```

#### Web Crawler Tests
```bash
cd finja-Open-Web-UI/finja-web-crawler
export BEARER_TOKEN="test-bearer-token-12345"
pytest test_web_crawler.py -v
```

#### Music Engine Tests
```bash
cd Finja-music/finja-everthing-in-once
pytest test_music_webserver.py -v
```

### Running All Tests

```bash
# From project root
pytest --tb=short
```

### Running with Coverage

```bash
# Generate coverage report
pytest --cov=. --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## GitHub Actions Workflows

### Automated Test Workflows

1. **Finja Chat Tests** (`finja-chat-tests.yml`)
   - Triggers on: Push/PR to `finja-chat/**`
   - Tests: Command bridge, Spotify integration
   - Python versions: 3.9, 3.10, 3.11

2. **OpenWebUI Modules Tests** (`openweb-ui-tests.yml`)
   - Triggers on: Push/PR to `finja-Open-Web-UI/**`
   - Tests: Memory server, Web crawler
   - Python versions: 3.9, 3.10, 3.11

3. **Music Engine Tests** (`music-engine-tests.yml`)
   - Triggers on: Push/PR to `Finja-music/**`
   - Tests: Music webserver, database functions
   - Python versions: 3.9, 3.10, 3.11

4. **Code Quality Checks** (`code-quality.yml`)
   - Triggers on: All pushes/PRs to main
   - Checks: flake8, black, isort, bandit, safety
   - Security scanning included

5. **Comprehensive Test Suite** (`comprehensive-tests.yml`)
   - Triggers on: All pushes/PRs + daily at 2 AM UTC
   - Runs: All test suites + Docker builds
   - Matrix: All Python versions × All modules

6. **Docker Build Checks**
   - `memory-build.yml` - Tests Memory module Docker build
   - `ocr-build.yml` - Tests OCR module Docker build
   - `web-crawler-build.yml` - Tests Web Crawler Docker build

## Test Coverage

### Current Test Coverage by Module

| Module | Test File | Coverage Areas |
|--------|-----------|----------------|
| **finja-chat** | `test_command_bridge.py` | Flask endpoints, command storage, timestamps |
| **finja-chat** | `test_spotify_request_server.py` | Spotify API, song requests, cooldowns, mod commands |
| **finja-Memory** | `test_memory_server.py` | CRUD operations, authentication, persistence, security |
| **finja-web-crawler** | `test_web_crawler.py` | DuckDuckGo search, fallback, auth, result formatting |
| **finja-music** | `test_music_webserver.py` | Database building, CSV parsing, file operations |

### What's Tested

✅ **API Endpoints**
- Authentication & authorization
- Request validation
- Response formats
- Error handling

✅ **Business Logic**
- Song request cooldowns
- Memory CRUD operations
- Search result processing
- Database operations

✅ **Security**
- Path traversal prevention
- API key validation
- Input sanitization
- Bearer token authentication

✅ **Data Persistence**
- File I/O operations
- Atomic writes
- Directory creation
- JSON serialization

✅ **Integration Points**
- Spotify API mocking
- DuckDuckGo search mocking
- VPet command bridge
- Database lookups

## Writing New Tests

### Test Naming Convention

```python
# Class names: Test + FeatureName
class TestAuthentication:
    pass

# Method names: test_ + specific_case
def test_valid_api_key(self):
    pass
```

### Fixture Usage

```python
@pytest.fixture
def client():
    """Create test client for FastAPI app"""
    return TestClient(app)

@pytest.fixture
def auth_headers():
    """Return authentication headers"""
    return {"X-API-Key": "test-key"}
```

### Mocking External Dependencies

```python
from unittest.mock import patch, MagicMock

@patch('module.external_api')
def test_with_mock(self, mock_api):
    mock_api.return_value = {"data": "test"}
    # Test code here
```

## Best Practices

1. **Isolation**: Each test should be independent
2. **Mocking**: Mock external APIs and services
3. **Cleanup**: Use fixtures with cleanup for file operations
4. **Assertions**: Use clear, specific assertions
5. **Coverage**: Aim for >80% code coverage
6. **Documentation**: Add docstrings to test methods
7. **Fast Tests**: Keep unit tests fast (<1s each)

## Continuous Integration

### Build Status Badges

Add these to your README:

```markdown
[![Finja Chat Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-chat-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-chat-tests.yml)
[![OpenWebUI Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/openweb-ui-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/openweb-ui-tests.yml)
[![Code Quality](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/code-quality.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/code-quality.yml)
```

### On Pull Requests

All tests must pass before merging:
- Python tests across 3 versions
- Docker builds successful
- Code quality checks pass
- Security scans clean

## Troubleshooting

### Common Issues

**Import Errors**
```bash
# Ensure you're in the correct directory
cd module-directory
pytest test_file.py
```

**Missing Dependencies**
```bash
# Install all dependencies
pip install -r requirements.txt
pip install -r test-requirements.txt
```

**Environment Variables**
```bash
# Set required env vars before testing
export MEMORY_API_KEY="test-key"
export BEARER_TOKEN="test-token"
```

## Future Enhancements

- [ ] Add end-to-end tests
- [ ] Implement performance benchmarks
- [ ] Add mutation testing
- [ ] Create mock Spotify/Twitch servers
- [ ] Add browser-based UI tests
- [ ] Implement stress testing
- [ ] Add API contract testing
- [ ] Create test data generators

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure all existing tests pass
3. Add new tests for your feature
4. Update this documentation
5. Run code quality checks
6. Submit PR with test results

## Support

For test-related issues:
- Check GitHub Actions logs
- Review test output locally
- Open an issue with test failures
- Contact: contact@jappshome.de

---

**Built with ❤️ by J. Apps**
*"Quality code deserves quality tests"*
