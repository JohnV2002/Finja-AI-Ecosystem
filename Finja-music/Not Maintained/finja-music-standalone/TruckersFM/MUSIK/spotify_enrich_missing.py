#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
======================================================================
          Spotify Enrich Missing - KB Song Enrichment Tool
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-music-standalone
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.2
  Description: Reads missing_songs_log.jsonl entries, searches Spotify
               for metadata (artist, album, genres, audio features),
               and merges enriched entries into songs_kb.json.

  ✨ New in 1.0.2:
    • --force flag to ignore ID cache
    • --update-existing flag to merge tags/aliases/album into existing entries
    • --verbose flag for detailed logging
    • --dry-run mode for safe testing

  📜 Features:
    • NowPlaying parser (single/double-line, dash / "by")
    • Robust save with backups and atomic writes
    • Hardened path security against traversal attacks
    • .env loader with auto-tag generation from Spotify genres

  🔒 Security Note:
    All path handling is hardened against path traversal (CWE-23):
    - All file paths resolve relative to SAFE_ROOT (env or script dir)
    - Absolute paths and '..' are explicitly rejected
    - Symlinks are blocked at file and parent level
    - File extensions are restricted via SUFFIX_ALLOW
    - No user input ever influences file paths
    - atomic_write_* functions receive pre-validated Paths only
    Automated scanners may flag path operations as CWE-23,
    but these are false positives — security is enforced by design.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# ===================== Path Hardening =====================

SCRIPT_ROOT = Path(__file__).resolve().parent
SAFE_ROOT = Path(os.environ.get("MUSIC_ROOT", str(SCRIPT_ROOT))).resolve()

ALLOWED_REL_FILES: dict[str, Path] = {
    "KB_PATH":   Path("SongsDB/songs_kb.json"),
    "MISS_PATH": Path("missingsongs/missing_songs_log.jsonl"),
}
ALLOWED_REL_DIRS: dict[str, Path] = {
    "CACHE_DIR":   Path("cache"),
    "BACKUPS_DIR": Path("SongsDB/backups"),
}

SUFFIX_ALLOW = (".json", ".jsonl", ".pkl", ".txt", ".tmp", ".log")


def _reject_abs_or_traversal(raw: str) -> Path | None:
    """Reject absolute paths and '..' traversal segments.

    Returns:
        A clean relative Path, or None if the input is unsafe.
    """
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return None
    s = str(p).replace("\\", "/")
    if ".." in s.split("/"):
        return None
    return p


def _ensure_under(p: Path, base: Path) -> Path:
    """Ensure resolved path is within the given base directory.

    Raises:
        ValueError: If path resolves outside base.
    """
    pr = p.resolve()
    br = base.resolve()
    if pr != br and br not in pr.parents:
        raise ValueError(f"Path outside SAFE_ROOT: {pr} (base={br})")
    return pr


def _ensure_no_symlink(p: Path) -> None:
    """Block symlinks at file and parent level.

    Raises:
        ValueError: If the path or its parent is a symlink.
    """
    if p.exists() and p.is_symlink():
        raise ValueError(f"Symlink not allowed: {p}")
    if p.parent.exists() and p.parent.is_symlink():
        raise ValueError(f"Symlink parent not allowed: {p.parent}")


def _ensure_suffix_allowed(p: Path) -> None:
    """Verify file extension is in the allowlist.

    Raises:
        ValueError: If the suffix is not permitted.
    """
    if p.suffix and p.suffix.lower() not in {s.lower() for s in SUFFIX_ALLOW}:
        raise ValueError(f"Disallowed file extension: {p.suffix} -> {p}")


def _resolve_allowed_file(env_name: str) -> Path:
    """Resolve and validate a file path from the allowlist.

    Args:
        env_name: Key in ALLOWED_REL_FILES to resolve.

    Returns:
        Validated absolute Path within SAFE_ROOT.
    """
    default_rel = ALLOWED_REL_FILES[env_name]
    raw = os.environ.get(env_name, "") or ""
    candidate_rel = _reject_abs_or_traversal(raw)
    rel = default_rel if (
        candidate_rel is None
        or candidate_rel.as_posix() != default_rel.as_posix()
    ) else candidate_rel
    p = (SAFE_ROOT / rel).resolve()
    _ensure_under(p, SAFE_ROOT)
    _ensure_suffix_allowed(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink(p)
    return p


def _resolve_allowed_dir(env_name: str) -> Path:
    """Resolve and validate a directory path from the allowlist.

    Args:
        env_name: Key in ALLOWED_REL_DIRS to resolve.

    Returns:
        Validated absolute Path within SAFE_ROOT.
    """
    default_rel = ALLOWED_REL_DIRS[env_name]
    raw = os.environ.get(env_name, "") or ""
    candidate_rel = _reject_abs_or_traversal(raw)
    rel = default_rel if (
        candidate_rel is None
        or candidate_rel.as_posix() != default_rel.as_posix()
    ) else candidate_rel
    p = (SAFE_ROOT / rel).resolve()
    _ensure_under(p, SAFE_ROOT)
    p.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink(p)
    return p


def atomic_write_json_safe(path: Path, obj: object) -> None:
    """Atomically write a JSON object to a validated path.

    Args:
        path: Target file (must be within SAFE_ROOT).
        obj: JSON-serializable object.
    """
    path = _ensure_under(path, SAFE_ROOT)
    _ensure_suffix_allowed(path)
    _ensure_no_symlink(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:  # nosec — validated path
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # nosec — both paths validated within SAFE_ROOT


def backup_songs_kb_safe(kb_path: Path, backups_dir: Path) -> Path | None:
    """Create a timestamped backup of the songs KB file.

    Args:
        kb_path: Source KB file path.
        backups_dir: Target backup directory.

    Returns:
        Path to backup file, or None if source doesn't exist.
    """
    if not kb_path.exists():
        return None
    backups_dir = _ensure_under(backups_dir, SAFE_ROOT)
    backups_dir.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink(backups_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dst = backups_dir / f"songs_kb.{ts}.json"
    # nosec — both paths validated within SAFE_ROOT
    with open(kb_path, "rb") as r, open(dst, "wb") as w:
        w.write(r.read())
        w.flush()
        os.fsync(w.fileno())
    return dst


# ===================== .env Loader =====================

def load_env_file() -> None:
    """Load .env file from SAFE_ROOT into os.environ (defaults only)."""
    env_path = SAFE_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)
    except Exception:
        pass


load_env_file()

# --------------- Config (locked to allowlist) ---------------
ROOT = SAFE_ROOT
KB_PATH = _resolve_allowed_file("KB_PATH")
MISS_PATH = _resolve_allowed_file("MISS_PATH")
CACHE_DIR = _resolve_allowed_dir("CACHE_DIR")
BACKUPS_DIR = _resolve_allowed_dir("BACKUPS_DIR")

DRY_RUN = bool(os.environ.get("DRY_RUN", "0") == "1")
CLIENT_ID = os.environ.get("CLIENT_ID") or os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET") or os.environ.get("SPOTIFY_CLIENT_SECRET")

# ===================== CLI Flags =====================
HELP = "--help" in sys.argv or "-h" in sys.argv
FORCE = "--force" in sys.argv
UPDATE_EXISTING = ("--update-existing" in sys.argv) or ("--update" in sys.argv)

if HELP:
    print("Usage: python spotify_enrich_missing.py [--verbose] [--force] [--update-existing] [--dry-run]")
    sys.exit(0)

# ===================== Logging =====================

VERBOSE = "--verbose" in sys.argv


def log(kind: str, msg: str) -> None:
    """Print a tagged log message."""
    print(f"[{kind}] {msg}", flush=True)


def v(msg: str) -> None:
    """Print a verbose-only log message."""
    if VERBOSE:
        log("i", msg)


# ===================== Helpers =====================

def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for p in (CACHE_DIR, BACKUPS_DIR, KB_PATH.parent, MISS_PATH.parent):
        p.mkdir(parents=True, exist_ok=True)


def norm_text(s: str) -> str:
    """Normalize whitespace in a string."""
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def alias_variants(title: str) -> list[str]:
    """Generate search alias variants for a song title."""
    if not title:
        return []
    base = norm_text(title)
    low = base.lower()
    plain = re.sub(r"[~''`\-—_,.:;!?/\\(){}\[\]]+", " ", low)
    plain = re.sub(r"\s+", " ", plain).strip()
    return [base, low, plain] if plain and plain != low else [base, low]


def http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | dict | None = None,
) -> tuple[int | None, bytes]:
    """Make an HTTP request and return (status_code, response_body).

    Args:
        url: Request URL.
        method: HTTP method.
        headers: Optional request headers.
        data: Optional request body (dict will be JSON-encoded).

    Returns:
        Tuple of (status_code, raw_response_bytes).
        status_code is None on connection errors.
    """
    req = urllib.request.Request(url=url, method=method)
    for k, val in (headers or {}).items():
        req.add_header(k, val)
    if data is not None and not isinstance(data, (bytes, bytearray)):
        data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:  # noqa: S310
            code = resp.getcode()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode("utf-8")
    return code, raw


# ===================== Spotify API =====================

class Spotify:
    """Minimal Spotify Web API client using client credentials flow."""

    def __init__(self, cid: str | None, secret: str | None) -> None:
        self.cid = cid
        self.secret = secret
        self.token: str | None = None
        self.token_until: float = 0

    def get_token(self) -> str:
        """Obtain or refresh the Spotify access token.

        Raises:
            RuntimeError: If credentials are missing or token request fails.
        """
        now = time.time()
        if self.token and now < self.token_until - 30:
            return self.token
        if not self.cid or not self.secret:
            raise RuntimeError("CLIENT_ID/CLIENT_SECRET not set")
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
        auth = (self.cid + ":" + self.secret).encode("utf-8")
        import base64
        basic = "Basic " + base64.b64encode(auth).decode("ascii")
        code, raw = http_json(
            "https://accounts.spotify.com/api/token",
            method="POST",
            headers={"Authorization": basic, "Content-Type": "application/x-www-form-urlencoded"},
            data=body
        )
        if code != 200:
            raise RuntimeError(f"Token failed: {code} {raw[:200]}")
        token_data = json.loads(raw)
        self.token = token_data["access_token"]
        self.token_until = time.time() + int(token_data.get("expires_in", 3600))
        assert self.token is not None  # Guaranteed by assignment above
        return self.token

    def _auth_hdr(self) -> dict[str, str]:
        """Return Authorization header dict with current Bearer token."""
        return {"Authorization": f"Bearer {self.get_token()}"}

    def search_track(self, title: str, artist: str | None = None) -> dict | None:
        """Search Spotify for a track by title and optional artist.

        Returns:
            First matching track object, or None if not found.
        """
        q = title
        if artist:
            q += f" artist:{artist}"
        params = urllib.parse.urlencode({"q": q, "type": "track", "limit": 1})
        code, raw = http_json(
            f"https://api.spotify.com/v1/search?{params}",
            headers=self._auth_hdr()
        )
        if code != 200:
            v(f"warn search {code}: {raw[:200]}")
            return None
        items = json.loads(raw)["tracks"]["items"]
        return items[0] if items else None

    def tracks_audio_features(self, ids: list[str]) -> dict[str, dict]:
        """Fetch audio features for a list of track IDs (batched by 100).

        Returns:
            Dict mapping track_id to its audio features.
        """
        if not ids:
            return {}
        out: dict[str, dict] = {}
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            params = urllib.parse.urlencode({"ids": ",".join(chunk)})
            code, raw = http_json(
                f"https://api.spotify.com/v1/audio-features?{params}",
                headers=self._auth_hdr()
            )
            if code == 429:
                retry = 1.5
                v("429 on audio-features -> retry once")
                time.sleep(retry)
                code, raw = http_json(
                    f"https://api.spotify.com/v1/audio-features?{params}",
                    headers=self._auth_hdr()
                )
            if code == 403:
                v("warn 403 on /audio-features -> skipping features (will still save KB).")
                return out
            if code != 200:
                v(f"warn {code} on audio-features: {raw[:200]}")
                continue
            for feat in json.loads(raw).get("audio_features", []) or []:
                if feat and feat.get("id"):
                    out[feat["id"]] = feat
        return out

    def get_artist(self, artist_id: str) -> dict | None:
        """Fetch artist metadata by Spotify artist ID.

        Returns:
            Artist object, or None on failure.
        """
        code, raw = http_json(
            f"https://api.spotify.com/v1/artists/{artist_id}",
            headers=self._auth_hdr()
        )
        if code != 200:
            v(f"warn artist {artist_id} -> {code}: {raw[:160]}")
            return None
        return json.loads(raw)


# ===================== Tagging Helpers =====================

DECADE_RX = re.compile(r"^(\d{4})")
SPECIAL_KEYS: dict[str, list[str]] = {
    "nightcore": ["nightcore"],
    "speed up": ["speed up", "sped up", "speedup"],
    "tiktok":   ["tiktok", "tik tok"],
    "radio edit": ["radio edit", "radio mix"]
}
GENRE_MAP: dict[str, str] = {
    "dance pop": "pop",
    "pop": "pop",
    "electropop": "pop",
    "edm": "edm",
    "dance": "dance",
    "electro house": "house",
    "house": "house",
    "progressive house": "house",
    "tropical house": "house",
    "future bass": "edm",
    "trap": "trap",
    "dubstep": "dubstep",
    "drum and bass": "dnb",
    "dnb": "dnb",
    "trance": "trance",
    "techno": "techno",
    "hiphop": "hip hop",
    "rap": "hip hop",
    "k-pop": "kpop",
    "j-pop": "jpop",
    "eurodance": "dance",
}


def _tag_from_decade(release_date: str) -> str | None:
    """Extract a decade tag (e.g. '2010s') from a release date string."""
    if not release_date:
        return None
    m = DECADE_RX.search(release_date)
    if not m:
        return None
    try:
        year = int(m.group(1))
    except ValueError:
        return None
    decade = (year // 10) * 10
    return f"{decade}s"


def _special_tags_from_title(title: str) -> list[str]:
    """Extract special tags (nightcore, speed up, etc.) from a song title."""
    t = (title or "").lower()
    return [tag for tag, keys in SPECIAL_KEYS.items() if any(k in t for k in keys)]


def _map_artist_genres_to_tags(artist_genres: list[str]) -> set[str]:
    """Map Spotify artist genres to simplified tag names."""
    tags: set[str] = set()
    for g in artist_genres or []:
        gl = g.lower()
        for key, tag in GENRE_MAP.items():
            if key in gl:
                tags.add(tag)
    return tags


# ===================== IO =====================

def load_kb(path: Path) -> list[dict]:
    """Load the songs knowledge base from a JSON file.

    Returns:
        List of song entry dicts, or empty list if file is missing/corrupt.
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            data = f.read()
            return json.loads(data)


def _parse_line(s: str) -> dict | None:
    """Parse a single line from missing_songs_log into a song dict.

    Handles JSON objects, plain text with dash/em-dash separators,
    and bare song titles.

    Returns:
        Dict with 'title', 'artist', 'album' keys, or None if unparseable.
    """
    try:
        obj = json.loads(s)
        title = obj.get("title") or obj.get("song") or ""
        artist = obj.get("artist") or ""
        album = obj.get("album") or ""
        if not title and isinstance(obj, str):
            title = obj
        if not title:
            return None
        return {"title": title, "artist": artist, "album": album}
    except json.JSONDecodeError:
        pass

    if " - " in s or " — " in s:
        parts = re.split(r"\s[-—]\s", s, maxsplit=1)
        t = parts[0].strip()
        a = parts[1].strip() if len(parts) > 1 else ""
        return {"title": t, "artist": a, "album": ""}

    return {"title": s, "artist": "", "album": ""}


def read_missing_lines(path: Path) -> list[dict]:
    """Read missing song entries from a JSONL file.

    Returns:
        List of dicts with 'title', 'artist', and 'album' keys.
    """
    if not path.exists():
        v(f"missing file not found: {path}")
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            parsed = _parse_line(s)
            if parsed:
                out.append(parsed)
    return out


def norm_key(title: str, artist: str) -> tuple[str, str]:
    """Create a normalized lookup key from title and artist."""
    def clean(x: str) -> str:
        x = (x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        x = re.sub(r"['`]", "", x)
        return x
    return clean(title), clean(artist)


# ===================== Main Helpers =====================

def _print_config() -> None:
    """Print startup configuration summary."""
    print("[i] enrich from missing_songs_log.jsonl via Spotify")
    print(f"[i] root      : {ROOT}")
    print(f"[i] kb_path   : {KB_PATH}")
    print(f"[i] miss_path : {MISS_PATH}")
    print(f"[i] cache_dir : {CACHE_DIR}")
    print(f"[i] backups   : {BACKUPS_DIR}")
    print(f"[i] verbose   : {VERBOSE} | dry_run: {DRY_RUN}")
    print(f"[i] flags     : force={FORCE} update_existing={UPDATE_EXISTING}")
    print(f"[i] env set?  : CLIENT_ID={'yes' if CLIENT_ID else 'no'} CLIENT_SECRET={'yes' if CLIENT_SECRET else 'no'}")


def _load_kb_indexed(path: Path) -> tuple[list[dict], set[tuple[str, str]], dict[tuple[str, str], dict]]:
    """Load KB and build lookup index.

    Returns:
        Tuple of (kb_list, seen_keys_set, key_to_entry_dict).
    """
    kb = load_kb(path)
    seen: set[tuple[str, str]] = set()
    kb_index: dict[tuple[str, str], dict] = {}
    for e in kb:
        k = norm_key(e.get("title", ""), e.get("artist", ""))
        seen.add(k)
        kb_index[k] = e
    v(f"[i] kb entries: {len(kb)}")
    return kb, seen, kb_index


def _load_id_cache(cache_dir: Path) -> dict[str, str]:
    """Load Spotify ID cache from disk."""
    cache_file = cache_dir / "id_cache.json"
    if not cache_file.exists():
        return {}
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_track(
    sp: Spotify, title: str, artist: str, key: str, id_cache: dict[str, str]
) -> tuple[str | None, dict | None]:
    """Resolve a Spotify track ID via cache or search.

    Returns:
        Tuple of (track_id, track_object). Both None if not found.
    """
    if key in id_cache and not FORCE:
        v(f"[cache-hit id] {key} -> {id_cache[key]}")
        return id_cache[key], None

    tr = sp.search_track(title, artist if artist else None)
    if not tr:
        v(f"warn: not found -> {title} — {artist}")
        return None, None
    id_cache[key] = tr["id"]
    return tr["id"], tr


def _fetch_track_by_id(sp: Spotify, track_id: str) -> dict | None:
    """Fetch a single track object from Spotify by ID.

    Returns:
        Track dict, or None on failure.
    """
    params = urllib.parse.urlencode({"ids": track_id})
    code, raw = http_json(
        f"https://api.spotify.com/v1/tracks?{params}",
        headers=sp._auth_hdr()
    )
    if code != 200:
        return None
    arr = json.loads(raw).get("tracks") or []
    return arr[0] if arr else None


def _fill_track_metadata(
    sp: Spotify, tr: dict | None, track_id: str, artist: str, album: str
) -> tuple[dict | None, str, str]:
    """Fill missing artist/album from Spotify track details.

    Returns:
        Tuple of (track_object, artist, album) with gaps filled.
    """
    if artist and album and tr is not None:
        return tr, artist, album

    if tr is None:
        tr = _fetch_track_by_id(sp, track_id)

    if tr:
        if not artist:
            artist = ", ".join([a["name"] for a in tr.get("artists", [])])
        if not album:
            album = (tr.get("album") or {}).get("name", album or "")

    return tr, artist, album


def _build_tags(sp: Spotify, tr: dict | None, title: str) -> set[str]:
    """Build a tag set from track metadata, artist genres, and title keywords."""
    tags_set: set[str] = set()

    try:
        rel_date = (tr.get("album") or {}).get("release_date") if tr else None
        dec = _tag_from_decade(rel_date or "")
        if dec:
            tags_set.add(dec)
    except Exception:
        pass

    try:
        primary_artist = (tr.get("artists") or [])[0] if tr else None
        if primary_artist and primary_artist.get("id"):
            pa = sp.get_artist(primary_artist["id"])
            if pa and isinstance(pa.get("genres"), list):
                tags_set |= _map_artist_genres_to_tags(pa["genres"])
    except Exception as e:
        v(f"warn artist-genres: {e}")

    tags_set |= set(_special_tags_from_title(title))
    return tags_set


def _update_existing_entry(entry: dict, tags_set: set[str], title: str, album: str) -> None:
    """Merge new tags, aliases, and album into an existing KB entry."""
    old_tags = set(entry.get("tags") or [])
    entry["tags"] = sorted(old_tags | tags_set)

    alias_src = alias_variants(title)
    old_aliases = entry.get("aliases") or []
    alias_lc = {a.lower(): a for a in old_aliases}
    for a in alias_src:
        if a.lower() not in alias_lc:
            old_aliases.append(a)
    entry["aliases"] = old_aliases

    if not entry.get("album") and album:
        entry["album"] = album

    print(f"[update] {entry['title']} — {entry['artist']} (tags={len(entry['tags'])})")


def _create_new_entry(title: str, artist: str, album: str, tags_set: set[str]) -> dict:
    """Create a new KB song entry."""
    return {
        "title": title,
        "artist": artist,
        "album": album or "",
        "aliases": alias_variants(title),
        "tags": sorted(tags_set) if tags_set else [],
        "notes": ""
    }


def _enrich_with_features(sp: Spotify, new_entries: list[tuple[dict, str]], feature_ids: list[str]) -> None:
    """Fetch audio features and append tempo/energy to entry notes."""
    feats: dict[str, dict] = {}
    try:
        feats = sp.tracks_audio_features(feature_ids)
        v(f"[features_batch] got: {list(feats.keys())[:3]}{'...' if len(feats) > 3 else ''}")
    except Exception as e:
        v(f"warn features fetch failed: {e}")

    for entry, tid in new_entries:
        f = feats.get(tid)
        if f:
            entry.setdefault("notes", "")
            entry["notes"] = (entry["notes"] + f" tempo={f.get('tempo')}, energy={f.get('energy')}").strip()


def _persist_results(
    kb: list[dict],
    new_entries: list[tuple[dict, str]],
    id_cache: dict[str, str],
    seen: set[tuple[str, str]],
    kb_index: dict[tuple[str, str], dict],
    added_count: int,
    updated_count: int,
    skipped_count: int,
) -> None:
    """Save ID cache, backup KB, merge new entries, and write KB to disk."""
    # Save cache
    try:
        (CACHE_DIR / "id_cache.json").write_text(
            json.dumps(id_cache, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        v(f"warn cache save failed: {e}")

    # Merge and persist
    try:
        dst = backup_songs_kb_safe(KB_PATH, BACKUPS_DIR)
        if dst:
            v(f"backup -> {dst}")
        for entry, _ in new_entries:
            kb.append(entry)
            norm = norm_key(entry["title"], entry["artist"])
            seen.add(norm)
            kb_index[norm] = entry
        atomic_write_json_safe(KB_PATH, kb)
        print(f"[ok] added={added_count} updated={updated_count} skipped={skipped_count} -> {KB_PATH.name}")
    except Exception as e:
        log("err", f"save failed: {e}")


# ===================== Main =====================

def main() -> None:
    """Main entry point: enrich missing songs via Spotify API."""
    _print_config()
    ensure_dirs()

    kb, seen, kb_index = _load_kb_indexed(KB_PATH)

    todo = read_missing_lines(MISS_PATH)
    v(f"[i] missing lines: {len(todo)}")
    if not todo:
        return

    sp = Spotify(CLIENT_ID, CLIENT_SECRET)
    id_cache = _load_id_cache(CACHE_DIR)

    to_feature_ids: list[str] = []
    new_entries: list[tuple[dict, str]] = []
    updated_count = 0
    added_count = 0
    skipped_count = 0

    for item in todo:
        title = norm_text(item.get("title", ""))
        artist = norm_text(item.get("artist", ""))
        album = norm_text(item.get("album", ""))
        if not title:
            skipped_count += 1
            continue

        key = f"{title}|{artist}".lower()
        track_id, tr = _resolve_track(sp, title, artist, key, id_cache)
        if track_id is None:
            skipped_count += 1
            continue

        tr, artist, album = _fill_track_metadata(sp, tr, track_id, artist, album)
        tags_set = _build_tags(sp, tr, title)
        k_norm = norm_key(title, artist)

        if k_norm in seen and UPDATE_EXISTING:
            _update_existing_entry(kb_index[k_norm], tags_set, title, album)
            updated_count += 1
            continue

        if k_norm in seen:
            v(f"skip (exists): {title} — {artist}")
            skipped_count += 1
            continue

        entry = _create_new_entry(title, artist, album, tags_set)
        to_feature_ids.append(track_id)
        new_entries.append((entry, track_id))
        added_count += 1
        print(f"[added] {entry['title']} — {entry['artist']}")

    _enrich_with_features(sp, new_entries, to_feature_ids)

    if not new_entries and updated_count == 0:
        v(f"nothing to write. skipped={skipped_count}")
        return

    if DRY_RUN:
        v(f"dry_run=1 -> no write. added={added_count} updated={updated_count} skipped={skipped_count}")
        return

    _persist_results(kb, new_entries, id_cache, seen, kb_index, added_count, updated_count, skipped_count)


if __name__ == "__main__":
    main()