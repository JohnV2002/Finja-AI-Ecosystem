# 💬 Finja Chat System — v2.4.0
*OBS Chat Overlay + Bot Panel + Song Requests — cute, fast, Gen-Z approved. 💙*

[![Version](https://img.shields.io/badge/version-2.4.0-blue.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/tree/main/finja-chat)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)](https://www.python.org/)

> **✨ New in v2.4.0:**
> - **24/7 Twitch OAuth:** public Device Code authorization with rotating access
>   and refresh tokens; no client secret is stored in the browser or repository
> - **Chat recovery:** hourly token validation, pre-expiry rotation, and controlled
>   reconnect after authentication or socket failures
> - Structured diagnostics: `FINJA-404` (device auth), `FINJA-405` (refresh), and
>   `FINJA-406` (reconnect recovery)
>
> **Changelog v2.3.0:**
> - **Song request toggle:** switch live between 24/7 auto-filter and manual
>   moderation via a button in the bot panel (no server restart needed)
> - **Fix:** `!pulse` was documented but had no effect — now properly wired up
> - Production and the public repo brought to a shared baseline
>
> **Changelog v2.2.1:**
> - **Code Quality:** All SonarQube issues resolved across all files
> - **Documentation:** Complete English documentation with comprehensive comments
> - **Finja stays ALWAYS blue** — no matter what accent is set!
> - `!uptime` command shows stream duration
> - **VPet Bridge & Song Requests** are now toggleable in the bot panel
> - AI responses stay **visible longer** in the overlay
> - Improved **system prompt** with streamer & game context
> - Better error handling and user feedback throughout

---

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Components](#-components)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Commands](#-commands)
- [Song Requests (Spotify)](#-song-requests-spotify)
- [7TV Emotes Setup](#-7tv-emotes-setup)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Security](#-security)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Quick Start

**TL;DR - Get Running in 5 Minutes:**

1. **Start the web server:**
   ```bash
   # Windows
   start_static_server.bat
   
   # Linux/Mac
   python -m http.server 8088
   ```

2. **Access the overlay (dev mode):**
   ```
   http://127.0.0.1:8088/index_merged.html?channel=YOURCHANNEL&dev=1
   ```

3. **Open the bot panel:**
   ```
   http://127.0.0.1:8088/bot_merged.html
   ```
   - Enter your public Twitch application's Client ID
   - Click **Twitch dauerhaft autorisieren**
   - Open the displayed Twitch activation link and confirm the device code once
   - Lexi validates, rotates, and reconnects with the token automatically afterward

4. **(Optional) Start song requests:**
   ```bash
   python spotify_request_server_env.py
   ```

---

## 🤖 Components

### Bot Panel (`bot_merged.html`)

The central control hub for your Twitch bot integration.

**Features:**
- Connects to Twitch chat via ComfyJS
- Executes chat commands (`!theme`, `!rgb`, `!uptime`, etc.)
- Controls OBS via WebSocket v5 (overlay URL updates & refresh)
- Integrates with OpenWebUI for AI chat responses
- Modular toggles for VPet Bridge and Song Requests
- Real-time log display
- Twitch Device Code OAuth with automatic token rotation and reconnect recovery

**Technology Stack:**
- ComfyJS for Twitch chat
- OBS WebSocket v5 for OBS control
- BroadcastChannel API for overlay communication
- LocalStorage for settings persistence

### Overlay (`index_merged.html`)

Beautiful chat message display for OBS with extensive customization.

**Features:**
- Multiple themes (glass, dark, light, neon)
- RGB effects (ring, fill, both)
- Customizable opacity and pulse animations
- Automatic emote loading (Twitch, 7TV, BTTV, FFZ)
- Badge display with proper icons
- Developer mode with live settings panel (`?dev=1`)
- LLM response display with extended duration
- Finja always stays blue (locked accent color)

**Themes:**
- **Glass** — Frosted glass effect with blur
- **Dark** — Clean dark mode
- **Light** — Bright and minimal
- **Neon** — Vibrant glow effects with auto-RGB

### Song Request Server (`spotify_request_server_env.py`)

Moderated Spotify song request system with queue management.

**Features:**
- Viewer song requests via `!sr` command
- Moderator approval/denial system
- Cooldown enforcement (configurable, default 120s)
- Direct Spotify URI/URL support
- Search query support
- Device selection (preferred or active)
- Finja's friendly response messages
- RESTful API for pending requests

**Endpoints:**
- `GET /health` — Health check
- `GET /pending` — List pending requests
- `GET /devices` — List Spotify devices
- `POST /chat` — Handle chat commands

### Command Bridge (`command_bridge.py`)

HTTP bridge for VPet Desktop Pet integration.

**Features:**
- Receives commands from Twitch bot
- Provides polling endpoint for VPet plugin
- Timestamp-based deduplication
- Simple in-memory storage

---

## 📦 Installation

### Prerequisites

- **Python 3.10+** (recommended)
- **Node.js** (optional, for development)
- **OBS Studio** with WebSocket plugin v5
- **Spotify Premium** account (for song requests)

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/finja-chat.git
cd finja-chat
```

### Step 2: Install Python Dependencies

For the full setup (including song requests):

```bash
pip install fastapi uvicorn spotipy python-dotenv
```

For testing:

```bash
pip install pytest
```

### Step 3: Start the Static Server

**Windows:**
```bash
start_static_server.bat
```

**Linux/Mac:**
```bash
python -m http.server 8088
```

The server will start on `http://127.0.0.1:8088`

---

## ⚙️ Configuration

### Twitch OAuth with Auto-Refresh

Lexi uses Twitch's public **Device Code Grant**, so the panel can rotate tokens
without embedding a client secret.

1. Open the [Twitch Developer Console](https://dev.twitch.tv/console/apps).
2. Create a dedicated application for Finja Chat. Twitch requires 2FA on the
   developer account.
3. Set **Client Type** to **Public**. The redirect URL is not used by the Device
   Code flow; if the console requires one, use a local placeholder such as
   `http://localhost`.
4. Copy the **Client ID** into the bot panel. Client IDs are public identifiers;
   never copy a Client Secret into the panel.
5. Click **Twitch dauerhaft autorisieren**, open the displayed activation link,
   and approve `chat:read` and `chat:edit` with the Lexi bot account.

The panel validates the token on startup and hourly, rotates the one-time refresh
token before the access token expires, and reconnects the existing chat client.
Tokens remain local to that browser origin and are never written to logs.

The legacy `oauth:...` input remains available for emergency migration, but those
tokens are not refreshable. A public-client refresh token may require the Device
Code step again after more than 30 days of inactivity, a password change, or an
app revocation.

### OBS WebSocket

1. In OBS: **Tools → WebSocket Server Settings**
2. Enable the server (default port: `4455`)
3. Set a password
4. In bot panel under **OBS Sync**:
   - Address: `ws://127.0.0.1:4455`
   - Password: (your password)
   - Browser Source: name of your OBS browser source

### OpenWebUI / LLM (Optional)

For AI chat responses:

1. Install OpenWebUI: [https://docs.openwebui.com/](https://docs.openwebui.com/)
2. Get your API key from OpenWebUI settings
3. In bot panel under **LLM Chatbot**:
   - Enable LLM Chatbot
   - OpenWebUI URL: `http://localhost:3000` (or your URL)
   - Model ID: `llama3:latest` (or your model)
   - API Key: (your OpenWebUI key)
   - System Prompt: Customize Finja's personality

### VPet Bridge (Optional)

1. Install VPet Desktop Pet
2. Start the command bridge:
   ```bash
   python command_bridge.py
   ```
3. Configure VPet plugin to poll `http://127.0.0.1:8091/command`

---

## 🎵 Song Requests (Spotify)

### Prerequisites

- Spotify account (Premium recommended)
- Spotify Developer App credentials

### Setup

**1. Create Spotify App:**

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your **Client ID** and **Client Secret**
4. Add redirect URI: `http://localhost:8080/callback`

**2. Create `.env` file:**

Copy `.env.example` to `private/.env` (the `private/` folder is never committed —
that's where all local secrets/credentials live):

```env
# Spotify Credentials
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://localhost:8080/callback

# Song Request Settings
SR_COOLDOWN_SECS=120
SR_FORCE_NOW=false
SR_MAX_PENDING_PER_USER=1
# false = auto-filter mode (popularity/label check, auto-queues if it passes)
# true  = full moderation queue (!accept/!deny/!rq)
SR_MODERATED=false
SR_MIN_POPULARITY=15

# Optional: Preferred Device
SPOTIFY_DEVICE_NAME=My Computer
# OR
SPOTIFY_DEVICE_ID=abc123def456
```

**3. Start the server:**

**Windows:**
```bash
start_server_with_env.bat
```

**Linux/Mac:**
```bash
python -m dotenv run -- uvicorn spotify_request_server_env:app --port 8099 --reload
```

**4. Verify it's running:**

Visit `http://127.0.0.1:8099/health`

### Usage

**For Viewers:**
```
!sr Never Gonna Give You Up
!sr spotify:track:4cOdK2wGLETKBW3PvgPWqT
!sr https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT
```

**For Moderators:**
```
!rq              # List pending requests
!accept 1        # Accept request with ID 1
!deny 2          # Deny request with ID 2
```

### Configuration Options

- `SR_COOLDOWN_SECS` — Cooldown between requests (default: 120)
- `SR_FORCE_NOW` — Play immediately on accept (default: false = queue)
- `SR_MAX_PENDING_PER_USER` — Max pending per user (default: 1)
- `SPOTIFY_DEVICE_NAME` — Preferred device name (optional)
- `SPOTIFY_DEVICE_ID` — Preferred device ID (optional)

---

## 🧩 Commands

### For Everyone

| Command | Description | Example |
|---------|-------------|---------|
| `!help` | Show command overview | `!help` |
| `!drink` | Give Finja a drink (VPet action) | `!drink` |
| `!uptime` | Show stream duration | `!uptime` |
| `!ask` / `!chat` | Ask AI a question | `!ask What's the weather?` |

### Visual Commands (60s cooldown)

| Command | Description | Values |
|---------|-------------|--------|
| `!theme` | Change overlay theme | `glass`, `dark`, `light`, `neon` |
| `!rgb` | RGB lighting mode | `off`, `ring`, `fill`, `both` |
| `!rgbspeed` | RGB animation speed | `2-30` (seconds) |
| `!ring` | Ring width | `6-10` (pixels) |
| `!opacity` | Overlay opacity | `0-100` |
| `!pulse` | Pulse animation | `on`, `off` |
| `!accent` | Accent color | `finja`, `channel`, `custom #hex` |

### Song Requests

| Command | Permission | Description |
|---------|-----------|-------------|
| `!sr <query\|link>` | Everyone | Request a song |
| `!rq` / `!requests` | Mods | List pending |
| `!accept <id>` | Mods | Accept request |
| `!deny <id>` | Mods | Deny request |

**Examples:**
```
!theme neon
!rgb ring 8
!rgbspeed 10
!opacity 85
!pulse on
!accent channel
!accent custom #ff6ad5
```

---

## 🎨 7TV Emotes Setup

To display 7TV emotes in your OBS overlay:

1. **Log in to [7tv.app](https://7tv.app)**
2. **Add emote to your active set**
3. **IMPORTANT:** Rename the emote in 7TV to match the **exact** Twitch name (case-sensitive!)
4. **Activate the set** in your 7TV profile
5. **Refresh OBS browser source** to load new emotes

**Why exact naming matters:**
The overlay fetches emotes from the ivr.fi API, which indexes 7TV emotes by their Twitch-compatible names.

**Troubleshooting:**
- Check capitalization (e.g., `Kappa` not `kappa`)
- Ensure the set is active and public
- Clear OBS cache: Right-click source → Interact → F5

---

## 🛠️ Development

### File Structure

```
Chat/
├── bot_merged.html                 # Bot control panel
├── twitch_auth.js                 # Twitch Device OAuth + rotation
├── index_merged.html               # OBS overlay
├── commands.html                   # Commands overlay
├── spotify_request_server_env.py   # Song request server
├── command_bridge.py               # VPet bridge
├── start_static_server.bat         # Windows overlay/panel launcher
├── start_server_with_env.bat       # Windows SR server launcher
├── test_command_bridge.py          # Bridge tests
├── test_spotify_request_server.py  # SR server tests
├── test_batch_files.py             # Launcher script tests
├── test_twitch_auth.js             # OAuth/rotation unit tests
├── .env.example                    # Environment template (safe to share)
├── private/                        # NEVER synced/committed -- real .env,
│                                    # personal scratch files, local cache
└── readme.md                       # This file
```

### Syncing with the public repo

Production (this folder) is the source of truth. To publish an update:

1. Make all changes here, in `Chat/`.
2. Copy the changed files into the public repo folder, **excluding**
   `private/` and `__pycache__/`.
3. Commit and push from within the public repo.

Never edit files directly in the public repo folder — always edit here first,
otherwise the two copies drift apart again (which is exactly what this
structure is meant to prevent).

### Running Tests

**Command Bridge Tests:**
```bash
pytest test_command_bridge.py -v
```

**Song Request Server Tests:**
```bash
pytest test_spotify_request_server.py -v
```

**All Tests:**
```bash
pytest -v
node --test test_twitch_auth.js
```

### Development Mode

Access the overlay with the dev panel:
```
http://127.0.0.1:8088/index_merged.html?channel=YOURCHANNEL&dev=1
```

The dev panel (⚙️ button) allows you to:
- Change themes live
- Adjust RGB settings
- Test different opacity values
- Copy OBS URL with current settings
- Save settings to localStorage

### Code Quality

All files have been validated with:
- **SonarQube** — Zero issues
- **ESLint** — JavaScript linting
- **Pylint** — Python linting
- **Pytest** — Unit test coverage

---

## 🔧 Troubleshooting

### Overlay Issues

**Problem:** Overlay is blank
- **Solution:** Ensure `?channel=yourlogin` is in the URL
- **Check:** Browser console for errors (F12)

**Problem:** No emotes showing
- **Solution:** Wait for API to load (~2-5 seconds)
- **Check:** Network tab shows successful API calls

**Problem:** 7TV emotes missing
- **Solution:** Verify exact name match in 7TV
- **Check:** Emote set is active and public

### Bot Connection Issues

**Problem:** Bot won't connect to chat
- **Solution:** Verify OAuth token is correct
- **Check:** Token has `chat:read` and `chat:edit` scopes
- **Try:** Generate new token

**Problem:** OBS control not working
- **Solution:** Check WebSocket is enabled in OBS
- **Check:** Port 4455 is correct
- **Check:** Password matches
- **Try:** Restart OBS WebSocket server

### Song Request Issues

**Problem:** "No active device" error
- **Solution:** Open Spotify on any device and play a song briefly
- **Alternative:** Set `SPOTIFY_DEVICE_NAME` or `SPOTIFY_DEVICE_ID` in `.env`

**Problem:** Search returns no results
- **Solution:** Try direct Spotify link instead
- **Check:** Your Spotify API credentials are correct

**Problem:** Server won't start
- **Solution:** Check `.env` file exists and has correct format
- **Check:** Install all dependencies: `pip install -r requirements.txt`
- **Check:** Port 8099 is not already in use

### General Issues

**Problem:** Changes not appearing
- **Solution:** Hard refresh browser (Ctrl+F5 / Cmd+Shift+R)
- **Try:** Clear browser cache
- **Check:** Correct URL is being used

**Problem:** Commands not working
- **Solution:** Check bot is connected (green status in panel)
- **Check:** User has appropriate permissions (for mod commands)
- **Try:** Check console log for errors

---

## 🔒 Security

### Best Practices

- ⚠️ **Never commit `.env` files** to version control
- ⚠️ **Never share OAuth tokens** publicly
- ⚠️ **Add `.env` to `.gitignore`**
- ⚠️ **Use Device Code OAuth so the panel can rotate tokens automatically**
- ⚠️ **Use environment variables** in production

### `.gitignore` Example

```gitignore
# Environment variables
.env
.env.local

# Python
__pycache__/
*.pyc
.pytest_cache/

# Node
node_modules/

# IDE
.vscode/
.idea/
```

### Token Safety

OAuth access/refresh tokens and Spotify secrets provide account access. Treat them like passwords:

1. **Never** include them in screenshots
2. **Never** paste them in public Discord/chat
3. **Never** commit them to GitHub
4. **Always** use `.env` files for local development
5. **Never** enter a Twitch Client Secret in the browser panel
6. **Use only the minimal Twitch scopes** (`chat:read`, `chat:edit`)

---

## 🤝 Contributing

We welcome contributions! Here's how:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes**
4. **Run tests** (`pytest -v`)
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

### Code Style

- **Python:** Follow PEP 8, use type hints
- **JavaScript:** Use modern ES6+, document with JSDoc
- **HTML/CSS:** Semantic markup, BEM naming
- **Comments:** English only, explain "why" not "what"

### Testing

All new features should include tests:
- Python: pytest with fixtures
- JavaScript: Manual testing in browser
- Integration: Test full user workflows

---

## 📄 License

**MIT** © J. Apps (JohnV2002 / Sodakiller1) — full text: repository root [`LICENSE`](../LICENSE).

Copyright / author lines in source headers must stay (standard MIT). Keeping the UI “Made with ❤️ …” credit is **appreciated**, not an extra legal requirement.

Character / brand rules and non-MIT modules: root [README — License & Usage](../README.md#license--usage).

---

## Support & Contact

- Email: [contact@jappshome.de](mailto:contact@jappshome.de)
- Website: [jappshome.de](https://jappshome.de)
- Support: [buymeacoffee.com/J.Apps](https://buymeacoffee.com/J.Apps)

---

## 💖 Acknowledgments

- **ComfyJS** — Twitch chat integration
- **Spotipy** — Spotify API wrapper
- **FastAPI** — Modern Python web framework
- **OBS Studio** — Streaming software
- **7TV, BTTV, FFZ** — Emote platforms

---

*Finja says: "Stay hydrated, Chat 💙"*
