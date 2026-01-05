# 🎶 Finja Music - All-in-One Edition
*Multi-source NowPlaying system with OBS overlays, radio scrapers & AI reactions. 💜*

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/yourusername/finja-music)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)](https://www.python.org/)

> **✨ New in v1.1.0:**
> - **Documentation:** Complete English documentation with comprehensive comments
> - **Code Quality:** All SonarQube & Snyk issues resolved across all files
> - **Security:** Path validation, SSRF protection, XSS prevention
> - **Refactoring:** Reduced cognitive complexity throughout
> - **Attribution:** Dev-mode footer in all overlays
> - **Copyright:** Updated to 2026

---

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Components](#-components)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [OBS Integration](#-obs-integration)
- [Web Interface](#-web-interface)
- [File Reference](#-file-reference)
- [Troubleshooting](#-troubleshooting)
- [Security](#-security)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Quick Start

**TL;DR - Get Running in 5 Minutes:**

1. **Configure Spotify API:**
   ```
   Edit: config/config_spotify.json
   Add your: client_id, client_secret, refresh_token
   ```

2. **Start the web server:**
   ```bash
   # Windows
   start_server.bat
   ```

3. **Open the control panel:**
   ```
   http://localhost:8022/Musik.html
   ```

4. **Add overlay to OBS:**
   - Add Browser Source
   - Select HTML from `OBSHTML/` folder
   - Done! 🎉

---

## 🤖 Components

### Control Panel (`Musik.html`)

The central control hub for all music sources.

**Features:**
- One-click activation for TruckersFM, Spotify, RTL, MDR
- Database management tools
- Helper script launchers
- Real-time status display

### OBS Overlays

Beautiful NowPlaying displays for different sources.

| Overlay | Source | Style |
|---------|--------|-------|
| `Sodakiller_NowPlaying_TFM_Bright.html` | TruckersFM | Bright glassmorphism |
| `Sodakiller_NowPlaying_Spotify.html` | Spotify | Dark with SVG logo |
| `Sodakiller_NowPlaying_RTL_Bright.html` | 89.0 RTL | Rainbow glow effect |
| `Sodakiller_NowPlaying_MDR.html` | MDR | Pink/cyan gradient |

**Common Features:**
- Glassmorphism design with blur effects
- Genre tags with special styling (Nightcore, Sped Up, etc.)
- Finja's AI reaction display
- Responsive design
- URL parameter customization
- Dev mode with attribution (`?dev=1`)

### Radio Scrapers

Python scripts that fetch NowPlaying data from radio stations.

| Script | Source | Method |
|--------|--------|--------|
| `rtl89_cdp_nowplaying.py` | 89.0 RTL | Chrome DevTools Protocol |
| `mdr_nowplaying.py` | MDR Sachsen-Anhalt | ICY/XML/HTML hybrid |

**Features:**
- Multiple fallback methods (ICY → XML → HTML)
- Non-track filtering (ads, news, jingles)
- Anti-flap logic to prevent flickering
- Atomic file writes
- Path validation for security

### Helper Scripts

| Script | Purpose |
|--------|---------|
| `rtl_repeat_counter.py` | Counts song repeats for RTL |
| `start_mdr_nowplaying.bat` | Launches MDR scraper with dependency check |
| `ArtistNotSure.html` | Web UI for resolving artist conflicts |

---

## 📦 Installation

### Prerequisites

- **Python 3.10+**
- **Google Chrome** (for RTL scraper)
- **OBS Studio**
- **Spotify Premium** (for Spotify source)

### Step 1: Clone/Download

```bash
git clone https://github.com/yourusername/finja-music.git
cd finja-music
```

### Step 2: Install Python Dependencies

```bash
pip install requests beautifulsoup4 defusedxml spotipy
```

For RTL scraper (Chrome DevTools Protocol):
```bash
pip install websocket-client
```

### Step 3: Configure Spotify

Edit `config/config_spotify.json`:
```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "refresh_token": "your_refresh_token"
}
```

> 🔴 **IMPORTANT:** Never commit this file to a public repository!

### Step 4: Start the Server

```bash
# Windows
start_server.bat

# The server runs on http://localhost:8022
```

---

## ⚙️ Configuration

### Spotify API Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your **Client ID** and **Client Secret**
4. Generate a refresh token using the OAuth flow
5. Add credentials to `config/config_spotify.json`

### Environment Variables (Optional)

The radio scrapers support environment variable overrides:

**MDR Scraper:**
```bash
MDR_XML_URL=https://...       # Custom XML feed URL
MDR_STREAM_URL=https://...    # Custom stream URL
MDR_HTML_URL=https://...      # Custom HTML page URL
MDR_POLL_S=10                 # Polling interval (seconds)
MDR_ICY_FORMAT=title-first    # ICY format (title-first|artist-first)
```

**RTL Scraper:**
```bash
RTL_CDP_PORT=9222             # Chrome DevTools port
RTL_POLL_S=5                  # Polling interval (seconds)
```

---

## 🎨 OBS Integration

### Adding an Overlay

1. In OBS: **Sources → Add → Browser**
2. Check **"Local file"**
3. Browse to `OBSHTML/Sodakiller_NowPlaying_*.html`
4. Set dimensions: **800 x 200** (adjust as needed)
5. Click **OK**

### URL Parameters

Customize overlays via URL hash parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `x` | Horizontal position (px) | `24` |
| `y` | Vertical position (px) | `24` |
| `maxw` | Maximum width (px) | `820` |
| `w` | Card width (px) | varies |
| `fs` | Font size (px) | varies |
| `label` | Custom station label | varies |
| `ms` | Poll interval (ms) | `3000` |
| `dev` | Dev mode (shows attribution) | `0` |

**Example:**
```
file:///C:/path/to/overlay.html#x=50&y=100&maxw=600&dev=1
```

### Output Files

All overlays read from the `Nowplaying/` folder:

| File | Content |
|------|---------|
| `nowplaying.txt` | Current song: "Title — Artist" |
| `now_source.txt` | Source identifier (icy, xml, html) |
| `obs_genres.txt` | Genre tags (comma separated) |
| `obs_react.txt` | Finja's AI reaction |
| `obs_repeat.txt` | Repeat count badge (RTL only) |

---

## 🎮 Web Interface

### Music Sources Section

| Button | Action |
|--------|--------|
| **Activate TruckersFM** | Starts TruckersFM listener |
| **Activate Spotify** | Starts Spotify listener |
| **Activate RTL 89.0** | Starts RTL listener (requires helper) |
| **Activate MDR** | Starts MDR listener (requires helper) |
| **Deactivate** | Stops current source |

### Database & Helper Scripts Section

| Button | Action |
|--------|--------|
| **Build DB from Spotify Exports** | Imports CSV exports to songs_kb.json |
| **Enrich Missing Songs** | Fetches missing info via Spotify API |
| **Review Artist Conflicts** | Opens ArtistNotSure.html |
| **Start RTL Browser** | Launches Chrome with CDP for RTL |
| **Start RTL Repeat Counter** | Tracks song repeats |
| **Start MDR NowPlaying** | Launches MDR scraper |

---

## 📂 File Reference

### Python Scripts

| File | Lines | Purpose |
|------|-------|---------|
| `rtl89_cdp_nowplaying.py` | ~450 | RTL scraper via Chrome DevTools |
| `rtl_repeat_counter.py` | ~250 | Song repeat counter |
| `mdr_nowplaying.py` | ~900 | MDR scraper (ICY/XML/HTML) |
| `webserver.py` | varies | Main web server |

### HTML Files

| File | Purpose |
|------|---------|
| `Musik.html` | Control panel |
| `ArtistNotSure.html` | Artist conflict resolver |
| `Sodakiller_NowPlaying_TFM_Bright.html` | TruckersFM overlay |
| `Sodakiller_NowPlaying_Spotify.html` | Spotify overlay |
| `Sodakiller_NowPlaying_RTL_Bright.html` | RTL overlay |
| `Sodakiller_NowPlaying_MDR.html` | MDR overlay |

### Batch Files

| File | Purpose |
|------|---------|
| `start_server.bat` | Starts main web server |
| `start_mdr_nowplaying.bat` | Starts MDR scraper with deps |

### Configuration

| File | Purpose |
|------|---------|
| `config/config_min.json` | Main brain configuration |
| `config/config_spotify.json` | Spotify API credentials |
| `songs_kb.json` | Song knowledge database |

---

## 🔧 Troubleshooting

### Overlay Issues

**Problem:** Overlay is blank
- **Check:** File paths are correct
- **Check:** `Nowplaying/nowplaying.txt` exists
- **Try:** Open in browser first to debug

**Problem:** Song not updating
- **Check:** Source is activated in control panel
- **Check:** Scraper is running (check console)
- **Try:** Refresh OBS browser source

### Scraper Issues

**Problem:** RTL scraper won't start
- **Check:** Chrome is installed
- **Check:** Port 9222 is free
- **Try:** Close all Chrome instances first

**Problem:** MDR scraper returns empty
- **Check:** Internet connection
- **Check:** MDR stream is online
- **Try:** Check console for error messages

### Server Issues

**Problem:** Control panel won't load
- **Check:** Server is running (`start_server.bat`)
- **Check:** Port 8022 is free
- **Try:** Check firewall settings

**Problem:** Buttons not responding
- **Check:** Browser console for errors
- **Check:** Server console for errors
- **Try:** Hard refresh (Ctrl+F5)

---

## 🔒 Security

### Implemented Measures

- ✅ **Path Validation** — Prevents path traversal attacks
- ✅ **SSRF Protection** — Port range validation for CDP
- ✅ **XSS Prevention** — DOM methods instead of innerHTML
- ✅ **defusedxml** — Safe XML parsing
- ✅ **Atomic Writes** — Prevents file corruption

### Best Practices

- ⚠️ **Never commit** `config_spotify.json` to public repos
- ⚠️ **Add to `.gitignore`:**
  ```gitignore
  config/config_spotify.json
  .env
  __pycache__/
  ```
- ⚠️ **Rotate tokens** if accidentally exposed

---

## 🤝 Contributing

We welcome contributions! Here's how:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes**
4. **Test thoroughly**
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

### Code Style

- **Python:** PEP 8, type hints, docstrings
- **JavaScript:** ES6+, JSDoc comments
- **HTML/CSS:** Semantic markup, CSS variables
- **Comments:** English only, explain "why" not "what"

---

## 📄 License

MIT © 2026 J. Apps (JohnV2002 / Sodakiller1)

**You are free to:**
- ✅ Use this code commercially
- ✅ Modify and adapt it
- ✅ Distribute and sell it
- ✅ Use it in closed-source projects

**The only requirement:**
- ⭐ **Keep the attribution visible** — Credit must remain in the UI (dev mode footer)

**Why attribution matters:**
Money comes and goes, but **reputation is gold**. This project is free for everyone, but credit keeps the open-source spirit alive.

**Links:**
- 🎮 Twitch: [twitch.tv/sodakiller1](https://twitch.tv/sodakiller1)
- 💼 Company: J. Apps
- 👤 GitHub: JohnV2002

---

## 💖 Acknowledgments

- **BeautifulSoup** — HTML parsing
- **defusedxml** — Secure XML parsing
- **Spotipy** — Spotify API wrapper
- **Chrome DevTools Protocol** — RTL scraping

---

*Built with 💖, Mate, and a pinch of chaos.*

*Finja says: "Let the music play! 🎵💜"*