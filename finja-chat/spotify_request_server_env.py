"""
======================================================================
                     Finja's Twitch Chat & Overlay
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 2.1.0

----------------------------------------------------------------------

  spotify_request_server_env.py
  Robust moderated Song Request server for Spotify + Finja replies
  - Loads .env automatically (python-dotenv)
  - Handles "no active device" gracefully with Finja hint
  - Optional device preference via SPOTIFY_DEVICE_NAME / SPOTIFY_DEVICE_ID
  - Safe-guards for Spotify API calls
  - Endpoints: /health, /pending, /devices, POST /chat

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import os, time, re
from typing import Dict, Tuple, List, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException

# --- .env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as _e:
    print("[warn] dotenv not loaded:", _e)

SPOTIFY_SCOPES = "user-read-playback-state user-modify-playback-state"
COOLDOWN_SECS = int(os.getenv("SR_COOLDOWN_SECS", "120"))
MODERATED = True
FORCE_NOW_ON_ACCEPT = os.getenv("SR_FORCE_NOW", "false").lower() == "true"
MAX_PENDING_PER_USER = int(os.getenv("SR_MAX_PENDING_PER_USER", "1"))

PREFERRED_DEVICE_NAME = os.getenv("SPOTIFY_DEVICE_NAME", "").strip()  # optional
PREFERRED_DEVICE_ID   = os.getenv("SPOTIFY_DEVICE_ID", "").strip()    # optional

print("[env] SPOTIPY_CLIENT_ID present:", bool(os.getenv("SPOTIPY_CLIENT_ID")))
if os.getenv("SPOTIPY_REDIRECT_URI"):
    print("[env] SPOTIPY_REDIRECT_URI:", os.getenv("SPOTIPY_REDIRECT_URI"))

sp = Spotify(auth_manager=SpotifyOAuth(scope=SPOTIFY_SCOPES, open_browser=False))

app = FastAPI(title="Finja SongRequest v2 (Moderated)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatCommand(BaseModel):
    user: str
    message: str
    is_mod: bool = False
    is_broadcaster: bool = False

cooldown: Dict[str, float] = {}
pending: Dict[int, Dict[str, Any]] = {}
user_pending_count: Dict[str, int] = {}
_next_id = 1

def now() -> float: return time.time()

# ---------------- Finja Replies ----------------
def finja_reply(kind: str, user: str, title: str = "", rid: int | None = None, extra: str = "") -> str:
    if kind == "cooldown":
        return f"💤 Finja: Kurz mal durchatmen, {user}! Alle {COOLDOWN_SECS}s ist ein Wunsch drin."
    if kind == "nohit":
        return f"🤔 Finja: Hm, ich hab nix auf Spotify gefunden… magst du einen direkten Link versuchen, {user}?"
    if kind == "taken":
        return f"🕓 Finja: Wunsch gespeichert (ID {rid}). Ich geb dir Bescheid, wenn’s freigegeben ist, {user}!"
    if kind == "queued":
        return f"💿 Finja: '{title}' kommt in die Queue. Gleich geht’s los! 🎧"
    if kind == "accept_now":
        return f"✅ Finja: '{title}' läuft JETZT – viel Spaß! 🎶"
    if kind == "accept_queue":
        return f"✅ Finja: '{title}' wurde zur Queue hinzugefügt! 💿"
    if kind == "deny":
        return f"⛔ Finja: Der Wunsch wurde abgelehnt. Nicht böse sein, okay? 💙"
    if kind == "no_pending":
        return "📝 Finja: Es gibt gerade keine offenen Wünsche."
    if kind == "too_many":
        return f"🚦 Finja: {user}, du hast schon einen offenen Wunsch. Warte kurz, bis er entschieden ist."
    if kind == "no_device":
        return ("📵 Finja: Ich finde kein aktives Spotify-Gerät. "
                "Öffne Spotify auf deinem PC/Handy und starte kurz einen Song, "
                "dann probier’s nochmal. (Tipp: SPOTIFY_DEVICE_NAME/ID in .env setzen, wenn du willst.)")
    if kind == "error":
        return f"⚠️ Finja: Uff, da ist was schiefgegangen: {extra or 'Unbekannter Fehler'}"
    return "✨ Finja"

# ---------------- Helpers ----------------
def on_cooldown(user: str) -> bool:
    t = cooldown.get(user.lower(), 0)
    return now() - t < COOLDOWN_SECS

def set_cooldown(user: str):
    cooldown[user.lower()] = now()

def can_act(is_mod: bool, is_broadcaster: bool) -> bool:
    return bool(is_broadcaster or is_mod)

def parse_track_uri_or_query(text: str) -> Tuple[str, str]:
    m = re.search(r"(spotify:track:[A-Za-z0-9]+|https?://open\.spotify\.com/track/[A-Za-z0-9]+)", text or "")
    if m:
        uri = m.group(1)
        if uri.startswith("http"):
            tid = uri.rstrip("/").split("/")[-1].split("?")[0]
            return f"spotify:track:{tid}", ""
        return uri, ""
    return "", (text or "").strip()

def search_track_uri(query: str) -> str:
    if not query: return ""
    try:
        res = sp.search(q=query, type="track", limit=5)
        items = []
        if res and isinstance(res, dict):
            items = res.get("tracks", {}).get("items", []) or []
        if items:
            return items[0].get("uri","") or ""
    except Exception as e:
        print(f"[Spotify] Suche-Fehler '{query}': {e}")
    print(f"[Spotify] Keine Treffer für: {query}")
    return ""

def track_title_from_uri(uri: str) -> str:
    try:
        tid = uri.split(":")[-1]
        tr = sp.track(tid)
        if not tr:
            return f"(unbekannter Track {tid})"
        artists = ", ".join((a.get("name","?") for a in tr.get("artists", [])))
        return f"{tr.get('name','?')} – {artists or '?'}"
    except Exception as e:
        print(f"[track_title_from_uri] Fehler: {e}")
        return f"(Fehler bei {uri})"

def list_devices() -> List[Dict[str, Any]]:
    try:
        res: Any = sp.devices()  # kann dict oder None sein
    except Exception as e:
        print("[devices] error:", e)
        return []

    if not isinstance(res, dict):
        # Spotify hat nichts Sinnvolles geliefert
        return []

    raw: Any = res.get("devices")
    if not isinstance(raw, list):
        return []

    out: List[Dict[str, Any]] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        out.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "type": d.get("type"),
            "is_active": d.get("is_active"),
            "volume": d.get("volume_percent"),
        })
    return out

def pick_device_id() -> str:
    devices = list_devices()
    # Optional preference (not required)
    if PREFERRED_DEVICE_ID and any(d["id"] == PREFERRED_DEVICE_ID for d in devices if d.get("id")):
        return PREFERRED_DEVICE_ID
    if PREFERRED_DEVICE_NAME:
        for d in devices:
            if d.get("name","").lower() == PREFERRED_DEVICE_NAME.lower():
                return d.get("id") or ""
    # Active device
    for d in devices:
        if d.get("is_active"):
            return d.get("id") or ""
    # Fallback: first device, if any
    return (devices[0].get("id") if devices else "") or ""

def add_to_queue(uri: str) -> Tuple[bool, str | None]:
    device_id = pick_device_id()
    try:
        if device_id:
            sp.add_to_queue(uri, device_id=device_id)
        else:
            sp.add_to_queue(uri)  # works only if Spotify already has an active device
        return True, None
    except SpotifyException as e:
        msg = str(e)
        if "NO_ACTIVE_DEVICE" in msg or "No active device found" in msg:
            return False, "NO_ACTIVE_DEVICE"
        return False, msg
    except Exception as e:
        return False, str(e)

def force_play_now(uri: str) -> Tuple[bool, str | None]:
    device_id = pick_device_id()
    try:
        sp.start_playback(device_id=device_id or None, uris=[uri])
        return True, None
    except SpotifyException as e:
        msg = str(e)
        if "NO_ACTIVE_DEVICE" in msg or "No active device found" in msg:
            return False, "NO_ACTIVE_DEVICE"
        return False, msg
    except Exception as e:
        return False, str(e)

# ---------------- API ----------------
@app.get("/health")
def health():
    return {"ok": True, "pending": len(pending)}

@app.get("/pending")
def get_pending():
    arr = [
        {"id": rid, "title": p["title"], "user": p["user"], "ts": p["ts"]}
        for rid, p in sorted(pending.items())
    ]
    return {"pending": arr}

@app.get("/devices")
def get_devices():
    return {"devices": list_devices()}

@app.post("/chat")
def handle_chat(cmd: ChatCommand):
    global _next_id
    m = (cmd.message or "").strip()
    lower = m.lower()

    # Moderation
    if lower.startswith("!accept "):
        if not can_act(cmd.is_mod, cmd.is_broadcaster):
            return {"reply": "Nur Mods/Streamer können akzeptieren.", "finja": ""}
        try:
            rid = int(lower.split()[1])
        except:
            return {"reply": "Usage: !accept <id>", "finja": ""}
        if rid not in pending:
            return {"reply": f"ID {rid} nicht gefunden.", "finja": ""}
        req = pending.pop(rid)
        user_pending_count[req["user"].lower()] = max(0, user_pending_count.get(req["user"].lower(), 1) - 1)
        title = req["title"]

        if FORCE_NOW_ON_ACCEPT:
            ok, err = force_play_now(req["uri"])
            if not ok and err == "NO_ACTIVE_DEVICE":
                return {"reply": "", "finja": finja_reply("no_device", req["user"])}
            if not ok:
                return {"reply": f"Fehler beim Starten: {err}", "finja": finja_reply("error", req["user"], extra=str(err))}
            return {"reply": f"ACCEPT: {title} → play now", "finja": finja_reply("accept_now", req["user"], title)}
        else:
            ok, err = add_to_queue(req["uri"])
            if not ok and err == "NO_ACTIVE_DEVICE":
                return {"reply": "", "finja": finja_reply("no_device", req["user"])}
            if not ok:
                return {"reply": f"Fehler beim Queue: {err}", "finja": finja_reply("error", req["user"], extra=str(err))}
            return {"reply": f"ACCEPT: {title} → queued", "finja": finja_reply("accept_queue", req["user"], title)}

    if lower.startswith("!deny "):
        if not can_act(cmd.is_mod, cmd.is_broadcaster):
            return {"reply": "Nur Mods/Streamer können ablehnen.", "finja": ""}
        try:
            rid = int(lower.split()[1])
        except:
            return {"reply": "Usage: !deny <id>", "finja": ""}
        if rid not in pending:
            return {"reply": f"ID {rid} nicht gefunden.", "finja": ""}
        req = pending.pop(rid)
        user_pending_count[req["user"].lower()] = max(0, user_pending_count.get(req["user"].lower(), 1) - 1)
        return {"reply": f"DENY: {req['title']}", "finja": finja_reply("deny", req["user"], req["title"])}

    if lower in ("!rq", "!requests", "!pending"):
        if not can_act(cmd.is_mod, cmd.is_broadcaster):
            return {"reply": "Nur Mods/Streamer.", "finja": ""}
        if not pending:
            return {"reply": "Keine offenen Requests.", "finja": finja_reply("no_pending", cmd.user)}
        lst = []
        for rid, p in sorted(pending.items()):
            title = p.get("title","?")
            user  = p.get("user","?")
            lst.append(f"{rid}: {title} — {user}")
        return {"reply": "Offene Requests | " + " | ".join(lst), "finja": ""}

    # Viewer
    if lower.startswith(("!sr ", "!songrequest ", "!queue ", "!q ")):
        if on_cooldown(cmd.user):
            return {"reply": "", "finja": finja_reply("cooldown", cmd.user)}
        if user_pending_count.get(cmd.user.lower(), 0) >= MAX_PENDING_PER_USER:
            return {"reply": "", "finja": finja_reply("too_many", cmd.user)}

        query = m.split(" ", 1)[1].strip() if " " in m else ""
        uri, search = parse_track_uri_or_query(query)
        if not uri:
            uri = search_track_uri(search)
            if not uri:
                return {"reply": "", "finja": finja_reply("nohit", cmd.user)}

        title = track_title_from_uri(uri)
        set_cooldown(cmd.user)

        rid = _next_id; _next_id += 1
        pending[rid] = {"user": cmd.user, "uri": uri, "title": title, "ts": now()}
        user_pending_count[cmd.user.lower()] = user_pending_count.get(cmd.user.lower(), 0) + 1
        return {"reply": f"Wunsch gespeichert (ID {rid}): {title}", "finja": finja_reply("taken", cmd.user, title, rid)}

    return {"reply": "", "finja": ""}