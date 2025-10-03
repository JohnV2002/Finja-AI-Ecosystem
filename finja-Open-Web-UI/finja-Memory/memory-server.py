# memory_service.py

"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory – Memory Server
  Version: 1.2
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
import uuid, time, json, threading, os, hashlib
from dotenv import load_dotenv
import aiofiles

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

# Ordner, in dem Erinnerungen pro User als JSON gespeichert werden
USER_MEMORY_DIR = "user_memories"
USER_AUDIO_DIR = "user_audio"
TTS_CACHE_DIR = "tts_cache"
os.makedirs(USER_MEMORY_DIR, exist_ok=True)  # Ordner wird erstellt, falls nicht vorhanden
os.makedirs(USER_AUDIO_DIR, exist_ok=True)
os.makedirs(TTS_CACHE_DIR, exist_ok=True)

# Speichert, wann ein User-Cache zuletzt verwendet wurde (für die automatische Bereinigung)
cache_last_accessed: Dict[str, float] = {}

# -------------------------
# Daten-Modelle (Schemas)
# -------------------------
class MemoryItem(BaseModel):
    id: str = ""    # Eindeutige ID (UUID)
    
    # snyk:ignore:python/UseOfHardcodedCredentials
    # Reason: User ID is dynamically retrieved from Open-Web-UI at runtime
    #         to identify the correct memory context. No static credentials
    #         are stored or loaded from hardcoded strings.
    user_id: str = "default"    # Benutzer-Identifikator # !snyk FALSE Positiv! 


    text: str                   # Inhalt der Erinnerung
    timestamp: float = 0        # Unix-Timestamp (wann gespeichert)

    # --- NEUE OPTIONALE FELDER ---
    bank: Optional[str] = "General"
    expires_at: Optional[float] = None
    meta: Optional[Dict[str, Any]] = {}

class UserAction(BaseModel):
    user_id: str    # Für Backup/Prune Aktionen

class PruneAction(BaseModel):
    user_id: str   # Ziel-Benutzer-ID
    amount: int    # Anzahl der zu löschenden Erinnerungen

# Speicherstruktur im RAM (alle aktiven Erinnerungen)
user_memories: Dict[str, List[MemoryItem]] = {}

class TTSRequest(BaseModel):
    text: str

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

def cleanup_inactive_caches():
    """Entfernt in regelmäßigen Abständen inaktive User-Caches aus dem RAM."""
    while True:
        # Prüfe alle 60 Sekunden, ob jemand aufgeräumt werden muss.
        time.sleep(60)
        
        # Erstelle eine Kopie, da wir das Dictionary während des Durchlaufs verändern.
        inactive_users = []
        for uid, last_time in list(cache_last_accessed.items()):
            if time.time() - last_time > CACHE_TIMEOUT:
                inactive_users.append(uid)
        
        if inactive_users:
            print(f"INFO:    Found {len(inactive_users)} inactive user(s) to clean from RAM-Cache.")
            for uid in inactive_users:
                # Speichere zur Sicherheit den letzten Stand auf die Festplatte.
                save_to_disk(uid)
                # Entferne die Daten aus den RAM-Speichern.
                if uid in user_memories:
                    del user_memories[uid]
                if uid in cache_last_accessed:
                    del cache_last_accessed[uid]
                print(f"INFO:    Evicted cache for user: {uid}")


# -------------------------
# Startup-Events
# -------------------------

@app.on_event("startup")
def startup():
    """Beim Start: Gespeicherte Erinnerungen laden & Hintergrund-Threads starten"""
    for file in os.listdir(USER_MEMORY_DIR):
        if file.endswith("_memory.json"):
            uid = file.replace("_memory.json", "")
            load_from_disk(uid)
            # --- KORREKTUR: Starte den Timer für jeden geladenen User ---
            cache_last_accessed[uid] = time.time()
            
    # Starte den Auto-Backup Thread
    backup_thread = threading.Thread(target=auto_backup, daemon=True)
    backup_thread.start()
    
    # Starte den Cache-Cleanup Thread
    cleanup_thread = threading.Thread(target=cleanup_inactive_caches, daemon=True)
    cleanup_thread.start()

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
async def add_memory(request: Request, mem: MemoryItem = Body(...)):
    """Fügt eine einzelne Erinnerung hinzu und nutzt den RAM-Cache."""
    auth_check(request)
    uid = mem.user_id or "default"

    # Lade die Daten nur, wenn sie nicht schon im RAM sind.
    if uid not in user_memories:
        load_from_disk(uid)
    
    # Aktualisiere den Zeitstempel für die User-Aktivität.
    cache_last_accessed[uid] = time.time()
    
    # Modifiziere die Daten direkt im RAM.
    mem.id = str(uuid.uuid4())
    mem.timestamp = time.time()
    memories = user_memories.get(uid, [])
    if len(memories) >= MAX_RAM_MEMORIES:
        del memories[0:len(memories)-MAX_RAM_MEMORIES+1]
    memories.append(mem)
    user_memories[uid] = memories
    
    # Speichere die Änderungen am Ende zurück auf die Festplatte.
    save_to_disk(uid)
    return {"status": "added", "id": mem.id}

@app.post("/add_memories")
def add_memories(request: Request, batch: List[MemoryItem] = Body(...)):
    """Fügt eine Liste von Erinnerungen hinzu und nutzt den RAM-Cache."""
    auth_check(request)
    if not batch:
        return {"status": "no_data"}
    uid = batch[0].user_id or "default"

    # Lade die Daten nur, wenn sie nicht schon im RAM sind.
    if uid not in user_memories:
        load_from_disk(uid)
    
    # Aktualisiere den Zeitstempel für die User-Aktivität.
    cache_last_accessed[uid] = time.time()

    # Modifiziere die Daten direkt im RAM.
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
    
    # Speichere die Änderungen am Ende zurück auf die Festplatte.
    save_to_disk(uid)
    return {"status": "batch_added", "added": added}

@app.get("/get_memories")
def get_memories(request: Request, user_id: Optional[str] = None, query: Optional[str] = None, limit: int = 50):
    """Erinnerungen abrufen, bevorzugt aus dem schnellen RAM-Cache."""
    auth_check(request)
    uid = user_id or "default"

    # Prüfe, ob die Erinnerungen für diesen User bereits im RAM sind.
    if uid not in user_memories:
        # Falls nicht, lade sie einmalig von der Festplatte.
        load_from_disk(uid)
    
    # Setze den Zeitstempel, um zu zeigen, dass dieser User gerade aktiv war.
    cache_last_accessed[uid] = time.time()
    
    # Arbeite ab jetzt nur noch mit den Daten aus dem RAM.
    memories = user_memories.get(uid, [])
    filtered = memories
    if query:
        # Filtere die RAM-Daten bei Bedarf.
        filtered = [m for m in filtered if query.lower() in m.text.lower()]
    return filtered[-limit:]

@app.get("/memory_stats")
def memory_stats(request: Request, user_id: Optional[str] = None):
    """Statistiken über die Erinnerungen eines Benutzers aus dem RAM-Cache."""
    auth_check(request)
    uid = user_id or "default"

    # Prüfe auch hier, ob die Daten bereits im RAM sind.
    if uid not in user_memories:
        load_from_disk(uid)
    
    # Setze auch hier den Zeitstempel für die Aktivität.
    cache_last_accessed[uid] = time.time()
    
    return {
        "total": len(user_memories.get(uid, [])),
        "max_ram": MAX_RAM_MEMORIES,
        "file": memory_file(uid)
    }

@app.post("/prune")
def prune(request: Request, data: PruneAction = Body(...)):
    """Älteste Einträge löschen und dabei den RAM-Cache nutzen."""
    auth_check(request)
    uid = data.user_id

    # Lade die Daten nur, wenn sie nicht schon im RAM sind.
    if uid not in user_memories:
        load_from_disk(uid)

    # Aktualisiere den Zeitstempel für die User-Aktivität.
    cache_last_accessed[uid] = time.time()

    # Modifiziere die Daten direkt im RAM.
    memories = user_memories.get(uid, [])
    if data.amount >= len(memories):
        user_memories[uid] = []
    else:
        user_memories[uid] = memories[data.amount:]
    
    # Speichere die Änderungen am Ende zurück auf die Festplatte.
    save_to_disk(uid)
    return {"status": "pruned", "left": len(user_memories[uid])}

@app.post("/backup_now")
def backup_now(request: Request, data: UserAction = Body(...)):
    """Manuelles Backup auslösen, auch für nicht-gecachte User."""
    auth_check(request)
    uid = data.user_id
    
    # --- KORREKTUR: Lade die Daten, falls sie nicht im RAM sind ---
    if uid not in user_memories:
        load_from_disk(uid)

    # Jetzt können wir sicher sein, dass die Daten da sind und gespeichert werden.
    save_to_disk(uid)
    return {"status": "backup_done", "file": memory_file(uid)}

def transcribe_audio_dummy(filepath: str) -> str:
    """
    PLATZHALTER-FUNKTION: Simuliert die Transkription einer Audiodatei.
    In der Zukunft wird hier der echte Whisper-Aufruf stehen.
    """
    filename = os.path.basename(filepath)
    print(f"INFO:    [DUMMY] Transcribing '{filename}'...")
    time.sleep(1) # Simuliert die Verarbeitungszeit
    return f"Transkript der Sprachnachricht '{filename}'"

@app.post("/add_voice_memory")
async def add_voice_memory(
    request: Request,
    user_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Nimmt eine Audiodatei vom User entgegen, speichert sie und erstellt
    eine Erinnerung mit einem (aktuell simulierten) Transkript.
    """
    auth_check(request)
    uid = user_id or "default"
    
    # 1. Audiodatei sicher speichern
    file_extension = os.path.splitext(file.filename)[1] # type: ignore
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    save_path = os.path.join(USER_AUDIO_DIR, unique_filename)
    
    try:
        async with aiofiles.open(save_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
        print(f"INFO:    Saved voice memory to {save_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save audio file: {e}")

    # 2. Transkription (aktuell nur ein Platzhalter)
    transcript = transcribe_audio_dummy(save_path)

    # 3. Neue Erinnerung erstellen und speichern
    voice_memory = MemoryItem(
        user_id=uid,
        text=transcript,
        meta={
            "source": "voice_input",
            "audio_url": save_path
        }
    )
    
    # --- HIER DIE KORREKTUR ---
    # Wir rufen jetzt die async-Funktion mit 'await' auf.
    await add_memory(request, voice_memory)
    # -------------------------
    
    return {"status": "voice_memory_added", "transcript": transcript, "audio_url": save_path}

def generate_speech_dummy(text: str, filepath: str) -> bool:
    """
    PLATZHALTER-FUNKTION: Simuliert die Erstellung einer Sprachdatei.
    In der Zukunft wird hier ein echtes TTS-Modell (z.B. Piper, Coqui) aufgerufen.
    """
    print(f"INFO:    [DUMMY] Generating speech for text: '{text[:30]}...'")
    time.sleep(1) # Simuliert die Generierungszeit
    # Erstellt eine leere Datei, um zu zeigen, dass etwas passiert ist.
    with open(filepath, 'w') as f:
        f.write(f"This is a dummy audio file for the text: {text}")
    print(f"INFO:    [DUMMY] Saved dummy speech file to {filepath}")
    return True

@app.post("/get_or_create_speech")
async def get_or_create_speech(request: Request, data: TTSRequest = Body(...)):
    """
    Nimmt Text entgegen und gibt den Pfad zu einer passenden Audiodatei zurück.
    Prüft zuerst den Cache; generiert die Datei nur, wenn sie nicht existiert.
    """
    auth_check(request)
    text_to_speak = data.text.strip()
    if not text_to_speak:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    # 1. Erzeuge einen eindeutigen & wiederholbaren Dateinamen aus dem Text-Inhalt
    # Wir nutzen einen SHA256-Hash, damit "Hallo Welt" immer denselben Dateinamen bekommt.
    text_hash = hashlib.sha256(text_to_speak.encode('utf-8')).hexdigest()
    filename = f"{text_hash}.mp3" # Wir nehmen an, es wird eine mp3
    filepath = os.path.join(TTS_CACHE_DIR, filename)

    # 2. Cache-Prüfung: Existiert die Datei bereits?
    if os.path.exists(filepath):
        # Cache HIT: Die Datei ist schon da, wir geben sie sofort zurück.
        print(f"INFO:    TTS Cache HIT for text: '{text_to_speak[:30]}...'")
        return {"status": "cache_hit", "audio_url": filepath}

    # 3. Cache MISS: Die Datei existiert nicht, wir müssen sie "generieren".
    print(f"INFO:    TTS Cache MISS for text: '{text_to_speak[:30]}...'. Generating...")
    
    # Hier rufen wir unsere Dummy-Funktion auf.
    # Später wird hier die echte, rechenintensive TTS-Logik stehen.
    success = generate_speech_dummy(text_to_speak, filepath)

    if success:
        return {"status": "created", "audio_url": filepath}
    else:
        raise HTTPException(status_code=500, detail="Failed to generate speech file.")

@app.post("/delete_user_memories")
def delete_user_memories(request: Request, data: UserAction = Body(...)):
    """
    Löscht ALLE Daten für einen bestimmten User unwiderruflich.
    Dies umfasst die JSON-Datei, zugehörige Audiodateien und alle RAM-Caches.
    """
    auth_check(request)
    uid = data.user_id
    print(f"WARNUNG: Lösch-Anfrage für User '{uid}' erhalten.")

    # --- NEU: Zuerst die Pfade zu den Audiodateien aus der JSON-Datei auslesen ---
    # Wir müssen die Daten von der Festplatte laden, um sicherzustellen, dass wir den letzten Stand haben.
    filepath = memory_file(uid)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                items = json.load(f)
                
            # Gehe durch jede Erinnerung und suche nach einem 'audio_url'-Eintrag.
            for item in items:
                meta = item.get("meta", {})
                if isinstance(meta, dict) and "audio_url" in meta:
                    audio_path = meta["audio_url"]
                    # Lösche die gefundene Audiodatei.
                    if os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                            print(f"INFO:    Zugehörige Audiodatei '{audio_path}' für User '{uid}' gelöscht.")
                        except Exception as e:
                            print(f"FEHLER: Konnte Audiodatei '{audio_path}' nicht löschen: {e}")
        except Exception as e:
            print(f"FEHLER: Konnte Speicherdatei '{filepath}' zum Auslesen der Audio-Pfade nicht öffnen: {e}")

    # 1. Aus dem RAM-Cache für Erinnerungen entfernen
    if uid in user_memories:
        del user_memories[uid]
        print(f"INFO:    Cache 'user_memories' für User '{uid}' gelöscht.")

    # 2. Aus dem RAM-Cache für Aktivitäts-Timestamps entfernen
    if uid in cache_last_accessed:
        del cache_last_accessed[uid]
        print(f"INFO:    Cache 'cache_last_accessed' für User '{uid}' gelöscht.")

    # 3. Die JSON-Datei von der Festplatte löschen (passiert nach dem Auslesen)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"INFO:    Speicherdatei '{filepath}' für User '{uid}' gelöscht.")
        except Exception as e:
            print(f"FEHLER: Konnte Speicherdatei für User '{uid}' nicht löschen: {e}")
            raise HTTPException(status_code=500, detail=f"Could not delete memory file for user {uid}.")
    
    return {"status": f"all data for user {uid} deleted"}