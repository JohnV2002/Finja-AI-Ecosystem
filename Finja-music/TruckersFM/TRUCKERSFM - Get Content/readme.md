# ⚡ TruckersFM – GET CONTENT
*(Teil 1 des Finja-Music Systems)*

Holt den aktuell laufenden Song von [Truckers.fm](https://truckers.fm/listen) und schreibt ihn in die Datei `nowplaying.txt`. Diese Datei wird dann vom Musikgehirn (Teil 2) gelesen, um Genres und Reaktionen zu erzeugen.

> Ohne dieses Skript gibt es keine neuen Songs und somit auch keine neuen Inhalte für dein OBS-Overlay.

---

## 🧠 Wie es funktioniert

-   Das Skript öffnet regelmäßig die TruckersFM-Webseite im Hintergrund (als Crawler).
-   Es liest den aktuell gespielten Titel und den Interpreten aus dem HTML-Code der Seite.
-   Diese Informationen werden atomar (auf eine sichere Weise, die Schreib-/Lesefehler verhindert) in die `nowplaying.txt` geschrieben.
-   Es erkennt automatisch, wenn sich der Song ändert und triggert damit Teil 2 des Systems.

> ⚠️ **Es ist egal, ob du selbst gerade TruckersFM hörst oder nicht.** Solange der Crawler neue Titel auf der Webseite sieht, läuft der Prozess weiter.
>
> 💡 Wenn es „realistisch wirken“ soll, kannst du TruckersFM einfach im Browser öffnen und die Musik parallel laufen lassen.

---

## ⚙️ Dateien im Überblick

| Datei | Zweck |
| :--- | :--- |
| `truckersfm_nowplaying.py` | Der Haupt-Crawler, der die Song-Informationen holt. |
| `start_nowplaying_windows.bat` | Ein einfaches Startskript für Windows. |
| `NowPlaying_TFM_Bright.html` | Die HTML-Datei für das OBS-Overlay. |
| `nowplaying.txt` *(wird erzeugt)* | Enthält den zuletzt erkannten Song. |
| `outputs/` *(von Teil 2 genutzt)* | Der Ordner, in den das Musikgehirn seine Ergebnisse schreibt. |

---

## 🚀 Quick Start

1.  Stelle sicher, dass **Python 3.9+** auf deinem System installiert ist.
2.  Starte den Crawler, indem du die Datei `start_nowplaying_windows.bat` ausführst.
    -   Ein Terminalfenster öffnet sich und der Prozess läuft im Hintergrund.
    -   Du kannst die `nowplaying.txt` mit einem Editor öffnen, um zu prüfen, ob der aktuelle Titel und Interpret korrekt angezeigt werden.

### OBS-Einrichtung

1.  Füge in OBS eine neue **"Browser"**-Quelle hinzu.
2.  Aktiviere die Option **"Lokale Datei"**.
3.  Wähle die Datei `NowPlaying_TFM_Bright.html` aus diesem Ordner aus.
4.  Passe die Größe und Position nach deinen Wünschen an.

> **Tipp:** Du kannst das Aussehen des Overlays mit URL-Parametern anpassen. Hänge sie einfach an den Dateipfad in den Browser-Quellen-Einstellungen an:
> ```text
> .../NowPlaying_TFM_Bright.html#fs=32&w=760&ms=3000&label=TruckersFM
> ```

---

## 📌 Wichtige Hinweise

-   Dieses Skript läuft **vollständig lokal**. Es wird kein externer Server benötigt.
-   Das HTML-Overlay ist sicher für die Nutzung in OBS, da es keine externen Skripte lädt.
-   Denke daran: Dieses Skript erzeugt **nur** die `nowplaying.txt`. Die Anzeige von Genres und Finja-Reaktionen im Overlay funktioniert erst, wenn Teil 2 (das Musikgehirn) ebenfalls läuft.

---

## 🧯 Troubleshooting

-   **`nowplaying.txt` bleibt leer:**
    -   Überprüfe deine Internetverbindung.
    -   Stelle sicher, dass das `start_nowplaying_windows.bat`-Skript noch läuft.
-   **OBS zeigt nichts an:**
    -   Prüfe, ob der Pfad zur `NowPlaying_TFM_Bright.html`-Datei in den OBS-Einstellungen korrekt ist.
-   **Komische Zeichen in der `nowplaying.txt`:**
    -   Öffne die Datei in einem Editor, der UTF-8-Kodierung unterstützt (wie z.B. VS Code oder Notepad++).

---

## 📜 Lizenz

MIT © 2025 – J. Apps  
*Gebaut mit 💖, Mate und einer Prise Chaos.*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)