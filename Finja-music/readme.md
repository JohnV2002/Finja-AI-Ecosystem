# 🎶 Finja-Music: Ein modulares Musik-System für OBS

Willkommen beim Finja-Music-System! 💖

Dieses Projekt ist eine Sammlung von Modulen, die es ermöglichen, Live-Musikinformationen aus verschiedenen Quellen (Webradio, Spotify) abzurufen, intelligent zu verarbeiten und als dynamisches Overlay in dein Streaming-Setup mit OBS zu integrieren.

Das Herzstück ist ein zentrales "Musikgehirn", das lernt, welche Musik du magst, und darauf mit personalisierten Reaktionen reagiert.

---

## 💡 Das Kernkonzept: Ein Gehirn, viele Ohren

Das gesamte System basiert auf einer zweiteiligen Architektur, die für jede Musikquelle gilt:

1.  **Teil 1: Get Content (Die Ohren)**
    Ein spezialisiertes Skript für jede Quelle (z.B. `truckersfm_nowplaying.py` für TruckersFM), das nur eine Aufgabe hat: den aktuell laufenden Song zu erkennen und in eine einfache Textdatei (`nowplaying.txt`) zu schreiben.

2.  **Teil 2: MUSIK/Brain (Das Gehirn)**
    Ein zentrales Skript, das die `nowplaying.txt` einer aktiven Quelle liest. Es gleicht den Song mit einer Wissensdatenbank ab, ermittelt Genres, wählt eine passende Reaktion aus und speichert Erinnerungen. Das Ergebnis wird in Dateien geschrieben, die dein OBS-Overlay anzeigt.

**Die empfohlene Methode ist, EIN zentrales Gehirn für ALLE Quellen zu nutzen.**

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

    A --> E
    B --> E
    C --> E
    D --> E
    E --> F
    F --> G
    G --> H
```

---

## 🎵 Unterstützte Musikquellen

Dieses Repository enthält alles, was du für die Anbindung der folgenden Quellen benötigst:

| Quelle | Abrufmethode | Status |
| :--- | :--- | :--- |
| **🚚 TruckersFM** | Web Scraping der offiziellen Webseite. | ✅ Einsatzbereit |
| **🎧 Spotify** | Abfrage über die offizielle Spotify Web API. | ✅ Einsatzbereit |
| **📻 MDR** | Hybride Abfrage (ICY-Metadaten, XML-Feed, Web-Scraping). | ✅ Einsatzbereit |
| **📡 89.0 RTL** | Auslesen der Webseite via Chrome Debugging Protocol (CDP). | ✅ Einsatzbereit |

---

## 🚀 Empfohlenes Setup: Schritt für Schritt

Um Inkonsistenzen zu vermeiden, solltest du das System mit einem zentralen Gehirn aufbauen.

1.  **Die Basis schaffen (TruckersFM):**
    Beginne mit der Einrichtung des **TruckersFM-Moduls**. Der `MUSIK`-Ordner in diesem Verzeichnis dient als unser zentrales Gehirn. Richte hier deine `songs_kb.json`, `reactions.json` und `contexts.json` vollständig ein.

2.  **Deine Musik-Datenbank aufbauen:**
    Nutze die **Spotify-Tools** im `TruckersFM/MUSIK`-Ordner (z.B. `build_spotify_kb_only.py`), um deine `songs_kb.json` aus deinen Spotify-Playlists zu erstellen. Dies ist die Wissensgrundlage für alle Module.

3.  **Weitere Quellen hinzufügen (z.B. Spotify):**
    -   Richte den **Teil 1 (Get Content)** des Spotify-Moduls gemäß seiner eigenen README ein.
    -   Folge dann den Anweisungen in der **Teil 2 README** für die **empfohlene Methode (🅑)**, bei der du die Konfigurationsdatei so anpasst, dass sie auf das zentrale Gehirn im TruckersFM-Ordner verweist.

4.  **Wiederholen:**
    Wiederhole Schritt 3 für alle weiteren Quellen, die du nutzen möchtest (MDR, 89.0 RTL).

---

## 📂 Module im Detail

Jedes Modul befindet sich in einem eigenen Unterordner und enthält eine oder mehrere detaillierte `README.md`-Dateien mit spezifischen Anweisungen.

### 🚚 TruckersFM
Der Grundbaustein des Systems. Holt Song-Infos durch direktes Auslesen der TruckersFM-Webseite. Der `MUSIK`-Ordner hier ist als zentrales Gehirn vorgesehen.

[➡️ **Zur ausführlichen Anleitung für das TruckersFM-Modul...**](./TruckersFM/README.md)

### 🎧 Spotify
Bindet deinen Spotify-Account über die offizielle API an. Erfordert eine einmalige Authentifizierung.

[➡️ **Zur ausführlichen Anleitung für das Spotify-Modul...**](./Spotify/README.md)

### 📻 MDR (MDR Sachsen-Anhalt)
Ein robustes Skript, das mehrere Quellen (Stream-Metadaten, XML, Webseite) prüft, um den aktuellen Song von MDR zuverlässig zu erkennen.

[➡️ **Zur ausführlichen Anleitung für das MDR-Modul...**](./MDR/README.md)

### 📡 89.0 RTL
Nutzt das Chrome Debugging Protocol, um den Songtitel direkt aus dem Webplayer von 89.0 RTL auszulesen. Erfordert eine laufende Instanz von Google Chrome.

[➡️ **Zur ausführlichen Anleitung für das 89.0 RTL-Modul...**](./RTL/README.md)

---

## 📜 Lizenz

Alle Module in diesem Projekt stehen unter der **MIT-Lizenz**.  
*Gebaut mit 💖, Mate und einer Prise Chaos ✨*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)