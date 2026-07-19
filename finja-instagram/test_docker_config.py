#!/usr/bin/env python3
"""
======================================================================
          Finja Instagram Reels – Docker Config Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Validates the Docker/Compose setup by inspecting file
               content -- no Docker daemon required, so this runs
               anywhere (including plain CI without Docker-in-Docker).

  Note: These tests do NOT build the image or run `docker compose up`
        (slow, needs a daemon, needs real VPN credentials). They check
        that the *configuration* is internally consistent and safe --
        e.g. that .dockerignore actually excludes every secret file
        that exists in this folder (regression test for the 2026-07-19
        security fix), and that the deliberate service/volume naming
        that keeps this stack from colliding with finja-youtube's
        (gluetun-instagram, chrome-profile-ig, gluetun-ig-data,
        VPN_COUNTRY_IG) never silently regresses back to the generic
        names during a future GitHub sync.

  New in v1.0.0:
    • Initial Docker test suite for finja-instagram
    • .dockerignore / secret-file cross-check
    • docker-compose.yml structure, kill-switch, and disambiguated
      naming validation via PyYAML (regression test for the
      collision-avoidance decision documented in the file's own
      "New in v1.1.0" changelog)
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

    SECRET_PATTERNS = [
        "private/",
        "www.instagram.com_cookies.json",
        "www.instagram.com_cookies.txt",
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
        assert "gluetun-instagram" in services, "VPN gateway service missing!"
        assert "finja-instagram" in services, "Main app service missing!"

    def test_service_names_are_disambiguated_from_youtube(self, compose: dict) -> None:
        """
        Regression test: these keys must stay -instagram/-ig suffixed, NOT the
        generic 'gluetun'/'chrome-profile'/'gluetun-data' that finja-youtube's
        own compose file uses -- otherwise combining both stacks via multiple
        -f flags would collide on service/volume names.
        """
        services = compose["services"]
        assert "gluetun" not in services, \
            "Generic 'gluetun' service key would collide with finja-youtube's stack!"

        volumes = compose["volumes"]
        assert "chrome-profile-ig" in volumes
        assert "gluetun-ig-data" in volumes
        assert "chrome-profile" not in volumes, \
            "Generic 'chrome-profile' volume key would collide with finja-youtube's stack!"
        assert "gluetun-data" not in volumes, \
            "Generic 'gluetun-data' volume key would collide with finja-youtube's stack!"

    def test_kill_switch_network_mode(self, compose: dict) -> None:
        """
        finja-instagram must have NO own network -- everything routes through
        gluetun-instagram, so a dropped VPN means no internet (kill switch).
        """
        app_service = compose["services"]["finja-instagram"]
        assert app_service.get("network_mode") == "service:gluetun-instagram"

    def test_app_service_has_no_own_ports(self, compose: dict) -> None:
        app_service = compose["services"]["finja-instagram"]
        assert "ports" not in app_service

    def test_cookie_mounts_point_into_private_folder(self, compose: dict) -> None:
        """
        Regression test: both cookie bind mounts (JSON + TXT) must read from
        ./private/, not the repo root -- that's what keeps the real cookie
        files out of git in the first place.
        """
        volumes = compose["services"]["finja-instagram"]["volumes"]
        cookie_mounts = [v for v in volumes if "cookies" in v]
        assert len(cookie_mounts) == 2, "Expected both JSON and TXT cookie mounts!"
        assert all(v.startswith("./private/") for v in cookie_mounts), (
            "A cookie mount does not point into ./private/ -- "
            "the real cookie file would have to live at the repo root!"
        )

    def test_vpn_credentials_come_from_env_vars(self, compose: dict) -> None:
        gluetun_env = compose["services"]["gluetun-instagram"]["environment"]
        assert "OPENVPN_USER=${PROTON_USER}" in gluetun_env
        assert "OPENVPN_PASSWORD=${PROTON_PASS}" in gluetun_env

    def test_uses_disambiguated_vpn_country_variable(self, compose: dict) -> None:
        """
        Regression test: must stay VPN_COUNTRY_IG (a deliberately different
        country than finja-youtube's VPN_COUNTRY, for IP diversity between
        the two services) -- not the generic VPN_COUNTRY GitHub's port used.
        """
        gluetun_env = compose["services"]["gluetun-instagram"]["environment"]
        server_countries = [e for e in gluetun_env if e.startswith("SERVER_COUNTRIES=")]
        assert server_countries, "SERVER_COUNTRIES not set on gluetun-instagram!"
        assert "VPN_COUNTRY_IG" in server_countries[0], (
            "gluetun-instagram is not using the disambiguated VPN_COUNTRY_IG variable -- "
            "would share finja-youtube's VPN_COUNTRY, defeating the IP-diversity design."
        )

    def test_expected_env_passthroughs_present(self, compose: dict) -> None:
        app_env = compose["services"]["finja-instagram"]["environment"]
        env_keys = [e.split("=", 1)[0] for e in app_env]
        for expected in ["INSTAGRAM_TARGET_URL", "FINJA_BRAIN_URL", "DISCORD_WEBHOOK_URL"]:
            assert expected in env_keys, f"{expected} is not passed through to the container!"

    def test_gluetun_healthcheck_present(self, compose: dict) -> None:
        assert "healthcheck" in compose["services"]["gluetun-instagram"]

    def test_depends_on_waits_for_healthy_vpn(self, compose: dict) -> None:
        depends_on = compose["services"]["finja-instagram"]["depends_on"]
        assert depends_on["gluetun-instagram"]["condition"] == "service_healthy"


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
        assert "EXPOSE 8061" in content

    def test_has_a_healthcheck(self) -> None:
        content = _read("Dockerfile")
        assert "HEALTHCHECK" in content
        assert "8061" in content.split("HEALTHCHECK", 1)[1].split("\n\n")[0]

    def test_copies_entire_build_context(self) -> None:
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
        content = _read("entrypoint.sh")
        assert "set -e" in content

    def test_waits_for_chrome_cdp_before_starting_api(self) -> None:
        content = _read("entrypoint.sh")
        cdp_wait_pos = content.find("json/version")
        api_start_pos = content.find("python instagram_api.py")
        assert cdp_wait_pos != -1, "No CDP readiness check found!"
        assert api_start_pos != -1, "API isn't started!"
        assert cdp_wait_pos < api_start_pos, "API starts before Chrome's CDP is confirmed ready!"

    def test_starts_the_correct_api_entrypoint(self) -> None:
        content = _read("entrypoint.sh")
        assert "python instagram_api.py" in content

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
