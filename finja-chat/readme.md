# 💬 Finja Chat System
*OBS Chat-Overlay + Bot-Panel + Song-Requests – cute, fast, Gen‑Z approved. 💙*

> **✨ Neu in v2.2.1:**
> - Finja bleibt **IMMER blau** – egal was passiert!
> - `!uptime` zeigt dir die Stream-Dauer an.
> - VPet Bridge & Song Requests sind jetzt **abschaltbar** im Bot-Panel.
> - KI-Antworten bleiben **länger im Overlay** sichtbar.
> - Verbessertes **System Prompt** mit Streamer- & Spielkontext.

> **Kurzfassung (TL;DR):**
> 1. Starte `start_static_server.bat` → öffne `http://127.0.0.1:8088/`.
> 2. **Overlay (DEV):** `http://127.0.0.1:8088/index_merged.html?channel=DEINCHANNEL&dev=1`
> 3. **Bot-Panel:** `http://127.0.0.1:8088/bot_merged.html` → Twitch **OAuth** eintragen → **Verbinden**.
> 4. **(Optional) Song-Requests:** `spotify_request_server_env.py` starten → `!sr` im Chat benutzen.

---

## 🤖 Komponenten

### Bot-Panel (`bot_merged.html`)
-   Verbindet sich mit deinem Twitch-Chat via ComfyJS.
-   Führt **Commands** aus (`!theme`, `!rgb`, `!uptime` etc.).
-   Steuert per **OBS WebSocket v5** deine Browser-Quelle (Overlay-URL & Refresh).
-   **Neu:** Enthält Checkboxen, um die VPet Bridge & Song Requests zu deaktivieren und so Fehlermeldungen zu vermeiden.

### Overlay (`index_merged.html`)
-   Zeigt Chat-Nachrichten hübsch an (Themes, RGB, Glas-Textur, Badges, Emotes).
-   Verfügt über einen **DEV-Mode** (`?dev=1`) mit Einstellungs-Panel.
-   7TV / BTTV / FFZ Emotes werden automatisch geladen.
-   **Neu:** Nachrichten von Finja (KI-Antworten) bleiben **länger sichtbar**.

### Song-Request-Server (`spotify_request_server_env.py`)
-   Ein moderiertes `!sr`-System (Viewer stellen Anfragen, Mods genehmigen/ablehnen).
-   Benötigt Spotify API-Keys in einer `.env`-Datei.
-   Stellt eine lokale API für die Anfragen bereit.

---

## 🛠️ Setup

**1. Lokalen Webserver starten**
-   **Windows:** Führe `start_static_server.bat` aus. Dies startet einen einfachen Webserver auf `http://127.0.0.1:8088/`.
-   **Manuell:**
    ```bash
    python -m http.server 8088
    ```

**2. Overlay aufrufen (Entwickler-Ansicht)**
-   Öffne folgende URL im Browser, um das Overlay mit dem Live-Tuning-Panel (⚙️) zu sehen:
    `http://127.0.0.1:8088/index_merged.html?channel=DEINCHANNEL&dev=1`

**3. Bot-Panel öffnen & verbinden**
-   **URL:** `http://127.0.0.1:8088/bot_merged.html`
-   **Twitch OAuth Token holen:**
    1. Gehe zu [twitchtokengenerator.com](https://twitchtokengenerator.com).
    2. Logge dich mit deinem **Bot-Account** ein.
    3. Wähle die Scopes `chat:read` und `chat:edit`.
    4. Kopiere den generierten **Access Token** (nur der Teil ohne `oauth:`).
-   **Im Panel eintragen:** Channel-Name, Bot-Username und den OAuth Token.
-   Klicke auf **Verbinden**.

**4. OBS koppeln (Optional, empfohlen)**
-   Aktiviere in OBS unter `Tools → WebSocket Server` den Server (Port `4455`) und setze ein Passwort.
-   Trage im Bot-Panel unter **OBS Sync** die Daten ein (`ws://127.0.0.1:4455`, Passwort, Name der Browser-Quelle).
-   Klicke auf **OBS verbinden**.

---

## 🎵 Song-Requests (Spotify)

> **Spotify Voraussetzungen (WICHTIG!)**
> - Du benötigst einen **Spotify Account** (Premium empfohlen).
> - Du brauchst eine **Spotify Developer App**: Erstelle sie im [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), notiere **Client ID/Secret** und setze die **Redirect URI** auf z.B. `http://localhost:8080/callback`.
> - Ein **aktives Spotify-Gerät** (Desktop, Handy etc.) muss laufen. Wenn nicht, kann die API keine Songs zur Warteschlange hinzufügen.

**1. `.env`-Datei anlegen:**
```env
SPOTIPY_CLIENT_ID=deinClientID
SPOTIPY_CLIENT_SECRET=deinSecret
SPOTIPY_REDIRECT_URI=http://localhost:8080/callback
SR_COOLDOWN_SECS=120
SR_FORCE_NOW=false
```

**2. Abhängigkeiten installieren:**
```bash
pip install fastapi uvicorn spotipy python-dotenv
```

**3. Server starten:**
```bash
python spotify_request_server_env.py
```

**4. Commands im Chat:**
-   **Viewer:** `!sr <Songsuche oder Spotify-Link>`
-   **Mods:** `!rq` (Liste ansehen), `!accept <id>`, `!deny <id>`

---

## 🧩 Commands

-   **Alle:** `!help`, `!drink`, `!uptime`
-   `!theme`, `!rgb`, `!rgbspeed`, `!opacity`, `!pulse`, `!accent`
-   **Song-Requests:** `!sr`, `!rq`, `!accept`, `!deny`

---

## 😎 7TV Emotes – Schritt für Schritt

Damit deine 7TV-Emotes im OBS-Chat angezeigt werden:
1.  Gehe zu **7tv.app** und logge dich ein.
2.  Füge das gewünschte Emote zu deinem aktiven Emote-Set hinzu.
3.  **WICHTIG:** Benenne das Emote in 7TV **exakt** so, wie es in Twitch heißt (Groß-/Kleinschreibung beachten!).
4.  Aktiviere das Set in deinem 7TV-Profil.
5.  Refreshe zur Sicherheit die OBS-Browserquelle.

---

## ⚙️ Einstellungen im Bot-Panel

Unter dem ⚙️-Icon kannst du Module an- und abschalten, um Fehlermeldungen zu vermeiden, wenn du sie nicht nutzt:
-   **VPet Bridge:** Deaktivieren, wenn keine VPet-Anbindung läuft.
-   **Song-Requests:** Deaktivieren, wenn der Spotify-Server nicht läuft.

---

## 🔐 Sicherheit

-   Behandle deinen Twitch OAuth Token und deine Spotify-Secrets wie Passwörter. Lade sie **niemals** auf öffentliche Repositories hoch!
-   Füge `.env`-Dateien immer zu deiner `.gitignore`-Datei hinzu.

---

## 🧯 Troubleshooting

-   **Overlay leer?** → Ist `?channel=deinlogin` in der URL gesetzt?
-   **7TV geht nicht?** → Name exakt identisch? Set aktiv? OBS-Quelle refresht?
-   **OBS-Steuerung klappt nicht?** → WebSocket (Port 4455) aktiv & Passwort korrekt?
-   **Spotify "kein Gerät"?** → Öffne Spotify, starte kurz einen Song und versuche es erneut.

---

MIT © 2026 J. Apps (JohnV2002 / Sodakiller1) — Finja sagt: *„Stay hydrated, Chat 💖“*