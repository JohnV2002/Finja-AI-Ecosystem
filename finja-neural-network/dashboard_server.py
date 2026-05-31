"""
YourAI Dashboard Server
======================
FastAPI server for the YourAI dashboard, websocket event stream, runtime config,
analytics APIs, speech endpoints, and static frontend serving.

Main Responsibilities:
- Serve the dashboard frontend and authenticated API routes.
- Manage websocket connections, input queue, maintenance state, and debug events.
- Expose analytics, health, TTS/STT, user, config, and control endpoints.

Side Effects:
- Reads and writes dashboard logs, runtime config, usage files, and access keys.
- Starts and stops the managed brain subprocess.
- Broadcasts websocket updates and serves static frontend assets.
"""
import _paths  # noqa: F401 - add subdirectories to the Python path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import asdict
import asyncio
import json
import os
import sys
import time
import random
import uuid as _uuid_mod
import uvicorn
from fastapi import HTTPException, status

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError
from feedback import FeedbackStore
from dashboard_client import DashboardClient
from dashboard_models import ConnectionInfo, DebugEvent, EventType
from dashboard_process import ProcessManager, get_active_model
from dashboard_runtime import (
    EXPOSED_FLAGS,
    load_runtime_overrides,
    save_runtime_override,
)
import dashboard_analytics
from dashboard_session import (
    PREDEFINED_USERS,
    SESSION_AVAILABLE,
    TOKEN_DASHBOARD_ACTIVE_SECONDS,
    TOKEN_SOFT_LIMIT,
    reload_sessions_from_disk,
    resolve_session_profile,
    session_manager,
    token_level,
    token_usage_payload,
)

QUEUE_WAIT_MESSAGES = [
    "Please wait, YourAI is making cocoa...",
    "YourAI is sorting her thoughts...",
    "One moment, YourAI is polishing the glitter line...",
    "YourAI is about to take off, one moment...",
]

QUEUE_PROCESSING_MESSAGES = [
    "YourAI is thinking...",
    "YourAI is writing...",
    "YourAI is listening and will answer soon...",
]

from config import (
    DASHBOARD_MAX_EVENTS, DASHBOARD_DEFAULT_USER, DASHBOARD_DEFAULT_MODE,
    TTS_VOLUME_CONFIG_FILE, DEBUG_LOG_FILE, DEBUG_LOG_MAX_LINES,
    YOURAI_OUTPUT_FILE
)

# ==========================================
# ACCESS CONTROL  (shared via app/auth.py)
# ==========================================

from app.auth import (
    load_access_keys, save_access_keys, get_key_info, get_role_for_key,
    verify_access, is_maintenance_mode,
)

# ==========================================
# EVENT STORE & WEBSOCKET MANAGER
# ==========================================

class DashboardState:
    """Manage dashboard events, connections, queue state, and maintenance flags."""
    def __init__(self):
        """Handle init."""
        self.events: List[DebugEvent] = []
        self.connections: Dict[WebSocket, ConnectionInfo] = {}
        self.input_queue: asyncio.Queue = asyncio.Queue()
        self.maintenance_draining: bool = False
        self.maintenance_active_jobs: Dict[str, int] = {}
        self.max_events = DASHBOARD_MAX_EVENTS
        self._load_from_log()  # Restore events from disk

        # Reset all user modes on startup (matches brain.py input_loop reset)
        if SESSION_AVAILABLE:
            session_manager.user_modes = {}
            session_manager._default_mode = DASHBOARD_DEFAULT_MODE
            session_manager._save()

    def _account_id_for_user_key(self, user_key: str) -> str:
        """Handle account id for user key."""
        if not user_key:
            return ""
        try:
            if SESSION_AVAILABLE:
                profile = session_manager.users.get(user_key)
                if profile:
                    return profile.user_id
        except Exception:
            pass
        return user_key

    def _queued_maintenance_count(self) -> int:
        """Handle queued maintenance count."""
        try:
            return sum(1 for item in list(self.input_queue._queue) if item.get("role") != "admin")
        except Exception:
            return 0

    def _active_maintenance_count(self) -> int:
        """Handle active maintenance count."""
        return sum(max(0, int(v or 0)) for v in self.maintenance_active_jobs.values())

    def maintenance_pending_count(self) -> int:
        """Handle maintenance pending count."""
        return self._queued_maintenance_count() + self._active_maintenance_count()

    def maintenance_status(self) -> dict:
        """Handle maintenance status."""
        import config as _cfg
        overrides = load_runtime_overrides()
        active = bool(overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False)))
        return {
            "active": active,
            "draining": self.maintenance_draining,
            "queued": self._queued_maintenance_count(),
            "active_jobs": self._active_maintenance_count(),
            "pending": self.maintenance_pending_count(),
        }

    def mark_job_started(self, item: dict) -> None:
        """Handle mark job started."""
        if item.get("role") == "admin":
            return
        account_id = item.get("for_user") or self._account_id_for_user_key(item.get("user_key", ""))
        if not account_id:
            return
        self.maintenance_active_jobs[account_id] = self.maintenance_active_jobs.get(account_id, 0) + 1

    async def mark_job_finished(self, for_user: Optional[str]) -> None:
        """Handle mark job finished."""
        if for_user:
            key = str(for_user)
            current = self.maintenance_active_jobs.get(key, 0)
            if current > 1:
                self.maintenance_active_jobs[key] = current - 1
            elif current == 1:
                self.maintenance_active_jobs.pop(key, None)
            else:
                # Fallback: finish the oldest active non-admin bucket if IDs differ.
                for k in list(self.maintenance_active_jobs.keys()):
                    self.maintenance_active_jobs[k] -= 1
                    if self.maintenance_active_jobs[k] <= 0:
                        self.maintenance_active_jobs.pop(k, None)
                    break
        await self.broadcast_message("maintenance_status", self.maintenance_status(), only_admins=True)
        await self.maybe_finish_maintenance_drain()

    async def maybe_finish_maintenance_drain(self) -> None:
        """Handle maybe finish maintenance drain."""
        if not self.maintenance_draining or self.maintenance_pending_count() > 0:
            return
        self.maintenance_draining = False
        save_runtime_override("USE_MAINTENANCE", True)
        await self.broadcast_message("maintenance_status", self.maintenance_status())
        await self.broadcast_message("config_changed", {
            "key": "USE_MAINTENANCE",
            "value": True,
            "maintenance": True,
        })
        await self.force_refresh_non_admins("maintenance_active")

    async def force_refresh_non_admins(self, reason: str) -> None:
        """Handle force refresh non admins."""
        dead = []
        for ws_conn, conn in self.connections.items():
            if conn.role == "admin":
                continue
            try:
                await ws_conn.send_json({
                    "type": "force_refresh",
                    "data": {"reason": reason},
                })
            except Exception:
                dead.append(ws_conn)
        for ws_conn in dead:
            self.disconnect(ws_conn)

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
        """Handle connect."""
        await websocket.accept()
        conn = ConnectionInfo(websocket=websocket, role=role, user_key=user_key, can_altpersona=can_altpersona)
        self.connections[websocket] = conn

        # Send user info scoped to this connection
        await websocket.send_json({
            "type": "user_info",
            "data": self._get_user_info(conn)
        })
        await websocket.send_json({
            "type": "maintenance_status",
            "data": self.maintenance_status(),
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
        # User-scoped status events are safe for chat tabs (e.g. context flush).
        if event.event_type == EventType.SYSTEM_INFO and event.node_name in ("queue_status", "session_flush"):
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
                "current_language": getattr(_prof, "language", "en") if "_prof" in locals() and _prof else "en",
                "current_mode": session_manager.user_modes.get(conn.user_key, session_manager._default_mode),
                "can_switch_user": conn.role == "admin",
            }
            # Only admin gets the full user list
            if conn.role == "admin":
                info["available_users"] = [
                    {"key": k, "user_id": v.user_id, "name": v.display_name, "role": v.role, "language": getattr(v, "language", "en")}
                    for k, v in session_manager.users.items()
                ]
            else:
                # Non-admin only sees themselves
                profile = session_manager.users.get(conn.user_key)
                if profile:
                    info["available_users"] = [
                        {"key": conn.user_key, "user_id": profile.user_id, "name": profile.display_name, "role": profile.role, "language": getattr(profile, "language", "en")}
                    ]
                else:
                    info["available_users"] = [
                        {"key": conn.user_key, "name": conn.user_key, "role": "guest"}
                    ]
            return info
        return {
            "current_user": conn.user_key,
            "current_user_key": conn.user_key,
            "current_language": "en",
            "current_mode": "yourai",
            "can_switch_user": conn.role == "admin",
            "available_users": [{"key": conn.user_key, "name": conn.user_key, "role": "guest", "language": "en"}]
        }

    def disconnect(self, websocket: WebSocket):
        """Handle disconnect."""
        self.connections.pop(websocket, None)

    async def broadcast(self, event: DebugEvent):
        """Broadcast event — filtered per connection's permissions."""
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

        # Persist to disk
        self._persist_event(event)
        dashboard_analytics.record_event(event)
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
        if event.event_type == EventType.PIPELINE_END:
            await self.mark_job_finished(event.for_user)

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

    async def send_queue_status(self, user_key: str, status: str, message: str,
                                position: int = 0, detail: str = ""):
        """Send chat queue/busy status to all open tabs for one user."""
        if not user_key:
            return
        payload = {
            "status": status,
            "message": message,
            "position": position,
            "detail": detail,
        }
        dead = []
        for ws, conn in self.connections.items():
            if str(conn.user_key).lower() != str(user_key).lower():
                continue
            try:
                await ws.send_json({"type": "queue_status", "data": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

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
                title=f"[USER] User switched: {session_manager.get_current_user('web')}",
                content=result,
                status="info"
            )
            await self.broadcast(event)

            # Only inform this admin's connection
            await self.send_to_connection(websocket, "user_changed", self._get_user_info(conn))
            return result
        return "Session manager not available"

    async def create_user(self, websocket: WebSocket, user_key: str, display_name: str, role: str, description: str, language: str = "en"):
        """Admin-only: create a new user."""
        conn = self.connections.get(websocket)
        if not conn or conn.role != "admin":
            return "No permission"

        if SESSION_AVAILABLE:
            result = session_manager.create_user(
                user_key=user_key,
                display_name=display_name,
                role=role,
                description=description,
                language=language,
            )

            event = DebugEvent(
                event_type=EventType.USER_SWITCH,
                node_name="session",
                timestamp=datetime.now().strftime("%H:%M:%S"),
                title=f"[USER] New account created: {display_name}",
                content=result,
                status="info"
            )
            await self.broadcast(event)
            await self.send_to_connection(websocket, "user_info", self._get_user_info(conn))
            return result
        return "Session manager not available"

    async def switch_mode(self, mode: str, user_key: str = "admin"):
        """Switch the mode (yourai/altpersona) for a specific user."""
        if SESSION_AVAILABLE:
            # Set mode for this specific user's web source
            session_manager.user_modes[user_key] = mode
            session_manager._save()

            mode_tag = "[ALTPERSONA]" if mode == "altpersona" else "[YOURAI]"
            result = f"{mode_tag} Mode for {user_key}: {mode.upper()}"

            event = DebugEvent(
                event_type=EventType.USER_SWITCH,
                node_name="session",
                timestamp=datetime.now().strftime("%H:%M:%S"),
                title=f"{mode_tag} Mode switched: {user_key} → {mode.upper()}",
                content=result,
                status="info"
            )
            await self.broadcast(event)

            # Mode change → only inform the affected user
            for ws, conn in self.connections.items():
                if conn.user_key == user_key:
                    await self.send_to_connection(ws, "mode_changed", self._get_user_info(conn))
            return result
        return "Session manager not available"

    def get_user_key_for(self, websocket: WebSocket) -> str:
        """Get the locked user_key for a connection."""
        conn = self.connections.get(websocket)
        return conn.user_key if conn else DASHBOARD_DEFAULT_USER

    def clear(self):
        """Handle clear."""
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
# APP VERSION (cache busting)
# Startup timestamp changes automatically on every docker up / server restart.
# ==========================================

import re as _re

_APP_VERSION = datetime.now().strftime("%Y%m%d%H%M%S")
_DASHBOARD_STARTED_AT = time.time()

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
    """Adapt bearer tokens into the legacy query-key flow."""
    async def dispatch(self, request, call_next):
        """Process a request through bearer-to-query authentication middleware."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and not request.query_params.get("key"):
            bearer_key = auth[7:].strip()
            params = dict(request.query_params)
            params["key"] = bearer_key
            # Modify scope in place; call_next picks it up from the same scope dict.
            request.scope["query_string"] = urlencode(params).encode("utf-8")
        return await call_next(request)

app.add_middleware(BearerToQueryParam)


# ==========================================
# WEBSOCKET MANAGER
# ==========================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, key: Optional[str] = None):
    """Handle authenticated dashboard websocket connections."""
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
    _overrides = load_runtime_overrides()
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
                text_attachments = msg.get("text_attachments") or []
                if text.strip() or image_urls or text_attachments:
                    # Block non-admins during maintenance
                    import config as _cfg
                    _overrides = load_runtime_overrides()
                    _maintenance = _overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False))
                    if (_maintenance or state.maintenance_draining) and role != "admin":
                        await state.send_to_connection(websocket, "maintenance_error", {
                            "draining": state.maintenance_draining,
                            "maintenance": bool(_maintenance),
                        })
                    else:
                        # Queue includes the locked user_key + session_uuid from THIS connection
                        conn_user = state.get_user_key_for(websocket)
                        session_uuid = msg.get("session_uuid", "")
                        await state.input_queue.put({
                            "text": text,
                            "user_key": conn_user,
                            "for_user": state._account_id_for_user_key(conn_user),
                            "role": role,
                            "image_urls": image_urls,
                            "text_attachments": text_attachments,
                            "session_uuid": session_uuid,
                        })
                        queue_position = state.input_queue.qsize()
                        # Only echo back to this connection (not everyone)
                        await state.send_to_connection(websocket, "input_received", {
                            "text": text[:50] + "..." if len(text) > 50 else text,
                            "user": conn_user,
                            "queue_position": queue_position,
                        })
                        await state.send_queue_status(
                            conn_user,
                            "queued",
                            random.choice(QUEUE_WAIT_MESSAGES),
                            position=queue_position,
                            detail="Deine Nachricht ist sicher in der Warteschlange.",
                        )
                        await state.broadcast_message("maintenance_status", state.maintenance_status(), only_admins=True)
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
                        {"message": "AltPersona mode is not enabled for this key."})
            elif msg.get("type") == "promise_response":
                promise_data = msg.get("promise_data", {})
                action = msg.get("action")  # "confirm" or "reject"
                conn_user = state.get_user_key_for(websocket)
                user_id = state._account_id_for_user_key(conn_user)

                if action == "confirm" and promise_data:
                    from detection import PromiseSignal, resolve_promise_signals
                    import helpers.personas as personas
                    sig = PromiseSignal(
                        action=promise_data.get("action", "NONE"),
                        promise_name=promise_data.get("promise_name", "none"),
                        reason=promise_data.get("reason"),
                        reason_quality=promise_data.get("reason_quality", "NONE"),
                        source=promise_data.get("source", "llm"),
                        reasoning=promise_data.get("reasoning", ""),
                        original_message=promise_data.get("original_message", ""),
                    )
                    if hasattr(personas, 'persona_manager'):
                        pm = personas.persona_manager
                        with pm.user_context(user_id):
                            resolve_promise_signals([sig], pm, user_id)
                    await websocket.send_json({
                        "type": "promise_ack",
                        "data": {"action": "confirmed", "promise": promise_data.get("promise_name")}
                    })
                elif action == "reject" and promise_data:
                    from detection import save_promise_rejection
                    save_promise_rejection(
                        message=promise_data.get("original_message", ""),
                        detected_as=promise_data.get("promise_name", ""),
                        user_id=user_id,
                    )
                    await websocket.send_json({
                        "type": "promise_ack",
                        "data": {"action": "rejected", "promise": promise_data.get("promise_name")}
                    })

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
    """Receive a debug event from local producers."""
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
        ttft_ms=event.get("ttft_ms"),
        prompt_tokens=event.get("prompt_tokens"),
        completion_tokens=event.get("completion_tokens"),
        total_tokens=event.get("total_tokens"),
        output_tokens_per_sec=event.get("output_tokens_per_sec"),
        estimated_cost_usd=event.get("estimated_cost_usd"),
        cost_source=event.get("cost_source"),
        input_cost_usd_per_m=event.get("input_cost_usd_per_m"),
        output_cost_usd_per_m=event.get("output_cost_usd_per_m"),
        content_chars=event.get("content_chars"),
        audio_duration_sec=event.get("audio_duration_sec"),
        metric_name=event.get("metric_name"),
        result_count=event.get("result_count"),
        candidate_count=event.get("candidate_count"),
        cache_hit=event.get("cache_hit"),
        input_data=event.get("input_data"),
        error=event.get("error"),
        error_code=event.get("error_code"),
        error_module=event.get("error_module"),
        error_type=event.get("error_type"),
        error_id=event.get("error_id"),
        is_seen=event.get("is_seen"),
        repeat_count=event.get("repeat_count"),
        first_seen_at=event.get("first_seen_at"),
        last_seen_at=event.get("last_seen_at"),
        stack_trace=event.get("stack_trace"),
        tracking_id=event.get("tracking_id"),
        source=event.get("source"),
        for_user=event.get("for_user"),
        image_url=event.get("image_url"),
        expert_domain=event.get("expert_domain"),
        expert_model=event.get("expert_model"),
        expert_pass=event.get("expert_pass"),
        fallback_reason=event.get("fallback_reason"),
        promise_data=event.get("promise_data"),
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
    """Delete debug_log.jsonl, clear in-memory events, and broadcast clear to clients."""
    verify_access(key, "admin")
    state.clear()
    await state.broadcast_clear()
    try:
        if os.path.exists(DEBUG_LOG_FILE):
            open(DEBUG_LOG_FILE, "w").close()  # Truncate to empty
        log("DASHBOARD", "[DEBUG-LOG] Log cleared by admin request", Fore.YELLOW)
        return {"ok": True, "message": "Debug log geleert"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/debug/download-log")
async def download_debug_log(key: Optional[str] = None):
    """Download debug_log.jsonl als Datei (admin only)."""
    verify_access(key, "admin")
    if not os.path.exists(DEBUG_LOG_FILE):
        raise HTTPException(status_code=404, detail="Log file not found")
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
        raise HTTPException(status_code=404, detail="yourai_output.txt does not exist yet; YourAI has not answered yet")
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
    """Return the next queued dashboard input item."""
    try:
        item = state.input_queue.get_nowait()
        state.mark_job_started(item)
        await state.broadcast_message("maintenance_status", state.maintenance_status(), only_admins=True)
        await state.send_queue_status(
            item["user_key"],
            "processing",
            random.choice(QUEUE_PROCESSING_MESSAGES),
            position=0,
            detail="YourAI received your message.",
        )
        # item is now a dict: {"text": ..., "user_key": ..., "image_urls": [...], "text_attachments": [...]}
        return {
            "has_input": True,
            "text": item["text"],
            "user_key": item["user_key"],
            "image_urls": item.get("image_urls", []),
            "text_attachments": item.get("text_attachments", []),
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
    """Return current in-memory debug events."""
    return [asdict(e) for e in state.events]

@app.post("/clear")
async def clear_events():
    """Clear in-memory debug events."""
    state.clear()
    return {"status": "cleared"}

@app.get("/users")
async def get_users():
    """Return the dashboard user list."""
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
    return {"status": "error", "message": "Session manager not available"}

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
    """Create a new user through the admin API."""
    verify_access(key, "admin")
    try:
        data = await request.json()
        user_key = data.get("user_key")
        display_name = data.get("display_name")
        role = data.get("role", "human_guest")
        description = data.get("description", "")
        
        language = data.get("language", "en")
        grant_dashboard = data.get("grant_dashboard", False)
        access_key = data.get("access_key", "")
        access_role = data.get("access_role", "chat")
        can_altpersona = data.get("can_altpersona", False)

        if not user_key:
            return {"status": "error", "message": "User-Key (ID) ist erforderlich."}
        canonical_user_key = user_key.strip().lower()

        if SESSION_AVAILABLE:
            result = session_manager.create_user(
                user_key=canonical_user_key,
                display_name=display_name,
                role=role,
                description=description,
                language=language,
            )
            
            # Create dashboard access in access_keys.json.
            if grant_dashboard and access_key:
                keys = load_access_keys()
                keys[access_key] = {
                    "role": access_role,
                    "user_key": canonical_user_key,
                    "can_altpersona": can_altpersona,
                    "description": f"Autocreated for {display_name}"
                }
                # Save access keys.
                try:
                    save_access_keys(keys)
                except Exception as e:
                    return {"status": "warning", "message": f"{result} - ABER access_keys.json speichern fehlgeschlagen: {e}"}

            return {"status": "ok", "message": result}
        return {"status": "error", "message": "Session manager not available"}
    except Exception as e:
        import traceback
        await state.broadcast_error(f"Error creating user '{user_key}'", str(e), traceback.format_exc())
        return {"status": "error", "message": str(e)}


@app.post("/api/update_user")
async def update_user_api(request: Request, key: Optional[str] = None):
    """API Endpoint zum Updaten eines bestehenden Users (Admin only).

    Nur gesendete Felder werden geaendert. Erlaubt: language, description, display_name, role, notes.
    Beispiel: curl -X POST 'http://...:8051/api/update_user?key=ADMIN_KEY' -H 'Content-Type: application/json' -d '{"user_key":"biggi","language":"de"}'
    """
    verify_access(key, "admin")
    try:
        data = await request.json()
        user_key = data.get("user_key", "").strip().lower()

        if not user_key:
            return {"status": "error", "message": "user_key ist erforderlich."}

        if not SESSION_AVAILABLE:
            return {"status": "error", "message": "Session manager not available"}

        profile = session_manager.users.get(user_key)
        if not profile:
            # Case-insensitive lookup.
            for existing_key in session_manager.users:
                if existing_key.lower() == user_key:
                    profile = session_manager.users[existing_key]
                    break
        if not profile:
            return {"status": "error", "message": f"User '{user_key}' not found."}

        changed = []
        if "language" in data:
            lang = data["language"]
            if lang in ("de", "en"):
                profile.language = lang
                changed.append(f"language={lang}")
            else:
                return {"status": "error", "message": f"Ungueltige Sprache: {lang}. Erlaubt: de, en"}
        if "display_name" in data:
            profile.display_name = data["display_name"].strip()
            changed.append(f"display_name={profile.display_name}")
        if "description" in data:
            profile.description = data["description"].strip()
            changed.append(f"description updated")
        if "role" in data:
            profile.role = data["role"]
            changed.append(f"role={profile.role}")
        if "notes" in data and isinstance(data["notes"], list):
            profile.notes = data["notes"]
            changed.append(f"notes updated")

        if not changed:
            return {"status": "error", "message": "Keine aenderbaren Felder gesendet."}

        session_manager._save()
        msg = f"User '{user_key}' aktualisiert: {', '.join(changed)}"
        log("DASHBOARD", msg, Fore.GREEN)
        return {"status": "ok", "message": msg}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==========================================
# USER PROFILE API
# ==========================================

@app.get("/api/user/me")
async def get_user_me(request: Request, key: Optional[str] = None):
    """Returns the current user's profile and usage stats (all roles)."""
    verify_access(key, "chat")
    reload_sessions_from_disk()
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
        profile = resolve_session_profile(user_key)
        if profile:
            display_name = profile.display_name
            session_role = profile.role
            description = profile.description
            user_id = profile.user_id

    session_uuid = request.headers.get("X-Session-UUID", "").strip()
    token_session_id = user_id or user_key
    if session_uuid and token_session_id:
        try:
            session_manager.merge_tokens(session_uuid, token_session_id)
        except Exception:
            pass
    try:
        session_manager.touch_token_session(token_session_id)
    except Exception:
        pass
    token_usage = token_usage_payload(token_session_id)
    try:
        from helpers.style_analyzer import get_style_summary, merge_style_profile
        from helpers.platform_links import get_discord_ids

        style_candidates = []

        def _add_style_candidate(style_id: str, label: str, kind: str):
            """Handle add style candidate."""
            if style_id and not any(item["id"] == style_id for item in style_candidates):
                style_candidates.append({"id": style_id, "label": label, "kind": kind})

        linked_discord_ids = get_discord_ids(user_key)
        for discord_id in linked_discord_ids:
            _add_style_candidate(f"dm_{discord_id}", "Discord DM", "discord_dm")
        _add_style_candidate(session_uuid, "Dashboard", "dashboard")
        _add_style_candidate(user_id, "User", "user")
        _add_style_candidate(user_key, "User-Key", "user_key")

        if user_id:
            for candidate in list(style_candidates):
                if candidate["id"] != user_id:
                    try:
                        merge_style_profile(candidate["id"], user_id)
                    except Exception as e:
                        err = YourAIUnexpectedError(
                            cause=e,
                            module="dashboard_style_merge",
                            source_id=candidate["id"],
                            user_id=user_id,
                        )
                        log_exception("DASHBOARD", err)

        style_sources = []
        for candidate in style_candidates:
            summary = get_style_summary(candidate["id"])
            summary["source_id"] = candidate["id"]
            summary["source_label"] = candidate["label"]
            summary["source_kind"] = candidate["kind"]
            style_sources.append(summary)

        def _style_rank(summary: dict) -> tuple[int, int]:
            """Handle style rank."""
            available = 1 if summary.get("available") else 0
            return (available, int(summary.get("msg_count") or 0))

        style_usage = get_style_summary(user_id) if user_id else (
            dict(max(style_sources, key=_style_rank)) if style_sources else {"available": False}
        )
        style_usage["source_id"] = user_id or style_usage.get("user_uuid")
        style_usage["source_label"] = "User"
        style_usage["source_kind"] = "user"
        style_usage["sources"] = style_sources
        style_usage["linked_discord_count"] = len(linked_discord_ids)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="dashboard_style_usage", user_key=user_key)
        log_exception("DASHBOARD", err)
        style_usage = {"available": False, "error": str(e)}

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
        "language": getattr(profile, "language", "en") if SESSION_AVAILABLE and profile else "en",
        "can_altpersona": can_altpersona,
        "image_usage": image_usage,
        "tts_usage": tts_usage,
        "yourai_tts_usage": yourai_tts_usage,
        "token_usage": token_usage,
        "style_usage": style_usage,
    }


@app.post("/api/user/me")
async def update_user_me(request: Request, key: Optional[str] = None):
    """User self-service endpoint for updating profile data."""
    verify_access(key, "chat")
    key_info = get_key_info(key)
    user_key = key_info["user_key"]

    if not SESSION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Session system unavailable")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ok = session_manager.update_profile(
        user_key,
        display_name=data.get("display_name"),
        description=data.get("description"),
        language=data.get("language"),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")

    return {"ok": True}


# /api/delete_my_data → moved to app/app_api.py (included via router)


# ==========================================
# TTS API
# ==========================================

@app.post("/api/tts")
async def tts_api(request: Request, key: Optional[str] = None):
    """
    Text-to-Speech endpoint — 3 Tiers:
      browser    → client-side only, returns 204
      yourai      → Resemble AI / DeepInfra (Voice Cloning), returns audio/mpeg
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
    key_info = get_key_info(key)
    user_key = key_info["user_key"]
    session_role = "guest"
    user_id = user_key
    if SESSION_AVAILABLE:
        profile = session_manager.users.get(user_key)
        if profile:
            session_role = profile.role
            user_id = profile.user_id

    if not text:
        raise HTTPException(status_code=400, detail="Text ist leer")

    if tier == "browser":
        return FastAPIResponse(status_code=204)

    if tier == "yourai":
        from config import DEEPINFRA_API_KEY
        if not DEEPINFRA_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="YourAI voice (Chatterbox) is unavailable; DEEPINFRA_API_KEY is missing 🦊"
            )
        try:
            from tools.tts_yourai import generate_speech as yourai_tts
            t0 = time.time()
            audio_bytes = await asyncio.get_event_loop().run_in_executor(
                None, yourai_tts, text, lang
            )
            duration_ms = int((time.time() - t0) * 1000)
            # Record Chatterbox usage (no limit, just tracking)
            try:
                from tools.tts_limits import record_yourai_usage
                record_yourai_usage(user_id)
            except Exception:
                pass
            dashboard_analytics.record_event({
                "event_type": "system_info",
                "metric_name": "tts_generation",
                "node_name": "tts_yourai",
                "model": "yourai_tts",
                "source": "tts_yourai",
                "for_user": user_id,
                "duration_ms": duration_ms,
                "content_chars": len(text),
                "result_count": 1,
                "cost_source": "provider_metric_or_unknown",
                "status": "success",
            })
            media = "audio/mpeg" if audio_bytes[:4] != b"RIFF" else "audio/wav"
            return FastAPIResponse(
                content=audio_bytes,
                media_type=media,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as e:
            log("TTS", f"❌ YourAI TTS failed: {type(e).__name__}: {e}", Fore.RED)
            raise HTTPException(status_code=503, detail=f"YourAI TTS: {type(e).__name__}: {str(e)[:250]}")

    if tier == "elevenlabs":
        from config import ELEVENLABS_API_KEY
        if not ELEVENLABS_API_KEY:
            raise HTTPException(status_code=503, detail="ElevenLabs is not configured")

        from tools.tts_limits import can_use_premium, record_usage as record_tts
        allowed, remaining, limit = can_use_premium(user_id, session_role)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Your {limit} free premium voices for this month are used up! 🎤",
                headers={"X-TTS-Remaining": "0", "X-TTS-Limit": str(limit)},
            )

        try:
            from tools.tts_elevenlabs import generate_speech
            t0 = time.time()
            audio_bytes = await asyncio.get_event_loop().run_in_executor(
                None, generate_speech, text, lang
            )
            duration_ms = int((time.time() - t0) * 1000)
            record_tts(user_id)
            dashboard_analytics.record_event({
                "event_type": "system_info",
                "metric_name": "tts_generation",
                "node_name": "tts_elevenlabs",
                "model": "elevenlabs",
                "source": "elevenlabs",
                "for_user": user_id,
                "duration_ms": duration_ms,
                "content_chars": len(text),
                "result_count": 1,
                "cost_source": "unknown_elevenlabs_plan",
                "status": "success",
            })
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
            raise HTTPException(status_code=500, detail=f"TTS error: {err_msg}")

    raise HTTPException(status_code=400, detail=f"Unbekannter Tier: {tier}")


# ==========================================
# STT (Speech-to-Text) API — DeepInfra Whisper
# ==========================================

@app.post("/api/stt")
async def stt_api(request: Request, key: Optional[str] = None):
    """
    Speech-to-Text endpoint — DeepInfra Whisper large-v3
    Receives audio blob (multipart/form-data), returns transcribed text.
    Cost: ~$0.00045/min
    """
    verify_access(key, "chat")

    from config import DEEPINFRA_API_KEY
    if not DEEPINFRA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="STT is unavailable; DEEPINFRA_API_KEY is missing 🦊"
        )

    # Parse multipart form data
    form = await request.form()
    audio_file = form.get("audio")
    if not audio_file:
        raise HTTPException(status_code=400, detail="Kein Audio empfangen")

    try:
        audio_bytes = await audio_file.read()
        if len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Audio-Datei zu klein")

        # Max 25 MB (Whisper limit)
        if len(audio_bytes) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio too large (max 25 MB)")

        size_kb = len(audio_bytes) / 1024
        log("STT", f"🎙️ Audio empfangen: {size_kb:.1f} KB", Fore.CYAN)

        import httpx

        # Send to DeepInfra Whisper API
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3",
                headers={"Authorization": f"Bearer {DEEPINFRA_API_KEY}"},
                files={"audio": ("recording.webm", audio_bytes, audio_file.content_type or "audio/webm")},
            )

        if resp.status_code != 200:
            detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            log("STT", f"❌ DeepInfra Whisper Error: {resp.status_code} — {detail}", Fore.RED)
            raise HTTPException(status_code=502, detail=f"Whisper API Error: {detail}")

        result = resp.json()
        text = result.get("text", "").strip()

        if not text:
            log("STT", "⚠️ Whisper returned empty text", Fore.YELLOW)
            return {"text": "", "warning": "No speech detected"}

        log("STT", f"✅ Transkribiert ({len(text)} Zeichen): {text[:80]}{'…' if len(text) > 80 else ''}", Fore.GREEN)
        return {"text": text}

    except HTTPException:
        raise
    except Exception as e:
        log("STT", f"❌ STT Error: {type(e).__name__}: {e}", Fore.RED)
        raise HTTPException(status_code=500, detail=f"STT error: {type(e).__name__}: {str(e)[:250]}")


# ==========================================
# VOLUME CONTROL API
# ==========================================

VOLUME_CONFIG_FILE = TTS_VOLUME_CONFIG_FILE

@app.get("/get_volume")
async def get_volume_api(key: Optional[str] = None):
    """Get current TTS volume."""
    verify_access(key, "chat")  # Everyone may view volume.
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
    verify_access(key, "debug")  # Only debug/admin users may change volume.
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


process_manager = ProcessManager()


# ==========================================
# ANALYTICS API
# ==========================================

@app.get("/api/analytics/summary")
async def analytics_summary_api(
    key: Optional[str] = None,
    hours: int = 24,
    user: Optional[str] = None,
    source: Optional[str] = None,
    model: Optional[str] = None,
):
    """Condensed performance/error analytics for dashboard users with debug access."""
    verify_access(key, "debug")
    hours = max(1, min(int(hours or 24), 24 * 14))
    try:
        summary = dashboard_analytics.build_summary(hours=hours, user=user, source=source, model=model)
        summary["brain"] = process_manager.status()
        return summary
    except Exception as e:
        import traceback
        err = YourAIUnexpectedError(cause=e, module="dashboard_analytics_summary")
        log_exception("DASHBOARD", err)
        await state.broadcast_error("Analytics API Error", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/timeseries")
async def analytics_timeseries_api(
    key: Optional[str] = None,
    hours: int = 24,
    bucket_minutes: int = 60,
    user: Optional[str] = None,
    source: Optional[str] = None,
    model: Optional[str] = None,
):
    """Bucketed request/error/latency timeline for the Analytics tab."""
    verify_access(key, "debug")
    hours = max(1, min(int(hours or 24), 24 * 14))
    bucket_minutes = max(5, min(int(bucket_minutes or 60), 240))
    try:
        return dashboard_analytics.build_timeseries(
            hours=hours,
            bucket_minutes=bucket_minutes,
            user=user,
            source=source,
            model=model,
        )
    except Exception as e:
        import traceback
        err = YourAIUnexpectedError(cause=e, module="dashboard_analytics_timeseries")
        log_exception("DASHBOARD", err)
        await state.broadcast_error("Analytics API Error", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/analytics/clear")
async def analytics_clear_api(key: Optional[str] = None):
    """Delete all analytics data. Admin only."""
    verify_access(key, "admin")
    result = dashboard_analytics.clear_all_metrics()
    return result


def _health_item(
    name: str,
    ok: bool,
    status_text: str,
    latency_ms: Optional[int] = None,
    detail: Optional[str] = None,
    url: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Handle health item."""
    item = {
        "name": name,
        "ok": bool(ok),
        "status": "ok" if ok else "error",
        "status_text": status_text,
        "latency_ms": latency_ms,
        "detail": detail or "",
    }
    if url:
        item["url"] = url
    if extra:
        item.update(extra)
    return item


def _probe_json_url(name: str, url: str, headers: Optional[dict] = None, timeout: float = 1.5) -> dict:
    """Handle probe json url."""
    import urllib.error
    import urllib.request

    started = time.time()
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4096)
            latency = int((time.time() - started) * 1000)
            status_code = getattr(resp, "status", 0)
            payload = {}
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except Exception:
                payload = {}
            ok = 200 <= int(status_code or 0) < 400
            remote_status = str(payload.get("status") or payload.get("state") or ("ok" if ok else status_code))
            detail = payload.get("message") or payload.get("detail") or payload.get("error") or ""
            return _health_item(
                name,
                ok,
                remote_status,
                latency_ms=latency,
                detail=str(detail)[:180],
                url=url,
                extra={"http_status": status_code},
            )
    except Exception as e:
        latency = int((time.time() - started) * 1000)
        return _health_item(name, False, type(e).__name__, latency_ms=latency, detail=str(e)[:180], url=url)


async def _probe_json_url_async(name: str, url: str, headers: Optional[dict] = None, timeout: float = 1.5) -> dict:
    """Handle probe json url async."""
    return await asyncio.to_thread(_probe_json_url, name, url, headers, timeout)


def _subconscious_health() -> dict:
    """Handle subconscious health."""
    status_file = os.path.join(_BASE_DIR, "subconscious_status.json")
    try:
        if not os.path.exists(status_file):
            return _health_item("Subconscious", False, "missing", detail="Status file not found")
        with open(status_file, "r", encoding="utf-8") as f:
            data = json.loads(f.read() or "{}")
        running = bool(data.get("running"))
        last_tick = data.get("last_tick") or data.get("last_tick_at") or ""
        detail = f"last_tick={last_tick}" if last_tick else str(data.get("error") or "")
        return _health_item("Subconscious", running, "running" if running else "stopped", detail=detail, extra={"raw": data})
    except Exception as e:
        return _health_item("Subconscious", False, type(e).__name__, detail=str(e)[:180])


def _public_health_item(
    service_id: str,
    name: str,
    ok: bool,
    status_text: str,
    latency_ms: Optional[int] = None,
    critical: bool = False,
) -> dict:
    """Handle public health item."""
    return {
        "id": service_id,
        "name": name,
        "ok": bool(ok),
        "status": "ok" if ok else "down",
        "status_text": str(status_text or ("ok" if ok else "down"))[:80],
        "latency_ms": latency_ms,
        "critical": bool(critical),
    }


def _public_from_health(service_id: str, item: dict, *, name: Optional[str] = None, critical: bool = False) -> dict:
    """Handle public from health."""
    return _public_health_item(
        service_id,
        name or str(item.get("name") or service_id),
        bool(item.get("ok")),
        str(item.get("status_text") or item.get("status") or ("ok" if item.get("ok") else "down")),
        latency_ms=item.get("latency_ms"),
        critical=critical,
    )


async def _public_health_services() -> list[dict]:
    """Public-safe health state. No URLs, keys, stack traces, or raw payloads."""
    dashboard = _public_health_item(
        "dashboard",
        "YourAI Dashboard",
        True,
        "online",
        latency_ms=0,
        critical=True,
    )
    brain = process_manager.status()
    brain_item = _public_health_item(
        "brain",
        "YourAI Brain",
        bool(brain.get("running")),
        "running" if brain.get("running") else "stopped",
        critical=True,
    )

    try:
        import config as _cfg
        memory_base = os.environ.get("MEMORY_API_BASE", getattr(_cfg, "MEMORY_API_BASE", "")).rstrip("/")
        memory_key = os.environ.get("MEMORY_API_KEY", getattr(_cfg, "MEMORY_API_KEY", ""))
        youtube_base = os.environ.get("YOUTUBE_API_URL", "http://YOUR_SERVICES_HOST_IP:8060").rstrip("/")  # NOSONAR
        instagram_base = os.environ.get("INSTAGRAM_API_URL", "http://YOUR_SERVICES_HOST_IP:8061").rstrip("/")  # NOSONAR
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", getattr(_cfg, "OPENROUTER_API_KEY", ""))
    except Exception:
        memory_base = ""
        memory_key = ""
        youtube_base = os.environ.get("YOUTUBE_API_URL", "http://YOUR_SERVICES_HOST_IP:8060").rstrip("/")  # NOSONAR
        instagram_base = os.environ.get("INSTAGRAM_API_URL", "http://YOUR_SERVICES_HOST_IP:8061").rstrip("/")  # NOSONAR
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    probes = []
    if memory_base:
        headers = {"X-API-Key": memory_key} if memory_key else {}
        probes.append(_probe_json_url_async("Memory", f"{memory_base}/health", headers=headers))
    else:
        probes.append(asyncio.sleep(0, result=_health_item("Memory", False, "not_configured")))
    probes.append(_probe_json_url_async("YouTube", f"{youtube_base}/health"))
    probes.append(_probe_json_url_async("Instagram", f"{instagram_base}/health"))
    memory, youtube, instagram = await asyncio.gather(*probes)

    subconscious_raw = _subconscious_health()
    services = [
        dashboard,
        brain_item,
        _public_from_health("memory", memory, name="Hippocampus Memory", critical=True),
        _public_from_health("youtube", youtube, name="YouTube Shorts API"),
        _public_from_health("instagram", instagram, name="Instagram Reels API"),
        _public_from_health("subconscious", subconscious_raw, name="YourAI Active"),
        _public_health_item(
            "openrouter",
            "OpenRouter Config",
            bool(openrouter_key),
            "configured" if openrouter_key else "missing_key",
        ),
    ]
    return services


def _public_health_payload(services: list[dict]) -> tuple[dict, int]:
    """Handle public health payload."""
    critical_down = [svc for svc in services if svc.get("critical") and not svc.get("ok")]
    degraded = [svc for svc in services if not svc.get("ok")]
    if critical_down:
        status_text = "down"
        status_code = 503
    elif degraded:
        status_text = "ok_with_optional_issues"
        status_code = 200
    else:
        status_text = "ok"
        status_code = 200
    payload = {
        "ok": not critical_down,
        "status": status_text,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "services": services,
        "ok_count": sum(1 for svc in services if svc.get("ok")),
        "total": len(services),
        "optional_down_count": len([svc for svc in degraded if not svc.get("critical")]),
        "critical_down_count": len(critical_down),
    }
    return payload, status_code


@app.get("/api/public-health")
async def public_health_api():
    """Handle public health api."""
    services = await _public_health_services()
    payload, status_code = _public_health_payload(services)
    return JSONResponse(payload, status_code=status_code)


@app.get("/api/public-health/{service_id}")
async def public_health_service_api(service_id: str):
    """Handle public health service api."""
    service_id = str(service_id or "").strip().lower()
    services = await _public_health_services()
    for service in services:
        if service.get("id") == service_id:
            status_code = 200 if service.get("ok") else 503
            return JSONResponse(service, status_code=status_code)
    return JSONResponse(
        {"ok": False, "status": "unknown_service", "id": service_id},
        status_code=404,
    )


@app.get("/api/analytics/health")
async def analytics_health_api(key: Optional[str] = None):
    """Internal health cockpit for Analytics. Debug access only."""
    verify_access(key, "debug")

    brain = process_manager.status()
    brain_ok = bool(brain.get("running"))
    dashboard = _health_item(
        "Dashboard",
        True,
        "online",
        latency_ms=0,
        detail=f"uptime {int(time.time() - _DASHBOARD_STARTED_AT)}s",
        extra={"uptime_s": int(time.time() - _DASHBOARD_STARTED_AT), "version": _APP_VERSION},
    )
    brain_item = _health_item(
        "Brain",
        brain_ok,
        "running" if brain_ok else "stopped",
        detail=str(brain.get("model") or ""),
        extra=brain,
    )

    try:
        import config as _cfg
        memory_base = os.environ.get("MEMORY_API_BASE", getattr(_cfg, "MEMORY_API_BASE", "")).rstrip("/")
        memory_key = os.environ.get("MEMORY_API_KEY", getattr(_cfg, "MEMORY_API_KEY", ""))
        youtube_base = os.environ.get("YOUTUBE_API_URL", "http://YOUR_SERVICES_HOST_IP:8060").rstrip("/")  # NOSONAR
        instagram_base = os.environ.get("INSTAGRAM_API_URL", "http://YOUR_SERVICES_HOST_IP:8061").rstrip("/")  # NOSONAR
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", getattr(_cfg, "OPENROUTER_API_KEY", ""))
    except Exception:
        memory_base = ""
        memory_key = ""
        youtube_base = os.environ.get("YOUTUBE_API_URL", "http://YOUR_SERVICES_HOST_IP:8060").rstrip("/")  # NOSONAR
        instagram_base = os.environ.get("INSTAGRAM_API_URL", "http://YOUR_SERVICES_HOST_IP:8061").rstrip("/")  # NOSONAR
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    probes = []
    if memory_base:
        headers = {"X-API-Key": memory_key} if memory_key else {}
        probes.append(_probe_json_url_async("Memory", f"{memory_base}/health", headers=headers))
    else:
        probes.append(asyncio.sleep(0, result=_health_item("Memory", False, "not_configured")))
    probes.append(_probe_json_url_async("YouTube API", f"{youtube_base}/health"))
    probes.append(_probe_json_url_async("Instagram API", f"{instagram_base}/health"))
    probed = await asyncio.gather(*probes)

    openrouter = _health_item(
        "OpenRouter",
        bool(openrouter_key),
        "configured" if openrouter_key else "missing_key",
        detail="No live request in health MVP",
    )

    services = [dashboard, brain_item, _subconscious_health(), *probed, openrouter]
    ok_count = sum(1 for item in services if item.get("ok"))
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "ok": ok_count == len(services),
        "ok_count": ok_count,
        "total": len(services),
        "services": services,
    }


# ==========================================
# BRAIN CONTROL API
# ==========================================

@app.get("/api/brain_status")
async def brain_status_api(key: Optional[str] = None):
    """Return managed brain process status."""
    verify_access(key, "debug")
    return process_manager.status()

@app.post("/api/restart")
async def restart_brain_api():
    """Restart the managed brain process."""
    ok = process_manager.restart()
    return {"ok": ok, "status": process_manager.status()}

@app.post("/api/brain/start")
async def start_brain_api():
    """Start the managed brain process."""
    ok = process_manager.start()
    return {"ok": ok, "status": process_manager.status()}

@app.post("/api/brain/stop")
async def stop_brain_api():
    """Stop the managed brain process."""
    ok = process_manager.stop()
    return {"ok": ok, "status": process_manager.status()}


# ==========================================
# SUBCONSCIOUS API (YourAI active)
# ==========================================

@app.get("/api/subconscious/status")
async def subconscious_status_api(key: Optional[str] = None):
    """Status des YourAI Aktiv Subconscious Loop (liest Status-Datei vom Brain-Subprocess)."""
    verify_access(key, "debug")
    status_file = os.path.join(_BASE_DIR, "subconscious_status.json")
    try:
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                return json.loads(f.read())
        return {"running": False, "error": "Status file not found (brain not started?)"}
    except Exception as e:
        return {"running": False, "error": str(e)}


# ==========================================
# COMMAND API (Admin-only slash commands)
# ==========================================

# Commands that are allowed via the API (whitelist)
_ALLOWED_COMMANDS = {
    "/website_update": "Autonomes Website Redesign starten",
    "/lab_update":     "Start autonomous lab update (YourAI sandbox, no filters)",
    "/diary":          "Tagebuch-Status anzeigen",
    "/memory":         "Memory-Status anzeigen",
    "/reset_mode":     "Reset YourAI/AltPersona mode",
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
            return {"ok": False, "error": f"Command '{cmd}' is not allowed. Allowed: {list(_ALLOWED_COMMANDS.keys())}"}

        log("DASHBOARD", f"🖥️ Admin Command via Dashboard: {cmd}", Fore.MAGENTA)

        # Execute the command
        result_msg = "✅ Command executed"

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
                result_msg = f"📔 Diary: {journal.get_status() if hasattr(journal, 'get_status') else 'Status unavailable'}"
            except Exception as e:
                result_msg = f"📔 Diary: module unavailable ({e})"

        elif cmd == "/memory":
            try:
                import config as _cfg
                result_msg = f"🧠 Memory: USE_MEMORY={getattr(_cfg, 'USE_MEMORY', '?')}, USE_EPISODIC={getattr(_cfg, 'USE_EPISODIC', '?')}"
            except Exception as e:
                result_msg = f"🧠 Memory: error ({e})"

        elif cmd == "/reset_mode":
            try:
                if SESSION_AVAILABLE:
                    session_manager.user_modes = {}
                    session_manager._save()
                    result_msg = "🔄 All user modes reset (→ YourAI)"
                else:
                    result_msg = "⚠️ Session manager not available"
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
            profile = resolve_session_profile(user_key)
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

@app.get("/api/token-usage/all")
async def get_all_token_usage_api(key: Optional[str] = None):
    """Returns token usage for all tracked sessions (admin only)."""
    verify_access(key, "admin")
    reload_sessions_from_disk()
    if not SESSION_AVAILABLE:
        return {"limit": TOKEN_SOFT_LIMIT, "sessions": [], "by_user": []}

    try:
        raw_tokens = dict(getattr(session_manager, "session_tokens", {}) or {})
        sessions = []
        stale_count = 0
        by_user_map = {}
        profiles_by_id = {}
        for ukey, profile in getattr(session_manager, "users", {}).items():
            profiles_by_id[getattr(profile, "user_id", ukey)] = (ukey, profile)

        for session_id, used_raw in raw_tokens.items():
            used = int(used_raw or 0)
            profile_info = profiles_by_id.get(session_id)
            user_key = profile_info[0] if profile_info else ""
            display_name = getattr(profile_info[1], "display_name", "") if profile_info else ""
            role = getattr(profile_info[1], "role", "") if profile_info else ""

            if not profile_info:
                sid = str(session_id)
                if sid.startswith("dm_"):
                    user_key = sid[3:]
                elif sid.startswith("chan_"):
                    user_key = sid
                else:
                    user_key = sid[:8] + ("..." if len(sid) > 8 else "")
                display_name = user_key
                role = "session"

            payload = token_usage_payload(str(session_id))
            payload.update({
                "user_key": user_key,
                "display_name": display_name,
                "role": role,
            })
            if not payload.get("active"):
                stale_count += 1
                continue
            sessions.append(payload)

            bucket = by_user_map.setdefault(user_key, {
                "user_key": user_key,
                "display_name": display_name,
                "role": role,
                "used": 0,
                "limit": TOKEN_SOFT_LIMIT,
                "session_count": 0,
            })
            bucket["used"] += used
            bucket["session_count"] += 1

        by_user = []
        for item in by_user_map.values():
            item["remaining"] = max(0, TOKEN_SOFT_LIMIT - item["used"])
            item["percent"] = min(100, round((item["used"] / TOKEN_SOFT_LIMIT) * 100, 1))
            item["level"] = token_level(item["used"])
            by_user.append(item)

        sessions.sort(key=lambda x: x["used"], reverse=True)
        by_user.sort(key=lambda x: x["used"], reverse=True)
        return {
            "limit": TOKEN_SOFT_LIMIT,
            "active_seconds": TOKEN_DASHBOARD_ACTIVE_SECONDS,
            "stale_count": stale_count,
            "sessions": sessions,
            "by_user": by_user,
        }
    except Exception as e:
        log("DASHBOARD", f"[!] Could not load token usage: {e}", Fore.YELLOW)
        return {"limit": TOKEN_SOFT_LIMIT, "sessions": [], "by_user": []}

# ==========================================
# CONFIG API (runtime_config.json overrides)
# ==========================================

@app.get("/api/config")
async def get_config_api(key: Optional[str] = None):
    """Returns current USE_* flags with runtime overrides applied."""
    verify_access(key, "debug")
    import config as _cfg  # noqa: PLC0415
    overrides = load_runtime_overrides()
    flags = {}
    for key_name in EXPOSED_FLAGS:
        base_val = getattr(_cfg, key_name, None)
        flags[key_name] = overrides.get(key_name, base_val)
    return {"flags": flags, "overrides": overrides, "maintenance": state.maintenance_status()}

@app.get("/api/maintenance/status")
async def maintenance_status_api(key: Optional[str] = None):
    """Current maintenance/drain state. Chat users may poll this to self-refresh."""
    key_info = get_key_info(key)
    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid key")
    status_data = state.maintenance_status()
    status_data["role"] = key_info.get("role")
    return status_data

@app.get("/api/expert_pool")
async def get_expert_pool_api(key: Optional[str] = None):
    """Returns current expert pool status for the Config tab.

    Merges benchmark-managed domains from expert_pool.json with ALL
    domains from EXPERT_OPENROUTER_OVERRIDES so nothing is invisible.
    """
    verify_access(key, "debug")
    try:
        from tools.expert_pool import get_pool_status
        pool_status = get_pool_status()
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="expert_pool_api")
        log_exception("DASHBOARD", err)
        pool_status = {"error": str(e), "domains": {}}

    # Merge non-managed domains from config so dashboard shows ALL experts
    try:
        import config as _cfg
        cost_catalog = dashboard_analytics.build_cost_catalog()
        price_by_model = {m.get("model"): m for m in cost_catalog.get("models", [])}
        overrides = getattr(_cfg, "EXPERT_OPENROUTER_OVERRIDES", {})
        existing = pool_status.get("domains", {})
        for domain, model_id in overrides.items():
            price = price_by_model.get(model_id) or {}
            if domain not in existing:
                existing[domain] = {
                    "benchmark": None,
                    "models": [{
                        "id": model_id,
                        "source": price.get("source") or "config",
                        "effective_cost_usd_per_m": price.get("input_usd_per_m"),
                        "input_cost_usd_per_m": price.get("input_usd_per_m"),
                        "output_cost_usd_per_m": price.get("output_usd_per_m"),
                    }],
                }
            else:
                for model in existing[domain].get("models", []):
                    price = price_by_model.get(model.get("id")) or {}
                    if price and model.get("effective_cost_usd_per_m") is None:
                        model["effective_cost_usd_per_m"] = price.get("input_usd_per_m")
                        model["input_cost_usd_per_m"] = price.get("input_usd_per_m")
                        model["output_cost_usd_per_m"] = price.get("output_usd_per_m")
                        model["source"] = price.get("source") or model.get("source")
        pool_status["domains"] = existing
    except Exception:
        pass  # config import fail → pool-only data is still fine

    return pool_status

@app.post("/api/config")
async def set_config_api(request: Request, key: Optional[str] = None):
    """Write a single runtime override (USE_* flags + IMAGE_MODEL)."""
    verify_access(key, "admin")
    try:
        data = await request.json()
        key_name = data.get("key", "")
        value    = data.get("value")
        allowed  = key_name in EXPOSED_FLAGS or key_name == "IMAGE_MODEL"
        if not allowed:
            return {"ok": False, "error": f"Key '{key_name}' is not allowed"}

        if key_name == "USE_MAINTENANCE":
            if value:
                pending = state.maintenance_pending_count()
                if pending > 0:
                    state.maintenance_draining = True
                    save_runtime_override("USE_MAINTENANCE", False)
                    log("DASHBOARD", f"[CFG] Maintenance drain started ({pending} pending)", Fore.YELLOW)
                    status_data = state.maintenance_status()
                    await state.broadcast_message("maintenance_status", status_data)
                    await state.broadcast_message("config_changed", {
                        "key": "USE_MAINTENANCE",
                        "value": False,
                        "maintenance": False,
                        "draining": True,
                        "pending": pending,
                    })
                    return {"ok": True, "key": key_name, "value": False, "draining": True, "pending": pending}

                state.maintenance_draining = False
                save_runtime_override("USE_MAINTENANCE", True)
                log("DASHBOARD", "[CFG] Maintenance active", Fore.CYAN)
                status_data = state.maintenance_status()
                await state.broadcast_message("maintenance_status", status_data)
                await state.broadcast_message("config_changed", {
                    "key": "USE_MAINTENANCE",
                    "value": True,
                    "maintenance": True,
                })
                await state.force_refresh_non_admins("maintenance_active")
                return {"ok": True, "key": key_name, "value": True, "maintenance": True}

            state.maintenance_draining = False
            save_runtime_override("USE_MAINTENANCE", False)
            log("DASHBOARD", "[CFG] Maintenance disabled", Fore.CYAN)
            status_data = state.maintenance_status()
            await state.broadcast_message("maintenance_status", status_data)
            await state.broadcast_message("config_changed", {
                "key": "USE_MAINTENANCE",
                "value": False,
                "maintenance": False,
                "draining": False,
            })
            return {"ok": True, "key": key_name, "value": False, "maintenance": False}

        save_runtime_override(key_name, value)
        log("DASHBOARD", f"[CFG] Config override: {key_name} = {value}", Fore.CYAN)
        await state.broadcast_message("config_changed", {
            "key": key_name,
            "value": value,
            "maintenance": bool(value) if key_name == "USE_MAINTENANCE" else None,
        })
        return {"ok": True, "key": key_name, "value": value}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/image_models")
async def get_image_models_api():
    """Returns available image models and the currently active one."""
    import config as _cfg
    overrides = load_runtime_overrides()
    active = overrides.get("IMAGE_MODEL", getattr(_cfg, "IMAGE_MODEL", "sourceful/riverflow-v2-fast"))
    models = getattr(_cfg, "IMAGE_MODELS", [active])
    return {"active": active, "models": models}


# ==========================================
# DISCORD PLATFORM LINKING
# ==========================================

@app.post("/api/discord/link/generate")
async def discord_link_generate(key: Optional[str] = None):
    """
    Generate a one-time code for linking a Discord account.
    Valid for 10 minutes. The user then types /link <CODE> in Discord.
    """
    verify_access(key, "chat")
    key_info = get_key_info(key)
    user_key = key_info["user_key"] if key_info else None
    if not user_key:
        raise HTTPException(status_code=400, detail="User not recognized")

    from helpers.platform_links import generate_link_code
    code = generate_link_code(user_key, ttl_seconds=600)

    return {
        "code": code,
        "user_key": user_key,
        "expires_in": 600,
        "hint": f"/link {code}",
    }


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
    """Return app version and active LLM metadata without auth."""
    return {
        "version": _APP_VERSION,
        "model": get_active_model(),
    }


# ==========================================
# APP API ROUTER  (mobile/app-specific endpoints)
# ==========================================

from app.app_api import router as _app_router
app.include_router(_app_router)


# ==========================================
# STATIC FILES (MOUNT AT ROOT LAST)
# Custom / route injects ?v= cache buster into index.html.
# ==========================================

_MAINTENANCE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YourAI - Be Right Back 🦊</title>
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
    <h1>YourAI will be right back!</h1>
    <p>A few updates are running in the background.<br>Check back in a few minutes!</p>
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
    # Check maintenance mode.
    import config as _cfg
    overrides = load_runtime_overrides()
    maintenance_on = overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False))
    if maintenance_on and get_role_for_key(key) != "admin":
        return HTMLResponse(content=_MAINTENANCE_HTML, status_code=503)

    html_path = os.path.join(_FRONTEND_DIR, "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Add ?v= only to local .css/.js files, not external CDN URLs.
        content = _re.sub(
            r'((?:href|src)="(?!https?://)[^"]+\.(?:css|js))(?:\?[^"]*)?(")',
            lambda m: f'{m.group(1)}?v={_APP_VERSION}{m.group(2)}',
            content
        )
        return HTMLResponse(content=content)
    except Exception as e:
        log("DASHBOARD", f"[ERR] index.html lesen fehlgeschlagen: {e}", Fore.RED)
        return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=500)

@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy():
    """Serve privacy.html — no auth required (DSGVO compliance)."""
    html_path = os.path.join(_FRONTEND_DIR, "privacy.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        log("DASHBOARD", f"[ERR] privacy.html lesen fehlgeschlagen: {e}", Fore.RED)
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)

@app.get("/terms", response_class=HTMLResponse)
async def serve_terms():
    """Serve terms.html — no auth required."""
    html_path = os.path.join(_FRONTEND_DIR, "terms.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        log("DASHBOARD", f"[ERR] terms.html lesen fehlgeschlagen: {e}", Fore.RED)
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)

if os.path.isdir(_FRONTEND_DIR):
    # Static assets; index.html is served through the custom route above.
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=False), name="frontend")

if __name__ == "__main__":
    try:
        log("DASHBOARD", "YourAI Dashboard v6 (Frontend Edition)", Fore.MAGENTA)
        log("DASHBOARD", f"   Root: {_FRONTEND_DIR}", Fore.LIGHTBLACK_EX)
        log("DASHBOARD", f"   URL:  http://localhost:8051", Fore.CYAN)
        log("DASHBOARD", "   Click Start in the Config tab to wake the brain.", Fore.CYAN)
        try:
            from tools.expert_pool import refresh_if_month_changed
            pool_refresh = refresh_if_month_changed()
            if pool_refresh.get("skipped"):
                log("DASHBOARD", "   Expert Pool: current month loaded", Fore.CYAN)
            else:
                log("DASHBOARD", f"   Expert Pool refresh: {pool_refresh.get('ok')} {pool_refresh.get('reason', '')}", Fore.CYAN)
        except Exception as pool_err:
            log("DASHBOARD", f"   Expert Pool init failed: {pool_err}", Fore.YELLOW)

        # Graceful shutdown: handle Ctrl+C properly.
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


