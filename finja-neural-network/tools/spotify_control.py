"""
YourAI AI - Spotify Control
============================
Playlist-/Queue-Steuerung über die Spotify Web API.
NUR für Admin (Admin) verfügbar!

Features:
    - Playlist nach Artist/Genre filtern & abspielen
    - Queue nach BPM sortieren (langsam→schnell, schnell→langsam)
    - Smart Shuffle (echtes Shuffle, nicht Spotifys Fake)
    - Skip, Pause, Resume
    - Aktuelle Queue anzeigen

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

# Tools-Ordner braucht Zugriff auf Parent-Module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN
from exceptions import YourAINoPrivilegeError, YourAIToolExecutionError

# ==========================================
# SPOTIFY AUTH
# ==========================================

class SpotifyAuth:
    """Handles Spotify OAuth token refresh."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires: float = 0.0

    def get_token(self) -> Optional[str]:
        """Holt oder refreshed den Access Token."""
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
        self.auth = SpotifyAuth()

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self.auth.get_token()}"}

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
        if resp.status_code == 401:
            # Token expired, refresh and retry
            self.auth._access_token = None
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    def _put(self, endpoint: str, json_data: Optional[Dict] = None) -> bool:
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.put(url, headers=self._headers(), json=json_data, timeout=10)
        if resp.status_code == 401:
            self.auth._access_token = None
            resp = requests.put(url, headers=self._headers(), json=json_data, timeout=10)
        return resp.status_code in (200, 204)

    def _post(self, endpoint: str, json_data: Optional[Dict] = None) -> bool:
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.post(url, headers=self._headers(), json=json_data, timeout=10)
        if resp.status_code == 401:
            self.auth._access_token = None
            resp = requests.post(url, headers=self._headers(), json=json_data, timeout=10)
        return resp.status_code in (200, 201, 204)

    # --- Playback ---

    def get_current_playback(self) -> Optional[Dict]:
        """Was läuft gerade?"""
        try:
            return self._get("me/player")
        except Exception:
            return None

    def play(self, uris: Optional[List[str]] = None, context_uri: Optional[str] = None,
             offset: Optional[Dict] = None) -> bool:
        """Startet Playback mit bestimmten Tracks oder Context."""
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
        return self._put("me/player/pause")

    def skip_next(self) -> bool:
        return self._post("me/player/next")

    def skip_previous(self) -> bool:
        return self._post("me/player/previous")

    def set_volume(self, volume_percent: int) -> bool:
        url = f"{self.BASE_URL}/me/player/volume?volume_percent={volume_percent}"
        resp = requests.put(url, headers=self._headers(), timeout=10)
        return resp.status_code in (200, 204)

    def add_to_queue(self, uri: str) -> bool:
        url = f"{self.BASE_URL}/me/player/queue?uri={uri}"
        resp = requests.post(url, headers=self._headers(), timeout=10)
        return resp.status_code in (200, 204)

    def set_shuffle(self, state: bool) -> bool:
        """Shuffle ein/ausschalten."""
        url = f"{self.BASE_URL}/me/player/shuffle?state={'true' if state else 'false'}"
        resp = requests.put(url, headers=self._headers(), timeout=10)
        log("SPOTIFY", f"🔀 Shuffle {'ON' if state else 'OFF'}: {resp.status_code}", Fore.CYAN)
        return resp.status_code in (200, 204)

    def get_queue(self) -> Optional[Dict]:
        """Holt die aktuelle Queue."""
        try:
            return self._get("me/player/queue")
        except Exception:
            return None

    # --- Playlists ---

    def get_my_playlists(self, limit: int = 50) -> List[Dict]:
        """Alle Playlists des Users."""
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
        """Alle Tracks einer Playlist."""
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

    # Aliases für Spotify's "Liked Songs" (speziell, nicht in /me/playlists!)
    LIKED_SONGS_ALIASES = [
        "lieblingssongs", "liked songs", "liked", "lieblings", "favorites",
        "favourites", "meine songs", "my songs", "gespeicherte songs", "saved songs"
    ]

    def _is_liked_songs(self, name: str) -> bool:
        """Prüft ob der Name auf Spotify's 'Liked Songs' verweist."""
        name_lower = name.lower().strip()
        return any(alias in name_lower for alias in self.LIKED_SONGS_ALIASES)

    def get_liked_songs(self, limit: int = 500) -> List[Dict]:
        """Holt die 'Liked Songs' (Lieblingssongs) über /me/tracks."""
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
        log("SPOTIFY", f"❤️ Liked Songs: {len(tracks)} tracks geladen", Fore.CYAN)
        return tracks

    def find_playlist(self, name: str) -> Optional[Dict]:
        """Findet eine Playlist nach Name (fuzzy). Erkennt auch 'Liked Songs'."""
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
        """Audio Features (BPM, Key, Energy etc.) für mehrere Tracks."""
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
    Holt enriched Song-Daten vom Docker Music Brain.
    Returns None wenn Docker nicht erreichbar → Fallback auf Spotify API.
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
        log("SPOTIFY", f"⚠️ Docker Brain not reachable: {e} → Spotify API fallback", Fore.YELLOW)
        return None


def _get_docker_song_features(title: str, artist: str) -> Optional[Dict]:
    """Holt Features für einen einzelnen Song vom Docker."""
    try:
        resp = requests.get(f"{MUSIC_BRAIN_URL}/get/song_features",
                           params={"title": title, "artist": artist}, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


class SpotifyControl:
    """
    High-level Spotify Control für YourAI.
    Nur Admin darf das benutzen!
    Nutzt Docker Music Brain für enriched Daten, Spotify API als Fallback.
    """

    def __init__(self):
        self.api = SpotifyAPI()

    def _get_tracks(self, playlist: Dict) -> List[Dict]:
        """Holt Tracks - automatisch Liked Songs oder normale Playlist."""
        if playlist.get("_is_liked"):
            return self.api.get_liked_songs()
        return self.api.get_playlist_tracks(playlist["id"])

    def shuffle_playlist(self, playlist_name: str,
                         filter_artist: Optional[str] = None,
                         filter_genre: Optional[str] = None) -> Dict[str, Any]:
        """
        Echtes Shuffle einer Playlist (nicht Spotifys Fake-Shuffle).
        Optional nach Artist oder Genre filtern.
        """
        # Playlist finden
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' nicht gefunden"}

        # Tracks laden
        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("uri")]

        if not tracks:
            return {"success": False, "error": f"Playlist '{playlist_name}' ist leer"}

        # Filter nach Artist
        if filter_artist:
            filter_lower = filter_artist.lower()
            tracks = [t for t in tracks if any(
                filter_lower in a["name"].lower() for a in t.get("artists", [])
            )]
            if not tracks:
                return {"success": False, "error": f"Kein Track von '{filter_artist}' in '{playlist_name}'"}

        # Echtes Shuffle
        random.shuffle(tracks)

        # Max 100 Tracks für die Queue (Spotify Limit)
        play_tracks = tracks[:100]
        uris = [t["uri"] for t in play_tracks]

        log("SPOTIFY", f"🎲 Shuffle: {len(tracks)} tracks found, playing {len(play_tracks)}", Fore.CYAN)
        log("SPOTIFY", f"🎲 Filter: artist='{filter_artist}', genre='{filter_genre}'", Fore.CYAN)
        log("SPOTIFY", f"🎲 First 3 URIs: {uris[:3]}", Fore.CYAN)
        log("SPOTIFY", f"🎲 First 3 tracks: {[t['name'] for t in play_tracks[:3]]}", Fore.CYAN)

        # Abspielen
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
            "message": f"🎵 Shuffled '{playlist['name']}' ({len(play_tracks)} Tracks). First up: {track_names[0]}"
        }

    def _enrich_tracks_with_features(self, tracks: List[Dict], sort_key: str) -> List[Dict]:
        """
        Enriched Tracks mit BPM/Energy/etc.
        Erst Docker Music Brain fragen, dann Spotify API als Fallback.
        """
        enriched = []

        # STEP 1: Versuche Docker Music Brain
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

        # STEP 2: Fallback für Songs die Docker nicht hatte
        # Spotify audio-features API ist seit 2024 für die meisten Apps gesperrt (403)
        # Wir versuchen es trotzdem, aber crashen nicht wenn es fehlschlägt
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

        # Entferne Tracks ohne gültige Daten (needs_spotify=True oder sort_key==0)
        enriched = [e for e in enriched if not e.get("needs_spotify") and e.get(sort_key, 0)]
        log("SPOTIFY", f"🧠 After filter: {len(enriched)} tracks with valid {sort_key} data", Fore.CYAN)
        return enriched

    def sort_by_bpm(self, playlist_name: str, ascending: bool = True) -> Dict[str, Any]:
        """
        Sortiert Playlist nach BPM (langsam→schnell oder umgekehrt).
        Nutzt Docker Music Brain, Spotify API als Fallback.
        """
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' nicht gefunden"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist ist leer"}

        enriched = self._enrich_tracks_with_features(tracks, "bpm")

        # Shuffle MUSS aus sein sonst ignoriert Spotify unsere Reihenfolge!
        self.api.set_shuffle(False)

        # BPM zu float konvertieren (Docker gibt manchmal Strings zurück)
        for e in enriched:
            try:
                e["bpm"] = float(e["bpm"])
            except (ValueError, TypeError):
                e["bpm"] = 0.0

        # Sortieren
        enriched.sort(key=lambda x: x["bpm"], reverse=not ascending)

        # Debug: Erste und letzte 5 Songs mit BPM zeigen
        log("SPOTIFY", f"📊 Sort direction: ascending={ascending}, reverse={not ascending}", Fore.CYAN)
        for i, e in enumerate(enriched[:5]):
            log("SPOTIFY", f"📊 #{i+1}: {e['bpm']:.0f} BPM - {e['track']['name']} ({e['source']})", Fore.CYAN)
        log("SPOTIFY", f"📊 ...", Fore.CYAN)
        for i, e in enumerate(enriched[-3:]):
            log("SPOTIFY", f"📊 #{len(enriched)-2+i}: {e['bpm']:.0f} BPM - {e['track']['name']} ({e['source']})", Fore.CYAN)

        # Abspielen
        play_tracks = enriched[:100]
        uris = [e["track"]["uri"] for e in play_tracks]
        success = self.api.play(uris=uris)

        direction = "langsam→schnell" if ascending else "schnell→langsam"
        first = play_tracks[0]
        last = play_tracks[-1]

        return {
            "success": success,
            "playlist": playlist["name"],
            "total_tracks": len(play_tracks),
            "direction": direction,
            "bpm_range": f"{first['bpm']:.0f} → {last['bpm']:.0f} BPM",
            "message": f"🎵 '{playlist['name']}' sortiert {direction}: {first['bpm']:.0f} → {last['bpm']:.0f} BPM ({len(play_tracks)} Tracks)"
        }

    def sort_by_energy(self, playlist_name: str, ascending: bool = True) -> Dict[str, Any]:
        """Sortiert Playlist nach Energy (chill→hype oder umgekehrt). Docker-first, Spotify-fallback."""
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' nicht gefunden"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist ist leer"}

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
            "message": f"🎵 '{playlist['name']}' sortiert {direction} ({len(play_tracks)} Tracks)"
        }

    def sort_by_key(self, playlist_name: str, target_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Sortiert Playlist nach musikalischem Key.
        Camelot Wheel Reihenfolge für harmonisches Mixing.
        Wenn target_key angegeben, werden Songs in diesem Key zuerst gespielt.
        """
        # Camelot Wheel Reihenfolge (harmonisches Mixing)
        CAMELOT_ORDER = [
            "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
            "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
            "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"
        ]
        camelot_rank = {k: i for i, k in enumerate(CAMELOT_ORDER)}

        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' nicht gefunden"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist ist leer"}

        enriched = self._enrich_tracks_with_features(tracks, "key")

        # Shuffle aus
        self.api.set_shuffle(False)

        # Filter: nur Songs mit gültigem Key
        enriched = [e for e in enriched if e.get("key") and str(e["key"]).strip()]

        if not enriched:
            return {"success": False, "error": "Keine Songs mit Key-Daten gefunden"}

        # Sortieren nach Camelot Wheel
        if target_key and target_key.upper() in camelot_rank:
            # Songs im target_key zuerst, dann nach Camelot-Nähe
            target_rank = camelot_rank[target_key.upper()]
            enriched.sort(key=lambda x: abs(camelot_rank.get(str(x.get("key", "")).upper(), 99) - target_rank))
        else:
            # Einfach nach Camelot-Reihenfolge
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
            "message": f"🎵 '{playlist['name']}' sortiert nach Key: {first_key} → {last_key} ({len(play_tracks)} Tracks)"
        }

    def yourai_shuffle(self, playlist_name: str, filter_artist: Optional[str] = None) -> Dict[str, Any]:
        """
        YourAI DJ Shuffle - KI-artiges Smart Shuffle.
        Wählt einen zufälligen Start-Song, dann immer den besten nächsten Match
        basierend auf Key-Kompatibilität (Camelot Wheel), BPM-Nähe und Artist-Abwechslung.
        Jedes Mal eine neue, aber musikalisch sinnvolle Reihenfolge!
        """
        CAMELOT_ORDER = [
            "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
            "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
            "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B"
        ]
        camelot_rank = {k: i for i, k in enumerate(CAMELOT_ORDER)}

        # Kompatible Keys auf dem Camelot Wheel (harmonisches Mixing)
        # Für jeden Key: gleicher Key, ±1 Nummer, und A↔B Switch
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
            # Gleiche Nummer, andere Tonart (A↔B)
            other_letter = "B" if letter == "A" else "A"
            compatible.add(f"{num}{other_letter}")
            # ±1 auf dem Wheel (wrap around 1-12)
            prev_num = 12 if num == 1 else num - 1
            next_num = 1 if num == 12 else num + 1
            compatible.add(f"{prev_num}{letter}")
            compatible.add(f"{next_num}{letter}")
            return compatible

        # Playlist laden
        playlist = self.api.find_playlist(playlist_name)
        if not playlist:
            return {"success": False, "error": f"Playlist '{playlist_name}' nicht gefunden"}

        raw_tracks = self._get_tracks(playlist)
        tracks = [t["track"] for t in raw_tracks if t.get("track") and t["track"].get("id")]

        if not tracks:
            return {"success": False, "error": "Playlist ist leer"}

        # Artist filter
        if filter_artist:
            filter_lower = filter_artist.lower()
            tracks = [t for t in tracks if any(
                filter_lower in a["name"].lower() for a in t.get("artists", [])
            )]
            if not tracks:
                return {"success": False, "error": f"Kein Track von '{filter_artist}' in '{playlist['name']}'"}

        # Enrich mit BPM + Key (brauchen beides!)
        enriched = self._enrich_tracks_with_features(tracks, "bpm")
        # Key separat nachladen für Tracks die BPM haben aber evtl. keinen Key
        for e in enriched:
            if not e.get("key"):
                docker_data = _get_docker_song_features(
                    e["track"].get("name", ""),
                    e["track"].get("artists", [{}])[0].get("name", "")
                )
                if docker_data and docker_data.get("key"):
                    e["key"] = docker_data["key"]

        # BPM zu float
        for e in enriched:
            try:
                e["bpm"] = float(e.get("bpm", 0))
            except (ValueError, TypeError):
                e["bpm"] = 0.0

        # Shuffle OFF
        self.api.set_shuffle(False)

        # === YOURAI DJ ALGORITHMUS ===
        # Zufälligen Start-Song wählen
        remaining = list(enriched)
        random.shuffle(remaining)  # Randomize start

        ordered = [remaining.pop(0)]

        while remaining:
            current = ordered[-1]
            curr_key = str(current.get("key", "")).upper()
            curr_bpm = current.get("bpm", 0)
            curr_artist = current["track"].get("artists", [{}])[0].get("name", "").lower()
            compatible_keys = get_compatible_keys(curr_key)

            # Score für jeden verbleibenden Track berechnen
            scored = []
            for candidate in remaining:
                score = 0.0
                cand_key = str(candidate.get("key", "")).upper()
                cand_bpm = candidate.get("bpm", 0)
                cand_artist = candidate["track"].get("artists", [{}])[0].get("name", "").lower()

                # Key Kompatibilität (0-40 Punkte)
                if cand_key and curr_key:
                    if cand_key == curr_key:
                        score += 40  # Perfekter Match
                    elif cand_key in compatible_keys:
                        score += 30  # Harmonisch kompatibel
                    else:
                        # Je weiter weg auf dem Camelot Wheel, desto weniger Punkte
                        dist = abs(camelot_rank.get(cand_key, 12) - camelot_rank.get(curr_key, 12))
                        dist = min(dist, 24 - dist)  # Kürzerer Weg auf dem Wheel
                        score += max(0, 20 - dist * 2)

                # BPM Nähe (0-30 Punkte)
                if cand_bpm > 0 and curr_bpm > 0:
                    bpm_diff = abs(cand_bpm - curr_bpm)
                    if bpm_diff <= 5:
                        score += 30
                    elif bpm_diff <= 15:
                        score += 20
                    elif bpm_diff <= 30:
                        score += 10
                    # >30 BPM diff = 0 Punkte

                # Artist Abwechslung (0-15 Punkte)
                if cand_artist != curr_artist:
                    score += 15  # Anderer Artist = bonus

                # Random Faktor (0-25 Punkte) - damit es nie langweilig wird!
                score += random.uniform(0, 25)

                scored.append((score, candidate))

            # Besten Match nehmen
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

        # Abspielen
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
            "message": f"🦊🎧 YourAI DJ Shuffle: '{playlist['name']}' ({len(play_tracks)} Tracks). Los geht's mit: {first_name}"
        }

    def play_control(self, action: str) -> Dict[str, Any]:
        """Einfache Playback-Steuerung: pause, resume, skip, previous, volume."""
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
        """Fügt Tracks einer Playlist zur Queue hinzu."""
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
        """Zeigt die aktuelle Queue."""
        queue = self.api.get_queue()
        if not queue:
            return {"success": False, "error": "Keine aktive Queue"}

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
        """Listet alle Playlists."""
        playlists = self.api.get_my_playlists()
        names = [f"{pl['name']} ({pl['tracks']['total']} tracks)" for pl in playlists[:20]]
        return {
            "success": True,
            "playlists": names,
            "total": len(playlists),
            "message": f"📋 {len(playlists)} Playlists: " + ", ".join(names[:5]) + "..."
        }


# ==========================================
# TOOL INTERFACE (für tool_router.py)
# ==========================================

# Singleton
_spotify: Optional[SpotifyControl] = None

def _get_spotify() -> SpotifyControl:
    global _spotify
    if _spotify is None:
        _spotify = SpotifyControl()
    return _spotify


def execute_spotify_command(context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """
    Main entry point für YourAI's Spotify Control.
    Wird vom tool_router aufgerufen mit (context, debug).

    Context enthält:
        question: Die User-Frage (daraus parsen wir den Command)
        user_role: Rolle des Users - NUR "admin" darf das!
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
            "message": "Sorry, nur Creator darf meine Musik steuern! 🎵🔒"
        }

    try:
        spotify = _get_spotify()
        cmd = question.lower().strip()

        # --- Playback Controls ---
        if any(w in cmd for w in ("pause", "stopp", "stop music", "pause musik")):
            return spotify.play_control("pause")

        if any(w in cmd for w in ("resume", "weiter", "play spotify", "musik weiter")):
            return spotify.play_control("resume")

        if any(w in cmd for w in ("skip", "nächstes lied", "next song", "überspring")):
            return spotify.play_control("skip")

        if any(w in cmd for w in ("previous", "vorheriges", "zurück", "back")):
            return spotify.play_control("previous")

        if any(w in cmd for w in ("volume", "lautstärke", "lauter", "leiser")):
            # Versuche Zahl zu finden
            import re
            vol_match = re.search(r'(\d+)', cmd)
            if "lauter" in cmd:
                return spotify.play_control("volume 80")
            elif "leiser" in cmd:
                return spotify.play_control("volume 30")
            elif vol_match:
                return spotify.play_control(f"volume {vol_match.group(1)}")
            return {"success": False, "error": "Welche Lautstärke? (0-100)"}

        # --- Queue ---
        if any(w in cmd for w in ("queue", "was kommt", "what's next", "was läuft")):
            return spotify.get_queue_info()

        # --- Playlists ---
        if any(w in cmd for w in ("playlists", "welche playlist", "meine playlists", "show playlist", "list playlist")):
            return spotify.list_playlists()

        # --- Shuffle ---
        if any(w in cmd for w in ("shuffle", "shuffel", "mischen", "durchmischen")):
            playlist_name = _extract_playlist_name(cmd)
            filter_artist = _extract_artist_filter(cmd)
            if not playlist_name:
                return {"success": False, "error": "Welche Playlist soll ich shufflen? z.B. 'shuffle meine Lieblingssongs'"}
            log("SPOTIFY", f"🎲 Shuffle: playlist='{playlist_name}', filter='{filter_artist}'", Fore.CYAN)
            return spotify.shuffle_playlist(playlist_name, filter_artist=filter_artist)

        # --- Sort by BPM ---
        if any(w in cmd for w in ("bpm", "tempo")):
            playlist_name = _extract_playlist_name(cmd)
            ascending = any(w in cmd for w in ("slow", "langsam", "ascending", "low", "rauf"))
            if not playlist_name:
                return {"success": False, "error": "Welche Playlist? z.B. 'sortiere Lieblingssongs nach BPM langsam bis schnell'"}
            return spotify.sort_by_bpm(playlist_name, ascending=ascending)

        # --- Sort by Energy ---
        if any(w in cmd for w in ("energy", "chill", "hype", "energie")):
            playlist_name = _extract_playlist_name(cmd)
            ascending = any(w in cmd for w in ("chill", "low", "langsam", "ruhig"))
            if not playlist_name:
                return {"success": False, "error": "Welche Playlist?"}
            return spotify.sort_by_energy(playlist_name, ascending=ascending)

        # --- Play specific playlist ---
        if any(w in cmd for w in ("spiel", "play my", "spiele meine")):
            playlist_name = _extract_playlist_name(cmd)
            filter_artist = _extract_artist_filter(cmd)
            if playlist_name:
                return spotify.shuffle_playlist(playlist_name, filter_artist=filter_artist)

        return {
            "success": False,
            "error": "Konnte Spotify-Befehl nicht verstehen. Probier: shuffle [playlist], skip, pause, queue, playlists, sort by bpm",
            "message": "🎵 Hmm, das hab ich nicht verstanden. Sag z.B. 'shuffle meine Lieblingssongs' oder 'skip'!"
        }

    except Exception as e:
        err = YourAIToolExecutionError("Fehler bei der Spotify Steuerung", tool_name="spotify_control", cause=e)
        log_exception("SPOTIFY", err)
        return {"success": False, "error": str(e), "message": f"🎵❌ Spotify Error: {e}"}


def _extract_playlist_name(text: str) -> Optional[str]:
    """
    Versucht einen Playlist-Namen aus natürlicher Sprache zu extrahieren.
    z.B. "shuffle meine Lieblingssongs" → "Lieblingssongs"
    z.B. "shuffle playlist Gaming Mix" → "Gaming Mix"
    """
    import re

    # Pattern: "playlist <name>" oder "meine <name>"
    patterns = [
        r'playlist\s+["\']?([^"\']+?)["\']?\s*(?:nach|by|filter|nur|$)',
        r'playlist\s+["\']?(.+?)["\']?$',
        r'meine\s+["\']?([^"\']+?)["\']?\s*(?:nach|by|filter|nur|shuffle|$)',
        r'spiel(?:e)?\s+["\']?(.+?)["\']?\s*(?:nach|by|ab|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Cleanup: Entferne Command-Wörter die versehentlich mit erfasst wurden
            for word in ["shuffle", "shuffel", "sort", "sortiere", "nach bpm", "nach energy",
                         "nur von", "filter", "only", "by bpm", "langsam", "schnell"]:
                name = name.replace(word, "").strip()
            if name:
                return name

    # Fallback: Alles nach dem Command-Keyword nehmen
    for keyword in ["shuffle", "shuffel", "mischen", "sortiere", "sort", "spiel", "play"]:
        if keyword in text:
            rest = text.split(keyword, 1)[1].strip()
            # Entferne "meine", "my", "playlist"
            for prefix in ["meine", "my", "playlist", "die"]:
                if rest.lower().startswith(prefix):
                    rest = rest[len(prefix):].strip()
            # Entferne trailing commands
            for suffix in ["nach bpm", "by bpm", "nach energy", "by energy",
                           "langsam", "schnell", "chill", "hype",
                           "nur von", "filter", "only by"]:
                if suffix in rest.lower():
                    rest = rest[:rest.lower().find(suffix)].strip()
            if rest:
                return rest

    return None


def _extract_artist_filter(text: str) -> Optional[str]:
    """
    Extrahiert Artist-Filter aus natürlicher Sprache.
    z.B. "nur Execute" → "Execute"
    z.B. "filter artist Neuro" → "Neuro"
    """
    import re

    patterns = [
        r'nur\s+(?:von\s+)?["\']?(.+?)["\']?$',
        r'only\s+(?:songs?\s+)?(?:by\s+)?["\']?(.+?)["\']?$',
        r'filter\s+(?:artist\s+)?["\']?(.+?)["\']?$',
        r'von\s+["\']?(.+?)["\']?$',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None
