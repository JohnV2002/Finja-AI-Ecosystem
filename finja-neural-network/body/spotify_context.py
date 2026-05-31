"""
Spotify Prompt Context Helpers
==============================
Pure utility helpers for converting YourAI music API metadata into prompt context payloads.

Main Responsibilities:
- Validate timestamp freshness.
- Detect active song listening phases.
- Retrieve and map Music Brain song features.
- Format current Spotify playback context for the LLM.

Side Effects:
- None.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from display import log, log_exception, Fore
from exceptions import YourAIWebParseError, YourAIUnexpectedError
from config import SPOTIFY_STALE_MINUTES


LISTENING_TEXTS = {
    "listening...", "deep listening...", "thinking more...", "listening more...",
    "vibing...", "analyzing...", "still listening...", "getting into it...",
    "one more sec...", "soaking it in...", "grooving...", "tuning in...",
    "feeling the track...", "let it sink in...", "dialing in...", "leaning in...",
    "catching details...", "head-bobbing...", "calibrating...", "locking in...",
    "riding the wave...", "breathing it in...", "counting beats...",
    "letting it build...", "finding groove...", "ear-candy check...",
    "savoring...", "fine-tuning...", "on the hook...", "scanning layers...",
    "zeroing in...", "still vibing...", "melody check...", "bass check...",
}


def is_stale(updated_at: str, stale_minutes: int) -> bool:
    """
    Determines if the music API timestamp has exceeded the staleness duration.

    Args:
        updated_at (str): The ISO-formatted update timestamp.
        stale_minutes (int): Minutes threshold before data is considered stale.

    Returns:
        bool: True if the timestamp is older than stale_minutes or invalid, False otherwise.
    """
    try:
        dt = datetime.fromisoformat(updated_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        return age_minutes > stale_minutes
    except (ValueError, TypeError) as e:
        err = YourAIWebParseError(
            "Invalid Spotify updated_at timestamp",
            updated_at=updated_at,
            cause=e,
            module="spotify_context",
        )
        log_exception("SPOTIFY", err)
        return True


def is_listening(reaction: str) -> bool:
    """
    Checks if the current music brain reaction represents an active listening phase.

    Args:
        reaction (str): The current reaction message.

    Returns:
        bool: True if the reaction indicates active listening, False otherwise.
    """
    clean = (reaction or "").strip().lower()
    return clean in LISTENING_TEXTS or clean.rstrip(".") + "..." in LISTENING_TEXTS


# ==========================================
# MUSIC EXPERT DATA HELPERS
# ==========================================
# Read music metadata from Music Brain and Spotify without sending control commands.
# Used by brain.py expert_node (music domain).
# ==========================================

def get_music_brain_song_features(title: Optional[str], artist: Optional[str]) -> Dict[str, Any]:
    """
    Queries Music Brain for song features for explicit title/artist lookups.

    Args:
        title (Optional[str]): The song title.
        artist (Optional[str]): The song artist.

    Returns:
        Dict[str, Any]: A dictionary containing source, lookup, and features, or an empty dict if not found.
    """
    if not title or not artist:
        return {}
    try:
        from tools.spotify_control import _get_docker_song_features
        features = _get_docker_song_features(title, artist)
        if not features:
            return {}
        return {
            "source": "music_brain",
            "lookup": "song_features",
            "title": title,
            "artist": artist,
            "features": features,
        }
    except Exception as exc:
        err = YourAIUnexpectedError(cause=exc, module="spotify_context_song_features")
        log_exception("SPOTIFY", err)
        return {}


def _fetch_song_features(title: str, artist: str) -> Optional[dict]:
    """
    Fetches Music Brain song features for a specific title and artist pair.

    Args:
        title (str): The song title to look up.
        artist (str): The song artist to look up.

    Returns:
        Optional[dict]: The fetched feature dictionary, or None if lookup fails.
    """
    try:
        from tools.spotify_control import _get_docker_song_features
        return _get_docker_song_features(title, artist)
    except Exception as exc:
        err = YourAIUnexpectedError(cause=exc, module="spotify_context_fetch_features")
        log_exception("SPOTIFY", err)
        return None


def _extract_artists(item: dict) -> list:
    """
    Extracts artist names from a Spotify item payload.

    Args:
        item (dict): The Spotify item payload.

    Returns:
        list: Artist names in the order returned by Spotify.
    """
    artists = []
    for a in item.get("artists", []):
        if isinstance(a, dict):
            name = a.get("name")
            if name:
                artists.append(name)
    return artists


def _extract_playback_details(playback: dict, item: dict) -> dict:
    """
    Builds normalized track metadata from Spotify playback and item payloads.

    Args:
        playback (dict): The current playback payload.
        item (dict): The track item payload.

    Returns:
        dict: Normalized Spotify track metadata, or an empty dictionary if no track is present.
    """
    artists = _extract_artists(item)
    title = item.get("name") or ""
    if not title and not artists:
        return {}

    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    external_urls = item.get("external_urls") if isinstance(item.get("external_urls"), dict) else {}

    return {
        "source": "spotify",
        "title": title or None,
        "artist": artists[0] if artists else None,
        "artists": artists,
        "album": album.get("name") if album else None,
        "release_date": album.get("release_date") if album else None,
        "duration_ms": item.get("duration_ms"),
        "track_id": item.get("id"),
        "uri": item.get("uri"),
        "external_url": external_urls.get("spotify"),
        "is_playing": playback.get("is_playing"),
        "progress_ms": playback.get("progress_ms"),
    }


def _build_expert_data_result(title: str, artist: str, data: dict) -> dict:
    """
    Builds a Music Brain expert metadata result with optional song features.

    Args:
        title (str): The current track title.
        artist (str): The current track artist.
        data (dict): The Music Brain metadata payload.

    Returns:
        dict: Expert metadata result for the music domain.
    """
    result = {
        "source": "music_brain",
        "title": title or None,
        "artist": artist or None,
        "genres": data.get("genres") or None,
        "reaction": data.get("reaction") or None,
        "context": data.get("context") or None,
        "updated_at": data.get("updated_at") or None,
    }
    features = _fetch_song_features(title, artist) if (title and artist) else None
    if features:
        result["features"] = features
    return result


def get_music_brain_expert_data() -> Dict[str, Any]:
    """
    Reads the current Music Brain metadata without sending Spotify control commands.

    Returns:
        Dict[str, Any]: A dictionary containing title, artist, genres, and features, or an empty dict if not available/stale.
    """
    try:
        import spotify as _music_context
        data = _music_context._fetch_music_data()  # type: ignore[attr-defined]
        if not isinstance(data, dict):
            return {}

        title = (data.get("title") or "").strip()
        artist = (data.get("artist") or "").strip()
        if not title and not artist:
            return {}

        updated_at = data.get("updated_at") or ""
        if updated_at and is_stale(updated_at, SPOTIFY_STALE_MINUTES):
            return {}

        return _build_expert_data_result(title, artist, data)
    except Exception as exc:
        err = YourAIUnexpectedError(cause=exc, module="spotify_context_brain_data")
        log_exception("SPOTIFY", err)
        return {}


def get_spotify_current_track_data() -> Dict[str, Any]:
    """
    Reads Spotify playback metadata in a read-only fashion without sending control commands.

    Returns:
        Dict[str, Any]: A dictionary containing track metadata, or an empty dict if not available.
    """
    try:
        from tools.spotify_control import _get_spotify
        ctrl = _get_spotify()
        playback = ctrl.api.get_current_playback()
        if not isinstance(playback, dict) or not playback:
            return {}

        item = playback.get("item")
        if not isinstance(item, dict):
            item = playback

        if not isinstance(item, dict) or not item:
            return {}

        return _extract_playback_details(playback, item)
    except Exception as exc:
        err = YourAIUnexpectedError(cause=exc, module="spotify_context_current_track")
        log_exception("SPOTIFY", err)
        return {}


def _extract_mood(tags: Any) -> list[str]:
    """
    Extracts mood-like tags while filtering generic playlist metadata.

    Args:
        tags (Any): Raw tag list from Music Brain features.

    Returns:
        list[str]: Up to five filtered mood or genre tags.
    """
    if not isinstance(tags, list):
        return []
    return [
        tag for tag in tags
        if isinstance(tag, str) and tag.lower() not in {"2020s", "playlist", "mix"}
    ][:5]


def _extract_camelot_key(key: Any) -> Optional[str]:
    """
    Validates and returns a Camelot key string.

    Args:
        key (Any): Raw musical key value.

    Returns:
        Optional[str]: The validated Camelot key, or None if invalid.
    """
    if isinstance(key, str) and re.match(r"^\d{1,2}[AB]$", key, flags=re.IGNORECASE):
        return key
    return None


def _extract_missing_fields(features: dict) -> list[str]:
    """
    Identifies expected Music Brain feature fields that are missing.

    Args:
        features (dict): The feature dictionary to inspect.

    Returns:
        list[str]: Names of missing fields.
    """
    check_fields = ["release_date", "energy", "danceability", "valence", "acousticness"]
    return [field for field in check_fields if features.get(field) is None]


def _extract_facts(title: Optional[str], artist: Optional[str]) -> list[str]:
    """
    Builds human-readable facts for a Music Brain match.

    Args:
        title (Optional[str]): The matched song title.
        artist (Optional[str]): The matched song artist.

    Returns:
        list[str]: Fact strings for expert output.
    """
    if title or artist:
        return [f"Music Brain match: {title} by {artist}"]
    return ["Music Brain match"]


def music_fact_from_brain(data: Dict[str, Any]) -> str:
    """
    Converts Music Brain song features into the YourAI-compatible Expert JSON format.

    Used directly as an expert response if Music Brain knows the track.

    Args:
        data (Dict[str, Any]): The Music Brain data dictionary.

    Returns:
        str: A JSON string containing the formatted expert output.
    """
    try:
        raw_features = data.get("features")
        features = raw_features if isinstance(raw_features, dict) else {}
        title = features.get("title") or data.get("title")
        artist = features.get("artist") or data.get("artist")
        raw_tags = features.get("tags")
        tags = raw_tags if isinstance(raw_tags, list) else []
        key = features.get("key")
        mood = _extract_mood(tags)
        album = features.get("album")

        fact = {
            "target": f"{title or ''} - {artist or ''}".strip(" -"),
            "type": "song",
            "artist": artist,
            "title": title,
            "album": album,
            "release_date": features.get("release_date"),
            "genres": tags,
            "bpm": features.get("bpm"),
            "key": key,
            "camelot_key": _extract_camelot_key(key),
            "energy": features.get("energy"),
            "danceability": features.get("danceability"),
            "valence": features.get("valence"),
            "acousticness": features.get("acousticness"),
            "mood": mood,
            "facts": _extract_facts(title, artist),
            "analysis": ["Use YourAI voice to explain the metadata naturally."],
            "missing": _extract_missing_fields(features),
            "source_quality": "music_brain",
        }
        return json.dumps(fact, ensure_ascii=False)
    except Exception as exc:
        err = YourAIUnexpectedError(cause=exc, module="spotify_context_music_fact")
        log_exception("SPOTIFY", err)
        fallback = {
            "target": "Unknown",
            "type": "song",
            "source_quality": "unknown",
            "facts": ["Failed to extract facts from Music Brain data"],
        }
        return json.dumps(fallback, ensure_ascii=False)



def format_music_context(data: dict, stale_minutes: int, last_title: Optional[str], last_title_since: float, now: float) -> tuple[str, Optional[str], float]:
    """
    Builds the Spotify prompt context block from music API metadata.

    Args:
        data (dict): The fetched music metadata.
        stale_minutes (int): Minutes threshold before data is considered stale.
        last_title (Optional[str]): Cached title of the last track.
        last_title_since (float): Timestamp when the last track started playing.
        now (float): Current timestamp.

    Returns:
        tuple[str, Optional[str], float]: A tuple of (formatted_context, updated_last_title, updated_last_title_since).
    """
    title = data.get("title", "").strip()
    artist = data.get("artist", "").strip()
    reaction = data.get("reaction", "").strip()
    genres = data.get("genres", "").strip()
    updated_at = data.get("updated_at", "")

    if not title and not artist:
        return "", last_title, last_title_since

    if is_stale(updated_at, stale_minutes):
        return "", last_title, last_title_since

    current_key = f"{title} - {artist}"
    if current_key != last_title:
        last_title = current_key
        last_title_since = now
    elif now - last_title_since > stale_minutes * 60:
        return "", last_title, last_title_since

    parts = ["## SPOTIFY CONTEXT"]
    parts.append(f"Creator is currently listening to: '{title}' by {artist}.")
    if genres and genres != "Unknown":
        parts.append(f"Genres: {genres}.")

    if is_listening(reaction):
        parts.append("You're still listening to it and forming your opinion...")
        parts.append("Feel free to mention you're vibing to the song, but don't give a final verdict yet!")
    else:
        parts.append(f"Your music brain's reaction: \"{reaction}\"")
        parts.append("Use this reaction as inspiration - rephrase it naturally in YOUR voice!")
        parts.append("Don't just copy the reaction text, make it your own!")

    return "\n".join(parts), last_title, last_title_since
