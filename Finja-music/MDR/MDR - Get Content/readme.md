# 📻 MDR – Get Content (Teil 1)

Dieses Modul ist der Inhalts-Lieferant für **MDR Sachsen-Anhalt**. Es zieht laufend die aktuell gespielten Songs aus verschiedenen Quellen (ICY, XML, HTML) und schreibt sie in eine `nowplaying.txt`, die dann von deinem Brain-Modul (Teil 2) gelesen wird.

> ⚡ Ohne dieses Modul gibt es keine neuen Songs für das Musikgehirn!

---

## 📁 Struktur

```plaintext
MDR - Get Content/
 ├─ mdr_nowplaying.py        ← Hauptskript: holt Titel+Artist
 ├─ start_mdr_nowplaying.bat   ← Startet das Skript unter Windows
 ├─ NowPlaying_MDR.html      ← Schönes OBS-Overlay (Browserquelle)
 ├─ nowplaying.txt           ← Ausgabe: "Titel — Artist"
 └─ now_source.txt           ← Ausgabe: von welcher Quelle (icy/xml/html)
```

---

## ⚙️ Wie es funktioniert

Das Skript `mdr_nowplaying.py` versucht nacheinander, den aktuellen Song von drei verschiedenen Quellen abzurufen, um die höchste Zuverlässigkeit zu gewährleisten:

1.  **ICY-Metadaten:** Direkte Abfrage vom MDR-Audiostream.
2.  **Offizielle XML-Titellisten:** Prüfung der von MDR bereitgestellten XML-Feeds.
3.  **HTML-Fallback:** Auslesen der Titel-Webseite als letzte Option.

Dabei wird automatisch geprüft:
-   Ob der Titel aktuell genug ist (nicht älter als 2 Minuten).
-   Ob es sich nicht um Werbung, Nachrichten oder Service-Meldungen handelt.
-   Ob derselbe Titel nicht mehrfach hintereinander geschrieben wird.

Das Ergebnis wird einheitlich als `Titel — Artist` in `nowplaying.txt` gespeichert, während die genutzte Quelle (`icy`, `xml` oder `html`) in `now_source.txt` vermerkt wird.

---

## 💻 Setup & Start

1.  Stelle sicher, dass du **Python 3.9+** installiert hast.
2.  **(Optional)** Du kannst die Quellen über Umgebungsvariablen anpassen:
    -   `MDR_STREAM_URL` – Direkter Stream (für ICY)
    -   `MDR_XML_URL` – XML-Titelliste
    -   `MDR_HTML_URL` – Web-Titelliste
3.  Starte das Skript einfach mit der beiliegenden Batch-Datei:
    ```bat
    start_mdr_nowplaying.bat
    ```

> 💡 Alternativ kannst du es auch direkt über Python starten: `python mdr_nowplaying.py`

---

## 🖥️ OBS einrichten

1.  Füge in OBS eine neue **"Browser"**-Quelle hinzu.
2.  Aktiviere die Option **"Lokale Datei"** und wähle die `NowPlaying_MDR.html` aus diesem Ordner.
3.  Stelle die Größe nach deinen Wünschen ein (z. B. auf 720 × 200 px).

Die HTML-Datei liest live die Informationen aus den folgenden Dateien:
-   `nowplaying.txt` (Titel + Artist)
-   `now_source.txt` (Herkunft der Info)
-   `../MUSIK/outputs/obs_genres.txt` (kommt später vom Brain)
-   `../MUSIK/outputs/obs_react.txt` (kommt später vom Brain)

---

## ⚡ Wichtige Hinweise

-   Das Skript läuft in einer Endlosschleife, bis du es im Terminal mit `Strg + C` stoppst.
-   Du kannst MDR parallel im Browser laufen lassen, damit es so aussieht, als würde dein Bot „live zuhören“. Das Skript funktioniert aber auch ohne.
-   Dieses Skript erstellt keine `.lock`-Datei. Es ist technisch möglich, mehrere Instanzen zu starten, dies wird aber nicht empfohlen.

---

## 📜 Lizenz

MIT © 2025 – J. Apps
*Gebaut mit 💖, Mate und einer Prise Chaos.*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)