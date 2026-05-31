"""
YourAI App API - Android & Mobile Endpoints
==========================================
FastAPI APIRouter that exposes all mobile-specific routes (versioning, mood,
uploads, GDPR/DSGVO data management, push notifications, and device linking).

Main Responsibilities:
- Serve as the interface for the mobile/Android app.
- Cleanly separate concerns by routing requests to sub-modules under app/.

Endpoints:
- GET    /api/app/version         - App update check (no auth, public)
- GET    /api/mood                - YourAI's current mood for app UI
- POST   /api/mobile/upload       - Upload image for chat (temp, 1h expiry)
- GET    /api/mobile/temp/{file}  - Serve uploaded temp image (no auth)
- DELETE /api/delete_my_data      - GDPR/DSGVO: delete diary entries by session UUID
- GET    /api/my_data             - GDPR/DSGVO: export user context summary
- GET    /api/status              - Liveness check (public)
- GET    /api/chat/history        - Retrieve recent chat message history
- GET    /api/streak              - Fetch user chat interaction streak
- POST   /api/app/fcm_token       - Register/update Firebase Push Token
- GET    /api/app/me              - Combined profile, mood, usage, and stats
- POST   /api/app/link/generate   - Generate pairing code for device linking
- POST   /api/app/link/claim      - Pair mobile device with dashboard account

Side Effects:
- Non-admin users get HTTP 503 JSON responses if maintenance mode is active.
"""

import os
import sys
import time

# =========================================================================
# Path Setup (needed when run standalone or in Docker)
# =========================================================================
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from typing import Optional, Annotated

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from display import log_exception
from exceptions import YourAIWebParseError
from app.auth import get_key_info, verify_access, maintenance_block
from app.chat_log import get_chat_history_payload, get_streak_payload
from app.identity import resolve_user_id
from app.linking import claim_app_link, generate_app_link
from app.mood import get_mood_payload
from app.profile import build_app_me_payload
from app.privacy import delete_user_data, get_user_data_summary
from app.push import register_fcm_token as save_fcm_token
from app.uploads import save_mobile_upload, serve_temp_upload
from app.versioning import get_app_version_payload

router = APIRouter()

AUTH_RESPONSES = {
    401: {"description": "Invalid or missing access key"},
    403: {"description": "Insufficient permissions"},
    503: {"description": "Maintenance mode is active"},
}


# =========================================================================
# Endpoints
# =========================================================================

@router.get("/api/app/version")
async def get_app_version():
    """
    Android app update check - no auth required (public meta endpoint).

    Returns the minimum required app version + MD5 hash.
    The app compares its own bundled version against 'version':
      - version matches  -> up to date
      - version differs  -> show update dialog
      - valid == false   -> tamper warning

    To force a new required version:
      1. Update app_version.txt  (e.g. "1.0.0+10002")
      2. Regenerate lock:
           compute the MD5 hash of app_version.txt and paste it into app_version.lock
      3. scp both + docker restart (no rebuild needed)

    Returns:
        dict: The required app version, expected hash, and integrity status.
    """
    return get_app_version_payload()


@router.get("/api/mood", responses=AUTH_RESPONSES)
async def get_mood(key: Optional[str] = None):
    """
    YourAI's current mood - for app UI header/avatar display.
    All roles allowed. Maintenance mode -> 503 JSON (not HTML).

    Args:
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: The current mood payload for the authenticated user, or a maintenance response.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    block = maintenance_block(key_info)
    if block:
        return block

    return get_mood_payload(resolve_user_id(key_info))


@router.post(
    "/api/mobile/upload",
    responses={
        **AUTH_RESPONSES,
        413: {"description": "Uploaded image exceeds the maximum size"},
        415: {"description": "Uploaded file type is not supported"},
        500: {"description": "Upload could not be saved"},
    },
)
async def mobile_upload(file: Annotated[UploadFile, File(...)], key: Optional[str] = None):
    """
    Upload a temp image from the app for use in chat.
    Multipart/form-data, field name: 'file'.
    Returns a temp URL valid for 1 hour.
    Max 10 MB, image/jpeg|png|gif|webp only.

    Args:
        file (UploadFile): The uploaded image file.
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: Upload metadata containing the temporary URL, filename, and byte size.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    block = maintenance_block(key_info)
    if block:
        return block

    return await save_mobile_upload(file)


@router.get("/api/mobile/temp/{filename}", responses={404: {"description": "Temporary image not found"}})
async def mobile_serve_temp(filename: str):
    """
    Serve a previously uploaded temp image.
    No auth required - UUID-based filename is unguessable.
    Used by brain.py and the app to retrieve uploaded images.

    Args:
        filename (str): The temporary upload filename to serve.

    Returns:
        FileResponse: The temporary image response.
    """
    return serve_temp_upload(filename) # Snyk False Positiv


@router.delete(
    "/api/delete_my_data",
    responses={
        **AUTH_RESPONSES,
        400: {"description": "X-Session-UUID header missing"},
        500: {"description": "User data could not be deleted"},
    },
)
async def delete_my_data(request: Request, key: Optional[str] = None):
    """
    GDPR/DSGVO Art. 17: Delete diary entries + memory facts for the requesting user.
    Diary: by session UUID (X-Session-UUID header).
    Memory: by user_id (resolved from API key -> session profile).

    Args:
        request (Request): The FastAPI request containing the X-Session-UUID header.
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: Deletion status and counters for local and memory-server data.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    block = maintenance_block(key_info)
    if block:
        return block

    session_uuid = request.headers.get("X-Session-UUID", "").strip()
    if not session_uuid:
        raise HTTPException(status_code=400, detail="X-Session-UUID header missing")

    user_id = resolve_user_id(key_info)
    return await delete_user_data(session_uuid, user_id)


@router.get("/api/my_data", responses=AUTH_RESPONSES)
async def get_my_data(request: Request, key: Optional[str] = None):
    """
    GDPR/DSGVO Art. 15: Return a summary of all stored data for the requesting user.
    Returns: diary_count (by user_id, cross-platform) + memory_facts (by user_id).

    Args:
        request (Request): The FastAPI request object reserved for future request-scoped metadata.
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: Data summary including diary counts and memory facts.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")

    user_key = key_info.get("user_key", "")
    user_id = resolve_user_id(key_info)
    return await get_user_data_summary(user_key, user_id)


# =========================================================================
# New Endpoints
# =========================================================================

@router.get("/api/status")
async def get_status():
    """
    Simple liveness check - no auth required.
    The app shows its offline state when this returns an error or times out.

    Returns:
        dict: Online status and current server timestamp.
    """
    return {"online": True, "ts": time.time()}


@router.get("/api/chat/history", responses=AUTH_RESPONSES)
async def get_chat_history(key: Optional[str] = None, limit: int = 50):
    """
    Clean chat history for the requesting user.
    Returns the last `limit` message pairs as [{role, text, ts, tracking_id}].
    Source: docker_data/app_chat_log.jsonl (persists across Docker rebuilds).

    Args:
        key (Optional[str]): The access key used to authenticate the mobile request.
        limit (int): The maximum number of persisted chat entries to include.

    Returns:
        dict: Chat history payload containing message pairs and total entry count.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    user_id = resolve_user_id(key_info)
    return get_chat_history_payload(user_id, limit)


@router.get("/api/streak", responses=AUTH_RESPONSES)
async def get_streak(key: Optional[str] = None):
    """
    Consecutive days the user has chatted with YourAI.
    Returns current streak, last active date, and total active days.

    Args:
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: Streak payload for the authenticated user.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    user_id = resolve_user_id(key_info)
    return get_streak_payload(user_id)


@router.post(
    "/api/app/fcm_token",
    responses={
        **AUTH_RESPONSES,
        400: {"description": "Invalid JSON body or fcm_token missing"},
        500: {"description": "Token could not be saved"},
    },
)
async def register_fcm_token(request: Request, key: Optional[str] = None):
    """
    Register or update a Firebase Cloud Messaging token for push notifications.
    Call on app start (and whenever FCM rotates the token).
    Body: {"fcm_token": "..."}

    Args:
        request (Request): The FastAPI request containing the JSON token body.
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: Registration status.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    try:
        data = await request.json()
        token = (data.get("fcm_token") or "").strip()
    except Exception as e:
        err = YourAIWebParseError("Invalid JSON body for FCM token registration", cause=e, module="app_api_fcm")
        log_exception("APP_API", err)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not token:
        raise HTTPException(status_code=400, detail="fcm_token missing")

    user_id = resolve_user_id(key_info)

    return save_fcm_token(user_id, token)


# =========================================================================
# APP /me - Combined profile, mood, usage, style, streak in ONE call
# ========================================================================= 

@router.get("/api/app/me", responses=AUTH_RESPONSES)
async def get_app_me(request: Request, key: Optional[str] = None):
    """
    All-in-one endpoint for the mobile app.
    Returns: profile, mood, token_usage, style_usage, image_usage, streak, platforms.
    Single HTTP call instead of 5+ separate requests.

    Args:
        request (Request): The FastAPI request containing optional session headers.
        key (Optional[str]): The access key used to authenticate the mobile request.

    Returns:
        dict: Consolidated mobile profile and usage payload.
    """
    key_info = get_key_info(key)
    verify_access(key, "chat")
    block = maintenance_block(key_info)
    if block:
        return block

    session_uuid = request.headers.get("X-Session-UUID", "").strip()
    return build_app_me_payload(key_info, session_uuid)

# =========================================================================
# Mobile Platform Linking - same code system as Discord /link
# ========================================================================= 

@router.post(
    "/api/app/link/generate",
    responses={
        **AUTH_RESPONSES,
        400: {"description": "User not recognized"},
    },
)
async def app_link_generate(key: Optional[str] = None):
    """
    Generate a one-time code for linking a mobile device.
    Called from the web dashboard - user enters the code in the app.
    Reuses the same code system as Discord's /link command.

    Args:
        key (Optional[str]): The access key used to authenticate the dashboard request.

    Returns:
        dict: Link code payload with expiry and user metadata.
    """
    verify_access(key, "chat")
    key_info = get_key_info(key)
    user_key = key_info["user_key"] if key_info else None
    if not user_key:
        raise HTTPException(status_code=400, detail="User not recognized")

    return generate_app_link(user_key)


@router.post(
    "/api/app/link/claim",
    responses={
        400: {"description": "Invalid JSON body, code missing, or device_id missing"},
        404: {"description": "Link code is invalid or expired"},
        500: {"description": "Access key could not be saved"},
    },
)
async def app_link_claim(request: Request):
    """
    Mobile app sends a link code + device_id to claim its connection.
    No auth required (the code IS the auth - like Discord's /link).

    Body: {"code": "YOURAI-XXXXXX", "device_id": "unique-device-uuid"}

    Returns:
      - access_key: a fresh chat-level key for the app to store
      - user_key, display_name: who the app is now linked to

    Args:
        request (Request): The FastAPI request containing the link code and device ID.

    Returns:
        dict: Claim result containing the generated access key and linked user metadata.
    """
    try:
        data = await request.json()
        code = (data.get("code") or "").strip().upper()
        device_id = (data.get("device_id") or "").strip()
    except Exception as e:
        err = YourAIWebParseError("Invalid JSON body for app link claim", cause=e, module="app_api_link_claim")
        log_exception("APP_API", err)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not code:
        raise HTTPException(status_code=400, detail="code missing")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id missing")

    return claim_app_link(code, device_id)
