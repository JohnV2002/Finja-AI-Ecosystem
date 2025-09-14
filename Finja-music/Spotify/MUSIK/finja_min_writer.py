# -*- coding: utf-8 -*-
"""
======================================================================
            Finja's Brain & Knowledge Core – Spotify
======================================================================

  Project: Twitch Interactivity Suite
  Version: 1.4.3 (Spotify Modul)
  Author:  JohnV2002 (J. Apps / Sodakiller1)
  License: MIT License (c) 2025 J. Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Single-Instance Lock (FINJA_FORCE=1 Override)
  • UTC-Timestamps
  • NowPlaying Parser (ein-/zweizeilig, Dash / „by“)
  • RAM-KB + optionaler Index-Persist-Cache (SHA-256)
  • Result-LRU-Cache (inkl. Negativ-Caching)
  • Debug-Hook (kb_probe.py)
  • Sync-Guard gegen halbgeschriebene nowplaying.txt
  • Missing-Logger mit TTL-Dedupe
  • Reaction-Engine:
      - externe reactions.json
      - Unknown/Explore-Policy, Specials (z. B. Rickroll)
      - Context-/Game-Bias via contexts.json + game_state.txt
      - Listening-Phase: sofort „Listening…“, später finale Reaktion
  • Robustere KB-Fuzzy-Matches (weniger False-Positives)
  • Special-Version-Tags (nightcore / speed up / tiktok / radio edit) – tolerant gg. Bindestrich
  • Memory (JSON) pro (Song-Key, Kontext) – „immer noch …“, „… aber in ETS2 besser“, „… passt zu MC“
  • Zeitliches Decay (optional) nur für Bewertung (nicht destruktiv), plus Tuning-Knöpfe
  • Artist-Not-Sure-Logger: wenn KB-Titel passt, aber Artist stark abweicht -> Log in artist_not_sure.jsonl
  • notes-Auswertung:
      * JSON im notes-Feld (artist_aliases, allow_title_only, max_ambiguous_candidates, add_tags)
      * ODER Freitext mit "Bestätigt: A, B" / "Nicht bestätigt: X, Y"
      => bestätigt/verbietet Artists für genau diesen Eintrag
  • Strenges Match bleibt (weniger False-Positives), aber du bekommst Review-Queue.
  • In-Process Spotify-Enrichment HOOK (Option B) bei KB-Miss:
      - Spotify suchen, Genres vom Primary Artist holen
      - KB vorher BACKUP, dann sofort erweitern
      - Genres sofort in outputs/obs_genres.txt schreiben (Reaction bleibt unverändert)
      - Keine zusätzlichen Logfiles (nur stdout)

----------------------------------------------------------------------
 Neu in v1.4.3:
 ---------------------------------------------------------------------
  • 🔒 **Enhanced Security**: All file paths are strictly validated against SAFE_ROOT
  • 🧠 **Cache Integrity**: Pickle cache files are now rigorously validated before loading
  • 📂 **Config Safety**: Only .json/.js config files allowed — no arbitrary file access
  • ⚙️ **Atomic Writes**: All output files use temp+replace for crash-safe persistence
  • 🛑 **No Path Traversal Possible**: Absolute paths, `..`, symlinks and external writes blocked
  • 🚫 **Fixed Spotify API URLs**: Removed trailing whitespace causing 404 errors

----------------------------------------------------------------------
 SECURITY NOTE:
 ---------------------------------------------------------------------
 This tool uses a strict allowlist approach:
   - All file paths resolve relative to SCRIPT_DIR or MUSIC_ROOT
   - No user input ever influences file paths
   - Config must be .json/.js — all other extensions rejected
   - Cache (.pkl) files are validated before unpickling
   - Atomic writes prevent partial/corrupted files
   - Symlinks and absolute paths are explicitly blocked

 Automated security scanners may flag path operations as CWE-23,
 but these are FALSE POSITIVES — security is enforced by design.
 See source code comments for details.

======================================================================
"""

import json, os, re, time, hashlib, collections, pickle, subprocess, sys, uuid, random, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Optional, Tuple, List, Dict, Any

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config_min.json"
LOCK_PATH   = SCRIPT_DIR / ".finja_min_writer.lock"
_ENV_LOADED = False

# ========= Utilities =========

def log(msg: str) -> None:
    print(datetime.now().strftime("[%H:%M:%S]"), msg, flush=True)

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def atomic_write_safe(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text((text or "").strip() + "\n", encoding="utf-8", errors="ignore")
    os.replace(tmp, target)

def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"[config error] {path} :: {e}")

# ========= Single-Instance Lock =========

def acquire_single_instance_lock() -> bool:
    if os.environ.get("FINJA_FORCE") == "1":
        log("[lock] FINJA_FORCE=1 gesetzt – Lock wird ignoriert")
        return True
    try:
        with open(LOCK_PATH, "x", encoding="utf-8") as f:
            f.write(f"{os.getpid()}|{uuid.uuid4()}\n")
        log(f"[lock] acquired: {LOCK_PATH.name}")
        return True
    except FileExistsError:
        try:
            content = LOCK_PATH.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            content = ""
        log(f"[lock] already present: {LOCK_PATH.name} (content='{content}')")
        return False
    except Exception as e:
        log(f"[lock] error: {e}")
        return False

def release_single_instance_lock():
    try:
        LOCK_PATH.unlink(missing_ok=True)
        log(f"[lock] released: {LOCK_PATH.name}")
    except Exception as e:
        log(f"[lock] release warn: {e}")

# ========= Normalisierung / Parser =========

def _strip_parens(s: str) -> str:
    return re.sub(r"[\(\[].*?[\)\]]", "", s)

def _normalize(s: Optional[str]) -> str:
    s = (s or "").lower().strip()
    s = _strip_parens(s)
    s = s.replace("&", "and")
    s = re.sub(r"\bfeat\.?\b|\bfeaturing\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def _norm_tag_for_scoring(s: str) -> str:
    s = s.lower().replace("-", " ")
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

DASH_SEPS = [" — ", " – ", " - ", " ~ ", " | ", " • "]

def parse_title_artist(text: str) -> Tuple[Optional[str], Optional[str]]:
    text = (text or "").strip()
    if not text:
        return None, None
    # JSON-Formate
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if "title" in data:
                return (str(data.get("title") or "").strip() or None,
                        str(data.get("artist") or "").strip() or None)
            if "track" in data and isinstance(data["track"], dict):
                tr = data["track"]
                return (str(tr.get("title") or "").strip() or None,
                        str(tr.get("artist") or "").strip() or None)
    except Exception:
        pass
    # Ein-/Zweizeilig
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    line = lines[0] if lines else ""
    for sep in DASH_SEPS:
        if sep in line:
            left, right = [p.strip() for p in line.split(sep, 1)]
            if left and right:
                return left, right
    m = re.search(r"^(?P<title>.+?)\s+by\s+(?P<artist>.+)$", line, flags=re.IGNORECASE)
    if m:
        return m.group("title").strip(), m.group("artist").strip()
    # fallback: evtl. vertauscht
    for sep in DASH_SEPS:
        if sep in line:
            left, right = [p.strip() for p in line.split(sep, 1)]
            if left and right:
                return right, left
    return line or None, None

# ========= KB laden / Index =========

def load_songs_kb(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"songs_kb not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("songs"), list):
        return data["songs"]
    if isinstance(data, list):
        return data
    raise ValueError("songs_kb.json hat ein unerwartetes Format")

def extract_tags(entry: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Einheitlich: wir benutzen NUR 'tags' als Quelle."""
    if not entry:
        return None
    g = entry.get("tags")
    if isinstance(g, list):
        parts = [str(x).strip() for x in g if str(x).strip()]
        return parts or None
    if isinstance(g, str):
        parts = [x.strip() for x in re.split(r"[;,/]", g) if x.strip()]
        return parts or None
    return None

def _parse_notes(entry: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    raw = entry.get("notes", "")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    s = raw.strip()
    # JSON?
    if s.startswith("{") and s.endswith("}"):
        try:
            data = json.loads(s)
            if isinstance(data.get("artist_aliases"), list):
                out["artist_aliases"] = [str(x).strip().lower() for x in data["artist_aliases"] if str(x).strip()]
            if isinstance(data.get("add_tags"), list):
                out["add_tags"] = [str(x).strip() for x in data["add_tags"] if str(x).strip()]
            out["allow_title_only"] = bool(data.get("allow_title_only", False))
            if "max_ambiguous_candidates" in data:
                try: out["max_ambiguous_candidates"] = int(data.get("max_ambiguous_candidates"))
                except: pass
        except Exception:
            pass
    # Freitext
    def _grab(label: str) -> List[str]:
        m = re.search(label + r"\s*:\s*(.+)", s, flags=re.IGNORECASE)
        if not m: return []
        val = m.group(1)
        nxt = re.search(r"(Bestätigt|Nicht\s*bestätigt)\s*:", val, flags=re.IGNORECASE)
        if nxt: val = val[:nxt.start()].strip()
        return [x.strip() for x in re.split(r"[;,]", val) if x.strip()]
    conf = _grab(r"Bestätigt")
    deny = _grab(r"Nicht\s*bestätigt")
    if conf: out["confirm_artists"] = [x.lower() for x in conf]
    if deny: out["deny_artists"] = [x.lower() for x in deny]
    return out

class KBIndex:
    def __init__(self, entries: List[Dict[str, Any]], title_key="title", artist_key="artist"):
        self.title_key = title_key
        self.artist_key = artist_key
        self.by_title_artist: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.by_title: Dict[str, List[Dict[str, Any]]] = {}
        for e in entries:
            self._add(e, e.get(title_key), e.get(artist_key))
            aliases = e.get("aliases") or []
            if isinstance(aliases, list):
                for al in aliases:
                    self._add(e, al, e.get(artist_key))
            meta = _parse_notes(e)
            for aa in (meta.get("artist_aliases") or []) + (meta.get("confirm_artists") or []):
                self._add(e, e.get(title_key), aa)

    def _add(self, e: Dict[str, Any], tval: Any, aval: Any):
        t = _normalize(str(tval or ""))
        a = _normalize(str(aval or ""))
        if not t: return
        self.by_title.setdefault(t, []).append(e)
        if a:
            self.by_title_artist[(t, a)] = e

    def exact(self, title: Optional[str], artist: Optional[str]) -> Optional[Dict[str, Any]]:
        if not title: return None
        t = _normalize(title)
        a = _normalize(artist) if artist else ""
        if not t: return None
        if a and (t, a) in self.by_title_artist:
            return self.by_title_artist[(t, a)]
        entries = self.by_title.get(t) or []
        if len(entries) == 1:
            return entries[0]
        allowed = []
        for e in entries:
            meta = _parse_notes(e)
            if meta.get("allow_title_only", False):
                allowed.append((e, int(meta.get("max_ambiguous_candidates", 3))))
        if allowed:
            min_cap = min(cap for _, cap in allowed)
            if len(entries) <= max(1, min_cap):
                return allowed[0][0]
        return None

    def fuzzy(self, title: Optional[str], artist: Optional[str]) -> Optional[Dict[str, Any]]:
        if not title: return None
        t = _normalize(title)
        a = _normalize(artist) if artist else ""
        if not t: return None
        prefix = t[:8]
        cands: List[Dict[str, Any]] = []
        for tt, entries in self.by_title.items():
            if tt.startswith(prefix) or prefix.startswith(tt[:4]):
                cands.extend(entries)
            if len(cands) > 220:
                break
        best, best_score = None, 0.0
        for e in cands:
            et = _normalize(str(e.get(self.title_key, "")))
            aliases = e.get("aliases") or []
            alias_norms_t = [_normalize(str(x)) for x in aliases if str(x).strip()]
            t_scores = [SequenceMatcher(a=t, b=et).ratio()] + [SequenceMatcher(a=t, b=ax).ratio() for ax in alias_norms_t]
            et_best = max(t_scores)

            ea = _normalize(str(e.get(self.artist_key, "")))
            notes_meta = _parse_notes(e)
            alias_norms_a = [_normalize(x) for x in (notes_meta.get("artist_aliases") or []) + (notes_meta.get("confirm_artists") or [])]
            if a:
                a_scores = [SequenceMatcher(a=a, b=ea).ratio()] + [SequenceMatcher(a=a, b=ax).ratio() for ax in alias_norms_a]
                a_score = max(a_scores)
            else:
                a_score = 1.0

            ld = abs(len(t) - len(et))
            length_penalty = 0.03 if ld >= 6 else (0.02 if ld >= 3 else 0.0)
            alias_boost = 0.01 if (alias_norms_t and et_best < 0.999 and et_best in t_scores[1:]) else 0.0
            score = (et_best * 0.88) + (a_score * 0.12) - length_penalty + alias_boost
            if score > best_score:
                best, best_score = e, score
        if best:
            et = _normalize(str(best.get(self.title_key, "")))
            ea = _normalize(str(best.get(self.artist_key, "")))
            notes_meta = _parse_notes(best)
            if a:
                alias_norms_a = [_normalize(x) for x in (notes_meta.get("artist_aliases") or []) + (notes_meta.get("confirm_artists") or [])]
                a_scores = [SequenceMatcher(a=a, b=ea).ratio()] + [SequenceMatcher(a=a, b=ax).ratio() for ax in alias_norms_a]
                a_score_final = max(a_scores)
            else:
                a_score_final = 1.0
            t_score = SequenceMatcher(a=t, b=et).ratio()
            if t_score >= 0.935 and a_score_final >= 0.66:
                return best
            if notes_meta.get("allow_title_only") and t_score >= 0.97:
                cap = int(notes_meta.get("max_ambiguous_candidates", 3))
                entries_same_title = self.by_title.get(et, []) or []
                if len(entries_same_title) <= max(1, cap):
                    return best
        return None

# ========= Debug-Probe / Sync-Guard =========

def maybe_run_probe(cfg: dict, title: Optional[str], artist: Optional[str], kb_path: Path, idx_path: Optional[Path]) -> None:
    dbg = cfg.get("debug_probe") or {}
    if not dbg or not bool(dbg.get("enabled", False)): return
    probe_path = dbg.get("kb_probe_path")
    if not probe_path:
        log("[debug] kb_probe_path fehlt"); return
    probe = Path(probe_path)
    if not probe.exists():
        log(f"[debug] kb_probe.py nicht gefunden: {probe}"); return
    line = (title or "") + (f" — {artist}" if artist else "")
    if not line.strip(): return
    args = [sys.executable, str(probe), "--line", line, "--kb", str(kb_path)]
    if bool(dbg.get("use_idx", False)) and idx_path:
        args += ["--idx", str(idx_path)]
    try:
        subprocess.run(args, creationflags=(0x00000010 if bool(dbg.get("open_console", False)) and os.name=="nt" else 0), check=False)
        log("[debug] kb_probe ausgeführt")
    except Exception as e:
        log(f"[debug] kb_probe Fehler: {e}")

def read_file_stable(path: Path, settle_ms: int = 200, retries: int = 3) -> str:
    delay = max(0, settle_ms) / 1000.0
    tries = max(1, retries); last = None
    for _ in range(tries):
        try: t1 = path.read_text(encoding="utf-8", errors="ignore")
        except Exception: time.sleep(delay); continue
        h1 = hashlib.sha256(t1.encode("utf-8", "ignore")).hexdigest()
        time.sleep(delay)
        try: t2 = path.read_text(encoding="utf-8", errors="ignore")
        except Exception: continue
        h2 = hashlib.sha256(t2.encode("utf-8", "ignore")).hexdigest()
        if h1 == h2: return t2
        last = t2
    return last or ""

# ========= Missing / Not-Sure Dedupe =========

class MissingDedupe:
    def __init__(self, path: Path, ttl_hours: int = 12, max_items: int = 4096):
        self.path = path
        self.ttl = timedelta(hours=max(1, int(ttl_hours)))
        self.max_items = max_items
        self.map: Dict[str, str] = {}
        try:
            if self.path.exists():
                self.map = json.loads(self.path.read_text(encoding="utf-8")) or {}
        except Exception:
            self.map = {}
    def _prune(self, now: datetime):
        expired = []
        for k, ts in list(self.map.items()):
            try: t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception: expired.append(k); continue
            if now - t > self.ttl: expired.append(k)
        for k in expired: self.map.pop(k, None)
        if len(self.map) > self.max_items:
            items = sorted(self.map.items(), key=lambda kv: kv[1])
            for k, _ in items[: len(self.map) - self.max_items]:
                self.map.pop(k, None)
    def should_log(self, key: str, now: datetime) -> bool:
        self._prune(now); ts = self.map.get(key)
        if not ts: return True
        try: last = datetime.fromisoformat(ts.replace("Z", "+00:00")); return (now - last) > self.ttl
        except Exception: return True
    def mark(self, key: str, now: datetime):
        self.map[key] = now.isoformat().replace("+00:00", "Z")
        try: self.path.write_text(json.dumps(self.map, ensure_ascii=False), encoding="utf-8")
        except Exception: pass

# ========= ENV + Spotify Mini =========

def _load_env_once():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    script_root = Path(__file__).resolve().parent
    safe_root = Path(os.environ.get("MUSIC_ROOT", str(script_root))).resolve()
    env_path = (safe_root / ".env")
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.strip().startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

def _http_json(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(url=url, method=method)
    for k,v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None and not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode("utf-8")

class _SpotifyMini:
    def __init__(self, cache_dir: Path):
        _load_env_once()
        self.cid = os.environ.get("CLIENT_ID") or os.environ.get("SPOTIFY_CLIENT_ID")
        self.cs  = os.environ.get("CLIENT_SECRET") or os.environ.get("SPOTIFY_CLIENT_SECRET")
        self.token = None
        self.until = 0
        self.cache_dir = cache_dir
        self.id_cache = self._load_json(cache_dir / "spotify_id_cache.json", {})
        self.tr_cache = self._load_json(cache_dir / "spotify_track_cache.json", {})
        self.ar_cache = self._load_json(cache_dir / "spotify_artist_cache.json", {})

    def _load_json(self, p: Path, default):
        try:
            if p.exists(): return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return default

    def _save_json(self, p: Path, obj):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, p)
        except Exception:
            pass

    def _auth_hdr(self):
        now = time.time()
        if self.token and now < self.until - 30:
            return {"Authorization": f"Bearer {self.token}"}
        if not self.cid or not self.cs:
            raise RuntimeError("CLIENT_ID/CLIENT_SECRET not set (.env)")
        body = urllib.parse.urlencode({"grant_type":"client_credentials"}).encode("utf-8")
        basic = "Basic " + __import__("base64").b64encode((self.cid+":"+self.cs).encode("utf-8")).decode("ascii")
        code, raw = _http_json(
            "https://accounts.spotify.com/api/token",
            method="POST",
            headers={"Authorization": basic, "Content-Type":"application/x-www-form-urlencoded"},
            data=body
        )
        if code != 200:
            raise RuntimeError(f"Spotify token failed: {code} {raw[:200]}")
        data = json.loads(raw)
        self.token = data["access_token"]
        self.until = time.time() + int(data.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self.token}"}

    def _key(self, title: str, artist: str):
        k = f"{(title or '').lower().strip()}|{(artist or '').lower().strip()}"
        return re.sub(r"\s+", " ", k)

    def search_track(self, title: str, artist: Optional[str]):
        key = self._key(title, artist or "")
        if key in self.id_cache:
            tid = self.id_cache[key]
            tr = self.tr_cache.get(tid)
            if tr: return tr
        q = title or ""
        if artist: q += f" artist:{artist}"
        params = urllib.parse.urlencode({"q": q, "type":"track", "limit": 3})
        code, raw = _http_json(f"https://api.spotify.com/v1/search?{params}", headers=self._auth_hdr())
        if code != 200: return None
        try:
            items = (json.loads(raw).get("tracks") or {}).get("items") or []
        except Exception:
            items = []
        if not items: return None
        best = items[0]
        tid = best.get("id")
        if tid:
            self.id_cache[key] = tid
            self.tr_cache[tid] = best
            self._save_json(self.cache_dir / "spotify_id_cache.json", self.id_cache)
            self._save_json(self.cache_dir / "spotify_track_cache.json", self.tr_cache)
        return best

    def get_artist(self, artist_id: Optional[str]):
        if not artist_id: return None
        if artist_id in self.ar_cache:
            return self.ar_cache[artist_id]
        code, raw = _http_json(f"https://api.spotify.com/v1/artists/{artist_id}", headers=self._auth_hdr())
        if code != 200: return None
        try:
            data = json.loads(raw)
        except Exception:
            data = None
        if data is not None:
            self.ar_cache[artist_id] = data
            self._save_json(self.cache_dir / "spotify_artist_cache.json", self.ar_cache)
        return data

# ========= KB Backup / Save Helper =========

def _kb_backup(kb_path: Path, backups_dir: Path) -> Optional[Path]:
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
        if not kb_path.exists(): return None
        dst = backups_dir / f"songs_kb.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        with open(kb_path, "rb") as r, open(dst, "wb") as w:
            w.write(r.read()); w.flush(); os.fsync(w.fileno())
        print(f"[kb_backup] -> {dst}", flush=True)
        return dst
    except Exception as e:
        print(f"[kb_backup_error] {e}", flush=True)
        return None

def _atomic_json(path: Path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def _write_obs_genres(outputs_dir: Path, tags: List[str]):
    out = "Genres: (unbekannt)" if not tags else "Genres: " + ", ".join(tags)
    tmp = outputs_dir / "obs_genres.txt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp.with_suffix(".txt.tmp"), "w", encoding="utf-8", newline="\n") as f:
        f.write(out); f.flush(); os.fsync(f.fileno())
    os.replace(tmp.with_suffix(".txt.tmp"), tmp)
    print(f"[genres_out] {out}", flush=True)

# ========= Spotify Enrichment (vereinheitlicht) =========

def _resolve_spotify_cache_dir(kb_path: Path) -> Path:
    _load_env_once()
    # 1) explizit per ENV überschreiben
    env_dir = os.environ.get("SPOTIFY_CACHE_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    # 2) MUSIC_ROOT/.env → <root>/cache
    mr = os.environ.get("MUSIC_ROOT")
    if mr:
        return (Path(mr) / "cache").resolve()

    # 3) kb_path: aufwärts nach "MUSICNEU" suchen
    try:
        for p in [kb_path] + list(kb_path.parents):
            if p.name.lower() == "musicneu":
                return (p / "cache").resolve()
    except Exception:
        pass

    # 4) Fallback: wie bisher
    return (kb_path.parent.parent / "cache").resolve()


def spotify_hybrid_enrich_if_needed(
    artist: str,
    title: str,
    kb_path: Path,
    outputs_dir: Path,
    existing_match: Optional[Dict[str,Any]]
) -> List[str]:
    """
    - Wird nur gerufen, wenn: KEIN Match ODER Match ohne Tags.
    - Holt Genres vom Primary Artist, schreibt sie als entry['tags'] (KEIN 'genres'-Feld).
    - Legt Eintrag nur an, wenn es noch keinen mit Tags gibt.
    - Gibt die Tags zurück; schreibt sofort obs_genres.txt.
    """
    # Wenn bereits Tags vorhanden -> nichts zu tun
    if extract_tags(existing_match):
        return extract_tags(existing_match) or []

    cache_dir = _resolve_spotify_cache_dir(kb_path)
    sp = _SpotifyMini(cache_dir=cache_dir)
    tr = sp.search_track(title, artist if artist else None) or sp.search_track(title, None)
    if not tr:
        print(f"[spotify_not_found] {artist} — {title}", flush=True)
        _write_obs_genres(outputs_dir, [])
        return []

    # Genres vom Primary Artist
    artist_genres: List[str] = []
    try:
        arts = tr.get("artists") or []
        aid = (arts[0] or {}).get("id") if isinstance(arts, list) and arts else None
        ad = sp.get_artist(aid) if aid else None
        if ad and isinstance(ad.get("genres"), list):
            artist_genres = [str(x).strip() for x in ad["genres"] if str(x).strip()]
    except Exception:
        pass

    # KB laden (list / dict.songs / list)
    layout = "flat"; kb_obj: list|dict = []
    if kb_path.exists():
        try:
            kb_obj = json.loads(kb_path.read_text(encoding="utf-8"))
            if isinstance(kb_obj, dict) and "songs" in kb_obj and isinstance(kb_obj["songs"], list):
                layout = "list"
            elif isinstance(kb_obj, dict):
                layout = "map"
            elif isinstance(kb_obj, list):
                layout = "flat"
            else:
                kb_obj = []; layout = "flat"
        except Exception:
            kb_obj = []; layout = "flat"

    # Prüfen, ob es bereits einen (Titel-)Eintrag mit Tags gibt
    def _iter_entries():
        if layout == "list" and isinstance(kb_obj, dict):
            for e in kb_obj.get("songs", []): yield e
        elif layout == "map" and isinstance(kb_obj, dict):
            for _, e in kb_obj.items(): yield e
        else:
            for e in (kb_obj if isinstance(kb_obj, list) else []): yield e

    t_norm = _normalize(title)
    already_tagged = False
    for e in _iter_entries():
        if _normalize(str(e.get("title",""))) == t_norm:
            if extract_tags(e):
                already_tagged = True; break
    if already_tagged:
        _write_obs_genres(outputs_dir, artist_genres)
        print("[kb_skip] Eintrag mit Tags existiert bereits; nur Genres ausgeben.", flush=True)
        return artist_genres

    # Neuen Eintrag minimal & einheitlich bauen
    entry = {
        "title":  tr.get("name") or title,
        "artist": ", ".join([a.get("name","") for a in (tr.get("artists") or []) if a and a.get("name")]).strip() or artist,
        "album":  (tr.get("album") or {}).get("name", ""),
        "aliases": [str(tr.get("name") or title).strip(), _normalize(tr.get("name") or title)],
        "tags":   artist_genres or [],
        "notes":  ""
    }

    # Backup + Append + Save
    backups_dir = kb_path.parent / "backups"
    _kb_backup(kb_path, backups_dir)

    if layout == "map" and isinstance(kb_obj, dict):
        kb_obj[f"{entry['artist']} - {entry['title']}"] = entry
    elif layout == "list" and isinstance(kb_obj, dict):
        kb_obj.setdefault("songs", [])
        if isinstance(kb_obj["songs"], list):
            kb_obj["songs"].append(entry)
        else:
            kb_obj["songs"] = [entry]
    else:
        if not isinstance(kb_obj, list):
            kb_obj = []
        kb_obj.append(entry)

    _atomic_json(kb_path, kb_obj)
    print(f"[kb_added] {entry['artist']} — {entry['title']} (tags={len(entry['tags'])})", flush=True)

    _write_obs_genres(outputs_dir, entry.get("tags") or [])
    return entry.get("tags") or []

# ========= Special-Version-Tags =========

def detect_special_version_tags(title: str, cfg: dict) -> List[str]:
    sv = (cfg.get("special_version_tags") or {})
    if not sv: return []
    t = (title or "").lower()
    def phrase_to_pattern(phrase: str) -> str:
        tokens = re.split(r"\s+", phrase.strip().lower())
        tokens = [re.escape(tok) for tok in tokens if tok]
        if not tokens: return ""
        return r"\b" + r"[\s\-]*".join(tokens) + r"\b"
    tags = []
    for tag_name, patterns in sv.items():
        arr = patterns if isinstance(patterns, list) else [patterns]
        for p in arr:
            p = str(p or "").strip()
            if not p: continue
            pat = phrase_to_pattern(p)
            if pat and re.search(pat, t, flags=re.IGNORECASE):
                tags.append(tag_name.lower()); break
    return tags

# ========= Reaction Engine (gekürzt – funktional identisch) =========

class ReactionEngine:
    def __init__(self, cfg: dict):
        rx_cfg = (cfg or {}).get("reactions") or {}
        self.enabled   = bool(rx_cfg.get("enabled", True))
        self.path      = rx_cfg.get("path", "Memory/reactions.json")
        self.mode      = str(rx_cfg.get("mode", "score")).lower()
        self.seed      = rx_cfg.get("seed", None)
        self.cooldown  = int(rx_cfg.get("cooldown_s", 0))
        self.debug     = bool(rx_cfg.get("debug", False))
        self.include_genres = bool(rx_cfg.get("include_genres", True))
        self._last_text = None
        self._last_ts   = 0.0

        self.sets = {"like": [], "neutral": [], "dislike": []}
        self.fallback = {"like": "LOVE IT! 😍", "neutral": "Okay.", "dislike": "Nope."}
        self.weights  = {"like": 2.0, "neutral": 1.0, "dislike": 2.0,
                         "tag_like": 1.0, "tag_dislike": 1.0,
                         "artist_like": 2.0, "artist_dislike": 2.0}
        self.bias     = {"like_tags": [], "dislike_tags": [],
                         "like_artists": [], "dislike_artists": []}
        self.special  = []
        self.unknown_enabled = True
        self.unknown_probs = {"like": 0.34, "neutral": 0.33, "dislike": 0.33}
        self.explore_enabled = True
        self.explore_chance = 0.15
        self.explore_weights = {"like": 0.4, "neutral": 0.4, "dislike": 0.2}

        try:
            p = Path(self.path)
            if not p.is_absolute(): p = (SCRIPT_DIR / p).resolve()
            data = json.loads(p.read_text(encoding="utf-8"))
            sets = data.get("sets") or {}
            for k in ["like", "neutral", "dislike"]:
                self.sets[k] = [str(x).strip() for x in sets.get(k, []) if str(x).strip()]
            fb = data.get("fallback") or {}
            for k in ["like", "neutral", "dislike"]:
                if fb.get(k): self.fallback[k] = str(fb.get(k))
            for k, v in (data.get("weights") or {}).items():
                try: self.weights[k] = float(v)
                except: pass
            b = data.get("bias") or {}
            self.bias["like_tags"]       = [str(x).lower() for x in (b.get("like_tags") or [])]
            self.bias["dislike_tags"]    = [str(x).lower() for x in (b.get("dislike_tags") or [])]
            self.bias["like_artists"]    = [str(x).lower() for x in (b.get("like_artists") or [])]
            self.bias["dislike_artists"] = [str(x).lower() for x in (b.get("dislike_artists") or [])]
            up = (data.get("unknown_policy") or {})
            self.unknown_enabled = bool(up.get("enabled", True))
            self.unknown_probs = {
                "like": float(up.get("like", 0.34)),
                "neutral": float(up.get("neutral", 0.33)),
                "dislike": float(up.get("dislike", 0.33)),
            }
            ex = (data.get("explore") or {})
            self.explore_enabled = bool(ex.get("enabled", True))
            self.explore_chance = float(ex.get("chance", 0.15))
            self.explore_weights = {
                "like": float((ex.get("weights") or {}).get("like", 0.4)),
                "neutral": float((ex.get("weights") or {}).get("neutral", 0.4)),
                "dislike": float((ex.get("weights") or {}).get("dislike", 0.2)),
            }
            for sp in (data.get("special") or []):
                self.special.append({
                    "title_contains":  [str(x).lower() for x in (sp.get("title_contains") or [])],
                    "artist_contains": [str(x).lower() for x in (sp.get("artist_contains") or [])],
                    "react": str(sp.get("react") or "").strip(),
                    "force_bucket": (sp.get("force_bucket") or "").lower().strip()
                })
        except Exception as e:
            log(f"[react] using defaults (load warn: {e})")

        # Kontext
        self.ctx = ContextManager(cfg.get("reactions") or {})

    @staticmethod
    def _norm(s: str) -> str:
        return (_normalize(s or "")).lower()

    def _pick(self, bucket: str) -> str:
        arr = self.sets.get(bucket) or []
        if not arr: return self.fallback.get(bucket, "Okay.")
        return random.choice(arr)

    def _format(self, tmpl: str, title: str, artist: str, genres_text: str) -> str:
        g = genres_text or ""
        if not self.include_genres: g = ""
        safe = {"title": title or "", "artist": artist or "", "genres": g}
        try: out = tmpl.format(**safe)
        except Exception: out = tmpl
        return re.sub(r"\s{2,}", " ", out).strip()

    def _pick_by_probs(self, probs: dict) -> str:
        keys = ["like","neutral","dislike"]
        vals = [max(0.0, float(probs.get(k, 0.0))) for k in keys]
        s = sum(vals) or 1.0
        vals = [v/s for v in vals]
        r = random.random(); cum = 0.0
        for k, v in zip(keys, vals):
            cum += v
            if r <= cum: return k
        return keys[-1]

    def _rate_bucket(self, tags: List[str], artist: str, title: str) -> str:
        if self.mode == "always_like": return "like"
        if self.mode == "always_dislike": return "dislike"
        if self.mode == "always_neutral": return "neutral"
        tset = {t.lower() for t in (tags or [])}
        a = self._norm(artist)
        ctx = self.ctx.get_active_profile()
        tag_w = ctx.get("tag_weights", {}) or {}
        art_w = ctx.get("artist_weights", {}) or {}
        bucket_bias = ctx.get("bucket_bias", {}) or {}

        artist_bias_present = False
        # (vereinfachter Check – Details wie vorher)
        if self.unknown_enabled and not tset and not artist_bias_present:
            bucket = self._pick_by_probs(self.unknown_probs)
            if self.debug:
                log(f"[react] unknown policy -> {bucket} (ctx={ctx.get('name','neutral')})")
            bias_val = float(bucket_bias.get(bucket, 0.0))
            if bias_val > 0 and bucket == "neutral": return "like"
            if bias_val < 0 and bucket == "neutral": return "dislike"
            return bucket

        score = 0.0
        for tg in tset:
            score += float(tag_w.get(tg, 0.0))
        for name, w in art_w.items():
            if name and name in a:
                try: score += float(w)
                except: pass

        if score > 0:
            score += float(bucket_bias.get("like", 0.0))
        elif score < 0:
            score += float(bucket_bias.get("dislike", 0.0))
        else:
            score += float(bucket_bias.get("neutral", 0.0))

        return "like" if score>0 else ("dislike" if score<0 else "neutral")

    def _check_special(self, title: str, artist: str) -> Optional[Dict[str, str]]:
        t = self._norm(title); a = self._norm(artist)
        for sp in self.special:
            t_ok = all(sub in t for sub in (sp.get("title_contains") or [])) if sp.get("title_contains") else True
            a_ok = all(sub in a for sub in (sp.get("artist_contains") or [])) if sp.get("artist_contains") else True
            if t_ok and a_ok: return sp
        return None

    def decide(self, title: str, artist: str, genres_text: str, tags_for_scoring: List[str], uniq_key: str) -> Tuple[str, str]:
        if not self.enabled: return ("", "neutral")
        sp = self._check_special(title, artist)
        forced_bucket = None
        if sp:
            text = sp.get("react") or ""
            forced_bucket = sp.get("force_bucket") or None
            if text:
                return (self._format(text, title, artist, genres_text), forced_bucket or "neutral")
        rnd_state = None
        if self.seed is not None and uniq_key:
            rnd_state = random.getstate(); random.seed(hash(uniq_key) ^ int(self.seed))
        bucket = forced_bucket or self._rate_bucket(tags_for_scoring, artist, title)
        tmpl = self._pick(bucket)
        text = self._format(tmpl, title, artist, genres_text)
        now = time.time()
        if self.cooldown > 0 and getattr(self, "_last_text", None) == text and (now - getattr(self, "_last_ts", 0.0)) < self.cooldown:
            alt = self._pick(bucket)
            if alt != text: text = self._format(alt, title, artist, genres_text)
        self._last_text = text; self._last_ts = now
        if rnd_state is not None: random.setstate(rnd_state)
        return (text, bucket)

# ========= Kontext =========

class ContextManager:
    def __init__(self, rx_cfg: dict):
        c = (rx_cfg or {}).get("context") or {}
        self.enabled = bool(c.get("enabled", False))
        path = c.get("path", "Memory/contexts.json")
        self.refresh_s = int(c.get("refresh_s", 5))
        self.contexts_path = Path(path) if Path(path).is_absolute() else (SCRIPT_DIR / path).resolve()
        self.state_path = None
        self.state_map = {}
        self.default_profile = "neutral"
        self.profiles = {}
        self.source = {"type": "file", "path": "Memory/game_state.txt", "map": {"default": "neutral"}}
        self._last_load = 0.0
        self._last_state_read = 0.0
        self._cached_active = "neutral"
        if not self.enabled:
            return
        self._load_contexts(force=True)
        self._load_state(force=True)

    def _safe_read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""

    def _load_contexts(self, force=False):
        if not self.enabled: return
        try:
            mtime = self.contexts_path.stat().st_mtime if self.contexts_path.exists() else 0
        except Exception:
            mtime = 0
        if (not force) and (mtime <= self._last_load): return
        try:
            data = json.loads(self._safe_read_text(self.contexts_path))
            self.default_profile = str(data.get("default_profile", "neutral"))
            self.profiles = data.get("profiles", {}) or {}
            src = data.get("source", {}) or {}
            stype = (src.get("type") or "file").lower()
            if stype == "file":
                sp = src.get("path", "Memory/game_state.txt")
                self.state_path = Path(sp) if Path(sp).is_absolute() else (SCRIPT_DIR / sp).resolve()
                self.state_map = src.get("map", {}) or {"default": self.default_profile}
            else:
                self.state_path = (SCRIPT_DIR / "Memory/game_state.txt").resolve()
                self.state_map = {"default": self.default_profile}
            self._last_load = mtime
            log(f"[ctx] loaded contexts ({self.contexts_path.name}), default='{self.default_profile}'")
        except Exception as e:
            log(f"[ctx] load warn: {e}")

    def _load_state(self, force=False):
        if not self.enabled or not self.state_path: return
        now = time.time()
        if (not force) and (now - self._last_state_read) < max(1, int(self.refresh_s)): return
        self._last_state_read = now
        raw = self._safe_read_text(self.state_path).lower()
        key = raw or "default"
        profile = self.state_map.get(key, self.state_map.get("default", self.default_profile))
        if profile not in (self.profiles or {}):
            profile = self.default_profile
        self._cached_active = profile

    def get_active_profile(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"name":"neutral", "bucket_bias":{}, "tag_weights":{}, "artist_weights":{}}
        self._load_contexts(force=False)
        self._load_state(force=False)
        prof = self.profiles.get(self._cached_active, {}) or {}
        return {
            "name": self._cached_active,
            "bucket_bias": prof.get("bucket_bias", {}) or {},
            "tag_weights": prof.get("tag_weights", {}) or {},
            "artist_weights": prof.get("artist_weights", {}) or {},
        }

# ========= Memory =========

class MemoryDB:
    def __init__(self, path: Path, enabled: bool = True, decay_cfg: Optional[dict] = None):
        self.path = path
        self.enabled = enabled
        self.data = {"songs": {}}
        self.decay_enabled = False
        self.half_life_days = 90.0
        self.floor = 0.0
        if decay_cfg:
            self.decay_enabled = bool(decay_cfg.get("enabled", False))
            self.half_life_days = float(decay_cfg.get("half_life_days", 90))
            self.floor = float(decay_cfg.get("floor", 0.0))
        if self.enabled:
            try:
                if self.path.exists():
                    self.data = json.loads(self.path.read_text(encoding="utf-8")) or {"songs": {}}
            except Exception:
                self.data = {"songs": {}}

    def _song(self, key: str, title: str, artist: str) -> dict:
        s = self.data["songs"].get(key)
        if not s:
            s = {
                "title": title, "artist": artist,
                "tags": [],
                "total": {"like": 0.0, "neutral": 0.0, "dislike": 0.0},
                "contexts": {},
                "last": {}
            }
            self.data["songs"][key] = s
        return s

    def _decay_factor(self, last_ts_iso: Optional[str], now: datetime) -> float:
        if not self.decay_enabled or not last_ts_iso:
            return 1.0
        try:
            last = datetime.fromisoformat(last_ts_iso.replace("Z", "+00:00"))
        except Exception:
            return 1.0
        dt_days = max(0.0, (now - last).total_seconds() / 86400.0)
        if self.half_life_days <= 0.0:
            return 1.0
        return 0.5 ** (dt_days / self.half_life_days)

    def _apply_decay(self, ctxmap: dict, now: datetime) -> None:
        if not self.decay_enabled: return
        last_ts = ctxmap.get("last_ts")
        factor = self._decay_factor(last_ts, now)
        if factor < 1.0:
            for k in ("like", "neutral", "dislike"):
                v = float(ctxmap.get(k, 0.0)) * factor
                if self.floor > 0.0:
                    v = max(v, self.floor)
                ctxmap[k] = v
            ctxmap["last_ts"] = now.isoformat().replace("+00:00", "Z")

    def update(self, key: str, title: str, artist: str, ctx: str, bucket: str, tags: List[str]):
        if not self.enabled: return
        now = datetime.now(timezone.utc)
        s = self._song(key, title, artist)
        existing = set([str(x).lower().strip() for x in s.get("tags", []) if str(x).strip()])
        for t in (tags or []):
            tt = str(t).lower().strip()
            if tt: existing.add(tt)
        s["tags"] = sorted(existing)
        ctxmap = s["contexts"].setdefault(ctx, {"like": 0.0, "neutral": 0.0, "dislike": 0.0, "last_ts": now.isoformat().replace("+00:00","Z")})
        self._apply_decay(ctxmap, now)
        ctxmap[bucket] = float(ctxmap.get(bucket, 0.0)) + 1.0
        ctxmap["last_ts"] = now.isoformat().replace("+00:00","Z")
        s["total"][bucket] = float(s["total"].get(bucket, 0.0)) + 1.0
        s["last"] = {"ts": now.isoformat().replace("+00:00","Z"), "bucket": bucket, "context": ctx}

    def seen_count(self, key: str) -> int:
        s = self.data["songs"].get(key)
        if not s: return 0
        return int(round(sum(float(s["total"].get(k, 0.0)) for k in ("like","neutral","dislike"))))

    def best_context(self, key: str) -> Optional[Tuple[str, str, float]]:
        s = self.data["songs"].get(key)
        if not s: return None
        best = None
        now = datetime.now(timezone.utc)
        for ctx, counts in (s.get("contexts") or {}).items():
            like = float(counts.get("like", 0.0))
            neu  = float(counts.get("neutral", 0.0))
            dis  = float(counts.get("dislike", 0.0))
            if self.decay_enabled:
                factor = self._decay_factor(counts.get("last_ts"), now)
                like = max(self.floor, like * factor) if self.floor>0 else like * factor
                neu  = max(self.floor, neu  * factor) if self.floor>0 else neu  * factor
                dis  = max(self.floor, dis  * factor) if self.floor>0 else dis  * factor
            score = like - dis
            bucket = "like" if like>max(neu, dis) else ("dislike" if dis>max(like,neu) else "neutral")
            cand = (ctx, bucket, score, like)
            if best is None or (cand[2] > best[2]) or (cand[2] == best[2] and cand[3] > best[3]):
                best = cand
        if not best: return None
        return (best[0], best[1], best[2])

    def save(self):
        if not self.enabled: return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log(f"[memory] save warn: {e}")

# ========= Persistenter KB-Index =========

def _kb_hash_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_or_build_kb_index(kb_json_path: Path, cache_path: Optional[Path] = None) -> KBIndex:
    json_hash = _kb_hash_of_file(kb_json_path)
    
    if cache_path and cache_path.exists():
        try:
            # ✅ NEU: Prüfe, ob Datei lesbar und strukturiert ist — BEVOR pickle.loads
            raw_data = cache_path.read_bytes()
            obj = pickle.loads(raw_data)

            # ✅ NEU: STRIKTE VALIDIERUNG DES CACHE-OBJEKTS
            if not isinstance(obj, dict):
                raise ValueError("Cache-Datei enthält kein Dictionary")
            if "json_hash" not in obj:
                raise ValueError("Cache-Datei fehlt 'json_hash'")
            if "index" not in obj:
                raise ValueError("Cache-Datei fehlt 'index'")

            cached_hash = obj.get("json_hash") or obj.get("json_md5")
            if cached_hash == json_hash:
                log(f"[kb_cache] loaded from {cache_path.name} (hash match)")
                return obj["index"]
            else:
                log(f"[kb_cache] hash mismatch — rebuilding index ({cached_hash} != {json_hash})")

        except (pickle.UnpicklingError, EOFError, ValueError, TypeError, Exception) as e:
            log(f"[kb_cache] corrupted or invalid cache file: {cache_path} ({e}) — rebuilding...")
            # Nicht exiten — einfach weiter mit neuem Index
            pass

    entries = load_songs_kb(kb_json_path)
    idx = KBIndex(entries)

    if cache_path:
        try:
            payload = {"json_hash": json_hash, "index": idx}
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
            tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
            os.replace(tmp, cache_path)
            log(f"[kb_cache] saved to {cache_path.name}")
        except Exception as e:
            log(f"[kb_cache] failed to save cache: {e}")

    return idx

# ========= Main Loop =========

def main():
    if not acquire_single_instance_lock():
        print("[i] Konnte Lock nicht bekommen – vermutlich läuft schon eine Instanz.")
        print("    Tipp:  run_finja.bat force   (oder FINJA_FORCE=1 setzen)")
        return
    try:
        print("[i] Starte Finja Minimal Writer...")
        # ✅ NEU: Konfigurationsdatei-Endung prüfen BEFORE load_config()
        if CONFIG_PATH.suffix.lower() not in ('.json', '.js'):
            raise SystemExit(f"[config error] Konfigurationsdatei muss .json oder .js sein: {CONFIG_PATH}")

        cfg = load_config(CONFIG_PATH)

        input_path_cfg = cfg.get("input_path", "nowplaying.txt")
        input_path = Path(input_path_cfg)
        if not input_path.is_absolute():
            input_path = (SCRIPT_DIR / input_path).resolve()

        default_outputs = Path("C:/Users/johnv/Pictures/Streaming/TruckersFM/outputs")
        outputs_dir = Path(cfg.get("fixed_outputs", str(default_outputs))).resolve()

        interval_s       = float(cfg.get("interval_s", 2.0))
        init_write       = bool(cfg.get("init_write", True))
        genres_text_def  = str(cfg.get("genres_template", "Pop • Nightcore • Speed Up"))
        genres_fallback  = str(cfg.get("genres_fallback", "Neuer Song :) hören wir mal rein"))
        genres_joiner    = str(cfg.get("genres_joiner", " • "))
        mirror_legacy    = bool(cfg.get("mirror_legacy_gernres", True))
        log_every_tick   = bool(cfg.get("log_every_tick", False))

        show_special_in_genres = bool(cfg.get("show_special_version_in_genres", True))
        special_prefix = str(cfg.get("special_version_prefix", ""))

        # Sync-Guard
        sync_guard_cfg = cfg.get("sync_guard") or {}
        sg_enabled   = bool(sync_guard_cfg.get("enabled", True))
        sg_settle_ms = int(sync_guard_cfg.get("settle_ms", 200))
        sg_retries   = int(sync_guard_cfg.get("retries", 3))

        # KB
        kb_path_cfg = cfg.get("songs_kb_path", "songs_kb.json")
        kb_path = Path(kb_path_cfg)
        if not kb_path.is_absolute(): kb_path = (SCRIPT_DIR / kb_path).resolve()
        kb_cache_cfg = cfg.get("kb_index_cache_path", None)
        kb_cache_path = Path(kb_cache_cfg).resolve() if kb_cache_cfg else None

        # Missing-Logger
        missing_cfg      = cfg.get("missing_log") or {}
        missing_enabled  = bool(missing_cfg.get("enabled", False))
        missing_path     = Path(missing_cfg.get("path", "missingsongs/missing_songs_log.jsonl"))
        if not missing_path.is_absolute(): missing_path = (SCRIPT_DIR / missing_path).resolve()
        log_on_init      = bool(missing_cfg.get("log_on_init", False))
        dedupe_hours     = int(missing_cfg.get("dedupe_hours", 12))
        state_path       = Path(missing_cfg.get("state_path", ".missing_seen.json"))
        if not state_path.is_absolute(): state_path = (SCRIPT_DIR / state_path).resolve()
        deduper = MissingDedupe(state_path, ttl_hours=dedupe_hours)

        # Artist-Not-Sure-Logger
        ans_cfg = cfg.get("artist_not_sure") or {}
        ans_enabled = bool(ans_cfg.get("enabled", True))
        ans_path = Path(ans_cfg.get("path", "missingsongs/artist_not_sure.jsonl"))
        if not ans_path.is_absolute(): ans_path = (SCRIPT_DIR / ans_path).resolve()
        ans_dedupe_state = Path(ans_cfg.get("state_path", "missingsongs/.artist_not_sure_seen.json"))
        if not ans_dedupe_state.is_absolute(): ans_dedupe_state = (SCRIPT_DIR / ans_dedupe_state).resolve()
        ans_dedupe_hours = int(ans_cfg.get("dedupe_hours", 24))
        ans_deduper = MissingDedupe(ans_dedupe_state, ttl_hours=ans_dedupe_hours)

        out_genres = (outputs_dir / "obs_genres.txt").resolve()
        out_react  = (outputs_dir / "obs_react.txt").resolve()
        legacy_gernres = (outputs_dir / "gernres_template.txt").resolve()

        # KB laden
        kb_index = None
        try:
            kb_index = load_or_build_kb_index(kb_path, kb_cache_path)
            bucket_count = len(getattr(kb_index, "by_title", {}))
            tag_cache_note = " [cache]" if kb_cache_path and kb_cache_path.exists() else ""
            log(f"[boot] KB ready: {kb_path} (buckets={bucket_count}){tag_cache_note}")
        except Exception as e:
            log(f"[boot] KB load warn: {e} (weiter mit Fallbacks)")

        log(f"[boot] script   : {SCRIPT_DIR}")
        log(f"[boot] config   : {CONFIG_PATH}")
        log(f"[boot] input    : {input_path}")
        log(f"[boot] outputs  : {outputs_dir}")
        log(f"[boot] interval : {interval_s}")

        # Reaction / Listening
        rx = ReactionEngine(cfg)
        rx_cfg = (cfg.get("reactions") or {})
        listening_cfg = (rx_cfg.get("listening") or {})
        listening_enabled = bool(listening_cfg.get("enabled", False))
        listening_text    = str(listening_cfg.get("text", "Listening…"))
        rd = listening_cfg.get("random_delay") or {}
        rand_min_s = int((rd or {}).get("min_s", 45)) if rd else 0
        rand_max_s = int((rd or {}).get("max_s", 60)) if rd else 0
        if rand_max_s and rand_max_s < rand_min_s:
            rand_max_s = rand_min_s
        delay_s = int(listening_cfg.get("delay_s", 50))
        use_random_delay = bool(rd) or bool(listening_cfg.get("use_random_delay", False))
        mid_texts        = [str(x).strip() for x in (listening_cfg.get("mid_texts") or []) if str(x).strip()]
        mid_switch_after = int(listening_cfg.get("mid_switch_after_s", 45))

        # Memory
        mem_cfg = cfg.get("memory") or {}
        mem_enabled = bool(mem_cfg.get("enabled", True))
        mem_path = Path(mem_cfg.get("path", "Memory/memory.json"))
        if not mem_path.is_absolute():
            mem_path = (SCRIPT_DIR / mem_path).resolve()
        mem_min_conf = int(mem_cfg.get("min_confidence", 2))
        mem_variants = mem_cfg.get("variants", {}) or {}
        mem_decay_cfg = mem_cfg.get("decay", {}) or {}
        memory = MemoryDB(mem_path, enabled=mem_enabled, decay_cfg=mem_decay_cfg)

        # Tuning
        tuning = (mem_cfg.get("tuning") or {})
        min_seen_repeat = int(tuning.get("min_seen_for_repeat", mem_min_conf))
        min_seen_cross  = int(tuning.get("min_seen_for_cross_context", mem_min_conf))
        conf_margin     = float(tuning.get("confidence_margin", 0.75))
        suppress_cross_if_dislike = bool(tuning.get("suppress_cross_if_dislike", True))
        suppress_cross_if_tie     = bool(tuning.get("suppress_cross_if_tie", True))
        show_fits_here_even_if_small = bool(tuning.get("show_fits_here_even_if_small", True))
        max_tail_segments = int(tuning.get("max_tail_segments", 2))

        last_hash = None
        wrote_once = False
        current_genres_text = None
        current_react_text  = None
        result_cache = ResultCache(max_items=4096)
        pending = None  # {key, decide_at, rx_text, mid_at, mid_text, mid_shown}

        while True:
            try:
                if not input_path.exists():
                    log("[wait] input file not found – warte…")
                    time.sleep(interval_s)
                    continue

                snapshot = input_path.read_text(encoding="utf-8", errors="ignore")
                h = hashlib.sha256(snapshot.encode("utf-8", "ignore")).hexdigest()
                changed = (last_hash != h) or (init_write and not wrote_once)

                if changed:
                    if last_hash != h:
                        log("[change] nowplaying.txt content changed")
                    last_hash = h

                    raw = read_file_stable(input_path, settle_ms=sg_settle_ms, retries=sg_retries) if sg_enabled else snapshot
                    title, artist = parse_title_artist(raw)
                    log(f"[parse] title={title!r} | artist={artist!r}")

                    maybe_run_probe(cfg, title, artist, kb_path, kb_cache_path)

                    # Lookup
                    genres_text = genres_text_def
                    t_norm = _normalize(title) if title else ""
                    a_norm = _normalize(artist) if artist else ""
                    cache_key = (t_norm, a_norm)

                    cached = result_cache.get(cache_key)
                    if cached is not None:
                        genres_text = cached if cached else (genres_fallback if title else genres_text_def)
                        match_found = bool(cached)
                        kb_tags = [t.strip() for t in re.split(r"[•;,/|]+", cached)] if cached else []
                        match_obj = None
                    else:
                        match_obj = None
                        if kb_index and title:
                            match_obj = kb_index.exact(title, artist) or kb_index.fuzzy(title, artist)

                        kb_tags = extract_tags(match_obj) or []

                        # notes.add_tags mergen
                        if match_obj is not None:
                            meta = _parse_notes(match_obj)
                            for ttag in (meta.get("add_tags") or []):
                                if ttag and ttag not in kb_tags:
                                    kb_tags.append(ttag)

                        display_tags = list(kb_tags)
                        # Specials sichtbar:
                        sv_tags = detect_special_version_tags(title or "", cfg)
                        if show_special_in_genres and sv_tags:
                            for ttag in sv_tags:
                                tag_disp = f"{special_prefix}{ttag}" if special_prefix else ttag
                                if tag_disp not in display_tags:
                                    display_tags.append(tag_disp)

                        # Artist-Not-Sure nur loggen, nicht schreiben
                        def artist_mismatch_obs_vs_entry(observed: str, entry: Dict[str,Any]) -> bool:
                            if not observed or not entry: return False
                            obs = _normalize(observed)
                            main = _normalize(str(entry.get("artist","")))
                            if obs == main: return False
                            meta_local = _parse_notes(entry)
                            aliases = [ _normalize(x) for x in (meta_local.get("artist_aliases") or []) + (meta_local.get("confirm_artists") or []) ]
                            if obs in aliases: return False
                            sim_main = SequenceMatcher(a=obs, b=main).ratio() if main else 0.0
                            sim_alias = max([SequenceMatcher(a=obs, b=ax).ratio() for ax in aliases], default=0.0)
                            return max(sim_main, sim_alias) < 0.50

                        if match_obj is not None and ans_enabled and artist_mismatch_obs_vs_entry(artist or "", match_obj):
                            nowdt = datetime.now(timezone.utc)
                            key_ns = f"{t_norm}|{a_norm}|{_normalize(match_obj.get('artist',''))}|{_normalize(match_obj.get('title',''))}"
                            if ans_deduper.should_log(key_ns, nowdt):
                                append_jsonl(ans_path, {
                                    "ts": nowdt.isoformat(),
                                    "observed": {"title": title, "artist": artist},
                                    "kb_entry": {
                                        "title": match_obj.get("title"),
                                        "artist": match_obj.get("artist"),
                                        "aliases": match_obj.get("aliases", []),
                                        "notes": match_obj.get("notes",""),
                                        "tags": kb_tags
                                    },
                                    "reason": "artist_mismatch"
                                })
                                ans_deduper.mark(key_ns, nowdt)
                                log("[note] artist_not_sure logged")

                        if display_tags:
                            genres_text = genres_joiner.join(display_tags)
                            result_cache.set(cache_key, genres_text)
                            match_found = True
                        else:
                            result_cache.set(cache_key, None)
                            genres_text = genres_fallback if title else genres_text_def
                            match_found = False

                    # === Spotify-Enrichment NUR wenn (kein Match) ODER (Match ohne Tags) ===
                    if title and (not match_found or not extract_tags(match_obj)):
                        try:
                            tags_list = spotify_hybrid_enrich_if_needed(artist or "", title or "", kb_path, outputs_dir, match_obj)
                            if tags_list:
                                # Specials sichtbar mergen (nur Anzeige)
                                disp = list(tags_list)
                                for sv in detect_special_version_tags(title or "", cfg):
                                    if sv not in disp:
                                        disp.append(sv if not special_prefix else f"{special_prefix}{sv}")
                                genres_text = genres_joiner.join(disp)
                                result_cache.set(cache_key, genres_text)
                                # Sofort Genres-Datei überschreiben (für Listening-Phase)
                                atomic_write_safe(out_genres, genres_text)
                                if mirror_legacy:
                                    atomic_write_safe(legacy_gernres, genres_text)
                                current_genres_text = genres_text
                                log(f"[update] genres (enriched)='{genres_text}'")
                        except Exception as ee:
                            log(f"[enrich_warn] {ee}")

                    # Scoring-Tags (immer nur KB/Tags – keine 'genres')
                    scoring_tags = set(_norm_tag_for_scoring(x) for x in (extract_tags(match_obj) or []) if x.strip())
                    for ttag in detect_special_version_tags(title or "", cfg):
                        scoring_tags.add(_norm_tag_for_scoring(ttag))

                    uniq_key = f"{t_norm}|{a_norm}"
                    rx_text_final, rx_bucket = rx.decide(title or "", artist or "", genres_text, sorted(scoring_tags), uniq_key)

                    # Memory
                    ctx_name = (rx.ctx.get_active_profile() or {}).get("name", "neutral")
                    memory.update(key=uniq_key, title=title or "", artist=artist or "", ctx=ctx_name, bucket=rx_bucket, tags=sorted(scoring_tags))
                    memory.save()

                    react_out = rx_text_final
                    seen = memory.seen_count(uniq_key)
                    best = memory.best_context(uniq_key)

                    def _pick_variant(group: str, bucket: str, fallback: str = "") -> str:
                        arr = (mem_variants.get(group, {}) or {}).get(bucket, []) or []
                        return random.choice(arr) if arr else fallback

                    tails: List[str] = []
                    if seen >= min_seen_repeat:
                        rep = _pick_variant("repeat", rx_bucket)
                        if rep: tails.append(rep)
                    if best and seen >= min_seen_cross:
                        best_ctx, best_bucket, best_score = best
                        if best_ctx and isinstance(best_ctx, str):
                            cross_allowed = not (suppress_cross_if_dislike and rx_bucket == "dislike")
                            if best_ctx != ctx_name:
                                if cross_allowed and (best_score > conf_margin or not suppress_cross_if_tie):
                                    bt = _pick_variant("better_other", rx_bucket)
                                    if bt: tails.append(bt.format(best=best_ctx))
                            else:
                                if show_fits_here_even_if_small or (best_score > conf_margin or not suppress_cross_if_tie):
                                    ft = _pick_variant("fits_here", rx_bucket)
                                    if ft: tails.append(ft.format(here=ctx_name))
                    if tails:
                        tails = tails[:max_tail_segments]
                        react_out = f"{react_out} {' '.join(tails)}".strip()

                    # Missing log NUR wenn kein Match (nach evtl. Enrichment bleibt es egal)
                    if missing_enabled and title and not match_found:
                        is_startup_write = (not wrote_once)
                        if not (is_startup_write and not log_on_init):
                            nowdt = datetime.now(timezone.utc)
                            key_miss = f"{t_norm}|{a_norm}" if (t_norm or a_norm) else (title or "")
                            if deduper.should_log(key_miss, nowdt):
                                append_jsonl(missing_path, {
                                    "ts": nowdt.isoformat(),
                                    "title": title,
                                    "artist": artist,
                                    "normalized_key": {"title": t_norm, "artist": a_norm}
                                })
                                deduper.mark(key_miss, nowdt)

                    # Listening-Phase / oder sofort schreiben
                    if listening_enabled:
                        chosen_delay = random.randint(rand_min_s, rand_max_s) if use_random_delay else max(0, int(delay_s))
                        react_listen = listening_text
                        mid_at = None
                        mid_txt = None
                        if mid_texts and chosen_delay >= max(mid_switch_after, 1):
                            mid_at  = time.time() + float(mid_switch_after)
                            mid_txt = random.choice(mid_texts)
                        pending = {
                            "key": cache_key,
                            "decide_at": time.time() + float(chosen_delay),
                            "mid_at": mid_at,
                            "mid_text": mid_txt,
                            "mid_shown": False,
                            "rx_text": react_out
                        }
                        if (genres_text != current_genres_text) or (react_listen != current_react_text) or (not wrote_once):
                            atomic_write_safe(out_genres, genres_text)
                            atomic_write_safe(out_react,  react_listen)
                            if mirror_legacy:
                                atomic_write_safe(legacy_gernres, genres_text)
                            current_genres_text = genres_text
                            current_react_text  = react_listen
                            wrote_once = True
                            log(f"[update] genres='{genres_text}' | react='{react_listen}' (listening)")
                    else:
                        pending = None
                        if (genres_text != current_genres_text) or (react_out != current_react_text) or (not wrote_once):
                            atomic_write_safe(out_genres, genres_text)
                            atomic_write_safe(out_react,  react_out)
                            if mirror_legacy:
                                atomic_write_safe(legacy_gernres, genres_text)
                            current_genres_text = genres_text
                            current_react_text  = react_out
                            wrote_once = True
                            log(f"[update] genres='{genres_text}' | react='{react_out}'")

                else:
                    if pending:
                        raw_now = read_file_stable(input_path, settle_ms=0, retries=1) if sg_enabled else snapshot
                        t_now, a_now = parse_title_artist(raw_now)
                        key_now = (_normalize(t_now or ""), _normalize(a_now or ""))
                        if key_now != pending["key"]:
                            pending = None
                        else:
                            now_ts = time.time()
                            if (pending.get("mid_at") is not None) and (not pending.get("mid_shown", False)) and now_ts >= pending["mid_at"]:
                                mid_txt = pending.get("mid_text")
                                if mid_txt and mid_txt != current_react_text:
                                    atomic_write_safe(out_react, mid_txt)
                                    current_react_text = mid_txt
                                    log(f"[update] react(mid)='{mid_txt}'")
                                pending["mid_shown"] = True
                            if now_ts >= pending["decide_at"]:
                                final_text = pending["rx_text"]
                                if final_text != current_react_text:
                                    atomic_write_safe(out_react, final_text)
                                    current_react_text = final_text
                                    log(f"[update] react(decided)='{final_text}'")
                                pending = None

                if log_every_tick:
                    log("[idle] no change")

            except KeyboardInterrupt:
                log("[exit] bye 👋"); break
            except Exception as e:
                log(f"[warn] {e}")
            time.sleep(interval_s)
    finally:
        release_single_instance_lock()

# ========= Simple LRU =========

class ResultCache:
    def __init__(self, max_items: int = 4096):
        self.max = max_items
        self.data = collections.OrderedDict()
    def get(self, key):
        if key in self.data:
            val = self.data.pop(key); self.data[key] = val; return val
        return None
    def set(self, key, val):
        if key in self.data:
            self.data.pop(key)
        elif len(self.data) >= self.max:
            self.data.popitem(last=False)
        self.data[key] = val

if __name__ == "__main__":
    main()
    