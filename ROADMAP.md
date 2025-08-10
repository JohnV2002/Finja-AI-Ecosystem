🧠 Memory & Filter – Roadmap (final nach Prio)
🔴 Prio 1.0
Lokaler Embedding‑Fallback beim Upload (Abruf bleibt OpenAI‑Ranking)
Warum: Wenn OpenAI down/timeout → trotzdem smart entscheiden, ob speichern sinnvoll ist.

Flow (Upload):

Versuche OpenAI‑Extract → wenn ok: normale Pipeline (Filter + Dedupe → Save).

Fallback: Lokale Embeddings (CPU, all-MiniLM-L6-v2) in OpenWebUI, nicht im Memory‑Server.

Embedding‑Relevanz prüfen ggü. aktueller User‑Historie (lokal gerankte Top‑K aus /get_memories).

Wenn cosine < MIN_RELEVANCE_ON_UPLOAD → nicht speichern.

User‑Feedback (Status/Events):

„⚠️ OpenAI nicht erreichbar – Fallback auf lokale Embeddings.“

„✅ Embedding meint: ‘suhsi’ relevant 0.95 – gespeichert.“

oder „❌ Embedding‑Score zu niedrig – nicht gespeichert. Bitte Admin kontaktieren.“

Dein Beispiel (umgesetzt):
User: „Hallo ich mag suhsi“ → OpenAI fail → Embedding sagt 0.95 → speichern + Status melden; wenn Save fail → sagen, dass Speichern nicht ging.

Schema‑Erweiterung (Erklärung):

bank: str = "General" → fachliche Schublade (General/Personal/Work/Jokes/Secrets).

vector: List[float] | None → nur lokal im Plugin verwenden (nicht im Server persistieren, wie du willst).

expires_at: float | None → optionales Ablaufdatum (Feature Prio 0.1).

meta: dict = {} → lose Metadaten (z. B. {"source":"voice","audio_url":"..."}). <- Audio auf externen server speichern>

Wichtig: Kein Embedding im Memory‑Server. Die Vektoren werden nur im OpenWebUI‑Plugin erzeugt/genutzt (und nicht gespeichert, außer du willst später Caching). <- caching okay aber da lokal emnedding ein fallback ist, ist es egal>


🟠 Prio 0.6
Duplicate‑Killer 2.0 (fuzzy + synonym)
Normalisierung: lowercase, trim, Mehrfach‑Spaces → 1, Emojis als Tokens, Zahlen maskieren.

Checks (Upload, vor Save):

Cosine-Similarity Score via OpenAI das selbe was wir machen wen wir /get_memory machen: ≥ 0.92 ⇒ Duplikat ⇒ skip

Beispiel: User: mag sushi, openai hmmm user mag sushi klingt wichtig, openai schickt server, server schaut -> user mag sushi, schon verhanden = nicht speichern , vorhanden speichern -> (Levenshtein‑Ratio: ≥ 0.90 ⇒ Duplikat ⇒ skip, in short) 

Konfig: DUP_COSINE=0.92, DUP_LEV=0.90.

Content‑Filter (Spam/Ein‑Wort) – erweitert
Regeln: MIN_CHARS=8, MIN_TOKENS=2, verbotene Muster (nur URLs/Emojis, „ok“, „ja“, „hi“…).

Voice Memories (STT/TTS) – Basis
Endpoints (Server):

POST /add_voice_memory (file + user_id) → Whisper‑STT → text + meta.audio_url.

GET /speak_memory?id=... → TTS (optional / später).

Storage: Audiodatei im Docker‑Volume; URL in meta.audio_url.

🟡 Prio 0.5
Offline‑Backup (Docker‑integriert)
Ablage: /backups/YYYY-MM-DD/<user_id>.tar.gz

Abruf:

Einfach: kleiner Download‑Endpoint (GET /download_backup?user_id&date=YYYY-MM-DD). <-- + User pass oder so siehe Prio 0.4>

Alternativ: per SFTP/FTP aufs Volume zugreifen (Doku hint).

Retention: In memory-server.py als Option (nicht ENV):
BACKUP_RETENTION_DAYS = 14 → kann per Datei‑Konstante/Kommentar an/aus geschaltet werden.

Endpoints: POST /backup_all_now (admin), /backup_now (erweitert: ZIP statt JSON).

„Test‑Sandbox“ = User‑Status‑Emitter (wie v3)
Genau dein Wunsch: sichtbare Status‑Events im Plugin:

„📝 Extracting potential new memories…“

„⏸ Adaptive Memory disabled – skipping.“

„⚠ Unable to access memory settings – aborting.“

Abschluss: „✅ Added X memories …“ / „⚠ skipped – filtered_or_duplicate …“

Schalter: show_status=True (Valve), kein Prod‑Spam.

🟢 Prio 0.4
Memory‑Chaining (Graph/Cluster)
Status: neu (nicht im Server).

How (Plugin‑seitig mit Embeddings):

Beim Upload: finde Nachbarn mit cosine ≥ 0.85 → schreibe meta.links=[ids] im Memory‑Text als Info (oder lege eine kleine lokale Mapping‑Datei im Plugin an). <-- Zu hoch , muss bei TTS gemacht werden>

Wöchentliches Clustering (Plugin‑Job; k‑means oder HDBSCAN) → meta.cluster_id (lokal gehalten). <-- zu hoch, muss mit bei tts gemacht werden>

API (Server, minimal):

GET /get_chain?id=... → Plugin resolved per lokalem Cache und gibt Liste zurück (Server kann Proxy spielen).

GET /get_cluster?cluster_id=... → dito.

Private Memory Lock (verschlüsselte Bank)
Scope: bank="Secrets".

How: Optional Passphrase je user_id → AES‑GCM clientseitig im Plugin verschlüsseln, Ciphertext speichern. Entschlüsselung nur, wenn Header X-User-Secret oder Plugin entschlüsselt vor Anzeige.

Server bleibt dumm (legt Byte‑Strings ab).

🔵 Prio 0.3
Memory‑Banks (General/Personal/Work/Jokes/Secrets)
Filter: /get_memories?bank=Work.

Plugin: Bank aus LLM‑JSON übernehmen, sonst General.

Search+Ask Modus
User: „Finja, was weißt du über XYZ?“

Server: GET /search_ask?user_id&query&k=5 → gibt Top‑Memories (rein Server)

Optional: Plugin macht darauf eine kurze LLM‑Antwort (oder offline: Stichpunkte).

Plugin: Intent erkennen → Endpoint aufrufen → hübsch antworten.

Memory‑Stats Dashboard (Basis)
Server erweitert: /memory_stats ergänzt Felder: hits, rejects, duplicates, by_bank.

Frontend (später): JSON‑Only zuerst; Visualizer kann später draufsetzen.

🟣 Prio 0.2
WebSocket Push (nur UI‑Events, kein Context‑Inject)
Zweck: Live‑Updates für Visualizer/Dashboard (added/rejected/duplicate/backup_done).

Server: GET /ws → Event‑Types: added, rejected, duplicate, backup_done.

Memory‑Story Mode
Nutzen: „Erzähl mir kurz, was du über mich weißt.“

Server/Plugin: GET /story?user_id&style=short|long

holt repräsentative Top‑Memories (per Cluster + Score)

LLM fasst zusammen (oder fallback extractive).

Kein Auto‑Inject; nur on‑demand Antwort.

Plugin‑API (klarer)
Ist: REST existiert.

Neu:

API‑Keys pro Client mit Scopes (read, write, banks:Secrets?)

Optionale Webhooks: /hooks/memory_added

Rate‑Limits per Key (simple Token‑Bucket im Server).

🟤 Prio 0.1
Memory‑Expiry (Option, default AUS)
Feld expires_at (Unix).

Cleanup‑Thread löscht nur wenn aktiviert (pro Bank/Scope einstellbar).

Auto‑Prune nach Wichtigkeit (Option, default AUS)
Regel: lösche Einträge mit score < X & last_hit == None nach N Tagen.

Nur opt‑in vom User.

Memory‑Visualizer (Langzeit)
Baut auf /ws + /memory_stats + /get_memories?bank=... auf.

Filter, Tag‑Cloud, Bank‑Tabs.

✍️ Mini‑Specs (API & Config)
Neue/erweiterte Felder (MemoryItem):

bank: str = "General"
vector: Optional[List[float]] = None
expires_at: Optional[float] = None
meta: Dict[str, Any] = {}
Neue/erweiterte Endpunkte:

POST /add_voice_memory (file + user_id) → transcript in text, meta.audio_url

GET /search_ask?user_id&query&k=5

GET /get_chain?id=..., GET /get_cluster?cluster_id=...

GET /story?user_id&style=short|long

GET /ws (WebSocket)

POST /backup_all_now (admin)

(optional) POST /encrypt_bank / POST /set_user_secret

Wichtige ENV/Valves:

EMBEDDINGS_MODEL=all-MiniLM-L6-v2
MIN_RELEVANCE_ON_UPLOAD=0.45
DUP_COSINE=0.92
DUP_LEV=0.90
MIN_CHARS=8
MIN_TOKENS=2
BACKUP_RETENTION_DAYS=14
DEV_SANDBOX=0|1