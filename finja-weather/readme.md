# 🌦️ Finja Weather API v1.0.0

A stateless weather microservice built for the **Finja AI Ecosystem**. It fetches normalized weather data for a given set of coordinates via a pluggable provider abstraction.

**Important:** This module handles **no user data and stores no user consent**. User location mapping and consent logic lives entirely on the Finja side. This microservice purely translates `(latitude, longitude)` into structured weather intelligence.

---

## ✨ Features

- **Provider Abstraction**: Switch easily between different weather providers.
  - **`open-meteo`** (Default): Free, no API key required, no billing. Perfect for self-hosting.
  - **`google`**: Google Maps Platform Weather API. Pre-built stub; requires a GCP billing account and API key. Bonus features like Pollen and Air Quality API are included on this provider.
- **REST API (FastAPI)**: Lightweight JSON endpoints secured via a shared Bearer Token.
- **Smart Location Caching**: To minimize upstream API calls (critical for paid APIs like Google), weather is cached based on *rounded* coordinates (approx. 1.1km grid). 10 users in the same town share a single upstream API call per TTL window!
- **Consensus Cross-Check**: (Optional) When multiple providers are available, the service cross-checks the current weather and leans towards rain on disagreement to prevent false-dry reports.
- **In-Memory Telemetry**: Self-contained counters, request durations, and cache hit-rates exposed via the `/stats` endpoint.

---

## 📁 Project Structure

| File | Description |
|------|-------------|
| `weather_api.py` | Main FastAPI application — REST endpoints and cache logic |
| `providers.py` | Provider implementations (Open-Meteo, Google) and WMO mapping |
| `generate_token.py` | Utility to generate a secure random Bearer token |
| `test_weather.py` | Smoke test script to verify API health and endpoints |
| `Dockerfile` | Container image: Python + Uvicorn + FastAPI |
| `docker-compose.yml` | Maps port 8095 to the container |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for environment variables |

---

## 🚀 Setup & Installation

### 1. Configure Environment

```bash
cp .env.example .env
```

### 2. Generate an Auth Token

The service is secured by a Bearer token. Run the generator script to create one:

```bash
python generate_token.py
```
*Copy the output `BEARER_TOKEN=...` and paste it into your `.env` file.*

### 3. Choose a Provider (Optional)

By default, the `.env` file uses `WEATHER_PROVIDER=open-meteo`.
If you want to use Google:
1. Change it to `WEATHER_PROVIDER=google`
2. Add your GCP key: `GOOGLE_WEATHER_API_KEY=your-api-key-here`

### 4. Start the Container

```bash
docker compose up -d --build
```
The service will be available on port `8095` (host) mapping to `80` (container).

### 5. Run Smoke Tests

```bash
python test_weather.py
```

---

## 💻 API Reference

### Authentication
All data endpoints require a Bearer token in the header:
`Authorization: Bearer <YOUR_TOKEN>`

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `GET` | `/health` | *None* | System health and small telemetry summary. *(No auth required)* |
| `GET` | `/stats` | *None* | Full telemetry snapshot (cache hits, latency, last errors). *(No auth required)* |
| `POST` | `/current` | `{latitude, longitude, [provider]}` | Returns normalized current weather. |
| `POST` | `/forecast` | `{latitude, longitude, days, [provider]}` | Returns a daily forecast for X days (1-16). |
| `POST` | `/pollen` | `{latitude, longitude, days}` | Returns pollen index (GRASS/TREE/WEED). **Google provider only.** |
| `POST` | `/air-quality`| `{latitude, longitude}` | Returns AQI, category, and health recommendations. **Google provider only.** |

### Normalized Schema (Provider-Agnostic)

The API responds with standard metric units regardless of the upstream provider:
- **Current**: `provider, latitude, longitude, time, is_day, temperature_c, feels_like_c, humidity_pct, precipitation_mm, wind_kmh, wind_dir_deg, weather_code, condition, duration_ms, cached, cache_age_s`
- **Forecast**: Returns an array of `days`, each containing: `date, temp_max_c, temp_min_c, precipitation_mm, precip_prob_pct, wind_max_kmh, uv_index, weather_code, condition`

---

## 🧰 Troubleshooting

| Problem | Solution |
|---------|----------|
| **401 Unauthorized** | The `Authorization` header is missing or incorrect. Make sure it exactly matches the `BEARER_TOKEN` in your `.env`. |
| **502 Bad Gateway / Provider Error** | The upstream provider (Open-Meteo or Google) is down or rejecting the request. Check `docker logs finja_weather`. |
| **Pollen / Air Quality returning 502** | These endpoints require the `google` provider. Ensure `GOOGLE_WEATHER_API_KEY` is set and has the specific APIs enabled in GCP. |
| **Changes to `.env` not applying** | You must restart the container for environment variables to take effect: `docker compose down && docker compose up -d`. |

---

## 📜 License

MIT License © 2026 J. Apps

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)
