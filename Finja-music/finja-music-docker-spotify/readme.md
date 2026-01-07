# 🎵 Finja Music System (Docker)
*Intelligent Spotify tracking, reaction generation & knowledge base for streamers. 💙*

[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/JohnV2002/finja-music-docker-spotify)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-yellow.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

> **✨ New in v1.0.1:**
> - **Code Quality:** All SonarQube issues resolved (S5754, S1192, S3358, S3776)
> - **Documentation:** Complete English documentation with comprehensive comments
> - **Docker:** Port mapping standardized to `8022` to match container config
> - **Stability:** Refactored nested logic and improved error handling
> - **Copyright:** Updated to 2026 standards
> - **Fallback:** Improved "Unknown" handling for missing KB entries

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
   Create a `.env` file in the root directory:
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

Create a `.env` file. **Do not share this file!**

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
| `GET` | `/health` | Service health check | `{"ok": true, "time": "..."}` |
| `GET` | `/get/Finja` | Current song & reaction | `{"reaction": "Banger!", ...}` |

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
├── .env                    # Secrets (Excluded from git)
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

## 🔧 Troubleshooting

### Spotify Issues

**Problem:** `[spotify] refresh error 400`
- **Solution:** Your Refresh Token is invalid or expired.
- **Fix:** Generate a new token using a tool like [Spotify Token Generator](https://developer.spotify.com/documentation/web-api).

**Problem:** "Unknown" genre/reaction
- **Cause:** The song is not in `SongsDB/songs_kb.json`.
- **Fix:** Add the song to the KB or check `reactions.json` for fallback policies.

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

- ⚠️ **Never commit `.env` files** to version control
- ⚠️ **Never share Spotify Tokens** publicly
- ⚠️ **Add `.env` to `.gitignore`**
- ⚠️ **Restrict API access** if running on a public server (use a reverse proxy)

### `.gitignore` Recommendation

```gitignore
.env
__pycache__/
*.pyc
.pytest_cache/
cache/
Nowplaying/
```

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

MIT © 2026 J. Apps (JohnV2002 / Sodakiller1)

**You are free to:**
- ✅ Use this code commercially
- ✅ Modify and adapt it
- ✅ Distribute and sell it
- ✅ Use it in closed-source projects

**The only requirement:**
- ⭐ **Keep the attribution visible** — Credit must remain in the UI/Logs.

**Why attribution matters:**
Money comes and goes, but **reputation is gold**. This project is free for everyone, but credit keeps the open-source spirit alive and helps others discover the project.

**Links:**
- 🎮 Twitch: [twitch.tv/sodakiller1](https://twitch.tv/sodakiller1)
- 💼 Company: J. Apps
- 👤 GitHub: JohnV2002

---

### Full MIT License Text

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

**The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.**

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 💖 Acknowledgments

- **FastAPI** — Modern high-performance web framework
- **Spotipy/Requests** — Reliable HTTP clients
- **Docker** — Containerization magic

---

*Finja says: "Music is the answer. 🎧"*