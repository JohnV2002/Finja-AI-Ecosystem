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
- **Consensus Cross-Check**: On `/current`, cross-checks the other provider and leans toward rain on disagreement (a missed rain is worse than a false alarm). Only fires when a second provider is usable (Google needs a key). Enabled by default via `WEATHER_CONSENSUS=1` — disable in `.env` if you'd rather only ever hit one provider.
- **In-Memory Telemetry**: Self-contained counters, request durations, and cache hit-rates exposed via the `/stats` endpoint.

---

## 📁 Project Structure

| File | Description |
|------|-------------|
| `weather_api.py` | Main FastAPI application — REST endpoints and cache logic |
| `providers.py` | Provider implementations (Open-Meteo, Google) and WMO mapping |
| `generate_token.py` | Utility to generate a secure random Bearer token |
| `test_weather.py` | Smoke test script to verify API health and endpoints against a running instance |
| `test_weather_api.py` | Unit tests: auth, caching, consensus merge, error mapping (mocked providers) |
| `test_providers.py` | Unit tests: WMO condition mapping, Open-Meteo/Google parsing (mocked HTTP) |
| `test_docker_config.py` | Config tests: Dockerfile/Compose sanity checks |
| `Dockerfile` | Container image: Python + Uvicorn + FastAPI |
| `docker-compose.yml` | Maps port 8095 to the container |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for environment variables |
| `.dockerignore` | Excludes dev/test files from the Docker build context |

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

Consensus cross-check (`WEATHER_CONSENSUS=1` by default) queries the *other*
provider too on `/current` and leans toward rain on disagreement. Set it to
`0` if you'd rather only ever call one provider per request.

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

## 🧪 Running Tests

Unit tests mock all outbound HTTP calls — no real provider API key or running
container needed.

```bash
pip install pytest pytest-cov pytest-mock fastapi uvicorn requests pydantic python-dotenv
```

**API Tests** (auth, caching, consensus merge, error mapping):
```bash
pytest test_weather_api.py -v
```

**Provider Tests** (WMO mapping, Open-Meteo/Google parsing, mocked HTTP):
```bash
pytest test_providers.py -v
```

**Docker Config Tests** (Dockerfile/Compose sanity):
```bash
pytest test_docker_config.py -v
```

**All Tests:**
```bash
pytest test_weather_api.py test_providers.py test_docker_config.py -v
```

`test_weather.py` is a separate **smoke test**, not a pytest suite — it hits a
*running* instance for a live end-to-end check:
```bash
docker compose up -d --build
python test_weather.py
```

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
