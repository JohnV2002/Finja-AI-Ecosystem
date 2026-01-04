# 💬 Finja Chat System
*OBS Chat Overlay + Bot Panel + Song Requests — cute, fast, Gen-Z approved. 💙*

[![Version](https://img.shields.io/badge/version-2.2.1-blue.svg)](https://github.com/yourusername/finja-chat)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)](https://www.python.org/)

> **✨ New in v2.2.1:**
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
   - Get your OAuth token from [twitchtokengenerator.com](https://twitchtokengenerator.com)
   - Enter channel name, bot username, and OAuth token
   - Click **Connect**

4. **(Optional) Start song requests:**
   ```bash
   python spotify_request_server_env.py
   ```

---

## 🤖 Components

### Bot Panel (`bot_merged_fixed.html`)

The central control hub for your Twitch bot integration.

**Features:**
- Connects to Twitch chat via ComfyJS
- Executes chat commands (`!theme`, `!rgb`, `!uptime`, etc.)
- Controls OBS via WebSocket v5 (overlay URL updates & refresh)
- Integrates with OpenWebUI for AI chat responses
- Modular toggles for VPet Bridge and Song Requests
- Real-time log display

**Technology Stack:**
- ComfyJS for Twitch chat
- OBS WebSocket v5 for OBS control
- BroadcastChannel API for overlay communication
- LocalStorage for settings persistence

### Overlay (`index_merged_fixed.html`)

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

### Song Request Server (`spotify_request_server_env_fixed.py`)

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

### Twitch OAuth Token

1. Visit [twitchtokengenerator.com](https://twitchtokengenerator.com)
2. Log in with your **bot account**
3. Select scopes: `chat:read` and `chat:edit`
4. Copy the generated access token
5. Paste into bot panel (format: `oauth:abc123...`)

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

Create a `.env` file in the project root:

```env
# Spotify Credentials
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://localhost:8080/callback

# Song Request Settings
SR_COOLDOWN_SECS=120
SR_FORCE_NOW=false
SR_MAX_PENDING_PER_USER=1

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
finja-chat/
├── bot_merged_fixed.html              # Bot control panel
├── index_merged_fixed.html            # OBS overlay
├── spotify_request_server_env_fixed.py # Song request server
├── command_bridge.py                   # VPet bridge
├── start_static_server.bat             # Windows server launcher
├── start_server_with_env.bat           # Windows SR server launcher
├── test_command_bridge.py              # Bridge tests
├── test_spotify_request_server.py      # SR server tests
├── .env.example                        # Environment template
└── README.md                           # This file
```

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
- ⚠️ **Rotate tokens regularly**
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

Your OAuth token and Spotify secrets provide **full access** to your accounts. Treat them like passwords:

1. **Never** include them in screenshots
2. **Never** paste them in public Discord/chat
3. **Never** commit them to GitHub
4. **Always** use `.env` files for local development
5. **Always** use secrets management in production

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

MIT © 2026 J. Apps (JohnV2002 / Sodakiller1)

**You are free to:**
- ✅ Use this code commercially
- ✅ Modify and adapt it
- ✅ Distribute and sell it
- ✅ Use it in closed-source projects

**The only requirement:**
- ⭐ **Keep the attribution visible** — The "Made with ❤️ by Sodakiller1" credit must remain in the UI

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

- **ComfyJS** — Twitch chat integration
- **Spotipy** — Spotify API wrapper
- **FastAPI** — Modern Python web framework
- **OBS Studio** — Streaming software
- **7TV, BTTV, FFZ** — Emote platforms

---

*Finja says: "Stay hydrated, Chat 💙"*