"""
======================================================================
         Finja Weather API – Providers
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / providers
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Pluggable weather provider abstraction for the Finja weather service.

  Main Responsibilities:
  - Define a provider-agnostic, normalized weather schema (metric units).
  - Implement the Open-Meteo provider (free, no API key).
  - Implement a Google Weather API provider stub (for later activation).
======================================================================
"""

from __future__ import annotations

import os
from typing import Any

import requests

# WMO weather interpretation codes -> short human condition text.
_WMO_CONDITIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def wmo_condition(code: Any) -> str:
    """Map a WMO weather code to a short condition string."""
    try:
        return _WMO_CONDITIONS.get(int(code), f"Unknown ({code})")
    except (TypeError, ValueError):
        return "Unknown"


# WMO codes that mean active precipitation (drizzle/rain/snow/showers/thunder).
_PRECIP_CODES = set(range(51, 68)) | set(range(71, 78)) | set(range(80, 87)) | {95, 96, 99}
# Keywords that mean "wet" in a free-text condition (Google's description).
_WET_WORDS = ("rain", "drizzle", "shower", "storm", "thunder", "snow", "sleet", "hail", "regen", "schnee")


def _is_precip_code(code: Any) -> bool:
    """True when a WMO code indicates active precipitation."""
    try:
        return int(code) in _PRECIP_CODES
    except (TypeError, ValueError):
        return False


def _text_is_wet(text: Any) -> bool:
    """True when a free-text condition mentions precipitation."""
    return any(w in str(text or "").lower() for w in _WET_WORDS)


def _num(value: Any) -> float | None:
    """Coerce to float, else None."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _nowcast_now(minutely: dict[str, Any] | None, now_iso: Any) -> tuple[float | None, Any]:
    """
    Pick the 15-min nowcast slot covering 'now' (radar-blended, sharper than the
    hourly model). Returns (precipitation_mm, weather_code) for that slot.
    """
    m = minutely or {}
    times = m.get("time") or []
    precs = m.get("precipitation") or []
    codes = m.get("weather_code") or []
    if not times:
        return None, None
    idx = 0
    for i, t in enumerate(times):
        if now_iso and str(t) <= str(now_iso):
            idx = i
        else:
            break
    prec = precs[idx] if idx < len(precs) else None
    code = codes[idx] if idx < len(codes) else None
    return _num(prec), code


class WeatherProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request."""


class WeatherProvider:
    """Base provider interface. Subclasses return the normalized schema."""

    name = "base"

    def current(self, lat: float, lon: float) -> dict[str, Any]:
        """Return normalized current weather for the coordinates."""
        raise NotImplementedError

    def forecast(self, lat: float, lon: float, days: int) -> dict[str, Any]:
        """Return normalized daily forecast for the coordinates."""
        raise NotImplementedError


class OpenMeteoProvider(WeatherProvider):
    """Free, key-less weather via Open-Meteo (https://open-meteo.com)."""

    name = "open-meteo"
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout: float = 8.0) -> None:
        """Store the request timeout."""
        self._timeout = timeout

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Perform the Open-Meteo request and return parsed JSON."""
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise WeatherProviderError(f"open-meteo request failed: {exc}") from exc

    def current(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Fetch and normalize current conditions.

        Truth for "is it raining right now" comes from PRECIPITATION (hourly +
        the 15-min radar-blended nowcast), not just the hourly model weather_code
        — the model often labels "clear/cloudy" while localized rain is falling.
        """
        data = self._get({
            "latitude": lat,
            "longitude": lon,
            "current": ",".join((
                "temperature_2m", "relative_humidity_2m", "apparent_temperature",
                "is_day", "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m",
                "cloud_cover",
            )),
            "minutely_15": "precipitation,weather_code",
            "forecast_minutely_15": 4,  # ~1h of radar-blended nowcast
            "timezone": "auto",
            "wind_speed_unit": "kmh",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        })
        cur = data.get("current") or {}
        code = cur.get("weather_code")
        hourly_precip = _num(cur.get("precipitation"))
        nc_precip, nc_code = _nowcast_now(data.get("minutely_15"), cur.get("time"))

        # Any precip signal (hourly or nowcast or a wet code) => it is raining now.
        precip_now = max([p for p in (hourly_precip, nc_precip) if p is not None] or [0.0])
        rain_now = precip_now > 0 or _is_precip_code(code) or _is_precip_code(nc_code)

        # Reconcile: never report a dry label when precip is detected. Prefer the
        # wet nowcast code; if only the amount betrays it, annotate honestly.
        condition_code = code
        if rain_now and not _is_precip_code(code) and _is_precip_code(nc_code):
            condition_code = nc_code
        condition = wmo_condition(condition_code)
        if rain_now and not _is_precip_code(condition_code):
            condition = f"{condition} + precipitation ({precip_now} mm now)"

        return {
            "provider": self.name,
            "latitude": lat,
            "longitude": lon,
            "time": cur.get("time"),
            "is_day": bool(cur.get("is_day")),
            "temperature_c": cur.get("temperature_2m"),
            "feels_like_c": cur.get("apparent_temperature"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "cloud_cover_pct": cur.get("cloud_cover"),
            "precipitation_mm": hourly_precip,
            "nowcast_precip_mm": nc_precip,
            "rain_now": bool(rain_now),
            "wind_kmh": cur.get("wind_speed_10m"),
            "wind_dir_deg": cur.get("wind_direction_10m"),
            "precip_prob_pct": None,  # open-meteo: only available in forecast, not current
            "weather_code": code,
            "condition": condition,
        }

    def forecast(self, lat: float, lon: float, days: int) -> dict[str, Any]:
        """Fetch and normalize a daily forecast."""
        data = self._get({
            "latitude": lat,
            "longitude": lon,
            "daily": ",".join((
                "weather_code", "temperature_2m_max", "temperature_2m_min",
                "precipitation_sum", "precipitation_probability_max", "wind_speed_10m_max",
                "uv_index_max",
            )),
            "forecast_days": max(1, min(days, 16)),
            "timezone": "auto",
            "wind_speed_unit": "kmh",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        })
        daily = data.get("daily") or {}
        dates = daily.get("time") or []
        out_days = []
        for i, date in enumerate(dates):
            code = _safe_index(daily.get("weather_code"), i)
            out_days.append({
                "date": date,
                "temp_max_c": _safe_index(daily.get("temperature_2m_max"), i),
                "temp_min_c": _safe_index(daily.get("temperature_2m_min"), i),
                "precipitation_mm": _safe_index(daily.get("precipitation_sum"), i),
                "precip_prob_pct": _safe_index(daily.get("precipitation_probability_max"), i),
                "wind_max_kmh": _safe_index(daily.get("wind_speed_10m_max"), i),
                "uv_index": _safe_index(daily.get("uv_index_max"), i),
                "weather_code": code,
                "condition": wmo_condition(code),
            })
        return {
            "provider": self.name,
            "latitude": lat,
            "longitude": lon,
            "days": out_days,
        }


class GoogleWeatherProvider(WeatherProvider):
    """Google Maps Platform Weather API provider.

    Needs GOOGLE_WEATHER_API_KEY (GCP billing account; check EEA/DE terms).
    Bonus SKUs available on the same key for later: Pollen API, Air Quality API.
    """

    name = "google"
    CURRENT_URL = "https://weather.googleapis.com/v1/currentConditions:lookup"
    FORECAST_URL = "https://weather.googleapis.com/v1/forecast/days:lookup"

    def __init__(self, timeout: float = 8.0) -> None:
        """Read the API key and store the timeout."""
        self._api_key = os.getenv("GOOGLE_WEATHER_API_KEY", "").strip()
        self._timeout = timeout

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Perform a Google Weather request and return parsed JSON."""
        if not self._api_key:
            raise WeatherProviderError(
                "GOOGLE_WEATHER_API_KEY not set — cannot use the google provider."
            )
        try:
            resp = requests.get(url, params={**params, "key": self._api_key}, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise WeatherProviderError(f"google weather request failed: {exc}") from exc

    def current(self, lat: float, lon: float) -> dict[str, Any]:
        """Fetch and normalize current conditions from Google."""
        d = self._get(self.CURRENT_URL, {"location.latitude": lat, "location.longitude": lon})
        precip = d.get("precipitation") or {}
        wind = d.get("wind") or {}
        cond = d.get("weatherCondition") or {}
        condition_text = (cond.get("description") or {}).get("text")
        precip_mm = _qty(precip.get("qpf"))
        precip_prob = (precip.get("probability") or {}).get("percent")
        # Rain truth for the consensus: actual amount, high probability, or a wet label.
        rain_now = (
            (precip_mm is not None and precip_mm > 0)
            or (precip_prob is not None and precip_prob >= 50)
            or _text_is_wet(condition_text)
        )
        return {
            "provider": self.name,
            "latitude": lat,
            "longitude": lon,
            "time": d.get("currentTime"),
            "is_day": bool(d.get("isDaytime")),
            "temperature_c": _deg(d.get("temperature")),
            "feels_like_c": _deg(d.get("feelsLikeTemperature")),
            "humidity_pct": d.get("relativeHumidity"),
            "precipitation_mm": precip_mm,
            "rain_now": bool(rain_now),
            "wind_kmh": (wind.get("speed") or {}).get("value"),
            "wind_dir_deg": (wind.get("direction") or {}).get("degrees"),
            "precip_prob_pct": precip_prob,
            "weather_code": cond.get("type"),
            "condition": condition_text,
        }

    def forecast(self, lat: float, lon: float, days: int) -> dict[str, Any]:
        """Fetch and normalize a daily forecast from Google (uses daytime forecast)."""
        d = self._get(self.FORECAST_URL, {
            "location.latitude": lat,
            "location.longitude": lon,
            "days": max(1, min(days, 16)),
        })
        out_days = []
        for fd in d.get("forecastDays") or []:
            dd = fd.get("displayDate") or {}
            date = (
                f"{int(dd['year']):04d}-{int(dd['month']):02d}-{int(dd['day']):02d}"
                if dd.get("year") else None
            )
            day = fd.get("daytimeForecast") or {}
            cond = day.get("weatherCondition") or {}
            precip = day.get("precipitation") or {}
            wind = day.get("wind") or {}
            out_days.append({
                "date": date,
                "temp_max_c": _deg(fd.get("maxTemperature")),
                "temp_min_c": _deg(fd.get("minTemperature")),
                "precipitation_mm": _qty(precip.get("qpf")),
                "precip_prob_pct": (precip.get("probability") or {}).get("percent"),
                "wind_max_kmh": (wind.get("speed") or {}).get("value"),
                "uv_index": day.get("uvIndex"),
                "weather_code": cond.get("type"),
                "condition": (cond.get("description") or {}).get("text"),
            })
        return {
            "provider": self.name,
            "latitude": lat,
            "longitude": lon,
            "days": out_days,
        }


def _google_key() -> str:
    """Return the Google API key (shared by Weather, Pollen and Air Quality)."""
    key = (os.getenv("GOOGLE_WEATHER_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise WeatherProviderError("GOOGLE_WEATHER_API_KEY not set — pollen/air-quality need the Google key.")
    return key


def google_pollen(lat: float, lon: float, days: int = 1, timeout: float = 8.0) -> dict[str, Any]:
    """Fetch and normalize a Google Pollen forecast (GRASS/TREE/WEED indices)."""
    key = _google_key()
    try:
        resp = requests.get(
            "https://pollen.googleapis.com/v1/forecast:lookup",
            params={"key": key, "location.latitude": lat, "location.longitude": lon, "days": max(1, min(days, 5))},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise WeatherProviderError(f"google pollen request failed: {exc}") from exc

    out_days = []
    for di in data.get("dailyInfo") or []:
        dd = di.get("date") or {}
        date = f"{int(dd['year']):04d}-{int(dd['month']):02d}-{int(dd['day']):02d}" if dd.get("year") else None
        types = []
        recs: list[str] = []
        for pt in di.get("pollenTypeInfo") or []:
            idx = pt.get("indexInfo") or {}
            types.append({
                "code": pt.get("code"),
                "name": pt.get("displayName"),
                "in_season": bool(pt.get("inSeason")),
                "index": idx.get("value"),
                "category": idx.get("category"),
            })
            for rec in pt.get("healthRecommendations") or []:
                if rec not in recs:
                    recs.append(rec)
        out_days.append({"date": date, "types": types, "recommendations": recs[:4]})
    return {"provider": "google", "latitude": lat, "longitude": lon, "days": out_days}


def google_air_quality(lat: float, lon: float, timeout: float = 8.0) -> dict[str, Any]:
    """Fetch and normalize Google Air Quality current conditions (AQI + recommendation)."""
    key = _google_key()
    try:
        resp = requests.post(
            "https://airquality.googleapis.com/v1/currentConditions:lookup",
            params={"key": key},
            json={"location": {"latitude": lat, "longitude": lon}, "extraComputations": ["HEALTH_RECOMMENDATIONS"]},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise WeatherProviderError(f"google air quality request failed: {exc}") from exc

    indexes = [
        {
            "code": i.get("code"),
            "name": i.get("displayName"),
            "aqi": i.get("aqi"),
            "category": i.get("category"),
            "dominant_pollutant": i.get("dominantPollutant"),
        }
        for i in data.get("indexes") or []
    ]
    primary = indexes[0] if indexes else {}
    recs = data.get("healthRecommendations") or {}
    return {
        "provider": "google",
        "latitude": lat,
        "longitude": lon,
        "datetime": data.get("dateTime"),
        "indexes": indexes,
        "aqi": primary.get("aqi"),
        "category": primary.get("category"),
        "dominant_pollutant": primary.get("dominant_pollutant"),
        "recommendation": recs.get("generalPopulation"),
    }


def _safe_index(seq: Any, idx: int) -> Any:
    """Return seq[idx] or None when out of range / not a list."""
    if isinstance(seq, list) and 0 <= idx < len(seq):
        return seq[idx]
    return None


def _deg(obj: Any) -> Any:
    """Extract Google's {unit, degrees} temperature value."""
    return obj.get("degrees") if isinstance(obj, dict) else None


def _qty(obj: Any) -> Any:
    """Extract Google's {unit, quantity} measure value."""
    return obj.get("quantity") if isinstance(obj, dict) else None


PROVIDERS = {
    "open-meteo": OpenMeteoProvider,
    "google": GoogleWeatherProvider,
}


def get_provider(name: str | None = None) -> WeatherProvider:
    """Return a provider instance by name (default from WEATHER_PROVIDER env)."""
    provider_name = (name or os.getenv("WEATHER_PROVIDER", "open-meteo")).strip().lower()
    provider_cls = PROVIDERS.get(provider_name)
    if not provider_cls:
        raise WeatherProviderError(
            f"Unknown weather provider '{provider_name}'. Available: {sorted(PROVIDERS)}"
        )
    return provider_cls()
