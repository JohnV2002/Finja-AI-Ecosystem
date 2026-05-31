"""
YourAI AI - Spotify Control
============================
Playlist/queue control via the Spotify Web API.
ADMIN ONLY (Admin)!

Features:
    - Filter a playlist by artist/genre & play it
    - Sort the queue by BPM (slow->fast, fast->slow)
    - Smart shuffle (real shuffle, not Spotify's fake one)
    - Skip, pause, resume
    - Show the current queue

Usage:
    from tools.spotify_control import SpotifyControl
    spotify = SpotifyControl()
    result = spotify.shuffle_playlist("Lieblingssongs", filter_artist="Execute")
"""

import os
import sys
import time
import random
import base64
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode

# The tools package needs access to parent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN
from exceptions import YourAINoPrivilegeError, YourAIToolExecutionError
from helpers.text_parser import (
    extract_spotify_artist_filter,
    extract_spotify_playlist_name,
    extract_spotify_volume,
)

# ==========================================
# SPOTIFY AUTH
# ==========================================

class SpotifyAuth:
    """Handles Spotify OAuth token refresh."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self):
        """Initialize the (empty) cached access token state."""
        self._access_token: Optional[str] = None
        self._token_expires: float = 0.0

    def get_token(self) -> Optional[str]:
        """Fetch or refresh the access token.

        Returns:
            Optional[str]: A valid access token.

        Raises:
            ValueError: When Spotify credentials are missing in .env.
            ConnectionError: When the token refresh request fails.
        """
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET or not SPOTIFY_REFRESH_TOKEN:
            raise ValueError("Spotify credentials not configured in .env!")

        auth_header = base64.b64encode(
            f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()

        resp = requests.post(self.TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": SPOTIFY_REFRESH_TOKEN,
        }, headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        }, timeout=10)

        if resp.status_code != 200:
            raise ConnectionError(f"Spotify token refresh failed: {resp.status_code} - {resp.text}")

        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        log("SPOTIFY", "🔑 Token refreshed ✅", Fore.GREEN)
        return self._access_token


# ==========================================
# SPOTIFY API CLIENT
# ==========================================

class SpotifyAPI:
    """Low-level Spotify Web API wrapper."""

    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self):
        """Create the API client with its own auth handler."""
        self.auth = SpotifyAuth()

    def _headers(self) -> Dict:
        """Return the bearer-token authorization headers."""
        return {"Authorization": f"Bearer {self.auth.get_token()}"}

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET an endpoint, refreshing the token once on a 401."""
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
        if resp.status_code == 401:
            # Token expired, refresh and retry
            self.auth._access_token = None
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    def _put(self, endpoint: str, json_data: Optional[Dict] = None) -> bool:
        """PUT to an endpoint, refreshing the token once on a 401."""
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.put(url, headers=self._headers(), json=json_data, timeout=10)
        if resp.status_code == 401:
            self.auth._access_token = None
            resp = requests.put(url, headers=self._headers(), json=json_data, timeout=10)
        return resp.status_code in (200, 204)

    def _post(self, endpoint: str, json_data: Optional[Dict] = None) -> bool:
        """POST to an endpoint, refreshing the token once on a 401."""
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.post(url, headers=self._headers(), json=json_data, timeout=10)
        if resp.status_code == 401:
            self.auth._access_token = None
            resp = requests.post(url, headers=self._headers(), json=json_data, timeout=10)
        return resp.status_code in (200, 201, 204)

    # --- Playback ---

    def get_current_playback(self) -> Optional[Dict]:
        """What is currently playing?"""
        try:
            return self._get("me/player")
        except Exception as e:
            err = YourAIToolExecutionError("Spotify current playback failed", tool_name="spotify_current_playback", cause=e)
            log_exception("SPOTIFY", err)
            return None

    def play(self, uris: Optional[List[str]] = None, context_uri: Optional[str] = None,
             offset: Optional[Dict] = None) -> bool:
        """Start playback with specific tracks or a context."""
        body = {}
        if uris:
            body["uris"] = uris
        if context_uri:
            body["context_uri"] = context_uri
        if offset:
            body["offset"] = offset
        log("SPOTIFY", f"▶️ play() body: uris={len(uris) if uris else 0} tracks, context={context_uri}", Fore.CYAN)
        url = f"{self.BASE_URL}/me/player/play"
        resp = requests.put(url, headers=self._headers(), json=body if body else None, timeout=10)
        log("SPOTIFY", f"▶️ play() response: {resp.status_code} {resp.text[:200] if resp.text else 'empty'}", Fore.CYAN)
        if resp.status_code == 401:
            self.auth._access_token = None
            resp = requests.put(url, headers=self._headers(), json=body if body else None, timeout=10)
        return resp.status_code in (200, 204)

    def pause(self) -> bool:
        """Pause playback."""
        return self._put("me/player/pause")

    def skip_next(self) -> bool:
        """Skip to the next track."""
        return self._post("me/player/next")

    def skip_previous(self) -> bool:
        """Skip to the previous track."""
        return self._post("me/player/previous")

    def set_volume(self, volume_percent: int) -> bool:
        """Set the playback volume (0-100)."""
        url = f"{self.BASE_URL}/me/player/volume?volume_percent={volume_percent}"
        resp = requests.put(url, headers=self._headers(), timeout=10)
        return resp.status_code in (200, 204)

    def add_to_queue(self, uri: str) -> bool:
        """Add a track URI to the playback queue."""
        url = f"{self.BASE_URL}/me/player/queue?uri={uri}"
        resp = requests.post(url, headers=self._headers(), timeout=10)
        return resp.status_code in (200, 204)

    def set_shuffle(self, state: bool) -> bool:
        """Turn shuffle on/off."""
        url = f"{self.BASE_URL}/me/player/shuffle?state={'true' if state else 'false'}"
        resp = requests.put(url, headers=self._headers(), timeout=10)
        log("SPOTIFY", f"🔀 Shuffle {'ON' if state else 'OFF'}: {resp.status_code}", Fore.CYAN)
        return resp.status_code in (200, 204)

    def get_queue(self) -> Optional[Dict]:
        """Fetch the current queue."""
        try:
            return self._get("me/player/queue")
        except Exception as e:
            err = YourAIToolExecutionError("Spotify queue fetch failed", tool_name="spotify_get_queue", cause=e)
            log_exception("SPOTIFY", err)
            return None

    # --- Playlists ---

    def get_my_playlists(self, limit: int = 50) -> List[Dict]:
        """All of the user's playlists."""
        playlists = []
        offset = 0
        while True:
            data = self._get("me/playlists", {"limit": min(limit, 50), "offset": offset})
            items = data.get("items", [])
            if not items:
                break
            playlists.extend(items)
            if not data.get("next"):
                break
            offset += len(items)
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """All tracks of a playlist."""
        tracks = []
        offset = 0
        while True:
            data = self._get(f"playlists/{playlist_id}/tracks", {
                "limit": 100, "offset": offset,
                "fields": "items(track(uri,name,artists,album,duration_ms,id)),next"
            })
            items = data.get("items", [])
            if not items:
                break
            tracks.extend(items)
            if not data.get("next"):
                break
            offset += len(items)
        return tracks

    # Aliases for Spotify's "Liked Songs" (special, not in /me/playlists!)
    LIKED_SONGS_ALIASES = [
        "lieblingssongs", "liked songs", "liked", "lieblings", "favorites",
        "favourites", "meine songs", "my songs", "gespeicherte songs", "saved songs"
    ]

    def _is_liked_songs(self, name: str) -> bool:
        """Check whether the name refers to Spotify's 'Liked Songs'."""
        name_lower = name.lower().strip()
        return any(alias in name_lower for alias in self.LIKED_SONGS_ALIASES)

    def get_liked_songs(self, limit: int = 500) -> List[Dict]:
        """Fetch the 'Liked Songs' via /me/tracks."""
        tracks = []
        offset = 0
        while len(tracks) < limit:
            batch_size = min(50, limit - len(tracks))
            data = self._get("me/tracks", {"limit": batch_size, "offset": offset})
            items = data.get("items", [])
            if not items:
                break
            tracks.extend(items)
            if not data.get("next"):
                break
            offset += len(items)
        log("SPOTIFY", f"❤️ Liked Songs: {len(tracks)} tracks loaded", Fore.CYAN)
        return tracks

    def find_playlist(self, name: str) -> Optional[Dict]:
        """Find a playlist by name (fuzzy). Also recognizes 'Liked Songs'."""
        # Strip quotes that LLMs love to add
        name = name.strip().strip('"').strip("'").strip()
        name_lower = name.lower().strip()

        # Special case: "Liked Songs" / "Lieblingssongs"
        if self._is_liked_songs(name):
            log("SPOTIFY", f"🔎 ❤️ '{name}' → Spotify Liked Songs (special collection)", Fore.GREEN)
            return {"name": "Lieblingssongs", "id": "__liked__", "_is_liked": True}

        playlists = self.get_my_playlists()

        log("SPOTIFY", f"🔎 Searching for playlist '{name}' in {len(playlists)} playlists", Fore.CYAN)
        log("SPOTIFY", f"🔎 Available: {[pl['name'] for pl in playlists[:15]]}", Fore.CYAN)

        # Exact match first
        for pl in playlists:
            if pl["name"].lower().strip() == name_lower:
                log("SPOTIFY", f"🔎 ✅ Exact match: '{pl['name']}'", Fore.GREEN)
                return pl

        # Contains match
        for pl in playlists:
            if name_lower in pl["name"].lower():
                log("SPOTIFY", f"🔎 ✅ Contains match: '{pl['name']}'", Fore.GREEN)
                return pl

        log("SPOTIFY", f"🔎 ❌ No match for '{name}'", Fore.RED)
        return None

    # --- Audio Features ---

    def get_audio_features(self, track_ids: List[str]) -> List[Optional[Dict]]:
        """Audio features (BPM, key, energy, etc.) for multiple tracks."""
        all_features = []
        # Max 100 per request
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i:i+100]
            ids_str = ",".join(batch)
            data = self._get("audio-features", {"ids": ids_str})
            all_features.extend(data.get("audio_features", []))
        return all_features


# ==========================================
# SPOTIFY CONTROL (High-Level)
# ==========================================

# ==========================================
# DOCKER MUSIC BRAIN BRIDGE
# ==========================================

# Docker Music Brain URL (Cloudflare Tunnel)
MUSIC_BRAIN_URL = "https://youraireact.your-domain.example.com"

def _get_docker_songs(artist: Optional[str] = None, genre: Optional[str] = None) -> Optional[List[Dict]]:
    """
    Fetch enriched song data from the Docker Music Brain.
    Returns None when Docker is unreachable -> fallback to the Spotify API.
    """
    try:
        params: Dict[str, Any] = {"limit": 500}
        if artist:
            params["artist"] = artist
        if genre:
            params["genre"] = genre

        resp = requests.get(f"{MUSIC_BRAIN_URL}/get/songs", params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            songs = data.get("songs", [])
            has_enrichment = data.get("has_enrichment", False)
            log("SPOTIFY", f"🧠 Docker Brain: {len(songs)} songs (enriched: {has_enrichment})", Fore.CYAN)
            return songs
        else:
            log("SPOTIFY", f"⚠️ Docker Brain returned {resp.status_code}", Fore.YELLOW)
            return None
    except Exception as e:
        err = YourAIToolExecutionError("Docker music brain songs failed", tool_name="spotify_docker_songs", cause=e)
        log_exception("SPOTIFY", err)
        log("SPOTIFY", f"⚠️ Docker Brain not reachable: {e} → Spotify API fallback", Fore.YELLOW)
        return None


def _get_docker_song_features(title: str, artist: str) -> Optional[Dict]:
    """Fetch features for a single song from Docker."""
    try:
        resp = requests.get(f"{MUSIC_BRAIN_URL}/get/song_features",
                           params={"title": title, "artist": artist}, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        err = YourAIToolExecutionError("Docker music brain song features failed", tool_name="spotify_docker_song_features", cause=e)
        log_exception("SPOTIFY", err)
        return None


class SpotifyControl:
    """
    High-level Spotify control for YourAI.
    Admin only!
    Uses the Docker Music Brain for enriched data, with the Spotify API as fallback.
    """

    def __init__(self):
        """Create the high-level controller with its API client."""
        self.api = SpotifyAPI()

    def _get_tracks(self, playlist: Dict) -> List[Dict]:
        """Fetch tracks - automatically Liked Songs or a normal playlist."""
        if playlist.get("_is_liked"):
            return self.api.get_liked_songs()
        return self.api.get_playlist_tracks(playlist["id"])

    def shuffle_playlist(self, playlist_name: str,
                         filter_artist: Optional[str] = None,
                         filter_genre: Optional[str] = None) -> Dict[str, Any]:
        """
        Real shuffle of a playlist (not Spotify's fake shuffle).
        Optionally filter by artist or genre.
        """
        # Find the playlist
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' not found"}

        # Load tracks
        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("uri")]

        if not tracks:
            return {"success": False, "error": f"Playlist '{playlist_name}' is empty"}

        # Filter by artist
        if filter_artist:
            filter_lower = filter_artist.lower()
            tracks = [t for t in tracks if any(
                filter_lower in a["name"].lower() for a in t.get("artists", [])
            )]
            if not tracks:
                return {"success": False, "error": f"No track by '{filter_artist}' in '{playlist_name}'"}

        # Real shuffle
        random.shuffle(tracks)

        # Max 100 tracks for the queue (Spotify limit)
        play_tracks = tracks[:100]
        uris = [t["uri"] for t in play_tracks]

        log("SPOTIFY", f"🎲 Shuffle: {len(tracks)} tracks found, playing {len(play_tracks)}", Fore.CYAN)
        log("SPOTIFY", f"🎲 Filter: artist='{filter_artist}', genre='{filter_genre}'", Fore.CYAN)
        log("SPOTIFY", f"🎲 First 3 URIs: {uris[:3]}", Fore.CYAN)
        log("SPOTIFY", f"🎲 First 3 tracks: {[t['name'] for t in play_tracks[:3]]}", Fore.CYAN)

        # Play
        success = self.api.play(uris=uris)
        log("SPOTIFY", f"🎲 play() returned: {success}", Fore.CYAN)

        track_names = [f"{t['name']} - {t['artists'][0]['name']}" for t in play_tracks[:5]]
        return {
            "success": success,
            "playlist": playlist["name"],
            "total_tracks": len(tracks),
            "playing": len(play_tracks),
            "filter": filter_artist or filter_genre or "none",
            "first_tracks": track_names,
            "message": f"🎵 Shuffled '{playlist['name']}' ({len(play_tracks)} tracks). First up: {track_names[0]}"
        }

    def _enrich_tracks_with_features(self, tracks: List[Dict], sort_key: str) -> List[Dict]:
        """
        Enrich tracks with BPM/energy/etc.
        Ask the Docker Music Brain first, then the Spotify API as fallback.
        """
        enriched = []

        # STEP 1: try the Docker Music Brain
        docker_hits = 0
        for track in tracks:
            title = track.get("name", "")
            artist = track.get("artists", [{}])[0].get("name", "")

            docker_data = _get_docker_song_features(title, artist)
            if docker_data and docker_data.get(sort_key) is not None:
                enriched.append({
                    "track": track,
                    "bpm": docker_data.get("bpm", 0) or 0,
                    "energy": docker_data.get("energy", 0) or 0,
                    "key": docker_data.get("key", ""),
                    "source": "docker",
                })
                docker_hits += 1
            else:
                enriched.append({"track": track, "needs_spotify": True})

        # STEP 2: fallback for songs Docker did not have.
        # The Spotify audio-features API has been blocked for most apps since 2024 (403).
        # We try anyway, but never crash when it fails.
        spotify_needed = [e for e in enriched if e.get("needs_spotify")]
        if spotify_needed:
            track_ids = [e["track"]["id"] for e in spotify_needed if e["track"].get("id")]
            feat_map = {}
            if track_ids:
                try:
                    features = self.api.get_audio_features(track_ids)
                    for tid, feat in zip(track_ids, features):
                        if feat:
                            feat_map[tid] = feat
                except Exception as e:
                    log("SPOTIFY", f"⚠️ audio-features fallback failed (expected - API restricted): {e}", Fore.YELLOW)

                for e in enriched:
                    if e.get("needs_spotify"):
                        tid = e["track"].get("id", "")
                        feat = feat_map.get(tid)
                        if feat:
                            e["bpm"] = feat.get("tempo", 0)
                            e["energy"] = feat.get("energy", 0)
                            e["key"] = feat.get("key", -1)
                            e["source"] = "spotify"
                        else:
                            e["bpm"] = 0
                            e["energy"] = 0
                            e["key"] = ""
                            e["source"] = "unknown"
                        e.pop("needs_spotify", None)

        spotify_hits = sum(1 for e in enriched if e.get("source") == "spotify")
        unknown = sum(1 for e in enriched if e.get("source") == "unknown" or e.get("needs_spotify"))
        log("SPOTIFY", f"🧠 Enrichment: {docker_hits} Docker ✅ | {spotify_hits} Spotify ✅ | {unknown} unknown ❌ (of {len(tracks)} total)", Fore.CYAN)

        # Remove tracks without valid data (needs_spotify=True or sort_key==0)
        enriched = [e for e in enriched if not e.get("needs_spotify") and e.get(sort_key, 0)]
        log("SPOTIFY", f"🧠 After filter: {len(enriched)} tracks with valid {sort_key} data", Fore.CYAN)
        return enriched

    def sort_by_bpm(self, playlist_name: str, ascending: bool = True) -> Dict[str, Any]:
        """
        Sort a playlist by BPM (slow->fast or the reverse).
        Uses the Docker Music Brain, with the Spotify API as fallback.
        """
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' not found"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist is empty"}

        enriched = self._enrich_tracks_with_features(tracks, "bpm")

        # Shuffle MUST be off or Spotify ignores our ordering!
        self.api.set_shuffle(False)

        # Convert BPM to float (Docker sometimes returns strings)
        for e in enriched:
            try:
                e["bpm"] = float(e["bpm"])
            except (ValueError, TypeError):
                e["bpm"] = 0.0

        # Sort
        enriched.sort(key=lambda x: x["bpm"], reverse=not ascending)

        # Debug: show the first and last 5 songs with BPM
        log("SPOTIFY", f"📊 Sort direction: ascending={ascending}, reverse={not ascending}", Fore.CYAN)
        for i, e in enumerate(enriched[:5]):
            log("SPOTIFY", f"📊 #{i+1}: {e['bpm']:.0f} BPM - {e['track']['name']} ({e['source']})", Fore.CYAN)
        log("SPOTIFY", f"📊 ...", Fore.CYAN)
        for i, e in enumerate(enriched[-3:]):
            log("SPOTIFY", f"📊 #{len(enriched)-2+i}: {e['bpm']:.0f} BPM - {e['track']['name']} ({e['source']})", Fore.CYAN)

        # Play
        play_tracks = enriched[:100]
        uris = [e["track"]["uri"] for e in play_tracks]
        success = self.api.play(uris=uris)

        direction = "slow→fast" if ascending else "fast→slow"
        first = play_tracks[0]
        last = play_tracks[-1]

        return {
            "success": success,
            "playlist": playlist["name"],
            "total_tracks": len(play_tracks),
            "direction": direction,
            "bpm_range": f"{first['bpm']:.0f} → {last['bpm']:.0f} BPM",
            "message": f"🎵 '{playlist['name']}' sorted {direction}: {first['bpm']:.0f} → {last['bpm']:.0f} BPM ({len(play_tracks)} tracks)"
        }

    def sort_by_energy(self, playlist_name: str, ascending: bool = True) -> Dict[str, Any]:
        """Sort a playlist by energy (chill->hype or the reverse). Docker-first, Spotify-fallback."""
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' not found"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist is empty"}

        enriched = self._enrich_tracks_with_features(tracks, "energy")

        enriched.sort(key=lambda x: x["energy"], reverse=not ascending)

        play_tracks = enriched[:100]
        uris = [e["track"]["uri"] for e in play_tracks]
        success = self.api.play(uris=uris)

        direction = "chill→hype" if ascending else "hype→chill"
        return {
            "success": success,
            "playlist": playlist["name"],
            "total_tracks": len(play_tracks),
            "direction": direction,
            "message": f"🎵 '{playlist['name']}' sorted {direction} ({len(play_tracks)} tracks)"
        }

    def sort_by_key(self, playlist_name: str, target_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Sort a playlist by musical key.
        Camelot wheel ordering for harmonic mixing.
        When target_key is given, songs in that key are played first.
        """
        # Camelot wheel order (harmonic mixing)
        CAMELOT_ORDER = [
            "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
            "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
            "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"
        ]
        camelot_rank = {k: i for i, k in enumerate(CAMELOT_ORDER)}

        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' not found"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist is empty"}

        enriched = self._enrich_tracks_with_features(tracks, "key")

        # Shuffle off
        self.api.set_shuffle(False)

        # Filter: only songs with a valid key
        enriched = [e for e in enriched if e.get("key") and str(e["key"]).strip()]

        if not enriched:
            return {"success": False, "error": "No songs with key data found"}

        # Sort by Camelot wheel
        if target_key and target_key.upper() in camelot_rank:
            # Songs in the target_key first, then by Camelot proximity
            target_rank = camelot_rank[target_key.upper()]
            enriched.sort(key=lambda x: abs(camelot_rank.get(str(x.get("key", "")).upper(), 99) - target_rank))
        else:
            # Simply by Camelot order
            enriched.sort(key=lambda x: camelot_rank.get(str(x.get("key", "")).upper(), 99))

        # Debug
        log("SPOTIFY", f"🎹 Key sort: {len(enriched)} tracks with key data", Fore.CYAN)
        for i, e in enumerate(enriched[:5]):
            log("SPOTIFY", f"🎹 #{i+1}: Key {e['key']} - {e['track']['name']} ({e['source']})", Fore.CYAN)
        log("SPOTIFY", f"🎹 ...", Fore.CYAN)
        for i, e in enumerate(enriched[-3:]):
            log("SPOTIFY", f"🎹 #{len(enriched)-2+i}: Key {e['key']} - {e['track']['name']} ({e['source']})", Fore.CYAN)

        play_tracks = enriched[:100]
        uris = [e["track"]["uri"] for e in play_tracks]
        success = self.api.play(uris=uris)

        first_key = play_tracks[0].get("key", "?")
        last_key = play_tracks[-1].get("key", "?")

        return {
            "success": success,
            "playlist": playlist["name"],
            "total_tracks": len(play_tracks),
            "key_range": f"{first_key} → {last_key}",
            "target_key": target_key,
            "message": f"🎵 '{playlist['name']}' sorted by key: {first_key} → {last_key} ({len(play_tracks)} tracks)"
        }

    def yourai_shuffle(self, playlist_name: str, filter_artist: Optional[str] = None) -> Dict[str, Any]:
        """
        YourAI DJ shuffle - AI-style smart shuffle.
        Picks a random starting song, then always the best next match based on
        key compatibility (Camelot wheel), BPM proximity, and artist variety.
        A new but musically sensible ordering every time!
        """
        CAMELOT_ORDER = [
            "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
            "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
            "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"
        ]
        camelot_rank = {k: i for i, k in enumerate(CAMELOT_ORDER)}

        # Compatible keys on the Camelot wheel (harmonic mixing)
        # For each key: same key, ±1 number, and A<->B switch
        def get_compatible_keys(key_str: str) -> set:
            if not key_str:
                return set()
            key_upper = key_str.upper()
            num_str = key_upper.rstrip("AB")
            letter = key_upper[-1] if key_upper[-1] in "AB" else ""
            try:
                num = int(num_str)
            except ValueError:
                return {key_upper}

            compatible = {key_upper}
            # Same number, other mode (A<->B)
            other_letter = "B" if letter == "A" else "A"
            compatible.add(f"{num}{other_letter}")
            # ±1 on the wheel (wrap around 1-12)
            prev_num = 12 if num == 1 else num - 1
            next_num = 1 if num == 12 else num + 1
            compatible.add(f"{prev_num}{letter}")
            compatible.add(f"{next_num}{letter}")
            return compatible

        # Load playlist
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' not found"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist is empty"}

        # Artist filter
        if filter_artist:
            filter_lower = filter_artist.lower()
            tracks = [t for t in tracks if any(
                filter_lower in a["name"].lower() for a in t.get("artists", [])
            )]
            if not tracks:
                return {"success": False, "error": f"No track by '{filter_artist}' in '{playlist['name']}'"}

        # Enrich with BPM + key (we need both!)
        enriched = self._enrich_tracks_with_features(tracks, "bpm")
        # Load the key separately for tracks that have BPM but maybe no key
        for e in enriched:
            if not e.get("key"):
                docker_data = _get_docker_song_features(
                    e["track"].get("name", ""),
                    e["track"].get("artists", [{}])[0].get("name", "")
                )
                if docker_data and docker_data.get("key"):
                    e["key"] = docker_data["key"]

        # BPM to float
        for e in enriched:
            try:
                e["bpm"] = float(e.get("bpm", 0))
            except (ValueError, TypeError):
                e["bpm"] = 0.0

        # Shuffle OFF
        self.api.set_shuffle(False)

        # === YOURAI DJ ALGORITHM ===
        # Pick a random starting song
        remaining = list(enriched)
        random.shuffle(remaining)  # Randomize start

        ordered = [remaining.pop(0)]

        while remaining:
            current = ordered[-1]
            curr_key = str(current.get("key", "")).upper()
            curr_bpm = current.get("bpm", 0)
            curr_artist = current["track"].get("artists", [{}])[0].get("name", "").lower()
            compatible_keys = get_compatible_keys(curr_key)

            # Score every remaining track
            scored = []
            for candidate in remaining:
                score = 0.0
                cand_key = str(candidate.get("key", "")).upper()
                cand_bpm = candidate.get("bpm", 0)
                cand_artist = candidate["track"].get("artists", [{}])[0].get("name", "").lower()

                # Key compatibility (0-40 points)
                if cand_key and curr_key:
                    if cand_key == curr_key:
                        score += 40  # Perfect match
                    elif cand_key in compatible_keys:
                        score += 30  # Harmonically compatible
                    else:
                        # The further away on the Camelot wheel, the fewer points
                        dist = abs(camelot_rank.get(cand_key, 12) - camelot_rank.get(curr_key, 12))
                        dist = min(dist, 24 - dist)  # Shorter path around the wheel
                        score += max(0, 20 - dist * 2)

                # BPM proximity (0-30 points)
                if cand_bpm > 0 and curr_bpm > 0:
                    bpm_diff = abs(cand_bpm - curr_bpm)
                    if bpm_diff <= 5:
                        score += 30
                    elif bpm_diff <= 15:
                        score += 20
                    elif bpm_diff <= 30:
                        score += 10
                    # >30 BPM diff = 0 points

                # Artist variety (0-15 points)
                if cand_artist != curr_artist:
                    score += 15  # Different artist = bonus

                # Random factor (0-25 points) - so it never gets boring!
                score += random.uniform(0, 25)

                scored.append((score, candidate))

            # Take the best match
            scored.sort(key=lambda x: x[0], reverse=True)
            best = scored[0][1]
            remaining.remove(best)
            ordered.append(best)

        # Debug
        log("SPOTIFY", f"🦊 YourAI DJ Shuffle: {len(ordered)} tracks", Fore.MAGENTA)
        for i, e in enumerate(ordered[:5]):
            key = e.get("key", "?")
            bpm = e.get("bpm", 0)
            name = e["track"]["name"]
            artist = e["track"].get("artists", [{}])[0].get("name", "")
            log("SPOTIFY", f"🦊 #{i+1}: {key} | {bpm:.0f}BPM | {artist} - {name}", Fore.MAGENTA)
        if len(ordered) > 5:
            log("SPOTIFY", f"🦊 ... ({len(ordered) - 5} more)", Fore.MAGENTA)

        # Play
        play_tracks = ordered[:100]
        uris = [e["track"]["uri"] for e in play_tracks]
        success = self.api.play(uris=uris)

        first = play_tracks[0]
        first_name = f"{first['track']['name']} - {first['track'].get('artists', [{}])[0].get('name', '')}"

        return {
            "success": success,
            "playlist": playlist["name"],
            "total_tracks": len(play_tracks),
            "first_track": first_name,
            "message": f"🦊🎧 YourAI DJ Shuffle: '{playlist['name']}' ({len(play_tracks)} tracks). Starting with: {first_name}"
        }

    def play_control(self, action: str) -> Dict[str, Any]:
        """Simple playback control: pause, resume, skip, previous, volume."""
        actions = {
            "pause": self.api.pause,
            "resume": lambda: self.api.play(),
            "skip": self.api.skip_next,
            "next": self.api.skip_next,
            "previous": self.api.skip_previous,
            "back": self.api.skip_previous,
        }

        if action.startswith("volume"):
            try:
                vol = int(action.split()[-1])
                vol = max(0, min(100, vol))
                success = self.api.set_volume(vol)
                return {"success": success, "message": f"🔊 Volume: {vol}%"}
            except (ValueError, IndexError):
                return {"success": False, "error": "Usage: volume 0-100"}

        func = actions.get(action.lower())
        if not func:
            return {"success": False, "error": f"Unknown action: {action}. Try: pause, resume, skip, previous, volume <0-100>"}

        success = func()
        icons = {"pause": "⏸️", "resume": "▶️", "skip": "⏭️", "next": "⏭️", "previous": "⏮️", "back": "⏮️"}
        icon = icons.get(action.lower(), "🎵")
        return {"success": success, "message": f"{icon} {action.capitalize()}!"}

    def queue_playlist(self, playlist_name: str, max_tracks: int = 20) -> Dict[str, Any]:
        """Add a playlist's tracks to the queue."""
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' not found"}

        raw_tracks = self._get_tracks(playlist)
        playable = [t for t in raw_tracks if t.get("track") and t["track"].get("uri")]
        if not playable:
            return {"success": False, "error": f"Playlist '{playlist_name}' has no playable tracks"}

        to_queue = playable[:max_tracks]
        queued = 0
        for item in to_queue:
            uri = item["track"]["uri"]
            if self.api.add_to_queue(uri):
                queued += 1

        pname = playlist.get("name", playlist_name)
        return {
            "success": queued > 0,
            "message": f"📋 Added {queued}/{len(to_queue)} tracks from '{pname}' to queue",
            "queued": queued,
            "total": len(to_queue),
        }

    def get_queue_info(self) -> Dict[str, Any]:
        """Show the current queue."""
        queue = self.api.get_queue()
        if not queue:
            return {"success": False, "error": "No active queue"}

        current = queue.get("currently_playing")
        upcoming = queue.get("queue", [])[:10]

        result: Dict[str, Any] = {"success": True}
        if current:
            result["now_playing"] = f"{current['name']} - {current['artists'][0]['name']}"

        result["upcoming"] = [
            f"{t['name']} - {t['artists'][0]['name']}" for t in upcoming
        ]
        result["message"] = f"🎵 Now: {result.get('now_playing', '?')} | Next {len(result['upcoming'])} tracks in queue"
        return result

    def list_playlists(self) -> Dict[str, Any]:
        """List all playlists."""
        playlists = self.api.get_my_playlists()
        names = [f"{pl['name']} ({pl['tracks']['total']} tracks)" for pl in playlists[:20]]
        return {
            "success": True,
            "playlists": names,
            "total": len(playlists),
            "message": f"📋 {len(playlists)} playlists: " + ", ".join(names[:5]) + "..."
        }


# ==========================================
# TOOL INTERFACE (for tool_router.py)
# ==========================================

# Singleton
_spotify: Optional[SpotifyControl] = None

def _get_spotify() -> SpotifyControl:
    """Return the global SpotifyControl instance (creating it on first use)."""
    global _spotify
    if _spotify is None:
        _spotify = SpotifyControl()
    return _spotify


def execute_spotify_command(context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """
    Main entry point for YourAI's Spotify control.
    Called by the tool router with (context, debug).

    Context contains:
        question: The user question (we parse the command from it).
        user_role: The user's role - ADMIN ONLY may use this!

    Args:
        context (Dict[str, Any]): Tool context (question, user_role, ...).
        debug (Any): Optional dashboard debug client.

    Returns:
        Dict[str, Any]: The result dict of the dispatched Spotify command.
    """
    user_role = context.get("user_role", "guest")
    question = context.get("question", "")

    # ADMIN CHECK
    if user_role != "admin":
        err = YourAINoPrivilegeError(user_role, "control Spotify")
        log("SPOTIFY", f"🚫 {err.short()}", Fore.RED)
        return {
            "success": False,
            "error": err.short(),
            "message": "Sorry, only Creator may control my music! 🎵🔒"
        }

    try:
        spotify = _get_spotify()
        cmd = question.lower().strip()

        # --- Playback controls ---
        if any(w in cmd for w in ("pause", "stopp", "stop music", "pause musik")):
            return spotify.play_control("pause")

        if any(w in cmd for w in ("resume", "weiter", "play spotify", "musik weiter")):
            return spotify.play_control("resume")

        if any(w in cmd for w in ("skip", "nächstes lied", "next song", "überspring")):
            return spotify.play_control("skip")

        if any(w in cmd for w in ("previous", "vorheriges", "zurück", "back")):
            return spotify.play_control("previous")

        if any(w in cmd for w in ("volume", "lautstärke", "lauter", "leiser")):
            # Try to find a number
            volume = extract_spotify_volume(cmd)
            if "lauter" in cmd:
                return spotify.play_control("volume 80")
            elif "leiser" in cmd:
                return spotify.play_control("volume 30")
            elif volume:
                return spotify.play_control(f"volume {volume}")
            return {"success": False, "error": "Which volume? (0-100)"}

        # --- Queue ---
        if any(w in cmd for w in ("queue", "was kommt", "what's next", "was läuft")):
            return spotify.get_queue_info()

        # --- Playlists ---
        if any(w in cmd for w in ("playlists", "welche playlist", "meine playlists", "show playlist", "list playlist")):
            return spotify.list_playlists()

        # --- Shuffle ---
        if any(w in cmd for w in ("shuffle", "shuffel", "mischen", "durchmischen")):
            playlist_name = extract_spotify_playlist_name(cmd)
            filter_artist = extract_spotify_artist_filter(cmd)
            if not playlist_name:
                return {"success": False, "error": "Which playlist should I shuffle? e.g. 'shuffle meine Lieblingssongs'"}
            log("SPOTIFY", f"🎲 Shuffle: playlist='{playlist_name}', filter='{filter_artist}'", Fore.CYAN)
            return spotify.shuffle_playlist(playlist_name, filter_artist=filter_artist)

        # --- Sort by BPM ---
        if any(w in cmd for w in ("bpm", "tempo")):
            playlist_name = extract_spotify_playlist_name(cmd)
            ascending = any(w in cmd for w in ("slow", "langsam", "ascending", "low", "rauf"))
            if not playlist_name:
                return {"success": False, "error": "Which playlist? e.g. 'sort Lieblingssongs by BPM slow to fast'"}
            return spotify.sort_by_bpm(playlist_name, ascending=ascending)

        # --- Sort by Energy ---
        if any(w in cmd for w in ("energy", "chill", "hype", "energie")):
            playlist_name = extract_spotify_playlist_name(cmd)
            ascending = any(w in cmd for w in ("chill", "low", "langsam", "ruhig"))
            if not playlist_name:
                return {"success": False, "error": "Which playlist?"}
            return spotify.sort_by_energy(playlist_name, ascending=ascending)

        # --- Play specific playlist ---
        if any(w in cmd for w in ("spiel", "play my", "spiele meine")):
            playlist_name = extract_spotify_playlist_name(cmd)
            filter_artist = extract_spotify_artist_filter(cmd)
            if playlist_name:
                return spotify.shuffle_playlist(playlist_name, filter_artist=filter_artist)

        return {
            "success": False,
            "error": "Could not understand the Spotify command. Try: shuffle [playlist], skip, pause, queue, playlists, sort by bpm",
            "message": "🎵 Hmm, I didn't get that. Say e.g. 'shuffle meine Lieblingssongs' or 'skip'!"
        }

    except Exception as e:
        err = YourAIToolExecutionError("Spotify control failed", tool_name="spotify_control", cause=e)
        log_exception("SPOTIFY", err)
        return {"success": False, "error": str(e), "message": f"🎵❌ Spotify Error: {e}"}
