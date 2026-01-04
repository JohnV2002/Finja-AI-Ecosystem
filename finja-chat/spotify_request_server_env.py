#!/usr/bin/env python3
"""
======================================================================
                  Finja's Song Request Server
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.2.1
  Description: Moderated Spotify song request server with queue.

  ✨ New in 2.2.1:
    • Code Quality: All SonarQube issues resolved
    • Complete English code documentation with docstrings
    • Improved error handling with specific exception types
    • Type hints throughout for better IDE support
    • Consistent variable naming (snake_case)
    • Removed bare exception handlers

  📜 Changelog 2.1.0:
    • Loads .env automatically (python-dotenv)
    • Handles "no active device" gracefully with Finja hints
    • Optional device preference via SPOTIFY_DEVICE_NAME/ID
    • Safe-guards for Spotify API calls
    • Endpoints: /health, /pending, /devices, POST /chat

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
from typing import Dict, Tuple, List, Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException

# ==============================================================================
# Environment Configuration
# ==============================================================================

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError as e:
    print(f"[warn] dotenv not available: {e}")
except Exception as e:
    print(f"[warn] dotenv not loaded: {e}")

# Spotify API configuration
SPOTIFY_SCOPES = "user-read-playback-state user-modify-playback-state"

# Song request configuration
COOLDOWN_SECS = int(os.getenv("SR_COOLDOWN_SECS", "120"))
MODERATED = True
FORCE_NOW_ON_ACCEPT = os.getenv("SR_FORCE_NOW", "false").lower() == "true"
MAX_PENDING_PER_USER = int(os.getenv("SR_MAX_PENDING_PER_USER", "1"))

# Optional device preferences
PREFERRED_DEVICE_NAME = os.getenv("SPOTIFY_DEVICE_NAME", "").strip()
PREFERRED_DEVICE_ID = os.getenv("SPOTIFY_DEVICE_ID", "").strip()

# Environment validation
print("[env] SPOTIPY_CLIENT_ID present:", bool(os.getenv("SPOTIPY_CLIENT_ID")))
if os.getenv("SPOTIPY_REDIRECT_URI"):
    print("[env] SPOTIPY_REDIRECT_URI:", os.getenv("SPOTIPY_REDIRECT_URI"))

# ==============================================================================
# Spotify Client Initialization
# ==============================================================================

sp = Spotify(auth_manager=SpotifyOAuth(
    scope=SPOTIFY_SCOPES,
    open_browser=False
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
        return f"💤 Finja: Take a breather, {user}! One request every {COOLDOWN_SECS}s."
    
    if kind == "nohit":
        return f"🤔 Finja: Hmm, couldn't find anything on Spotify... try a direct link, {user}?"
    
    if kind == "taken":
        return f"🕐 Finja: Request saved (ID {rid}). I'll let you know when it's approved, {user}!"
    
    if kind == "queued":
        return f"💿 Finja: '{title}' is going into the queue. Starting soon! 🎧"
    
    if kind == "accept_now":
        return f"✅ Finja: '{title}' is playing NOW — enjoy! 🎶"
    
    if kind == "accept_queue":
        return f"✅ Finja: '{title}' has been added to the queue! 💿"
    
    if kind == "deny":
        return "⛔ Finja: The request was denied. No hard feelings, okay? 💙"
    
    if kind == "no_pending":
        return "📭 Finja: There are no pending requests right now."
    
    if kind == "too_many":
        return f"🚦 Finja: {user}, you already have a pending request. Wait for it to be decided first."
    
    if kind == "no_device":
        return (
            "🔵 Finja: I can't find an active Spotify device. "
            "Open Spotify on your PC/phone and play a song briefly, "
            "then try again. (Tip: Set SPOTIFY_DEVICE_NAME/ID in .env if needed.)"
        )
    
    if kind == "error":
        return f"⚠️ Finja: Oops, something went wrong: {extra or 'Unknown error'}"
    
    return "✨ Finja"


def on_cooldown(user: str) -> bool:
    """
    Checks if a user is currently on cooldown.
    
    Args:
        user: Username to check
    
    Returns:
        True if user is on cooldown, False otherwise
    """
    timestamp = cooldown.get(user.lower(), 0)
    return now() - timestamp < COOLDOWN_SECS


def set_cooldown(user: str) -> None:
    """
    Sets cooldown timestamp for a user.
    
    Args:
        user: Username to set cooldown for
    """
    cooldown[user.lower()] = now()


def can_act(is_mod: bool, is_broadcaster: bool) -> bool:
    """
    Checks if user has permission to moderate requests.
    
    Args:
        is_mod: Whether user is a moderator
        is_broadcaster: Whether user is the broadcaster
    
    Returns:
        True if user can moderate, False otherwise
    """
    return bool(is_broadcaster or is_mod)


def parse_track_uri_or_query(text: str) -> Tuple[str, str]:
    """
    Parses text to extract Spotify URI or search query.
    
    Handles both direct Spotify URIs/URLs and search queries.
    
    Args:
        text: Input text to parse
    
    Returns:
        Tuple of (spotify_uri, search_query)
        If URI found, search_query is empty
        If no URI found, spotify_uri is empty
    """
    pattern = r"(spotify:track:[A-Za-z0-9]+|https?://open\.spotify\.com/track/[A-Za-z0-9]+)"
    match = re.search(pattern, text or "")
    
    if match:
        uri = match.group(1)
        if uri.startswith("http"):
            # Extract track ID from URL
            track_id = uri.rstrip("/").split("/")[-1].split("?")[0]
            return f"spotify:track:{track_id}", ""
        return uri, ""
    
    return "", (text or "").strip()


def search_track_uri(query: str) -> str:
    """
    Searches Spotify for a track and returns its URI.
    
    Args:
        query: Search query string
    
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
    
    Args:
        uri: Spotify track URI
    
    Returns:
        Formatted string: "Track Name — Artist(s)"
    """
    try:
        track_id = uri.split(":")[-1]
        track = sp.track(track_id)
        
        if not track:
            return f"(unknown track {track_id})"
        
        artists = ", ".join(
            artist.get("name", "?") for artist in track.get("artists", [])
        )
        track_name = track.get("name", "?")
        
        return f"{track_name} — {artists or '?'}"
        
    except SpotifyException as e:
        print(f"[track_title_from_uri] Spotify error: {e}")
        return f"(error for {uri})"
    except Exception as e:
        print(f"[track_title_from_uri] Unexpected error: {e}")
        return f"(error for {uri})"


def list_devices() -> List[Dict[str, Any]]:
    """
    Lists all available Spotify devices.
    
    Returns:
        List of device dictionaries with id, name, type, is_active, volume
    """
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
    """
    Finds device by ID.
    
    Args:
        devices: List of device dictionaries
        device_id: Device ID to find
    
    Returns:
        Device ID if found, None otherwise
    """
    for device in devices:
        if device.get("id") == device_id:
            return device_id
    return None


def find_device_by_name(devices: List[Dict[str, Any]], device_name: str) -> Optional[str]:
    """
    Finds device by name (case-insensitive).
    
    Args:
        devices: List of device dictionaries
        device_name: Device name to find
    
    Returns:
        Device ID if found, None otherwise
    """
    for device in devices:
        if device.get("name", "").lower() == device_name.lower():
            return device.get("id") or None
    return None


def find_active_device(devices: List[Dict[str, Any]]) -> Optional[str]:
    """
    Finds currently active device.
    
    Args:
        devices: List of device dictionaries
    
    Returns:
        Device ID if active device found, None otherwise
    """
    for device in devices:
        if device.get("is_active"):
            return device.get("id") or None
    return None


def pick_device_id() -> str:
    """
    Picks the best Spotify device to use.
    
    Priority:
    1. PREFERRED_DEVICE_ID (if set and available)
    2. PREFERRED_DEVICE_NAME (if set and available)
    3. Currently active device
    4. First available device
    
    Returns:
        Device ID string, or empty string if no devices available
    """
    devices = list_devices()
    
    # Check for preferred device ID
    if PREFERRED_DEVICE_ID:
        device_id = find_device_by_id(devices, PREFERRED_DEVICE_ID)
        if device_id:
            return device_id
    
    # Check for preferred device name
    if PREFERRED_DEVICE_NAME:
        device_id = find_device_by_name(devices, PREFERRED_DEVICE_NAME)
        if device_id:
            return device_id
    
    # Check for active device
    active_id = find_active_device(devices)
    if active_id:
        return active_id
    
    # Fallback to first available device
    if devices:
        return devices[0].get("id") or ""
    
    return ""


def add_to_queue(uri: str) -> Tuple[bool, Optional[str]]:
    """
    Adds a track to the Spotify queue.
    
    Args:
        uri: Spotify track URI
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
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
    """
    Starts playing a track immediately.
    
    Args:
        uri: Spotify track URI
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    device_id = pick_device_id()
    
    try:
        sp.start_playback(
            device_id=device_id or None,
            uris=[uri]
        )
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
    """
    Health check endpoint.
    
    Returns:
        Dictionary with ok status and pending request count
    """
    return {
        "ok": True,
        "pending": len(pending)
    }


@app.get("/pending")
def get_pending() -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns list of pending song requests.
    
    Returns:
        Dictionary with pending array containing request details
    """
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
    """
    Returns list of available Spotify devices.
    
    Returns:
        Dictionary with devices array
    """
    return {"devices": list_devices()}


@app.post("/chat")
def handle_chat(cmd: ChatCommand) -> Dict[str, str]:
    """
    Handles chat commands for song requests.
    
    Supported commands:
    - !accept <id>: Moderator accepts a request
    - !deny <id>: Moderator denies a request
    - !rq / !requests / !pending: Lists pending requests
    - !sr / !songrequest / !queue / !q <query|uri>: Request a song
    
    Args:
        cmd: ChatCommand model with user, message, and permissions
    
    Returns:
        Dictionary with reply (for logs) and finja (for chat)
    """
    global _next_id
    
    message = (cmd.message or "").strip()
    lower_message = message.lower()

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


def handle_accept_command(
    cmd: ChatCommand,
    lower_message: str
) -> Dict[str, str]:
    """
    Handles !accept command to approve pending request.
    
    Args:
        cmd: ChatCommand with user permissions
        lower_message: Lowercase command message
    
    Returns:
        Response dictionary with reply and finja messages
    """
    if not can_act(cmd.is_mod, cmd.is_broadcaster):
        return {
            "reply": "Only mods/broadcaster can accept.",
            "finja": ""
        }
    
    try:
        request_id = int(lower_message.split()[1])
    except (IndexError, ValueError):
        return {
            "reply": "Usage: !accept <id>",
            "finja": ""
        }
    
    if request_id not in pending:
        return {
            "reply": f"ID {request_id} not found.",
            "finja": ""
        }
    
    request = pending.pop(request_id)
    user_pending_count[request["user"].lower()] = max(
        0,
        user_pending_count.get(request["user"].lower(), 1) - 1
    )
    
    title = request["title"]

    if FORCE_NOW_ON_ACCEPT:
        success, error = force_play_now(request["uri"])
        if not success and error == "NO_ACTIVE_DEVICE":
            return {
                "reply": "",
                "finja": finja_reply("no_device", request["user"])
            }
        if not success:
            return {
                "reply": f"Error starting playback: {error}",
                "finja": finja_reply("error", request["user"], extra=str(error))
            }
        return {
            "reply": f"ACCEPT: {title} → play now",
            "finja": finja_reply("accept_now", request["user"], title)
        }
    else:
        success, error = add_to_queue(request["uri"])
        if not success and error == "NO_ACTIVE_DEVICE":
            return {
                "reply": "",
                "finja": finja_reply("no_device", request["user"])
            }
        if not success:
            return {
                "reply": f"Error adding to queue: {error}",
                "finja": finja_reply("error", request["user"], extra=str(error))
            }
        return {
            "reply": f"ACCEPT: {title} → queued",
            "finja": finja_reply("accept_queue", request["user"], title)
        }


def handle_deny_command(
    cmd: ChatCommand,
    lower_message: str
) -> Dict[str, str]:
    """
    Handles !deny command to reject pending request.
    
    Args:
        cmd: ChatCommand with user permissions
        lower_message: Lowercase command message
    
    Returns:
        Response dictionary with reply and finja messages
    """
    if not can_act(cmd.is_mod, cmd.is_broadcaster):
        return {
            "reply": "Only mods/broadcaster can deny.",
            "finja": ""
        }
    
    try:
        request_id = int(lower_message.split()[1])
    except (IndexError, ValueError):
        return {
            "reply": "Usage: !deny <id>",
            "finja": ""
        }
    
    if request_id not in pending:
        return {
            "reply": f"ID {request_id} not found.",
            "finja": ""
        }
    
    request = pending.pop(request_id)
    user_pending_count[request["user"].lower()] = max(
        0,
        user_pending_count.get(request["user"].lower(), 1) - 1
    )
    
    return {
        "reply": f"DENY: {request['title']}",
        "finja": finja_reply("deny", request["user"], request["title"])
    }


def handle_list_requests(cmd: ChatCommand) -> Dict[str, str]:
    """
    Handles !rq/!requests/!pending command to list pending requests.
    
    Args:
        cmd: ChatCommand with user permissions
    
    Returns:
        Response dictionary with reply and finja messages
    """
    if not can_act(cmd.is_mod, cmd.is_broadcaster):
        return {
            "reply": "Only mods/broadcaster.",
            "finja": ""
        }
    
    if not pending:
        return {
            "reply": "No pending requests.",
            "finja": finja_reply("no_pending", cmd.user)
        }
    
    request_list = []
    for request_id, request_data in sorted(pending.items()):
        title = request_data.get("title", "?")
        user = request_data.get("user", "?")
        request_list.append(f"{request_id}: {title} — {user}")
    
    return {
        "reply": "Pending requests | " + " | ".join(request_list),
        "finja": ""
    }


def handle_song_request(
    cmd: ChatCommand,
    message: str
) -> Dict[str, str]:
    """
    Handles !sr/!songrequest/!queue/!q command to request a song.
    
    Args:
        cmd: ChatCommand with user info
        message: Original message text
    
    Returns:
        Response dictionary with reply and finja messages
    """
    global _next_id
    
    # Check cooldown
    if on_cooldown(cmd.user):
        return {
            "reply": "",
            "finja": finja_reply("cooldown", cmd.user)
        }
    
    # Check pending limit
    if user_pending_count.get(cmd.user.lower(), 0) >= MAX_PENDING_PER_USER:
        return {
            "reply": "",
            "finja": finja_reply("too_many", cmd.user)
        }

    # Extract query from message
    query = message.split(" ", 1)[1].strip() if " " in message else ""
    
    # Parse URI or search query
    uri, search = parse_track_uri_or_query(query)
    
    if not uri:
        uri = search_track_uri(search)
        if not uri:
            return {
                "reply": "",
                "finja": finja_reply("nohit", cmd.user)
            }

    # Get track title
    title = track_title_from_uri(uri)
    
    # Set cooldown
    set_cooldown(cmd.user)

    # Create pending request
    request_id = _next_id
    _next_id += 1
    
    pending[request_id] = {
        "user": cmd.user,
        "uri": uri,
        "title": title,
        "ts": now()
    }
    
    user_pending_count[cmd.user.lower()] = (
        user_pending_count.get(cmd.user.lower(), 0) + 1
    )
    
    return {
        "reply": f"Request saved (ID {request_id}): {title}",
        "finja": finja_reply("taken", cmd.user, title, request_id)
    }


# ==============================================================================
# Application Startup & Shutdown
# ==============================================================================

def handle_shutdown(signum, frame):
    """
    Handles graceful shutdown on SIGINT (Ctrl+C) or SIGTERM.
    
    Args:
        signum: Signal number
        frame: Current stack frame
    """
    print("\n[INFO] Shutting down gracefully...")
    print("[INFO] Pending requests:", len(pending))
    sys.exit(0)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 70)
    print("  Finja Song Request Server v2.2.1")
    print("=" * 70)
    print(f"  Cooldown: {COOLDOWN_SECS}s")
    print(f"  Max pending per user: {MAX_PENDING_PER_USER}")
    print(f"  Force play on accept: {FORCE_NOW_ON_ACCEPT}")
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