# memory_service.py
from fastapi import FastAPI, HTTPException, Body, Request
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid, time, json, threading, os

# Starte FastAPI-App
app = FastAPI(title="Memory Service")

# *** WICHTIG: Dein API-Key, muss bei allen Requests im Header mitgeschickt werden ***
API_KEY = "changeme-supersecretkey"  # <- Hier richtigen Key eintragen!

# Maximale Anzahl an Erinnerungen, die im RAM pro User gehalten werden
MAX_RAM_MEMORIES = 5000

# Alle wie viele Sekunden ein automatisches Backup gemacht wird (600 = 10 Minuten)
BACKUP_INTERVAL = 600

# Ordner, in dem Erinnerungen pro User als JSON gespeichert werden
USER_MEMORY_DIR = "user_memories"
os.makedirs(USER_MEMORY_DIR, exist_ok=True)  # Ordner wird erstellt, falls nicht vorhanden

# -------------------------
# Daten-Modelle (Schemas)
# -------------------------
class MemoryItem(BaseModel):
    id: str = ""                # Eindeutige ID (UUID)
    user_id: str = "default"    # Benutzer-Identifikator
    text: str                   # Inhalt der Erinnerung
    timestamp: float = 0        # Unix-Timestamp (wann gespeichert)

class UserAction(BaseModel):
    user_id: str    # Für Backup/Prune Aktionen

class PruneAction(BaseModel):
    user_id: str   # Ziel-Benutzer-ID
    amount: int    # Anzahl der zu löschenden Erinnerungen

# Speicherstruktur im RAM (alle aktiven Erinnerungen)
user_memories: Dict[str, List[MemoryItem]] = {}

# -------------------------
# Hilfsfunktionen
# -------------------------

def memory_file(user_id):
    """Pfad zur Speicherdatei für einen bestimmten User zurückgeben"""
    return os.path.join(USER_MEMORY_DIR, f"{user_id}_memory.json")

def save_to_disk(user_id):
    """Speichert die Erinnerungen eines Benutzers auf die Festplatte"""
    if user_id in user_memories:
        with open(memory_file(user_id), "w", encoding="utf-8") as f:
            json.dump([m.dict() for m in user_memories[user_id]], f, ensure_ascii=False, indent=2)

def load_from_disk(user_id):
    """Lädt die Erinnerungen eines Benutzers von der Festplatte in den RAM"""
    try:
        with open(memory_file(user_id), "r", encoding="utf-8") as f:
            items = json.load(f)
            user_memories[user_id] = [MemoryItem(**entry) for entry in items]
    except Exception:
        user_memories[user_id] = []

def auto_backup():
    """Automatisches Backup aller User-Erinnerungen in regelmäßigen Abständen"""
    while True:
        time.sleep(BACKUP_INTERVAL)
        for uid in user_memories:
            save_to_disk(uid)

# -------------------------
# Startup-Events
# -------------------------

@app.on_event("startup")
def startup():
    """Beim Start: Alle gespeicherten Erinnerungen laden + Auto-Backup starten"""
    for file in os.listdir(USER_MEMORY_DIR):
        if file.endswith("_memory.json"):
            uid = file.replace("_memory.json", "")
            load_from_disk(uid)
    thread = threading.Thread(target=auto_backup, daemon=True)
    thread.start()

# -------------------------
# Authentifizierung
# -------------------------
def auth_check(request: Request):
    """Überprüft, ob der API-Key im Header vorhanden und gültig ist"""
    key = request.headers.get("X-API-Key")
    if not key or key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API Key.")
    
    
# -------------------------
# API-Endpunkte
# -------------------------

@app.post("/add_memory")
def add_memory(request: Request, mem: MemoryItem = Body(...)):
    """Fügt eine einzelne Erinnerung hinzu"""
    auth_check(request)
    uid = mem.user_id or "default"
    load_from_disk(uid)
    mem.id = str(uuid.uuid4())
    mem.timestamp = time.time()
    memories = user_memories.get(uid, [])
    if len(memories) >= MAX_RAM_MEMORIES:
        del memories[0:len(memories)-MAX_RAM_MEMORIES+1]
    memories.append(mem)
    user_memories[uid] = memories
    save_to_disk(uid)
    return {"status": "added", "id": mem.id}

@app.post("/add_memories")
def add_memories(request: Request, batch: List[MemoryItem] = Body(...)):
    """Fügt eine Liste von Erinnerungen hinzu (Batch-Operation)"""
    auth_check(request)
    if not batch:
        return {"status": "no_data"}
    uid = batch[0].user_id or "default"
    load_from_disk(uid)
    memories = user_memories.get(uid, [])
    added = 0
    for mem in batch:
        mem.id = str(uuid.uuid4())
        mem.timestamp = time.time()
        memories.append(mem)
        added += 1
    if len(memories) > MAX_RAM_MEMORIES:
        memories = memories[-MAX_RAM_MEMORIES:]
    user_memories[uid] = memories
    save_to_disk(uid)
    return {"status": "batch_added", "added": added}

@app.get("/get_memories")
def get_memories(request: Request, user_id: Optional[str] = None, query: Optional[str] = None, limit: int = 50):
    """Erinnerungen abrufen (optional filtern mit Such-Query)"""
    auth_check(request)
    uid = user_id or "default"
    load_from_disk(uid)
    memories = user_memories.get(uid, [])
    filtered = memories
    if query:
        filtered = [m for m in filtered if query.lower() in m.text.lower()]
    return filtered[-limit:]

@app.get("/memory_stats")
def memory_stats(request: Request, user_id: Optional[str] = None):
    """Statistiken über die Erinnerungen eines Benutzers"""
    auth_check(request)
    uid = user_id or "default"
    load_from_disk(uid)
    return {
        "total": len(user_memories.get(uid, [])),
        "max_ram": MAX_RAM_MEMORIES,
        "file": memory_file(uid)
    }

@app.post("/prune")
def prune(request: Request, data: PruneAction = Body(...)):
    """Älteste Einträge löschen (Privacy oder Platz sparen)"""
    auth_check(request)
    load_from_disk(data.user_id)
    memories = user_memories.get(data.user_id, [])
    if data.amount >= len(memories):
        user_memories[data.user_id] = []
    else:
        user_memories[data.user_id] = memories[data.amount:]
    save_to_disk(data.user_id)
    return {"status": "pruned", "left": len(user_memories[data.user_id])}

@app.post("/backup_now")
def backup_now(request: Request, data: UserAction = Body(...)):
    """Manuelles Backup auslösen"""
    auth_check(request)
    uid = data.user_id
    save_to_disk(uid)
    return {"status": "backup_done", "file": memory_file(uid)}
