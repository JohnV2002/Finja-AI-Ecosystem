"""
YourAI Dashboard v6 — Frontend Edition
======================================
- Echtes Frontend in frontend/ (HTML + CSS + JS)
- brain.py als managed Subprocess (Start / Stop / Restart per Button)
- Config API: liest USE_* flags, schreibt runtime_config.json
- Alle bestehenden Endpoints bleiben kompatibel

Run: python dashboard_server.py
Open: http://localhost:8051
"""

import _paths  # noqa: F401 — Subdirectories zum Python-Path hinzufügen

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
import json
import os
import sys
import subprocess
import time
import uuid as _uuid_mod
import uvicorn
from fastapi import HTTPException, status

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError
from feedback import FeedbackStore
from dashboard_client import DashboardClient

from config import (
    DASHBOARD_MAX_EVENTS, DASHBOARD_DEFAULT_USER, DASHBOARD_DEFAULT_MODE,
    TTS_VOLUME_CONFIG_FILE, DEBUG_LOG_FILE, DEBUG_LOG_MAX_LINES,
    YOURAI_OUTPUT_FILE
)

# ==========================================
# SESSION MANAGER IMPORT
# ==========================================

# Dummy class falls session.py nicht existiert
class DummySessionManager:
    """Fallback wenn session.py nicht vorhanden."""
    def get_current_user(self, source: str = "console") -> str:
        return "Admin (Admin)"
    def get_current_user_id(self, source: str = "console") -> str:
        return "admin"
    def switch_user(self, user_key: str, source: str = "console") -> str:
        return "Session Manager nicht verfügbar"
    def get_mode(self, source: str = "console") -> str:
        return "yourai"
    def set_mode(self, mode: str, source: str = "console") -> str:
        return "Session Manager nicht verfügbar"
    def is_altpersona_mode(self, source: str = "console") -> bool:
        return False
    @property
    def users(self) -> dict:
        return {"admin": type('obj', (object,), {'display_name': 'Admin (Admin)', 'role': 'admin'})()}

session_manager: Any = DummySessionManager()
PREDEFINED_USERS: Dict[str, Any] = {}
SESSION_AVAILABLE = False

try:
    from session import session_manager as _sm, PREDEFINED_USERS as _pu
    session_manager = _sm
    PREDEFINED_USERS = _pu
    SESSION_AVAILABLE = True
    log("DASHBOARD", "[OK] Session Manager geladen!", Fore.GREEN)
except ImportError:
    log("DASHBOARD", "[!] Session Manager nicht gefunden - User-Switching deaktiviert", Fore.YELLOW)

# ==========================================
# SESSION HELPERS
# ==========================================

def _resolve_session_profile(user_key: str):
    """Find a session profile by user_key — tries exact, case-insensitive, and display_name match."""
    if not SESSION_AVAILABLE:
        return None
    # Exact match
    profile = session_manager.users.get(user_key)
    if profile:
        return profile
    # Case-insensitive key match
    for k, p in session_manager.users.items():
        if k.lower() == user_key.lower():
            return p
    return None

# ==========================================
# ACCESS CONTROL  (shared via app/auth.py)
# ==========================================

from app.auth import (
    load_access_keys, get_key_info, get_role_for_key,
    verify_access, is_maintenance_mode,
)

# ==========================================
# DATA MODELS
# ==========================================

class EventType(str, Enum):
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    NODE_START = "node_start"
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    LLM_CALL = "llm_call"
    LLM_THINKING = "llm_thinking"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"
    MEMORY_SEARCH = "memory_search"
    MEMORY_FOUND = "memory_found"
    MEMORY_SAVE = "memory_save"
    SYSTEM_INFO = "system_info"
    SYSTEM_ERROR = "system_error"
    USER_SWITCH = "user_switch"
    SYSTEM_PROMPT = "system_prompt"  # NEU: Full system prompt dump
    USER_MESSAGE = "user_message"    # NEU: Full user message dump
    PROMISE_EVENT = "promise_event"  # NEU: Promise made/broken/fulfilled
    IMAGE_READY = "image_ready"      # NEU: Image generation completed

@dataclass
class DebugEvent:
    event_type: EventType
    node_name: str
    timestamp: str
    title: str
    content: Optional[str] = None
    thinking: Optional[str] = None
    raw_output: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    input_data: Optional[str] = None
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    tracking_id: Optional[str] = None
    source: Optional[str] = None        # "web", "discord", "discord_dm", ...
    for_user: Optional[str] = None      # user_key this response is for
    image_url: Optional[str] = None     # für image_ready events
    status: str = "info"

# ==========================================
# EVENT STORE & WEBSOCKET MANAGER
# ==========================================

@dataclass
class ConnectionInfo:
    """Per-WebSocket connection metadata (locked to access key)."""
    websocket: Any  # WebSocket
    role: str       # "admin", "debug", "chat"
    user_key: str   # locked user_key from access_keys.json
    can_altpersona: bool = False  # darf dieser Key AltPersona-Mode nutzen?

class DashboardState:
    def __init__(self):
        self.events: List[DebugEvent] = []
        self.connections: Dict[WebSocket, ConnectionInfo] = {}
        self.input_queue: asyncio.Queue = asyncio.Queue()
        self.max_events = DASHBOARD_MAX_EVENTS
        self._load_from_log()  # Restore events from disk

        # Reset all user modes on startup (matches brain.py input_loop reset)
        if SESSION_AVAILABLE:
            session_manager.user_modes = {}
            session_manager._default_mode = DASHBOARD_DEFAULT_MODE
            session_manager._save()

    # ─── JSONL Persistence ──────────────────────────────────────
    def _load_from_log(self):
        """Load persisted events from debug_log.jsonl on startup."""
        if not os.path.exists(DEBUG_LOG_FILE):
            log("DASHBOARD", "[DEBUG-LOG] No log file found — starting fresh", Fore.YELLOW)
            return
        try:
            loaded = []
            with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        d["event_type"] = EventType(d["event_type"])
                        loaded.append(DebugEvent(**d))
                    except Exception:
                        continue  # Skip corrupt lines
            # Keep only the last max_events
            self.events = loaded[-self.max_events:]
            log("DASHBOARD", f"[DEBUG-LOG] Restored {len(self.events)} events from disk ({len(loaded)} total in file)", Fore.GREEN)
        except Exception as e:
            log("DASHBOARD", f"[DEBUG-LOG] Failed to load log: {e}", Fore.RED)

    def _persist_event(self, event: DebugEvent):
        """Append a single event to the JSONL log file."""
        try:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        except Exception as e:
            log("DASHBOARD", f"[DEBUG-LOG] Write error: {e}", Fore.RED)

    def _maybe_rotate_log(self):
        """Rotate log file if it exceeds max lines (keep last half)."""
        try:
            if not os.path.exists(DEBUG_LOG_FILE):
                return
            with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= DEBUG_LOG_MAX_LINES:
                return
            # Keep last half
            keep = lines[-(DEBUG_LOG_MAX_LINES // 2):]
            with open(DEBUG_LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(keep)
            log("DASHBOARD", f"[DEBUG-LOG] Rotated: {len(lines)} → {len(keep)} lines", Fore.CYAN)
        except Exception as e:
            log("DASHBOARD", f"[DEBUG-LOG] Rotation error: {e}", Fore.RED)

    async def connect(self, websocket: WebSocket, role: str, user_key: str, can_altpersona: bool = False):
        await websocket.accept()
        conn = ConnectionInfo(websocket=websocket, role=role, user_key=user_key, can_altpersona=can_altpersona)
        self.connections[websocket] = conn

        # Send user info scoped to this connection
        await websocket.send_json({
            "type": "user_info",
            "data": self._get_user_info(conn)
        })

        # Send recent events (filtered!) — admins get 200, chat users get 50
        replay_count = 200 if conn.role == "admin" else 50
        for event in self.events[-replay_count:]:
            if self._can_see_event(conn, event):
                await websocket.send_json({"type": "event", "data": asdict(event)})

    def _can_see_event(self, conn: ConnectionInfo, event: DebugEvent) -> bool:
        """Check if this connection is allowed to see this event."""
        # Admins see everything
        if conn.role == "admin":
            return True
        # Resolve this connection's user_id (for_user uses user_id, not user_key)
        conn_user_id = conn.user_key
        try:
            if SESSION_AVAILABLE:
                _prof = session_manager.users.get(conn.user_key)
                if _prof:
                    conn_user_id = _prof.user_id
        except Exception:
            pass
        # pipeline_start → typing indicator for chat users, filtered by for_user
        if event.event_type == EventType.PIPELINE_START:
            if conn.role == "chat":
                if event.for_user is None:
                    return False
                fu = str(event.for_user).lower()
                return fu == str(conn.user_key).lower() or fu == str(conn_user_id).lower()
            return conn.role in ("debug", "admin")
        # pipeline_end (chat responses) → only if it's for THIS user
        if event.event_type == EventType.PIPELINE_END:
            if event.for_user is None or conn.user_key is None:
                return False
            fu = str(event.for_user).lower()
            return fu == str(conn.user_key).lower() or fu == str(conn_user_id).lower()
        # image_ready → same filter as pipeline_end (user sees their own images)
        if event.event_type == EventType.IMAGE_READY:
            if event.for_user is None or conn.user_key is None:
                return False
            fu = str(event.for_user).lower()
            return fu == str(conn.user_key).lower() or fu == str(conn_user_id).lower()
        # Chat users ONLY see their own pipeline_end + image_ready events
        if conn.role == "chat":
            return False
        # Debug role sees all non-pipeline debug events
        return conn.role == "debug"

    def _get_user_info(self, conn: ConnectionInfo) -> dict:
        """User-Info scoped to this connection's permissions."""
        if SESSION_AVAILABLE:
            user_display = "Unknown"
            try:
                profile = session_manager.users.get(conn.user_key)
                user_display = profile.display_name if profile else conn.user_key
            except Exception:
                user_display = conn.user_key

            # Resolve user_id (used in for_user on events) for frontend matching
            _uid = conn.user_key
            try:
                _prof = session_manager.users.get(conn.user_key)
                if _prof:
                    _uid = _prof.user_id
            except Exception:
                pass
            info = {
                "current_user": user_display,
                "current_user_key": conn.user_key,
                "current_user_id": _uid,
                "current_mode": session_manager.user_modes.get(conn.user_key, session_manager._default_mode),
                "can_switch_user": conn.role == "admin",
            }
            # Only admin gets the full user list
            if conn.role == "admin":
                info["available_users"] = [
                    {"key": k, "user_id": v.user_id, "name": v.display_name, "role": v.role}
                    for k, v in session_manager.users.items()
                ]
            else:
                # Non-admin only sees themselves
                profile = session_manager.users.get(conn.user_key)
                if profile:
                    info["available_users"] = [
                        {"key": conn.user_key, "name": profile.display_name, "role": profile.role}
                    ]
                else:
                    info["available_users"] = [
                        {"key": conn.user_key, "name": conn.user_key, "role": "guest"}
                    ]
            return info
        return {
            "current_user": conn.user_key,
            "current_user_key": conn.user_key,
            "current_mode": "yourai",
            "can_switch_user": conn.role == "admin",
            "available_users": [{"key": conn.user_key, "name": conn.user_key, "role": "guest"}]
        }

    def disconnect(self, websocket: WebSocket):
        self.connections.pop(websocket, None)

    async def broadcast(self, event: DebugEvent):
        """Broadcast event — filtered per connection's permissions."""
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

        # Persist to disk
        self._persist_event(event)
        # Check rotation every 500 events
        if len(self.events) % 500 == 0:
            self._maybe_rotate_log()

        dead = []
        for ws, conn in self.connections.items():
            if not self._can_see_event(conn, event):
                continue
            try:
                await ws.send_json({"type": "event", "data": asdict(event)})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_message(self, msg_type: str, data: dict, only_admins: bool = False):
        """Send a message to connections. If only_admins, skip non-admin."""
        dead = []
        for ws, conn in self.connections.items():
            if only_admins and conn.role != "admin":
                continue
            try:
                await ws.send_json({"type": msg_type, "data": data})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_connection(self, websocket: WebSocket, msg_type: str, data: dict):
        """Send directly to one connection."""
        try:
            await websocket.send_json({"type": msg_type, "data": data})
        except Exception:
            self.disconnect(websocket)

    async def broadcast_error(self, title: str, error_msg: str, stack: Optional[str] = None):
        """Broadcasts a dashboard-internal error without feeding it to YourAI."""
        event = DebugEvent(
            event_type=EventType.SYSTEM_ERROR,
            node_name="dashboard",
            timestamp=datetime.now().strftime("%H:%M:%S"),
            title=title,
            error=error_msg,
            stack_trace=stack,
            status="error"
        )
        await self.broadcast(event)

    async def switch_user(self, websocket: WebSocket, user_key: str):
        """Admin-only: switch the active user for this connection."""
        conn = self.connections.get(websocket)
        if not conn or conn.role != "admin":
            await self.send_to_connection(websocket, "error", {"message": "Keine Berechtigung zum User-Wechseln."})
            return "Keine Berechtigung"

        conn.user_key = user_key

        if SESSION_AVAILABLE:
            result = session_manager.switch_user(user_key, "web")

            event = DebugEvent(
                event_type=EventType.USER_SWITCH,
                node_name="session",
                timestamp=datetime.now().strftime("%H:%M:%S"),
                title=f"[USER] User gewechselt: {session_manager.get_current_user('web')}",
                content=result,
                status="info"
            )
            await self.broadcast(event)

            # Only inform this admin's connection
            await self.send_to_connection(websocket, "user_changed", self._get_user_info(conn))
            return result
        return "Session Manager nicht verfügbar"

    async def create_user(self, websocket: WebSocket, user_key: str, display_name: str, role: str, description: str):
        """Admin-only: create a new user."""
        conn = self.connections.get(websocket)
        if not conn or conn.role != "admin":
            return "Keine Berechtigung"

        if SESSION_AVAILABLE:
            result = session_manager.create_user(
                user_key=user_key,
                display_name=display_name,
                role=role,
                description=description
            )

            event = DebugEvent(
                event_type=EventType.USER_SWITCH,
                node_name="session",
                timestamp=datetime.now().strftime("%H:%M:%S"),
                title=f"[USER] Neuer Account erstellt: {display_name}",
                content=result,
                status="info"
            )
            await self.broadcast(event)
            await self.send_to_connection(websocket, "user_info", self._get_user_info(conn))
            return result
        return "Session Manager nicht verfügbar"

    async def switch_mode(self, mode: str, user_key: str = "admin"):
        """Wechselt den Mode (yourai/altpersona) für einen bestimmten User."""
        if SESSION_AVAILABLE:
            # Set mode for this specific user's web source
            session_manager.user_modes[user_key] = mode
            session_manager._save()

            mode_tag = "[ALTPERSONA]" if mode == "altpersona" else "[YOURAI]"
            result = f"{mode_tag} Mode für {user_key}: {mode.upper()}"

            event = DebugEvent(
                event_type=EventType.USER_SWITCH,
                node_name="session",
                timestamp=datetime.now().strftime("%H:%M:%S"),
                title=f"{mode_tag} Mode gewechselt: {user_key} → {mode.upper()}",
                content=result,
                status="info"
            )
            await self.broadcast(event)

            # Mode change → nur den betroffenen User informieren
            for ws, conn in self.connections.items():
                if conn.user_key == user_key:
                    await self.send_to_connection(ws, "mode_changed", self._get_user_info(conn))
            return result
        return "Session Manager nicht verfügbar"

    def get_user_key_for(self, websocket: WebSocket) -> str:
        """Get the locked user_key for a connection."""
        conn = self.connections.get(websocket)
        return conn.user_key if conn else DASHBOARD_DEFAULT_USER

    def clear(self):
        self.events = []

    async def broadcast_clear(self):
        """Tell all connected clients to wipe their debug tab."""
        dead = []
        for ws in list(self.connections):
            try:
                await ws.send_json({"type": "clear_events"})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

state = DashboardState()

# ==========================================
# FASTAPI APP
# ==========================================

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_BASE_DIR, "frontend")

# ==========================================
# APP VERSION (für Cache-Busting)
# Startup-Timestamp: ändert sich automatisch bei jedem docker up / Server-Neustart
# ==========================================

import re as _re

_APP_VERSION = datetime.now().strftime("%Y%m%d%H%M%S")

app = FastAPI(title="YourAI Dashboard v6")

# ==========================================
# BEARER AUTH MIDDLEWARE
# ==========================================
# Accepts "Authorization: Bearer <key>" and injects it as ?key= query param.
# This lets all existing endpoints keep working unchanged while the frontend
# sends headers instead of URL params (keys stay out of browser history/logs).
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urlencode

class BearerToQueryParam(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and not request.query_params.get("key"):
            bearer_key = auth[7:].strip()
            params = dict(request.query_params)
            params["key"] = bearer_key
            # Modify scope in-place — call_next picks it up from the same scope dict
            request.scope["query_string"] = urlencode(params).encode("utf-8")
        return await call_next(request)

app.add_middleware(BearerToQueryParam)

# ==========================================
# WEBSOCKET MANAGER
# ==========================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, key: Optional[str] = None):
    key_info = get_key_info(key)
    if not key_info:
        await websocket.accept()
        await websocket.send_json({"type": "auth_error", "data": "Access Denied: Invalid Key"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    role = key_info["role"]
    user_key = key_info["user_key"]
    can_altpersona = key_info.get("can_altpersona", False)

    await state.connect(websocket, role=role, user_key=user_key, can_altpersona=can_altpersona)

    # Send permissions to frontend (incl. locked user_key)
    import config as _cfg
    _overrides = _load_runtime_overrides()
    _maintenance_active = _overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False))
    await websocket.send_json({
        "type": "permissions",
        "data": {
            "role": role,
            "user_key": user_key,
            "can_switch_user": role == "admin",
            "can_create_user": role == "admin",
            "can_altpersona": can_altpersona,
            "maintenance": bool(_maintenance_active),
        }
    })
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "clear":
                if role in ("admin", "debug"):
                    state.clear()
            elif msg.get("type") == "user_input":
                text = msg.get("text", "")
                image_urls = msg.get("image_urls") or []
                if text.strip() or image_urls:
                    # Block non-admins during maintenance
                    import config as _cfg
                    _overrides = _load_runtime_overrides()
                    _maintenance = _overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False))
                    if _maintenance and role != "admin":
                        await state.send_to_connection(websocket, "maintenance_error", {})
                    else:
                        # Queue includes the locked user_key + session_uuid from THIS connection
                        conn_user = state.get_user_key_for(websocket)
                        session_uuid = msg.get("session_uuid", "")
                        await state.input_queue.put({"text": text, "user_key": conn_user, "image_urls": image_urls, "session_uuid": session_uuid})
                        # Only echo back to this connection (not everyone)
                        await state.send_to_connection(websocket, "input_received", {
                            "text": text[:50] + "..." if len(text) > 50 else text,
                            "user": conn_user
                        })
            elif msg.get("type") == "switch_user":
                # Admin only!
                user_key_req = msg.get("user_key", "admin")
                await state.switch_user(websocket, user_key_req)
            elif msg.get("type") == "switch_mode":
                conn = state.connections.get(websocket)
                if conn and conn.can_altpersona:
                    mode = msg.get("mode", "yourai")
                    await state.switch_mode(mode, user_key=conn.user_key)
                else:
                    await state.send_to_connection(websocket, "error",
                        {"message": "AltPersona-Mode ist für diesen Key nicht freigeschaltet."})
            elif msg.get("type") == "feedback":
                tid = msg.get("tracking_id")
                rating = msg.get("rating")
                if tid and rating:
                    fb = FeedbackStore()
                    ok = fb.rate(tid, rating)
                    await websocket.send_json({
                        "type": "feedback_ack",
                        "data": {"tracking_id": tid, "rating": rating, "ok": ok}
                    })
            elif msg.get("type") == "get_users":
                conn = state.connections.get(websocket)
                if conn:
                    await websocket.send_json({
                        "type": "user_info",
                        "data": state._get_user_info(conn)
                    })
    except WebSocketDisconnect:
        state.disconnect(websocket)

@app.post("/event")
async def post_event(event: Dict[str, Any]):
    # Note: Event posting remains open for local brain.py communication
    # (Usually restricted to localhost anyway)
    debug_event = DebugEvent(
        event_type=EventType(event.get("event_type", "system_info")),
        node_name=event.get("node_name", "unknown"),
        timestamp=event.get("timestamp", datetime.now().strftime("%H:%M:%S")),
        title=event.get("title", "Event"),
        content=event.get("content"),
        thinking=event.get("thinking"),
        raw_output=event.get("raw_output"),
        model=event.get("model"),
        duration_ms=event.get("duration_ms"),
        input_data=event.get("input_data"),
        error=event.get("error"),
        stack_trace=event.get("stack_trace"),
        tracking_id=event.get("tracking_id"),
        source=event.get("source"),
        for_user=event.get("for_user"),
        image_url=event.get("image_url"),
        status=event.get("status", "info")
    )
    await state.broadcast(debug_event)
    return {"status": "ok"}

@app.get("/api/debug/history")
async def get_debug_history(
    key: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    user: Optional[str] = None,
    event_type: Optional[str] = None,
):
    """Paginated debug event history (admin only). Newest first."""
    verify_access(key, "admin")
    # Filter events
    filtered = state.events
    if user:
        filtered = [e for e in filtered if e.for_user == user or e.source == user]
    if event_type:
        filtered = [e for e in filtered if e.event_type.value == event_type]
    # Reverse (newest first), then paginate
    filtered = list(reversed(filtered))
    page = filtered[offset:offset + limit]
    return {
        "events": [asdict(e) for e in page],
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(filtered),
    }

@app.delete("/api/debug/clear-log")
async def clear_debug_log(key: Optional[str] = None):
    """Löscht debug_log.jsonl + in-memory Events + broadcastet clear an alle Clients (admin only)."""
    verify_access(key, "admin")
    state.clear()
    await state.broadcast_clear()
    try:
        if os.path.exists(DEBUG_LOG_FILE):
            open(DEBUG_LOG_FILE, "w").close()  # Truncate to empty
        log("DASHBOARD", "[DEBUG-LOG] Log geleert (admin request)", Fore.YELLOW)
        return {"ok": True, "message": "Debug log geleert"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/debug/download-log")
async def download_debug_log(key: Optional[str] = None):
    """Download debug_log.jsonl als Datei (admin only)."""
    verify_access(key, "admin")
    if not os.path.exists(DEBUG_LOG_FILE):
        raise HTTPException(status_code=404, detail="Log-Datei nicht gefunden")
    from datetime import datetime as _dt
    filename = f"debug_log_{_dt.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    return FileResponse(
        path=DEBUG_LOG_FILE,
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/yourai/download-output")
async def download_yourai_output(key: Optional[str] = None):
    """Download yourai_output.txt — YourAIs Antworten 1:1 (admin only)."""
    verify_access(key, "admin")
    if not os.path.exists(YOURAI_OUTPUT_FILE):
        raise HTTPException(status_code=404, detail="yourai_output.txt existiert noch nicht — YourAI hat noch nicht geantwortet")
    from datetime import datetime as _dt
    filename = f"yourai_output_{_dt.now().strftime('%Y%m%d_%H%M%S')}.txt"
    size_mb = os.path.getsize(YOURAI_OUTPUT_FILE) / (1024 * 1024)
    log("DASHBOARD", f"[EXPORT] yourai_output.txt Download — {size_mb:.1f} MB", Fore.CYAN)
    return FileResponse(
        path=YOURAI_OUTPUT_FILE,
        filename=filename,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/get_input")
async def get_input():
    try:
        item = state.input_queue.get_nowait()
        # item is now a dict: {"text": ..., "user_key": ..., "image_urls": [...]}
        return {
            "has_input": True,
            "text": item["text"],
            "user_key": item["user_key"],
            "image_urls": item.get("image_urls", []),
            "session_uuid": item.get("session_uuid", ""),
        }
    except asyncio.QueueEmpty:
        return {
            "has_input": False,
            "text": None,
            "user_key": None
        }

@app.get("/events")
async def get_events():
    return [asdict(e) for e in state.events]

@app.post("/clear")
async def clear_events():
    state.clear()
    return {"status": "cleared"}

@app.get("/users")
async def get_users():
    """API Endpoint für User-Liste."""
    return state._get_user_info()

@app.post("/switch_user/{user_key}")
async def switch_user_api(user_key: str, key: Optional[str] = None):
    """API Endpoint zum User-Wechseln (Admin only)."""
    verify_access(key, "admin")
    if SESSION_AVAILABLE:
        try:
            result = session_manager.switch_user(user_key, "web")
            return {"status": "ok", "message": result}
        except Exception as e:
            import traceback
            await state.broadcast_error(f"Error switching to user '{user_key}'", str(e), traceback.format_exc())
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Session Manager nicht verfügbar"}

@app.post("/switch_mode/{mode}")
async def switch_mode_api(mode: str, key: Optional[str] = None):
    """API Endpoint zum Mode-Wechseln (yourai/altpersona)."""
    # Determine user_key from access key
    user_key = "admin"
    if key:
        ak = _load_access_keys()
        entry = ak.get(key)
        if entry:
            user_key = entry.get("user_key", "admin")
    result = await state.switch_mode(mode, user_key=user_key)
    return {"status": "ok", "message": result}

@app.post("/api/create_user")
async def create_user_api(request: Request, key: Optional[str] = None):
    """API Endpoint zum Erstellen eines neuen Users (Admin only)."""
    verify_access(key, "admin")
    try:
        data = await request.json()
        user_key = data.get("user_key")
        display_name = data.get("display_name")
        role = data.get("role", "human_guest")
        description = data.get("description", "")
        
        grant_dashboard = data.get("grant_dashboard", False)
        access_key = data.get("access_key", "")
        access_role = data.get("access_role", "chat")
        can_altpersona = data.get("can_altpersona", False)

        if not user_key:
            return {"status": "error", "message": "User-Key (ID) ist erforderlich."}

        if SESSION_AVAILABLE:
            result = session_manager.create_user(
                user_key=user_key,
                display_name=display_name,
                role=role,
                description=description
            )
            
            # Dashboard Access in access_keys.json anlegen
            if grant_dashboard and access_key:
                keys = load_access_keys()
                keys[access_key] = {
                    "role": access_role,
                    "user_key": user_key,
                    "can_altpersona": can_altpersona,
                    "description": f"Autocreated for {display_name}"
                }
                # Speichern
                try:
                    with open(ACCESS_KEYS_FILE, "w") as f:
                        json.dump(keys, f, indent=2)
                except Exception as e:
                    return {"status": "warning", "message": f"{result} - ABER access_keys.json speichern fehlgeschlagen: {e}"}

            return {"status": "ok", "message": result}
        return {"status": "error", "message": "Session Manager nicht verfügbar"}
    except Exception as e:
        import traceback
        await state.broadcast_error(f"Error creating user '{user_key}'", str(e), traceback.format_exc())
        return {"status": "error", "message": str(e)}


# ==========================================
# USER PROFILE API
# ==========================================

@app.get("/api/user/me")
async def get_user_me(key: Optional[str] = None):
    """Returns the current user's profile and usage stats (all roles)."""
    verify_access(key, "chat")
    key_info = get_key_info(key)
    user_key = key_info["user_key"]
    access_role = key_info["role"]
    can_altpersona = key_info.get("can_altpersona", False)

    # Session profile
    display_name = user_key
    session_role = "guest"
    description = ""
    user_id = user_key

    if SESSION_AVAILABLE:
        profile = session_manager.users.get(user_key)
        if profile:
            display_name = profile.display_name
            session_role = profile.role
            description = profile.description
            user_id = profile.user_id

    # Image usage
    try:
        from tools.image_limits import get_usage as get_image_usage
        image_usage = get_image_usage(user_id, session_role)
    except Exception as e:
        log("DASHBOARD", f"[!] Could not load image usage for {user_key}: {e}", Fore.YELLOW)
        image_usage = {"used": 0, "limit": 0, "remaining": 0, "month": "", "unlimited": False}

    # TTS Premium usage (ElevenLabs)
    try:
        from tools.tts_limits import get_usage as get_tts_usage, get_yourai_usage
        tts_usage = get_tts_usage(user_id, session_role)
        yourai_tts_usage = get_yourai_usage(user_id)
    except Exception as e:
        log("DASHBOARD", f"[!] Could not load TTS usage for {user_key}: {e}", Fore.YELLOW)
        tts_usage = {"used": 0, "limit": 3, "remaining": 3, "month": "", "unlimited": False}
        yourai_tts_usage = {"used": 0, "month": ""}

    return {
        "user_key": user_key,
        "display_name": display_name,
        "session_role": session_role,
        "access_role": access_role,
        "description": description,
        "can_altpersona": can_altpersona,
        "image_usage": image_usage,
        "tts_usage": tts_usage,
        "yourai_tts_usage": yourai_tts_usage,
    }



# /api/delete_my_data → moved to app/app_api.py (included via router)


# ==========================================
# TTS API
# ==========================================

@app.post("/api/tts")
async def tts_api(request: Request, key: Optional[str] = None):
    """
    Text-to-Speech endpoint — 3 Tiers:
      browser    → client-side only, returns 204
      yourai      → Zonos v0.1 via OpenRouter (Voice Cloning), returns audio/wav
      elevenlabs → ElevenLabs Premium, returns audio/mpeg
    """
    from fastapi.responses import Response as FastAPIResponse
    verify_access(key, "chat")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    text = (data.get("text") or "").strip()
    tier = (data.get("tier") or "browser").lower()
    lang = (data.get("lang") or "de").lower()

    if not text:
        raise HTTPException(status_code=400, detail="Text ist leer")

    if tier == "browser":
        return FastAPIResponse(status_code=204)

    if tier == "yourai":
        from config import DEEPINFRA_API_KEY
        if not DEEPINFRA_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="YourAI-Stimme (Chatterbox) nicht verfügbar — DEEPINFRA_API_KEY fehlt 🦊"
            )
        try:
            from tools.tts_yourai import generate_speech as yourai_tts
            audio_bytes = await asyncio.get_event_loop().run_in_executor(
                None, yourai_tts, text, lang
            )
            # Record Chatterbox usage (no limit, just tracking)
            try:
                from tools.tts_limits import record_yourai_usage
                record_yourai_usage(user_id)
            except Exception:
                pass
            return FastAPIResponse(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={"Cache-Control": "no-store"},
            )
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"YourAI TTS: {str(e)[:300]}")

    if tier == "elevenlabs":
        from config import ELEVENLABS_API_KEY
        if not ELEVENLABS_API_KEY:
            raise HTTPException(status_code=503, detail="ElevenLabs nicht konfiguriert")

        # Limit check
        key_info = get_key_info(key)
        user_key = key_info["user_key"]
        session_role = "guest"
        user_id = user_key
        if SESSION_AVAILABLE:
            profile = session_manager.users.get(user_key)
            if profile:
                session_role = profile.role
                user_id = profile.user_id

        from tools.tts_limits import can_use_premium, record_usage as record_tts
        allowed, remaining, limit = can_use_premium(user_id, session_role)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Deine {limit} kostenlosen Premium-Stimmen für diesen Monat sind aufgebraucht! 🎤",
                headers={"X-TTS-Remaining": "0", "X-TTS-Limit": str(limit)},
            )

        try:
            from tools.tts_elevenlabs import generate_speech
            audio_bytes = await asyncio.get_event_loop().run_in_executor(
                None, generate_speech, text, lang
            )
            record_tts(user_id)
            remaining_after = max(0, remaining - 1)
            return FastAPIResponse(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={
                    "Cache-Control": "no-store",
                    "X-TTS-Remaining": str(remaining_after),
                    "X-TTS-Limit": str(limit) if limit != -1 else "unlimited",
                },
            )
        except Exception as e:
            import traceback
            err_msg = str(e)
            log("DASHBOARD", f"[TTS] ElevenLabs Error: {err_msg}", Fore.RED)
            await state.broadcast_error("TTS ElevenLabs Error", err_msg, traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"TTS Fehler: {err_msg}")

    raise HTTPException(status_code=400, detail=f"Unbekannter Tier: {tier}")


# ==========================================
# VOLUME CONTROL API
# ==========================================

VOLUME_CONFIG_FILE = TTS_VOLUME_CONFIG_FILE

@app.get("/get_volume")
async def get_volume_api(key: Optional[str] = None):
    """Get current TTS volume."""
    verify_access(key, "chat")  # Jeder darf die Lautstärke sehen
    try:
        if os.path.exists(VOLUME_CONFIG_FILE):
            with open(VOLUME_CONFIG_FILE, "r") as f:
                data = json.load(f)
                return {"volume": int(data.get("volume", 0.5) * 100)}
    except Exception as e:
        import traceback
        err = YourAIUnexpectedError(cause=e, module="dashboard_server_volume_get")
        log_exception("DASHBOARD", err)
        await state.broadcast_error("Volume API Error", str(e), traceback.format_exc())
    return {"volume": 50}

@app.post("/set_volume")
async def set_volume_api(request: Request, key: Optional[str] = None):
    """Set TTS volume (0-100)."""
    verify_access(key, "debug")  # Nur Debug/Admin dürfen Lautstärke ändern
    try:
        data = await request.json()
        volume_percent = data.get("volume", 50)
        volume_float = max(0.0, min(1.0, volume_percent / 100))
        with open(VOLUME_CONFIG_FILE, "w") as f:
            json.dump({"volume": volume_float}, f)
        log("DASHBOARD", f"🔊 TTS Volume set to {volume_percent}%", Fore.CYAN)
        volume_event = DebugEvent(
            event_type=EventType.SYSTEM_INFO,
            node_name="tts",
            timestamp=datetime.now().strftime("%H:%M:%S"),
            title=f"🔊 TTS Volume: {volume_percent}%",
            status="success"
        )
        await state.broadcast(volume_event)
        return {"success": True, "volume": volume_percent}
    except Exception as e:
        import traceback
        err = YourAIUnexpectedError(cause=e, module="dashboard_server_volume_set")
        log_exception("DASHBOARD", err)
        await state.broadcast_error("Volume API Error", str(e), traceback.format_exc())
        return {"success": False, "error": str(e)}


# ==========================================
# PROCESS MANAGER (brain.py as subprocess)
# ==========================================

class ProcessManager:
    """Manages brain.py as a child subprocess."""

    BRAIN_SCRIPT = os.path.join(_BASE_DIR, "core", "brain.py")
    RUNTIME_CONFIG = os.path.join(_BASE_DIR, "runtime_config.json")

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._started_at: Optional[float] = None

    def start(self) -> bool:
        if self.is_running():
            return False
        python_exe = sys.executable
        # CREATE_NEW_PROCESS_GROUP so we can kill brain + all its children
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        kwargs = {"creationflags": creationflags} if sys.platform == "win32" else {"start_new_session": True}
        self._proc = subprocess.Popen(
            [python_exe, self.BRAIN_SCRIPT],
            cwd=_BASE_DIR,
            **kwargs,
        )
        self._started_at = time.time()
        log("DASHBOARD", f"▶️ Brain started (PID {self._proc.pid})", Fore.GREEN)
        return True

    def stop(self) -> bool:
        if not self.is_running():
            return False
        pid = self._proc.pid
        # Kill entire process tree (brain + discord bot + any child processes)
        try:
            if sys.platform == "win32":
                # taskkill /T kills the process tree on Windows
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            else:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                self._proc.wait(timeout=5)
        except Exception:
            # Fallback: force kill the main process
            try:
                self._proc.kill()
            except Exception:
                pass
        log("DASHBOARD", f"⏹️ Brain stopped (PID {pid} + children)", Fore.YELLOW)
        self._proc = None
        self._started_at = None
        return True

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> dict:
        running = self.is_running()
        uptime = int(time.time() - self._started_at) if (running and self._started_at) else None
        return {
            "running":  running,
            "pid":      self._proc.pid if running else None,
            "uptime_s": uptime,
            "model":    _get_active_model(),
        }


def _get_active_model() -> str:
    """Returns the actually active YourAI model name (respects USE_OPENROUTER + runtime overrides)."""
    try:
        import config as _cfg  # noqa: PLC0415
        overrides = _load_runtime_overrides()
        use_openrouter = overrides.get("USE_OPENROUTER", getattr(_cfg, "USE_OPENROUTER", False))
        if use_openrouter:
            return f"☁️ {getattr(_cfg, 'MODEL_YOURAI_OPENROUTER', 'unknown')}"
        else:
            return f"🏠 {getattr(_cfg, 'MODEL_YOURAI_LOCAL_PRIMARY', 'unknown')}"
    except Exception:
        return "unknown"


process_manager = ProcessManager()


# ==========================================
# BRAIN CONTROL API
# ==========================================

@app.get("/api/brain_status")
async def brain_status_api(key: Optional[str] = None):
    verify_access(key, "debug")
    return process_manager.status()

@app.post("/api/restart")
async def restart_brain_api():
    ok = process_manager.restart()
    return {"ok": ok, "status": process_manager.status()}

@app.post("/api/brain/start")
async def start_brain_api():
    ok = process_manager.start()
    return {"ok": ok, "status": process_manager.status()}

@app.post("/api/brain/stop")
async def stop_brain_api():
    ok = process_manager.stop()
    return {"ok": ok, "status": process_manager.status()}


# ==========================================
# COMMAND API (Admin-only slash commands)
# ==========================================

# Commands that are allowed via the API (whitelist)
_ALLOWED_COMMANDS = {
    "/website_update": "Autonomes Website Redesign starten",
    "/lab_update":     "Autonomes Lab-Update starten (YourAIs Spielwiese, keine Filter)",
    "/diary":          "Tagebuch-Status anzeigen",
    "/memory":         "Memory-Status anzeigen",
    "/reset_mode":     "YourAI/AltPersona Mode zurücksetzen",
    "/expert_pool_refresh": "Expert Model Pool aktualisieren",
}

@app.post("/api/command")
async def run_command_api(request: Request, key: Optional[str] = None):
    """Execute a whitelisted slash command (admin only)."""
    verify_access(key, "admin")
    try:
        data = await request.json()
        cmd = (data.get("command") or "").strip()

        if not cmd:
            return {"ok": False, "error": "Kein Command angegeben"}

        if cmd not in _ALLOWED_COMMANDS:
            return {"ok": False, "error": f"Command '{cmd}' nicht erlaubt. Erlaubt: {list(_ALLOWED_COMMANDS.keys())}"}

        log("DASHBOARD", f"🖥️ Admin Command via Dashboard: {cmd}", Fore.MAGENTA)

        # Execute the command
        result_msg = "✅ Command ausgeführt"

        if cmd == "/website_update":
            try:
                from tools.website_autonomy import maybe_trigger_website_update
                maybe_trigger_website_update(DashboardClient(), force=True)
                result_msg = "🎨 Autonomes Website-Redesign gestartet — Fortschritt im Dashboard sichtbar!"
            except Exception as e:
                return {"ok": False, "error": f"website_update failed: {e}"}

        elif cmd == "/lab_update":
            try:
                from tools.website_autonomy_lab import maybe_trigger_lab_update
                maybe_trigger_lab_update(DashboardClient(), force=True)
                result_msg = "🎪 Lab-Update gestartet — Fortschritt im Dashboard sichtbar!"
            except Exception as e:
                return {"ok": False, "error": f"lab_update failed: {e}"}

        elif cmd == "/diary":
            try:
                from memory.episodic import journal
                result_msg = f"📔 Diary: {journal.get_status() if hasattr(journal, 'get_status') else 'Status nicht verfügbar'}"
            except Exception as e:
                result_msg = f"📔 Diary: Modul nicht verfügbar ({e})"

        elif cmd == "/memory":
            try:
                import config as _cfg
                result_msg = f"🧠 Memory: USE_MEMORY={getattr(_cfg, 'USE_MEMORY', '?')}, USE_EPISODIC={getattr(_cfg, 'USE_EPISODIC', '?')}"
            except Exception as e:
                result_msg = f"🧠 Memory: Fehler ({e})"

        elif cmd == "/reset_mode":
            try:
                if SESSION_AVAILABLE:
                    session_manager.user_modes = {}
                    session_manager._save()
                    result_msg = "🔄 Alle User-Modes zurückgesetzt (→ YourAI)"
                else:
                    result_msg = "⚠️ Session Manager nicht verfügbar"
            except Exception as e:
                result_msg = f"❌ Reset fehlgeschlagen: {e}"

        elif cmd == "/expert_pool_refresh":
            try:
                from tools.expert_pool import refresh_from_llm_stats
                refresh = refresh_from_llm_stats()
                result_msg = "Expert Pool aktualisiert" if refresh.get("ok") else f"Expert Pool Fallback: {refresh.get('reason')}"
            except Exception as e:
                result_msg = f"Expert Pool Refresh fehlgeschlagen: {e}"

        # Broadcast as dashboard event so it shows up in the debug feed
        cmd_event = DebugEvent(
            event_type=EventType.SYSTEM_INFO,
            node_name="admin_command",
            timestamp=datetime.now().strftime("%H:%M:%S"),
            title=f"🖥️ Admin Command: {cmd}",
            content=result_msg,
            status="success"
        )
        await state.broadcast(cmd_event)

        return {"ok": True, "result": result_msg}

    except Exception as e:
        import traceback
        err = YourAIUnexpectedError(cause=e, module="dashboard_command_api")
        log_exception("DASHBOARD", err)
        return {"ok": False, "error": str(e)}


# ==========================================
# IMAGE USAGE API
# ==========================================

@app.get("/api/image-usage")
async def get_image_usage_api(key: Optional[str] = None):
    """Returns image generation usage for the requesting user."""
    verify_access(key, "chat")
    key_info = get_key_info(key)
    user_key = key_info["user_key"] if key_info else "unknown"
    is_admin = key_info["role"] == "admin" if key_info else False

    # Resolve user_id and role from session manager
    user_id = user_key
    session_role = None
    try:
        if SESSION_AVAILABLE:
            profile = _resolve_session_profile(user_key)
            if profile:
                user_id = profile.user_id
                session_role = profile.role
    except Exception:
        pass

    # Use session role if found, otherwise map access-key role to a limit role
    if session_role:
        role = session_role
    elif is_admin:
        role = "admin"
    else:
        role = "family"  # Safe default for known chat/debug users (25/month)

    try:
        from tools.image_limits import get_usage
        return get_usage(user_id, role)
    except ImportError:
        return {"used": 0, "limit": 0, "remaining": 0, "month": "", "unlimited": is_admin}

@app.get("/api/image-usage/all")
async def get_all_image_usage_api(key: Optional[str] = None):
    """Returns image usage for ALL users (admin only)."""
    verify_access(key, "admin")
    try:
        from tools.image_limits import get_usage
        from config import IMAGE_LIMITS_FILE
        result = {}
        if SESSION_AVAILABLE:
            for ukey, profile in session_manager.users.items():
                usage = get_usage(profile.user_id, profile.role)
                usage["display_name"] = profile.display_name
                usage["role"] = profile.role
                result[ukey] = usage
        return result
    except Exception:
        return {}

# ==========================================
# CONFIG API (runtime_config.json overrides)
# ==========================================

_RUNTIME_CONFIG_FILE = os.path.join(_BASE_DIR, "runtime_config.json")

# USE_* flags we expose to the frontend
_EXPOSED_FLAGS = [
    "USE_STREAMING", "USE_VOICE", "USE_VISION", "USE_DISCORD", "USE_SPOTIFY",
    "USE_TOOLS", "USE_MEMORY", "USE_EPISODIC", "USE_THINKING",
    "USE_GRANITE", "USE_COHERENCE_CHECK", "USE_CONSOLE_LOG",
    "USE_WEB_SEARCH",
    "USE_PAPERLESS",
    "USE_HOME_ASSISTANT",
    "USE_IMAGE_GEN",
    "USE_PROMISE_CHECK",
    "USE_MAINTENANCE",  # Handled separately in frontend (prominent banner)
]

_EXPOSED_MODELS = [
    "MODEL_YOURAI_OPENROUTER", "MODEL_YOURAI_LOCAL_PRIMARY", "MODEL_YOURAI_LOCAL_FALLBACK",
    "MODEL_ROUTER", "MODEL_COHERENCE",
    "IMAGE_MODEL",
]

def _load_runtime_overrides() -> dict:
    if os.path.exists(_RUNTIME_CONFIG_FILE):
        try:
            with open(_RUNTIME_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_runtime_override(key: str, value) -> None:
    overrides = _load_runtime_overrides()
    overrides[key] = value
    with open(_RUNTIME_CONFIG_FILE, "w") as f:
        json.dump(overrides, f, indent=2)

@app.get("/api/config")
async def get_config_api(key: Optional[str] = None):
    """Returns current USE_* flags (with runtime overrides applied) and active models."""
    verify_access(key, "debug")
    import config as _cfg  # noqa: PLC0415
    overrides = _load_runtime_overrides()
    flags = {}
    for key_name in _EXPOSED_FLAGS:
        base_val = getattr(_cfg, key_name, None)
        flags[key_name] = overrides.get(key_name, base_val)
    models = {}
    for key_name in _EXPOSED_MODELS:
        models[key_name] = getattr(_cfg, key_name, "—")
    return {"flags": flags, "models": models, "overrides": overrides}

@app.get("/api/expert_pool")
async def get_expert_pool_api(key: Optional[str] = None):
    """Returns current expert pool status for the Config tab."""
    verify_access(key, "debug")
    try:
        from tools.expert_pool import get_pool_status
        return get_pool_status()
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="expert_pool_api")
        log_exception("DASHBOARD", err)
        return {"error": str(e), "domains": {}}

@app.post("/api/config")
async def set_config_api(request: Request, key: Optional[str] = None):
    """Write a single runtime override (USE_* flags + IMAGE_MODEL)."""
    verify_access(key, "admin")
    try:
        data = await request.json()
        key_name = data.get("key", "")
        value    = data.get("value")
        allowed  = key_name in _EXPOSED_FLAGS or key_name == "IMAGE_MODEL"
        if not allowed:
            return {"ok": False, "error": f"Key '{key_name}' nicht erlaubt"}
        _save_runtime_override(key_name, value)
        log("DASHBOARD", f"[CFG] Config override: {key_name} = {value}", Fore.CYAN)
        return {"ok": True, "key": key_name, "value": value}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/image_models")
async def get_image_models_api():
    """Returns available image models and the currently active one."""
    import config as _cfg
    overrides = _load_runtime_overrides()
    active = overrides.get("IMAGE_MODEL", getattr(_cfg, "IMAGE_MODEL", "sourceful/riverflow-v2-fast"))
    models = getattr(_cfg, "IMAGE_MODELS", [active])
    return {"active": active, "models": models}


# ==========================================
# VERSION API
# ==========================================

@app.get("/api/emojis")
async def get_emojis_api(key: Optional[str] = None):
    """Returns Discord custom emoji map: {name: cdn_url} for web rendering."""
    verify_access(key, "chat")
    _emap_path = os.path.join(_BASE_DIR, "emoji_map.json")
    try:
        with open(_emap_path, "r") as f:
            emoji_data = json.load(f)
        result = {}
        for name, info in emoji_data.items():
            # Support both old format (just id string) and new format ({id, animated})
            if isinstance(info, dict):
                eid = info["id"]
                ext = "gif" if info.get("animated") else "webp"
            else:
                eid = info
                ext = "webp"
            result[name] = f"https://cdn.discordapp.com/emojis/{eid}.{ext}?size=32&quality=lossless"
        return result
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

@app.get("/api/version")
async def get_version_api():
    """App-Version + aktives LLM (kein Auth nötig — nur Meta-Info)."""
    return {
        "version": _APP_VERSION,
        "model": _get_active_model(),
    }


# ==========================================
# APP API ROUTER  (mobile/app-specific endpoints)
# ==========================================

from app.app_api import router as _app_router
app.include_router(_app_router)


# ==========================================
# STATIC FILES (MOUNT AT ROOT LAST)
# Custom / Route injiziert ?v= Cache-Buster in index.html
# ==========================================

_MAINTENANCE_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YourAI – Gleich zurück 🦊</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      background: #0f0f14;
      font-family: 'Segoe UI', sans-serif;
      color: #e0d6f0;
    }
    .card {
      text-align: center;
      padding: 48px 40px;
      background: #1a1a24;
      border: 1px solid #2e2a3a;
      border-radius: 20px;
      max-width: 480px;
      box-shadow: 0 0 40px rgba(255,140,60,0.08);
    }
    .fox { font-size: 5rem; margin-bottom: 16px; animation: bounce 2s ease-in-out infinite; }
    @keyframes bounce {
      0%, 100% { transform: translateY(0); }
      50%       { transform: translateY(-12px); }
    }
    h1 { font-size: 1.6rem; margin-bottom: 10px; color: #ff8c3c; }
    p  { color: #9988aa; line-height: 1.6; font-size: 0.95rem; }
    .dots { margin-top: 28px; display: flex; justify-content: center; gap: 8px; }
    .dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #ff8c3c; opacity: 0.3;
      animation: pulse 1.4s ease-in-out infinite;
    }
    .dot:nth-child(2) { animation-delay: 0.2s; }
    .dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
  </style>
</head>
<body>
  <div class="card">
    <div class="fox">🦊</div>
    <h1>YourAI ist gleich zurück!</h1>
    <p>Gerade laufen ein paar Updates im Hintergrund.<br>Schau in ein paar Minuten nochmal vorbei!</p>
    <div class="dots">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def serve_index(key: Optional[str] = None):
    """Serve index.html — bei aktivem Maintenance Mode sehen Nicht-Admins eine Wartungsseite."""
    # Maintenance Mode prüfen
    import config as _cfg
    overrides = _load_runtime_overrides()
    maintenance_on = overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False))
    if maintenance_on and get_role_for_key(key) != "admin":
        return HTMLResponse(content=_MAINTENANCE_HTML, status_code=503)

    html_path = os.path.join(_FRONTEND_DIR, "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Nur LOKALE .css/.js Dateien mit ?v= versehen (keine externen CDN URLs!)
        content = _re.sub(
            r'((?:href|src)="(?!https?://)[^"]+\.(?:css|js))(?:\?[^"]*)?(")',
            lambda m: f'{m.group(1)}?v={_APP_VERSION}{m.group(2)}',
            content
        )
        return HTMLResponse(content=content)
    except Exception as e:
        log("DASHBOARD", f"[ERR] index.html lesen fehlgeschlagen: {e}", Fore.RED)
        return HTMLResponse(content="<h1>Frontend nicht gefunden</h1>", status_code=500)

@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy():
    """Serve privacy.html — no auth required (DSGVO compliance)."""
    html_path = os.path.join(_FRONTEND_DIR, "privacy.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        log("DASHBOARD", f"[ERR] privacy.html lesen fehlgeschlagen: {e}", Fore.RED)
        return HTMLResponse(content="<h1>Seite nicht gefunden</h1>", status_code=404)

@app.get("/terms", response_class=HTMLResponse)
async def serve_terms():
    """Serve terms.html — no auth required."""
    html_path = os.path.join(_FRONTEND_DIR, "terms.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        log("DASHBOARD", f"[ERR] terms.html lesen fehlgeschlagen: {e}", Fore.RED)
        return HTMLResponse(content="<h1>Seite nicht gefunden</h1>", status_code=404)

if os.path.isdir(_FRONTEND_DIR):
    # Statische Assets (CSS, JS, Bilder) — index.html wird oben per Custom Route bedient
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=False), name="frontend")

if __name__ == "__main__":
    try:
        log("DASHBOARD", "YourAI Dashboard v6 (Frontend Edition)", Fore.MAGENTA)
        log("DASHBOARD", f"   Root: {_FRONTEND_DIR}", Fore.LIGHTBLACK_EX)
        log("DASHBOARD", f"   URL:  http://localhost:8051", Fore.CYAN)
        log("DASHBOARD", "   Klick 'Start' im Config-Tab um das Brain zu wecken!", Fore.CYAN)
        try:
            from tools.expert_pool import refresh_if_month_changed
            pool_refresh = refresh_if_month_changed()
            if pool_refresh.get("skipped"):
                log("DASHBOARD", "   Expert Pool: current month loaded", Fore.CYAN)
            else:
                log("DASHBOARD", f"   Expert Pool refresh: {pool_refresh.get('ok')} {pool_refresh.get('reason', '')}", Fore.CYAN)
        except Exception as pool_err:
            log("DASHBOARD", f"   Expert Pool init failed: {pool_err}", Fore.YELLOW)

        # Graceful shutdown: handle Ctrl+C properly
        import signal
        signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

        config = uvicorn.Config(app, host="0.0.0.0", port=8051, log_level="warning", access_log=False)
        server = uvicorn.Server(config)
        server.run()
    except Exception as fatal_e:
        import traceback
        with open("fatal_error.log", "w", encoding="utf-8") as f:
            f.write(f"FATAL ERROR AT STARTUP:\n{str(fatal_e)}\n\n")
            f.write(traceback.format_exc())
        print(f"CRITICAL: Server failed to start. See fatal_error.log")
        sys.exit(1)


