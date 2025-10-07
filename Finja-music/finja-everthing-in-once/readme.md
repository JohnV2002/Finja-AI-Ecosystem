# 🎶 Finja Music - All-in-One Edition

Willkommen zur All-in-One Edition von Finja Music! Dieses Paket bündelt alle Musik-Module (TruckersFM, Spotify, RTL, MDR) in einem einzigen Ordner und wird über eine komfortable Weboberfläche gesteuert.

Das Herzstück ist ein zentraler Webserver, der es dir erlaubt, Musikquellen per Knopfdruck zu wechseln, deine Song-Datenbank zu pflegen und Finjas Reaktionen zu verwalten, ohne Konsolenbefehle eingeben zu müssen.

---

## ✨ Features

-   **Zentrale Steuerung:** Eine Weboberfläche (`Musik.html`) zur Verwaltung des gesamten Systems.
-   **Multi-Quellen-Unterstützung:** Aktiviere mit einem Klick die Erkennung für TruckersFM, Spotify, 89.0 RTL oder MDR.
-   **Intelligentes Musikgehirn:** Nutzt eine zentrale Wissensdatenbank (`songs_kb.json`), um Genres zu erkennen und dynamische Reaktionen zu generieren.
-   **Integrierte Datenbank-Tools:** Baue und erweitere deine Song-Datenbank direkt über die Weboberfläche aus Spotify-Playlists.
-   **Konfliktlösung:** Eine eigene Web-UI (`ArtistNotSure.html`), um unklare Künstlerzuordnungen zu korrigieren.
-   **Einfache OBS-Integration:** Alle Module schreiben ihre Ausgaben in einen zentralen Ordner, was die Einrichtung in OBS vereinfacht.
-   **Hilfsskripte:** Beinhaltet Helfer-Skripte für externe Prozesse wie den RTL- und MDR-Crawler.

---

## 📂 Ordnerstruktur

```plaintext
finja-everthing-in-once/
├── config/                  # Konfigurationsdateien
│   ├── config_min.json      # Hauptkonfiguration des "Gehirns"
│   └── config_spotify.json  # Spotify API-Schlüssel
├── MDRHilfe/                # Hilfsskripte für MDR
├── Memory/                  # Finjas Langzeitgedächtnis & Profile
├── missingsongs/            # Logs für unbekannte Songs
├── Nowplaying/              # Zentrale Ausgabedateien für OBS
├── OBSHTML/                 # Alle HTML-Overlays und Steuerungs-Webseiten
├── RTLHilfe/                # Hilfsskripte für 89.0 RTL
├── SongsDB/                 # Die zentrale Song-Datenbank
├── .env                     # Platzhalter für Spotify-Schlüssel
├── start_server.bat         # Startet den Haupt-Webserver
└── webserver.py             # Der Code für den Webserver
```

---

## 🚀 Einrichtung & Start

**Schritt 1: Spotify API konfigurieren**
Bevor du startest, musst du deine Spotify-Zugangsdaten eintragen.
1.  Öffne die Datei `finja-everthing-in-once/config/config_spotify.json`.
2.  Trage deine `client_id`, `client_secret` und deinen `refresh_token` ein.

> 🔴 **WICHTIG:** Diese Datei enthält sensible Zugangsdaten! Lade sie niemals auf ein öffentliches GitHub-Repository hoch. Die `.env`-Datei ist nur eine Vorlage und wird von diesem Setup nicht direkt verwendet.

**Schritt 2: Datenbank aufbauen (Optional)**
Wenn du deine eigene Song-Datenbank aus Spotify-Playlists erstellen möchtest:
1.  Exportiere deine Playlists als `.csv`-Dateien.
2.  Lege sie in den (neu zu erstellenden) Ordner `finja-everthing-in-once/exports/`.
3.  Starte den Server (Schritt 3) und nutze die Weboberfläche, um die Datenbank zu bauen.

**Schritt 3: Server starten**
Führe die Datei `start_server.bat` per Doppelklick aus. Es öffnet sich ein Konsolenfenster. Solange dieses Fenster offen ist, läuft dein Server.

**Schritt 4: Weboberfläche öffnen**
Öffne deinen Browser und gehe zu folgender Adresse:
`http://localhost:8022/Musik.html`
Du siehst nun die zentrale Steuerungsoberfläche.

---

## 🎮 Benutzung der Weboberfläche

Die Weboberfläche ist in zwei Bereiche unterteilt:

### 1. Musikquellen
Hier wählst du aus, welcher Musikquelle Finja "zuhören" soll.
-   **TruckersFM & Spotify aktivieren:** Klicke einfach auf den entsprechenden Button. Der Server startet im Hintergrund den passenden Prozess.
-   **RTL & MDR aktivieren:** Diese Quellen benötigen externe Hilfsskripte.
    1.  Starte zuerst im unteren Bereich der Webseite die entsprechenden Helfer (`Starte RTL Browser`, `Starte MDR NowPlaying`).
    2.  Sobald der Helfer läuft, wird der "Aktivieren"-Button freigeschaltet und du kannst die Quelle auswählen.
-   **Quelle deaktivieren:** Wenn eine Quelle aktiv ist, erscheint ein roter "Deaktivieren"-Button, um den Prozess zu stoppen.

### 2. DB und Hilfsskripte
Hier findest du Werkzeuge zur Verwaltung deiner Datenbank und zum Starten der externen Crawler.
-   **Spotify-Exporte in DB bauen:** Liest die `.csv`-Dateien aus dem `exports/`-Ordner und fügt sie deiner `songs_kb.json` hinzu.
-   **Fehlende Songs via Spotify anreichern:** Geht die `missingsongs_log.jsonl` durch und versucht, fehlende Song-Infos über die Spotify-API zu finden.
-   **Artist-Konflikte prüfen:** Öffnet eine neue Seite (`ArtistNotSure.html`), auf der du manuell unklare Künstlerzuordnungen korrigieren kannst.
-   **Starte RTL Browser / Starte MDR NowPlaying:** Diese Buttons führen die notwendigen `.bat`-Dateien aus, die für die Song-Erkennung dieser Sender benötigt werden.

---

## 🎨 OBS-Integration

Alle Overlays und Text-Dateien werden zentral im `Nowplaying`- und `OBSHTML`-Ordner verwaltet.
-   **Browser-Quelle:** Füge eine Browser-Quelle in OBS hinzu und wähle als "Lokale Datei" das passende HTML-Overlay aus dem `OBSHTML`-Ordner (z.B. `Sodakiller_NowPlaying_TFM_Bright.html`).
-   **Text-Quellen:** Die Overlays lesen die Daten automatisch aus den Dateien im `Nowplaying`-Ordner (z.B. `nowplaying.txt`, `obs_genres.txt`). Du musst die Pfade in den HTML-Dateien nicht mehr anpassen!

---

## ⚠️ Wichtige Hinweise

-   **Hartcodierte Pfade:** Die Skripte im `RTLHilfe`-Ordner enthalten teilweise noch absolute Pfade. Wenn du das Projekt verschiebst, musst du diese eventuell anpassen.
-   **Server muss laufen:** Die Weboberfläche und die gesamte Automatik funktionieren nur, solange `start_server.bat` im Hintergrund läuft.

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos.*