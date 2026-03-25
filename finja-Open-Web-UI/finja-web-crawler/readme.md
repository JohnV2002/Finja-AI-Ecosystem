# 🌐 Web Crawler API

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

## ✨ Features

- **Hybrid Search**: DuckDuckGo (`ddgs`) via **Tor** first → if too few hits: **Google Fallback**
- **Wikipedia Fallback**: If nothing is found at all → `https://en.wikipedia.org/wiki/Tabby_cat`
- **API Server (FastAPI)**: JSON Endpoint `POST /search`
- **Randomized User-Agents** per request (makes blocking harder)
- **Access Protection** via **Bearer Token** (from `.env`, mandatory for Open WebUI)
- **Parsing** via BeautifulSoup (Title, Link, Snippet)
- **Configurable Delays** on Google fallback (minimizes ban risk)
- **Docker & Compose Ready** (no local Python setup necessary)

---

## 📁 Project Structure

- `.env` → contains your secret `BEARER_TOKEN`
- `docker-compose.yml`
- `Dockerfile`
- `requirements.txt`
- `main.py` → the active hybrid crawler (Tor + DDGS + Google Fallback)
- `generate_token.py` → Token generator (optional; only used to generate tokens)

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
The API is now available at `http://127.0.0.1:8080` (depending on the port mapping in `docker-compose.yml`).
**Note:** On the first start, it may take a moment for the Tor service to fully initialize.

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

---

## 🧰 Troubleshooting

- **401 Unauthorized**: The `Authorization: Bearer <YOUR_TOKEN>` header is missing or incorrect.
- **Slow / No Results**: Give Tor some time after startup. DDG/Google can still throttle or block you.
- **Port Conflicts**: Check the port mapping in `docker-compose.yml`. The app itself listens on port `80` inside the container.

---

## 📜 License
MIT License © 2026 J. Apps

---

## 🆘 Support & Contact

If you have any questions or problems, you can reach me here:

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)