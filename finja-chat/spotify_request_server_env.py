#!/usr/bin/env python3
"""
======================================================================
                  Finja's Song Request Server
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.3.0
  Description: Robust moderated Song Request server for Spotify + Finja replies.

  ✨ New in 2.3.0:
    • Merged Production + GitHub tracks into one common ground (2026-07-19)
    • Auto-filter mode restored (SR_MODERATED=false: popularity/label filter
      instead of a manual accept/deny queue)
    • Finja Twitch AI-talk bridge restored (!ask/!chat/!say/!talk)
    • Moderation route handlers kept as separate functions (from GitHub 2.2.x)
    • Moderators/Broadcaster bypass cooldown + max-pending limit (from GitHub 2.2.2)

  📜 Changelog 2.2.x (GitHub track):
    • Complete English documentation with docstrings, type hints
    • Additional validation tests, better Spotify API mocking

  📜 Changelog 2.1.0 (Production track):
    • Auto-filter mode (SR_MODERATED=false) as alternative to moderation queue
    • Finja Twitch AI-talk bridge via command-bridge policy endpoint
    • Loads .env automatically (python-dotenv)
    • Handles "no active device" gracefully with Finja hint
    • Optional device preference via SPOTIFY_DEVICE_NAME / SPOTIFY_DEVICE_ID

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os
import time
import re
import signal
import sys
import urllib.parse
import urllib.request
from typing import Dict, Tuple, List, Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
from spotipy.exceptions import SpotifyException

# ==============================================================================
# Environment Configuration
# ==============================================================================

# Load environment variables from .env file -- lives in private/ (never
# committed/synced to GitHub), not next to this script anymore.
try:
    from dotenv import load_dotenv
    _ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "private", ".env")
    load_dotenv(_ENV_PATH)
except ImportError as e:
    print(f"[warn] dotenv not available: {e}")
except Exception as e:
    print(f"[warn] dotenv not loaded: {e}")

# Spotify API configuration
SPOTIFY_SCOPES = "user-read-playback-state user-modify-playback-state"

# Song request configuration
COOLDOWN_SECS = int(os.getenv("SR_COOLDOWN_SECS", "120"))
# false = auto-filter mode (popularity/label check, no manual queue)
# true  = full moderation queue (!accept/!deny/!rq)
MODERATED = os.getenv("SR_MODERATED", "false").lower() == "true"
FORCE_NOW_ON_ACCEPT = os.getenv("SR_FORCE_NOW", "false").lower() == "true"
MAX_PENDING_PER_USER = int(os.getenv("SR_MAX_PENDING_PER_USER", "1"))

# Optional device preferences
PREFERRED_DEVICE_NAME = os.getenv("SPOTIFY_DEVICE_NAME", "").strip()
PREFERRED_DEVICE_ID = os.getenv("SPOTIFY_DEVICE_ID", "").strip()

# Finja AI-talk bridge (policy-gated -- browser page must not hold
# OpenWebUI/OpenRouter credentials itself, everything goes through the
# command-bridge which decides if AI talk is currently enabled)
FINJA_BRIDGE_URL = os.getenv(
    "FINJA_BRIDGE_URL", "http://127.0.0.1:8051/api/twitch/command-bridge"
).strip()
FINJA_BRIDGE_TOKEN = os.getenv("FINJA_BRIDGE_TOKEN", "").strip()
FINJA_ASK_REPLY_DISABLED = os.getenv(
    "FINJA_ASK_REPLY_DISABLED",
    "@{user} AI chat is disabled on Twitch for safety/legal reasons. Use the "
    "dashboard or Discord private channel for real conversations.",
).strip()

# Auto-filter thresholds (only active when MODERATED=false)
MIN_POPULARITY = int(os.getenv("SR_MIN_POPULARITY", "15"))  # 0-100, below this -> decline
LABEL_BLACKLIST: set = {
    "ncs", "nocopyrightsounds", "ncs release",
    "monstercat ncs", "monstercat uncaged",
    "extrememusic", "epidemic sound",  # royalty-free libraries
}
NAME_BLACKLIST_KEYWORDS: list = ["[ncs release]", "(ncs release)", "ncs release"]

# Environment validation
print("[env] SPOTIPY_CLIENT_ID present:", bool(os.getenv("SPOTIPY_CLIENT_ID")))
if os.getenv("SPOTIPY_REDIRECT_URI"):
    print("[env] SPOTIPY_REDIRECT_URI:", os.getenv("SPOTIPY_REDIRECT_URI"))

# ==============================================================================
# Spotify Client Initialization
# ==============================================================================

# cache_handler explicit -- spotipy defaults to ".cache" in the CWD, but the
# real cached token lives in private/ now (never synced/committed).
sp = Spotify(auth_manager=SpotifyOAuth(
    scope=SPOTIFY_SCOPES,
    open_browser=False,
    cache_handler=CacheFileHandler(cache_path=_ENV_PATH.replace(".env", ".cache")),
))

# ==============================================================================
# FastAPI Application Setup
# ==============================================================================

app = FastAPI(title="Finja SongRequest v2 (Moderated)")

# Enable CORS for bot communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# Data Models
# ==============================================================================

class ChatCommand(BaseModel):
    """
    Represents a chat command from Twitch bot.

    Attributes:
        user: Username of the person issuing command
        message: Full message text including command
        is_mod: Whether user is a moderator
        is_broadcaster: Whether user is the broadcaster
    """
    user: str
    message: str
    is_mod: bool = False
    is_broadcaster: bool = False

# ==============================================================================
# Global State
# ==============================================================================

# User cooldown tracker: username -> timestamp
cooldown: Dict[str, float] = {}

# Pending requests: request_id -> request_data
pending: Dict[int, Dict[str, Any]] = {}

# User pending count tracker: username -> count
user_pending_count: Dict[str, int] = {}

# Next request ID counter
_next_id = 1

# ==============================================================================
# Helper Functions
# ==============================================================================

def now() -> float:
    """Returns current Unix timestamp."""
    return time.time()


def finja_twitch_talk_reply(user: str, question: str) -> str:
    """
    Returns the safe Twitch AI-talk reply using Finja's command-bridge policy.

    The browser-facing bot page must never hold OpenWebUI/OpenRouter
    credentials itself -- this asks the command-bridge whether AI talk is
    currently enabled, and falls back to a disabled-notice if the bridge is
    unreachable or reports it off.

    Args:
        user: Username asking the question
        question: The question text (unused until a real response flow exists)

    Returns:
        A chat-safe reply string
    """
    if not FINJA_BRIDGE_TOKEN:
        return FINJA_ASK_REPLY_DISABLED.format(user=user)

    try:
        query = urllib.parse.urlencode({"token": FINJA_BRIDGE_TOKEN})
        sep = "&" if "?" in FINJA_BRIDGE_URL else "?"
        req = urllib.request.Request(
            f"{FINJA_BRIDGE_URL}{sep}{query}", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[finja-bridge] unavailable: {e}")
        return FINJA_ASK_REPLY_DISABLED.format(user=user)

    if not data.get("ai_talk_enabled"):
        return FINJA_ASK_REPLY_DISABLED.format(user=user)

    return (
        f"@{user} Finja Twitch AI talk is enabled, but this command page is not "
        "wired to a paid/approved response flow yet."
    )


def finja_reply(
    kind: str,
    user: str,
    title: str = "",
    rid: Optional[int] = None,
    extra: str = ""
) -> str:
    """
    Generates Finja's response message for different scenarios.

    Args:
        kind: Type of response (cooldown, nohit, taken, etc.)
        user: Username to address
        title: Song title (if applicable)
        rid: Request ID (if applicable)
        extra: Extra information for error messages

    Returns:
        Formatted Finja response message
    """
    if kind == "cooldown":
        return f"💤 Finja: Kurz mal durchatmen, {user}! Alle {COOLDOWN_SECS}s ist ein Wunsch drin."
    if kind == "nohit":
        return f"🤔 Finja: Hm, ich hab nix auf Spotify gefunden… magst du einen direkten Link versuchen, {user}?"
    if kind == "taken":
        return f"🕓 Finja: Wunsch gespeichert (ID {rid}). Ich geb dir Bescheid, wenn's freigegeben ist, {user}!"
    if kind == "queued":
        return f"💿 Finja: '{title}' kommt in die Queue. Gleich geht's los! 🎧"
    if kind == "accept_now":
        return f"✅ Finja: '{title}' läuft JETZT – viel Spaß! 🎶"
    if kind == "accept_queue":
        return f"✅ Finja: '{title}' wurde zur Queue hinzugefügt! 💿"
    if kind == "deny":
        return "⛔ Finja: Der Wunsch wurde abgelehnt. Nicht böse sein, okay? 💙"
    if kind == "no_pending":
        return "📝 Finja: Es gibt gerade keine offenen Wünsche."
    if kind == "too_many":
        return f"🚦 Finja: {user}, du hast schon einen offenen Wunsch. Warte kurz, bis er entschieden ist."
    if kind == "no_device":
        return (
            "📵 Finja: Ich finde kein aktives Spotify-Gerät. "
            "Öffne Spotify auf deinem PC/Handy und starte kurz einen Song, "
            "dann probier's nochmal. (Tipp: SPOTIFY_DEVICE_NAME/ID in .env setzen, wenn du willst.)"
        )
    if kind == "filtered_popularity":
        return f"❌ Finja: Sorry {user}, '{title}' ist zu unbekannt für die Queue. Versuch was Bekannteres! 🎵"
    if kind == "filtered_label":
        return f"❌ Finja: Sorry {user}, NCS/Royalty-Free Zeug kommt hier nicht rein. 😇 Versuch was anderes!"
    if kind == "auto_queued":
        return f"✅ @{user} — '{title}' wurde zur Queue hinzugefügt! 🎶"
    if kind == "error":
        return f"⚠️ Finja: Uff, da ist was schiefgegangen: {extra or 'Unbekannter Fehler'}"
    return "✨ Finja"


def on_cooldown(user: str) -> bool:
    """Checks if a user is currently on cooldown."""
    timestamp = cooldown.get(user.lower(), 0)
    return now() - timestamp < COOLDOWN_SECS


def set_cooldown(user: str) -> None:
    """Sets cooldown timestamp for a user."""
    cooldown[user.lower()] = now()


def can_act(is_mod: bool, is_broadcaster: bool) -> bool:
    """Checks if user has permission to moderate requests."""
    return bool(is_broadcaster or is_mod)


def parse_track_uri_or_query(text: str) -> Tuple[str, str]:
    """
    Parses text to extract Spotify URI or search query.

    Returns:
        Tuple of (spotify_uri, search_query). If URI found, search_query is
        empty; if no URI found, spotify_uri is empty.
    """
    pattern = r"(spotify:track:[A-Za-z0-9]+|https?://open\.spotify\.com/track/[A-Za-z0-9]+)"
    match = re.search(pattern, text or "")

    if match:
        uri = match.group(1)
        if uri.startswith("http"):
            track_id = uri.rstrip("/").split("/")[-1].split("?")[0]
            return f"spotify:track:{track_id}", ""
        return uri, ""

    return "", (text or "").strip()


def check_track_filter(uri: str) -> Tuple[bool, str]:
    """
    Auto-filter for song requests (only used when MODERATED=false).

    Checks popularity >= MIN_POPULARITY, label not in blacklist, and name
    not containing blacklisted keywords (NCS/royalty-free releases).

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    try:
        track_id = uri.split(":")[-1]
        track = sp.track(track_id)
        if not track:
            return False, "not_found"

        popularity = track.get("popularity", 0)
        if popularity < MIN_POPULARITY:
            return False, f"popularity:{popularity}"

        track_name = (track.get("name") or "").lower()
        for kw in NAME_BLACKLIST_KEYWORDS:
            if kw in track_name:
                return False, "label_blacklist"

        album_id = (track.get("album") or {}).get("id")
        if album_id:
            album = sp.album(album_id)
            label = (album.get("label") or "").lower().strip()
            if label in LABEL_BLACKLIST:
                return False, "label_blacklist"

        return True, "ok"
    except Exception as e:
        print(f"[filter] Fehler bei {uri}: {e}")
        return True, "ok"  # im Zweifel durchlassen


def search_track_uri(query: str) -> str:
    """
    Searches Spotify for a track and returns its URI.

    Returns:
        Spotify URI of first result, or empty string if not found
    """
    if not query:
        return ""

    try:
        result = sp.search(q=query, type="track", limit=5)
        items = []

        if result and isinstance(result, dict):
            tracks = result.get("tracks", {})
            if isinstance(tracks, dict):
                items = tracks.get("items", []) or []

        if items and len(items) > 0:
            uri = items[0].get("uri", "")
            return uri if uri else ""

    except SpotifyException as e:
        print(f"[Spotify] Search error for '{query}': {e}")
    except Exception as e:
        print(f"[Spotify] Unexpected error searching '{query}': {e}")

    print(f"[Spotify] No results for: {query}")
    return ""


def track_title_from_uri(uri: str) -> str:
    """
    Fetches track title and artists from Spotify URI.

    Returns:
        Formatted string: "Track Name – Artist(s)"
    """
    try:
        track_id = uri.split(":")[-1]
        track = sp.track(track_id)

        if not track:
            return f"(unbekannter Track {track_id})"

        artists = ", ".join(
            artist.get("name", "?") for artist in track.get("artists", [])
        )
        track_name = track.get("name", "?")

        return f"{track_name} – {artists or '?'}"

    except SpotifyException as e:
        print(f"[track_title_from_uri] Spotify error: {e}")
        return f"(Fehler bei {uri})"
    except Exception as e:
        print(f"[track_title_from_uri] Unexpected error: {e}")
        return f"(Fehler bei {uri})"


def list_devices() -> List[Dict[str, Any]]:
    """Lists all available Spotify devices."""
    try:
        result: Any = sp.devices()
    except SpotifyException as e:
        print(f"[devices] Spotify error: {e}")
        return []
    except Exception as e:
        print(f"[devices] Unexpected error: {e}")
        return []

    if not isinstance(result, dict):
        return []

    raw_devices: Any = result.get("devices")
    if not isinstance(raw_devices, list):
        return []

    devices: List[Dict[str, Any]] = []
    for device in raw_devices:
        if not isinstance(device, dict):
            continue

        devices.append({
            "id": device.get("id"),
            "name": device.get("name"),
            "type": device.get("type"),
            "is_active": device.get("is_active"),
            "volume": device.get("volume_percent"),
        })

    return devices


def find_device_by_id(devices: List[Dict[str, Any]], device_id: str) -> Optional[str]:
    """Finds device by ID."""
    for device in devices:
        if device.get("id") == device_id:
            return device_id
    return None


def find_device_by_name(devices: List[Dict[str, Any]], device_name: str) -> Optional[str]:
    """Finds device by name (case-insensitive)."""
    for device in devices:
        if device.get("name", "").lower() == device_name.lower():
            return device.get("id") or None
    return None


def find_active_device(devices: List[Dict[str, Any]]) -> Optional[str]:
    """Finds currently active device."""
    for device in devices:
        if device.get("is_active"):
            return device.get("id") or None
    return None


def pick_device_id() -> str:
    """
    Picks the best Spotify device to use.

    Priority: PREFERRED_DEVICE_ID -> PREFERRED_DEVICE_NAME -> currently
    active device -> first available device.
    """
    devices = list_devices()

    if PREFERRED_DEVICE_ID:
        device_id = find_device_by_id(devices, PREFERRED_DEVICE_ID)
        if device_id:
            return device_id

    if PREFERRED_DEVICE_NAME:
        device_id = find_device_by_name(devices, PREFERRED_DEVICE_NAME)
        if device_id:
            return device_id

    active_id = find_active_device(devices)
    if active_id:
        return active_id

    if devices:
        return devices[0].get("id") or ""

    return ""


def add_to_queue(uri: str) -> Tuple[bool, Optional[str]]:
    """Adds a track to the Spotify queue."""
    device_id = pick_device_id()

    try:
        if device_id:
            sp.add_to_queue(uri, device_id=device_id)
        else:
            # Works only if Spotify already has an active device
            sp.add_to_queue(uri)
        return True, None

    except SpotifyException as e:
        error_msg = str(e)
        if "NO_ACTIVE_DEVICE" in error_msg or "No active device found" in error_msg:
            return False, "NO_ACTIVE_DEVICE"
        return False, error_msg

    except Exception as e:
        print(f"[add_to_queue] Unexpected error: {e}")
        return False, str(e)


def force_play_now(uri: str) -> Tuple[bool, Optional[str]]:
    """Starts playing a track immediately."""
    device_id = pick_device_id()

    try:
        sp.start_playback(device_id=device_id or None, uris=[uri])
        return True, None

    except SpotifyException as e:
        error_msg = str(e)
        if "NO_ACTIVE_DEVICE" in error_msg or "No active device found" in error_msg:
            return False, "NO_ACTIVE_DEVICE"
        return False, error_msg

    except Exception as e:
        print(f"[force_play_now] Unexpected error: {e}")
        return False, str(e)


# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"ok": True, "pending": len(pending), "moderated": MODERATED}


class ModeCommand(BaseModel):
    """Body for POST /mode -- switches between auto-filter and moderation queue."""
    moderated: bool


@app.get("/mode")
def get_mode() -> Dict[str, bool]:
    """Returns the current song-request mode."""
    return {"moderated": MODERATED}


@app.post("/mode")
def set_mode(cmd: ModeCommand) -> Dict[str, bool]:
    """
    Switches between auto-filter mode (moderated=false, for Finja's 24/7
    unattended stream -- popularity/label filter decides automatically) and
    moderation queue mode (moderated=true, for active streaming -- streamer/mod
    accepts or denies each request via !accept/!deny or the bot panel).

    Does not affect requests already pending -- those still need to be
    accepted/denied/expire normally.
    """
    global MODERATED
    MODERATED = cmd.moderated
    print(f"[mode] Switched to {'moderated queue' if MODERATED else 'auto-filter'} mode")
    return {"moderated": MODERATED}


@app.get("/pending")
def get_pending() -> Dict[str, List[Dict[str, Any]]]:
    """Returns list of pending song requests (moderation mode only)."""
    pending_list = [
        {
            "id": request_id,
            "title": request_data["title"],
            "user": request_data["user"],
            "ts": request_data["ts"]
        }
        for request_id, request_data in sorted(pending.items())
    ]
    return {"pending": pending_list}


@app.get("/devices")
def get_devices() -> Dict[str, List[Dict[str, Any]]]:
    """Returns list of available Spotify devices."""
    return {"devices": list_devices()}


@app.post("/chat")
def handle_chat(cmd: ChatCommand) -> Dict[str, str]:
    """
    Handles chat commands for song requests and Finja AI-talk.

    Supported commands:
    - !ask/!chat/!say/!talk <question>: Finja AI-talk (policy-gated)
    - !accept <id>: Moderator accepts a pending request (moderation mode)
    - !deny <id>: Moderator denies a pending request (moderation mode)
    - !rq / !requests / !pending: Lists pending requests (moderation mode)
    - !sr / !songrequest / !queue / !q <query|uri>: Request a song
    """
    global _next_id

    message = (cmd.message or "").strip()
    lower_message = message.lower()

    # Finja AI-talk commands are policy-gated through the Finja dashboard
    # bridge -- the browser page must not hold OpenWebUI/OpenRouter credentials.
    if lower_message.startswith(("!ask ", "!chat ", "!say ", "!talk ")) or \
            lower_message in ("!ask", "!chat", "!say", "!talk"):
        if " " not in message:
            return {"reply": "", "finja": f"@{cmd.user}, du musst mir schon eine Frage stellen."}
        question = message.split(" ", 1)[1].strip()
        return {"reply": "", "finja": finja_twitch_talk_reply(cmd.user, question)}

    # ========== Moderation Commands ==========

    if lower_message.startswith("!accept "):
        return handle_accept_command(cmd, lower_message)

    if lower_message.startswith("!deny "):
        return handle_deny_command(cmd, lower_message)

    if lower_message in ("!rq", "!requests", "!pending"):
        return handle_list_requests(cmd)

    # ========== Viewer Commands ==========

    if lower_message.startswith(("!sr ", "!songrequest ", "!queue ", "!q ")):
        return handle_song_request(cmd, message)

    return {"reply": "", "finja": ""}


def handle_accept_command(cmd: ChatCommand, lower_message: str) -> Dict[str, str]:
    """Handles !accept command to approve a pending request (moderation mode)."""
    if not can_act(cmd.is_mod, cmd.is_broadcaster):
        return {"reply": "Nur Mods/Streamer können akzeptieren.", "finja": ""}

    try:
        request_id = int(lower_message.split()[1])
    except (IndexError, ValueError):
        return {"reply": "Usage: !accept <id>", "finja": ""}

    if request_id not in pending:
        return {"reply": f"ID {request_id} nicht gefunden.", "finja": ""}

    request = pending.pop(request_id)
    user_pending_count[request["user"].lower()] = max(
        0, user_pending_count.get(request["user"].lower(), 1) - 1
    )
    title = request["title"]

    if FORCE_NOW_ON_ACCEPT:
        success, error = force_play_now(request["uri"])
        if not success and error == "NO_ACTIVE_DEVICE":
            return {"reply": "", "finja": finja_reply("no_device", request["user"])}
        if not success:
            return {
                "reply": f"Fehler beim Starten: {error}",
                "finja": finja_reply("error", request["user"], extra=str(error)),
            }
        return {
            "reply": f"ACCEPT: {title} → play now",
            "finja": finja_reply("accept_now", request["user"], title),
        }
    else:
        success, error = add_to_queue(request["uri"])
        if not success and error == "NO_ACTIVE_DEVICE":
            return {"reply": "", "finja": finja_reply("no_device", request["user"])}
        if not success:
            return {
                "reply": f"Fehler beim Queue: {error}",
                "finja": finja_reply("error", request["user"], extra=str(error)),
            }
        return {
            "reply": f"ACCEPT: {title} → queued",
            "finja": finja_reply("accept_queue", request["user"], title),
        }


def handle_deny_command(cmd: ChatCommand, lower_message: str) -> Dict[str, str]:
    """Handles !deny command to reject a pending request (moderation mode)."""
    if not can_act(cmd.is_mod, cmd.is_broadcaster):
        return {"reply": "Nur Mods/Streamer können ablehnen.", "finja": ""}

    try:
        request_id = int(lower_message.split()[1])
    except (IndexError, ValueError):
        return {"reply": "Usage: !deny <id>", "finja": ""}

    if request_id not in pending:
        return {"reply": f"ID {request_id} nicht gefunden.", "finja": ""}

    request = pending.pop(request_id)
    user_pending_count[request["user"].lower()] = max(
        0, user_pending_count.get(request["user"].lower(), 1) - 1
    )

    return {
        "reply": f"DENY: {request['title']}",
        "finja": finja_reply("deny", request["user"], request["title"]),
    }


def handle_list_requests(cmd: ChatCommand) -> Dict[str, str]:
    """Handles !rq/!requests/!pending command to list pending requests."""
    if not can_act(cmd.is_mod, cmd.is_broadcaster):
        return {"reply": "Nur Mods/Streamer.", "finja": ""}

    if not pending:
        return {"reply": "Keine offenen Requests.", "finja": finja_reply("no_pending", cmd.user)}

    request_list = []
    for request_id, request_data in sorted(pending.items()):
        title = request_data.get("title", "?")
        user = request_data.get("user", "?")
        request_list.append(f"{request_id}: {title} — {user}")

    return {"reply": "Offene Requests | " + " | ".join(request_list), "finja": ""}


def handle_song_request(cmd: ChatCommand, message: str) -> Dict[str, str]:
    """
    Handles !sr/!songrequest/!queue/!q command to request a song.

    In auto-filter mode (MODERATED=false) the track is checked against
    popularity/label rules and queued directly. In moderation mode
    (MODERATED=true) it's stored as a pending request for !accept/!deny.
    """
    global _next_id

    # Mods/Broadcaster bypass cooldown and pending-limit checks
    if not can_act(cmd.is_mod, cmd.is_broadcaster) and on_cooldown(cmd.user):
        return {"reply": "", "finja": finja_reply("cooldown", cmd.user)}

    if MODERATED and not can_act(cmd.is_mod, cmd.is_broadcaster) and \
            user_pending_count.get(cmd.user.lower(), 0) >= MAX_PENDING_PER_USER:
        return {"reply": "", "finja": finja_reply("too_many", cmd.user)}

    query = message.split(" ", 1)[1].strip() if " " in message else ""
    uri, search = parse_track_uri_or_query(query)

    if not uri:
        uri = search_track_uri(search)
        if not uri:
            return {"reply": "", "finja": finja_reply("nohit", cmd.user)}

    title = track_title_from_uri(uri)
    set_cooldown(cmd.user)

    # ── AUTO-FILTER MODE (MODERATED=false) ──────────────────────────────
    if not MODERATED:
        allowed, reason = check_track_filter(uri)
        if not allowed:
            kind = "filtered_label" if reason == "label_blacklist" else "filtered_popularity"
            return {"reply": f"DECLINED ({reason}): {title}", "finja": finja_reply(kind, cmd.user, title)}

        ok, err = add_to_queue(uri)
        if not ok and err == "NO_ACTIVE_DEVICE":
            return {"reply": "", "finja": finja_reply("no_device", cmd.user)}
        if not ok:
            return {"reply": f"Queue-Fehler: {err}", "finja": finja_reply("error", cmd.user, extra=str(err))}
        return {"reply": f"AUTO-QUEUED: {title}", "finja": finja_reply("auto_queued", cmd.user, title)}

    # ── MODERATED MODE (MODERATED=true) → pending queue ─────────────────
    request_id = _next_id
    _next_id += 1
    pending[request_id] = {"user": cmd.user, "uri": uri, "title": title, "ts": now()}
    user_pending_count[cmd.user.lower()] = user_pending_count.get(cmd.user.lower(), 0) + 1
    return {
        "reply": f"Wunsch gespeichert (ID {request_id}): {title}",
        "finja": finja_reply("taken", cmd.user, title, request_id),
    }


# ==============================================================================
# Application Startup & Shutdown
# ==============================================================================

def handle_shutdown(signum, frame):
    """Handles graceful shutdown on SIGINT (Ctrl+C) or SIGTERM."""
    print("\n[INFO] Shutting down gracefully...")
    print("[INFO] Pending requests:", len(pending))
    sys.exit(0)


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("  Finja Song Request Server v2.3.0")
    print("=" * 70)
    print(f"  Moderated: {MODERATED}")
    print(f"  Cooldown: {COOLDOWN_SECS}s")
    print(f"  Max pending per user: {MAX_PENDING_PER_USER}")
    print(f"  Force play on accept: {FORCE_NOW_ON_ACCEPT}")
    if not MODERATED:
        print(f"  Min popularity: {MIN_POPULARITY}")
    if PREFERRED_DEVICE_NAME:
        print(f"  Preferred device name: {PREFERRED_DEVICE_NAME}")
    if PREFERRED_DEVICE_ID:
        print(f"  Preferred device ID: {PREFERRED_DEVICE_ID}")
    print("=" * 70)
    print()
    print("[INFO] Starting server on http://127.0.0.1:8099")
    print("[INFO] Press Ctrl+C to stop")
    print()

    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="info")
