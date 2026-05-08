"""
YourAI App API — Android/Mobile Endpoints
==========================================
FastAPI APIRouter with all app-specific endpoints.
Included into dashboard_server.py via app.include_router().

Endpoints:
  GET  /api/app/version         — App update check (no auth, public)
  GET  /api/mood                — YourAI's current mood for app UI
  POST /api/mobile/upload       — Upload image for chat (temp, 1h expiry)
  GET  /api/mobile/temp/{file}  — Serve uploaded temp image (no auth)
  DELETE /api/delete_my_data    — DSGVO: delete diary entries by session UUID

Maintenance mode:
  Non-admin users get HTTP 503 JSON instead of HTML maintenance page.
  Admins always pass through.
"""

import hashlib
import json
import os
import re
import sys
import time
import uuid as _uuid_mod
from datetime import date, timedelta

# ── Path setup (needed when run standalone or in Docker) ───────────────────���─
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError, YourAIUploadError, YourAIMaintenanceError
from app.auth import get_key_info, verify_access, maintenance_block

router = APIRouter()

# ─── Paths ────────────────────────────────────────────────────────────────────
_ROOT_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_VERSION_TXT  = os.path.join(_ROOT_DIR, "app_version.txt")
_APP_VERSION_LOCK = os.path.join(_ROOT_DIR, "app_version.lock")
_TEMP_UPLOADS_DIR = os.path.join(_ROOT_DIR, "temp_uploads")
_CHAT_LOG_FILE    = os.path.join(_ROOT_DIR, "docker_data", "app_chat_log.jsonl")
_FCM_TOKENS_FILE  = os.path.join(_ROOT_DIR, "docker_data", "fcm_tokens.json")

# ─── Upload constants ─────────────────────────────────────────────────────────
_UPLOAD_MAX_AGE  = 3600                    # 1 hour
_UPLOAD_MAX_SIZE = 10 * 1024 * 1024        # 10 MB
_UPLOAD_ALLOWED  = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_UPLOAD_EXTS     = {"image/jpeg": "jpg", "image/png": "png",
                    "image/gif": "gif", "image/webp": "webp"}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cleanup_temp_uploads() -> None:
    """Remove temp uploads older than _UPLOAD_MAX_AGE seconds."""
    if not os.path.isdir(_TEMP_UPLOADS_DIR):
        return
    now = time.time()
    for fname in os.listdir(_TEMP_UPLOADS_DIR):
        fpath = os.path.join(_TEMP_UPLOADS_DIR, fname)
        try:
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > _UPLOAD_MAX_AGE:
                os.unlink(fpath)
        except Exception:
            pass


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/app/version")
async def get_app_version():
    """
    Android app update check — no auth required (public meta endpoint).

    Returns the minimum required app version + MD5 hash.
    The app compares its own bundled version against 'version':
      - version matches  → up to date ✅
      - version differs  → show update dialog ⬆️
      - valid == false   → tamper warning ⚠️

    To force a new required version:
      1. Update app_version.txt  (e.g. "1.0.0+10002")
      2. Regenerate lock:
           python -c "import hashlib; print(hashlib.md5(open('app_version.txt','rb').read()).hexdigest())"
         → paste result into app_version.lock
      3. scp both + docker restart (no rebuild needed)
    """
    try:
        with open(_APP_VERSION_TXT, "r", encoding="utf-8") as f:
            version = f.read().strip()
        with open(_APP_VERSION_LOCK, "r", encoding="utf-8") as f:
            stored_hash = f.read().strip()

        computed = hashlib.md5(version.encode()).hexdigest()
        valid = computed == stored_hash

        if not valid:
            log("APP_API", f"⚠️ app_version lock mismatch! version={version} stored={stored_hash} computed={computed}", Fore.RED)

        return {"version": version, "hash": stored_hash, "valid": valid}

    except FileNotFoundError:
        return {"version": "0.0.0", "hash": "", "valid": False}
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_version")
        log_exception("APP_API", err)
        return {"version": "0.0.0", "hash": "", "valid": False}


@router.get("/api/mood")
async def get_mood(key: Optional[str] = None):
    """
    YourAI's current mood — for app UI header/avatar display.
    All roles allowed. Maintenance mode → 503 JSON (not HTML).
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    block = maintenance_block(key_info)
    if block:
        return block

    try:
        from helpers.personas import persona_manager
        return persona_manager.get_mood_for_dashboard()
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_mood")
        log_exception("APP_API", err)
        return {"mood": "default", "emoji": "🐾", "description": "Normal", "time": "", "time_of_day": ""}


@router.post("/api/mobile/upload")
async def mobile_upload(file: UploadFile = File(...), key: Optional[str] = None):
    """
    Upload a temp image from the app for use in chat.
    Multipart/form-data, field name: 'file'.
    Returns a temp URL valid for 1 hour.
    Max 10 MB, image/jpeg|png|gif|webp only.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    block = maintenance_block(key_info)
    if block:
        return block

    content_type = (file.content_type or "").lower()
    if content_type not in _UPLOAD_ALLOWED:
        err = YourAIUploadError(f"unsupported type: {content_type}", filename=file.filename)
        log_exception("APP_API", err)
        raise HTTPException(status_code=415, detail=f"Nur Bilder erlaubt (jpeg/png/gif/webp), erhalten: {content_type}")

    data = await file.read()
    if len(data) > _UPLOAD_MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"Bild zu groß (max {_UPLOAD_MAX_SIZE // (1024 * 1024)} MB)")

    os.makedirs(_TEMP_UPLOADS_DIR, exist_ok=True)
    _cleanup_temp_uploads()

    img_id  = str(_uuid_mod.uuid4())
    ext     = _UPLOAD_EXTS[content_type]
    filename = f"{img_id}.{ext}"
    filepath = os.path.join(_TEMP_UPLOADS_DIR, filename)

    try:
        with open(filepath, "wb") as f:
            f.write(data)
    except OSError as e:
        err = YourAIUploadError("disk write failed", filename=filename, cause=e)
        log_exception("APP_API", err)
        raise HTTPException(status_code=500, detail="Fehler beim Speichern des Uploads")

    log("APP_API", f"📱 Upload: {filename} ({len(data) // 1024} KB)", Fore.CYAN)
    return {
        "ok":       True,
        "url":      f"/api/mobile/temp/{filename}",
        "filename": filename,
        "size":     len(data),
    }


@router.get("/api/mobile/temp/{filename}")
async def mobile_serve_temp(filename: str):
    """
    Serve a previously uploaded temp image.
    No auth required — UUID-based filename is unguessable.
    Used by brain.py and the app to retrieve uploaded images.
    """
    if not re.match(r'^[a-f0-9\-]{36}\.(jpg|png|gif|webp)$', filename):
        raise HTTPException(status_code=404, detail="Not found")

    filepath = os.path.join(_TEMP_UPLOADS_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Bild nicht mehr verfügbar (abgelaufen oder nie hochgeladen)")

    ext   = filename.rsplit(".", 1)[-1]
    media = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
    return FileResponse(filepath, media_type=media[ext], headers={"Cache-Control": "no-store"})


@router.delete("/api/delete_my_data")
async def delete_my_data(request: Request, key: Optional[str] = None):
    """
    DSGVO: Delete all diary entries belonging to a session UUID.
    UUID is passed via the X-Session-UUID header.
    Generated client-side on first app launch, stored in SharedPreferences.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    block = maintenance_block(key_info)
    if block:
        return block

    session_uuid = request.headers.get("X-Session-UUID", "").strip()
    if not session_uuid:
        raise HTTPException(status_code=400, detail="X-Session-UUID Header fehlt")

    deleted = 0
    try:
        from memory.episodic import Diary
        diary  = Diary()
        deleted = diary.delete_by_uuid(session_uuid)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="delete_my_data")
        log_exception("APP_API", err)
        raise HTTPException(status_code=500, detail="Fehler beim Löschen der Daten")

    log("APP_API", f"🗑️ DSGVO delete: {deleted} entries for UUID {session_uuid[:8]}...", Fore.CYAN)
    return {"ok": True, "deleted": deleted, "message": f"{deleted} Einträge gelöscht"}


@router.get("/api/my_data")
async def get_my_data(request: Request, key: Optional[str] = None):
    """
    DSGVO Art. 15: Return a summary of all stored data for the requesting user.
    Returns: diary_count (by session UUID) + memory_facts (by user_id/key).
    """
    import httpx
    key_info = get_key_info(key)
    verify_access(key, "chat")

    user_key = key_info.get("user_key", "")
    session_uuid = request.headers.get("X-Session-UUID", "").strip()

    result: dict = {
        "diary_count": 0,
        "memory_facts": [],
        "memory_error": False,
    }

    # ── Diary count (by session UUID) ────────────────────────────
    if session_uuid:
        try:
            from memory.episodic import Diary
            result["diary_count"] = Diary().count_by_uuid(session_uuid)
        except Exception as e:
            log("APP_API", f"[my_data] diary count error: {e}", Fore.YELLOW)

    # ── Memory facts (by user_id = access key) ───────────────────
    try:
        from config import MEMORY_API_BASE, MEMORY_API_KEY
        if MEMORY_API_BASE and MEMORY_API_KEY:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{MEMORY_API_BASE}/get_memories",
                    headers={"X-API-Key": MEMORY_API_KEY},
                    params={"user_id": user_key, "limit": 200},
                )
                if r.status_code == 200:
                    facts = r.json()
                    result["memory_facts"] = [m.get("text", "") for m in facts if m.get("text")]
                else:
                    result["memory_error"] = True
    except Exception as e:
        log("APP_API", f"[my_data] memory fetch error: {e}", Fore.YELLOW)
        result["memory_error"] = True

    log("APP_API", f"📋 Art.15 data view: {user_key} — diary={result['diary_count']}, facts={len(result['memory_facts'])}", Fore.CYAN)
    return result


# ─── Helper: resolve user_id from key_info ────────────────────────────────────

def _resolve_user_id(key_info: dict) -> str:
    """Returns the real user_id (from session profile if available, else user_key)."""
    user_key = key_info["user_key"]
    try:
        from session import session_manager as _sm
        profile = _sm.users.get(user_key)
        if profile:
            return profile.user_id
    except Exception:
        pass
    return user_key


# ─── New endpoints ────────────────────────────────────────────────────────────

@router.get("/api/status")
async def get_status():
    """
    Simple liveness check — no auth required.
    App shows 'YourAI schläft 💤' when this returns an error or times out.
    """
    return {"online": True, "ts": time.time()}


@router.get("/api/chat/history")
async def get_chat_history(key: Optional[str] = None, limit: int = 50):
    """
    Clean chat history for the requesting user.
    Returns the last `limit` message pairs as [{role, text, ts, tracking_id}].
    Source: docker_data/app_chat_log.jsonl (persists across Docker rebuilds).
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    user_id = _resolve_user_id(key_info)
    entries = []
    try:
        if os.path.exists(_CHAT_LOG_FILE):
            with open(_CHAT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("user_id") == user_id:
                            entries.append(entry)
                    except Exception:
                        pass
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="chat_history")
        log_exception("APP_API", err)

    entries = entries[-limit:]
    messages = []
    for e in entries:
        messages.append({"role": "user",  "text": e["user_msg"],  "ts": e["ts"], "tracking_id": ""})
        messages.append({"role": "yourai", "text": e["yourai_msg"], "ts": e["ts"], "tracking_id": e.get("tracking_id", "")})

    return {"messages": messages, "total": len(entries)}


@router.get("/api/streak")
async def get_streak(key: Optional[str] = None):
    """
    Consecutive days the user has chatted with YourAI.
    Returns current streak, last active date, and total active days.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    user_id = _resolve_user_id(key_info)
    active_dates: set = set()

    try:
        if os.path.exists(_CHAT_LOG_FILE):
            with open(_CHAT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("user_id") == user_id:
                            ts = entry.get("ts", "")
                            if ts:
                                active_dates.add(ts[:10])  # "YYYY-MM-DD"
                    except Exception:
                        pass
    except Exception:
        pass

    today      = date.today()
    streak     = 0
    check      = today
    # If active today, count backwards; if not, check if yesterday starts a streak
    if str(today) not in active_dates:
        check = today - timedelta(days=1)
    while str(check) in active_dates:
        streak += 1
        check  -= timedelta(days=1)

    return {
        "streak":      streak,
        "last_active": max(active_dates) if active_dates else None,
        "total_days":  len(active_dates),
    }


@router.post("/api/app/fcm_token")
async def register_fcm_token(request: Request, key: Optional[str] = None):
    """
    Register or update a Firebase Cloud Messaging token for push notifications.
    Call on app start (and whenever FCM rotates the token).
    Body: {"fcm_token": "..."}
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    try:
        data = await request.json()
        token = (data.get("fcm_token") or "").strip()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger JSON Body")

    if not token:
        raise HTTPException(status_code=400, detail="fcm_token fehlt")

    user_id = _resolve_user_id(key_info)

    tokens: dict = {}
    if os.path.exists(_FCM_TOKENS_FILE):
        try:
            with open(_FCM_TOKENS_FILE, "r", encoding="utf-8") as f:
                tokens = json.load(f)
        except Exception:
            pass

    tokens[user_id] = token
    try:
        os.makedirs(os.path.dirname(_FCM_TOKENS_FILE), exist_ok=True)
        with open(_FCM_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="fcm_register")
        log_exception("APP_API", err)
        raise HTTPException(status_code=500, detail="Fehler beim Speichern des Tokens")

    log("APP_API", f"📱 FCM token registered for {user_id}", Fore.CYAN)
    return {"ok": True}
