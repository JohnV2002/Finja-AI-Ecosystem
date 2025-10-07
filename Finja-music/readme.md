# 🎶 Finja Music System

Willkommen beim Finja Music System! 💖

Dieses Projekt ist eine Sammlung von Modulen, die es ermöglichen, Live-Musikinformationen aus verschiedenen Quellen (Webradio, Spotify) abzurufen, intelligent zu verarbeiten und als dynamisches Overlay in dein Streaming-Setup mit OBS zu integrieren.

Das Herzstück ist ein zentrales "Musikgehirn", das lernt, welche Musik du magst, und darauf mit personalisierten Reaktionen reagiert.

---

## ✨ Wähle deine Version: All-in-One oder Modular?

Dieses Projekt existiert in zwei Varianten. Wähle die, die am besten zu dir passt.

### 🚀 All-in-One Edition (Empfohlen)
Alles in einem Ordner, gesteuert über eine komfortable Weboberfläche.
-   **Ideal für:** Einsteiger und die meisten Nutzer.
-   **Vorteile:** Einfache Bedienung per Mausklick, zentrale Verwaltung aller Quellen, weniger Konsolenarbeit.

### 🛠️ Modulares System (Für Fortgeschrittene)
Jede Musikquelle befindet sich in einem eigenen, unabhängigen Ordner.
-   **Ideal für:** Entwickler oder Nutzer, die nur eine einzige Quelle benötigen und volle manuelle Kontrolle bevorzugen.
-   **Vorteile:** Granulare Kontrolle, Quellen können komplett unabhängig voneinander betrieben werden.

---

## 🚀 All-in-One Edition (Empfohlene Methode)

Diese Version bündelt alle Musik-Module in einem einzigen Ordner und wird über eine komfortable Weboberfläche gesteuert.

### Features
-   **Zentrale Steuerung:** Eine Weboberfläche (`Musik.html`) zur Verwaltung des gesamten Systems.
-   **Multi-Quellen-Unterstützung:** Aktiviere mit einem Klick die Erkennung für TruckersFM, Spotify, 89.0 RTL oder MDR.
-   **Intelligentes Musikgehirn:** Nutzt eine zentrale Wissensdatenbank (`songs_kb.json`), um Genres zu erkennen und dynamische Reaktionen zu generieren.
-   **Integrierte Datenbank-Tools:** Baue und erweitere deine Song-Datenbank direkt über die Weboberfläche aus Spotify-Playlists.
-   **Konfliktlösung:** Eine eigene Web-UI (`ArtistNotSure.html`), um unklare Künstlerzuordnungen zu korrigieren.

### Ordnerstruktur
```plaintext
finja-everthing-in-once/
├── config/                  # Konfigurationsdateien
├── MDRHilfe/                # Hilfsskripte für MDR
├── Memory/                  # Finjas Langzeitgedächtnis & Profile
├── missingsongs/            # Logs für unbekannte Songs
├── Nowplaying/              # Zentrale Ausgabedateien für OBS
├── OBSHTML/                 # Alle HTML-Overlays und Steuerungs-Webseiten
├── RTLHilfe/                # Hilfsskripte für 89.0 RTL
├── SongsDB/                 # Die zentrale Song-Datenbank
├── start_server.bat         # Startet den Haupt-Webserver
└── webserver.py             # Der Code für den Webserver
```

### Einrichtung & Start
**Schritt 1: Spotify API konfigurieren**
1.  Öffne die Datei `finja-everthing-in-once/config/config_spotify.json`.
2.  Trage deine `client_id`, `client_secret` und deinen `refresh_token` ein.
> 🔴 **WICHTIG:** Diese Datei enthält sensible Zugangsdaten! Lade sie niemals auf ein öffentliches Repository hoch.

**Schritt 2: Datenbank aufbauen (Optional)**
1.  Exportiere deine Spotify-Playlists als `.csv`-Dateien.
2.  Lege sie in den (neu zu erstellenden) Ordner `finja-everthing-in-once/exports/`.
3.  Nutze später die Weboberfläche, um die Datenbank zu bauen.

**Schritt 3: Server starten**
Führe die Datei `start_server.bat` per Doppelklick aus. Solange das Konsolenfenster offen ist, läuft dein Server.

**Schritt 4: Weboberfläche öffnen**
Öffne deinen Browser und gehe zu: `http://localhost:8022/Musik.html`.

### Benutzung der Weboberfläche
-   **Musikquellen:** Wähle per Knopfdruck, welcher Quelle Finja "zuhören" soll. Für RTL & MDR müssen zuerst die entsprechenden "Helfer" im unteren Bereich der Seite gestartet werden.
-   **DB und Hilfsskripte:** Nutze die Werkzeuge, um deine Song-Datenbank aus den `.csv`-Exporten zu erstellen, fehlende Song-Infos anzureichern oder Künstler-Konflikte zu lösen.

### OBS-Integration
-   **Browser-Quelle:** Füge eine Browser-Quelle in OBS hinzu und wähle als "Lokale Datei" das passende HTML-Overlay aus dem `OBSHTML`-Ordner.
-   **Text-Quellen:** Die Overlays lesen die Daten automatisch aus dem `Nowplaying`-Ordner. Pfade müssen nicht mehr angepasst werden!

---

## 🛠️ Modulares System (Manuelle Einrichtung)

Diese klassische Variante nutzt für jede Musikquelle einen separaten Ordner. Die Steuerung erfolgt über individuelle Skripte im Terminal.

### Das Kernkonzept
Das System besteht aus zwei Teilen:
1.  **"Get Content" (Ohren):** Ein Skript, das den Song von einer Quelle holt.
2.  **"MUSIK/Brain" (Gehirn):** Ein zentrales Skript, das den Song analysiert.

Die empfohlene Methode ist, **EIN zentrales Gehirn für ALLE Quellen** zu nutzen, um ein konsistentes Erlebnis zu gewährleisten.

```mermaid
flowchart TD
    subgraph Quellen (Ohren)
        A[🚚 TruckersFM]
        B[🎧 Spotify]
        C[📻 MDR]
        D[📡 89.0 RTL]
    end

    subgraph Verarbeitung
        E((nowplaying.txt))
        F[🧠 Zentrales Musikgehirn]
    end

    subgraph Ausgabe
        G[📁 OBS-Dateien]
        H[💖 OBS Overlay]
    end

    A & B & C & D --> E --> F --> G --> H
```

### Module im Detail
Für eine detaillierte Anleitung zur Einrichtung, lies bitte die `README.md` im jeweiligen Unterordner des modularen Projekts.

-   **🚚 TruckersFM:** Der Grundbaustein. Holt Song-Infos durch Web-Scraping. Der `MUSIK`-Ordner hier dient als **zentrales Gehirn**.
-   **🎧 Spotify:** Bindet deinen Spotify-Account über die offizielle API an.
-   **📻 MDR:** Ein robustes Skript, das mehrere Quellen (ICY, XML, Webseite) prüft.
-   **📡 89.0 RTL:** Nutzt das Chrome Debugging Protocol, um den Songtitel direkt aus dem Webplayer auszulesen.

---

## 📜 Lizenz

Alle Module in diesem Projekt stehen unter der **MIT-Lizenz**.
*Gebaut mit 💖, Mate und einer Prise Chaos.*