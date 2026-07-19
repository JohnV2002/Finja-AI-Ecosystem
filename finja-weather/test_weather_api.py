#!/usr/bin/env python3
"""
======================================================================
             Finja Weather API – Endpoint Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Unit tests for the FastAPI layer (weather_api.py) --
               auth, the location cache, the consensus cross-check
               merge, and error-to-HTTP-status mapping. All outbound
               provider calls are mocked (no real HTTP, no API key,
               no running container needed).

  New in v1.0.0:
    • Initial test suite for weather_api.py
    • Auth tests: open when no BEARER_TOKEN configured, 401 on
      missing/wrong token, 200 on a correct one
    • Cache tests: miss-then-hit for /current, /forecast, /pollen,
      /air-quality, each keyed independently
    • Consensus tests: agreement vs. disagreement merge, skipped when
      the second provider is unavailable
    • Provider-error -> 502 and unknown-provider -> 400 mapping
    • Pydantic request validation (lat/lon bounds, days bounds)

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

import weather_api
from providers import WeatherProviderError

LEIPZIG = {"latitude": 51.3397, "longitude": 12.3731}


class FakeProvider:
    """Stand-in for a WeatherProvider -- returns canned data, counts calls."""

    def __init__(self, name: str, current_data: dict | None = None,
                 forecast_data: dict | None = None,
                 current_error: Exception | None = None,
                 forecast_error: Exception | None = None) -> None:
        self.name = name
        self._current_data = current_data
        self._forecast_data = forecast_data
        self._current_error = current_error
        self._forecast_error = forecast_error
        self.current_calls = 0
        self.forecast_calls = 0

    def current(self, lat: float, lon: float) -> dict[str, Any]:
        self.current_calls += 1
        if self._current_error:
            raise self._current_error
        return dict(self._current_data)

    def forecast(self, lat: float, lon: float, days: int) -> dict[str, Any]:
        self.forecast_calls += 1
        if self._forecast_error:
            raise self._forecast_error
        return dict(self._forecast_data)


def _dry_current(provider: str = "open-meteo") -> dict:
    return {
        "provider": provider, "latitude": LEIPZIG["latitude"], "longitude": LEIPZIG["longitude"],
        "time": "2026-07-19T12:00", "is_day": True, "temperature_c": 22.0,
        "feels_like_c": 21.0, "humidity_pct": 55, "precipitation_mm": 0.0,
        "rain_now": False, "wind_kmh": 10.0, "wind_dir_deg": 180,
        "precip_prob_pct": None, "weather_code": 1, "condition": "Mainly clear",
    }


def _wet_current(provider: str = "google") -> dict:
    d = _dry_current(provider)
    d.update(rain_now=True, precipitation_mm=2.4, condition="Light rain")
    return d


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Each test gets a clean slate: no auth required by default, consensus
    off by default (dedicated tests opt back in), and an empty cache --
    otherwise a cache hit in one test could leak into the next.
    """
    monkeypatch.setattr(weather_api, "EXPECTED_BEARER_TOKEN", None)
    monkeypatch.setattr(weather_api, "WEATHER_CONSENSUS", False)
    weather_api._cache._store.clear()
    weather_api._cache.hits = 0
    weather_api._cache.misses = 0


@pytest.fixture
def client() -> TestClient:
    return TestClient(weather_api.app)


# ==============================================================================
# Auth Tests
# ==============================================================================

class TestAuth:
    """Tests for _require_auth() as exercised through /current."""

    def test_open_when_no_token_configured(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: FakeProvider("open-meteo", current_data=_dry_current()))

        response = client.post("/current", json=LEIPZIG)
        assert response.status_code == 200

    def test_401_when_token_configured_but_header_missing(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "EXPECTED_BEARER_TOKEN", "secret123")
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: FakeProvider("open-meteo", current_data=_dry_current()))

        response = client.post("/current", json=LEIPZIG)
        assert response.status_code == 401

    def test_401_when_token_configured_and_header_wrong(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "EXPECTED_BEARER_TOKEN", "secret123")

        response = client.post("/current", json=LEIPZIG, headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_200_when_token_correct(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "EXPECTED_BEARER_TOKEN", "secret123")
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: FakeProvider("open-meteo", current_data=_dry_current()))

        response = client.post("/current", json=LEIPZIG, headers={"Authorization": "Bearer secret123"})
        assert response.status_code == 200

    def test_health_and_stats_never_require_auth(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "EXPECTED_BEARER_TOKEN", "secret123")

        assert client.get("/health").status_code == 200
        assert client.get("/stats").status_code == 200


# ==============================================================================
# Health / Stats Tests
# ==============================================================================

class TestHealthAndStats:
    def test_health_shape(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["service"] == "finja-weather"
        assert "uptime_s" in data
        assert "cache_hit_rate" in data

    def test_stats_shape(self, client: TestClient) -> None:
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        assert "counters" in data
        assert "avg_duration_ms" in data
        assert "last_error" in data
        assert "cache" in data


# ==============================================================================
# /current Tests
# ==============================================================================

class TestCurrentEndpoint:
    def test_returns_normalized_weather(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: FakeProvider("open-meteo", current_data=_dry_current()))

        response = client.post("/current", json=LEIPZIG)

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "open-meteo"
        assert data["cached"] is False
        assert "duration_ms" in data

    def test_second_identical_call_is_a_cache_hit(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = FakeProvider("open-meteo", current_data=_dry_current())
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: provider)

        first = client.post("/current", json=LEIPZIG)
        second = client.post("/current", json=LEIPZIG)

        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert "cache_age_s" in second.json()
        # The fake provider itself must only have been hit once -- the second
        # request should be served entirely from cache.
        assert provider.current_calls == 1

    def test_provider_error_maps_to_502(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            weather_api, "get_provider",
            lambda name=None: FakeProvider("open-meteo", current_error=WeatherProviderError("upstream down")),
        )

        response = client.post("/current", json=LEIPZIG)
        assert response.status_code == 502

    def test_unknown_provider_maps_to_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(name=None):
            raise WeatherProviderError(f"Unknown weather provider '{name}'")
        monkeypatch.setattr(weather_api, "get_provider", _raise)

        response = client.post("/current", json={**LEIPZIG, "provider": "not-a-real-provider"})
        assert response.status_code == 400


# ==============================================================================
# Consensus Cross-Check Tests
# ==============================================================================

class TestConsensus:
    """
    When WEATHER_CONSENSUS is on, /current also queries the OTHER provider
    and merges the two -- leaning toward rain on disagreement.
    """

    def test_agreement_keeps_original_condition(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "WEATHER_CONSENSUS", True)
        monkeypatch.setattr(weather_api, "_google_available", lambda: True)

        providers = {"open-meteo": FakeProvider("open-meteo", current_data=_dry_current("open-meteo")),
                     "google": FakeProvider("google", current_data=_dry_current("google"))}
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: providers[name or "open-meteo"])

        response = client.post("/current", json=LEIPZIG)

        data = response.json()
        assert data["consensus"]["agreement"] is True
        assert data["condition"] == "Mainly clear"

    def test_disagreement_reports_unsettled_and_leans_wet(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "WEATHER_CONSENSUS", True)
        monkeypatch.setattr(weather_api, "_google_available", lambda: True)

        providers = {"open-meteo": FakeProvider("open-meteo", current_data=_dry_current("open-meteo")),
                     "google": FakeProvider("google", current_data=_wet_current("google"))}
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: providers[name or "open-meteo"])

        response = client.post("/current", json=LEIPZIG)

        data = response.json()
        assert data["consensus"]["agreement"] is False
        assert data["rain_now"] is True
        assert "unsettled" in data["condition"]

    def test_skipped_when_google_unavailable(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """Consensus must not blow up (or silently call Google) without a key."""
        monkeypatch.setattr(weather_api, "WEATHER_CONSENSUS", True)
        monkeypatch.setattr(weather_api, "_google_available", lambda: False)

        provider = FakeProvider("open-meteo", current_data=_dry_current("open-meteo"))
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: provider)

        response = client.post("/current", json=LEIPZIG)

        assert response.status_code == 200
        assert "consensus" not in response.json()


# ==============================================================================
# /forecast Tests
# ==============================================================================

class TestForecastEndpoint:
    def _forecast_data(self) -> dict:
        return {
            "provider": "open-meteo", "latitude": LEIPZIG["latitude"], "longitude": LEIPZIG["longitude"],
            "days": [{"date": "2026-07-20", "temp_max_c": 24.0, "temp_min_c": 14.0,
                      "precipitation_mm": 0.0, "precip_prob_pct": 10, "wind_max_kmh": 15.0,
                      "uv_index": 5.0, "weather_code": 1, "condition": "Mainly clear"}],
        }

    def test_returns_forecast_days(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: FakeProvider("open-meteo", forecast_data=self._forecast_data()))

        response = client.post("/forecast", json={**LEIPZIG, "days": 3})

        assert response.status_code == 200
        assert len(response.json()["days"]) == 1

    def test_second_identical_call_is_a_cache_hit(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = FakeProvider("open-meteo", forecast_data=self._forecast_data())
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: provider)

        client.post("/forecast", json={**LEIPZIG, "days": 3})
        second = client.post("/forecast", json={**LEIPZIG, "days": 3})

        assert second.json()["cached"] is True
        assert provider.forecast_calls == 1

    def test_different_days_are_different_cache_keys(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = FakeProvider("open-meteo", forecast_data=self._forecast_data())
        monkeypatch.setattr(weather_api, "get_provider", lambda name=None: provider)

        client.post("/forecast", json={**LEIPZIG, "days": 3})
        client.post("/forecast", json={**LEIPZIG, "days": 7})

        assert provider.forecast_calls == 2

    def test_provider_error_maps_to_502(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            weather_api, "get_provider",
            lambda name=None: FakeProvider("open-meteo", forecast_error=WeatherProviderError("upstream down")),
        )

        response = client.post("/forecast", json={**LEIPZIG, "days": 3})
        assert response.status_code == 502


# ==============================================================================
# /pollen and /air-quality Tests
# ==============================================================================

class TestPollenEndpoint:
    def test_returns_pollen_data(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"provider": "google", "latitude": LEIPZIG["latitude"], "longitude": LEIPZIG["longitude"],
                   "days": [{"date": "2026-07-20", "types": [], "recommendations": []}]}
        monkeypatch.setattr(weather_api, "google_pollen", lambda lat, lon, days: dict(payload))

        response = client.post("/pollen", json={**LEIPZIG, "days": 1})

        assert response.status_code == 200
        assert response.json()["provider"] == "google"

    def test_provider_error_maps_to_502(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(lat, lon, days):
            raise WeatherProviderError("GOOGLE_WEATHER_API_KEY not set")
        monkeypatch.setattr(weather_api, "google_pollen", _raise)

        response = client.post("/pollen", json={**LEIPZIG, "days": 1})
        assert response.status_code == 502


class TestAirQualityEndpoint:
    def test_returns_air_quality_data(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"provider": "google", "latitude": LEIPZIG["latitude"], "longitude": LEIPZIG["longitude"],
                   "aqi": 42, "category": "Good", "recommendation": "Enjoy the outdoors"}
        monkeypatch.setattr(weather_api, "google_air_quality", lambda lat, lon: dict(payload))

        response = client.post("/air-quality", json=LEIPZIG)

        assert response.status_code == 200
        assert response.json()["aqi"] == 42

    def test_provider_error_maps_to_502(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(lat, lon):
            raise WeatherProviderError("GOOGLE_WEATHER_API_KEY not set")
        monkeypatch.setattr(weather_api, "google_air_quality", _raise)

        response = client.post("/air-quality", json=LEIPZIG)
        assert response.status_code == 502


# ==============================================================================
# Request Validation Tests
# ==============================================================================

class TestRequestValidation:
    @pytest.mark.parametrize("field,value", [("latitude", 90.1), ("latitude", -90.1), ("longitude", 180.1), ("longitude", -180.1)])
    def test_coordinates_out_of_range_are_rejected(self, client: TestClient, field: str, value: float) -> None:
        payload = {**LEIPZIG, field: value}
        response = client.post("/current", json=payload)
        assert response.status_code == 422

    @pytest.mark.parametrize("days", [0, 17])
    def test_forecast_days_out_of_range_are_rejected(self, client: TestClient, days: int) -> None:
        response = client.post("/forecast", json={**LEIPZIG, "days": days})
        assert response.status_code == 422

    @pytest.mark.parametrize("days", [0, 6])
    def test_pollen_days_out_of_range_are_rejected(self, client: TestClient, days: int) -> None:
        response = client.post("/pollen", json={**LEIPZIG, "days": days})
        assert response.status_code == 422


# ==============================================================================
# _merge_consensus() Unit Tests (pure function)
# ==============================================================================

class TestMergeConsensus:
    def test_agreement_is_reported(self) -> None:
        merged = weather_api._merge_consensus(_dry_current("open-meteo"), _dry_current("google"))
        assert merged["consensus"]["agreement"] is True
        assert merged["rain_now"] is False

    def test_disagreement_leans_toward_rain(self) -> None:
        merged = weather_api._merge_consensus(_dry_current("open-meteo"), _wet_current("google"))
        assert merged["consensus"]["agreement"] is False
        assert merged["rain_now"] is True
        assert "unsettled" in merged["condition"]
        assert "open-meteo" in merged["condition"]
        assert "google" in merged["condition"]


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with verbose output when executed directly.

    Usage:
        python test_weather_api.py

    Or with pytest:
        pytest test_weather_api.py -v
    """
    pytest.main([__file__, "-v", "--color=yes"])
