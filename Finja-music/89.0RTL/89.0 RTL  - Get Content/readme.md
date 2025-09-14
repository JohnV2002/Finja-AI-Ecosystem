# 📡 98.0 RTL – Get Content (Teil 1)

Dieses Modul holt den aktuell laufenden Song von 98.0 RTL  
und schreibt ihn in `nowplaying.txt`.  

Die Datei wird später vom Musik-Brain (`MUSIK/`) eingelesen,  
um Genres, Reaktionen und Memories zu erzeugen. 💖

---

## ⚙️ Funktionsweise

- Nutzt das **Chrome DevTools Protocol (CDP)** über :contentReference[oaicite:1]{index=1}
- Liest direkt den Songtitel aus dem geöffneten 98.0 RTL-Tab
- Erkennt neue Songs nur, wenn sich Titel **stabil geändert** haben (Anti-Glitch)
- Schreibt den erkannten Song nach `nowplaying.txt`

💡 **Bonus:** Da ein echter 98.0 RTL-Browsertab geöffnet wird,  
kannst du dort auch direkt **Musik abspielen lassen**.  
So wirkt es, als ob Finja wirklich zuhört. 🥹🎶

---

## 🧠 Dateien

RTL/
├─ 98.0 RTL - Get Content/
│ ├─ rtl89_cdp_nowplaying.py ← Haupt-Script (liest Songtitel)
│ ├─ start_rtl_cdp.bat ← Startet das Script einfach per Doppelklick
│ └─ nowplaying.txt ← Ausgabedatei für den aktuellen Song
│
└─ Sodakiller_NowPlaying_RTL_Bright.html ← OBS Overlay für den Songtitel

yaml
Code kopieren

---

## 🖥️ Setup & Start

### 🅐 Einfache Methode (empfohlen)
1. **Chrome mit Remote-Debugging starten**  
   - Schließe alle Chrome-Fenster  
   - Starte Chrome mit:
     ```bash
     chrome.exe --remote-debugging-port=9222
     ```
2. **Webseite öffnen**  
   - Besuche [https://www.89.0rtl.de/](https://www.89.0rtl.de/)  
   - Starte dort den Radioplayer (Musik darf laufen)
3. **Crawler starten**  
   - Doppelklicke `start_rtl_cdp.bat`
   - Es erscheint eine Konsole mit `[rtl89-cdp] Schreibe nach ...`
   - Nach kurzer Zeit wird `nowplaying.txt` mit dem Songtitel beschrieben

---

## 🎨 OBS Overlay einrichten

1. In OBS → **Browserquelle hinzufügen**
2. „**Lokale Datei verwenden**“ aktivieren
3. Wähle `Sodakiller_NowPlaying_RTL_Bright.html`
4. Optional: `?x=40&y=40&maxw=800` an die URL hängen für Position/Größe

---

## 📌 Hinweise

- Script muss dauerhaft laufen, sonst bleibt `nowplaying.txt` leer
- Titel erscheinen teils mit Verzögerung (ca. 30–120 Sekunden)
- Diese Komponente erzeugt **nur den Songtitel**, kein Brain, keine Genres

---

## 🚨 Troubleshooting

- **Kein Song wird erkannt:**  
  Stelle sicher, dass Chrome mit `--remote-debugging-port=9222` gestartet wurde  
  und ein Tab mit der 98.0 RTL-Seite geöffnet ist.
- **Skript beendet sich sofort:**  
  Rechtsklick → „Mit Python öffnen“ starten, um Fehlerausgabe zu sehen.
- **Keine Musik hörbar:**  
  Lautstärke im Radioplayer aktivieren — optional, nicht nötig für Funktion,
  aber perfekt damit es **so wirkt, als ob Finja wirklich zuhört** 💖

---

## 📜 Lizenz

MIT © 2025 – J. Apps  
Built with 💖, Mate und einer Prise Chaos ✨

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)