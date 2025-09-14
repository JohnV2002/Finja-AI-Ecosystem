# 🌐 Web Crawler API

Ein schlanker, schneller und sicherer Web-Crawler, der Suchanfragen anonym über **DuckDuckGo (DDGS)** via **Tor** stellt —  
und bei zu wenigen Treffern automatisch auf **Google-HTML-Scraping** zurückfällt.  
Wenn gar nichts gefunden wird, liefert er als Notfall ein **Wikipedia-Fallback (Tabby-Katzen)**.  
Perfekt als **externer Web-Suchdienst für Open WebUI**. 🕵️‍♀️💻

---

## ⚠️ Recht, Haftung & Datenschutz (bitte lesen)

- **Zweck**: Dieses Projekt ist **nur für Tests & Lernzwecke** gedacht.
- **Google-Scraping**: Das automatische Abfragen von Google **verstößt gegen deren Nutzungsbedingungen (TOS)**. Die Nutzung erfolgt **auf eigene Gefahr** und kann zu **IP-Sperren, Captchas oder rechtlichen Schritten** führen.
- **Haftungsausschluss**: Ich stelle nur den Code bereit. **Ich hafte nicht** für deine Nutzung, daraus folgende Konsequenzen, Datenverluste oder mögliche DSGVO-Verstöße.
- **Datenspeicherung (Crawler)**: Der Crawler selbst speichert **keine Daten dauerhaft**, abgesehen von temporären Logs während der Ausführung.
- **Datenspeicherung (Open WebUI)**: Wenn du den Crawler in **Open WebUI** einbindest, speichert Open WebUI die Suchergebnisse in seiner internen Vektor-Datenbank. Bei aktivem **"Adaptive Memory v4"** können extrahierte Informationen zusätzlich im Memory-Server landen.
    - → **Bei Unsicherheit:** Deaktiviere das "Adaptive Memory" Plugin in Open WebUI.

---

## ✨ Features

- **Hybrid-Suche**: zuerst DuckDuckGo (`ddgs`) via **Tor** → wenn zu wenige Treffer: **Google-Fallback** - **Wikipedia-Fallback**: Wenn wirklich nichts gefunden wird → `https://de.wikipedia.org/wiki/Tabby`
- **API-Server (FastAPI)**: JSON-Endpoint `POST /search`
- **Zufällige User-Agents** pro Request (erschwert Blocking)
- **Zugriffsschutz** via **Bearer-Token** (aus `.env`, verpflichtend für Open WebUI)
- **Parsing** via BeautifulSoup (Titel, Link, Snippet)
- **Konfigurierbare Pausen** beim Google-Fallback (minimiert Ban-Risiko)
- **Bereit für Docker & Compose** (kein lokales Python-Setup nötig)

---

## 📁 Projektstruktur

- `.env` → enthält deinen geheimen `BEARER_TOKEN`
- `docker-compose.yml`
- `Dockerfile`
- `requirements.txt`
- `main.py` → aktiver Hybrid-Crawler (Tor + DDGS + Google-Fallback)
- `generate_token.py` → Token-Generator (optional; nur zur Token-Erzeugung)

---

## 🐳 Setup mit Docker (empfohlen, **kein** lokales Python nötig)

### 1. Repository klonen

```bash
git clone [https://github.com/JohnV2002/Finja-AI-Ecosystem/finja-Open-Web-UI/finja-web-crawler.git](https://github.com/JohnV2002/Finja-AI-Ecosystem/finja-Open-Web-UI/finja-web-crawler.git)
cd finja-web-crawler
```

### 2. `.env` anlegen (Zugriffsschutz aktivieren)

Erstelle/öffne die Datei `.env` im Projektordner und setze ein geheimes Token:
```env
BEARER_TOKEN=mein-sicheres-super-token
```
⚠️ **Pflicht für Open WebUI:** Ohne gültigen Token lässt sich der externe Crawler in Open WebUI nicht speichern.
⚠️ **SIEHE WEITERUNTEN: Sichere Token erstellen für wie das geht**

### 3. Starten (Docker Compose)
```bash
docker compose up --build -d
```
Die API ist nun unter `http://127.0.0.1:8080` erreichbar (je nach Port-Mapping in `docker-compose.yml`).
**Hinweis:** Beim ersten Start kann es etwas dauern, bis der Tor-Dienst vollständig initialisiert ist.

---

### 🔐 Sicheren Token erstellen (optional, aber empfohlen)
Dein Token sollte 64 Zeichen lang sein und nur Buchstaben enthalten (A–Z, a–z), um Probleme in der `.env`-Datei zu vermeiden.

**Methode 1 – mit Python (einfach & plattformunabhängig)**

Im Repository liegt bereits die Datei `generate_token.py`. Führe sie einfach im Projektordner aus:
```bash
python generate_token.py
```
Kopiere den Token, der in der Konsole ausgegeben wird, und füge ihn in deine `.env`-Datei ein.

**Methode 2 – Shell (Linux / macOS / WSL)**
```bash
tr -dc 'A-Za-z' < /dev/urandom | head -c 64 ; echo
```
Den ausgegebenen Token ebenfalls in die `.env`-Datei eintragen.

---

### 💻 API nutzen

**Anfrage**
```http
POST /search
Host: [http://127.0.0.1:8080](http://127.0.0.1:8080)
Authorization: Bearer <DEIN_TOKEN>
Content-Type: application/json

{
  "query": "Tabby Katze",
  "count": 5
}
```

**Antwort (Beispiel)**
```json
[
  {
    "link": "[https://de.wikipedia.org/wiki/Tabby](https://de.wikipedia.org/wiki/Tabby)",
    "title": "Tabby – Wikipedia",
    "snippet": "Tabby bezeichnet die typischen Fellzeichnungen von Katzen..."
  }
]
```

---

## 🤖 In Open WebUI einbinden

📚 Offizielle Doku: `https://docs.openwebui.com/tutorials/web-search/external`

1.  Gehe zu **Open WebUI → Settings → Web Search**.
2.  Aktiviere **"External Web Search"**.
3.  Trage die Daten ein:
    - **URL:** `http://127.0.0.1:8080/search` (oder die IP deines Docker-Hosts)
    - **Bearer Token:** Dein geheimer Token aus der `.env`-Datei.
4.  Klicke auf **Save**. Fertig!

---

## 🛡️ Sicherheit & Rate-Limit Tipps
- Setze immer ein starkes **Token** und stelle den Dienst nicht ungeschützt ins öffentliche Internet.
- Bei öffentlichem Betrieb: Nutze einen **Reverse Proxy** mit zusätzlicher Authentifizierung und Rate-Limiting.
- Der Google-Fallback ist ein **Risiko**. Captchas oder IP-Sperren sind möglich.
- Die **User-Agent-Rotation** ist aktiv, reduziert aber keine rechtlichen Risiken.

---

## 🧰 Troubleshooting

- **401 Unauthorized**: Der `Authorization: Bearer <DEIN_TOKEN>` Header fehlt oder ist falsch.
- **Langsam / keine Ergebnisse**: Gib Tor nach dem Start etwas Zeit. DDG/Google können dich trotzdem drosseln oder blockieren.
- **Port-Konflikte**: Prüfe das Port-Mapping in der `docker-compose.yml`. Die App selbst lauscht im Container auf Port `80`.

---

## 📜 Lizenz
MIT License © 2025 J. Apps

---

## 🆘 Support & Kontakt

Bei Fragen oder Problemen erreichst du uns hier:

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)