# 📸 Finja Instagram Reels v1.0.0

A headless Instagram Reels browser container that scrolls through Reels, takes screenshots, scrapes metadata, and lets an external **Vision-LLM (the Brain)** decide whether to **like** and **forward** a video — all routed anonymously through a **VPN tunnel (Gluetun + ProtonVPN)**.

Built as a standalone Docker service for the **Finja AI Ecosystem**. 🕵️‍♀️💻

---

## ⚠️ Legal, Liability & Privacy (Please Read)

- **Purpose**: This project is intended **for testing & educational purposes only**.
- **Instagram TOS**: Automated interaction with Instagram (scrolling, liking, scraping) **may violate their Terms of Service**. Usage is **at your own risk**.
- **Disclaimer**: I only provide the code. **I am not liable** for your usage, any resulting consequences, account bans, or potential legal issues.
- **Cookie Security**: Your cookie files contain **real Instagram session tokens**. Never commit them to a public repository! Use `.gitignore` to exclude them.

---

## ✨ Features

- **Headless Chrome (Desktop Mode)**: Emulates a Full HD desktop browser. *Desktop layout is required because ArrowDown navigation in the Reels feed is most stable in this mode.*
- **VPN Kill Switch**: All traffic routed through Gluetun (ProtonVPN). VPN drops → no internet → no IP leaks.
- **Cookie Injection**: Injects exported Instagram cookies at startup for authenticated access.
- **REST API (FastAPI)**: JSON endpoints for scrolling, liking, health checks, and Wakeup/Sleep cycle management.
- **Sleep/Wakeup Logic**: Prevent 24/7 presence on Reels. Container stays on `about:blank` until explicitly woken up.
- **Screenshots + Metadata**: Each scroll returns a JPEG screenshot + channel name.
- **Non-root Container**: Both Chrome and the API run as an unprivileged `appuser`.
- **Buffer-Buster**: Intelligent retry logic if Instagram gets stuck buffering the next Reel.

---

## 💡 Tips & Tricks (Best Practices for Account Longevity)

While automated interaction goes against Instagram's TOS, following these patterns helps the container blend in as normal human traffic. *(Note: This is not a guarantee against bans, but rather a sharing of what has worked in practice).*

- **Use an Aged Burner Account:** **Never** use your main personal Instagram account! Use a secondary/fake account that you don't care about. Ideally, use an **older account** (e.g., 5 years old) rather than a brand-new one, as older accounts are generally more trusted by Meta's anti-bot systems.
- **Manual "Warm-Up" (Train the Algorithm):** Before handing the account over to the bot, manually watch Reels on your PC/Phone for 1 to 3 days. Give likes to videos you actually enjoy and subscribe/follow channels you like (e.g., following ~100-120 accounts). This trains the algorithm on what you like *before* the bot takes over, giving the bot a high-quality feed right from the start.
- **Human-Like Delays:** Notice how `autopilot.py` waits a random 10-18 seconds between swipes. Don't swipe every 2 seconds — real humans actually watch the videos for a bit.
- **Don't Spam Likes:** Humans don't like *every single* video they see. The bot should only like a realistic percentage of videos (the Brain/LLM logic should filter heavily).
- **Give the Bot "Sleep":** Nobody watches Instagram 24/7. Use the `/sleep` endpoint to pause the container for several hours a day (e.g., during the night) to simulate a normal human sleep schedule.
- **VPN IP Rotation:** If Instagram starts throwing CAPTCHAs or blocking requests, change the `VPN_COUNTRY` in your `.env` or restart the Gluetun container to grab a fresh IP address.

---

## 📁 Project Structure

| File | Description |
|------|-------------|
| `instagram_api.py` | Main FastAPI application — headless browser control API |
| `autopilot.py` | Prototype: autonomous Reels browsing loop (Brain + Discord stubs) |
| `startbrowser.py` | Local dev utility: launches Chrome in desktop mode |
| `entrypoint.sh` | Container startup: VPN wait → Chrome → API |
| `Dockerfile` | Container image: Python + Chromium + Playwright |
| `docker-compose.yml` | Orchestrates Gluetun (VPN) + finja-instagram |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for VPN credentials & App Config |
| `cookies.json.example` | Template for Instagram cookie export (JSON format) |
| `www.instagram.com_cookies.txt.example` | Template for Instagram cookies (Netscape format) |
| `.dockerignore` | Excludes sensitive files from Docker build |

---

## 🍪 Cookie Setup (Required for Instagram Login)

The container needs your Instagram cookies to browse Reels while logged in. Without cookies, Instagram will block requests almost immediately.

### How to Export Cookies

1. **Install a cookie export extension** in your browser:
   - Chrome: [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg)
2. **Log in to Instagram** in your browser.
3. **Export cookies** for `instagram.com`:
   - Save as `www.instagram.com_cookies.json` (or `cookies.json`) in the project root.

> ⚠️ **SECURITY WARNING**: These files contain real session tokens! **Never commit them to Git!**
> They are already listed in `.dockerignore`. Make sure your `.gitignore` excludes them too.

See `cookies.json.example` for the full template structure.

---

## 🐳 Setup with Docker Compose

### 1. Clone Repository

```bash
git clone https://github.com/JohnV2002/Finja-AI-Ecosystem.git
cd Finja-AI-Ecosystem/finja-instagram
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
INSTAGRAM_TARGET_URL=about:blank
CHROME_PORT=9222
FINJA_BRAIN_URL=http://finja-ai:8051
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

> ⚠️ These are **NOT** your normal ProtonVPN login credentials!
> Find them at: https://account.protonvpn.com/account#openvpn → "OpenVPN / IKEv2 username"

### 3. Add Your Cookies

Replace the placeholder values in `cookies.json.example` with your real exported Instagram cookies and save it as `www.instagram.com_cookies.json` or `cookies.json`.

### 4. Start the Stack

```bash
docker compose up -d --build
```

### 5. Verify VPN

```bash
curl http://localhost:8061/ip
```

---

## 💻 API Reference

### `GET /health`
Health check — returns browser connection status.

### `GET /status`
Returns the current page URL, title, and whether the bot is awake.

### `POST /wakeup`
Navigates from `about:blank` to `instagram.com/reels/`. Instagram will now see the account as "online".

### `POST /sleep`
Navigates back to `about:blank`. Use this to simulate offline/sleep times.

### `POST /scroll`
Scrolls to the next Reel (using ArrowDown + Buffer-Buster) and returns:
```json
{
  "url": "https://www.instagram.com/reels/xyz123",
  "channel": "CoolCreator",
  "screenshot_b64": "base64-encoded-jpeg...",
  "scrolled": true
}
```

### `POST /like`
Clicks the like button on the current video in the visible viewport:
```json
{"liked": true, "url": "https://www.instagram.com/reels/xyz123", "method": "button"}
```

---

## 🛡️ Security Notes

- All traffic is routed through VPN — built-in **kill switch** (no VPN → no internet)
- Container runs as **non-root** (`appuser`)
- Cookie files are excluded from Docker build via `.dockerignore`

---

## 🧰 Troubleshooting

| Problem | Solution |
|---------|----------|
| **No VPN connection** | Check `.env` credentials. Run `docker compose logs gluetun` for errors. |
| **Chrome not starting** | Check `docker compose logs finja-instagram`. Look for FINJA-130 errors. |
| **"No cookie file found"** | Copy `cookies.json.example` to `cookies.json` and add your real cookies. |
| **Instagram blocks requests / asks for login** | Your cookies may have expired. Re-export from your browser and restart. |
| **Port 8061 not accessible** | Port is mapped on the `gluetun` service, not `finja-instagram`. Check Gluetun health. |

---

## 📜 License

MIT License © 2026 J. Apps

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)