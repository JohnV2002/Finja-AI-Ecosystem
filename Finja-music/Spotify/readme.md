# 🎧 Spotify – Vollständiges Musikmodul

Dieses Modul sorgt dafür, dass dein System erkennt, welcher Song gerade auf Spotify läuft, ihn in Genres einordnet, Reaktionen generiert und sich merkt, was es davon hält. 🧠💖

> **Wichtig:** Das Modul besteht aus zwei Teilen, die zusammenarbeiten. Ohne beide Teile "hört" das System keine Musik!

---

## 📂 Verzeichnisstruktur

So ist der `Spotify/`-Ordner aufgebaut:

```plaintext
Spotify/
├─ Spotify - Get Content/
│   ├─ spotify_nowplaying.py
│   ├─ spotify_auth_helper.py
│   ├─ spotify_config.json
│   ├─ start_spotify_nowplaying_windows.bat
│   ├─ NowPlaying_Spotify.html
│   ├─ nowplaying_spotify.txt
│   └─ outputs/
│       ├─ obs_genres.txt
│       └─ obs_react.txt
│
└─ MUSIK/
    ├─ Memory/
    ├─ SongsDB/
    ├─ exports/
    ├─ cache/
    ├─ missingsongs/
    ├─ config_min.json
    ├─ finja_min_writer.py
    ├─ ... (weitere Brain-Dateien)
    └─ run_finja.bat
```

---

## 🛰️ Teil 1: Get Content – Songs abrufen

**Ziel:** Holt den aktuell auf Spotify gespielten Song und schreibt ihn in die Datei `nowplaying_spotify.txt`.

### Funktionsweise

-   Nutzt die offizielle **Spotify Web API**, um den Wiedergabestatus deines Accounts abzufragen.
-   Liest den aktuellen Titel und Interpreten deines aktiven Spotify-Players (egal ob App, Browser oder Handy).
-   Schreibt das Ergebnis im Format `Titel — Artist` in die `nowplaying_spotify.txt`.
-   **Voraussetzung:** Es muss ein Player aktiv sein (Musik läuft oder ist pausiert) und die Authentifizierung muss erfolgreich sein.

### Setup & Authentifizierung

1.  **Spotify-App erstellen:** Gehe zum [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) und erstelle eine neue App.
2.  **Redirect-URI eintragen:** Trage in den Einstellungen deiner neuen App unter "Redirect URIs" exakt `http://127.0.0.1:8080/callback` ein.
3.  **Konfiguration anpassen:** Öffne die `spotify_config.json` und trage deine `Client ID` und `Client Secret` ein, die du im Dashboard findest.

    ```json
    {
      "client_id": "DEINE_CLIENT_ID",
      "client_secret": "DEIN_CLIENT_SECRET",
      "redirect_uri": "[http://127.0.0.1:8080/callback](http://127.0.0.1:8080/callback)",
      "scope": "user-read-playback-state user-read-currently-playing"
    }
    ```
4.  **Authentifizieren:** Starte die `start_spotify_nowplaying_windows.bat`. Ein Browserfenster öffnet sich, in dem du den Zugriff erlauben musst. Danach wird automatisch ein Token für zukünftige Anfragen gespeichert.

---

## 🧠 Teil 2: MUSIK – Songs analysieren

**Ziel:** Nimmt den Songtitel aus der `nowplaying_spotify.txt` und generiert daraus Genre-Tags, dynamische Reaktionen und Langzeit-Erinnerungen.

### Setup-Varianten

Du hast zwei Möglichkeiten, das Musik-Brain für Spotify einzurichten.

#### 🅑 Spotify nutzt das zentrale TruckersFM-Brain (Empfohlen 💖)

Dies ist die beste Methode, um ein konsistentes Musikerlebnis über alle Quellen hinweg zu gewährleisten.

1.  **Voraussetzung:** Richte zuerst das Musik-Brain im `TruckersFM/MUSIK/`-Ordner vollständig und sauber ein.
2.  **Konfiguration kopieren:** Kopiere die `config_min.json` aus `TruckersFM/MUSIK/` in den `Spotify/MUSIK/`-Ordner.
3.  **Pfade anpassen:** Öffne die neue `config_min.json` und passe **nur die Pfade** so an, dass sie auf das zentrale Brain und die richtigen Spotify-Dateien verweisen:

    ```json
    {
      "input_path": "../Spotify - Get Content/nowplaying_spotify.txt",
      "fixed_outputs": "../Spotify - Get Content/outputs",
    
      "songs_kb_path": "../../TruckersFM/MUSIK/SongsDB/songs_kb.json",
      "kb_index_cache_path": "../../TruckersFM/MUSIK/cache/kb_index.pkl",
    
      "reactions": {
        "enabled": true,
        "path": "../../TruckersFM/MUSIK/Memory/reactions.json",
        "context": {
          "enabled": true,
          "path": "../../TruckersFM/MUSIK/Memory/contexts.json"
        }
      },
    
      "memory": {
        "enabled": true,
        "path": "../../TruckersFM/MUSIK/Memory/memory.json"
      }
    }
    ```
> **Vorteile:** Spotify nutzt dieselbe Song-Datenbank, dieselben Reaktionen und dasselbe Gedächtnis wie TruckersFM. Neue Erinnerungen wirken sich sofort auf alle Musikquellen aus.

#### 🅐 Eigenständiger Spotify-Betrieb (Nicht empfohlen)
Es ist möglich, ein komplett separates Brain nur für Spotify zu betreiben, aber dies führt zu inkonsistenten Daten und mehr Wartungsaufwand. Eine Anleitung dafür findest du in der detaillierteren Dokumentation.

---

## ⚡ Starten & OBS-Integration

1.  **Teil 1 starten:** Führe `start_spotify_nowplaying_windows.bat` aus.
2.  **Teil 2 starten:** Führe `run_finja.bat` aus dem `Spotify/MUSIK`-Ordner aus.
3.  **OBS einrichten:**
    -   Füge eine **"Browser"**-Quelle hinzu und verweise als **"Lokale Datei"** auf `Spotify - Get Content/NowPlaying_Spotify.html`.
    -   Füge zwei **"Text (GDI+)"**-Quellen hinzu und lasse sie aus den folgenden Dateien lesen:
        -   `Spotify - Get Content/outputs/obs_genres.txt`
        -   `Spotify - Get Content/outputs/obs_react.txt`

---

## 📌 Wichtige Hinweise

-   Die `.finja_min_writer.lock`-Datei schützt das Brain vor einem versehentlichen Doppelstart.
-   Beende das Brain-Skript immer mit `Strg+C`, damit die `.lock`-Datei sauber entfernt wird.
-   Ohne eine `songs_kb.json` können keine Genres ermittelt werden.
-   Ohne `reactions.json` und `contexts.json` sind Finjas Reaktionen nur generisch und nicht auf deinen Geschmack abgestimmt.

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos ✨*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)