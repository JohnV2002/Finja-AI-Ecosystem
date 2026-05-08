"""
YourAI AI - Spotify Integration
================================
Holt Musik-Kontext von YourAIs Musik-Docker-API.
Liefert Prompt-Context damit YourAI weiß was Creator gerade hört.

API: https://youraireact.your-domain.example.com/get/YourAI
Returns: {"reaction","genres","title","artist","context","updated_at"}

Usage:
    from spotify import get_music_context
    context_str = get_music_context()  # Returns str or "" if nothing playing
"""

import time
import sys, os
import requests
from datetime import datetime, timezone
from typing import Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAINetworkError, YourAIWebFetchError
from config import SPOTIFY_API_URL, SPOTIFY_STALE_MINUTES

# ==========================================
# STATE
# ==========================================

_last_data: Optional[Dict] = None
_last_fetch: float = 0.0
_last_title: Optional[str] = None
_last_title_since: float = 0.0

FETCH_COOLDOWN = 10  # Nicht öfter als alle 10 Sekunden fetchen

# Listening-Phase Texte (aus config_min.json)
LISTENING_TEXTS = {
    "listening…", "deep listening…", "thinking more…", "listening more…",
    "vibing…", "analyzing…", "still listening…", "getting into it…",
    "one more sec…", "soaking it in…", "grooving…", "tuning in…",
    "feeling the track…", "let it sink in…", "dialing in…", "leaning in…",
    "catching details…", "head-bobbing…", "calibrating…", "locking in…",
    "riding the wave…", "breathing it in…", "counting beats…",
    "letting it build…", "finding groove…", "ear-candy check…",
    "savoring…", "fine-tuning…", "on the hook…", "scanning layers…",
    "zeroing in…", "still vibing…", "melody check…", "bass check…",
}


# ==========================================
# FETCH
# ==========================================

def _fetch_music_data() -> Optional[Dict]:
    """Fetcht aktuelle Musik-Daten von der Docker-API."""
    global _last_data, _last_fetch

    now = time.time()
    if now - _last_fetch < FETCH_COOLDOWN and _last_data is not None:
        return _last_data

    try:
        resp = requests.get(SPOTIFY_API_URL, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            _last_data = data
            _last_fetch = now
            return data
        else:
            err = YourAIWebFetchError(url=SPOTIFY_API_URL, status_code=resp.status_code, module="spotify_api")
            log_exception("SPOTIFY", err)
            return _last_data
    except requests.Timeout as e:
        err = YourAINetworkError(host=SPOTIFY_API_URL, cause=e, module="spotify_api")
        log_exception("SPOTIFY", err)
        return _last_data
    except requests.exceptions.RequestException as e:
        err = YourAINetworkError(host=SPOTIFY_API_URL, cause=e, module="spotify_api")
        log_exception("SPOTIFY", err)
        return _last_data


def _is_stale(updated_at: str) -> bool:
    """Prüft ob die Daten zu alt sind (Song nicht mehr aktiv)."""
    try:
        dt = datetime.fromisoformat(updated_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        return age_minutes > SPOTIFY_STALE_MINUTES
    except (ValueError, TypeError) as e:
        log("SPOTIFY", f"⚠️ Invalid date format in updated_at: {e}", Fore.YELLOW)
        return True


def _is_listening(reaction: str) -> bool:
    """Prüft ob YourAI noch in der Listening-Phase ist."""
    clean = (reaction or "").strip().lower()
    return clean in LISTENING_TEXTS or clean.rstrip("…").rstrip(".") + "…" in LISTENING_TEXTS


# ==========================================
# PUBLIC API
# ==========================================

def get_music_context() -> str:
    """
    Holt den aktuellen Musik-Kontext für YourAIs Prompt.

    Returns:
        str: Musik-Kontext als Text, oder "" wenn nichts läuft.
    """
    global _last_title, _last_title_since

    data = _fetch_music_data()
    if not data:
        return ""

    title = data.get("title", "").strip()
    artist = data.get("artist", "").strip()
    reaction = data.get("reaction", "").strip()
    genres = data.get("genres", "").strip()
    updated_at = data.get("updated_at", "")

    # Nichts da?
    if not title and not artist:
        return ""

    # Zu alt? (API nullt sich nicht, zeigt immer letzten Song)
    if _is_stale(updated_at):
        return ""

    # Gleiches Lied seit über 6 Minuten? → stale
    now = time.time()
    current_key = f"{title} - {artist}"
    if current_key != _last_title:
        _last_title = current_key
        _last_title_since = now
    elif now - _last_title_since > SPOTIFY_STALE_MINUTES * 60:
        return ""

    # Listening-Phase? → YourAI hört noch zu
    if _is_listening(reaction):
        parts = ["## SPOTIFY CONTEXT"]
        parts.append(f"Creator is currently listening to: '{title}' by {artist}.")
        if genres and genres != "Unknown":
            parts.append(f"Genres: {genres}.")
        parts.append("You're still listening to it and forming your opinion...")
        parts.append("Feel free to mention you're vibing to the song, but don't give a final verdict yet!")
        return "\n".join(parts)

    # Finale Reaktion da!
    parts = ["## SPOTIFY CONTEXT"]
    parts.append(f"Creator is currently listening to: '{title}' by {artist}.")
    if genres and genres != "Unknown":
        parts.append(f"Genres: {genres}.")
    parts.append(f"Your music brain's reaction: \"{reaction}\"")
    parts.append("Use this reaction as inspiration - rephrase it naturally in YOUR voice!")
    parts.append("Don't just copy the reaction text, make it your own!")

    return "\n".join(parts)
