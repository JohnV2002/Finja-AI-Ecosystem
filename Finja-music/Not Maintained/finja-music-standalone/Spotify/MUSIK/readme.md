# 🎧 Spotify – MUSIK (Teil 2 – Brain)

Dieses Modul ist der **Musik-Brain-Teil für Spotify**. Es liest die `nowplaying_spotify.txt` aus dem `Spotify - Get Content`-Ordner und erzeugt daraus **Genres, Reaktionen und Memories**.

> ⚡ Dies ist nur der „Denker“ des Systems. Ohne ihn bekommst du keine Genres oder dynamischen Reaktionen in deinem Stream angezeigt.

---

## 💡 Setup-Varianten

Du hast zwei Möglichkeiten, dieses Modul zu nutzen. Die empfohlene Methode ist, ein zentrales Gehirn für alle deine Musikquellen zu verwenden.

### 🅑 Spotify nutzt das TruckersFM-Brain (Empfohlen 💖)

> **Empfehlung des Creators:** Nutze ein gemeinsames Brain für alle Quellen (TruckersFM, Spotify etc.). So lernt das System zentral und alle deine Erinnerungen, Reaktionen und Vorlieben sind an einem Ort.

1.  **Voraussetzung:** Richte zuerst das `TruckersFM/MUSIK/`-Verzeichnis vollständig und korrekt ein.
2.  **Konfiguration kopieren:** Kopiere die fertige `config_min.json` von `TruckersFM/MUSIK/` nach `Spotify/MUSIK/`.
3.  **Pfade anpassen:** Öffne die neue `config_min.json` in `Spotify/MUSIK/` und ändere **nur die Pfade** so ab, dass sie auf die richtigen Ein- und Ausgabedateien für Spotify sowie auf das zentrale TruckersFM-Brain verweisen:

    ```jsonc
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
      },
    
      "missing_log": {
        "enabled": true,
        "path": "../../TruckersFM/MUSIK/missingsongs/missing_songs_log.jsonl"
      },
    
      "artist_not_sure": {
        "enabled": true,
        "path": "../../TruckersFM/MUSIK/missingsongs/artist_not_sure.jsonl"
      }
    }
    ```

> #### Ergebnis:
> -   Spotify nutzt exakt dieselbe Wissensdatenbank, dasselbe Gedächtnis und dieselben Reaktionen wie TruckersFM.
> -   Neue Erinnerungen und Vorlieben wirken sich sofort auf alle angebundenen Musiksysteme aus.

### 🅐 Nur Spotify mit eigenem Brain

> **Hinweis:** Diese Methode ist möglich, aber nicht empfohlen, da sie zu getrennten Datenbanken und inkonsistentem Verhalten führt.

1.  **Voraussetzung:** Stelle sicher, dass der erste Teil (`Spotify - Get Content`) korrekt läuft und eine `nowplaying_spotify.txt` erzeugt wird.
2.  **Dateien kopieren:** Kopiere `contexts.json`, `reactions.json` und `build_spotify_kb_only.py` aus dem `TruckersFM/MUSIK/`-Ordner in den `Spotify/MUSIK/`-Ordner.
3.  **Spotify-Exporte hinzufügen:** Erstelle in `Spotify/MUSIK/` einen Ordner `exports/` und lege dort deine Spotify-Playlist-Exporte als `.csv`-Dateien ab.
4.  **Wissensdatenbank erstellen:** Führe im `Spotify/MUSIK/`-Ordner folgenden Befehl aus:
    ```bash
    python build_spotify_kb_only.py
    ```
    Dies erstellt eine neue, Spotify-spezifische `SongsDB/songs_kb.json`.
5.  **Konfiguration anpassen:** Bearbeite die `config_min.json` so, dass alle Pfade auf die lokalen Verzeichnisse innerhalb von `Spotify/MUSIK/` zeigen.

---

## 🧠 Funktionsweise im Detail

-   Das Skript lädt die `nowplaying_spotify.txt` alle paar Sekunden.
-   Es gleicht den Song mit deiner `songs_kb.json` ab, um Genres und Tags zu finden.
-   Basierend auf den Profilen in `contexts.json` wird eine passende Reaktion (`like`/`neutral`/`dislike`) ausgewählt.
-   Das Ergebnis wird in die `outputs/`-Dateien für OBS geschrieben.
-   Jede Reaktion wird im Langzeitgedächtnis (`memory.json`) vermerkt.
-   Ein `.finja_min_writer.lock` verhindert den versehentlichen Doppelstart des Skripts.

---

## 🚀 Starten & OBS-Einrichtung

1.  Stelle sicher, dass im ersten Teil (`Spotify - Get Content`) Musik auf Spotify erkannt wird.
2.  Starte das Musik-Brain mit dem Skript:
    ```bat
    run_finja.bat
    ```
3.  Füge in OBS zwei neue **"Text (GDI+)"**-Quellen hinzu.
4.  Wähle für jede Quelle **"Aus Datei lesen"** und verweise auf:
    -   `Spotify - Get Content/outputs/obs_genres.txt`
    -   `Spotify - Get Content/outputs/obs_react.txt`

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos.*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)