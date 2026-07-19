#!/usr/bin/env python3
"""
======================================================================
              Finja Weather API – Provider Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0
  Description: Unit tests for providers.py -- WMO condition mapping,
               the "truth comes from precipitation, not just the
               weather code" reconciliation logic in OpenMeteoProvider,
               and Open-Meteo/Google Weather/Pollen/Air-Quality response
               parsing. All outbound HTTP is mocked (no real network
               calls, no API key needed to run these).

  New in v1.0.0:
    • Initial test suite for providers.py
    • wmo_condition / _is_precip_code / _text_is_wet / _num / _nowcast_now
      pure-function tests
    • OpenMeteoProvider.current(): dry, code-already-wet, amount-only-wet
      (code says dry but precipitation > 0), and nowcast-detected-wet
      (hourly code dry, 15-min nowcast code wet) cases
    • OpenMeteoProvider.forecast() day-array parsing
    • GoogleWeatherProvider: missing-key error, current()/forecast()
      response parsing
    • google_pollen() / google_air_quality(): missing-key error and
      response parsing
    • get_provider(): valid names, unknown name, env-var default

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from providers import (
    GoogleWeatherProvider,
    OpenMeteoProvider,
    WeatherProviderError,
    _is_precip_code,
    _nowcast_now,
    _num,
    _text_is_wet,
    get_provider,
    google_air_quality,
    google_pollen,
    wmo_condition,
)


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


# ==============================================================================
# wmo_condition() Tests
# ==============================================================================

class TestWmoCondition:
    @pytest.mark.parametrize("code,expected", [
        (0, "Clear sky"),
        (61, "Slight rain"),
        (95, "Thunderstorm"),
    ])
    def test_known_codes(self, code: int, expected: str) -> None:
        assert wmo_condition(code) == expected

    def test_unknown_code_is_labeled(self) -> None:
        assert wmo_condition(12345) == "Unknown (12345)"

    def test_non_numeric_code_is_unknown(self) -> None:
        assert wmo_condition("not-a-code") == "Unknown"
        assert wmo_condition(None) == "Unknown"


# ==============================================================================
# _is_precip_code() Tests
# ==============================================================================

class TestIsPrecipCode:
    @pytest.mark.parametrize("code", [51, 61, 67, 71, 77, 80, 86, 95, 96, 99])
    def test_precip_codes(self, code: int) -> None:
        assert _is_precip_code(code) is True

    @pytest.mark.parametrize("code", [0, 1, 2, 3, 45, 50, 68, 70, 78, 79, 87, 97, 98])
    def test_non_precip_codes(self, code: int) -> None:
        assert _is_precip_code(code) is False

    def test_non_numeric_is_false(self) -> None:
        assert _is_precip_code("not-a-code") is False
        assert _is_precip_code(None) is False


# ==============================================================================
# _text_is_wet() Tests
# ==============================================================================

class TestTextIsWet:
    @pytest.mark.parametrize("text", ["Light rain", "RAIN SHOWERS", "Thunderstorm", "Regen", "Schneefall"])
    def test_wet_text(self, text: str) -> None:
        assert _text_is_wet(text) is True

    @pytest.mark.parametrize("text", ["Clear sky", "Partly cloudy", "", None])
    def test_dry_text(self, text) -> None:
        assert _text_is_wet(text) is False


# ==============================================================================
# _num() Tests
# ==============================================================================

class TestNum:
    def test_int_and_float_pass_through(self) -> None:
        assert _num(5) == 5
        assert _num(5.5) == 5.5

    def test_bool_is_rejected(self) -> None:
        """bool is technically an int subclass in Python -- must not slip through."""
        assert _num(True) is None
        assert _num(False) is None

    def test_non_numeric_is_none(self) -> None:
        assert _num("5") is None
        assert _num(None) is None


# ==============================================================================
# _nowcast_now() Tests
# ==============================================================================

class TestNowcastNow:
    def test_picks_the_slot_covering_now(self) -> None:
        minutely = {
            "time": ["2026-07-19T12:00", "2026-07-19T12:15", "2026-07-19T12:30", "2026-07-19T12:45"],
            "precipitation": [0.0, 0.5, 1.0, 0.0],
            "weather_code": [1, 61, 63, 1],
        }
        prec, code = _nowcast_now(minutely, "2026-07-19T12:20")
        assert prec == 0.5
        assert code == 61

    def test_empty_times_returns_none(self) -> None:
        assert _nowcast_now({"time": []}, "2026-07-19T12:00") == (None, None)
        assert _nowcast_now(None, "2026-07-19T12:00") == (None, None)

    def test_missing_now_iso_defaults_to_first_slot(self) -> None:
        minutely = {"time": ["2026-07-19T12:00"], "precipitation": [0.2], "weather_code": [61]}
        prec, code = _nowcast_now(minutely, None)
        assert prec == 0.2
        assert code == 61


# ==============================================================================
# OpenMeteoProvider.current() Tests
# ==============================================================================

class TestOpenMeteoCurrent:
    def _base_payload(self, **current_overrides) -> dict:
        current = {
            "time": "2026-07-19T12:00", "temperature_2m": 22.0, "relative_humidity_2m": 55,
            "apparent_temperature": 21.0, "is_day": 1, "precipitation": 0.0, "weather_code": 1,
            "wind_speed_10m": 10.0, "wind_direction_10m": 180, "cloud_cover": 20,
        }
        current.update(current_overrides)
        return {
            "current": current,
            "minutely_15": {"time": ["2026-07-19T12:00"], "precipitation": [0.0], "weather_code": [1]},
        }

    def test_dry_conditions(self) -> None:
        with patch("providers.requests.get", return_value=_mock_response(self._base_payload())):
            result = OpenMeteoProvider().current(51.34, 12.37)

        assert result["rain_now"] is False
        assert result["condition"] == "Mainly clear"
        assert result["provider"] == "open-meteo"

    def test_code_already_indicates_rain(self) -> None:
        payload = self._base_payload(weather_code=61, precipitation=2.0)
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = OpenMeteoProvider().current(51.34, 12.37)

        assert result["rain_now"] is True
        assert result["condition"] == "Slight rain"

    def test_amount_only_wet_gets_annotated(self) -> None:
        """Code says 'clear' but precipitation > 0 -- truth comes from the amount."""
        payload = self._base_payload(weather_code=1, precipitation=0.3)
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = OpenMeteoProvider().current(51.34, 12.37)

        assert result["rain_now"] is True
        assert "Mainly clear" in result["condition"]
        assert "precipitation" in result["condition"]

    def test_nowcast_detected_wet_overrides_dry_hourly_code(self) -> None:
        """Hourly code is dry, but the 15-min nowcast slot says rain -- must win."""
        payload = self._base_payload(weather_code=1, precipitation=0.0)
        payload["minutely_15"] = {"time": ["2026-07-19T12:00"], "precipitation": [0.4], "weather_code": [61]}
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = OpenMeteoProvider().current(51.34, 12.37)

        assert result["rain_now"] is True
        assert result["condition"] == "Slight rain"

    def test_request_failure_raises_weather_provider_error(self) -> None:
        with patch("providers.requests.get", side_effect=requests.RequestException("timeout")):
            with pytest.raises(WeatherProviderError):
                OpenMeteoProvider().current(51.34, 12.37)


# ==============================================================================
# OpenMeteoProvider.forecast() Tests
# ==============================================================================

class TestOpenMeteoForecast:
    def test_builds_normalized_day_list(self) -> None:
        payload = {
            "daily": {
                "time": ["2026-07-20", "2026-07-21"],
                "weather_code": [1, 61],
                "temperature_2m_max": [25.0, 20.0],
                "temperature_2m_min": [15.0, 12.0],
                "precipitation_sum": [0.0, 5.0],
                "precipitation_probability_max": [10, 80],
                "wind_speed_10m_max": [15.0, 25.0],
                "uv_index_max": [6.0, 3.0],
            }
        }
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = OpenMeteoProvider().forecast(51.34, 12.37, 2)

        assert len(result["days"]) == 2
        assert result["days"][0]["condition"] == "Mainly clear"
        assert result["days"][1]["condition"] == "Slight rain"
        assert result["days"][0]["uv_index"] == 6.0


# ==============================================================================
# GoogleWeatherProvider Tests
# ==============================================================================

class TestGoogleWeatherProvider:
    def test_missing_key_raises_before_any_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_WEATHER_API_KEY", raising=False)

        with pytest.raises(WeatherProviderError):
            GoogleWeatherProvider().current(51.34, 12.37)

    def test_current_parses_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_WEATHER_API_KEY", "test-key")
        payload = {
            "currentTime": "2026-07-19T12:00:00Z", "isDaytime": True,
            "temperature": {"degrees": 22.0}, "feelsLikeTemperature": {"degrees": 21.0},
            "relativeHumidity": 55,
            "precipitation": {"qpf": {"quantity": 0.0}, "probability": {"percent": 10}},
            "wind": {"speed": {"value": 10.0}, "direction": {"degrees": 180}},
            "weatherCondition": {"type": "CLEAR", "description": {"text": "Clear"}},
        }
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = GoogleWeatherProvider().current(51.34, 12.37)

        assert result["provider"] == "google"
        assert result["temperature_c"] == 22.0
        assert result["rain_now"] is False

    def test_current_detects_rain_from_high_probability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_WEATHER_API_KEY", "test-key")
        payload = {
            "currentTime": "2026-07-19T12:00:00Z", "isDaytime": True,
            "temperature": {"degrees": 18.0}, "feelsLikeTemperature": {"degrees": 17.0},
            "relativeHumidity": 80,
            "precipitation": {"qpf": {"quantity": 0.0}, "probability": {"percent": 75}},
            "wind": {"speed": {"value": 5.0}, "direction": {"degrees": 90}},
            "weatherCondition": {"type": "CLOUDY", "description": {"text": "Cloudy"}},
        }
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = GoogleWeatherProvider().current(51.34, 12.37)

        assert result["rain_now"] is True

    def test_forecast_parses_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_WEATHER_API_KEY", "test-key")
        payload = {
            "forecastDays": [{
                "displayDate": {"year": 2026, "month": 7, "day": 20},
                "maxTemperature": {"degrees": 25.0}, "minTemperature": {"degrees": 15.0},
                "daytimeForecast": {
                    "weatherCondition": {"type": "RAIN", "description": {"text": "Rain"}},
                    "precipitation": {"qpf": {"quantity": 3.0}, "probability": {"percent": 60}},
                    "wind": {"speed": {"value": 20.0}},
                    "uvIndex": 4,
                },
            }]
        }
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = GoogleWeatherProvider().forecast(51.34, 12.37, 1)

        assert result["days"][0]["date"] == "2026-07-20"
        assert result["days"][0]["temp_max_c"] == 25.0
        assert result["days"][0]["condition"] == "Rain"

    def test_request_failure_raises_weather_provider_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_WEATHER_API_KEY", "test-key")
        with patch("providers.requests.get", side_effect=requests.RequestException("timeout")):
            with pytest.raises(WeatherProviderError):
                GoogleWeatherProvider().current(51.34, 12.37)


# ==============================================================================
# google_pollen() / google_air_quality() Tests
# ==============================================================================

class TestGooglePollen:
    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_WEATHER_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(WeatherProviderError):
            google_pollen(51.34, 12.37)

    def test_parses_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_WEATHER_API_KEY", "test-key")
        payload = {
            "dailyInfo": [{
                "date": {"year": 2026, "month": 7, "day": 20},
                "pollenTypeInfo": [{
                    "code": "GRASS", "displayName": "Grass", "inSeason": True,
                    "indexInfo": {"value": 3, "category": "Moderate"},
                    "healthRecommendations": ["Stay indoors if sensitive"],
                }],
            }]
        }
        with patch("providers.requests.get", return_value=_mock_response(payload)):
            result = google_pollen(51.34, 12.37, days=1)

        assert result["days"][0]["date"] == "2026-07-20"
        assert result["days"][0]["types"][0]["code"] == "GRASS"
        assert result["days"][0]["recommendations"] == ["Stay indoors if sensitive"]


class TestGoogleAirQuality:
    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_WEATHER_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(WeatherProviderError):
            google_air_quality(51.34, 12.37)

    def test_parses_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_WEATHER_API_KEY", "test-key")
        payload = {
            "dateTime": "2026-07-19T12:00:00Z",
            "indexes": [{"code": "uaqi", "displayName": "AQI", "aqi": 42, "category": "Good", "dominantPollutant": "pm25"}],
            "healthRecommendations": {"generalPopulation": "Enjoy the outdoors"},
        }
        with patch("providers.requests.post", return_value=_mock_response(payload)):
            result = google_air_quality(51.34, 12.37)

        assert result["aqi"] == 42
        assert result["category"] == "Good"
        assert result["recommendation"] == "Enjoy the outdoors"


# ==============================================================================
# get_provider() Tests
# ==============================================================================

class TestGetProvider:
    def test_returns_open_meteo_by_name(self) -> None:
        assert isinstance(get_provider("open-meteo"), OpenMeteoProvider)

    def test_returns_google_by_name(self) -> None:
        assert isinstance(get_provider("google"), GoogleWeatherProvider)

    def test_unknown_name_raises_with_available_list(self) -> None:
        with pytest.raises(WeatherProviderError, match="Unknown weather provider"):
            get_provider("not-a-real-provider")

    def test_defaults_to_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEATHER_PROVIDER", "google")
        assert isinstance(get_provider(None), GoogleWeatherProvider)

    def test_name_is_case_and_whitespace_insensitive(self) -> None:
        assert isinstance(get_provider("  OPEN-METEO  "), OpenMeteoProvider)


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == "__main__":
    """
    Run tests with verbose output when executed directly.

    Usage:
        python test_providers.py

    Or with pytest:
        pytest test_providers.py -v
    """
    pytest.main([__file__, "-v", "--color=yes"])
