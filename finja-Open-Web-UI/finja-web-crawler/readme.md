# 🌐 Finja Web Crawler v2.0.0

A streamlined, fast, and secure web crawler that sends search queries anonymously via **DuckDuckGo (DDGS)** over **Tor** —  
and automatically falls back to **Google HTML scraping** if too few results are found.  
If absolutely nothing is found, it delivers a **Wikipedia fallback (Tabby cats)** as an emergency response.  
Perfect as an **external web search service for Open WebUI**. 🕵️‍♀️💻

---

## ⚠️ Legal, Liability & Privacy (Please Read)

- **Purpose**: This project is intended **for testing & educational purposes only**.
- **Google Scraping**: Automatically scraping Google **violates their Terms of Service (TOS)**. Usage is **at your own risk** and may lead to **IP bans, Captchas, or legal actions**.
- **Disclaimer**: I only provide the code. **I am not liable** for your usage, any resulting consequences, data loss, or potential GDPR/privacy violations.
- **Data Storage (Crawler)**: The crawler itself does **not permanently store** any data, apart from temporary logs during execution.
- **Data Storage (Open WebUI)**: If you integrate the crawler into **Open WebUI**, Open WebUI will store the search results in its internal vector database. If **"Adaptive Memory v4"** is active, extracted information may additionally be ingested into the memory server.
    - → **If unsure:** Disable the "Adaptive Memory" plugin in Open WebUI.

---

## 🆕 Updates & Changelog (v2.0.0)

* **🐳 Custom Tor Sidecar (`Dockerfile.tor`):** Replaced the third-party `dperson/torproxy` image with a self-built, minimal Alpine + Tor container. Full control over the Tor configuration via a local `torrc` file, runs as unprivileged `tor` user, and weighs only ~15 MB.
* **⚙️ Custom `torrc` Configuration:** New `torrc` config file included in the repository. Configure SOCKS port, logging, data directory, and client-only mode directly — no more black-box third-party images.
* **🔒 Security Hardened:** Both the crawler container (`appuser`) and the Tor sidecar (`tor` user) now run as non-root for defense in depth.
* **📦 Updated `docker-compose.yml`:** The `tor` service now builds from `Dockerfile.tor` instead of pulling an external image, keeping the entire stack self-contained and reproducible.

---

## ✨ Features

- **Hybrid Search**: DuckDuckGo (`ddgs`) via **Tor** first → if too few hits: **Google Fallback**
- **Wikipedia Fallback**: If nothing is found at all → `https://en.wikipedia.org/wiki/Tabby_cat`
- **Custom Tor Proxy**: Self-built Alpine Tor SOCKS5 sidecar — no third-party images required
- **API Server (FastAPI)**: JSON Endpoint `POST /search`
- **Randomized User-Agents** per request (makes blocking harder)
- **Access Protection** via **Bearer Token** (from `.env`, mandatory for Open WebUI)
- **Parsing** via BeautifulSoup (Title, Link, Snippet)
- **Configurable Delays** on Google fallback (minimizes ban risk)
- **Docker & Compose Ready** (no local Python setup necessary)

---

## 📁 Project Structure

| File | Description |
|------|-------------|
| `.env` | Contains your secret `BEARER_TOKEN` |
| `docker-compose.yml` | Orchestrates the crawler + Tor sidecar |
| `Dockerfile` | Multi-stage build for the crawler API (Python/FastAPI) |
| `Dockerfile.tor` | **NEW** — Custom Alpine-based Tor SOCKS5 proxy sidecar |
| `torrc` | **NEW** — Tor daemon configuration (see section below) |
| `requirements.txt` | Python dependencies |
| `main.py` | The active hybrid crawler (Tor + DDGS + Google Fallback) |
| `generate_token.py` | Token generator (optional; only used to generate tokens) |
| `test_web_crawler.py` | Pytest test suite |

---

## 🐳 Setup with Docker (Recommended, **no** local Python needed)

### 1. Clone Repository

```bash
git clone https://github.com/JohnV2002/Finja-AI-Ecosystem/finja-Open-Web-UI/finja-web-crawler.git
cd finja-web-crawler
```

### 2. Create `.env` (Enable Access Protection)

Create/open the `.env` file in the project folder and set a secret token:
```env
BEARER_TOKEN=my-secure-super-token
```
⚠️ **Mandatory for Open WebUI:** Without a valid token, the external crawler cannot be saved in Open WebUI.
⚠️ **SEE BELOW: How to create secure tokens**

### 3. Start (Docker Compose)
```bash
docker compose up --build -d
```
This builds **both** containers:
- **`tor`** — the custom Tor SOCKS5 proxy from `Dockerfile.tor`
- **`search-proxy`** — the FastAPI crawler from `Dockerfile`

The API is now available at `http://127.0.0.1:8080` (depending on the port mapping in `docker-compose.yml`).
**Note:** On the first start, it may take a moment for the Tor service to fully initialize and establish a circuit.

---

## ⚙️ The `torrc` Configuration File

The `torrc` file controls how the Tor daemon behaves inside the sidecar container. It is copied into the image at build time (`COPY torrc /etc/tor/torrc`).

### Default Configuration

```ini
SocksPort 0.0.0.0:9050    # Listen on all interfaces (required for Docker networking)
Log notice stdout          # Log notices to stdout (visible via docker logs)
DataDirectory /var/lib/tor # Where Tor stores its state (consensus, keys, etc.)
ClientOnly 1               # Never act as a relay or exit node — client mode only
```

### What each option does

| Option | Description |
|--------|-------------|
| `SocksPort 0.0.0.0:9050` | Opens a SOCKS5 proxy on port 9050. The `0.0.0.0` binding is necessary so the crawler container can reach the Tor proxy via Docker's internal network. |
| `Log notice stdout` | Sends Tor log messages (notice level) to stdout. This makes logs visible via `docker logs tor` for easy debugging. |
| `DataDirectory /var/lib/tor` | The directory where Tor stores its cached network consensus, keys, and circuit state. This is the default Alpine location. |
| `ClientOnly 1` | **Important!** Ensures the Tor instance only acts as a client and will **never** become a relay or exit node. This is a critical safety measure. |

### Customizing `torrc`

You can add additional options to `torrc` before building the container. Some useful ones:

```ini
# Use specific exit nodes (e.g., only German exits)
ExitNodes {de}
StrictNodes 1

# Increase circuit timeout for slow networks
CircuitBuildTimeout 30

# Disable fetching directory info you don't need
FetchUselessDescriptors 0
```

> ⚠️ After editing `torrc`, you **must rebuild** the container for changes to take effect:
> ```bash
> docker compose up --build -d
> ```

---

## 🐳 The `Dockerfile.tor` (Tor Sidecar)

The `Dockerfile.tor` builds a minimal Tor SOCKS5 proxy container. It replaces the previously used third-party `dperson/torproxy` image with a self-built alternative.

### Why a custom Tor image?
- **Full control** over the Tor version and configuration
- **No third-party dependency** — you know exactly what's running
- **Minimal size** (~15 MB) — just Alpine + Tor, nothing else
- **Security hardened** — runs as the unprivileged `tor` user

### How it works
1. Starts from `alpine:3.22` (tiny base image)
2. Installs the `tor` package via `apk`
3. Copies your local `torrc` into the image
4. Switches to the `tor` user (non-root)
5. Exposes port `9050` (SOCKS5 proxy)
6. Runs `tor -f /etc/tor/torrc` on startup

The crawler container (`search-proxy`) connects to this sidecar via `socks5h://tor:9050` using Docker's internal DNS resolution.

---

### 🔐 Creating a Secure Token (Optional, but recommended)
Your token should be 64 characters long and contain only alphanumeric characters (A–Z, a–z) to avoid issues in the `.env` file.

**Method 1 – Using Python (Simple & Platform Independent)**

The repository already includes the file `generate_token.py`. Simply run it in the project folder:
```bash
python generate_token.py
```
Copy the token output in the console and paste it into your `.env` file.

**Method 2 – Shell (Linux / macOS / WSL)**
```bash
tr -dc 'A-Za-z' < /dev/urandom | head -c 64 ; echo
```
Paste the generated token into the `.env` file as well.

---

### 💻 Using the API

**Request**
```http
POST /search
Host: http://127.0.0.1:8080
Authorization: Bearer <YOUR_TOKEN>
Content-Type: application/json

{
  "query": "Tabby Cat",
  "count": 5
}
```

**Response (Example)**
```json
[
  {
    "link": "https://en.wikipedia.org/wiki/Tabby_cat",
    "title": "Tabby cat - Wikipedia",
    "snippet": "A tabby is any domestic cat with a distinctive coat that features..."
  }
]
```

---

## 🤖 Integrating into Open WebUI

📚 Official Docs: `https://docs.openwebui.com/tutorials/web-search/external`

1.  Go to **Open WebUI → Settings → Web Search**.
2.  Enable **"External Web Search"**.
3.  Enter the details:
    - **URL:** `http://127.0.0.1:8080/search` (or the IP of your Docker host)
    - **Bearer Token:** Your secret token from the `.env` file.
4.  Click **Save**. Done! 💖

---

## 🛡️ Security & Rate-Limit Tips
- Always set a strong **token** and do not expose the service unprotected to the public internet.
- For public operations: Use a **Reverse Proxy** with additional authentication and rate-limiting.
- The Google fallback is a **risk**. Captchas or IP bans are possible.
- **User-Agent rotation** is active, but does not reduce legal risks.
- Both containers run as **non-root users** (`appuser` / `tor`) for defense in depth.

---

## 🧰 Troubleshooting

| Problem | Solution |
|---------|----------|
| **401 Unauthorized** | The `Authorization: Bearer <YOUR_TOKEN>` header is missing or incorrect. |
| **Slow / No Results** | Give Tor some time after startup to build circuits. DDG/Google can still throttle or block you. |
| **Port Conflicts** | Check the port mapping in `docker-compose.yml`. The app listens on port `80` inside the container, Tor on `9050`. |
| **Tor not connecting** | Run `docker logs tor` to check for errors in the torrc config. |
| **Changes to torrc not applied** | You must rebuild: `docker compose up --build -d` |

---

## 📜 License
MIT License © 2026 J. Apps

---

## 🆘 Support & Contact

If you have any questions or problems, you can reach me here:

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)