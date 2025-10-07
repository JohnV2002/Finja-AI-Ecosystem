# 🧠 Finja's Brain & Knowledge Core – Docker Spotify Modul

Ein dynamisches und intelligentes Song-Reaktionssystem, das in Echtzeit auf die aktuelle Spotify-Wiedergabe reagiert. Entwickelt für den Einsatz in interaktiven Umgebungen wie Twitch-Streams, um eine personalisierte und kontextsensitive Atmosphäre zu schaffen.

---

## 🌟 Features

-   Echtzeit-Verbindung zur **Spotify-API** zur Überwachung der aktuellen Wiedergabe.
-   Dynamische & intelligente Song-Reaktionen basierend auf einer lokalen **Wissensdatenbank (KB)**.
-   **Kontext-sensitives** Reaktionssystem, das Stimmungen anpasst (z.B. je nach gestreamtem Spiel).
-   Langzeitgedächtnis für Songs mit **"Decay"-Funktion**, das Wiederholungen erkennt und darauf reagiert.
-   Hochgradig anpassbares Scoring-System mit Biases für Künstler, Genres und Song-Stimmungen.
-   **"Special Rule"-Engine** für vordefinierte Reaktionen auf bestimmte Lieder oder Künstler.
-   Automatische Erkennung von Song-Versionen wie "Nightcore", "Speed Up", "Remix" etc.
-   Effizientes Caching des Song-Index für blitzschnelle Ladezeiten.
-   Ausgabe der Reaktionen in Textdateien und über eine integrierte **FastAPI-Web-API**.
-   Vollständig über **JSON-Dateien** konfigurierbar für maximale Flexibilität.

---

## 🚀 Setup & Installation

Dieses Projekt ist für den Betrieb mit **Docker und Docker Compose** optimiert, um die Einrichtung so einfach wie möglich zu gestalten.

### Voraussetzungen

-   Docker muss auf deinem System installiert sein.
-   Docker Compose (ist bei Docker Desktop meist enthalten).
-   Einen [Spotify Developer Account](https://developer.spotify.com/dashboard) und eine App, um API-Schlüssel zu erhalten.

### Schritt 1: Projekt klonen oder herunterladen
Lade alle Projektdateien in einen Ordner auf deinem Server oder Computer.

### Schritt 2: Spotify API-Schlüssel konfigurieren
Erstelle eine Datei mit dem Namen `.env` im Hauptverzeichnis des Projekts und füge deine Spotify API-Schlüssel ein:
```bash
# .env
SPOTIFY_CLIENT_ID=DEIN_CLIENT_ID_HIER
SPOTIFY_CLIENT_SECRET=DEIN_CLIENT_SECRET_HIER
SPOTIFY_REFRESH_TOKEN=DEIN_REFRESH_TOKEN_HIER
```

### Schritt 3: Docker-Container starten
Öffne ein Terminal im Hauptverzeichnis des Projekts und führe den folgenden Befehl aus:
```bash
docker compose up -d --build
```
-   `up`: Startet den Container.
-   `-d`: Führt den Container im Hintergrund aus (detached mode).
-   `--build`: Baut das Docker-Image neu, falls Änderungen an der `Dockerfile` vorgenommen wurden.

Der Container wird nun gebaut und gestartet. Die Anwendung ist sofort einsatzbereit.

---

## 🔧 Konfiguration

Die Logik der Anwendung kann detailliert über die JSON-Dateien im Projektverzeichnis angepasst werden:

-   `config_min.json`: Hauptkonfiguration für Pfade, Intervalle und grundlegendes Verhalten.
-   `Memory/reactions.json`: Definiert die Reaktionstexte, Schwellenwerte für Stimmungen (like, dislike etc.) und spezielle Regeln.
-   `Memory/contexts.json`: Definiert verschiedene Profile und Kontexte (z.B. für verschiedene Spiele), um die Song-Bewertung anzupassen.
-   `SongsDB/songs_kb.json`: Die Wissensdatenbank, die alle bekannten Songs, deren Genres und Metadaten enthält.

---

## 📡 API-Endpunkte

Die Anwendung stellt eine kleine API zur Verfügung, um den aktuellen Status abzurufen.

### Health Check
Überprüft, ob der Server läuft.
-   **URL:** `http://DEINE_SERVER_IP:8022/health`
-   **Antwort:** `{"ok":true,"time":"..."}`

### Aktuelle Reaktion abrufen
Gibt die letzte generierte Reaktion und Song-Informationen zurück.
-   **URL:** `http://DEINE_SERVER_IP:8022/get/Finja`
-   **Antwort:**
    ```json
    {
      "reaction": "Immer noch ein Banger.",
      "genres": "2020s, tekno, speed up",
      "title": "About You",
      "artist": "Rütekker, Hardtekk Channel",
      "context": "offline",
      "updated_at": "..."
    }
    ```

---

## 📝 Lizenz

Dieses Projekt steht unter der **MIT-Lizenz**. Siehe die `LICENSE`-Datei für weitere Details.