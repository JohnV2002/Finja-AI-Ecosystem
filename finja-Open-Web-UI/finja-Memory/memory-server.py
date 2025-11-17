# memory_service.py

"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory – Memory Server
  Version: 1.3.2
  Author:  John (J. Apps / Sodakiller1)
  License: Apache License 2.0 (c) 2025 J. Apps
  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2
  Author Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Serverseitiger Speicher für das "Adaptive Memory" OpenWebUI-Plugin.
  • Speichert Erinnerungen getrennt nach User-ID in portablen JSON-Dateien.
  • Intelligenter RAM-Cache: Hält aktive User für blitzschnelle Lesezugriffe
    im Arbeitsspeicher und räumt sich nach Inaktivität selbst auf.
  • Voice-Memory-Schnittstellen: Bietet Endpunkte zur Annahme von User-Sprachdateien
    (STT) und zum Caching von KI-Sprachausgaben (TTS).
  • Robuste REST-API auf Basis von FastAPI für alle CRUD-Operationen.
  • Konfiguration über eine .env-Datei für mehr Sicherheit.
----------------------------------------------------------------------

----------------------------------------------------------------------
 Updates 1.3.2:
 ---------------------------------------------------------------------
  + **Security Hardening (Path Traversal):** Kritische Sicherheitsverbesserungen in
    den Endpunkten `/delete_user_memories` und `/add_voice_memory` implementiert.
    Zusätzliche Checks (Empty-String & Path Canonicalization) verhindern nun
    potenzielle Path-Traversal-Angriffe oder das versehentliche Löschen von
    Hauptverzeichnissen durch manipulierte User-IDs.
  + **Dependency Security Fix:** `starlette` in der `requirements.txt` auf
    Version 0.50.0 aktualisiert, um eine bekannte Sicherheitslücke (Vulnerability)
    in der älteren Version zu schließen.

 Updates 1.3.1:
 ---------------------------------------------------------------------
  + **Fix Auth Log Fehler:** Ein Check in `auth_check` hinzugefügt, um
    einen `TypeError` beim Loggen von unautorisierten Zugriffen zu verhindern,
    wenn der `X-API-Key` Header komplett fehlt (`key` ist None).

 Updates 1.3.0:
 ---------------------------------------------------------------------
  + **Admin Backup Endpunkt:** `POST /backup_all_now` Endpunkt hinzugefügt.
    - Speichert alle aktuellen In-Memory-Daten auf die Festplatte.
    - Kopiert alle Benutzer-Memory-JSON-Dateien in einen Unterordner mit Zeitstempel
      innerhalb des neuen `backups`-Verzeichnisses.
  + **User Backup Platzhalter:** `POST /backup_now` Endpunkt hinzugefügt.
    - Akzeptiert eine User-ID.
    - Führt Authentifizierung durch.
    - Gibt derzeit eine einfache Bestätigungsnachricht zurück (Platzhalter).
  + **Backup Verzeichnis:** `BACKUP_DIR` Konstante und Verzeichniserstellung
    beim Start hinzugefügt.

 Updates 1.2.0:
 ---------------------------------------------------------------------
  + **Grundgerüst für User-Input (STT):** Neuer Endpunkt `/add_voice_memory`
    implementiert. Er kann Audiodateien annehmen, speichern und eine
    Platzhalter-Erinnerung mit dem Dateipfad erstellen.
  + **Grundgerüst für KI-Output (TTS-Cache):** Neuer Endpunkt `/get_or_create_speech`
    implementiert. Er prüft, ob eine Sprachausgabe für einen Text bereits
    existiert und simuliert die Neuerstellung, falls nicht.

 Updates 1.1.0:
 ---------------------------------------------------------------------
  + **Intelligenter RAM-Cache:** Der Server lädt User-Daten jetzt nur noch
    einmalig von der Festplatte und bedient alle folgenden Anfragen aus dem
    schnellen Arbeitsspeicher.
  + **Automatische Speicherbereinigung:** Ein neuer Hintergrund-Thread
    überwacht die Aktivität und entfernt inaktive User aus dem RAM.
  + **Stabilitäts-Fixes:** Logikfehler im Zusammenhang mit dem neuen
    Cache-System beim Server-Start und bei manuellen Backups behoben.
----------------------------------------------------------------------

----------------------------------------------------------------------
 Roadmap:
 ---------------------------------------------------------------------
  • Nutzerverwaltung & Zugriffskontrolle
  • Optionale Datenbank-Backends (ChromaDB, Redis, SQLite)
  • API-Authentifizierung (Token-System)
  • Memory-Visualizer (Admin-Oberfläche)
  • Automatische Memory-Archivierung & -Pruning
  • Erweiterte Logging-Funktionen

----------------------------------------------------------------------
 License Notice:
 ---------------------------------------------------------------------
  Dieses Projekt basiert auf der Arbeit von gramanoid (diligent_chooser)
  und wurde unter Beibehaltung der Apache License 2.0 veröffentlicht.
  Alle Rechte an den Änderungen © 2025 J. Apps

======================================================================
"""


from fastapi import FastAPI, HTTPException, Body, Request, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid, time, json, threading, os, hashlib, shutil # Added shutil
from dotenv import load_dotenv
import aiofiles
from datetime import datetime # Added datetime for backup timestamp

# Starte FastAPI-App
app = FastAPI(title="Memory Service")

# Lade .env Datei
load_dotenv()

# Hole API Key aus Umgebungsvariable
API_KEY = os.getenv("MEMORY_API_KEY")

if not API_KEY:
    raise ValueError("MEMORY_API_KEY environment variable is required!")

# Maximale Anzahl an Erinnerungen, die im RAM pro User gehalten werden
MAX_RAM_MEMORIES = 5000

# Alle wie viele Sekunden ein automatisches Backup gemacht wird (600 = 10 Minuten)
BACKUP_INTERVAL = 600
CACHE_TIMEOUT = 600

# Ordner-Definitionen
USER_MEMORY_DIR = "user_memories"
USER_AUDIO_DIR = "user_audio"
TTS_CACHE_DIR = "tts_cache"
BACKUP_DIR = "backups" # New backup directory

# Erstelle alle notwendigen Ordner beim Start
os.makedirs(USER_MEMORY_DIR, exist_ok=True)
os.makedirs(USER_AUDIO_DIR, exist_ok=True)
os.makedirs(TTS_CACHE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True) # Create backup dir

# Speichert, wann ein User-Cache zuletzt verwendet wurde (für die automatische Bereinigung)
cache_last_accessed: Dict[str, float] = {}

# -------------------------
# Daten-Modelle (Schemas)
# -------------------------
class MemoryItem(BaseModel):
    id: str = ""
    # snyk:ignore:python/UseOfHardcodedCredentials
    # Reason: User ID is dynamically retrieved from Open-Web-UI at runtime
    user_id: str = "default"
    text: str
    timestamp: float = 0
    bank: Optional[str] = "General"
    expires_at: Optional[float] = None
    meta: Optional[Dict[str, Any]] = {}

class UserAction(BaseModel):
    user_id: str

class PruneAction(BaseModel):
    user_id: str
    amount: int

# Speicherstruktur im RAM (alle aktiven Erinnerungen)
user_memories: Dict[str, List[MemoryItem]] = {}

class TTSRequest(BaseModel):
    text: str

# -------------------------
# Hilfsfunktionen
# -------------------------

def memory_file(user_id):
    """Gibt den Pfad zur Speicherdatei für einen bestimmten User zurück"""
    # Ensure user_id is filename-safe (basic sanitation)
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ('-', '_')).rstrip()
    if not safe_user_id: safe_user_id = "invalid_user_id"
    return os.path.join(USER_MEMORY_DIR, f"{safe_user_id}_memory.json")

def save_to_disk(user_id):
    """Speichert die Erinnerungen eines Benutzers auf die Festplatte"""
    filepath = memory_file(user_id)
    if user_id in user_memories:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                # Use Pydantic's model_dump for serialization
                json.dump([m.model_dump() for m in user_memories[user_id]], f, ensure_ascii=False, indent=2)
            print(f"INFO:    Saved memories for user {user_id} to {filepath}")
        except Exception as e:
            print(f"ERROR:   Failed to save memories for user {user_id} to {filepath}: {e}")
    #else:
        # Optionally log if user_id not in memory (might happen during cleanup)
        # print(f"DEBUG:   User {user_id} not in RAM cache, skipping save_to_disk.")


def load_from_disk(user_id):
    """Lädt die Erinnerungen eines Benutzers von der Festplatte in den RAM"""
    filepath = memory_file(user_id)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            items = json.load(f)
            # Validate items structure before creating MemoryItem objects
            validated_items = []
            for entry in items:
                if isinstance(entry, dict) and "text" in entry: # Basic check
                    # Ensure timestamp exists and is float, default if needed
                    entry['timestamp'] = float(entry.get('timestamp', 0.0))
                    validated_items.append(MemoryItem(**entry))
                else:
                    print(f"WARN:    Skipping invalid entry in {filepath}: {entry}")
            user_memories[user_id] = validated_items
            print(f"INFO:    Loaded {len(validated_items)} memories for user {user_id} from {filepath}")
    except FileNotFoundError:
        print(f"INFO:    No memory file found for user {user_id}, starting fresh.")
        user_memories[user_id] = []
    except json.JSONDecodeError as e:
        print(f"ERROR:   Failed to decode JSON from {filepath}: {e}. Starting fresh for user {user_id}.")
        user_memories[user_id] = []
    except Exception as e:
        print(f"ERROR:   Failed to load memories for user {user_id} from {filepath}: {e}")
        user_memories[user_id] = [] # Fallback to empty list on other errors

def auto_backup_thread_func():
    """Automatisches Backup aller User-Erinnerungen im RAM in regelmäßigen Abständen"""
    while True:
        time.sleep(BACKUP_INTERVAL)
        print(f"INFO:    Starting periodic auto-save of {len(user_memories)} users in RAM...")
        # Create a copy of keys to avoid runtime errors if dict changes
        user_ids_to_save = list(user_memories.keys())
        saved_count = 0
        for uid in user_ids_to_save:
            # Check again if user is still in memory before saving
            if uid in user_memories:
                save_to_disk(uid)
                saved_count += 1
        print(f"INFO:    Auto-save complete for {saved_count} users.")


def cleanup_inactive_caches_thread_func():
    """Entfernt in regelmäßigen Abständen inaktive User-Caches aus dem RAM."""
    while True:
        time.sleep(60) # Check every minute
        now = time.time()
        inactive_users = [
            uid for uid, last_time in cache_last_accessed.items()
            if now - last_time > CACHE_TIMEOUT
        ]

        if inactive_users:
            print(f"INFO:    Found {len(inactive_users)} inactive user(s) to clean from RAM-Cache.")
            for uid in inactive_users:
                # Save final state before evicting
                save_to_disk(uid)
                # Remove from RAM caches
                if uid in user_memories: del user_memories[uid]
                if uid in cache_last_accessed: del cache_last_accessed[uid]
                print(f"INFO:    Evicted cache for user: {uid}")


# -------------------------
# Startup-Events
# -------------------------

@app.on_event("startup")
def startup():
    """Beim Start: Gespeicherte Erinnerungen laden & Hintergrund-Threads starten"""
    print("INFO:    Server startup initiated...")
    # No initial load here, lazy loading on first access per user

    # Start the Auto-Save Thread
    auto_save_thread = threading.Thread(target=auto_backup_thread_func, daemon=True)
    auto_save_thread.start()
    print("INFO:    Auto-save thread started.")

    # Start the Cache-Cleanup Thread
    cleanup_thread = threading.Thread(target=cleanup_inactive_caches_thread_func, daemon=True)
    cleanup_thread.start()
    print("INFO:    Cache cleanup thread started.")
    print("INFO:    Server startup complete.")


# -------------------------
# Authentifizierung
# -------------------------
def auth_check(request: Request):
    """Überprüft, ob der API-Key im Header vorhanden und gültig ist"""
    key = request.headers.get("X-API-Key")
    if not key or key != API_KEY:
        # FIX: Check if key is not None before slicing
        key_display = f"{key[:5]}..." if key else "None"
        print(f"WARN:    Unauthorized access attempt. Provided key: {key_display}") # Log masked key or "None"
        raise HTTPException(status_code=401, detail="Missing or invalid API Key.")


# -------------------------
# API-Endpunkte
# -------------------------

@app.post("/add_memory")
async def add_memory(request: Request, mem: MemoryItem = Body(...)):
    """Fügt eine einzelne Erinnerung hinzu und nutzt den RAM-Cache."""
    auth_check(request)
    uid = mem.user_id or "default"

    if uid not in user_memories: load_from_disk(uid)
    cache_last_accessed[uid] = time.time()

    mem.id = str(uuid.uuid4())
    mem.timestamp = time.time()
    memories = user_memories.get(uid, [])
    # Prune if exceeding MAX_RAM_MEMORIES
    if len(memories) >= MAX_RAM_MEMORIES:
        # Simple FIFO pruning for RAM cache
        memories.pop(0)
    memories.append(mem)
    user_memories[uid] = memories

    # Optional: Trigger immediate save or rely on auto-save
    # save_to_disk(uid)
    return {"status": "added", "id": mem.id}

@app.post("/add_memories")
def add_memories(request: Request, batch: List[MemoryItem] = Body(...)):
    """Fügt eine Liste von Erinnerungen hinzu und nutzt den RAM-Cache."""
    auth_check(request)
    if not batch: return {"status": "no_data"}
    # Assume all items in batch are for the same user
    uid = batch[0].user_id or "default"

    if uid not in user_memories: load_from_disk(uid)
    cache_last_accessed[uid] = time.time()

    memories = user_memories.get(uid, [])
    added_count = 0
    for mem in batch:
        mem.id = str(uuid.uuid4())
        mem.timestamp = time.time()
        memories.append(mem)
        added_count += 1

    # Prune if exceeding limit after adding batch
    if len(memories) > MAX_RAM_MEMORIES:
        memories = memories[-MAX_RAM_MEMORIES:] # Keep only the newest MAX_RAM_MEMORIES
    user_memories[uid] = memories

    # Optional: Trigger immediate save or rely on auto-save
    # save_to_disk(uid)
    return {"status": "batch_added", "added": added_count, "total_in_ram": len(memories)}

@app.get("/get_memories")
def get_memories(request: Request, user_id: Optional[str] = None, query: Optional[str] = None, limit: int = 50):
    """Erinnerungen abrufen, bevorzugt aus dem schnellen RAM-Cache."""
    auth_check(request)
    uid = user_id or "default"

    if uid not in user_memories: load_from_disk(uid)
    cache_last_accessed[uid] = time.time()

    memories = user_memories.get(uid, [])
    filtered = memories
    if query:
        try:
            # Case-insensitive search
            query_lower = query.lower()
            filtered = [m for m in memories if query_lower in m.text.lower()]
        except Exception as e:
            print(f"ERROR:   Error during query filtering for user {uid}: {e}")
            # Return unfiltered list or raise error? Returning unfiltered for now.
            filtered = memories

    # Return the latest 'limit' matching memories
    return filtered[-limit:]

@app.get("/memory_stats")
def memory_stats(request: Request, user_id: Optional[str] = None):
    """Statistiken über die Erinnerungen eines Benutzers aus dem RAM-Cache."""
    auth_check(request)
    uid = user_id or "default"

    if uid not in user_memories: load_from_disk(uid)
    cache_last_accessed[uid] = time.time()

    filepath = memory_file(uid)
    file_exists = os.path.exists(filepath)
    # Get actual file size if it exists
    file_size = os.path.getsize(filepath) if file_exists else 0

    return {
        "user_id": uid,
        "memories_in_ram": len(user_memories.get(uid, [])),
        "max_ram_capacity": MAX_RAM_MEMORIES,
        "memory_file_path": filepath,
        "memory_file_exists": file_exists,
        "memory_file_size_bytes": file_size,
        "last_accessed_ram": cache_last_accessed.get(uid) # Unix timestamp
    }

@app.post("/prune")
def prune(request: Request, data: PruneAction = Body(...)):
    """Älteste Einträge löschen und dabei den RAM-Cache nutzen."""
    # Note: This only prunes the RAM cache. File is overwritten on next save.
    auth_check(request)
    uid = data.user_id

    if uid not in user_memories: load_from_disk(uid) # Load if not in RAM
    cache_last_accessed[uid] = time.time()

    memories = user_memories.get(uid, [])
    original_count = len(memories)
    amount_to_prune = min(data.amount, original_count) # Don't prune more than available

    if amount_to_prune > 0:
        user_memories[uid] = memories[amount_to_prune:]
        pruned_count = amount_to_prune
    else:
        pruned_count = 0

    remaining_count = len(user_memories.get(uid, []))
    # Optional: Trigger immediate save after pruning
    # save_to_disk(uid)
    return {"status": "pruned_ram", "pruned": pruned_count, "remaining_in_ram": remaining_count}

# --- Original /backup_now (User specific, renamed for clarity) ---
# This endpoint now handles the admin full backup.
@app.post("/backup_all_now")
def backup_all_now(request: Request):
    """
    Admin Endpoint: Triggers an immediate backup of all user memory files.
    Saves current RAM state to disk first, then copies files to a timestamped backup folder.
    """
    auth_check(request) # Ensure only authorized access
    print("INFO:    Admin backup requested: /backup_all_now")

    # 1. Save all current RAM caches to disk
    print("INFO:    Saving all active RAM caches to disk before backup...")
    user_ids_in_ram = list(user_memories.keys())
    saved_count = 0
    for uid in user_ids_in_ram:
        if uid in user_memories: # Check again in case cleanup ran
            save_to_disk(uid)
            saved_count +=1
    print(f"INFO:    Saved data for {saved_count} users from RAM.")

    # 2. Create timestamped backup directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_subdir = os.path.join(BACKUP_DIR, timestamp)
    try:
        os.makedirs(backup_subdir, exist_ok=True)
        print(f"INFO:    Created backup directory: {backup_subdir}")
    except Exception as e:
        print(f"ERROR:   Failed to create backup directory {backup_subdir}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create backup directory: {e}")

    # 3. Copy all memory files to the backup directory
    copied_files_count = 0
    errors = []
    try:
        for filename in os.listdir(USER_MEMORY_DIR):
            if filename.endswith("_memory.json"):
                source_path = os.path.join(USER_MEMORY_DIR, filename)
                dest_path = os.path.join(backup_subdir, filename)
                try:
                    shutil.copy2(source_path, dest_path) # copy2 preserves metadata
                    copied_files_count += 1
                except Exception as copy_e:
                    error_msg = f"Failed to copy {filename}: {copy_e}"
                    print(f"ERROR:   {error_msg}")
                    errors.append(error_msg)
        print(f"INFO:    Copied {copied_files_count} memory files to backup directory.")
    except Exception as e:
        print(f"ERROR:   Failed during file listing or copying process: {e}")
        # Report partial success/failure
        detail = f"Backup partially failed after copying {copied_files_count} files. Error: {e}"
        if errors: detail += f" Specific copy errors: {'; '.join(errors)}"
        raise HTTPException(status_code=500, detail=detail)

    status_message = f"Backup complete. Copied {copied_files_count} memory files to {backup_subdir}."
    if errors:
        status_message += f" Encountered {len(errors)} copy errors."

    return {"status": "backup_done", "details": status_message, "backup_location": backup_subdir}

# --- Placeholder for User-Triggered Backup ---
@app.post("/backup_now")
async def backup_now_placeholder(request: Request, data: UserAction = Body(...)):
    """
    Placeholder Endpoint for User Backup Request.
    Currently only acknowledges the request.
    """
    auth_check(request)
    uid = data.user_id
    print(f"INFO:    Received user backup request for user: {uid} (Placeholder - no action taken yet).")
    # --- Future Logic ---
    # 1. Save this specific user's RAM to disk: save_to_disk(uid)
    # 2. Create a specific backup file/archive for this user (e.g., in their own subfolder or a single archive)
    # 3. Store metadata about the backup (timestamp, location)
    # 4. Return information about the backup (e.g., file path or ID) - TBD how plugin receives this
    # -------------------
    return {"status": "backup_request_received", "user_id": uid, "details": "User backup functionality is not yet fully implemented."}


def transcribe_audio_dummy(filepath: str) -> str:
    """PLATZHALTER-FUNKTION: Simuliert die Transkription."""
    filename = os.path.basename(filepath)
    print(f"INFO:    [DUMMY] Transcribing '{filename}'...")
    time.sleep(0.5) # Shorter delay
    return f"Transkript: {filename}"

@app.post("/add_voice_memory")
async def add_voice_memory(request: Request, user_id: str = Form(...), file: UploadFile = File(...)):
    """Nimmt Audio entgegen, speichert es, simuliert Transkription."""
    auth_check(request)
    uid = user_id or "default"
    
    # 1. Sanitize input
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ('-', '_')).strip()
    
    # 2. CHECK: Verhindere leere Strings (Verhindert schreiben ins Root-Verzeichnis)
    if not safe_uid:
        print(f"WARN:    Invalid user_id for audio upload: '{uid}'")
        raise HTTPException(status_code=400, detail="Invalid User ID.")

    # 3. Pfad sicher zusammenbauen
    user_audio_subdir = os.path.join(USER_AUDIO_DIR, safe_uid)

    # 4. PARANOID CHECK (Snyk-Friendly): Path Canonicalization
    # Sicherstellen, dass der Zielordner wirklich innerhalb von USER_AUDIO_DIR liegt
    try:
        real_target_path = os.path.realpath(user_audio_subdir)
        real_base_path = os.path.realpath(USER_AUDIO_DIR)
        if not real_target_path.startswith(real_base_path):
             print(f"CRITICAL: Path Traversal attempt in audio upload! {real_target_path}")
             raise HTTPException(status_code=400, detail="Security check failed.")
    except Exception as e:
        print(f"ERROR:   Path security check failed: {e}")
        raise HTTPException(status_code=500, detail="Internal security check error.")

    # Ab hier ist alles sicher -> Ordner erstellen
    os.makedirs(user_audio_subdir, exist_ok=True) 

    file_extension = os.path.splitext(file.filename or "audio.unk")[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    save_path = os.path.join(user_audio_subdir, unique_filename)

    try:
        async with aiofiles.open(save_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024): await out_file.write(content)
        print(f"INFO:    Saved voice memory to {save_path}")
    except Exception as e: 
        raise HTTPException(status_code=500, detail=f"Could not save audio file: {e}")

    transcript = transcribe_audio_dummy(save_path)
    voice_memory = MemoryItem(user_id=uid, text=transcript, meta={"source": "voice_input", "audio_path": save_path}) 

    # Use the existing add_memory endpoint logic
    await add_memory(request, voice_memory)

    return {"status": "voice_memory_added", "transcript": transcript, "audio_path": save_path}

def generate_speech_dummy(text: str, filepath: str) -> bool:
    """PLATZHALTER-FUNKTION: Simuliert TTS."""
    print(f"INFO:    [DUMMY] Generating speech for: '{text[:30]}...'")
    time.sleep(0.5) # Shorter delay
    try:
        with open(filepath, 'w') as f: f.write(f"Dummy audio for: {text}")
        print(f"INFO:    [DUMMY] Saved dummy speech to {filepath}")
        return True
    except Exception as e:
        print(f"ERROR:   [DUMMY] Failed to save dummy speech file {filepath}: {e}")
        return False

@app.post("/get_or_create_speech")
async def get_or_create_speech(request: Request, data: TTSRequest = Body(...)):
    """Prüft TTS Cache, simuliert Generierung."""
    auth_check(request)
    text_to_speak = data.text.strip()
    if not text_to_speak: raise HTTPException(status_code=400, detail="Text cannot be empty.")

    text_hash = hashlib.sha256(text_to_speak.encode('utf-8')).hexdigest()
    filename = f"{text_hash}.mp3" # Assume mp3
    filepath = os.path.join(TTS_CACHE_DIR, filename)

    if os.path.exists(filepath):
        print(f"INFO:    TTS Cache HIT for: '{text_to_speak[:30]}...'")
        return {"status": "cache_hit", "audio_path": filepath} # Use path

    print(f"INFO:    TTS Cache MISS for: '{text_to_speak[:30]}...'. Generating...")
    success = generate_speech_dummy(text_to_speak, filepath)

    if success: return {"status": "created", "audio_path": filepath} # Use path
    else: raise HTTPException(status_code=500, detail="Failed to generate speech file.")

@app.post("/delete_user_memories")
def delete_user_memories(request: Request, data: UserAction = Body(...)):
    """Löscht ALLE Daten für einen User (JSON, Audio, RAM)."""
    auth_check(request)
    uid = data.user_id
    
    # 1. Input Sanitization: Entferne alles außer Alphanumerik, Bindestrich, Unterstrich
    # .strip() entfernt Leerzeichen am Anfang/Ende
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ('-', '_')).strip()
    
    # 2. CRITICAL SECURITY CHECK: Verhindere leere Strings!
    # Wenn safe_uid leer ist (z.B. weil User nur "..." gesendet hat), brechen wir sofort ab.
    if not safe_uid:
        print(f"WARN:    Invalid user_id provided for deletion: '{uid}' -> resulted in empty safe_uid.")
        raise HTTPException(status_code=400, detail="Invalid User ID for deletion.")

    print(f"WARN:    Deletion requested for user '{uid}' (safe: '{safe_uid}')")

    filepath = memory_file(uid) # Nutzt intern auch safe_uid Logik, ist hier okay
    
    # 3. Pfad sicher zusammenbauen
    user_audio_subdir = os.path.join(USER_AUDIO_DIR, safe_uid)

    # 4. PARANOID CHECK (Snyk-Friendly): Path Canonicalization
    # Wir lösen den Pfad komplett auf und prüfen, ob er wirklich noch im USER_AUDIO_DIR liegt.
    # Das verhindert theoretische "../"-Angriffe komplett.
    try:
        real_audio_path = os.path.realpath(user_audio_subdir)
        real_base_path = os.path.realpath(USER_AUDIO_DIR)
        if not real_audio_path.startswith(real_base_path):
             print(f"CRITICAL: Path Traversal attempt detected! {real_audio_path}")
             raise HTTPException(status_code=400, detail="Security check failed.")
    except Exception as e:
        print(f"ERROR:    Path security check failed: {e}")
        raise HTTPException(status_code=500, detail="Internal security check error.")

    # 5. Delete associated audio files first (if dir exists)
    if os.path.isdir(user_audio_subdir):
        try:
            shutil.rmtree(user_audio_subdir)
            print(f"INFO:    Deleted audio directory: {user_audio_subdir}")
        except Exception as e:
            print(f"ERROR:   Failed to delete audio directory {user_audio_subdir}: {e}")
            # Continue deletion process even if audio removal fails partially

    # 6. Delete from RAM caches
    if uid in user_memories: 
        del user_memories[uid]
        print(f"INFO:    Evicted RAM cache 'user_memories' for {uid}.")
    
    if uid in cache_last_accessed: 
        del cache_last_accessed[uid]
        print(f"INFO:    Evicted RAM cache 'cache_last_accessed' for {uid}.")

    # 7. Delete the JSON file from disk
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"INFO:    Deleted memory file: {filepath}")
        except Exception as e:
            print(f"ERROR:   Failed to delete memory file {filepath}: {e}")
            # Raise error if file deletion fails, as it's critical
            raise HTTPException(status_code=500, detail=f"Could not delete memory file for user {uid}.")
    else:
        print(f"INFO:    Memory file not found, nothing to delete on disk: {filepath}")

    return {"status": f"all data for user {uid} deleted successfully"}

