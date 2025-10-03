# 🧠 Memory & Filter – Roadmap

Eine Übersicht der verbleibenden Features für den Finja Memory-Service und das OpenWebUI-Plugin.

---

## 🟡 Prio 0.5: Backups & besseres User-Feedback

### Offline-Backup (Docker-integriert)

-   **Speicherort:** `/backups/YYYY-MM-DD/<user_id>.tar.gz` im Docker-Volume.
-   **Abruf:** Über einen neuen Endpoint `GET /download_backup?user_id&date=...` (später mit Passwortschutz weiterem). 
-   **DATEIN SICHER SPEICHERN:** (EXTREM WICHTIG  | Grundgedanke --> User id + fester Salt? Admin kann die User Id nicht sehen hat also nur den Salt. datein also jsons werden encrypted hoch geladen.)
-   **Aufbewahrung (Retention):** Eine Code-Konstante `BACKUP_RETENTION_DAYS = 14` in `memory-server.py` legt fest, wie lange Backups behalten werden.
-   **Endpunkte:** `POST /backup_all_now` (Admin) und eine erweiterte `POST /backup_now`-Funktion.

---

## 🟢 Prio 0.4: Erweiterte Memory-Funktionen

### Memory-Chaining (Graph/Cluster)

-   **Logik (nur im Plugin):** Beim Speichern einer neuen Erinnerung werden thematisch ähnliche "Nachbarn" (cosine ≥ 0.85) gefunden. Die IDs dieser Nachbarn werden in `meta.links` gespeichert.

### Private Memory Lock (Verschlüsselung)

-   **Anwendung:** Gilt für die Memory-Bank `"Secrets"`.
-   **Umsetzung:** Eine optionale Passphrase pro `user_id` wird genutzt, um Erinnerungen **clientseitig im Plugin** (via AES-GCM) zu ver- und entschlüsseln. Der Server speichert nur den verschlüsselten Ciphertext.

---

## 🔵 Prio 0.3: Struktur & Interaktion

### Memory-Banks (Kategorien)

-   **(Teilweise umgesetzt)** Der `/get_memories`-Endpoint muss noch um einen `bank`-Parameter erweitert werden, um nach Kategorien filtern zu können. Die Grundstruktur existiert bereits.

### "Search+Ask"-Modus

-   **Nutzerfrage:** "Finja, was weißt du über XYZ?"
-   **Prozess:** Das Plugin erkennt die Absicht und ruft den neuen Endpoint `GET /search_ask?user_id&query=...` auf. Der Server gibt die Top-K relevantesten Erinnerungen zurück, die das Plugin zu einer Antwort zusammenfasst.

### Memory-Stats Dashboard (Basis)

-   **(Teilweise umgesetzt)** Der `GET /memory_stats`-Endpoint existiert, muss aber um detailliertere Statistiken wie `hits`, `rejects`, `duplicates` und eine Aufschlüsselung nach `bank` erweitert werden.

---

## 🟣 Prio 0.2: Live-Updates & On-Demand-Zusammenfassungen

-   **WebSocket Push:** Ein `/ws`-Endpoint auf dem Server sendet Live-Events (`added`, `rejected`, `duplicate`, `backup_done`) an ein potenzielles Dashboard.
-   **Memory-Story Mode:** Auf die Frage "Erzähl mir, was du über mich weißt" ruft das Plugin `GET /story?user_id` auf, holt repräsentative Erinnerungen und lässt sie vom LLM zu einer Geschichte zusammenfassen.
-   **Plugin-API-Verbesserungen:** Einführung von API-Keys mit Scopes (read/write) und optionalen Webhooks.

---

## 🟤 Prio 0.1: Langzeit-Management & Visualisierung

-   **Memory-Expiry:** **(Teilweise umgesetzt)** Das `expires_at`-Feld existiert. Es fehlt die serverseitige Logik, die abgelaufene Erinnerungen automatisch löscht.
-   **Auto-Prune:** Löscht optional unwichtige Erinnerungen (niedriger Score, keine Zugriffe) nach N Tagen.
-   **Memory-Visualizer (Langzeitvision):** Ein Frontend, das auf den Statistik- und WebSocket-Endpunkten aufbaut.

---

## ✍️ Verbleibende Mini-Specs

### Erweiterte Felder (MemoryItem)
```python
vector: Optional[List[float]] = None # Für persistenten Vektor-Cache
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