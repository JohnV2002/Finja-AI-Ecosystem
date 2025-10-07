# 📡 89.0 RTL – Vollständiges Musikmodul

Dieses Modul sorgt dafür, dass Finja erkennt, welcher Song gerade auf **89.0 RTL** läuft, ihn in Genres einordnet, dynamische Reaktionen generiert und sich merkt, was sie davon hält. 🧠💖

> ⚡ **Wichtig:** Ohne dieses Modul sieht es für Finja aus, als ob keine Musik läuft. Du brauchst beide Teile, damit sie „zuhören“ kann!

---

## 📂 Verzeichnisstruktur

So ist der `RTL/`-Ordner aufgebaut:

```plaintext
RTL/
├─ 89.0 RTL - Get Content/
│   ├─ rtl89_cdp_nowplaying.py
│   ├─ start_rtl_cdp.bat
│   ├─ nowplaying.txt
│   ├─ outputs/
│   │   ├─ obs_genres.txt
│   │   └─ obs_react.txt
│   └─ Sodakiller_NowPlaying_RTL_Bright.html
│
└─ MUSIK/
    ├─ Memory/
    ├─ SongsDB/
    ├─ exports/
    ├─ ... (weitere Brain-Dateien)
    ├─ config_rtl.json
    └─ run_finja_rtl.bat
```

---

## 🛰️ Teil 1: Get Content – Songs abrufen

**Ziel:** Holt den aktuellen Song von der 89.0 RTL-Webseite und schreibt ihn in `nowplaying.txt`.

### Funktionsweise

-   Das Skript startet eine Instanz von Google Chrome mit aktiviertem Remote Debugging (CDP).
-   Es liest den Titel des aktuell gespielten Songs direkt aus der Webseiten-Struktur (DOM).
-   Änderungen werden nur geschrieben, wenn sich der Titel stabil geändert hat, um Flackern zu vermeiden.

>💡 **Bonus:** Da ein echter Browser-Tab offen ist, kannst du dort gleichzeitig die Musik abspielen lassen. So wirkt es für deine Zuschauer, als ob Finja „live zuhört“. 🥹💖

### Setup

1.  **Chrome mit Remote-Debugging starten:** Öffne ein Terminal und führe aus:
    ```shell
    chrome.exe --remote-debugging-port=9222
    ```
2.  **Seite öffnen:** Gehe im eben gestarteten Chrome-Fenster auf `https://www.89.0rtl.de/` und starte den Radioplayer.
3.  **Crawler starten:** Führe die Datei `start_rtl_cdp.bat` aus. Nach kurzer Zeit sollte der aktuelle Song in der `nowplaying.txt` erscheinen.

### OBS Overlay

-   Füge in OBS eine **"Browser"**-Quelle hinzu.
-   Aktiviere **"Lokale Datei verwenden"** und wähle die `Sodakiller_NowPlaying_RTL_Bright.html`.
-   Optional kannst du Parameter zur Positionierung anhängen: `?x=40&y=40&maxw=800`.

---

## 🧠 Teil 2: MUSIK/Brain – Songs verarbeiten

**Ziel:** Nimmt die Titel aus `nowplaying.txt` und generiert daraus Genre-Tags, dynamische Reaktionen und Langzeit-Erinnerungen.

### Setup-Varianten

Du hast zwei Möglichkeiten, das Musik-Brain für 89.0 RTL einzurichten.

#### 🅑 RTL nutzt das TruckersFM-Brain (Empfohlen 💖)

> **Empfehlung des Creators:** Nutze ein gemeinsames Brain für alle Quellen (TruckersFM, RTL, etc.). Das sorgt für ein konsistentes Verhalten und ein zentrales Gedächtnis.

1.  **Voraussetzung:** Richte zuerst das `TruckersFM/MUSIK/`-Verzeichnis vollständig und korrekt ein.
2.  **Konfiguration kopieren:** Kopiere die `config_min.json` von `TruckersFM/MUSIK/` nach `RTL/MUSIK/` und benenne sie in `config_rtl.json` um.
3.  **Pfade anpassen:** Öffne die neue `config_rtl.json` und ändere **nur die Pfade** so ab, dass sie auf die richtigen Ein- und Ausgabedateien für RTL sowie auf das zentrale TruckersFM-Brain verweisen:

    ```json
    {
      "input_path": "../89.0 RTL - Get Content/nowplaying.txt",
      "fixed_outputs": "../89.0 RTL - Get Content/outputs",
    
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
> -   89.0 RTL nutzt exakt dieselbe Wissensdatenbank, dasselbe Gedächtnis und dieselben Reaktionen wie TruckersFM.
> -   Neue Erinnerungen und Vorlieben wirken sich sofort auf alle angebundenen Musiksysteme aus.

#### 🅐 Nur RTL mit eigenem Brain (Nicht empfohlen)
Es ist möglich, ein komplett separates Brain nur für RTL zu betreiben, dies führt aber zu mehr Wartungsaufwand und inkonsistenten Daten. Eine Anleitung dafür findest du in der detaillierteren Dokumentation der anderen Module.

---

## ⚡ Starten & OBS-Integration

1.  **Starte Teil 1 (Crawler):** Führe `start_rtl_cdp.bat` aus.
2.  **Starte Teil 2 (Brain):** Führe `run_finja_rtl.bat` aus.
3.  **(Optional) Starte den Wiederholungszähler:** Führe `run_repeat_rtl.bat` aus.
4.  **Richte OBS ein:**
    -   **Browserquelle:** `89.0 RTL - Get Content/Sodakiller_NowPlaying_RTL_Bright.html`
    -   **Textquellen (Aus Datei lesen):**
        -   `89.0 RTL - Get Content/outputs/obs_genres.txt`
        -   `89.0 RTL - Get Content/outputs/obs_react.txt`

---

## 📝 Wichtige Hinweise

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