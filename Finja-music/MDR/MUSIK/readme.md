# 🧠 MDR – MUSIK (Teil 2 – Brain)

Dieses Modul ist der Analyse- und Reaktions-Teil für **MDR Sachsen-Anhalt**. Es liest die `nowplaying.txt` aus dem `MDR - Get Content`-Verzeichnis und erzeugt daraus Genres, Reaktionen und Langzeit-Erinnerungen.

> ⚡ Ohne dieses Modul gibt es keine Genres, keine dynamischen Reaktionen und kein Langzeitgedächtnis für die von MDR gespielten Songs!

---

## 💡 Setup-Varianten

Du hast zwei Möglichkeiten, dieses Modul zu nutzen. Die empfohlene Methode ist, ein zentrales Gehirn für alle deine Musikquellen zu verwenden.

### 🅑 MDR nutzt das TruckersFM-Brain (Empfohlen 💖)

> **Empfehlung des Creators:** Alle Musikquellen (TruckersFM, MDR, Spotify etc.) sollten dasselbe Brain nutzen. Das sorgt für ein konsistentes Verhalten und ein zentrales Gedächtnis.

1.  **Voraussetzung:** Richte zuerst das `TruckersFM/MUSIK/`-Verzeichnis vollständig und korrekt ein.
2.  **Konfiguration kopieren:** Kopiere die fertige `config_min.json` aus `TruckersFM/MUSIK/` in das `MDR/MUSIK/`-Verzeichnis und benenne sie in `config_mdr.json` um.
3.  **Pfade anpassen:** Öffne die neue `config_mdr.json` und ändere **nur die Pfade** so ab, dass sie auf die richtigen Ein- und Ausgabedateien für MDR sowie auf das zentrale TruckersFM-Brain verweisen:

    ```json
    {
      "input_path": "../MDR - Get Content/nowplaying.txt",
      "fixed_outputs": "../MDR - Get Content/outputs",
    
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

> #### Ergebnis:
> -   MDR nutzt exakt dieselbe Wissensdatenbank, dasselbe Gedächtnis und dieselben Reaktionen wie TruckersFM.
> -   Neue Songs und Erinnerungen wirken sich sofort auf alle angebundenen Musiksysteme aus.

### 🅐 Eigenständiger MDR-Betrieb (Nicht empfohlen)
> **📝 Hinweis:** Diese Methode ist möglich, aber nicht empfohlen, da sie zu getrennten Datenbanken und inkonsistentem Verhalten führt.

1.  **Voraussetzung:** Stelle sicher, dass der erste Teil (`MDR - Get Content`) korrekt läuft und eine `nowplaying.txt` erzeugt.
2.  **Dateien kopieren:** Kopiere `contexts.json`, `reactions.json` und `build_spotify_kb_only.py` aus `TruckersFM/MUSIK/` in den `MDR/MUSIK/`-Ordner.
3.  **Exporte hinzufügen:** Erstelle in `MDR/MUSIK/` einen Ordner `exports/` und lege dort deine Musik-Exporte als `.csv`-Dateien ab.
4.  **Wissensdatenbank erstellen:** Führe im `MDR/MUSIK/`-Ordner folgenden Befehl aus:
    ```bash
    python build_spotify_kb_only.py
    ```
    Dies erstellt eine neue, MDR-spezifische `SongsDB/songs_kb.json`.
5.  **Konfiguration anpassen:** Bearbeite die `config_mdr.json` so, dass alle Pfade auf die lokalen Verzeichnisse innerhalb von `MDR/MUSIK/` zeigen.

---

## ⚙️ Funktionsweise im Detail

-   Das Skript (`finja_min_writer.py`) liest die `nowplaying.txt` alle paar Sekunden.
-   Es gleicht den erkannten Song mit deiner `songs_kb.json` ab, um Genres und Tags zu finden.
-   Basierend auf den Profilen in `contexts.json` wird eine passende Reaktion (`like`/`neutral`/`dislike`) ausgewählt.
-   Das Ergebnis wird in die `outputs/`-Dateien für OBS geschrieben.
-   Jede Reaktion wird im Langzeitgedächtnis (`memory.json`) vermerkt.
-   Eine `.lock`-Datei verhindert den versehentlichen Doppelstart des Skripts.

---

## 🚀 Starten & OBS-Einrichtung

1.  Stelle sicher, dass im ersten Teil (`MDR - Get Content`) die `nowplaying.txt` erfolgreich erstellt wird.
2.  Starte das Musik-Brain mit dem Skript:
    ```bat
    run_finja_MDR.bat
    ```
3.  Füge in OBS zwei neue **"Text (GDI+)"**-Quellen hinzu.
4.  Wähle für jede Quelle **"Aus Datei lesen"** und verweise auf:
    -   `MDR - Get Content/outputs/obs_genres.txt`
    -   `MDR - Get Content/outputs/obs_react.txt`

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos.*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)