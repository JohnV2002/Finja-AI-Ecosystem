# Finja v2 — Vision/OCR Test-Roadmap

> Test-Sandbox. Simuliert was das **VPet** (Windows-Seite) spaeter tut:
> Screenshots + OCR + SQL lokal, schickt nur Daten ans Finja-Backend.
> Backend bleibt unbeeinflusst / Docker-tauglich. eyes.py (v1) faellt weg.

## Architektur-Entscheidungen (fix)
- Capture/OCR/SQL laufen auf der **VPet/App-Seite** (Windows), nicht im Backend.
- VPet schickt nur **Text-Daten** an Finja -> abschaltbar, modular, datensparsam.
- **Ebene 1 = Lesen** (OCR latin5fast, oft, billig) — Gewinner steht fest.
- **Ebene 2 = Sehen** (VLM, selten, "was passiert") — kommt neu.
- Aktives-Fenster-Erkennung via `pygetwindow` (aus eyes.py uebernommen).
- Speicherung: **SQLite + FTS5** (lokal, offline, durchsuchbar; wie OMI).

## Status Ebene 1 (Grund) — ✅ FERTIG
- RapidOCR Profil **latin5fast** (PP-OCRv5 det_mobile + latin rec, MIN_CONF 0.8)
- Umlaute korrekt, kein Halluzinieren, ~1.6s/Frame Anime-Subs.
- Vollbild-Test zeigte: liest Code/YT-Subs/Anime gut, ABER Vollbild = langsam
  (9s bei vollem IDE) + viel UI-Rauschen -> Loesung = aktives Fenster + Region.

---

## TODO (heute+)

### A. Test-Setup  ✅
- [x] Bleiben im Ordner finja-omni-test, mehrere Skripte.

### B. Aktive-Fenster-Capture + groesserer Real-World-Test  ✅ (mit Lehre)
- [x] `capture_active.py`: pygetwindow getActiveWindow() -> Region + Titel,
      speichert unskaliert + meta.json (frame -> {title, region}).
- [x] 50 Frames realworld2 getestet.
- **ERGEBNIS / wichtige Lehre:**
  - Aktive-Fenster-Crop bringt NICHTS bei maximierten Fenstern (alle 1920x1038
    = ~Vollbild). Speed sogar schlechter: Median 7.6s, Spitze 16s.
  - OCR-ganzer-Screen = SACKGASSE: 90% UI-Chrome-Muell, echter Inhalt ertrinkt.
  - **Goldfund 1:** Fenstertitel (getActiveWindow().title) = gratis Kontext-Signal
    ("...YouTube - Video-Titel", "...Antigravity IDE - datei.py", "Discord @Finja").
    ~0ms, kein OCR noetig.
  - **Goldfund 2:** OCRs Sweet Spot bleibt UNTERTITEL (untere Region, ~1s, sauber).

### B2. NEUE Architektur: Drei Signale (statt Vollbild-OCR)
```
1. FENSTERTITEL  -> gratis, IMMER   -> "welche App / welcher Inhalt"
2. OCR unten-Region -> billig, oft  -> "was wird gesagt" (Untertitel)
3. VLM ganzes Bild  -> teuer, selten -> "was passiert visuell"
```
- [x] Video-Erkennung per TITEL (nicht Geometrie!) -> IDE wird nie als Video verkannt.
- [x] Chrome-Crop: oberen Balken (BROWSER_TOP_CROP px) weg -> killt Lesezeichen-Muell
      + Privacy. meta.json bekommt content (video/ide/other) + browser_cropped.
- [x] Vollbild-Erkennung: Fenster deckt ganzen Monitor (1920x1080) = Vollbild,
      1920x1038 = nur maximiert. Signal in meta: fullscreen, wants_fullscreen.
- **PERSONALITY-FEATURE:** content==video + NICHT Vollbild -> `wants_fullscreen`
      -> Finja nervt suess "Papaaa mach GROSS, will mitschauen!" (statt still nur Titel).
      Aus Limitierung wird Charakterzug. Trigger-Signal kommt von VPet-Seite.
- [ ] Wenn Video+Vollbild: OCR nur unteren Streifen (Subs) statt ganzem Frame.
- **realworld3-Test (30 Frames) bestaetigt ALLES:** Klassifizierung 100% korrekt
  (IDE nie als Video), Chrome-Crop killt Lesezeichen-Muell, 💢-Nag feuert exakt
  bei video+nicht-Vollbild. Vollbild-Anime-Subs = ~1s sauber (Sweet Spot!).
  Median 7.6s -> 2.5s. Langsame Frames (IDE 14s, OpenRouter 8s) = ide/other,
  werden in Prod NICHT voll-OCRt. Kleine Tweaks offen: crop bei Vollbild
  unnoetig (harmlos f. Subs); fuer video+FS spaeter nur unteren Streifen OCRen.

### C. SQLite-Anbindung  ✅ FERTIG
- [x] `db.py`: SQLite + FTS5 (id, ts, content, app, window_title, text, phash,
      fullscreen, wants_fullscreen). FTS5 mit Praefix-Suche (dt. Komposita!).
- [x] Perceptual-Hash-Dedup (aHash 8x8) + Text-Dedup (gleicher Sub nicht doppelt).
- [x] `ocr.py`: wiederverwendbarer read_text(path, band=) mit latin5fast.
- [x] `verarbeite.py`: ROUTING — video->OCR(unterer Streifen bei Vollbild),
      ide/other->nur Titel (kein teures OCR! loest das 14s-IDE-Problem).
- [x] Test realworld3: 30 Frames -> 26 gespeichert, 4 Dups weg, 16 OCR / 14 Titel.
      Suche "Bibliothek"->"Bibliotheksdienst", "Discord"/"Finja"/"aniworld" alle ok.

### D. Ebene 2 bauen (Vision)  🔶 in Arbeit
- [x] `see.py`: VLM lokal (Ollama) + OpenRouter, beide Backends.
- [x] **Frame-Split (Johns Idee):** video+Vollbild -> VLM bekommt nur OBEREN Teil
      (Szene ohne Subs, SCENE_TOP=0.55), OCR den unteren. Downscale 1024.
- [x] Prompt: 1 Satz Szenenbeschreibung, KEIN Text/Subs lesen.
- [x] Lokal getestet (minicpm-v4.6, 25.8s): beschrieb Schulhof-Szene korrekt OHNE
      den Untertitel mitzulesen -> Split funktioniert!
- [x] .env-Loader in see.py (kein export/PowerShell-Stress, kein hardcoded Key).
- [x] OpenRouter-Vergleich: lokal minicpm-v4.6 (4.4s, generisch "Flur/Schueler")
      vs qwen3-vl-8b-instruct (9.3s, reich "pinkhaarige Figur gestikuliert zum Jungen").
      Cloud klar besser/lebendiger; qwen3-vl-INSTRUCT ist schnell (9s, nicht 1-5min
      wie die thinking-Variante!). ENTSCHEIDUNG: Tier konfigurierbar (lokal Default
      fuer Datenschutz, Cloud opt-in) wie v1.
- [x] Lokal-Modell-Entscheidung: minicpm-v4.6 (4.4s, brauchbar). qwen3-vl:2b lokal
      = TOT (57.5s + leere Antwort). Cloud qwen3-vl-8b-instruct = 3-9s, top Qualitaet.
- [x] Cloud-Kosten gerechnet: ~$0.12/Tag (~$3.60/Monat) bei alle-30s/8h, Obergrenze
      ~$0.25/Tag. Mit Szenenwechsel-Trigger viel weniger. Cloud = guenstig aber opt-in.
- [x] Subtitle-Leak in Szene-Crop akzeptiert (Vision faengt Sub eh mit, kein
      aufwendiges Splitten noetig).
- [ ] Trigger-Logik: sparsam (~30s / Szenenwechsel), vision-Eintrag in DB.

### E. Alles zusammen (parallel, stabil)  ✅ FERTIG
- [x] `capture.py` (reusable Capture-Modul) + `live.py` (Producer-Consumer-Threads).
- [x] Producer: alle 5s aktives Fenster + phash-Dedup -> Queue.
- [x] Consumer: Routing (video->OCR Sub-Streifen, ide/other->Titel) +
      sparsam Vision (alle 30s, nur video) -> SQLite (mit vision-Spalte).
- [x] ocr.read_text + see.prep_image nehmen jetzt PIL-Image (in-memory, kein Disk).
- [x] TESTLAUF: 85 DB-Eintraege, lief stabil. MAGIC MOMENT (Eintraege 72-83):
      Vision "two characters in a library" + OCR "Mir fiel ein, dass ich die
      Bibliothek noch nie genutzt habe" -> SEHEN + LESEN zusammen = vollstaendiges
      Bild. Genau das was OMNI/OMI NICHT konnten. Dedup/Routing/Nag/Vision alle ok.
      Befund f. F: Fenster-Video-OCR verrauscht (aber da feuert NAG->Vollbild=sauber).

### F. Realismus-Check
- [x] 3-Thread-Design (Producer / OCR-Worker / Vision-Worker) -> Vision blockiert
      OCR nie mehr. DB: ein conn + db_lock, check_same_thread=False, busy_timeout.
- [x] **REWIND-PRINZIP (Johns Idee, wie OMI):** jeder Frame traegt captured_at;
      Vision-Ergebnis wird mit AUFNAHME-Zeit gespeichert (nicht Antwort-Zeit).
      -> Vision-Lag wird HARMLOS: Beschreibung landet in der Timeline beim Moment
      des Screenshots, korreliert automatisch per Zeitstempel mit den OCR-Subs
      desselben Moments. Kein explizites Gruppieren noetig (waere over-eng.).
- [x] Modell-Warmup beim Start (OCR + Vision vorladen) -> kein Mid-Run-Stall.
      TICK 5s->3s (snappier). Laeuft jetzt fluessig nach ~30s Startup.
- [x] **KORRELATION BESTAETIGT (F-Kern):** Vision-Beschreibungen passen zeitlich +
      semantisch zu den OCR-Subs desselben Moments. Beweis: VISION @22:06:01
      "character holding a BOOK" + OCR "Vielleicht komme ich oefter in die
      BIBLIOTHEK / Empfiehl mir ein BUCH". Mehrere saubere Matches (Schule, Tuer,
      zwei Figuren reden). Lag (~3-5s Vision-Compute) durch captured_at unsichtbar.
      ide/other korrekt ohne OCR (nur Vision weiss was laeuft).

### G. LLM-Gefuehlstest
- [x] `quatsch.py` gebaut: zieht Timeline (Vision+OCR Zeitfenster) aus DB, filtert
      Fenster-Video-Rauschen + Einzelzeichen weg, baut lesbaren Bildschirm-Kontext,
      schickt an OpenRouter (Default google/gemini-3.5-flash) mit leichter Finja-
      Persona (Stand-in, NICHT echtes Backend). CHAT_MODEL via env umstellbar.
- [x] JOHN: erster Call lief, Finja charmant & in-character ("Ich mag deine
      Prioritaeten, Dad!"). Feel-Test bestanden.
- [x] `bubble.py`: schwebendes Overlay (tkinter, always-on-top ueber Vollbild-Video,
      pink umrandet, ziehbar, ESC/Rechtsklick schliesst). Zeigt Finjas Gedanken live
      alle 35s. Funktioniert sichtbar.
- [x] Feedback-Runde 1: Lag OK (Vision ⌀27s, OCR ⌀4.4s). ABER: Wiederholung (3-Min-
      Kontext ueberlappt) + greift konkrete Juwelen nicht (RAM-Halsband war im OCR!).
      FIX: build_context(since=) nur Neues + ask(avoid=) gegen Wdh. + Persona greift
      EIN konkretes Detail. Modell: gemma-4 zu schwach -> CHAT_MODEL hochsetzbar
      (gemini-3.5-flash / claude-haiku) via .env.
- [x] "0"-Bug gefunden: gemini-3.5-flash ist Reasoning-Modell, verballerte alle
      Token fuers Denken -> Antwort leer/abgeschnitten. FIX: reasoning effort=low
      (mandatory bei dem Modell, nicht abschaltbar) + max_tokens 700 + Fallback
      ohne reasoning fuer Nicht-Reasoning-Modelle. Greift jetzt konkrete Juwelen
      ("Halskette aus RAM-Riegeln? High-Tech-Schmuck, Dad!"). Kosten ~$0.004/Call
      (~$0.40/h @35s) -> Alternativen: claude-haiku (kein reasoning-tax) oder
      COMMENT_EVERY hoch. bubble.py loggt Gedanken in Konsole + finja_thoughts.txt.
- [ ] TTS optional spaeter.

### DB-Skalierung (geklaert)
- SQLite reicht JAHRE: ~622 Byte/Zeile -> ~680 MB/Jahr Heavy-Use. Limit 281 TB,
  schnell bis Millionen Zeilen. KEIN db_2/db_3, KEIN Postgres (waere Overkill fuer
  1 lokales VPet). Hebel: ts-Index (drin) + db.prune(keep_days) statt Sharding.
  WAL-Modus aktiv (Leser blockieren Schreiber nicht).

---
*Sowas baut sich nicht in 2 Sekunden — Schritt fuer Schritt. :3*
