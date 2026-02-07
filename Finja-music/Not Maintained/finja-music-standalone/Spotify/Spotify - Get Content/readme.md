# 🎵 Spotify – GET CONTENT
*(Teil 1 des Finja-Music Systems)*

Holt den aktuell laufenden Track direkt von der **Spotify Web API** und schreibt ihn in `nowplaying_spotify.txt`.
> Diese Datei wird dann vom Musikgehirn (Teil 2) gelesen & analysiert.

---

## ⚙️ Was dieser Teil macht

-   Nutzt die **offizielle Spotify API** für eine zuverlässige Abfrage.
-   Fragt alle paar Sekunden (einstellbar in der `spotify_config.json`) den aktuell laufenden Track ab.
-   Schreibt Titel & Artist atomar in die `nowplaying_spotify.txt`-Datei.
-   Erkennt neue Songs und triggert damit das Musikgehirn bei jeder Änderung.

> ⚡ **Voraussetzung:** Du brauchst einen Spotify-Account, auf dem gerade aktiv Musik wiedergegeben wird (ein Song muss laufen oder pausiert sein, sonst gibt die API nichts zurück!).

---

## 📂 Dateien im Überblick

| Datei | Zweck |
| :--- | :--- |
| `spotify_auth_helper.py` | Einmaliges Tool, um deinen `refresh_token` zu erzeugen. |
| `spotify_config.json` | Konfiguration (Client-ID, Secret, Refresh-Token, Output). |
| `spotify_nowplaying.py` | Hauptskript, das den aktuellen Track abruft. |
| `start_spotify_nowplaying_windows.bat` | Startet `spotify_nowplaying.py` unter Windows. |
| `nowplaying_spotify.txt` | Ausgabedatei: enthält den zuletzt erkannten Track. |
| `NowPlaying_Spotify.html` | Die HTML-Datei für das OBS-Overlay für Spotify. |

---

## 🚀 Quick Start

### 1. Spotify API-App erstellen
-   Gehe zum **[Spotify Developer Dashboard](https://developer.spotify.com/dashboard)**.
-   Erstelle eine neue App und notiere dir `Client ID` und `Client Secret`.
-   Füge in den App-Einstellungen unter "Redirect URIs" den Wert `http://localhost:8888/callback` hinzu.

### 2. Refresh Token generieren
-   Öffne ein Terminal (CMD oder PowerShell) und setze deine Zugangsdaten als temporäre Umgebungsvariablen:
    ```bash
    set SPOTIFY_CLIENT_ID=deine_id
    set SPOTIFY_CLIENT_SECRET=dein_secret
    ```
-   Führe dann das Hilfsskript aus:
    ```bash
    python spotify_auth_helper.py
    ```
-   Ein Browserfenster öffnet sich. Logge dich ein und akzeptiere die Berechtigungen.
-   Danach erscheint in deinem Terminal der `REFRESH_TOKEN`. Kopiere ihn.

### 3. Config einrichten
-   Öffne die Datei `spotify_config.json` mit einem Texteditor.
-   Trage deine `Client ID`, dein `Client Secret` und den eben generierten `Refresh Token` ein:
    ```json
    {
      "output": "nowplaying_spotify.txt",
      "interval": 5,
      "spotify": {
        "client_id": "DEINE_ID",
        "client_secret": "DEIN_SECRET",
        "refresh_token": "DEIN_REFRESH_TOKEN"
      }
    }
    ```

### 4. Starten
-   Führe die `start_spotify_nowplaying_windows.bat` aus.
-   Das Skript läuft nun im Hintergrund und aktualisiert die `nowplaying_spotify.txt`. **Stelle sicher, dass auf deinem Spotify-Account gerade ein Song läuft!** 🎧

---

## 📺 OBS Overlay hinzufügen

1.  Füge in OBS eine neue **"Browser"**-Quelle hinzu.
2.  Aktiviere die Option **"Lokale Datei"** und wähle die `NowPlaying_Spotify.html` aus diesem Ordner.
3.  Passe optional das Aussehen mit Hash-Parametern im Dateipfad an:
    ```text
    .../NowPlaying_Spotify.html#x=24&y=24&maxw=800
    ```

> ⚡ **Das Overlay zeigt an:**
> -   Den Songtitel aus `nowplaying_spotify.txt`.
> -   Die Genres aus `outputs/obs_genres.txt` (vom Musikgehirn).
> -   Die Reaktion aus `outputs/obs_react.txt` (vom Musikgehirn).

---

## ⚠️ Wichtige Hinweise

-   Ohne einen laufenden Song auf einem deiner Spotify-Geräte kann die API keine Daten abrufen.
-   Behandle deine `Client ID`, `Client Secret` und besonders den `Refresh Token` wie Passwörter. Lade sie **niemals** auf öffentliche Plattformen wie GitHub hoch!

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos.*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)