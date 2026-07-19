#!/usr/bin/env python3
"""
======================================================================
           Finja YouTube Shorts – Docker Config Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-youtube / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Validates the Docker/Compose setup by inspecting file
               content -- no Docker daemon required, so this runs
               anywhere (including plain CI without Docker-in-Docker).

  Note: These tests do NOT build the image or run `docker compose up`
        (slow, needs a daemon, needs real VPN credentials). They check
        that the *configuration* is internally consistent and safe --
        e.g. that .dockerignore actually excludes every secret file
        that exists in this folder, so a real Docker build can never
        bake live credentials into an image layer again (see the
        2026-07-19 security fix for the bug this specifically guards
        against).

  New in v1.0.0:
    • Initial Docker test suite for finja-youtube
    • .dockerignore / secret-file cross-check (regression test for the
      "cookies.json baked into the image" vulnerability)
    • docker-compose.yml structure, kill-switch, and env-passthrough
      validation via PyYAML
    • Dockerfile content checks (non-root user, healthcheck, EXPOSE)
    • entrypoint.sh startup-sequence sanity checks
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
# .dockerignore / Secret Exposure Tests
# ==============================================================================

class TestDockerignoreExcludesSecrets:
    """
    Regression tests for the "COPY . . bakes real secrets into the image"
    vulnerability: every file in this folder that holds a real credential
    or session token must be excluded from the Docker build context.
    """

    # Every one of these must be covered by a .dockerignore rule.
    SECRET_PATTERNS = [
        "private/",
        "cookies.json",
        "www.youtube.com_cookies.txt",
        ".env",
    ]

    def test_dockerignore_file_exists(self) -> None:
        assert os.path.exists(os.path.join(BASE_DIR, ".dockerignore")), \
            ".dockerignore is missing -- COPY . . would bake ALL secrets into the image!"

    @pytest.mark.parametrize("pattern", SECRET_PATTERNS)
    def test_pattern_is_excluded(self, pattern: str) -> None:
        content = _read(".dockerignore")
        lines = [line.strip() for line in content.splitlines()]
        assert pattern in lines, (
            f"'{pattern}' is not excluded in .dockerignore! "
            f"Dockerfile uses 'COPY . .', so this would be baked into every image build."
        )

    def test_example_templates_are_not_excluded(self) -> None:
        """
        *.example files must stay OUT of .dockerignore's effect on git (they're
        already handled there) but are fine to exclude from the Docker image
        itself since the running container never needs the template, only the
        real file. This just documents the (intentional) *.example exclusion
        doesn't accidentally swallow real Python files via an overly broad glob.
        """
        content = _read(".dockerignore")
        assert "*.py" not in content.splitlines(), \
            ".dockerignore excludes all Python files -- the app code wouldn't build!"


# ==============================================================================
# docker-compose.yml Structure Tests
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

    def test_expected_services_present(self, compose: dict) -> None:
        services = compose["services"]
        assert "gluetun" in services, "VPN gateway service missing!"
        assert "finja-youtube" in services, "Main app service missing!"

    def test_kill_switch_network_mode(self, compose: dict) -> None:
        """
        finja-youtube must have NO own network -- everything routes through
        gluetun, so a dropped VPN means no internet (kill switch). Losing
        this line would silently leak the real IP.
        """
        app_service = compose["services"]["finja-youtube"]
        assert app_service.get("network_mode") == "service:gluetun"

    def test_app_service_has_no_own_ports(self, compose: dict) -> None:
        """Ports must live on gluetun only -- finja-youtube shares its network."""
        app_service = compose["services"]["finja-youtube"]
        assert "ports" not in app_service

    def test_cookie_mount_points_into_private_folder(self, compose: dict) -> None:
        """
        Regression test: the cookie bind mount must read from ./private/,
        not the repo root -- that's what keeps the real cookie file out of
        git in the first place.
        """
        volumes = compose["services"]["finja-youtube"]["volumes"]
        cookie_mounts = [v for v in volumes if "cookies.json" in v]
        assert cookie_mounts, "No cookies.json volume mount found!"
        assert any(v.startswith("./private/") for v in cookie_mounts), (
            "Cookie mount does not point into ./private/ -- "
            "the real cookie file would have to live at the repo root!"
        )

    def test_vpn_credentials_come_from_env_vars(self, compose: dict) -> None:
        """VPN credentials must be templated from .env, never hardcoded."""
        gluetun_env = compose["services"]["gluetun"]["environment"]
        assert "OPENVPN_USER=${PROTON_USER}" in gluetun_env
        assert "OPENVPN_PASSWORD=${PROTON_PASS}" in gluetun_env

    def test_expected_env_passthroughs_present(self, compose: dict) -> None:
        """The env vars autopilot.py / youtube_api.py actually read must be wired through."""
        app_env = compose["services"]["finja-youtube"]["environment"]
        env_keys = [e.split("=", 1)[0] for e in app_env]
        for expected in ["YOUTUBE_TARGET_URL", "MOBILE_UA", "FINJA_BRAIN_URL", "DISCORD_WEBHOOK_URL"]:
            assert expected in env_keys, f"{expected} is not passed through to the container!"

    def test_gluetun_healthcheck_present(self, compose: dict) -> None:
        """depends_on: condition: service_healthy needs an actual healthcheck to wait for."""
        assert "healthcheck" in compose["services"]["gluetun"]

    def test_depends_on_waits_for_healthy_vpn(self, compose: dict) -> None:
        """The app must not start before the VPN tunnel is actually up."""
        depends_on = compose["services"]["finja-youtube"]["depends_on"]
        assert depends_on["gluetun"]["condition"] == "service_healthy"


# ==============================================================================
# Dockerfile Tests
# ==============================================================================

class TestDockerfile:
    """Validates the Dockerfile content for security-relevant properties."""

    def test_runs_as_non_root_user(self) -> None:
        content = _read("Dockerfile")
        assert "USER appuser" in content, "Container would run as root!"

    def test_exposes_the_correct_api_port(self) -> None:
        content = _read("Dockerfile")
        assert "EXPOSE 8060" in content

    def test_has_a_healthcheck(self) -> None:
        content = _read("Dockerfile")
        assert "HEALTHCHECK" in content
        assert "8060" in content.split("HEALTHCHECK", 1)[1].split("\n\n")[0]

    def test_copies_entire_build_context(self) -> None:
        """
        Documents the exact line that makes .dockerignore security-critical --
        if this ever changes to selective COPYs, the .dockerignore tests above
        become less critical (but shouldn't be removed).
        """
        content = _read("Dockerfile")
        assert "COPY . ." in content

    def test_entrypoint_is_the_startup_script(self) -> None:
        content = _read("Dockerfile")
        assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in content


# ==============================================================================
# entrypoint.sh Tests
# ==============================================================================

class TestEntrypointScript:
    """
    Sanity tests for entrypoint.sh (does NOT execute it -- that needs a real
    container -- only inspects its content for the expected startup sequence).
    """

    def test_has_bash_shebang(self) -> None:
        content = _read("entrypoint.sh")
        assert content.startswith("#!/bin/bash")

    def test_exits_on_error(self) -> None:
        """set -e ensures a failed step (e.g. Chrome not starting) stops the container."""
        content = _read("entrypoint.sh")
        assert "set -e" in content

    def test_waits_for_chrome_cdp_before_starting_api(self) -> None:
        content = _read("entrypoint.sh")
        cdp_wait_pos = content.find("json/version")
        api_start_pos = content.find("python youtube_api.py")
        assert cdp_wait_pos != -1, "No CDP readiness check found!"
        assert api_start_pos != -1, "API isn't started!"
        assert cdp_wait_pos < api_start_pos, "API starts before Chrome's CDP is confirmed ready!"

    def test_starts_the_correct_api_entrypoint(self) -> None:
        content = _read("entrypoint.sh")
        assert "python youtube_api.py" in content

    def test_has_graceful_shutdown_handler(self) -> None:
        content = _read("entrypoint.sh")
        assert "trap cleanup SIGTERM SIGINT" in content


# ==============================================================================
# requirements.txt Tests
# ==============================================================================

class TestRequirements:
    """Checks that every top-level import actually used by the app is declared."""

    @pytest.fixture(scope="class")
    def requirements(self) -> str:
        return _read("requirements.txt").lower()

    @pytest.mark.parametrize("package", ["playwright", "fastapi", "uvicorn", "httpx", "python-dotenv"])
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
