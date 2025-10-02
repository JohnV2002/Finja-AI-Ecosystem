# 🧠 Memory & Filter – Roadmap

Eine Übersicht der geplanten Features für den Finja Memory-Service und das OpenWebUI-Plugin, sortiert nach Priorität.


## 🟠 Prio 0.6: Verbesserte Filter & Voice-Input

### Duplicate-Killer 2.0 (Fuzzy & Synonym-Erkennung)

-   **Normalisierung:** Vor dem Vergleich wird der Text bereinigt (Kleinschreibung, Leerzeichen entfernen, Emojis als Tokens, Zahlen maskieren).
-   **Prüfungen (vor dem Speichern):**
    1.  **Cosine-Similarity (via OpenAI):** Wenn der Score im Vergleich zu bestehenden Einträgen `≥ 0.92` ist → Duplikat, wird nicht gespeichert.
    2.  **Levenshtein-Distanz (Backup):** Wenn die textuelle Ähnlichkeit `≥ 0.90` ist → Duplikat.
-   **Konfiguration:** `DUP_COSINE=0.92`, `DUP_LEV=0.90`

### Erweiterter Content-Filter (Spam/Ein-Wort)

-   **Regeln:** Blockiert das Speichern, wenn die Erinnerung zu kurz ist (`MIN_CHARS=8`, `MIN_TOKENS=2`) oder verbotene Muster enthält (nur URLs, nur Emojis, Füllwörter wie "ok", "ja", "hi").

### Voice Memories (Basis-Implementierung)

-   **Server-Endpoint:** `POST /add_voice_memory` (akzeptiert eine Audiodatei und `user_id`).
-   **Verarbeitung:**
    1.  Transkribiert die Audiodatei (z.B. via Whisper STT) in Text.
    2.  Speichert die Audiodatei in einem Docker-Volume.
    3.  Speichert die Erinnerung mit dem Transkript als Text und dem Dateipfad in `meta.audio_url`.
-   **Spätere Erweiterung:** `GET /speak_memory?id=...` für eine Text-to-Speech-Ausgabe.

---

## 🟡 Prio 0.5: Backups & besseres User-Feedback

### Offline-Backup (Docker-integriert)

-   **Speicherort:** `/backups/YYYY-MM-DD/<user_id>.tar.gz` im Docker-Volume.
-   **Abruf:** Über einen neuen Endpoint `GET /download_backup?user_id&date=...` (später mit Passwortschutz).
-   **Aufbewahrung (Retention):** Eine Code-Konstante `BACKUP_RETENTION_DAYS = 14` in `memory-server.py` legt fest, wie lange Backups behalten werden.
-   **Endpunkte:** `POST /backup_all_now` (Admin) und eine erweiterte `POST /backup_now`-Funktion.

### "Test-Sandbox" (Sichtbare Status-Events)

-   Ein Schalter `show_status=True` im Plugin aktiviert sichtbare Statusmeldungen für den Nutzer.
-   **Beispiele:**
    -   `📝 Extrahiere potenzielle neue Erinnerungen...`
    -   `✅ 2 neue Erinnerungen hinzugefügt, 1 Duplikat übersprungen.`
    -   `⚠️ Konnte auf die Memory-Einstellungen nicht zugreifen – Vorgang abgebrochen.`

---

## 🟢 Prio 0.4: Erweiterte Memory-Funktionen

### Memory-Chaining (Graph/Cluster)

-   **Logik (nur im Plugin):** Beim Speichern einer neuen Erinnerung werden thematisch ähnliche "Nachbarn" (cosine ≥ 0.85) gefunden. Die IDs dieser Nachbarn werden in `meta.links` gespeichert. Dies passiert während der Voice-Analyse (TTS), um die Last zu reduzieren.

### Private Memory Lock (Verschlüsselung)

-   **Anwendung:** Gilt für die Memory-Bank `"Secrets"`.
-   **Umsetzung:** Eine optionale Passphrase pro `user_id` wird genutzt, um Erinnerungen **clientseitig im Plugin** (via AES-GCM) zu ver- und entschlüsseln. Der Server speichert nur den verschlüsselten Ciphertext und bleibt "dumm".

---

## 🔵 Prio 0.3: Struktur & Interaktion

### Memory-Banks (Kategorien)

-   **Struktur:** Erinnerungen werden in fachliche Schubladen sortiert (`General`, `Personal`, `Work`, `Jokes`, `Secrets`).
-   **Filter:** Der `/get_memories`-Endpoint wird um einen `bank`-Parameter erweitert.

### "Search+Ask"-Modus

-   **Nutzerfrage:** "Finja, was weißt du über XYZ?"
-   **Prozess:** Das Plugin erkennt die Absicht und ruft den neuen Endpoint `GET /search_ask?user_id&query=...` auf. Der Server gibt die Top-K relevantesten Erinnerungen zurück, die das Plugin zu einer Antwort zusammenfasst.

### Memory-Stats Dashboard (Basis)

-   **Server-Endpoint:** `GET /memory_stats` liefert Statistiken wie `hits`, `rejects`, `duplicates` und eine Aufschlüsselung nach `bank`. Dient als Grundlage für ein späteres Frontend.

---

## 🟣 Prio 0.2: Live-Updates & On-Demand-Zusammenfassungen

-   **WebSocket Push:** Ein `/ws`-Endpoint auf dem Server sendet Live-Events (`added`, `rejected`, `duplicate`, `backup_done`) an ein potenzielles Dashboard.
-   **Memory-Story Mode:** Auf die Frage "Erzähl mir, was du über mich weißt" ruft das Plugin `GET /story?user_id` auf, holt repräsentative Erinnerungen und lässt sie vom LLM zu einer Geschichte zusammenfassen.
-   **Plugin-API-Verbesserungen:** Einführung von API-Keys mit Scopes (read/write) und optionalen Webhooks.

---

## 🟤 Prio 0.1: Langzeit-Management & Visualisierung

-   **Memory-Expiry:** Ein optionales `expires_at`-Feld (Unix-Timestamp) ermöglicht das automatische Löschen veralteter Erinnerungen.
-   **Auto-Prune:** Löscht optional unwichtige Erinnerungen (niedriger Score, keine Zugriffe) nach N Tagen.
-   **Memory-Visualizer (Langzeitvision):** Ein Frontend, das auf den Statistik- und WebSocket-Endpunkten aufbaut und eine visuelle Darstellung der Erinnerungen ermöglicht.

---

## ✍️ Mini-Specs (API & Konfiguration)

### Erweiterte Felder (MemoryItem)
```python
bank: str = "General"
vector: Optional[List[float]] = None
expires_at: Optional[float] = None
meta: Dict[str, Any] = {}
```

### Neue Endpunkte
- `POST /add_voice_memory`
- `GET /search_ask`
- `GET /story`
- `GET /ws` (WebSocket)
- `POST /backup_all_now`
- `GET /download_backup`

### Wichtige Konfigurationsvariablen
- `EMBEDDINGS_MODEL=all-MiniLM-L6-v2`
- `MIN_RELEVANCE_ON_UPLOAD=0.45`
- `DUP_COSINE=0.92`
- `DUP_LEV=0.90`
- `MIN_CHARS=8`
- `MIN_TOKENS=2`
- `BACKUP_RETENTION_DAYS=14`
- `DEV_SANDBOX=0|1`