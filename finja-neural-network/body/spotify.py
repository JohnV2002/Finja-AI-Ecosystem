"""
Body Spotify - Music Integration
================================
Integrates with the Spotify web API helper to fetch information about the currently 
playing music track and format it for prompt inclusion.

Main Responsibilities:
- Fetch current track data with local rate limit throttling.
- Delegate caching and formatting to the spotify_context module.

Side Effects:
- Performs external HTTP network requests (Spotify API helper URL).
"""

import os
import sys
import time
from typing import Dict, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception
from exceptions import YourAINetworkError, YourAIWebFetchError
from config import SPOTIFY_API_URL, SPOTIFY_STALE_MINUTES
from body.spotify_context import format_music_context

_last_data: Optional[Dict] = None
_last_fetch: float = 0.0
_last_title: Optional[str] = None
_last_title_since: float = 0.0

FETCH_COOLDOWN = 10


def _fetch_music_data() -> Optional[Dict]:
    """
    Fetches currently playing track metadata from the Spotify API helper endpoint.

    Enforces a rate-limiting cooldown check (FETCH_COOLDOWN) to prevent spamming the endpoint.

    Returns:
        Optional[Dict]: The fetched music metadata dictionary, or the cached data on failure/cooldown.
    """
    global _last_data, _last_fetch

    now = time.time()
    if now - _last_fetch < FETCH_COOLDOWN and _last_data is not None:
        return _last_data

    try:
        response = requests.get(SPOTIFY_API_URL, timeout=5)
        if response.status_code == 200:
            _last_data = response.json()
            _last_fetch = now
            return _last_data

        err = YourAIWebFetchError(url=SPOTIFY_API_URL, status_code=response.status_code, module="spotify_api")
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


def get_music_context() -> str:
    """
    Retrieves and builds the formatted Spotify prompt context.

    Returns:
        str: The formatted Spotify prompt block, or an empty string if inactive or unavailable.
    """
    global _last_title, _last_title_since

    data = _fetch_music_data()
    if not data:
        return ""

    context, _last_title, _last_title_since = format_music_context(
        data,
        stale_minutes=SPOTIFY_STALE_MINUTES,
        last_title=_last_title,
        last_title_since=_last_title_since,
        now=time.time(),
    )
    return context
