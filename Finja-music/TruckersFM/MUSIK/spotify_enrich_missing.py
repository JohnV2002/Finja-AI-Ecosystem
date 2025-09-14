# -*- coding: utf-8 -*-

"""
======================================================================
            Finja's Brain & Knowledge Core - TruckersFM
======================================================================

  Project: Twitch Interactivity Suite
  Version: 1.0.0 (TruckersFM Modul)
  Author:  JohnV2002 (J. Apps / Sodakiller1)
  License: MIT License (c) 2025 J. Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • NowPlaying Parser (ein-/zweizeilig, Dash / „by“)
  • robust save + backups, hardened paths, .env + auto-tags)
  • hardened paths
  • .env + auto-tags

----------------------------------------------------------------------
 Neu in v1.0.0:
 ---------------------------------------------------------------------
+ --force (ignore ID cache)
+ --update-existing (merge tags/aliases/album into existing entries)
+ python spotify_enrich_missing.py --verbose

# ======================================================================
# SECURITY NOTE: ALL PATH HANDLING IS HARDENED AGAINST PATH TRAVERSAL
# ======================================================================
# This script uses a strict allowlist approach:
#   - All file paths are resolved relative to SAFE_ROOT (environment or script dir)
#   - Absolute paths and '..' are explicitly rejected by _reject_abs_or_traversal()
#   - Symlinks are blocked with _ensure_no_symlink()
#   - File extensions are restricted via SUFFIX_ALLOW
#   - No user input is ever used to construct file paths
#   - atomic_write_* functions receive pre-validated Paths only
#
# Automated scanners (Snyk, CodeQL) may flag path operations as CWE-23,
# but these are FALSE POSITIVES. Security is enforced at design level.
# ======================================================================

======================================================================
"""

import os, sys, json, time, re
from pathlib import Path
from datetime import datetime, timezone
import urllib.request, urllib.parse, urllib.error  # for HTTPError

# ===================== Path Hardening =====================

SCRIPT_ROOT = Path(__file__).resolve().parent
SAFE_ROOT   = Path(os.environ.get("MUSIC_ROOT", str(SCRIPT_ROOT))).resolve()

ALLOWED_REL_FILES = {
    "KB_PATH":   Path("SongsDB/songs_kb.json"),
    "MISS_PATH": Path("missingsongs/missing_songs_log.jsonl"),
}
ALLOWED_REL_DIRS = {
    "CACHE_DIR":   Path("cache"),
    "BACKUPS_DIR": Path("SongsDB/backups"),
}

SUFFIX_ALLOW = (".json", ".jsonl", ".pkl", ".txt", ".tmp", ".log")

def _reject_abs_or_traversal(raw: str) -> Path | None:
    if not raw: return None
    p = Path(raw)
    if p.is_absolute():
        return None
    s = str(p).replace("\\", "/")
    if ".." in s.split("/"):
        return None
    return p

def _ensure_under(p: Path, base: Path) -> Path:
    pr = p.resolve()
    br = base.resolve()
    if pr != br and br not in pr.parents:
        raise ValueError(f"Pfad außerhalb von SAFE_ROOT: {pr} (base={br})")
    return pr

def _ensure_no_symlink(p: Path) -> None:
    if p.exists() and p.is_symlink():
        raise ValueError(f"Symlink nicht erlaubt: {p}")
    if p.parent.exists() and p.parent.is_symlink():
        raise ValueError(f"Symlink-Parent nicht erlaubt: {p.parent}")

def _ensure_suffix_allowed(p: Path) -> None:
    if p.suffix and p.suffix.lower() not in {s.lower() for s in SUFFIX_ALLOW}:
        raise ValueError(f"Unerlaubte Dateiendung: {p.suffix} -> {p}")

def _resolve_allowed_file(env_name: str) -> Path:
    default_rel = ALLOWED_REL_FILES[env_name]
    raw = os.environ.get(env_name, "") or ""
    candidate_rel = _reject_abs_or_traversal(raw)
    rel = default_rel if (candidate_rel is None or candidate_rel.as_posix() != default_rel.as_posix()) else candidate_rel
    p = (SAFE_ROOT / rel).resolve()
    _ensure_under(p, SAFE_ROOT)
    _ensure_suffix_allowed(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink(p)
    return p

def _resolve_allowed_dir(env_name: str) -> Path:
    default_rel = ALLOWED_REL_DIRS[env_name]
    raw = os.environ.get(env_name, "") or ""
    candidate_rel = _reject_abs_or_traversal(raw)
    rel = default_rel if (candidate_rel is None or candidate_rel.as_posix() != default_rel.as_posix()) else candidate_rel
    p = (SAFE_ROOT / rel).resolve()
    _ensure_under(p, SAFE_ROOT)
    p.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink(p)
    return p

def atomic_write_json_safe(path: Path, obj) -> None:
    path = _ensure_under(path, SAFE_ROOT)
    _ensure_suffix_allowed(path)
    _ensure_no_symlink(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def backup_songs_kb_safe(kb_path: Path, backups_dir: Path) -> Path | None:
    if not kb_path.exists():
        return None
    backups_dir = _ensure_under(backups_dir, SAFE_ROOT)
    backups_dir.mkdir(parents=True, exist_ok=True)
    _ensure_no_symlink(backups_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # UTC-aware
    dst = backups_dir / f"songs_kb.{ts}.json"
    with open(kb_path, "rb") as r, open(dst, "wb") as w:
        w.write(r.read())
        w.flush()
        os.fsync(w.fileno())
    return dst

# ===================== .env Loader =====================

def load_env_file():
    env_path = (SAFE_ROOT / ".env")
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
ROOT        = SAFE_ROOT
KB_PATH     = _resolve_allowed_file("KB_PATH")
MISS_PATH   = _resolve_allowed_file("MISS_PATH")
CACHE_DIR   = _resolve_allowed_dir("CACHE_DIR")
BACKUPS_DIR = _resolve_allowed_dir("BACKUPS_DIR")

DRY_RUN = bool(os.environ.get("DRY_RUN", "0") == "1")
CLIENT_ID     = os.environ.get("CLIENT_ID") or os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET") or os.environ.get("SPOTIFY_CLIENT_SECRET")

# ===================== CLI Flags =====================
HELP = "--help" in sys.argv or "-h" in sys.argv
FORCE = "--force" in sys.argv
UPDATE_EXISTING = ("--update-existing" in sys.argv) or ("--update" in sys.argv)

if HELP:
    print("Usage: python spotify_enrich_missing.py [--verbose] [--force] [--update-existing] [--dry-run]")
    sys.exit(0)

# ===================== Logging =====================

VERBOSE  = "--verbose" in sys.argv

def log(kind, msg):
    print(f"[{kind}] {msg}", flush=True)

def v(msg):
    if VERBOSE: log("i", msg)

# ===================== Helpers =====================

def ensure_dirs():
    for p in (CACHE_DIR, BACKUPS_DIR, KB_PATH.parent, MISS_PATH.parent):
        p.mkdir(parents=True, exist_ok=True)

def norm_text(s: str) -> str:
    if not s: return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

def alias_variants(title: str) -> list:
    if not title: return []
    base = norm_text(title)
    low  = base.lower()
    plain = re.sub(r"[~’'`´\-–—_,.:;!?/\\(){}\[\]]+", " ", low)
    plain = re.sub(r"\s+", " ", plain).strip()
    return [base, low, plain] if plain and plain != low else [base, low]

def http_json(url, method="GET", headers=None, data=None, expect=200):
    req = urllib.request.Request(url=url, method=method)
    for k,v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None and not isinstance(data, (bytes, bytearray)):
        data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            code = resp.getcode()
            raw  = resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode("utf-8")
    return code, raw

# ===================== Spotify API =====================

class Spotify:
    def __init__(self, cid, secret):
        self.cid = cid
        self.secret = secret
        self.token = None
        self.token_until = 0

    def get_token(self):
        now = time.time()
        if self.token and now < self.token_until - 30:
            return self.token
        if not self.cid or not self.secret:
            raise RuntimeError("CLIENT_ID/CLIENT_SECRET not set")
        body = urllib.parse.urlencode({"grant_type":"client_credentials"}).encode("utf-8")
        auth = (self.cid + ":" + self.secret).encode("utf-8")
        basic = "Basic " + __import__("base64").b64encode(auth).decode("ascii")
        code, raw = http_json(
            "https://accounts.spotify.com/api/token",
            method="POST",
            headers={"Authorization": basic, "Content-Type":"application/x-www-form-urlencoded"},
            data=body
        )
        if code != 200:
            raise RuntimeError(f"Token failed: {code} {raw[:200]}")
        data = json.loads(raw)
        self.token = data["access_token"]
        self.token_until = time.time() + int(data.get("expires_in", 3600))
        return self.token

    def _auth_hdr(self):
        return {"Authorization": f"Bearer {self.get_token()}"}

    def search_track(self, title, artist=None):
        q = title
        if artist: q += f" artist:{artist}"
        params = urllib.parse.urlencode({"q": q, "type":"track", "limit": 1})
        code, raw = http_json(f"https://api.spotify.com/v1/search?{params}", headers=self._auth_hdr())
        if code != 200:
            v(f"warn search {code}: {raw[:200]}")
            return None
        items = json.loads(raw)["tracks"]["items"]
        return items[0] if items else None

    def tracks_audio_features(self, ids):
        if not ids: return {}
        out = {}
        for i in range(0, len(ids), 100):
            chunk = ids[i:i+100]
            params = urllib.parse.urlencode({"ids": ",".join(chunk)})
            code, raw = http_json(f"https://api.spotify.com/v1/audio-features?{params}", headers=self._auth_hdr())
            if code == 429:
                retry = 1.5
                v("429 on audio-features -> retry once")
                time.sleep(retry)
                code, raw = http_json(f"https://api.spotify.com/v1/audio-features?{params}", headers=self._auth_hdr())
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

    def get_artist(self, artist_id: str):
        code, raw = http_json(f"https://api.spotify.com/v1/artists/{artist_id}", headers=self._auth_hdr())
        if code != 200:
            v(f"warn artist {artist_id} -> {code}: {raw[:160]}")
            return None
        return json.loads(raw)

# ===================== Tagging Helpers =====================

DECADE_RX = re.compile(r"^(\d{4})")
SPECIAL_KEYS = {
    "nightcore": ["nightcore"],
    "speed up": ["speed up", "sped up", "speedup"],
    "tiktok":   ["tiktok", "tik tok"],
    "radio edit": ["radio edit", "radio mix"]
}
GENRE_MAP = {
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
    "hip hop": "hip hop",
    "rap": "hip hop",
    "k-pop": "kpop",
    "j-pop": "jpop",
    "eurodance": "dance",
}

def _tag_from_decade(release_date: str) -> str | None:
    if not release_date:
        return None
    m = DECADE_RX.search(release_date)
    if not m:
        return None
    try:
        year = int(m.group(1))
    except:
        return None
    decade = (year // 10) * 10
    return f"{decade}s"

def _special_tags_from_title(title: str) -> list[str]:
    t = (title or "").lower()
    return [tag for tag, keys in SPECIAL_KEYS.items() if any(k in t for k in keys)]

def _map_artist_genres_to_tags(artist_genres: list[str]) -> set[str]:
    tags = set()
    for g in artist_genres or []:
        gl = g.lower()
        for key, tag in GENRE_MAP.items():
            if key in gl:
                tags.add(tag)
    return tags

# ===================== IO =====================

def load_kb(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            data = f.read()
            return json.loads(data)

def read_missing_lines(path: Path):
    if not path.exists():
        v(f"missing file not found: {path}")
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s: continue
            try:
                obj = json.loads(s)
                title = obj.get("title") or obj.get("song") or ""
                artist = obj.get("artist") or ""
                album = obj.get("album") or ""
                if not title and isinstance(obj, str):
                    title = obj
                if not title:
                    continue
                out.append({"title": title, "artist": artist, "album": album})
            except json.JSONDecodeError:
                if " - " in s or " — " in s:
                    parts = re.split(r"\s[-—]\s", s, maxsplit=1)
                    t = parts[0].strip()
                    a = parts[1].strip() if len(parts) > 1 else ""
                    out.append({"title": t, "artist": a, "album": ""})
                else:
                    out.append({"title": s, "artist": "", "album": ""})
    return out

def norm_key(title, artist):
    def clean(x):
        x = (x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        x = re.sub(r"[’'`´]", "", x)
        return x
    return clean(title), clean(artist)

# ===================== Main =====================

def main():
    print("[i] enrich from missing_songs_log.jsonl via Spotify")
    print(f"[i] root      : {ROOT}")
    print(f"[i] kb_path   : {KB_PATH}")
    print(f"[i] miss_path : {MISS_PATH}")
    print(f"[i] cache_dir : {CACHE_DIR}")
    print(f"[i] backups   : {BACKUPS_DIR}")
    print(f"[i] verbose   : {VERBOSE} | dry_run: {DRY_RUN}")
    print(f"[i] flags     : force={FORCE} update_existing={UPDATE_EXISTING}")
    print(f"[i] env set?  : CLIENT_ID={'yes' if CLIENT_ID else 'no'} CLIENT_SECRET={'yes' if CLIENT_SECRET else 'no'}")

    ensure_dirs()

    kb = load_kb(KB_PATH)
    seen = set()
    kb_index = {}  # (title,artist)->entry
    for e in kb:
        k = norm_key(e.get("title",""), e.get("artist",""))
        seen.add(k)
        kb_index[k] = e
    v(f"[i] kb entries: {len(kb)}")

    todo = read_missing_lines(MISS_PATH)
    v(f"[i] missing lines: {len(todo)}")
    if not todo:
        return

    sp = Spotify(CLIENT_ID, CLIENT_SECRET)
    cache_file = (CACHE_DIR / "id_cache.json")
    id_cache = {}
    if cache_file.exists():
        try:
            id_cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            id_cache = {}

    to_feature_ids = []
    new_entries = []
    updated_count = 0
    added_count = 0
    skipped_count = 0

    for item in todo:
        title = norm_text(item.get("title",""))
        artist= norm_text(item.get("artist",""))
        album = norm_text(item.get("album",""))
        if not title:
            skipped_count += 1
            continue

        key = f"{title}|{artist}".lower()

        # Resolve track_id (respect --force)
        track_id = None
        if key in id_cache and not FORCE:
            track_id = id_cache[key]
            v(f"[cache-hit id] {key} -> {track_id}")

        tr = None
        if track_id is None:
            tr = sp.search_track(title, artist if artist else None)
            if not tr:
                v(f"warn: not found -> {title} — {artist}")
                skipped_count += 1
                continue
            track_id = tr["id"]
            id_cache[key] = track_id

        # Fill missing artist/album from track detail if needed (or if we forced a search)
        if (not artist or not album) or tr is None:
            if tr is None:
                # fetch track object via /tracks?ids=
                params = urllib.parse.urlencode({"ids": track_id})
                code, raw = http_json(f"https://api.spotify.com/v1/tracks?{params}", headers=sp._auth_hdr())
                if code == 200:
                    arr = json.loads(raw).get("tracks") or []
                    tr = arr[0] if arr else None
            if tr:
                if not artist:
                    artist = ", ".join([a["name"] for a in tr.get("artists", [])])
                if not album:
                    album = (tr.get("album") or {}).get("name", album or "")

        # Build tag set (we’ll also use it for updates)
        tags_set = set()
        try:
            rel_date = (tr.get("album") or {}).get("release_date") if tr else None
            dec = _tag_from_decade(rel_date or "")
            if dec: tags_set.add(dec)
        except Exception:
            pass
        try:
            primary_artist = (tr.get("artists") or [])[0] if tr else None
            pa = sp.get_artist(primary_artist["id"]) if (primary_artist and primary_artist.get("id")) else None
            if pa and isinstance(pa.get("genres"), list):
                tags_set |= _map_artist_genres_to_tags(pa["genres"])
        except Exception as e:
            v(f"warn artist-genres: {e}")
        tags_set |= set(_special_tags_from_title(title))

        k_norm = norm_key(title, artist)
        exists = k_norm in seen

        if exists and UPDATE_EXISTING:
            entry = kb_index[k_norm]
            # merge tags
            old_tags = set(entry.get("tags") or [])
            new_tags = sorted((old_tags | tags_set))
            # merge aliases
            alias_src = alias_variants(title)
            old_aliases = entry.get("aliases") or []
            alias_lc = {a.lower(): a for a in old_aliases}
            for a in alias_src:
                if a.lower() not in alias_lc:
                    old_aliases.append(a)
            # album fill-in if empty
            if not entry.get("album") and album:
                entry["album"] = album
            entry["tags"] = new_tags
            entry["aliases"] = old_aliases
            updated_count += 1
            print(f"[update] {entry['title']} — {entry['artist']} (tags={len(new_tags)})")
            # (we do not append features for updates; optional if wanted later)
            continue

        if exists and not UPDATE_EXISTING:
            v(f"skip (exists): {title} — {artist}")
            skipped_count += 1
            continue

        # New entry
        entry = {
            "title": title,
            "artist": artist,
            "album": album or "",
            "aliases": alias_variants(title),
            "tags": sorted(tags_set) if tags_set else [],
            "notes": ""
        }
        to_feature_ids.append(track_id)
        new_entries.append((entry, track_id))
        added_count += 1
        print(f"[added] {entry['title']} — {entry['artist']}")

    # Optional: Audio-Features batch
    feats = {}
    try:
        feats = sp.tracks_audio_features(to_feature_ids)
        v(f"[features_batch] got: {list(feats.keys())[:3]}{'...' if len(feats)>3 else ''}")
    except Exception as e:
        v(f"warn features fetch failed: {e}")

    for entry, tid in new_entries:
        f = feats.get(tid)
        if f:
            entry.setdefault("notes", "")
            entry["notes"] = (entry["notes"] + f" tempo={f.get('tempo')}, energy={f.get('energy')}").strip()

    if not new_entries and updated_count == 0:
        v(f"nothing to write. skipped={skipped_count}")
        return

    if DRY_RUN:
        v(f"dry_run=1 -> no write. added={added_count} updated={updated_count} skipped={skipped_count}")
        return

    # Save cache
    try:
        (CACHE_DIR / "id_cache.json").write_text(json.dumps(id_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        v(f"warn cache save failed: {e}")

    # Merge and persist
    try:
        dst = backup_songs_kb_safe(KB_PATH, BACKUPS_DIR)
        if dst: v(f"backup -> {dst}")
        for entry, _ in new_entries:
            kb.append(entry)
            key = norm_key(entry["title"], entry["artist"])
            seen.add(key)
            kb_index[key] = entry
        atomic_write_json_safe(KB_PATH, kb)
        print(f"[ok] added={added_count} updated={updated_count} skipped={skipped_count} -> {KB_PATH.name}")
    except Exception as e:
        log("err", f"save failed: {e}")

if __name__ == "__main__":
    main()
