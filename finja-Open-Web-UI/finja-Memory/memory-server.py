# memory_service.py

"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory – Memory Server
  Version: 4.4.2
  Author:  John (J. Apps / Sodakiller1)
  License: Apache License 2.0 (c) 2025 J. Apps
  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2
  Author Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps 
  
----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Server-side storage for the "Adaptive Memory" OpenWebUI Plugin.
  • Stores memories separated by User-ID in portable JSON files.
  • Intelligent RAM Cache: Keeps active users in memory for lightning-fast
    read access and cleans up automatically after inactivity.
  • Voice-Memory Interfaces: Provides endpoints for accepting user audio files
    (STT) and caching AI speech outputs (TTS).
  • Robust REST API based on FastAPI for all CRUD operations.
  • Configuration via a .env file for enhanced security.
----------------------------------------------------------------------

----------------------------------------------------------------------
 Updates 4.4.2:
 ---------------------------------------------------------------------
  + **True TTS Caching:** Replaced placeholder TTS generation with fully
    implemented endpoints (`/upload_tts_cache` and `/get_tts_audio`). The
    server now cleanly accepts generated `.wav` audio files and streams them
    back directly on request, acting as a robust audio caching layer.
  + **Security Hardening (Path Traversal):** Implemented critical security
    improvements in the `/delete_user_memories` and `/add_voice_memory` endpoints.
    Additional checks (Empty-String & Path Canonicalization) now prevent
    potential Path Traversal attacks or accidental deletion of root directories
    via manipulated User-IDs.
  + **Dependency Security Fix:** Updated `starlette` in `requirements.txt` to
    version 0.50.0 to close a known vulnerability in the older version.
  + **Code Quality & Modernization:** Migrated FastAPI endpoints to the new
    `Annotated` syntax to resolve IDE warnings. Properly documented all
    HTTP-Exceptions in the endpoint schemas. Resolved false-positive
    warnings for Hardcoded-Credentials.

 Updates 4.4.1:
 ---------------------------------------------------------------------
  + **Fix Auth Log Error:** Added a check in `auth_check` to prevent a
    `TypeError` when logging unauthorized access attempts if the `X-API-Key`
    header is completely missing (`key` is None).

 Updates 4.4.0:
 ---------------------------------------------------------------------
  + **Admin Backup Endpoint:** Added `POST /backup_all_now` endpoint.
    - Saves all current in-memory data to disk.
    - Copies all user memory JSON files to a timestamped subfolder
      within the new `backups` directory.
  + **User Backup Placeholder:** Added `POST /backup_now` endpoint.
    - Accepts a User-ID.
    - Performs authentication.
    - Currently returns a simple confirmation message (Placeholder).
  + **Backup Directory:** Added `BACKUP_DIR` constant and directory
    creation on startup.

 Updates 4.3.0:
 ---------------------------------------------------------------------
  + **Foundation for User-Input (STT):** Implemented new endpoint
    `/add_voice_memory`. It accepts audio files, saves them, and creates a
    placeholder memory with the file path.
  + **Foundation for AI-Output (TTS-Cache):** Implemented new endpoint
    `/get_or_create_speech`. It checks if speech output for a text already
    exists and simulates creation if it doesn't.

 Updates 4.2.0:
 ---------------------------------------------------------------------
  + **Intelligent RAM Cache:** The server now loads user data only once
    from the disk and serves all subsequent requests from fast memory.
  + **Automatic Garbage Collection:** A new background thread monitors
    activity and removes inactive users from RAM.
  + **Stability Fixes:** Fixed logic errors related to the new cache
    system during server startup and manual backups.
----------------------------------------------------------------------

----------------------------------------------------------------------
 Roadmap:
 ---------------------------------------------------------------------
  • User Management & Access Control
  • Optional Database Backends (ChromaDB, Redis, SQLite)
  • API Authentication (Token System)
  • Memory Visualizer (Admin Interface)
  • Automatic Memory Archiving & Pruning
  • Extended Logging Features

----------------------------------------------------------------------
 License Notice:
 ---------------------------------------------------------------------
  This project is based on the work of gramanoid (diligent_chooser)
  and is released under the Apache License 2.0.
  All rights to modifications © 2025 J. Apps

=====================================================================================================================================
"""


from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException, Body, Request, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Annotated
import uuid, time, json, threading, os, hashlib, shutil # Added shutil
from dotenv import load_dotenv
import aiofiles
from datetime import datetime # Added datetime for backup timestamp

# Start FastAPI App
app = FastAPI(title="Memory Service")

# Load .env file
load_dotenv()

# Get API Key from environment variable
API_KEY = os.getenv("MEMORY_API_KEY")

if not API_KEY:
    raise ValueError("MEMORY_API_KEY environment variable is required!")

# Maximum number of memories kept in RAM per user
MAX_RAM_MEMORIES = 5000

# Auto-backup interval in seconds (600 = 10 minutes)
BACKUP_INTERVAL = 600
CACHE_TIMEOUT = 600

# Folder definitions
USER_MEMORY_DIR = "user_memories"
USER_AUDIO_DIR = "user_audio"
TTS_CACHE_DIR = "tts_cache"
BACKUP_DIR = "backups" # New backup directory

# Create all necessary folders on startup
os.makedirs(USER_MEMORY_DIR, exist_ok=True)
os.makedirs(USER_AUDIO_DIR, exist_ok=True)
os.makedirs(TTS_CACHE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True) # Create backup dir

# Stores when a user cache was last accessed (for automatic cleanup)
cache_last_accessed: Dict[str, float] = {}

# -------------------------
# Data Models (Schemas)
# -------------------------
class MemoryItem(BaseModel):
    id: str = ""
    # deepcode ignore HardcodedCredentials: User ID is dynamically retrieved from Open-Web-UI at runtime
    user_id: str = Field(default="default_user")
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

# Memory structure in RAM (all active memories)
user_memories: Dict[str, List[MemoryItem]] = {}

class TTSRequest(BaseModel):
    text: str

# -------------------------
# Helper Functions
# -------------------------

def memory_file(user_id):
    """Returns the file path for the memory file of a specific user."""
    # Ensure user_id is filename-safe (basic sanitation)
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ('-', '_')).rstrip()
    if not safe_user_id: safe_user_id = "invalid_user_id"
    return os.path.join(USER_MEMORY_DIR, f"{safe_user_id}_memory.json")

def save_to_disk(user_id):
    """Saves a user's memories to disk."""
    filepath = memory_file(user_id)
    if user_id in user_memories:
        try:
            with open(filepath, "w", encoding="utf-8") as f:  # NOSONAR
                # Use Pydantic's model_dump for serialization
                json.dump([m.model_dump() for m in user_memories[user_id]], f, ensure_ascii=False, indent=2)
            print(f"INFO:    Saved memories for user {user_id} to {filepath}")
        except Exception as e:
            print(f"ERROR:   Failed to save memories for user {user_id} to {filepath}: {e}")
    #else:
        # Optionally log if user_id not in memory (might happen during cleanup)
        # print(f"DEBUG:   User {user_id} not in RAM cache, skipping save_to_disk.")


def load_from_disk(user_id):
    """Loads a user's memories from disk into RAM."""
    filepath = memory_file(user_id)
    try:
        with open(filepath, "r", encoding="utf-8") as f:  # NOSONAR
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
    """Automatic backup of all user memories in RAM at regular intervals."""
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
    """Periodically removes inactive user caches from RAM."""
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
# Startup Events
# -------------------------

@app.on_event("startup")
def startup():
    """On startup: Load saved memories & start background threads."""
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
# Authentication
# -------------------------
def auth_check(request: Request):
    """Checks if the API key in the header is present and valid."""
    key = request.headers.get("X-API-Key")
    if not key or key != API_KEY:
        # FIX: Check if key is not None before slicing
        key_display = f"{key[:5]}..." if key else "None"
        print(f"WARN:    Unauthorized access attempt. Provided key: {key_display}") # Log masked key or "None"
        raise HTTPException(status_code=401, detail="Missing or invalid API Key.")


# -------------------------
# API Endpoints
# -------------------------

@app.post("/add_memory", responses={401: {"description": "Unauthorized"}})
async def add_memory(request: Request, mem: Annotated[MemoryItem, Body(...)]):
    """Adds a single memory and utilizes the RAM cache."""
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

@app.post("/add_memories", responses={401: {"description": "Unauthorized"}})
def add_memories(request: Request, batch: Annotated[List[MemoryItem], Body(...)]):
    """Adds a list of memories and utilizes the RAM cache."""
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

@app.get("/get_memories", responses={401: {"description": "Unauthorized"}})
def get_memories(request: Request, user_id: Optional[str] = None, query: Optional[str] = None, limit: int = 50):
    """Retrieve memories, preferably from the fast RAM cache."""
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

@app.get("/memory_stats", responses={401: {"description": "Unauthorized"}})
def memory_stats(request: Request, user_id: Optional[str] = None):
    """Statistics about a user's memories from the RAM cache."""
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

@app.post("/prune", responses={401: {"description": "Unauthorized"}})
def prune(request: Request, data: Annotated[PruneAction, Body(...)]):
    """Delete oldest entries while utilizing the RAM cache."""
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
@app.post("/backup_all_now", responses={401: {"description": "Unauthorized"}, 500: {"description": "Server Error"}})
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
@app.post("/backup_now", responses={401: {"description": "Unauthorized"}})
async def backup_now_placeholder(request: Request, data: Annotated[UserAction, Body(...)]):
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
    """PLACEHOLDER FUNCTION: Simulates transcription."""
    filename = os.path.basename(filepath)
    print(f"INFO:    [DUMMY] Transcribing '{filename}'...")
    time.sleep(0.5) # Shorter delay
    return f"Transkript: {filename}"

@app.post("/add_voice_memory", responses={400: {"description": "Bad Request"}, 401: {"description": "Unauthorized"}, 500: {"description": "Server Error"}})
async def add_voice_memory(request: Request, user_id: Annotated[str, Form(...)], file: Annotated[UploadFile, File(...)]):
    """Receives audio, saves it, and simulates transcription."""
    auth_check(request)
    uid = user_id or "default"
    
    # 1. Sanitize input
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ('-', '_')).strip()
    
    # 2. CHECK: Prevent empty strings (Prevents writing to the root directory)
    if not safe_uid:
        print(f"WARN:    Invalid user_id for audio upload: '{uid}'")
        raise HTTPException(status_code=400, detail="Invalid User ID.")

    # 3. Build path securely
    user_audio_subdir = os.path.join(USER_AUDIO_DIR, safe_uid)

    # 4. PARANOID CHECK (Snyk-Friendly): Path Canonicalization
    # Ensure that the target folder is truly inside USER_AUDIO_DIR
    try:
        real_target_path = os.path.realpath(user_audio_subdir)
        real_base_path = os.path.realpath(USER_AUDIO_DIR)
        if not real_target_path.startswith(real_base_path):
             print(f"CRITICAL: Path Traversal attempt in audio upload! {real_target_path}")
             raise HTTPException(status_code=400, detail="Security check failed.")
    except Exception as e:
        print(f"ERROR:   Path security check failed: {e}")
        raise HTTPException(status_code=500, detail="Internal security check error.")

    # From here on everything is safe -> create folder
    os.makedirs(user_audio_subdir, exist_ok=True) 

    file_extension = os.path.splitext(file.filename or "audio.unk")[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    save_path = os.path.join(user_audio_subdir, unique_filename)  # NOSONAR - path validated above via canonicalization, filename is uuid4

    try:
        async with aiofiles.open(save_path, 'wb') as out_file:  # NOSONAR
            while content := await file.read(1024 * 1024): await out_file.write(content)
        print(f"INFO:    Saved voice memory to {save_path}")
    except Exception as e: 
        raise HTTPException(status_code=500, detail=f"Could not save audio file: {e}")

    transcript = transcribe_audio_dummy(save_path)
    voice_memory = MemoryItem(user_id=uid, text=transcript, meta={"source": "voice_input", "audio_path": save_path}) 

    # Use the existing add_memory endpoint logic
    await add_memory(request, voice_memory)

    return {"status": "voice_memory_added", "transcript": transcript, "audio_path": save_path}

@app.post("/upload_tts_cache", responses={401: {"description": "Unauthorized"}, 500: {"description": "Server Error"}})
async def upload_tts_cache(request: Request, text: Annotated[str, Form(...)], file: Annotated[UploadFile, File(...)]):
    """Receives generated TTS audio and stores it in the cache."""
    auth_check(request)
    
    # Calculate hash to determine filename
    text_hash = hashlib.sha256(text.strip().encode('utf-8')).hexdigest()
    filename = f"{text_hash}.wav" # We use wav
    filepath = os.path.join(TTS_CACHE_DIR, filename)  # NOSONAR - filename is sha256 hex hash, no path traversal possible

    try:
        # Save file
        async with aiofiles.open(filepath, 'wb') as out_file:  # NOSONAR
            while content := await file.read(1024 * 1024): 
                await out_file.write(content)
        
        print(f"INFO:    TTS Cache ADDED: '{text[:20]}...' -> {filename}")
        return {"status": "cached", "file": filename}
    except Exception as e:
        print(f"ERROR:   Failed to cache TTS upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_tts_audio", responses={401: {"description": "Unauthorized"}, 404: {"description": "Not Found"}})
def get_tts_audio(request: Request, text: str):
    """
    Checks if audio for the text exists.
    If YES: Returns the file directly (Audio Stream).
    If NO: 404 (Signal for clients: 'You need to generate!')
    """
    auth_check(request)
    
    text_hash = hashlib.sha256(text.strip().encode('utf-8')).hexdigest()
    # Check for wav and mp3
    for ext in [".wav", ".mp3"]:
        filepath = os.path.join(TTS_CACHE_DIR, f"{text_hash}{ext}")  # NOSONAR - filename is sha256 hex hash
        if os.path.exists(filepath):
            print(f"INFO:    TTS Cache HIT: Serve '{text[:20]}...'")
            return FileResponse(filepath, media_type=f"audio/{ext.strip('.')}")  # NOSONAR

    print(f"INFO:    TTS Cache MISS: '{text[:20]}...'")
    raise HTTPException(status_code=404, detail="Audio not found in cache")

@app.post("/delete_user_memories", responses={400: {"description": "Bad Request"}, 401: {"description": "Unauthorized"}, 500: {"description": "Server Error"}})
def delete_user_memories(request: Request, data: Annotated[UserAction, Body(...)]):
    """Deletes ALL data for a user (JSON, Audio, RAM)."""
    auth_check(request)
    uid = data.user_id
    
    # 1. Input Sanitization: Remove everything except alphanumeric, hyphen, underscore
    # .strip() removes spaces at the beginning/end
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ('-', '_')).strip()
    
    # 2. CRITICAL SECURITY CHECK: Prevent empty strings!
    # If safe_uid is empty (e.g. because User only sent "..."), we abort immediately.
    if not safe_uid:
        print(f"WARN:    Invalid user_id provided for deletion: '{uid}' -> resulted in empty safe_uid.")
        raise HTTPException(status_code=400, detail="Invalid User ID for deletion.")

    print(f"WARN:    Deletion requested for user '{uid}' (safe: '{safe_uid}')")

    filepath = memory_file(uid) # Internally uses safe_uid logic as well, which is fine here
    
    # 3. Build path securely
    user_audio_subdir = os.path.join(USER_AUDIO_DIR, safe_uid)

    # 4. PARANOID CHECK (Snyk-Friendly): Path Canonicalization
    # We fully resolve the path and check if it really still lies within USER_AUDIO_DIR.
    # This completely prevents theoretical "../" attacks.
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

    # 7. Delete the JSON file from disk (with path canonicalization check)
    real_memory_path = os.path.realpath(filepath)
    real_memory_base = os.path.realpath(USER_MEMORY_DIR)
    if not real_memory_path.startswith(real_memory_base):
        print(f"CRITICAL: Path Traversal attempt on memory file! {real_memory_path}")
        raise HTTPException(status_code=400, detail="Security check failed.")

    if os.path.exists(filepath):
        try:
            os.remove(filepath)  # NOSONAR - path validated above via canonicalization
            print(f"INFO:    Deleted memory file: {filepath}")
        except Exception as e:
            print(f"ERROR:   Failed to delete memory file {filepath}: {e}")
            # Raise error if file deletion fails, as it's critical
            raise HTTPException(status_code=500, detail=f"Could not delete memory file for user {uid}.")
    else:
        print(f"INFO:    Memory file not found, nothing to delete on disk: {filepath}")

    return {"status": f"all data for user {uid} deleted successfully"}

