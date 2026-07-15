"""
======================================================================
         Finja Weather API – Service
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / weather_api
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
  Stateless weather microservice for Finja. Fetches normalized weather
  for given coordinates via a pluggable provider (Open-Meteo or Google).

  Main Responsibilities:
  - Expose /current and /forecast for coordinates.
  - Bearer-token auth, health + self-contained telemetry (/stats).
  - Stay stateless: no user data, no consent storage (handled in Finja).
======================================================================
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from providers import WeatherProviderError, get_provider, google_air_quality, google_pollen

load_dotenv()

SERVICE_NAME = "finja-weather"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("finja.weather")

EXPECTED_BEARER_TOKEN = os.getenv("BEARER_TOKEN")
DEFAULT_PROVIDER = os.getenv("WEATHER_PROVIDER", "open-meteo").strip().lower()

app = FastAPI(title="Finja Weather API", version="0.1.0")

# ── Telemetry (self-contained, in-process counters exposed via /stats) ─────────
_METRICS_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = collections.defaultdict(int)
_DUR_SUM: dict[str, float] = collections.defaultdict(float)
_DUR_CNT: dict[str, int] = collections.defaultdict(int)
_STARTED_AT = time.time()
_LAST_ERROR: dict[str, object] = {"msg": None, "at": None}


def _m_incr(key: str, n: int = 1) -> None:
    """Increment a named counter."""
    with _METRICS_LOCK:
        _COUNTERS[key] += n


def _m_observe(key: str, ms: float) -> None:
    """Record a duration sample (ms) for averaging."""
    with _METRICS_LOCK:
        _DUR_SUM[key] += ms
        _DUR_CNT[key] += 1


def _m_error(msg: object) -> None:
    """Remember the most recent error for /stats."""
    with _METRICS_LOCK:
        _LAST_ERROR["msg"] = str(msg)[:300]
        _LAST_ERROR["at"] = int(time.time())


def _m_snapshot() -> dict:
    """Return a JSON-safe telemetry snapshot."""
    with _METRICS_LOCK:
        avg = {k: round(_DUR_SUM[k] / _DUR_CNT[k]) for k in _DUR_CNT if _DUR_CNT[k]}
        return {
            "service": SERVICE_NAME,
            "uptime_s": int(time.time() - _STARTED_AT),
            "provider": DEFAULT_PROVIDER,
            "counters": dict(_COUNTERS),
            "avg_duration_ms": avg,
            "last_error": dict(_LAST_ERROR),
        }


# ── Location cache ─────────────────────────────────────────────────────────────
# Weather barely changes per minute and is identical for everyone at the same spot.
# We cache by ROUNDED coordinates (not per user) so 10 people in the same town share
# ONE upstream API call per TTL window — important for the paid Google provider.
WEATHER_CACHE_CURRENT_TTL = int(os.getenv("WEATHER_CACHE_CURRENT_TTL_S", "600"))      # 10 min
WEATHER_CACHE_FORECAST_TTL = int(os.getenv("WEATHER_CACHE_FORECAST_TTL_S", "3600"))   # 1 h
WEATHER_CACHE_POLLEN_TTL = int(os.getenv("WEATHER_CACHE_POLLEN_TTL_S", "10800"))      # 3 h (daily data)
WEATHER_CACHE_AQ_TTL = int(os.getenv("WEATHER_CACHE_AQ_TTL_S", "1800"))               # 30 min
WEATHER_CACHE_PRECISION = int(os.getenv("WEATHER_CACHE_PRECISION", "2"))              # 2 dp ≈ 1.1 km grid

# Consensus: cross-check /current against the OTHER provider and lean toward rain
# on disagreement. Fires only when the second provider is usable (Google needs a
# key). Default on; weather is requested rarely + cached, so the extra call is cheap.
WEATHER_CONSENSUS = os.getenv("WEATHER_CONSENSUS", "1").strip().lower() in {"1", "true", "yes", "on"}


def _google_available() -> bool:
    """True when a Google key is configured (so the google provider can be used)."""
    return bool((os.getenv("GOOGLE_WEATHER_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())


def _merge_consensus(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    """
    Merge two providers' current weather. Rain is the OR of both (a missed rain is
    worse than a false alarm); on disagreement the condition is reported honestly
    as 'unsettled' and leans toward the wet source.
    """
    pr, sr = bool(primary.get("rain_now")), bool(secondary.get("rain_now"))
    agree = pr == sr
    merged = dict(primary)
    merged["rain_now"] = pr or sr
    merged["consensus"] = {
        "agreement": agree,
        "rain_now": pr or sr,
        "sources": [
            {"provider": primary.get("provider"), "condition": primary.get("condition"),
             "precipitation_mm": primary.get("precipitation_mm"), "rain": pr},
            {"provider": secondary.get("provider"), "condition": secondary.get("condition"),
             "precipitation_mm": secondary.get("precipitation_mm"), "rain": sr},
        ],
    }
    if not agree:
        wet, dry = (primary, secondary) if pr else (secondary, primary)
        merged["condition"] = (
            f"unsettled — {wet.get('provider')} sees {wet.get('condition')}, "
            f"{dry.get('provider')} sees {dry.get('condition')}"
        )
    return merged


class _LocationCache:
    """Thread-safe TTL cache keyed by (kind, provider, rounded lat/lon, days)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[tuple, dict] = {}
        self.hits = 0
        self.misses = 0

    def _key(self, kind: str, provider: str, lat: float, lon: float, days: int) -> tuple:
        return (kind, provider, round(lat, WEATHER_CACHE_PRECISION), round(lon, WEATHER_CACHE_PRECISION), days)

    def get(self, kind: str, provider: str, lat: float, lon: float, days: int):
        """Return (data, age_seconds) on a fresh hit, else None."""
        key = self._key(kind, provider, lat, lon, days)
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry and entry["exp"] > now:
                self.hits += 1
                return entry["data"], int(now - entry["born"])
            if entry:
                self._store.pop(key, None)  # expired
            self.misses += 1
            return None

    def set(self, kind: str, provider: str, lat: float, lon: float, days: int, data: dict, ttl: int) -> None:
        """Store a payload under the rounded-location key with a TTL."""
        key = self._key(kind, provider, lat, lon, days)
        now = time.time()
        with self._lock:
            self._store[key] = {"born": now, "exp": now + ttl, "data": data}

    def snapshot(self) -> dict:
        """Cache metrics for /stats."""
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


_cache = _LocationCache()


def _require_auth(authorization: str | None) -> None:
    """Validate bearer-token authentication when configured."""
    if not EXPECTED_BEARER_TOKEN:
        return
    if authorization != f"Bearer {EXPECTED_BEARER_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


class CurrentRequest(BaseModel):
    """Current-weather request for one coordinate."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    provider: str | None = Field(default=None, description="Override provider (default: env)")


class ForecastRequest(CurrentRequest):
    """Daily forecast request."""

    days: int = Field(default=5, ge=1, le=16)


class PollenRequest(BaseModel):
    """Pollen forecast request (Google only)."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    days: int = Field(default=1, ge=1, le=5)


class AirQualityRequest(BaseModel):
    """Air quality request (Google only)."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


def _resolve_provider(name: str | None):
    """Resolve a provider, mapping unknown names to a clean 400."""
    try:
        return get_provider(name)
    except WeatherProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
async def health() -> dict:
    """Health/status endpoint with a small telemetry summary."""
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "uptime_s": int(time.time() - _STARTED_AT),
        "provider": DEFAULT_PROVIDER,
        "current_total": _COUNTERS.get("current_total", 0),
        "forecast_total": _COUNTERS.get("forecast_total", 0),
        "cache_hit_rate": _cache.snapshot()["hit_rate"],
    }


@app.get("/stats")
async def stats() -> dict:
    """Self-contained telemetry snapshot (counters + avg durations + cache + last error)."""
    snap = _m_snapshot()
    snap["cache"] = _cache.snapshot()
    return snap


@app.post("/current", responses={401: {"description": "Unauthorized"}})
async def current_endpoint(
    request: Annotated[CurrentRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return normalized current weather for a coordinate."""
    _require_auth(authorization)
    _m_incr("current_total")
    provider = _resolve_provider(request.provider)

    cached = _cache.get("current", provider.name, request.latitude, request.longitude, 0)
    if cached is not None:
        data, age = cached
        _m_incr("current_cache_hit")
        logger.info("Current weather CACHE HIT (age=%ds) lat=%.4f lon=%.4f", age, request.latitude, request.longitude)
        return {**data, "cached": True, "cache_age_s": age}

    start = time.time()
    logger.info("Current weather: lat=%.4f lon=%.4f provider=%s", request.latitude, request.longitude, provider.name)
    try:
        result = provider.current(request.latitude, request.longitude)
    except WeatherProviderError as exc:
        _m_incr("current_fail")
        _m_error(f"current: {exc}")
        logger.warning("Current weather failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    duration_ms = int((time.time() - start) * 1000)
    _m_incr("current_ok")
    _m_observe("current", duration_ms)

    # Consensus cross-check against the OTHER provider (lean toward rain on disagreement).
    if WEATHER_CONSENSUS:
        other_name = "google" if provider.name == "open-meteo" else "open-meteo"
        if other_name != "google" or _google_available():
            try:
                second = get_provider(other_name).current(request.latitude, request.longitude)
                result = _merge_consensus(result, second)
                _m_incr("consensus_ok")
                logger.info("Consensus: %s+%s agree=%s rain_now=%s",
                            provider.name, other_name,
                            result["consensus"]["agreement"], result["consensus"]["rain_now"])
            except WeatherProviderError as exc:
                result.setdefault("consensus", {"agreement": None, "note": f"{other_name} unavailable: {exc}"})
                _m_incr("consensus_skip")

    logger.info("Current weather ok: %s %s°C (%dms)", result.get("condition"), result.get("temperature_c"), duration_ms)
    result["duration_ms"] = duration_ms
    result["cached"] = False
    _cache.set("current", provider.name, request.latitude, request.longitude, 0, result, WEATHER_CACHE_CURRENT_TTL)
    return result


@app.post("/forecast", responses={401: {"description": "Unauthorized"}})
async def forecast_endpoint(
    request: Annotated[ForecastRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return a normalized daily forecast for a coordinate."""
    _require_auth(authorization)
    _m_incr("forecast_total")
    provider = _resolve_provider(request.provider)

    cached = _cache.get("forecast", provider.name, request.latitude, request.longitude, request.days)
    if cached is not None:
        data, age = cached
        _m_incr("forecast_cache_hit")
        logger.info("Forecast CACHE HIT (age=%ds) lat=%.4f lon=%.4f days=%d",
                    age, request.latitude, request.longitude, request.days)
        return {**data, "cached": True, "cache_age_s": age}

    start = time.time()
    logger.info("Forecast: lat=%.4f lon=%.4f days=%d provider=%s",
                request.latitude, request.longitude, request.days, provider.name)
    try:
        result = provider.forecast(request.latitude, request.longitude, request.days)
    except WeatherProviderError as exc:
        _m_incr("forecast_fail")
        _m_error(f"forecast: {exc}")
        logger.warning("Forecast failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    duration_ms = int((time.time() - start) * 1000)
    _m_incr("forecast_ok")
    _m_observe("forecast", duration_ms)
    logger.info("Forecast ok: %d day(s) (%dms)", len(result.get("days") or []), duration_ms)
    result["duration_ms"] = duration_ms
    result["cached"] = False
    _cache.set("forecast", provider.name, request.latitude, request.longitude, request.days, result, WEATHER_CACHE_FORECAST_TTL)
    return result


@app.post("/pollen", responses={401: {"description": "Unauthorized"}})
async def pollen_endpoint(
    request: Annotated[PollenRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return a normalized Google pollen forecast (GRASS/TREE/WEED + recommendations)."""
    _require_auth(authorization)
    _m_incr("pollen_total")

    cached = _cache.get("pollen", "google", request.latitude, request.longitude, request.days)
    if cached is not None:
        data, age = cached
        _m_incr("pollen_cache_hit")
        logger.info("Pollen CACHE HIT (age=%ds) lat=%.4f lon=%.4f", age, request.latitude, request.longitude)
        return {**data, "cached": True, "cache_age_s": age}

    start = time.time()
    logger.info("Pollen: lat=%.4f lon=%.4f days=%d", request.latitude, request.longitude, request.days)
    try:
        result = google_pollen(request.latitude, request.longitude, request.days)
    except WeatherProviderError as exc:
        _m_incr("pollen_fail")
        _m_error(f"pollen: {exc}")
        logger.warning("Pollen failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    duration_ms = int((time.time() - start) * 1000)
    _m_incr("pollen_ok")
    _m_observe("pollen", duration_ms)
    result["duration_ms"] = duration_ms
    result["cached"] = False
    _cache.set("pollen", "google", request.latitude, request.longitude, request.days, result, WEATHER_CACHE_POLLEN_TTL)
    return result


@app.post("/air-quality", responses={401: {"description": "Unauthorized"}})
async def air_quality_endpoint(
    request: Annotated[AirQualityRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return normalized Google air quality (AQI + category + recommendation)."""
    _require_auth(authorization)
    _m_incr("air_quality_total")

    cached = _cache.get("air_quality", "google", request.latitude, request.longitude, 0)
    if cached is not None:
        data, age = cached
        _m_incr("air_quality_cache_hit")
        logger.info("Air quality CACHE HIT (age=%ds) lat=%.4f lon=%.4f", age, request.latitude, request.longitude)
        return {**data, "cached": True, "cache_age_s": age}

    start = time.time()
    logger.info("Air quality: lat=%.4f lon=%.4f", request.latitude, request.longitude)
    try:
        result = google_air_quality(request.latitude, request.longitude)
    except WeatherProviderError as exc:
        _m_incr("air_quality_fail")
        _m_error(f"air_quality: {exc}")
        logger.warning("Air quality failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    duration_ms = int((time.time() - start) * 1000)
    _m_incr("air_quality_ok")
    _m_observe("air_quality", duration_ms)
    result["duration_ms"] = duration_ms
    result["cached"] = False
    _cache.set("air_quality", "google", request.latitude, request.longitude, 0, result, WEATHER_CACHE_AQ_TTL)
    return result


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "80"))
    logger.info("Starting Finja Weather API on %s:%s (provider=%s)...", host, port, DEFAULT_PROVIDER)
    uvicorn.run("weather_api:app", host=host, port=port)
