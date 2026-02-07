# 🧠 Musik – Finja's Brain (Teil 2)
**Das Musikgehirn des Systems**

Liest die `nowplaying.txt` von Teil 1 und erzeugt daraus **Genres, Reaktionen & Memories**. Hier findet die komplette **Analyse, Bewertung & Ausgabe** für dein OBS-Overlay statt.

> **Wichtig:** Ohne dieses Skript gibt es keine Genres oder Finja-Reaktionen in deinem Stream – nur den reinen Songtitel!

---

## 🧩 Was dieser Teil macht

-   Liest den aktuellen Songtitel und Interpreten aus der `nowplaying.txt`.
-   Gleicht diese Informationen mit deiner persönlichen Song-Datenbank (`songs_kb.json`) ab.
-   Ermittelt Genres und erkennt Spezialversionen (z.B. Nightcore, Speed Up).
-   Wählt eine passende Reaktion (Like / Neutral / Dislike) basierend auf deinen Vorlieben.
-   Schreibt die aufbereiteten Informationen in Echtzeit in zwei Textdateien für OBS:
    -   `outputs/obs_genres.txt`
    -   `outputs/obs_react.txt`
-   Speichert Finjas Meinung zu den Songs langfristig im Langzeitgedächtnis (`Memory/memory.json`).

---

## 📂 Dateien im Überblick

| Datei | Funktion | Was du anpassen kannst |
| :--- | :--- | :--- |
| `finja_min_writer.py` | Hauptskript – verarbeitet alles | ⚙️ Nur Code: Muss meist nicht verändert werden |
| `run_finja.bat` | Startet `finja_min_writer.py` | 🔧 Optional: Python-Pfad anpassen |
| `config_min.json` | **Zentrale Konfiguration** | ⚙️ **Alle Pfade, Verhalten, Features** |
| `SongsDB/songs_kb.json` | Knowledge Base (Songs + Genres/Tags) | 📥 Mit Spotify-Tools generieren/erweitern |
| `Memory/reactions.json` | Reaktionstexte für Finja | ✍️ Eigene Texte hinzufügen oder anpassen |
| `Memory/contexts.json` | Spiel-/Kontext-spezifischer Bias | ✍️ Neue Profile anlegen (mit `tag_weights`) |
| `Memory/memory.json` | Langzeitgedächtnis | ⚡ Automatisch gefüllt – nicht manuell editieren |
| `missingsongs/*.jsonl` | Logs unbekannter Songs/Artists | 📌 Später mit Spotify-Tools vervollständigen |
| `outputs/obs_genres.txt` | Ausgabe für OBS (Genres) | ⚡ Wird automatisch überschrieben |
| `outputs/obs_react.txt` | Ausgabe für OBS (Reaktionen) | ⚡ Wird automatisch überschrieben |

---

## ⚙️ Die `config_min.json` – Das Kontrollzentrum

Dies ist die wichtigste Datei zur Steuerung von Finjas Musikgehirn. Hier stellst du alle Pfade und Verhaltensweisen ein.

### Wichtige Optionen

```jsonc
{
  "input_path": "../TRUCKERSFM - GET CONTENT/nowplaying.txt",  // Wo die Songtitel herkommen
  "fixed_outputs": "../TRUCKERSFM - GET CONTENT/outputs",      // Wohin obs_genres.txt & obs_react.txt geschrieben werden
  "songs_kb_path": "SongsDB/songs_kb.json",                    // Deine Song-KB

  "interval_s": 2.0,           // Alle X Sekunden auf Änderungen prüfen
  "init_write": true,            // Gleich beim Start schon in die OBS-Dateien schreiben

  "genres_template": "Pop • Nightcore • Speed Up", // Wie Genres im OBS angezeigt werden
  "react_template": "OMG NICE",                    // Wie Reaktionen aussehen
  "genres_joiner": " • ",                          // Trennzeichen zwischen den Genres

  "kb_index_cache_path": "cache/kb_index.pkl",     // RAM-KB Cache (SHA-256 geprüft)
  "log_every_tick": false,                           // True = sehr viele Logs für Debugging
}
```

### Reactions-Block
```jsonc
"reactions": {
  "enabled": true,
  "path": "Memory/reactions.json",
  "mode": "score",            // Bewertet Songs (like/neutral/dislike)
  "cooldown_s": 45,           // Wartezeit zwischen Reaktionen
  "context": {
    "enabled": true,
    "path": "Memory/contexts.json",
    "refresh_s": 5            // Alle 5s den aktuellen Spiel-Status laden
  }
}
```

### Memory-Block
```jsonc
"memory": {
  "enabled": true,
  "path": "Memory/memory.json",
  "min_confidence": 2,      // Speichert erst, wenn ein Song 2x gehört wurde

  "decay": {                // "Vergessen" über Zeit
    "enabled": true,
    "half_life_days": 90
  },

  "tuning": {
    "min_seen_for_repeat": 2,
    "suppress_cross_if_dislike": true
  }
}
```

---

## 🧠 Kernlogik & Datenbank

### `reactions.json` & `contexts.json`

-   **`reactions.json`:** Enthält alle Texte, die Finja als Reaktion anzeigen kann, unterteilt in die Kategorien `like`, `neutral` und `dislike`. Du kannst hier nach Belieben Texte ändern, hinzufügen oder löschen.
-   **`contexts.json`:** Erlaubt es dir, Finjas Musikgeschmack je nach Kontext (z.B. dem aktuell gestreamten Spiel) anzupassen. Du kannst Profile anlegen, die bestimmte Genres oder Künstler bevorzugen oder ablehnen. Der aktive Kontext wird aus der Datei `Memory/game_state.txt` gelesen.

### `songs_kb.json` (Die Wissensdatenbank)

-   Dies ist die zentrale Datenbank mit all deinen Songs und den dazugehörigen Genres und Tags.
-   **Wichtig:** Diese Datei wird nicht manuell bearbeitet, sondern mit den beiliegenden **Spotify-Tools** (siehe `Teil 1 README`) aufgebaut und gepflegt.
-   Für maximale Geschwindigkeit wird die Datenbank beim Start in den Arbeitsspeicher geladen und der Inhalt gehasht (SHA-256).

### Specials & Listening Phase

-   Das Skript hat eine eingebaute Erkennung für bekannte Meme-Songs (z.B. Rickroll, Crab Rave), um spezielle Reaktionen auszulösen.
-   Eine kurze **"Listening..."**-Phase nach einem Songwechsel verhindert, dass Finja sofort reagiert, was realistischer wirkt.

### Schutz vor Doppelstart (`.lock`-System)

-   Beim Start wird eine `finja_min_writer.lock`-Datei erstellt, die einen versehentlichen Doppelstart verhindert.
-   Wird das Skript mit `Strg + C` beendet, löscht es sich automatisch. Bei einem Absturz musst du es eventuell manuell entfernen:
    ```bash
    del finja_min_writer.lock
    ```

---

## 🚀 Starten & OBS-Einrichtung

1.  Stelle sicher, dass **Teil 1** (`start_nowplaying_windows.bat`) läuft und die `nowplaying.txt` erzeugt wird.
2.  Starte das Musikgehirn mit:
    ```bash
    run_finja.bat
    ```
3.  Füge in OBS eine **"Browser"**-Quelle hinzu.
4.  Wähle **"Lokale Datei"** und verweise auf die `NowPlaying_TFM_Bright.html` aus dem Ordner von **Teil 1**. Die HTML-Datei liest dann automatisch die von diesem Skript erzeugten `.txt`-Dateien.

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos.*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)