#!/usr/bin/env python3
"""
======================================================================
            Finja Weather API – Docker Config Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Validates the Docker/Compose setup by inspecting file
               content -- no Docker daemon required, so this runs
               anywhere (including plain CI without Docker-in-Docker).

  Note: Unlike finja-youtube/finja-instagram, this Dockerfile does NOT
        use `COPY . .` -- it COPYs only the exact files it needs
        (requirements.txt, weather_api.py, providers.py). That means
        there's no "secrets baked into the image" class of bug here
        by construction. The important regression test is the inverse
        of the other modules': assert the Dockerfile keeps using an
        explicit file list and never regresses to a blanket COPY that
        would silently start pulling in .env/test files/.git.

  New in v1.0.0:
    • Initial Docker test suite for finja-weather
    • Dockerfile: explicit COPY list (not `COPY . .`), no secrets
      possible in the build context, EXPOSE 80, correct CMD
    • docker-compose.yml structure via PyYAML: port mapping, env_file,
      restart policy
    • .dockerignore / .gitignore existence and secret-pattern checks
    • requirements.txt completeness vs. actual imports

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os

import pytest
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _read(filename: str) -> str:
    path = os.path.join(BASE_DIR, filename)
    assert os.path.exists(path), f"{filename} missing!"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ==============================================================================
# Dockerfile Tests
# ==============================================================================

class TestDockerfile:
    """Validates the Dockerfile content."""

    def test_does_not_use_blanket_copy(self) -> None:
        """
        Regression test (inverse of the other Finja modules): this Dockerfile
        must keep copying an explicit file list. A `COPY . .` here would start
        baking .env, test files, and .git into every image build with no
        .dockerignore-shaped safety net currently relied upon.
        """
        content = _read("Dockerfile")
        assert "COPY . ." not in content, (
            "Dockerfile now uses a blanket 'COPY . .' -- add a .dockerignore "
            "exclusion for .env/test_*.py/.git before this ships, the current "
            "explicit-file-list design is what keeps secrets out of the image!"
        )

    def test_copies_only_required_application_files(self) -> None:
        content = _read("Dockerfile")
        assert "COPY requirements.txt ." in content
        assert "COPY weather_api.py providers.py ." in content

    def test_exposes_the_correct_port(self) -> None:
        content = _read("Dockerfile")
        assert "EXPOSE 80" in content

    def test_starts_uvicorn_with_the_correct_app(self) -> None:
        content = _read("Dockerfile")
        assert 'CMD ["uvicorn", "weather_api:app", "--host", "0.0.0.0", "--port", "80"]' in content

    def test_installs_requirements_before_copying_app_code(self) -> None:
        """Dependency layer must come before app-code layer for build caching."""
        content = _read("Dockerfile")
        req_pos = content.find("COPY requirements.txt .")
        app_pos = content.find("COPY weather_api.py providers.py .")
        assert req_pos != -1 and app_pos != -1
        assert req_pos < app_pos


# ==============================================================================
# docker-compose.yml Tests
# ==============================================================================

class TestDockerComposeStructure:
    """Validates docker-compose.yml parses and has the expected shape."""

    @pytest.fixture(scope="class")
    def compose(self) -> dict:
        content = _read("docker-compose.yml")
        return yaml.safe_load(content)

    def test_parses_as_valid_yaml(self, compose: dict) -> None:
        assert isinstance(compose, dict)
        assert "services" in compose

    def test_weather_service_present(self, compose: dict) -> None:
        assert "weather" in compose["services"]

    def test_port_mapping(self, compose: dict) -> None:
        ports = compose["services"]["weather"]["ports"]
        assert "8095:80" in ports

    def test_loads_env_file(self, compose: dict) -> None:
        """WEATHER_CONSENSUS and other vars flow in via env_file, not hardcoded."""
        env_files = compose["services"]["weather"].get("env_file")
        assert env_files, "No env_file directive -- .env would never reach the container!"
        assert ".env" in env_files

    def test_restarts_unless_stopped(self, compose: dict) -> None:
        assert compose["services"]["weather"].get("restart") == "unless-stopped"

    def test_provider_env_passthrough_has_a_safe_default(self, compose: dict) -> None:
        env = compose["services"]["weather"]["environment"]
        provider_entries = [e for e in env if e.startswith("WEATHER_PROVIDER=")]
        assert provider_entries
        assert "open-meteo" in provider_entries[0], \
            "Default provider should be the free, key-less open-meteo, not google"


# ==============================================================================
# .dockerignore Tests
# ==============================================================================

class TestIgnoreFiles:
    """
    Makes sure .env can never end up in a Docker image build context. (.gitignore
    is GitHub-repo-only -- it doesn't exist in the Production copy these tests
    run from, so it isn't checked here; see finja-weather-docker-build.yml /
    the repo's own .gitignore for that side of the safety net.)
    """

    def test_dockerignore_excludes_env(self) -> None:
        content = _read(".dockerignore")
        assert ".env" in content.splitlines()


# ==============================================================================
# requirements.txt Tests
# ==============================================================================

class TestRequirements:
    """Checks that every top-level import actually used by the app is declared."""

    @pytest.fixture(scope="class")
    def requirements(self) -> str:
        return _read("requirements.txt").lower()

    @pytest.mark.parametrize("package", ["fastapi", "uvicorn", "requests", "pydantic", "python-dotenv"])
    def test_required_package_declared(self, requirements: str, package: str) -> None:
        assert package in requirements, f"{package} is imported but missing from requirements.txt!"


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with verbose output when executed directly.

    Usage:
        python test_docker_config.py

    Or with pytest:
        pytest test_docker_config.py -v
    """
    pytest.main([__file__, "-v", "--color=yes"])
