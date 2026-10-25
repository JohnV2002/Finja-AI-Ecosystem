# 🎵 Finja Music System (Docker) v1.3.1
*Intelligent Spotify tracking, reaction generation & knowledge base for streamers. 💙*

[![Version](https://img.shields.io/badge/version-1.3.1-blue.svg)](https://github.com/JohnV2002/finja-music-docker-spotify)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../../LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-yellow.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

> **✨ New in v1.3.1:**
> - **Fix:** `spotify_reauth.py` can write a hidden `private/.env` on Windows (it stopped with `PermissionError` before) and keeps a granted token in a fallback file if a target cannot be written.
>
> **Changelog v1.3.0:**
> - **Spotify login expiry:** Since July 2026 Spotify ends refresh tokens 6 months after the login. An expired or revoked login is now `FINJA-408`: three quick tries, then a retry every 15 minutes (instead of a failing refresh every 5 seconds). `spotify_reauth.py` renews the token.
> - **Rate limits:** HTTP 429 waits for `Retry-After`; `/health` shows the Spotify state.
> - **Flare & Analytics (optional, off by default):** errors to the Analytics Collector; unexpected failures are `FINJA-522/523`; owner-only `/diagnostics/probe` (`FINJA-524`).
> - **Docker:** hardened compose (bind address, private network, limits, healthcheck).
>
> **Changelog v1.2.0:**
> - **Fix:** The example `.env` shipped with the repo used `CLIENT_ID`/`CLIENT_SECRET`
>   (no `SPOTIFY_` prefix, no refresh token) — `app.py` never reads those names, so
>   filling it in did nothing. Replaced with a correct `.env.example`.
> - **Change:** Real credentials now live in `private/.env` (never synced/committed)
>   instead of a plain `.env` at the repo root
> - Production and the public repo brought to a shared baseline
>
> **Changelog v1.1.0:**
> - **Song Features API:** New `/get/songs` and `/get/song_features` endpoints for BPM, Key, Energy, Danceability queries
> - **BPM Enrichment Pipeline:** `jank_scraper.js` (Spicetify extension) + `merge_bpm.py` for automated BPM/Key data collection
> - **Landing Page:** Root endpoint with API provider attribution
> - **Security:** `random` replaced with `secrets` module (SonarCloud compliance)

---

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Components](#-components)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [API Endpoints](#-api-endpoints)
- [Knowledge Base](#-knowledge-base)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Security](#-security)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Quick Start

**TL;DR - Get Running in 2 Minutes:**

1. **Clone the repository:**
   ```bash
   git clone https://github.com/JohnV2002/finja-music-docker-spotify.git
   cd finja-music-docker-spotify
   ```

2. **Add credentials:**
   ```bash
   mkdir -p private
   cp .env.example private/.env
   ```
   Then edit `private/.env`:
   ```ini
   SPOTIFY_CLIENT_ID=your_id_here
   SPOTIFY_CLIENT_SECRET=your_secret_here
   SPOTIFY_REFRESH_TOKEN=your_token_here
   ```

3. **Launch with Docker:**
   ```bash
   docker compose up -d --build
   ```

4. **Verify it's working:**
   Open `http://localhost:8022/get/Finja` in your browser.
   You should see a JSON response with the current song reaction.

---

## 🤖 Components

### Core Logic (`app.py`)

The brain of the operation. It handles the entire loop:
- **Monitoring:** Polls Spotify API (every ~5s) to detect changes.
- **Identification:** Matches songs against the local Knowledge Base (`SongsDB`).
- **Reaction:** Calculates a "Tier" (Love/Like/Neutral/Dislike) based on scoring.
- **Memory:** Updates `Memory/memory.json` to track how often a song was heard.

### Knowledge Base (`SongsDB`)

A local database that allows Finja to "know" music.
- **Normalization:** Intelligently handles "feat.", brackets, and case sensitivity.
- **Tagging:** Supports genres, moods, and custom tags per song.
- **Version Detection:** Automatically detects "Nightcore", "Speed Up", "Slowed" from titles.

### API Server (FastAPI)

Exposes the state to the outside world (e.g., for OBS overlays).
- **Port:** 8022
- **Format:** JSON
- **Performance:** Caches results to prevent unnecessary re-calculation.

---

## 📦 Installation

### Prerequisites

- **Docker & Docker Compose**
- **Spotify Developer Account** (to get Client ID/Secret)
- **Spotify Refresh Token** (for headless authentication)

### Step 1: Clone Repository

```bash
git clone https://github.com/JohnV2002/finja-music-docker-spotify.git
cd finja-music-docker-spotify
```

### Step 2: Environment Setup

Copy the template and fill in your real values. **Never commit `private/`!**

```bash
mkdir -p private
cp .env.example private/.env
```

`private/.env`:
```ini
SPOTIFY_CLIENT_ID=abc123...
SPOTIFY_CLIENT_SECRET=def456...
SPOTIFY_REFRESH_TOKEN=ghi789...
UID=1000  # Optional: Your Linux User ID
GID=1000  # Optional: Your Linux Group ID
```

### Step 3: Start Container

```bash
docker compose up -d --build
```

The service will start on `0.0.0.0:8022`.

---

## ⚙️ Configuration

All logic is configurable via JSON files mapped into the container.

| File | Path | Description |
|------|------|-------------|
| **Main Config** | `config_min.json` | Paths, intervals, sync guard settings. |
| **Reactions** | `Memory/reactions.json` | Reaction texts, sentiment thresholds, special rules. |
| **Contexts** | `Memory/contexts.json` | Profiles (e.g. "Gaming", "Chatting") to adjust scoring. |
| **Knowledge Base** | `SongsDB/songs_kb.json` | Database of known songs and metadata. |

### Example `config_min.json`

```json
{
  "interval_s": 5,
  "token_refresh_interval_s": 1500,
  "special_version_prefix": " (",
  "debug": true
}
```

---

## 📡 API Endpoints

The service exposes a FastAPI interface on Port **8022**.

| Method | Endpoint | Description | Response Example |
|--------|----------|-------------|------------------|
| `GET` | `/` | Landing page with attribution | HTML |
| `GET` | `/health` | Service health check | `{"ok": true, "time": "..."}` |
| `GET` | `/get/Finja` | Current song & reaction | `{"reaction": "Banger!", ...}` |
| `GET` | `/get/songs` | Browse KB with filters | `{"songs": [...], "total": N}` |
| `GET` | `/get/song_features` | Get BPM/Key/Energy for a song | `{"bpm": 128, "key": "C"}` |

#### Query Parameters

**`/get/songs`** — Browse the Knowledge Base:
- `artist` — Filter by artist name (fuzzy, case-insensitive)
- `genre` — Filter by genre/tag
- `limit` — Max results (default: 500)

**`/get/song_features`** — Look up a specific song:
- `title` — Song title
- `artist` — Artist name

### Response Structure (`/get/Finja`)

```json
{
  "reaction": "Still a banger.",
  "genres": "2020s, tekno, speed up",
  "title": "About You",
  "artist": "Rütekker",
  "context": "offline",
  "updated_at": "2026-01-07T16:20:00+00:00"
}
```

---

## 🛠️ Development

### File Structure

```
finja-music-docker-spotify/
├── app.py                  # Main application logic
├── config_min.json         # Core settings
├── docker-compose.yml      # Service definition
├── Dockerfile              # Image build instructions
├── requirements.txt        # Python dependencies
├── test_music_app.py       # Unit & Integration tests
├── jank_scraper.js         # Spicetify BPM/Key scraper extension
├── merge_bpm.py            # Migration tool: merge scraped BPM data into KB
├── .env.example            # Template -- copy to private/.env and fill in
├── .gitignore
├── .dockerignore
├── private/                # Real secrets (private/.env) -- never synced/committed
├── Memory/                 # Data folder
│   ├── memory.json         # Long-term history
│   ├── reactions.json      # Config for text output
│   └── contexts.json       # Config for scoring context
└── SongsDB/                # Knowledge Base
    └── songs_kb.json       # Song database
```

### Running Tests

This project includes a comprehensive test suite.

**Run inside Docker (Recommended):**
```bash
docker compose exec finja-musik-api python -m unittest test_music_app.py
```

**Run locally:**
```bash
pip install -r requirements.txt
python -m unittest test_music_app.py
```

---

## 🎵 BPM Enrichment Pipeline

The system can enrich songs with BPM, Key, and audio features using two tools:

### `jank_scraper.js` — Spicetify Extension

A Spicetify custom app that scrapes BPM and Key data directly from Spotify's DJ mode UI. Install it as a Spicetify extension and it will automatically POST data to `http://127.0.0.1:8080/submit` whenever a new song plays.

**Features:**
- Auto-detects song changes (polls every 2s)
- Reads BPM/Key from Spotify's `dj-info` UI elements
- Uses `127.0.0.1` instead of `localhost` (IPv6/IPv4 routing fix)

### `merge_bpm.py` — Migration Tool

Merges scraped BPM/Key data from `SongsDB/fertige_bpm_keys.json` into the main `songs_kb.json`. Run it after collecting data with the scraper.

```bash
python merge_bpm.py
```

- Creates automatic backups before merging
- Skips songs that already have BPM data
- Reports detailed statistics

---

## 🔧 Troubleshooting

### Spotify Issues

**Problem:** `FINJA-408 Spotify login expired or was revoked (invalid_grant)` / `/health` shows `reauthorization_needed`
- **Cause:** Spotify ends refresh tokens 6 months after the login (since July 2026), or access was removed in your Spotify account.
- **Fix:** On the PC with your browser, add `http://127.0.0.1:8888/callback` as a redirect URI in your app on the Spotify developer dashboard (once), then run:
  ```bash
  python spotify_reauth.py
  ```
  Log in; the new token lands in `private/.env` (never printed). With `--all-in-one-config <path>/config/config_spotify.json` the All-in-One edition gets it too. Copy `private/.env` to the server and restart the container.
- **Note:** Development-mode Spotify apps need the app owner to have Spotify Premium (since February 2026).

**Problem:** "Unknown" genre/reaction
- **Cause:** The song is not in `SongsDB/songs_kb.json`.
- **Fix:** Add the song to the KB or check `reactions.json` for fallback policies.

### Flare & Analytics (optional)

Settings in `private/.env` (see `.env.example`): `ANALYTICS_ENABLED`, `ANALYTICS_ENDPOINT` (e.g. `http://analytics-collector:8080` on the `flare-finja-private` network), `ANALYTICS_TOKEN`, `MUSIC_DOCKER_PROBE_TOKEN` (empty = probe off). Off means no thread and no network traffic. The compose file joins the external network `flare-finja-private` (create it once with `docker network create flare-finja-private`); `MUSIC_DOCKER_BIND` in a `.env` next to `docker-compose.yml` sets the port's bind address.

Errors: `FINJA-408` Spotify login expired/revoked or not configured (Flare asks a person), `FINJA-522` the polling loop, `FINJA-523` an unexpected request failure, `FINJA-524` the diagnostics probe.

### Docker Issues

**Problem:** Port 8022 already in use
- **Solution:** Change the port mapping in `docker-compose.yml`.
  ```yaml
  ports:
    - "8023:8022"
  ```

**Problem:** Permissions error in `Memory/`
- **Solution:** Ensure the host user owns the mapped directories.
  ```bash
  sudo chown -R $USER:$USER Memory Nowplaying SongsDB cache
  ```

---

## 🔒 Security

### Best Practices

- ⚠️ **Never commit `private/`** — that's where `private/.env` and your real Spotify credentials live
- ⚠️ **Never share Spotify Tokens** publicly
- ⚠️ **Restrict API access** if running on a public server (use a reverse proxy)

`.gitignore` already covers `private/`, `.env`, caches, and the real (vs. seed/example)
`Memory/`/`SongsDB/` data files — see the repo's own `.gitignore` for the full list.

---

## 🤝 Contributing

We welcome contributions! Here's how:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-logic`)
3. **Make your changes**
4. **Run tests** (`python -m unittest test_music_app.py`)
5. **Commit your changes** (`git commit -m 'Add amazing logic'`)
6. **Push to branch** (`git push origin feature/amazing-logic`)
7. **Open a Pull Request**

---

## 📄 License

**MIT** © J. Apps (JohnV2002 / Sodakiller1) — full text: repository root [`LICENSE`](../../LICENSE).

Keep copyright notices in source (MIT). Extra UI/log credits are appreciated, not required beyond MIT.

Ecosystem exceptions (assets, Apache modules): root [README — License & Usage](../../README.md#license--usage).

---

## 💖 Acknowledgments

- **FastAPI** — Modern high-performance web framework
- **Spotipy/Requests** — Reliable HTTP clients
- **Docker** — Containerization magic

---

*Finja says: "Music is the answer. 🎧"*