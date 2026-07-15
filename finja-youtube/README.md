# 📺 Finja YouTube Shorts v1.0.0

A headless YouTube Shorts browser container that scrolls through Shorts, takes screenshots, scrapes metadata, and lets an external **Vision-LLM (the Brain)** decide whether to **like** and **forward** a video — all routed anonymously through a **VPN tunnel (Gluetun + ProtonVPN)**.

Built as a standalone Docker service for the **Finja AI Ecosystem**. 🕵️‍♀️💻

---

## ⚠️ Legal, Liability & Privacy (Please Read)

- **Purpose**: This project is intended **for testing & educational purposes only**.
- **YouTube TOS**: Automated interaction with YouTube (scrolling, liking, scraping) **may violate their Terms of Service**. Usage is **at your own risk**.
- **Disclaimer**: I only provide the code. **I am not liable** for your usage, any resulting consequences, account bans, or potential legal issues.
- **Cookie Security**: Your `cookies.json` contains **real YouTube session tokens**. Never commit it to a public repository! Use `.gitignore` to exclude it.

---

## ✨ Features

- **Headless Chrome in Mobile Mode**: Emulates a Samsung S22 Ultra browsing YouTube Shorts
- **VPN Kill Switch**: All traffic routed through Gluetun (ProtonVPN). VPN drops → no internet → no IP leaks
- **Cookie Injection**: Injects exported YouTube cookies at startup for authenticated access
- **REST API (FastAPI)**: JSON endpoints for scrolling, liking, health checks, and VPN IP verification
- **Screenshots + Metadata**: Each scroll returns a JPEG screenshot + video title + channel name
- **Non-root Container**: Both Chrome and the API run as an unprivileged `appuser`
- **Autopilot Prototype**: Included `autopilot.py` for autonomous browsing (Brain/Discord stubs)

---

## 📁 Project Structure

| File | Description |
|------|-------------|
| `youtube_api.py` | Main FastAPI application — headless browser control API |
| `autopilot.py` | Prototype: autonomous Shorts browsing loop (Brain + Discord stubs) |
| `startbrowser.py` | Local dev utility: launches Chrome with mobile emulation |
| `entrypoint.sh` | Container startup: VPN wait → Chrome → API |
| `Dockerfile` | Container image: Python + Chromium + Playwright |
| `docker-compose.yml` | Orchestrates Gluetun (VPN) + finja-youtube |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for VPN credentials |
| `cookies.json.example` | Template for YouTube cookie export (JSON format) |
| `www.youtube.com_cookies.txt.example` | Template for YouTube cookies (Netscape format) |
| `.dockerignore` | Excludes sensitive files from Docker build |

---

## 🍪 Cookie Setup (Required for YouTube Login)

The container needs your YouTube cookies to browse Shorts while logged in. Without cookies, YouTube will show limited content and may block requests.

### How to Export Cookies

1. **Install a cookie export extension** in your browser:
   - Chrome: [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg) or [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. **Log in to YouTube** in your browser
3. **Export cookies** for `youtube.com`:
   - **JSON format** → save as `cookies.json` in the project root
   - **Netscape TXT format** → save as `www.youtube.com_cookies.txt` (optional, for yt-dlp compatibility)

> ⚠️ **SECURITY WARNING**: These files contain real session tokens! **Never commit them to Git!**
> They are already listed in `.dockerignore`. Make sure your `.gitignore` excludes them too.

### Cookie File Format

**`cookies.json`** (used by the container):
```json
[
  {
    "domain": ".youtube.com",
    "name": "SID",
    "value": "YOUR_VALUE_HERE",
    "path": "/",
    "secure": false,
    "httpOnly": false,
    "sameSite": "unspecified",
    "expirationDate": 1813348178.0
  }
]
```

See `cookies.json.example` for the full template.

---

## 🐳 Setup with Docker Compose

### 1. Clone Repository

```bash
git clone https://github.com/JohnV2002/Finja-AI-Ecosystem.git
cd Finja-AI-Ecosystem/finja-youtube
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and configure your VPN and App settings:
```env
# VPN Settings
PROTON_USER=your-openvpn-username
PROTON_PASS=your-openvpn-password
VPN_COUNTRY=Netherlands

# App Settings
YOUTUBE_TARGET_URL=https://www.youtube.com/shorts
CHROME_PORT=9222
FINJA_BRAIN_URL=http://finja-ai:8051
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

> ⚠️ These are **NOT** your normal ProtonVPN login credentials!
> Find them at: https://account.protonvpn.com/account#openvpn → "OpenVPN / IKEv2 username"

### 3. Add Your Cookies

```bash
cp cookies.json.example cookies.json
```

Replace the placeholder values with your real exported YouTube cookies.

### 4. Start the Stack

```bash
docker compose up -d --build
```

This starts two containers:
- **`finja-vpn`** — Gluetun VPN gateway (ProtonVPN)
- **`finja-youtube`** — Headless Chrome + FastAPI (routed through VPN)

### 5. Verify VPN

```bash
curl http://localhost:8060/ip
```

Expected response:
```json
{"vpn_ip": "185.xx.xx.xx", "source": "api.ipify.org"}
```

The IP should be from the VPN country, **not** your real IP.

---

## 💻 API Reference

### `GET /health`
Health check — returns browser connection status.

### `GET /ip`
Returns the public IP (routed through VPN) for verification.

### `GET /status`
Returns the current page URL and title.

### `POST /scroll`
Scrolls to the next Short and returns:
```json
{
  "url": "https://www.youtube.com/shorts/abc123",
  "title": "Cute Cat Compilation",
  "channel": "@CatChannel",
  "screenshot_b64": "base64-encoded-jpeg..."
}
```

### `POST /like`
Clicks the like button on the current video:
```json
{"liked": true, "url": "https://www.youtube.com/shorts/abc123"}
```

---

## 🛡️ Security Notes

- All traffic is routed through VPN — built-in **kill switch** (no VPN → no internet)
- Container runs as **non-root** (`appuser`)
- Cookie files are excluded from Docker build via `.dockerignore`
- `no-new-privileges` security option enabled
- Resource limits: 1 CPU, 1 GB RAM

---

## 💡 Tips & Tricks (Best Practices for Account Longevity)

While automated interaction goes against YouTube's TOS, following these patterns helps the container blend in as normal human traffic. (Note: This is not a guarantee against bans, but rather a sharing of what has worked in practice).

- **Use an Aged Burner Account:** **Never** use your main personal Google account! Use a secondary/fake account that you don't care about. Ideally, use an **older account** (e.g., 5 years old) rather than a brand-new one, as older accounts are generally more trusted by YouTube's anti-bot systems.
- **Manual "Warm-Up" (Train the Algorithm):** Before handing the account over to the bot, manually watch Shorts on your PC/Phone for 1 to 3 days. Give likes to videos you actually enjoy and subscribe to channels you like (e.g., following ~100-120 channels). This trains the YouTube algorithm on what you like *before* the bot takes over, giving the bot a high-quality feed right from the start.
- **Human-Like Delays:** Notice how `autopilot.py` waits a random 10-18 seconds between swipes. Don't swipe every 2 seconds — real humans actually watch the videos for a bit.
- **Don't Spam Likes:** Humans don't like *every single* video they see. The bot should only like a realistic percentage of videos (the Brain/LLM logic should filter heavily).
- **Give the Bot "Sleep":** Nobody watches YouTube 24/7. Build logic to pause the container for several hours a day (e.g., during the night) to simulate a normal human sleep schedule.
- **VPN IP Rotation:** If YouTube starts throwing CAPTCHAs or blocking requests, change the `VPN_COUNTRY` in your `.env` or restart the Gluetun container to grab a fresh IP address.

---

## 🧰 Troubleshooting

| Problem | Solution |
|---------|----------|
| **No VPN connection** | Check `.env` credentials. Run `docker compose logs gluetun` for errors. |
| **Chrome not starting** | Check `docker compose logs finja-youtube`. Look for FINJA-130 errors. |
| **"No cookies.json found"** | Copy `cookies.json.example` to `cookies.json` and add your real cookies. |
| **YouTube blocking requests** | Your cookies may have expired. Re-export from your browser. |
| **Port 8060 not accessible** | Port is mapped on the `gluetun` service, not `finja-youtube`. Check Gluetun health. |

---

## 📜 License

MIT License © 2026 J. Apps

---

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)
