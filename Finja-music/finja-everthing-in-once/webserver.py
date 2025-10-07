"""
======================================================================
            Finja's Brain & Knowledge Core – All-in-One Webserver
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (All-in-One Modul)

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Startet einen lokalen Webserver als zentrale Steuereinheit.
  • Bietet API-Endpunkte zum Aktivieren/Deaktivieren von Musikquellen (TruckersFM, Spotify, RTL, MDR).
  • Ermöglicht das Starten von Hilfsskripten (DB bauen, Songs anreichern) per Web-Aufruf.
  • Stellt eine Web-UI zur Verfügung, um Künstler-Konflikte zu lösen.
  • Dient als Backend für die `Musik.html` Steuerzentrale.

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import http.server
import socketserver
import os
import json
import subprocess
import time
import threading
import hashlib
from pathlib import Path
import sys
import glob
import csv
import re
import random
import tempfile
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import pickle
from typing import Any, List, Dict, Tuple, Optional, Callable
import signal

# --- NEU: Für TruckersFM-Abfrage ---
import requests
from bs4 import BeautifulSoup

# --- NEU: Für Spotify Enrich Missing ---
import urllib.request
import urllib.parse
import urllib.error
import urllib

# --- GRUNDEINSTELLUNGEN ---
PORT = 8022
SCRIPT_DIR = Path(__file__).resolve().parent
LOCK_PATH = SCRIPT_DIR / ".finja_server.lock"

# --- ORDNERSTRUKTUR ---
OBSHTML_DIR = SCRIPT_DIR / "OBSHTML"
EXPORTS_DIR = SCRIPT_DIR / "exports"
NOWPLAYING_DIR = SCRIPT_DIR / "Nowplaying"
SONGSDB_DIR = SCRIPT_DIR / "SongsDB"
CONFIG_DIR = SCRIPT_DIR / "config"
MEMORY_DIR = SCRIPT_DIR / "Memory"
CACHE_DIR = SCRIPT_DIR / "cache"

# --- GLOBALE STEUERUNG ---
active_writer: Optional['Writer'] = None
writer_stop_event = threading.Event()
active_nowplaying_thread: Optional[threading.Thread] = None
nowplaying_stop_event = threading.Event()

# ##############################################################################
#  BEREICH 1: BUILD-DB LOGIK
# ##############################################################################
@dataclass
class Track:
    title: str; artist: str; album: str = ""; source: str = ""

def build_db_norm(s: str) -> str: return re.sub(r"\s+", " ", s or "").strip()
def build_db_strip_parens(s: str) -> str: return re.sub(r"\s*[\(\[\{].*?[\)\]\}]\s*", " ", s or "").strip()
def build_db_basic_aliases(title: str) -> list[str]:
    t0 = title or ""; t1 = build_db_strip_parens(t0)
    return sorted([a for a in {t0, t1, t0.lower(), t1.lower()} if a])
def build_db_atomic_write_text(path: Path, text: str, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding=encoding, dir=str(path.parent)) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), str(path))
def parse_row_csv(row: dict[str, str]) -> Track | None:
    title = (row.get("Track Name") or row.get("Title") or "").strip()
    artist = (row.get("Artist Name(s)") or row.get("Artist") or "").strip()
    if not title or not artist: return None
    return Track(title=title, artist=artist, album=(row.get("Album Name") or row.get("Album") or "").strip())
def read_input_csvs(paths: list[str]) -> list[Track]:
    items = []
    for g in paths:
        for fp_str in glob.glob(g):
            fp = Path(fp_str)
            if fp.suffix.lower() == ".csv":
                with fp.open("r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tr = parse_row_csv(row)
                        if tr: tr.source = str(fp); items.append(tr)
    return items
def track_to_entry(tr: Track) -> dict:
    return {"title": build_db_norm(tr.title), "artist": build_db_norm(tr.artist), "album": build_db_norm(tr.album), "aliases": build_db_basic_aliases(tr.title), "tags": [], "notes": ""}
def kb_key_of(entry: dict) -> str: return f"{(entry.get('title') or '').lower()}::{(entry.get('artist') or '').lower()}"
def merge_entry(base: dict, newe: dict) -> dict:
    out = dict(base)
    if not (out.get("album") or "").strip(): out["album"] = build_db_norm(newe.get("album") or "")
    existing_aliases = {a.lower() for a in out.get("aliases", [])}
    for alias in newe.get("aliases", []):
        if alias.lower() not in existing_aliases: out.get("aliases", []).append(alias)
    return out
def execute_build_spotify_db():
    print("[DB Builder] Prozess gestartet...")
    try:
        kb_path = SONGSDB_DIR / "songs_kb.json"
        existing_kb = json.load(kb_path.open("r", encoding="utf-8")) if kb_path.exists() else []
        print(f"[DB Builder] {len(existing_kb)} bestehende Einträge geladen.")
        tracks = read_input_csvs([str(EXPORTS_DIR / "*.csv")])
        if not tracks: print("[DB Builder] Keine neuen Tracks in 'exports' gefunden."); return
        print(f"[DB Builder] {len(tracks)} Tracks aus CSV-Dateien gelesen.")
        kb_index_map = {kb_key_of(e): e for e in existing_kb}
        for tr in tracks:
            new_entry = track_to_entry(tr); key = kb_key_of(new_entry)
            kb_index_map[key] = merge_entry(kb_index_map[key], new_entry) if key in kb_index_map else new_entry
        merged_list = sorted(kb_index_map.values(), key=lambda e: (e.get("artist","").lower(), e.get("title","").lower()))
        build_db_atomic_write_text(kb_path, json.dumps(merged_list, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[DB Builder] Erfolg! DB auf {len(merged_list)} Einträge aktualisiert. Gespeichert in: {kb_path}")
    except Exception as e: print(f"[DB Builder] FEHLER: {e}", file=sys.stderr)


# ##############################################################################
#  BEREICH 2: DAS GEHIRN & SEINE HELFER (VOLLSTÄNDIGE VERSION - aus dem alten Skript)
# ##############################################################################
def log(msg: str): print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

def atomic_write_safe(target: Path, text: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f"{target.suffix}.tmp")
    tmp.write_text(f"{(text or '').strip()}\n", encoding="utf-8")
    os.replace(tmp, target)

def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

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

def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"[config error] {path} :: {e}")

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

# --- KB und Index ---
def load_songs_kb(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"songs_kb not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("songs"), list):
        return data["songs"]
    if isinstance(data, list):
        return data
    raise ValueError("songs_kb.json hat ein unerwartetes Format")

def _parse_notes(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unterstützt:
      - JSON im notes:
        { "artist_aliases": [...], "allow_title_only": true, "max_ambiguous_candidates": 3, "add_tags": [...] }
      - Freitext mit:
        "Bestätigt: A, B" -> confirm_artists
        "Nicht bestätigt: X, Y" -> deny_artists
    """
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
            # fällt zurück auf Freitext
            pass
    # Freitext-Parsing (auch zusätzlich zum JSON möglich)
    def _grab(label: str) -> List[str]:
        # Suche "Label: <liste>" (kommasepariert)
        m = re.search(label + r"\s*:\s*(.+)", s, flags=re.IGNORECASE)
        if not m: return []
        val = m.group(1)
        # bis zum nächsten Label abschneiden
        nxt = re.search(r"(Bestätigt|Nicht\s*bestätigt)\s*:", val, flags=re.IGNORECASE)
        if nxt:
            val = val[:nxt.start()].strip()
        items = [x.strip() for x in re.split(r"[;,]", val) if x.strip()]
        return items
    conf = _grab(r"Bestätigt")
    deny = _grab(r"Nicht\s*bestätigt")
    if conf:
        out["confirm_artists"] = [x.lower() for x in conf]
    if deny:
        out["deny_artists"] = [x.lower() for x in deny]
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
            # artist_aliases & confirm_artists aus notes ebenfalls indexieren
            meta = _parse_notes(e)
            for aa in (meta.get("artist_aliases") or []) + (meta.get("confirm_artists") or []):
                self._add(e, e.get(title_key), aa)
    def _add(self, e: Dict[str, Any], tval: Any, aval: Any):
        t = _normalize(str(tval or ""))
        a = _normalize(str(aval or ""))
        if not t:
            return
        self.by_title.setdefault(t, []).append(e)
        if a:
            self.by_title_artist[(t, a)] = e
    def exact(self, title: Optional[str], artist: Optional[str]) -> Optional[Dict[str, Any]]:
        if not title:
            return None
        t = _normalize(title)
        a = _normalize(artist) if artist else ""
        if not t:
            return None
        # exakt (inkl. Aliases via _add)
        if a and (t, a) in self.by_title_artist:
            return self.by_title_artist[(t, a)]
        # eindeutig per Titel?
        entries = self.by_title.get(t) or []
        if len(entries) == 1:
            return entries[0]
        # allow_title_only per notes
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
        if not title:
            return None
        t = _normalize(title)
        a = _normalize(artist) if artist else ""
        if not t:
            return None
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

def extract_genres(entry: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    if not entry:
        return None
    for key in ("genres", "genre", "primary_genres", "tags"):
        if key in entry:
            g = entry[key]
            if isinstance(g, str):
                parts = [x.strip() for x in re.split(r"[;,/]", g) if x.strip()]
                return parts or None
            if isinstance(g, list):
                parts = [str(x).strip() for x in g if str(x).strip()]
                return parts or None
    return None

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
            obj = pickle.loads(cache_path.read_bytes())
            cached_hash = obj.get("json_hash") or obj.get("json_md5")
            if isinstance(obj, dict) and cached_hash == json_hash and "index" in obj:
                return obj["index"]
        except Exception:
            pass
    entries = load_songs_kb(kb_json_path)
    idx = KBIndex(entries)
    if cache_path:
        try:
            payload = {"json_hash": json_hash, "index": idx}
            cache_path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:
            pass
    return idx

# --- Parser ---
DASH_SEPS = [" — ", " – ", " - ", " ~ ", " | ", " • "]
def parse_title_artist(text: str) -> Tuple[Optional[str], Optional[str]]:
    text = (text or "").strip()
    if not text:
        return None, None
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
    for sep in DASH_SEPS:
        if sep in line:
            left, right = [p.strip() for p in line.split(sep, 1)]
            if left and right:
                return right, left
    return line or None, None

# --- LRU Cache ---
from collections import OrderedDict
class ResultCache:
    def __init__(self, max_items: int = 4096):
        self.max = max_items
        self.data = OrderedDict()
    def __contains__(self, key):
        """Ermöglicht 'key in result_cache'."""
        return key in self.data
    def get(self, key):
        if key in self.data:
            val = self.data.pop(key); self.data[key] = val; return val
        return None
    def set(self, key, val):
        if key in self: # <-- Jetzt funktioniert 'in self'
            self.data.pop(key)
        elif len(self.data) >= self.max:
            self.data.popitem(last=False)
        self.data[key] = val

# --- Missing / Not-Sure Dedupe ---
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

# --- Context Manager ---
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
        if not self.enabled:
            return
        try:
            mtime = self.contexts_path.stat().st_mtime if self.contexts_path.exists() else 0
        except Exception:
            mtime = 0
        if (not force) and (mtime <= self._last_load):
            return
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
        if not self.enabled or not self.state_path:
            return
        now = time.time()
        if (not force) and (now - self._last_state_read) < max(1, int(self.refresh_s)):
            return
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

# --- Special-Version-Tag Detection ---
def detect_special_version_tags(title: str, cfg: dict) -> List[str]:
    sv = (cfg.get("special_version_tags") or {})
    if not sv: return []
    t = (title or "").lower()
    def phrase_to_pattern(phrase: str) -> str:
        tokens = re.split(r"\s+", phrase.strip().lower())
        tokens = [re.escape(tok) for tok in tokens if tok]
        if not tokens:
            return ""
        return r"\b" + r"[\s\-]*".join(tokens) + r"\b"
    tags = []
    for tag_name, patterns in sv.items():
        arr = patterns if isinstance(patterns, list) else [patterns]
        for p in arr:
            p = str(p or "").strip()
            if not p:
                continue
            pat = phrase_to_pattern(p)
            if pat and re.search(pat, t, flags=re.IGNORECASE):
                tags.append(tag_name.lower())
                break
    return tags

# --- Reaction Engine ---
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
        # NEW: artist_preferences (score bias + probabilistic flip)
        self.artist_prefs: Dict[str, Dict[str, Any]] = {}
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
            # artist_preferences from reactions.json (optional)
            ap = (data.get("artist_preferences") or {})
            # normalize
            norm_map: Dict[str, Dict[str, Any]] = {}
            for name, cfg_ap in ap.items():
                if not isinstance(cfg_ap, dict): continue
                k = _normalize(name)
                if not k: continue
                entry = {}
                # allow both "score_bias" and legacy "like_weight"
                if "score_bias" in cfg_ap:
                    try: entry["score_bias"] = float(cfg_ap.get("score_bias", 0.0))
                    except: pass
                elif "like_weight" in cfg_ap:
                    try: entry["score_bias"] = float(cfg_ap.get("like_weight", 0.0))
                    except: pass
                # flip can be dict {"dislike": 0.4, "neutral": 0.1, "like": 0.0}
                flip = cfg_ap.get("flip", {})
                if isinstance(flip, dict):
                    entry["flip"] = {k2: max(0.0, min(1.0, float(v))) for k2, v in flip.items() if k2 in ("like","neutral","dislike")}
                self.artist_prefs[k] = entry
        except Exception as e:
            log(f"[react] using defaults (load warn: {e})")
        self.ctx = ContextManager(rx_cfg)
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
    @staticmethod
    def _pick_by_probs(probs: dict) -> str:
        keys = ["like", "neutral", "dislike"]
        vals = [max(0.0, float(probs.get(k, 0.0))) for k in keys]
        s = sum(vals) or 1.0
        vals = [v / s for v in vals]
        r = random.random()
        cum = 0.0
        for k, v in zip(keys, vals):
            cum += v
            if r <= cum:
                return k
        return keys[-1]
    def _artist_pref_for(self, artist_norm: str) -> Optional[Dict[str, Any]]:
        if not self.artist_prefs or not artist_norm: return None
        for key, cfg in self.artist_prefs.items():
            if key and key in artist_norm:
                return cfg
        return None
    def _apply_pref_flip(self, current_bucket: str, pref: Dict[str, Any]) -> str:
        """Optional probabilistic flip to a target bucket, e.g. {'dislike': 0.4}"""
        flip = pref.get("flip")
        if not isinstance(flip, dict) or not flip:
            return current_bucket
        # remaining probability -> stay
        p_to = {k: max(0.0, min(1.0, float(v))) for k, v in flip.items() if k in ("like","neutral","dislike")}
        p_stay = max(0.0, 1.0 - sum(p_to.values()))
        keys = list(p_to.keys()) + ["__stay__"]
        probs = list(p_to.values()) + [p_stay]
        # normalize just in case numerical drift
        s = sum(probs) or 1.0
        probs = [p/s for p in probs]
        r = random.random(); acc = 0.0
        for k, p in zip(keys, probs):
            acc += p
            if r <= acc:
                if k == "__stay__": return current_bucket
                return k
        return current_bucket
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
        artist_bias_present = any(x and x in a for x in self.bias["like_artists"]) or any(x and x in a for x in self.bias["dislike_artists"])
        if self.unknown_enabled and not tset and not artist_bias_present:
            bucket = self._pick_by_probs(self.unknown_probs)
            if self.debug:
                log(f"[react] unknown policy -> {bucket} (ctx={ctx.get('name','neutral')})")
            bias_val = float(bucket_bias.get(bucket, 0.0))
            if bias_val > 0 and bucket == "neutral": return "like"
            if bias_val < 0 and bucket == "neutral": return "dislike"
            # even unknowns can be post-flipped by artist_prefs
            pref = self._artist_pref_for(a)
            if pref: bucket = self._apply_pref_flip(bucket, pref)
            return bucket
        score = 0.0
        for tg in self.bias["like_tags"]:
            if tg in tset: score += self.weights["tag_like"]
        for tg in self.bias["dislike_tags"]:
            if tg in tset: score -= self.weights["tag_dislike"]
        for ar in self.bias["like_artists"]:
            if ar and ar in a: score += self.weights["artist_like"]
        for ar in self.bias["dislike_artists"]:
            if ar and ar in a: score -= self.weights["artist_dislike"]
        for tg in tset:
            score += float(tag_w.get(tg, 0.0))
        for name, w in art_w.items():
            if name and name in a:
                try: score += float(w)
                except: pass
        # NEW: artist_preferences score bias
        pref = self._artist_pref_for(a)
        if pref and isinstance(pref.get("score_bias"), (int, float)):
            score += float(pref.get("score_bias", 0.0))
        if score > 0:
            score += float(bucket_bias.get("like", 0.0))
        elif score < 0:
            score += float(bucket_bias.get("dislike", 0.0))
        else:
            score += float(bucket_bias.get("neutral", 0.0))
        base_bucket = "like" if score > 0 else ("dislike" if score < 0 else "neutral")
        if self.explore_enabled and random.random() < max(0.0, min(1.0, self.explore_chance)):
            bucket = self._pick_by_probs(self.explore_weights)
            if self.debug:
                log(f"[react] explore({self.explore_chance:.2f}) -> {bucket} (base={base_bucket}, ctx={ctx.get('name','neutral')})")
        else:
            bucket = base_bucket
        # NEW: probabilistic flip based on artist_preferences
        if pref:
            bucket = self._apply_pref_flip(bucket, pref)
        if self.debug:
            log(f"[react] ctx={ctx.get('name','neutral')} score={score:.2f} -> {bucket}")
        return bucket
    def _check_special(self, title: str, artist: str) -> Optional[Dict[str, str]]:
        t = self._norm(title); a = self._norm(artist)
        for sp in self.special:
            t_ok = all(sub in t for sub in (sp.get("title_contains") or [])) if sp.get("title_contains") else True
            a_ok = all(sub in a for sub in (sp.get("artist_contains") or [])) if sp.get("artist_contains") else True
            if t_ok and a_ok: return sp
        return None
    def decide(self, title: str, artist: str, genres_text: str, tags_for_scoring: List[str], uniq_key: str) -> Tuple[str, str]:
        if not self.enabled:
            return ("", "neutral")
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

# --- Memory ---
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
        if not self.decay_enabled:
            return
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
        if not self.enabled:
            return
        now = datetime.now(timezone.utc)
        s = self._song(key, title, artist)
        existing = set([str(x).lower().strip() for x in s.get("tags", []) if str(x).strip()])
        for t in (tags or []):
            tt = str(t).lower().strip()
            if tt:
                existing.add(tt)
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
            if best is None:
                best = cand
            else:
                if (cand[2] > best[2]) or (cand[2] == best[2] and cand[3] > best[3]):
                    best = cand
        if not best: return None
        return (best[0], best[1], best[2])
    def save(self):
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log(f"[memory] save warn: {e}")

# ##############################################################################
#  BEREICH 3: TRUCKERSFM NOWPLAYING ABFRAGE (als Funktion)
# ##############################################################################
URL = "https://truckers.fm/listen"

def fetch_nowplaying(session, timeout=10):
    """Holt den aktuellen Song von TruckersFM."""
    try:
        r = session.get(URL, headers={"User-Agent":"Mozilla/5.0"}, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title_el = soup.find(id="song-title")
        artist_el = soup.find(id="song-artist")
        if not title_el or not artist_el: return None
        title = title_el.get_text(strip=True)
        artist = artist_el.get_text(strip=True)
        if not title or not artist: return None
        return f"{title} — {artist}"
    except Exception as e:
        log(f"[nowplaying] Fehler beim Abrufen: {e}")
        return None

def nowplaying_main_loop(output_file: Path, interval: int, stop_event: threading.Event):
    """
    Die Hauptschleife für das Abrufen von TruckersFM.
    Läuft in einem eigenen Thread.
    """
    log("[nowplaying] Starte TruckersFM Abfrage-Thread...")
    sess = requests.Session()
    last = None
    while not stop_event.is_set():
        try:
            cur = fetch_nowplaying(sess)
            if cur and cur != last:
                atomic_write_safe(output_file, cur)
                log(f"[nowplaying] Aktualisiert: {cur}")
                last = cur
        except Exception as e:
            log(f"[nowplaying] Unerwarteter Fehler: {e}")
        if stop_event.wait(timeout=interval): # Warte auf Stop-Event oder Timeout
            break
    log("[nowplaying] TruckersFM Abfrage-Thread beendet.")

# ##############################################################################
#  BEREICH 4: SPOTIFY NOWPLAYING ABFRAGE (als Funktion)
# ##############################################################################

SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_NOW_URL = 'https://api.spotify.com/v1/me/player/currently-playing'

def refresh_spotify_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """
    Holt ein neues Access-Token von Spotify anhand des Refresh-Tokens.
    """
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    response = requests.post(SPOTIFY_TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()
    token_data = response.json()
    return token_data['access_token']

def get_spotify_now_playing(access_token: str) -> Optional[str]:
    """
    Fragt die aktuelle Wiedergabe von Spotify ab.
    Gibt 'Titel — Künstler' als String zurück oder None.
    """
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'additional_types': 'track'}
    response = requests.get(SPOTIFY_NOW_URL, headers=headers, params=params, timeout=10)
    if response.status_code == 204:
        # Keine Wiedergabe
        return None
    response.raise_for_status()
    data = response.json()
    if not data or data.get('currently_playing_type') != 'track':
        # Kein Track wird abgespielt
        return None
    item = data.get('item') or {}
    name = item.get('name', '')
    artists = ', '.join(a.get('name', '') for a in item.get('artists', []))
    if name and artists:
        return f"{name} — {artists}"
    return None

def spotify_nowplaying_main_loop(output_file: Path, config_path: Path, interval: int, stop_event: threading.Event):
    """
    Die Hauptschleife für das Abrufen der aktuellen Spotify-Wiedergabe.
    Läuft in einem eigenen Thread.
    """
    log("[spotify_nowplaying] Starte Spotify-Abfrage-Thread...")
    # Lade die Spotify-Konfiguration
    try:
        with config_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        spotify_cfg = cfg.get("spotify", {})
        client_id = spotify_cfg.get("client_id")
        client_secret = spotify_cfg.get("client_secret")
        refresh_token = spotify_cfg.get("refresh_token")
        if not all([client_id, client_secret, refresh_token]):
            raise ValueError("Spotify-Konfiguration unvollständig: client_id, client_secret, refresh_token benötigt.")
    except Exception as e:
        log(f"[spotify_nowplaying] Fehler beim Laden der Konfiguration {config_path}: {e}")
        return

    last = None
    while not stop_event.is_set():
        try:
            access_token = refresh_spotify_token(client_id, client_secret, refresh_token)
            cur = get_spotify_now_playing(access_token)
            if cur and cur != last:
                atomic_write_safe(output_file, cur)
                log(f"[spotify_nowplaying] Aktualisiert: {cur}")
                last = cur
            elif not cur and last is not None:
                # Falls vorher was lief und jetzt nichts mehr, schreibe leer
                # Optional: Du könntest auch entscheiden, die Datei leer zu lassen oder ein spezielles Zeichen zu setzen
                atomic_write_safe(output_file, "")
                log(f"[spotify_nowplaying] Keine Wiedergabe, Datei geleert.")
                last = None
        except Exception as e:
            log(f"[spotify_nowplaying] Fehler bei der Abfrage: {e}")
        if stop_event.wait(timeout=interval): # Warte auf Stop-Event oder Timeout
            break
    log("[spotify_nowplaying] Spotify-Abfrage-Thread beendet.")

# ##############################################################################
#  BEREICH 4: DIE NEUE WRITER-KLASSE (kapselt die alte main-Logik) - KORRIGIERT & FINAL
# ##############################################################################

class Writer:
    """
    Diese Klasse kapselt die komplette Logik eines einzelnen Writers (z.B. für TruckersFM).
    Sie wird mit einer Konfigurationsdatei ODER einem Konfigurations-Dictionary initialisiert und führt die Hauptschleife aus.
    """
    def __init__(self, config_path: Optional[Path] = None, config_data: Optional[dict] = None):
        if config_path is not None:
            self.config_path = config_path
            # Laden der Konfiguration aus der Datei
            self.cfg = load_config(self.config_path)
            # Generiere log_prefix aus Dateinamen
            self.log_prefix = f"[Writer-{config_path.stem}]"
            log(f"{self.log_prefix} Lade Konfiguration: {self.config_path}")
        elif config_data is not None:
            self.config_path = None # Kein Pfad, wenn Daten direkt übergeben wurden
            self.cfg = config_data
            # Generiere log_prefix aus einem Standardwert oder einem Schlüssel in config_data
            # z.B. config_data.get("name", "Dynamic")
            self.log_prefix = f"[Writer-Dynamic]" # Anpassen, da kein Dateiname
            log(f"{self.log_prefix} Verwende übergebene Konfiguration.")
        else:
            raise ValueError("Entweder 'config_path' oder 'config_data' muss angegeben werden.")

        # Initialisieren der Pfade und Komponenten basierend auf der Konfiguration
        input_path_cfg = self.cfg.get("input_path", "nowplaying.txt")
        self.input_path = Path(input_path_cfg)
        if not self.input_path.is_absolute():
            self.input_path = (SCRIPT_DIR / self.input_path).resolve()

        # KORRIGIERT: Verwende einen relativen Standardpfad, der sich auf SCRIPT_DIR bezieht
        default_outputs_rel = Path("outputs") # Relativer Pfad
        outputs_dir_cfg = self.cfg.get("fixed_outputs", str(default_outputs_rel))
        self.outputs_dir = Path(outputs_dir_cfg)
        if not self.outputs_dir.is_absolute():
            self.outputs_dir = (SCRIPT_DIR / self.outputs_dir).resolve() # <-- Jetzt absolut relativ zu SCRIPT_DIR

        self.interval_s       = float(self.cfg.get("interval_s", 2.0))
        self.init_write       = bool(self.cfg.get("init_write", True))
        self.genres_text_def  = str(self.cfg.get("genres_template", "Pop • Nightcore • Speed Up"))
        self.genres_fallback  = str(self.cfg.get("genres_fallback", "Neuer Song :) hören wir mal rein"))
        self.genres_joiner    = str(self.cfg.get("genres_joiner", " • "))
        self.mirror_legacy    = bool(self.cfg.get("mirror_legacy_gernres", True))
        self.log_every_tick   = bool(self.cfg.get("log_every_tick", False))
        self.show_special_in_genres = bool(self.cfg.get("show_special_version_in_genres", True))
        self.special_prefix = str(self.cfg.get("special_version_prefix", ""))

        # Sync-Guard
        sync_guard_cfg = self.cfg.get("sync_guard") or {}
        self.sg_enabled   = bool(sync_guard_cfg.get("enabled", True))
        self.sg_settle_ms = int(sync_guard_cfg.get("settle_ms", 200))
        self.sg_retries   = int(sync_guard_cfg.get("retries", 3))

        # KB
        kb_path_cfg = self.cfg.get("songs_kb_path", "songs_kb.json")
        self.kb_path = Path(kb_path_cfg)
        if not self.kb_path.is_absolute(): self.kb_path = (SCRIPT_DIR / self.kb_path).resolve()
        kb_cache_cfg = self.cfg.get("kb_index_cache_path", None)
        self.kb_cache_path = Path(kb_cache_cfg).resolve() if kb_cache_cfg else None

        # Missing-Logger
        missing_cfg      = self.cfg.get("missing_log") or {}
        self.missing_enabled  = bool(missing_cfg.get("enabled", False))
        missing_path     = Path(missing_cfg.get("path", "missing_songs_log.jsonl"))
        if not missing_path.is_absolute(): missing_path = (SCRIPT_DIR / missing_path).resolve()
        self.missing_path = missing_path
        self.log_on_init      = bool(missing_cfg.get("log_on_init", False))
        dedupe_hours     = int(missing_cfg.get("dedupe_hours", 12))
        state_path       = Path(missing_cfg.get("state_path", ".missing_seen.json"))
        if not state_path.is_absolute(): state_path = (SCRIPT_DIR / state_path).resolve()
        self.deduper = MissingDedupe(state_path, ttl_hours=dedupe_hours)

        # Artist-Not-Sure-Logger (eigene Dedupe)
        ans_cfg = self.cfg.get("artist_not_sure") or {}
        self.ans_enabled = bool(ans_cfg.get("enabled", True))
        ans_path = Path(ans_cfg.get("path", "missingsongs/artist_not_sure.jsonl"))
        if not ans_path.is_absolute(): ans_path = (SCRIPT_DIR / ans_path).resolve()
        self.ans_path = ans_path
        ans_dedupe_state = Path(ans_cfg.get("state_path", "missingsongs/.artist_not_sure_seen.json"))
        if not ans_dedupe_state.is_absolute(): ans_dedupe_state = (SCRIPT_DIR / ans_dedupe_state).resolve()
        ans_dedupe_hours = int(ans_cfg.get("dedupe_hours", 24))
        self.ans_deduper = MissingDedupe(ans_dedupe_state, ttl_hours=ans_dedupe_hours)

        self.out_genres = (self.outputs_dir / "obs_genres.txt").resolve()
        self.out_react  = (self.outputs_dir / "obs_react.txt").resolve()
        self.legacy_gernres = (self.outputs_dir / "gernres_template.txt").resolve()

        # KB laden
        self.kb_index = None
        try:
            self.kb_index = load_or_build_kb_index(self.kb_path, self.kb_cache_path)
            bucket_count = len(getattr(self.kb_index, "by_title", {}))
            tag_cache_note = " [cache]" if self.kb_cache_path and self.kb_cache_path.exists() else ""
            log(f"{self.log_prefix} KB ready: {self.kb_path} (buckets={bucket_count}){tag_cache_note}")
        except Exception as e:
            log(f"{self.log_prefix} KB load warn: {e} (weiter mit Fallbacks)")

        # Reaction Engine + Listening-Phase
        rx_cfg = (self.cfg.get("reactions") or {})
        self.rx = ReactionEngine(self.cfg)
        listening_cfg = (rx_cfg.get("listening") or {})
        self.listening_enabled = bool(listening_cfg.get("enabled", False))
        self.listening_text    = str(listening_cfg.get("text", "Listening…"))
        rd = listening_cfg.get("random_delay") or {}
        self.rand_min_s = int(rd.get("min_s", 45)) if rd else 0
        self.rand_max_s = int(rd.get("max_s", 60)) if rd else 0
        if self.rand_max_s and self.rand_max_s < self.rand_min_s:
            self.rand_max_s = self.rand_min_s
        self.delay_s = int(listening_cfg.get("delay_s", 50))
        self.use_random_delay = bool(rd) or bool(listening_cfg.get("use_random_delay", False))
        self.mid_texts        = [str(x).strip() for x in (listening_cfg.get("mid_texts") or []) if str(x).strip()]
        self.mid_switch_after = int(listening_cfg.get("mid_switch_after_s", 45))

        # Memory
        mem_cfg = self.cfg.get("memory") or {}
        mem_enabled = bool(mem_cfg.get("enabled", True))
        mem_path = Path(mem_cfg.get("path", "Memory/memory.json"))
        if not mem_path.is_absolute():
            mem_path = (SCRIPT_DIR / mem_path).resolve()
        self.mem_min_conf = int(mem_cfg.get("min_confidence", 2))
        self.mem_variants = mem_cfg.get("variants", {}) or {}
        mem_decay_cfg = mem_cfg.get("decay", {}) or {}
        self.memory = MemoryDB(mem_path, enabled=mem_enabled, decay_cfg=mem_decay_cfg)

        # Tuning
        tuning = (mem_cfg.get("tuning") or {})
        self.min_seen_repeat = int(tuning.get("min_seen_for_repeat", self.mem_min_conf))
        self.min_seen_cross  = int(tuning.get("min_seen_for_cross_context", self.mem_min_conf))
        self.conf_margin     = float(tuning.get("confidence_margin", 0.75))
        self.suppress_cross_if_dislike = bool(tuning.get("suppress_cross_if_dislike", True))
        self.suppress_cross_if_tie     = bool(tuning.get("suppress_cross_if_tie", True))
        self.show_fits_here_even_if_small = bool(tuning.get("show_fits_here_even_if_small", True))
        self.max_tail_segments = int(tuning.get("max_tail_segments", 2))

        # Zustand
        self.last_hash = None
        self.wrote_once = False
        self.current_genres_text = None
        self.current_react_text  = None
        self.result_cache = ResultCache(max_items=4096)
        self.pending = None  # {key, decide_at, rx_text, mid_at, mid_text, mid_shown}

        # NEU: Initialisiere das stop_event
        self.stop_event = threading.Event()
        self.thread = None # Wird in start() gesetzt

    # NEU: Methode run(self)
    def run(self):
        """
        Die Hauptschleife des Writers. Diese Methode wird in einem Thread ausgeführt.
        """
        log(f"{self.log_prefix} Starte Hauptschleife...")
        while not self.stop_event.is_set():
            try:
                if not self.input_path.exists():
                    log(f"{self.log_prefix} [wait] input file not found – warte…")
                    time.sleep(self.interval_s)
                    continue

                snapshot = self.input_path.read_text(encoding="utf-8", errors="ignore")
                h = hashlib.sha256(snapshot.encode("utf-8", "ignore")).hexdigest()
                changed = (self.last_hash != h) or (self.init_write and not self.wrote_once)

                if changed:
                    if self.last_hash != h:
                        log(f"{self.log_prefix} [change] nowplaying.txt content changed")
                    self.last_hash = h
                    raw = read_file_stable(self.input_path, settle_ms=self.sg_settle_ms, retries=self.sg_retries) if self.sg_enabled else snapshot
                    title, artist = parse_title_artist(raw)
                    log(f"{self.log_prefix} [parse] title={title!r} | artist={artist!r}")

                    # --- Der Rest der Logik aus dem alten main() ---
                    # Lookup Genres (+ optional Specials sichtbar)
                    genres_text = self.genres_text_def
                    t_norm = _normalize(title) if title else ""
                    a_norm = _normalize(artist) if artist else ""
                    cache_key = (t_norm, a_norm)
                    cached = self.result_cache.get(cache_key)
                    if cached is not None:
                        genres_text = cached if cached else (self.genres_fallback if title else self.genres_text_def)
                        match_found = bool(cached)
                        kb_tags = [t.strip() for t in re.split(r"[•;,/|]+", cached)] if cached else []
                    else:
                        match = None
                        if self.kb_index and title:
                            # try exact -> fuzzy
                            match = self.kb_index.exact(title, artist) or self.kb_index.fuzzy(title, artist)
                        kb_tags_opt = extract_genres(match) if match is not None else None
                        kb_tags = kb_tags_opt or []
                        # notes.add_tags mergen
                        if match is not None:
                            meta = _parse_notes(match)
                            for ttag in (meta.get("add_tags") or []):
                                if ttag and ttag not in kb_tags:
                                    kb_tags.append(ttag)
                        display_tags = list(kb_tags)
                        sv_tags = detect_special_version_tags(title or "", self.cfg)
                        if self.show_special_in_genres and sv_tags:
                            for ttag in sv_tags:
                                tag_disp = f"{self.special_prefix}{ttag}" if self.special_prefix else ttag
                                if tag_disp not in display_tags:
                                    display_tags.append(tag_disp)
                        # Artist-Not-Sure: wenn es zwar ein match gibt, aber Artist stark abweicht UND notes nicht eindeutig freigeben
                        def artist_mismatch_obs_vs_entry(observed: str, entry: Dict[str,Any]) -> bool:
                            if not observed or not entry: return False
                            obs = _normalize(observed)
                            main = _normalize(str(entry.get("artist","")))
                            if obs == main: return False
                            meta_local = _parse_notes(entry)
                            aliases = [ _normalize(x) for x in (meta_local.get("artist_aliases") or []) + (meta_local.get("confirm_artists") or []) ]
                            if obs in aliases: return False
                            # weiche Schwelle: wenn Ähnlichkeit < 0.50 -> stark abweichend
                            sim_main = SequenceMatcher(a=obs, b=main).ratio() if main else 0.0
                            sim_alias = max([SequenceMatcher(a=obs, b=ax).ratio() for ax in aliases], default=0.0)
                            return max(sim_main, sim_alias) < 0.50
                        if match is not None and self.ans_enabled and artist_mismatch_obs_vs_entry(artist or "", match):
                            nowdt = datetime.now(timezone.utc)
                            meta_m = _parse_notes(match)
                            key_ns = f"{t_norm}|{a_norm}|{_normalize(match.get('artist',''))}|{_normalize(match.get('title',''))}"
                            if self.ans_deduper.should_log(key_ns, nowdt):
                                append_jsonl(self.ans_path, {
                                    "ts": nowdt.isoformat(),
                                    "observed": {"title": title, "artist": artist},
                                    "kb_entry": {
                                        "title": match.get("title"),
                                        "artist": match.get("artist"),
                                        "aliases": match.get("aliases", []),
                                        "notes": match.get("notes",""),
                                        "tags": kb_tags
                                    },
                                    "reason": "artist_mismatch"
                                })
                                self.ans_deduper.mark(key_ns, nowdt)
                                log(f"{self.log_prefix} [note] artist_not_sure logged")
                        if display_tags:
                            genres_text = self.genres_joiner.join(display_tags)
                            self.result_cache.set(cache_key, genres_text)
                            match_found = True
                        else:
                            self.result_cache.set(cache_key, None)
                            genres_text = self.genres_fallback if title else self.genres_text_def
                            match_found = False

                    # Scoring-Tags
                    scoring_tags = set(_norm_tag_for_scoring(x) for x in kb_tags if x.strip())
                    for ttag in detect_special_version_tags(title or "", self.cfg):
                        scoring_tags.add(_norm_tag_for_scoring(ttag))
                    uniq_key = f"{t_norm}|{a_norm}"
                    rx_text_final, rx_bucket = self.rx.decide(title or "", artist or "", genres_text, sorted(scoring_tags), uniq_key)

                    # --- MEMORY: Update + Hinweis ---
                    ctx_name = (self.rx.ctx.get_active_profile() or {}).get("name", "neutral")
                    self.memory.update(key=uniq_key, title=title or "", artist=artist or "", ctx=ctx_name, bucket=rx_bucket, tags=sorted(scoring_tags))
                    self.memory.save()
                    react_out = rx_text_final
                    seen = self.memory.seen_count(uniq_key)
                    best = self.memory.best_context(uniq_key)  # (best_ctx, best_bucket, score) | None
                    def _pick_variant(group: str, bucket: str, fallback: str = "") -> str:
                        arr = (self.mem_variants.get(group, {}) or {}).get(bucket, []) or []
                        return random.choice(arr) if arr else fallback
                    tails: List[str] = []
                    if seen >= self.min_seen_repeat:
                        rep = _pick_variant("repeat", rx_bucket)
                        if rep: tails.append(rep)
                    if best and seen >= self.min_seen_cross:
                        best_ctx, best_bucket, best_score = best
                        if best_ctx and isinstance(best_ctx, str):
                            cross_allowed = True
                            if self.suppress_cross_if_dislike and rx_bucket == "dislike":
                                cross_allowed = False
                            if best_ctx != ctx_name:
                                if cross_allowed and (best_score > self.conf_margin or not self.suppress_cross_if_tie):
                                    bt = _pick_variant("better_other", rx_bucket)
                                    if bt: tails.append(bt.format(best=best_ctx))
                            else:
                                if self.show_fits_here_even_if_small or (best_score > self.conf_margin or not self.suppress_cross_if_tie):
                                    ft = _pick_variant("fits_here", rx_bucket)
                                    if ft: tails.append(ft.format(here=ctx_name))
                    if tails:
                        tails = tails[:self.max_tail_segments]
                        react_out = f"{react_out} {' '.join(tails)}".strip()

                    # Missing log (nur wenn kein KB-Match)
                    if self.missing_enabled and title and not match_found:
                        is_startup_write = (not self.wrote_once)
                        if not (is_startup_write and not self.log_on_init):
                            nowdt = datetime.now(timezone.utc)
                            key_miss = f"{t_norm}|{a_norm}" if (t_norm or a_norm) else (title or "")
                            if self.deduper.should_log(key_miss, nowdt):
                                append_jsonl(self.missing_path, {
                                    "ts": nowdt.isoformat(),
                                    "title": title,
                                    "artist": artist,
                                    "normalized_key": {"title": t_norm, "artist": a_norm}
                                })
                                self.deduper.mark(key_miss, nowdt)

                    # Listening-Phase
                    if self.listening_enabled:
                        chosen_delay = random.randint(self.rand_min_s, self.rand_max_s) if self.use_random_delay else max(0, int(self.delay_s))
                        react_listen = self.listening_text
                        mid_at = None
                        mid_txt = None
                        if self.mid_texts and chosen_delay >= max(self.mid_switch_after, 1):
                            mid_at  = time.time() + float(self.mid_switch_after)
                            mid_txt = random.choice(self.mid_texts)
                        self.pending = {
                            "key": cache_key,
                            "decide_at": time.time() + float(chosen_delay),
                            "mid_at": mid_at,
                            "mid_text": mid_txt,
                            "mid_shown": False,
                            "rx_text": react_out
                        }
                        if (genres_text != self.current_genres_text) or (react_listen != self.current_react_text) or (not self.wrote_once):
                            atomic_write_safe(self.out_genres, genres_text)
                            atomic_write_safe(self.out_react,  react_listen)
                            if self.mirror_legacy:
                                atomic_write_safe(self.legacy_gernres, genres_text)
                            self.current_genres_text = genres_text
                            self.current_react_text  = react_listen
                            self.wrote_once = True
                            log(f"{self.log_prefix} [update] genres='{genres_text}' | react='{react_listen}' (listening)")
                    else:
                        self.pending = None
                        if (genres_text != self.current_genres_text) or (react_out != self.current_react_text) or (not self.wrote_once):
                            atomic_write_safe(self.out_genres, genres_text)
                            atomic_write_safe(self.out_react,  react_out)
                            if self.mirror_legacy:
                                atomic_write_safe(self.legacy_gernres, genres_text)
                            self.current_genres_text = genres_text
                            self.current_react_text  = react_out
                            self.wrote_once = True
                            log(f"{self.log_prefix} [update] genres='{genres_text}' | react='{react_out}'")
                else:
                    if self.pending:
                        raw_now = read_file_stable(self.input_path, settle_ms=0, retries=1) if self.sg_enabled else snapshot
                        t_now, a_now = parse_title_artist(raw_now)
                        key_now = (_normalize(t_now or ""), _normalize(a_now or ""))
                        if key_now != self.pending["key"]:
                            self.pending = None
                        else:
                            now_ts = time.time()
                            if (self.pending.get("mid_at") is not None) and (not self.pending.get("mid_shown", False)) and now_ts >= self.pending["mid_at"]:
                                mid_txt = self.pending.get("mid_text")
                                if mid_txt and mid_txt != self.current_react_text:
                                    atomic_write_safe(self.out_react, mid_txt)
                                    self.current_react_text = mid_txt
                                    log(f"{self.log_prefix} [update] react(mid)='{mid_txt}'")
                                self.pending["mid_shown"] = True
                            if now_ts >= self.pending["decide_at"]:
                                final_text = self.pending["rx_text"]
                                if final_text != self.current_react_text:
                                    atomic_write_safe(self.out_react, final_text)
                                    self.current_react_text = final_text
                                    log(f"{self.log_prefix} [update] react(decided)='{final_text}'")
                                self.pending = None
                if self.log_every_tick:
                    log(f"{self.log_prefix} [idle] no change")
            except KeyboardInterrupt:
                log(f"{self.log_prefix} [exit] bye 👋"); break
            except Exception as e:
                log(f"{self.log_prefix} [warn] {e}")
            time.sleep(self.interval_s)
        log(f"{self.log_prefix} Hauptschleife beendet.")

    # NEU: Methode start(self)
    def start(self):
        """
        Startet den Writer in einem neuen Thread.
        """
        if self.thread is not None and self.thread.is_alive():
            log(f"{self.log_prefix} Writer läuft bereits.")
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        log(f"{self.log_prefix} Writer-Thread gestartet.")

    # NEU: Methode stop(self)
    def stop(self):
        """
        Stoppt den Writer und wartet auf das Ende des Threads.
        """
        if self.thread is None or not self.thread.is_alive():
            log(f"{self.log_prefix} Writer läuft nicht.")
            return
        log(f"{self.log_prefix} Stoppe Writer...")
        self.stop_event.set()
        self.thread.join()
        log(f"{self.log_prefix} Writer-Thread beendet.")

# ##############################################################################
#  BEREICH 5: ARTIST-NOT-SURE WEB-UI LOGIK
# ##############################################################################

def load_artist_not_sure_queue(path: Path) -> List[Dict[str, Any]]:
    """
    Laedt die Eintraege aus der artist_not_sure.jsonl-Datei.
    """
    log(f"[ans_ui] Lade artist_not_sure-Queue von: {path}") # <-- NEU: Logging
    entries = []
    if not path.exists():
        log(f"[ans_ui] artist_not_sure-Datei nicht gefunden: {path}") # <-- NEU: Logging
        return entries
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                    log(f"[ans_ui] Geladener Eintrag (Zeile {line_num}): {entry.get('observed', {}).get('title', 'N/A')} - {entry.get('observed', {}).get('artist', 'N/A')}") # <-- NEU: Logging
                except json.JSONDecodeError as e:
                    log(f"[ans_ui] Warnung: Zeile {line_num} in {path} ist kein gueltiges JSON: {e}")
    except Exception as e:
        log(f"[ans_ui] Fehler beim Lesen von {path}: {e}")
    log(f"[ans_ui] Insgesamt {len(entries)} Eintraege geladen.") # <-- NEU: Logging
    return entries

def save_artist_not_sure_queue(path: Path, entries: List[Dict[str, Any]]) -> None:
    """
    Schreibt die verbleibenden Einträge zurück in die artist_not_sure.jsonl-Datei.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def save_artist_not_sure_reviewed(path: Path, entry: Dict[str, Any]) -> None:
    """
    Fügt einen Eintrag zur reviewed.jsonl-Datei hinzu.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def merge_notes_json(entry: Dict[str, Any], confirm_artist: Optional[str] = None, deny_artist: Optional[str] = None, allow_title_only: bool = False, max_ambiguous: int = 0) -> str:
    """
    Helferfunktion: Mergt neue Notizen in das notes-Feld eines KB-Eintrags (im JSON-Format).
    """
    notes_raw = entry.get("notes", "")
    obj: Dict[str, Any] = {}
    parsed = False
    if notes_raw and isinstance(notes_raw, str) and notes_raw.strip().startswith("{") and notes_raw.strip().endswith("}"):
        try:
            obj = json.loads(notes_raw)
            if not isinstance(obj, dict): obj = {}
            parsed = True
        except json.JSONDecodeError:
            pass
    if not parsed: obj = {}

    if confirm_artist:
        if not obj.get("artist_aliases"): obj["artist_aliases"] = []
        alias_lower = _normalize(confirm_artist)
        if alias_lower and alias_lower not in obj["artist_aliases"]:
            obj["artist_aliases"].append(alias_lower)

    if deny_artist:
        if not obj.get("deny_artists"): obj["deny_artists"] = []
        d_lower = _normalize(deny_artist)
        if d_lower and d_lower not in obj["deny_artists"]:
            obj["deny_artists"].append(d_lower)

    if allow_title_only: obj["allow_title_only"] = True
    if max_ambiguous > 0: obj["max_ambiguous_candidates"] = max_ambiguous

    return json.dumps(obj, ensure_ascii=False)

def update_kb_entry_notes(kb_path: Path, kb_entry_title: str, kb_entry_artist: str, new_notes: str) -> bool:
    """
    Aktualisiert das 'notes'-Feld eines spezifischen Eintrags in der songs_kb.json.
    Sucht anhand von Titel und Künstler.
    """
    try:
        with kb_path.open("r", encoding="utf-8") as f:
            raw_data = f.read()
            data = json.loads(raw_data)
        is_wrapped = isinstance(data, dict) and isinstance(data.get("songs"), list)
        entries = data["songs"] if is_wrapped else data

        found = False
        for entry in entries:
            if _normalize(entry.get("title", "")) == _normalize(kb_entry_title) and _normalize(entry.get("artist", "")) == _normalize(kb_entry_artist):
                entry["notes"] = new_notes
                found = True
                break

        if not found:
            log(f"[ans_ui] Warnung: KB-Eintrag nicht gefunden für {kb_entry_title} — {kb_entry_artist}")
            return False

        with kb_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"[ans_ui] KB-Eintrag aktualisiert: {kb_entry_title} — {kb_entry_artist}")
        return True

    except Exception as e:
        log(f"[ans_ui] Fehler beim Aktualisieren der KB: {e}")
        return False

def process_artist_not_sure_action(action: str, observed_title: str, observed_artist: str, kb_entry_title: str, kb_entry_artist: str, kb_path: Path, queue_path: Path, reviewed_path: Path) -> bool:
    """
    Führt eine Aktion (confirm, deny, allow_title_only) für einen Eintrag aus.
    """
    # Lade aktuelle KB
    try:
        kb_data_raw = kb_path.read_text(encoding="utf-8")
        kb_data = json.loads(kb_data_raw)
        is_wrapped = isinstance(kb_data, dict) and isinstance(kb_data.get("songs"), list)
        kb_entries = kb_data["songs"] if is_wrapped else kb_data
    except Exception as e:
        log(f"[ans_ui] Fehler beim Laden der KB für Aktion: {e}")
        return False

    # Finde den KB-Eintrag
    target_kb_entry = None
    for e in kb_entries:
        if _normalize(e.get("title", "")) == _normalize(kb_entry_title) and _normalize(e.get("artist", "")) == _normalize(kb_entry_artist):
            target_kb_entry = e
            break

    if not target_kb_entry:
        log(f"[ans_ui] KB-Eintrag nicht gefunden: {kb_entry_title} — {kb_entry_artist}")
        return False

    # Erstelle neue Notes basierend auf der Aktion
    current_notes = target_kb_entry.get("notes", "")
    new_notes_str = current_notes
    if action == "confirm":
        new_notes_str = merge_notes_json(target_kb_entry, confirm_artist=observed_artist)
    elif action == "deny":
        new_notes_str = merge_notes_json(target_kb_entry, deny_artist=observed_artist)
    elif action == "allow_title_only":
        new_notes_str = merge_notes_json(target_kb_entry, allow_title_only=True)

    # Aktualisiere die KB lokal
    target_kb_entry["notes"] = new_notes_str

    # Schreibe KB zurück
    try:
        with kb_path.open("w", encoding="utf-8") as f:
            json.dump(kb_data, f, ensure_ascii=False, indent=2)
        log(f"[ans_ui] KB aktualisiert für {kb_entry_title} — {kb_entry_artist}")
    except Exception as e:
        log(f"[ans_ui] Fehler beim Schreiben der KB: {e}")
        return False

    # Verschiebe den Eintrag von Queue zu Reviewed
    queue_entries = load_artist_not_sure_queue(queue_path)
    entry_to_move = None
    for i, entry in enumerate(queue_entries):
        if (entry.get("observed", {}).get("title") == observed_title and
            entry.get("observed", {}).get("artist") == observed_artist and
            entry.get("kb_entry", {}).get("title") == kb_entry_title and
            entry.get("kb_entry", {}).get("artist") == kb_entry_artist):
            entry_to_move = entry
            queue_entries.pop(i)
            break

    if entry_to_move:
        save_artist_not_sure_queue(queue_path, queue_entries)
        save_artist_not_sure_reviewed(reviewed_path, entry_to_move)
        log(f"[ans_ui] Eintrag verschoben: {observed_title} — {observed_artist}")
        return True
    else:
        log(f"[ans_ui] Eintrag nicht in Queue gefunden zum Verschieben: {observed_title} — {observed_artist}")
        # Versuche trotzdem zu speichern, falls der Eintrag nur temporär war
        return True
    
# ##############################################################################
#  BEREICH 6: SPOTIFY ENRICH MISSING LOGIK
# ##############################################################################

# Verwende die bereits definierten globalen Variablen aus webserver.py
ENRICH_SAFE_ROOT = SCRIPT_DIR # Verwende das Hauptverzeichnis des Skripts

ENRICH_ALLOWED_REL_FILES = {
    "KB_PATH":   Path("SongsDB/songs_kb.json"),
    "MISS_PATH": Path("missingsongs/missing_songs_log.jsonl"),
}
ENRICH_ALLOWED_REL_DIRS = {
    "CACHE_DIR":   Path("cache"),
    "BACKUPS_DIR": Path("SongsDB/backups"),
}

ENRICH_SUFFIX_ALLOW = (".json", ".jsonl", ".pkl", ".txt", ".tmp", ".log")

def _enrich_reject_abs_or_traversal(raw: str) -> Path | None:
    if not raw: return None
    p = Path(raw)
    if p.is_absolute():
        return None
    s = str(p).replace("\\", "/")
    if ".." in s.split("/"):
        return None
    return p

def _enrich_ensure_under(p: Path, base: Path) -> Path:
    pr = p.resolve()
    br = base.resolve()
    if pr != br and br not in pr.parents:
        raise ValueError(f"Pfad außerhalb von SAFE_ROOT: {pr} (base={br})")
    return pr

def _enrich_ensure_no_symlink(p: Path) -> None:
    if p.exists() and p.is_symlink():
        raise ValueError(f"Symlink nicht erlaubt: {p}")
    if p.parent.exists() and p.parent.is_symlink():
        raise ValueError(f"Symlink-Parent nicht erlaubt: {p.parent}")

def _enrich_ensure_suffix_allowed(p: Path) -> None:
    if p.suffix and p.suffix.lower() not in {s.lower() for s in ENRICH_SUFFIX_ALLOW}:
        raise ValueError(f"Unerlaubte Dateiendung: {p.suffix} -> {p}")

def _enrich_resolve_allowed_file(env_name: str) -> Path:
    default_rel = ENRICH_ALLOWED_REL_FILES[env_name]
    raw = os.environ.get(env_name, "") or ""
    candidate_rel = _enrich_reject_abs_or_traversal(raw)
    rel = default_rel if (candidate_rel is None or candidate_rel.as_posix() != default_rel.as_posix()) else candidate_rel
    p = (ENRICH_SAFE_ROOT / rel).resolve()
    _enrich_ensure_under(p, ENRICH_SAFE_ROOT)
    _enrich_ensure_suffix_allowed(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    _enrich_ensure_no_symlink(p)
    return p

def _enrich_resolve_allowed_dir(env_name: str) -> Path:
    default_rel = ENRICH_ALLOWED_REL_DIRS[env_name]
    raw = os.environ.get(env_name, "") or ""
    candidate_rel = _enrich_reject_abs_or_traversal(raw)
    rel = default_rel if (candidate_rel is None or candidate_rel.as_posix() != default_rel.as_posix()) else candidate_rel
    p = (ENRICH_SAFE_ROOT / rel).resolve()
    _enrich_ensure_under(p, ENRICH_SAFE_ROOT)
    p.mkdir(parents=True, exist_ok=True)
    _enrich_ensure_no_symlink(p)
    return p

def _enrich_atomic_write_json_safe(path: Path, obj) -> None:
    path = _enrich_ensure_under(path, ENRICH_SAFE_ROOT)
    _enrich_ensure_suffix_allowed(path)
    _enrich_ensure_no_symlink(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def _enrich_backup_songs_kb_safe(kb_path: Path, backups_dir: Path) -> Path | None:
    if not kb_path.exists():
        return None
    backups_dir = _enrich_ensure_under(backups_dir, ENRICH_SAFE_ROOT)
    backups_dir.mkdir(parents=True, exist_ok=True)
    _enrich_ensure_no_symlink(backups_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # UTC-aware
    dst = backups_dir / f"songs_kb.{ts}.json"
    with open(kb_path, "rb") as r, open(dst, "wb") as w:
        w.write(r.read())
        w.flush()
        os.fsync(w.fileno())
    return dst

# ===================== .env Loader =====================

def _enrich_load_env_file():
    env_path = (ENRICH_SAFE_ROOT / ".env")
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
        pass # Ignoriere Fehler beim Laden der .env

_enrich_load_env_file()

# --------------- Config (locked to allowlist) (angepasst) ---------------
ENRICH_ROOT        = ENRICH_SAFE_ROOT
ENRICH_KB_PATH     = _enrich_resolve_allowed_file("KB_PATH")
ENRICH_MISS_PATH   = _enrich_resolve_allowed_file("MISS_PATH")
ENRICH_CACHE_DIR   = _enrich_resolve_allowed_dir("CACHE_DIR")
ENRICH_BACKUPS_DIR = _enrich_resolve_allowed_dir("BACKUPS_DIR")

# DRY_RUN wird hier nicht verwendet, da wir direkt schreiben wollen
# CLIENT_ID und CLIENT_SECRET werden aus der Umgebung gelesen
ENRICH_CLIENT_ID     = os.environ.get("CLIENT_ID") or os.environ.get("SPOTIFY_CLIENT_ID")
ENRICH_CLIENT_SECRET = os.environ.get("CLIENT_SECRET") or os.environ.get("SPOTIFY_CLIENT_SECRET")

# ===================== Logging (angepasst) =====================

# Verwende unsere globale log-Funktion
def _enrich_log(kind, msg):
    log(f"[enrich-{kind}] {msg}")

def _enrich_v(msg):
    # Optional: Verbose-Logging über eine globale Variable steuern
    # z.B. global_enrich_verbose = True/False
    # Hier vorerst immer loggen, wenn VERBOSE-Flag gesetzt ist (z.B. über ENV oder globale Variable)
    if os.environ.get("ENRICH_VERBOSE", "0") == "1": # Beispiel für ENV-Steuerung
        _enrich_log("i", msg)

# ===================== Helpers (angepasst) =====================

def _enrich_ensure_dirs():
    for p in (ENRICH_CACHE_DIR, ENRICH_BACKUPS_DIR, ENRICH_KB_PATH.parent, ENRICH_MISS_PATH.parent):
        p.mkdir(parents=True, exist_ok=True)

def _enrich_norm_text(s: str) -> str:
    if not s: return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _enrich_alias_variants(title: str) -> list:
    if not title: return []
    base = _enrich_norm_text(title)
    low  = base.lower()
    plain = re.sub(r"[~’'`´\-–—_,.:;!?/\\(){}\[\]]+", " ", low)
    plain = re.sub(r"\s+", " ", plain).strip()
    return [base, low, plain] if plain and plain != low else [base, low]

def _enrich_http_json(url, method="GET", headers=None, data=None, expect=200):
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

# ===================== Spotify API (angepasst) =====================

class _EnrichSpotify:
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
        code, raw = _enrich_http_json(
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
        code, raw = _enrich_http_json(f"https://api.spotify.com/v1/search?{params}", headers=self._auth_hdr())
        if code != 200:
            _enrich_v(f"warn search {code}: {raw[:200]}")
            return None
        items = json.loads(raw)["tracks"]["items"]
        return items[0] if items else None

    def tracks_audio_features(self, ids):
        if not ids: return {}
        out = {}
        for i in range(0, len(ids), 100):
            chunk = ids[i:i+100]
            params = urllib.parse.urlencode({"ids": ",".join(chunk)})
            code, raw = _enrich_http_json(f"https://api.spotify.com/v1/audio-features?{params}", headers=self._auth_hdr())
            if code == 429:
                retry = 1.5
                _enrich_v("429 on audio-features -> retry once")
                time.sleep(retry)
                code, raw = _enrich_http_json(f"https://api.spotify.com/v1/audio-features?{params}", headers=self._auth_hdr())
            if code == 403:
                _enrich_v("warn 403 on /audio-features -> skipping features (will still save KB).")
                return out
            if code != 200:
                _enrich_v(f"warn {code} on audio-features: {raw[:200]}")
                continue
            for feat in json.loads(raw).get("audio_features", []) or []:
                if feat and feat.get("id"):
                    out[feat["id"]] = feat
        return out

    def get_artist(self, artist_id: str):
        code, raw = _enrich_http_json(f"https://api.spotify.com/v1/artists/{artist_id}", headers=self._auth_hdr())
        if code != 200:
            _enrich_v(f"warn artist {artist_id} -> {code}: {raw[:160]}")
            return None
        return json.loads(raw)

# ===================== Tagging Helpers (unverändert) =====================

ENRICH_DECADE_RX = re.compile(r"^(\d{4})")
ENRICH_SPECIAL_KEYS = {
    "nightcore": ["nightcore"],
    "speed up": ["speed up", "sped up", "speedup"],
    "tiktok":   ["tiktok", "tik tok"],
    "radio edit": ["radio edit", "radio mix"]
}
ENRICH_GENRE_MAP = {
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

def _enrich_tag_from_decade(release_date: str) -> str | None:
    if not release_date:
        return None
    m = ENRICH_DECADE_RX.search(release_date)
    if not m:
        return None
    try:
        year = int(m.group(1))
    except:
        return None
    decade = (year // 10) * 10
    return f"{decade}s"

def _enrich_special_tags_from_title(title: str) -> list[str]:
    t = (title or "").lower()
    return [tag for tag, keys in ENRICH_SPECIAL_KEYS.items() if any(k in t for k in keys)]

def _enrich_map_artist_genres_to_tags(artist_genres: list[str]) -> set[str]:
    tags = set()
    for g in artist_genres or []:
        gl = g.lower()
        for key, tag in ENRICH_GENRE_MAP.items():
            if key in gl:
                tags.add(tag)
    return tags

# ===================== IO (angepasst) =====================

def _enrich_load_kb(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            data = f.read()
            return json.loads(data)

def _enrich_read_missing_lines(path: Path):
    if not path.exists():
        _enrich_v(f"missing file not found: {path}")
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

def _enrich_norm_key(title, artist):
    def clean(x):
        x = (x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        x = re.sub(r"[’'`´]", "", x)
        return x
    return clean(title), clean(artist)

# ===================== Main Funktion (angepasst) =====================

def run_spotify_enrich_missing(force: bool = False, update_existing: bool = False, verbose: bool = False) -> Tuple[bool, str]:
    """
    Führt die Spotify-Anreicherung aus.
    :param force: Ignoriere den ID-Cache.
    :param update_existing: Aktualisiere bestehende Einträge.
    :param verbose: Ausführliche Ausgaben.
    :return: (Erfolg, Nachricht)
    """
    if verbose:
        os.environ["ENRICH_VERBOSE"] = "1"
    else:
        os.environ.pop("ENRICH_VERBOSE", None)

    _enrich_log("i", "starte Anreicherung von missing_songs_log.jsonl via Spotify")
    _enrich_log("i", f"kb_path   : {ENRICH_KB_PATH}")
    _enrich_log("i", f"miss_path : {ENRICH_MISS_PATH}")
    _enrich_log("i", f"cache_dir : {ENRICH_CACHE_DIR}")
    _enrich_log("i", f"backups   : {ENRICH_BACKUPS_DIR}")
    _enrich_log("i", f"flags     : force={force} update_existing={update_existing}")
    _enrich_log("i", f"env set?  : CLIENT_ID={'yes' if ENRICH_CLIENT_ID else 'no'} CLIENT_SECRET={'yes' if ENRICH_CLIENT_SECRET else 'no'}")

    if not ENRICH_CLIENT_ID or not ENRICH_CLIENT_SECRET:
        return False, "CLIENT_ID oder CLIENT_SECRET nicht gesetzt. Bitte in .env konfigurieren."

    _enrich_ensure_dirs()

    kb = _enrich_load_kb(ENRICH_KB_PATH)
    seen = set()
    kb_index = {}  # (title,artist)->entry
    for e in kb:
        k = _enrich_norm_key(e.get("title",""), e.get("artist",""))
        seen.add(k)
        kb_index[k] = e
    _enrich_v(f"kb entries: {len(kb)}")

    todo = _enrich_read_missing_lines(ENRICH_MISS_PATH)
    _enrich_v(f"missing lines: {len(todo)}")
    if not todo:
        return True, "Keine Einträge in missing_songs_log.jsonl zum Anreichern gefunden."

    sp = _EnrichSpotify(ENRICH_CLIENT_ID, ENRICH_CLIENT_SECRET)
    cache_file = (ENRICH_CACHE_DIR / "id_cache.json")
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
        title = _enrich_norm_text(item.get("title",""))
        artist= _enrich_norm_text(item.get("artist",""))
        album = _enrich_norm_text(item.get("album",""))
        if not title:
            skipped_count += 1
            continue

        key = f"{title}|{artist}".lower()

        # Resolve track_id (respect --force)
        track_id = None
        if key in id_cache and not force:
            track_id = id_cache[key]
            _enrich_v(f"cache-hit id: {key} -> {track_id}")

        tr = None
        if track_id is None:
            tr = sp.search_track(title, artist if artist else None)
            if not tr:
                _enrich_v(f"warn: not found -> {title} — {artist}")
                skipped_count += 1
                continue
            track_id = tr["id"]
            id_cache[key] = track_id

        # Fill missing artist/album from track detail if needed (or if we forced a search)
        if (not artist or not album) or tr is None:
            if tr is None:
                # fetch track object via /tracks?ids=
                params = urllib.parse.urlencode({"ids": track_id})
                code, raw = _enrich_http_json(f"https://api.spotify.com/v1/tracks?{params}", headers=sp._auth_hdr())
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
            dec = _enrich_tag_from_decade(rel_date or "")
            if dec: tags_set.add(dec)
        except Exception:
            pass
        try:
            primary_artist = (tr.get("artists") or [])[0] if tr else None
            pa = sp.get_artist(primary_artist["id"]) if (primary_artist and primary_artist.get("id")) else None
            if pa and isinstance(pa.get("genres"), list):
                tags_set |= _enrich_map_artist_genres_to_tags(pa["genres"])
        except Exception as e:
            _enrich_v(f"warn artist-genres: {e}")
        tags_set |= set(_enrich_special_tags_from_title(title))

        k_norm = _enrich_norm_key(title, artist)
        exists = k_norm in seen

        if exists and update_existing:
            entry = kb_index[k_norm]
            # merge tags
            old_tags = set(entry.get("tags") or [])
            new_tags = sorted((old_tags | tags_set))
            # merge aliases
            alias_src = _enrich_alias_variants(title)
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
            _enrich_log("i", f"updated: {entry['title']} — {entry['artist']} (tags={len(new_tags)})")
            # (we do not append features for updates; optional if wanted later)
            continue

        if exists and not update_existing:
            _enrich_v(f"skip (exists): {title} — {artist}")
            skipped_count += 1
            continue

        # New entry
        entry = {
            "title": title,
            "artist": artist,
            "album": album or "",
            "aliases": _enrich_alias_variants(title),
            "tags": sorted(tags_set) if tags_set else [],
            "notes": ""
        }
        to_feature_ids.append(track_id)
        new_entries.append((entry, track_id))
        added_count += 1
        _enrich_log("i", f"added: {entry['title']} — {entry['artist']}")

    # Optional: Audio-Features batch
    feats = {}
    try:
        feats = sp.tracks_audio_features(to_feature_ids)
        _enrich_v(f"features_batch got: {list(feats.keys())[:3]}{'...' if len(feats)>3 else ''}")
    except Exception as e:
        _enrich_v(f"warn features fetch failed: {e}")

    for entry, tid in new_entries:
        f = feats.get(tid)
        if f:
            entry.setdefault("notes", "")
            entry["notes"] = (entry["notes"] + f" tempo={f.get('tempo')}, energy={f.get('energy')}").strip()

    if not new_entries and updated_count == 0:
        _enrich_v(f"nothing to write. skipped={skipped_count}")
        return True, f"Fertig. Keine neuen Einträge hinzugefügt oder aktualisiert. Übersprungen: {skipped_count}"

    # Save cache
    try:
        (ENRICH_CACHE_DIR / "id_cache.json").write_text(json.dumps(id_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _enrich_v(f"warn cache save failed: {e}")

    # Merge and persist
    try:
        dst = _enrich_backup_songs_kb_safe(ENRICH_KB_PATH, ENRICH_BACKUPS_DIR)
        if dst: _enrich_v(f"backup -> {dst}")
        for entry, _ in new_entries:
            kb.append(entry)
            key = _enrich_norm_key(entry["title"], entry["artist"])
            seen.add(key)
            kb_index[key] = entry
        _enrich_atomic_write_json_safe(ENRICH_KB_PATH, kb)
        _enrich_log("ok", f"added={added_count} updated={updated_count} skipped={skipped_count} -> {ENRICH_KB_PATH.name}")
        return True, f"Erfolgreich! Hinzugefügt: {added_count}, Aktualisiert: {updated_count}, Übersprungen: {skipped_count}. Neue DB in {ENRICH_KB_PATH.name}"
    except Exception as e:
        _enrich_log("err", f"save failed: {e}")
        return False, f"Fehler beim Speichern der neuen songs_kb.json: {e}"

# ##############################################################################
#  BEREICH 7: WEB SERVER & STEUERZENTRALE (angepasst)
# ##############################################################################

def stop_current_writer_and_nowplaying():
    """
    Stoppt die aktuell aktive Writer-Instanz und den NowPlaying-Thread (falls vorhanden).
    """
    global active_writer, active_nowplaying_thread
    success_writer, msg_writer = True, ""
    success_np, msg_np = True, ""

    if active_writer:
        active_writer.stop()
        active_writer = None
        msg_writer = "Aktiver Writer gestoppt."
    else:
        msg_writer = "Kein aktiver Writer zum Stoppen."

    if active_nowplaying_thread:
        nowplaying_stop_event.set()
        active_nowplaying_thread.join()
        active_nowplaying_thread = None
        nowplaying_stop_event.clear() # Zurücksetzen für nächste Verwendung
        msg_np = "NowPlaying-Thread gestoppt."
    else:
        msg_np = "Kein aktiver NowPlaying-Thread zum Stoppen."

    return success_writer and success_np, f"{msg_writer} {msg_np}".strip()

def start_writer_and_nowplaying_for_source(config_name: str):
    """
    Stoppt aktive Instanzen und startet einen neuen Writer und ggf. einen passenden NowPlaying-Thread
    für die gegebene Konfiguration.
    config_name z.B. 'truckersfm', 'spotify', 'rtl'
    """
    global active_writer, active_nowplaying_thread
    try:
        # Stoppe zuerst alles Altes
        stop_current_writer_and_nowplaying()

        # Lade die allgemeine Writer-Konfiguration
        general_config_path = CONFIG_DIR / "config_min.json"
        if not general_config_path.exists():
             return False, f"Generelle Konfigurationsdatei nicht gefunden: {general_config_path}"

        general_cfg = load_config(general_config_path)

        # Standardmaessiger Input-Pfad
        default_input_relative = Path("Nowplaying") / "nowplaying.txt"
        input_path_for_writer = (SCRIPT_DIR / default_input_relative).resolve()

        # Fallunterscheidung basierend auf der Quelle
        if config_name == 'truckersfm':
            # TruckersFM: Interner NowPlaying-Thread
            input_path_cfg = general_cfg.get("input_path", str(default_input_relative))
            input_path_for_writer = Path(input_path_cfg)
            if not input_path_for_writer.is_absolute():
                input_path_for_writer = (SCRIPT_DIR / input_path_for_writer).resolve()

            nowplaying_stop_event.clear()
            active_nowplaying_thread = threading.Thread(target=nowplaying_main_loop, args=(input_path_for_writer, 10, nowplaying_stop_event), daemon=True)
            active_nowplaying_thread.start()
            log(f"[nowplaying] TruckersFM-Abfrage-Thread fuer {input_path_for_writer} gestartet.")

        elif config_name == 'spotify':
            # Spotify: Interner NowPlaying-Thread mit spezifischer Konfiguration
            source_config_path = CONFIG_DIR / f"config_{config_name}.json"
            if not source_config_path.exists():
                return False, f"Quell-Konfigurationsdatei nicht gefunden: {source_config_path}"
            source_cfg = load_config(source_config_path)
            
            input_path_from_source_cfg = source_cfg.get("output", str(default_input_relative))
            input_path_for_writer = Path(input_path_from_source_cfg)
            if not input_path_for_writer.is_absolute():
                input_path_for_writer = (SCRIPT_DIR / input_path_for_writer).resolve()

            nowplaying_stop_event.clear()
            active_nowplaying_thread = threading.Thread(
                target=spotify_nowplaying_main_loop,
                args=(input_path_for_writer, source_config_path, source_cfg.get("interval", 5), nowplaying_stop_event),
                daemon=True
            )
            active_nowplaying_thread.start()
            log(f"[spotify_nowplaying] Spotify-Abfrage-Thread fuer {input_path_for_writer} gestartet.")

        elif config_name == 'rtl':
            # RTL: Externer NowPlaying-Thread (via .bat/py-Skript)
            # Input-Pfad kann in config_min.json unter "rtl_input_path" konfiguriert werden
            rtl_input_path_cfg = general_cfg.get("rtl_input_path", str(default_input_relative))
            input_path_for_writer = Path(rtl_input_path_cfg)
            if not input_path_for_writer.is_absolute():
                input_path_for_writer = (SCRIPT_DIR / input_path_for_writer).resolve()

            # Kein interner NowPlaying-Thread wird gestartet
            log(f"[nowplaying] Kein interner NowPlaying-Thread fuer '{config_name}'. Externer Prozess erwartet. Liest von {input_path_for_writer}.")

        else:
            # Unbekannte Quelle: Warnung und Standardpfad verwenden.
            log(f"[warn] Unbekannte Quelle '{config_name}'. Verwende Standard-Input-Pfad fuer Writer.")

        # Ueberschreibe den input_path in der allgemeinen Konfiguration fuer den Writer
        general_cfg_with_correct_input = general_cfg.copy()
        general_cfg_with_correct_input["input_path"] = str(input_path_for_writer)

        # Starte Writer-Thread mit der angepassten Konfiguration
        active_writer = Writer(config_data=general_cfg_with_correct_input)
        active_writer.start()
        log(f"[Writer-Dynamic] Writer fuer '{config_name}' gestartet. Liest von {input_path_for_writer}")

        final_message = f"Writer fuer '{config_name}' erfolgreich gestartet. Liest von: {input_path_for_writer}."
        if config_name in ['truckersfm', 'spotify']:
            final_message += " NowPlaying-Thread: Gestartet."
        else: # z.B. 'rtl' oder unbekannt
            final_message += " NowPlaying-Quelle: Extern."

        return True, final_message

    except Exception as e:
        # Falls etwas schiefgeht, stoppe alles, was ggf. gestartet wurde
        stop_current_writer_and_nowplaying()
        log(f"[start_writer] Fehler beim Starten fuer '{config_name}': {e}")
        return False, f"Fehler beim Starten fuer '{config_name}': {e}"

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(OBSHTML_DIR), **kwargs)
    def do_GET(self):
        """Verarbeitet eingehende GET-Anfragen."""
        success, message, handled = False, "Unbekannter Befehl", True
        # log(f"[debug_do_get] 1. Start. handled={handled}, success={success}, message='{message}', path='{self.path}'")
        if self.path.startswith('/activate/'):
            source = self.path.split('/')[-1]
            # log(f"[debug_do_get] 2. Activate block. source='{source}'")
            if source == 'truckersfm':
                 # Alte Logik: Lädt config_min.json
                 success, message = start_writer_and_nowplaying_for_source("truckersfm")
                 # log(f"[debug_do_get] 3. truckersfm handled. success={success}, message='{message}'")
            elif source == 'spotify':
                 # Neue Logik: Lädt config_spotify.json dynamisch
                 success, message = start_writer_and_nowplaying_for_source("spotify")
                 # log(f"[debug_do_get] 4. spotify handled. success={success}, message='{message}'")
            elif source == 'rtl':
                 # Neue Logik für RTL: Lädt config_min.json, startet KEINEN internen NowPlaying-Thread
                 # Der externe Prozess (start_rtl_cdp.bat + start_rtl_repeat_counter.bat) schreibt die Datei.
                 # log(f"[debug_do_get] 5. rtl block entered.")
                 success, message = start_writer_and_nowplaying_for_source("rtl")
                 # log(f"[debug_do_get] 6. rtl handled. success={success}, message='{message}'")
            elif source == 'mdr':
            # Neue Logik für MDR: Lädt config_min.json, startet KEINEN internen NowPlaying-Thread
            # Der externe Prozess (start_mdr_nowplaying.bat) schreibt die Datei.
                 log(f"[debug_do_get] 5. mdr block entered.")
                 success, message = start_writer_and_nowplaying_for_source("mdr")
                 log(f"[debug_do_get] 6. mdr handled. success={success}, message='{message}'")
            else:
                 message = f"Unbekannte Quelle: {source}. Unterstützt: truckersfm, spotify, rtl."
                 # log(f"[debug_do_get] 7. Unknown source. message='{message}'")
                 handled = False # <-- Wichtig: Unbekannte Quelle -> nicht behandelt

            # --- NEU: Antwort fuer /activate/* senden ---
            # Da dieser Block eine Antwort senden soll, muessen wir sie hier explizit senden
            # und die Methode beenden.
            if handled:
                # Erfolgreich behandelt (bekannte Quelle)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": success, "message": message}).encode())
                # log(f"[debug_do_get] 15. /activate/ response sent. success={success}, message='{message}'")
                return # <-- WICHTIG: Beende die Methode hier
            else:
                # Unbekannte Quelle
                self.send_response(400) # <-- 400 Bad Request fuer unbekannte Quelle ist besser
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": success, "message": message}).encode())
                # log(f"[debug_do_get] 16. /activate/ unknown source response sent. message='{message}'")
                return # <-- WICHTIG: Beende die Methode hier
            # --- ENDE: NEU ---

        elif self.path == '/deactivate':
            success, message = stop_current_writer_and_nowplaying()
            # log(f"[debug_do_get] 8. deactivate handled. success={success}, message='{message}'")
            # --- NEU: Antwort fuer /deactivate senden ---
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode())
            # log(f"[debug_do_get] 17. /deactivate/ response sent. success={success}, message='{message}'")
            return # <-- WICHTIG: Beende die Methode hier
            # --- ENDE: NEU ---

        elif self.path.startswith('/run/build_db'):
            threading.Thread(target=execute_build_spotify_db, daemon=True).start()
            success, message = True, "DB-Bau gestartet. Siehe Konsole."
            # log(f"[debug_do_get] 9. build_db handled. success={success}, message='{message}'")
            # --- NEU: Antwort fuer /run/build_db senden ---
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode())
            # log(f"[debug_do_get] 18. /run/build_db response sent. success={success}, message='{message}'")
            return # <-- WICHTIG: Beende die Methode hier
            # --- ENDE: NEU ---

        elif self.path == '/get_artist_not_sure_entries':
            ans_path = SCRIPT_DIR / "missingsongs" / "artist_not_sure.jsonl"
            entries = load_artist_not_sure_queue(ans_path)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "entries": entries}).encode('utf-8'))
            return

        elif self.path.startswith('/run/enrich_missing'):
            success, message = run_spotify_enrich_missing(force=False, update_existing=False, verbose=True)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode('utf-8'))
            return
        elif self.path.startswith('/run/start_mdr'):
            import subprocess
            try:
                bat_path = SCRIPT_DIR / "MDRHilfe" / "start_mdr_nowplaying.bat"
                if not bat_path.exists():
                    raise FileNotFoundError(f"MDR-Hilfe-Skript nicht gefunden: {bat_path}")
                
                title = "MDR NowPlaying"
                command = f'start "{title}" cmd /C call "{bat_path}"'
                log(f"[debug] Starte mit Befehl: {command}")
                
                # Starte die .bat-Datei in einer neuen Konsole
                subprocess.Popen(
                    command,
                    shell=True
                )
                
                success = True
                message = f"MDR-Hilfe-Skript gestartet: {bat_path.name}. Ein separates Konsolenfenster sollte sichtbar sein. Bitte warten, bis das Skript läuft."
            except Exception as e:
                success = False
                message = f"Fehler beim Starten des MDR-Hilfe-Skripts: {e}"

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode('utf-8'))
            return
        # --- NEU: Endpoint zum Starten des RTL Repeat Counters ---
        elif self.path.startswith('/run/gimick_repeat_counter'):
            import subprocess
            try:
                bat_path = SCRIPT_DIR / "RTLHilfe" / "gimickrepeatsongs.bat"
                if not bat_path.exists():
                    raise FileNotFoundError(f"RTL-Repeat-Counter-Skript nicht gefunden: {bat_path}")

                # --- DEBUGGING: Logge den zu startenden Pfad ---
                log(f"[debug] Versuche, externen Prozess (Repeat-Counter) zu starten: {bat_path}")
                # ---

                # --- KORREKTUR: Verwende 'start' ueber shell=True ---
                title = "RTL Repeat Counter"
                command = f'start "{title}" cmd /C call "{bat_path}"'
                log(f"[debug] Starte mit Befehl: {command}")

                subprocess.Popen(
                    command,
                    shell=True
                )
                # --- ENDE: KORREKTUR ---

                # --- DEBUGGING: Logge, dass der Startversuch stattgefunden hat ---
                log(f"[debug] Externer Prozess (Repeat-Counter) gestartet.")
                # ---
                
                success = True
                message = f"RTL-Wiederholungs-Zaehler gestartet: {bat_path.name}. Ein separates Konsolenfenster sollte sichtbar sein."
            except Exception as e:
                # --- DEBUGGING: Logge den Fehler ---
                log(f"[debug] Fehler beim Starten des externen Prozess (Repeat-Counter): {e}")
                # ---
                success = False
                message = f"Fehler beim Starten des RTL-Wiederholungs-Zaehlers: {e}"
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode('utf-8'))
            return

        # --- NEU: Endpoint zum Starten der RTL .bat ---
        elif self.path.startswith('/run/rtl_start_browser'):
            import subprocess
            try:
                bat_path = SCRIPT_DIR / "RTLHilfe" / "start_rtl_cdp.bat"
                if not bat_path.exists():
                    raise FileNotFoundError(f"RTL-Hilfe-Skript nicht gefunden: {bat_path}")
                
                # --- DEBUGGING: Logge den zu startenden Pfad ---
                log(f"[debug] Versuche, externen Prozess (Browser) zu starten: {bat_path}")
                # ---
                
                # --- KORREKTUR: Verwende 'start' ueber shell=True ---
                title = "RTL Browser"
                command = f'start "{title}" cmd /C call "{bat_path}"'
                log(f"[debug] Starte mit Befehl: {command}")

                subprocess.Popen(
                    command,
                    shell=True
                )
                # --- ENDE: KORREKTUR ---
                
                # --- DEBUGGING: Logge, dass der Startversuch stattgefunden hat ---
                log(f"[debug] Externer Prozess (Browser) gestartet.")
                # ---

                success = True
                message = f"RTL-Hilfe-Skript gestartet: {bat_path.name}. Ein separates Konsolenfenster sollte sichtbar sein. Bitte warten, bis Chrome geladen ist."
            except Exception as e:
                # --- DEBUGGING: Logge den Fehler ---
                log(f"[debug] Fehler beim Starten des externen Prozess (Browser): {e}")
                # ---
                success = False
                message = f"Fehler beim Starten des RTL-Hilfe-Skripts: {e}"

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode('utf-8'))
            return

        else:
            handled = False
            # log(f"[debug_do_get] 10. else block. handled={handled}")

        # --- NEU: Diese End-Logik wird NUR erreicht, wenn KEIN spezifischer Endpoint zutraf ---
        # log(f"[debug_do_get] 11. Before final if. handled={handled}, success={success}, message='{message}'")
        if handled:
            # log(f"[debug_do_get] 12. Sending 200 response. success={success}, message='{message}'")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": message}).encode())
            # log(f"[debug_do_get] 13. 200 response sent.")
            return # <-- Wichtig!
        # log(f"[debug_do_get] 14. Not handled. Calling super().do_GET(). path='{self.path}'")
        return super().do_GET()
        # --- ENDE: NEU ---
    
    def do_POST(self):
        if self.path == '/artist_not_sure_action':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                request = json.loads(post_data.decode('utf-8'))
                action = request.get('action')
                obs_title = request.get('observed_title')
                obs_artist = request.get('observed_artist')
                kb_title = request.get('kb_title')
                kb_artist = request.get('kb_artist')

                allowed_actions = {"confirm", "deny", "allow_title_only"}
                if action not in allowed_actions:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": f"Ungültige Aktion: {action}"}).encode('utf-8'))
                    return

                if not all([obs_title, obs_artist, kb_title, kb_artist]):
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "Fehlende Parameter"}).encode('utf-8'))
                    return

                # Pfade aus Standardkonfiguration ableiten
                kb_path = SONGSDB_DIR / "songs_kb.json"
                queue_path = SCRIPT_DIR / "missingsongs" / "artist_not_sure.jsonl" # <-- KORRIGIERT
                reviewed_path = SCRIPT_DIR / "missingsongs" / "artist_not_sure.reviewed.jsonl" # <-- KORRIGIERT

                success = process_artist_not_sure_action(action, obs_title, obs_artist, kb_title, kb_artist, kb_path, queue_path, reviewed_path)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                if success:
                    self.wfile.write(json.dumps({"success": True, "message": f"Aktion '{action}' erfolgreich ausgeführt."}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"success": False, "message": "Aktion konnte nicht ausgeführt werden."}).encode('utf-8'))
                return
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Ungültiges JSON"}).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": str(e)}).encode('utf-8'))
                return
        else:
            self.send_response(404)
            self.end_headers()

# --- HAUPTPROGRAMM ---
def acquire_lock():
    try: LOCK_PATH.touch(exist_ok=False); return True
    except FileExistsError: log("FEHLER: Lock-Datei existiert. Läuft das Programm schon?"); return False
def release_lock(): LOCK_PATH.unlink(missing_ok=True)

def main():
    if not acquire_lock(): sys.exit(1)
    httpd = None
    try:
        httpd = socketserver.TCPServer(("", PORT), MyHandler)
        log(f"Finjas RIESEN-Gehirn v5.3 ist online! :3 | Steuerung: http://localhost:{PORT}/Musik.html")
        httpd.serve_forever()

    except KeyboardInterrupt: log("Beende Programm...")
    finally:
        if httpd: httpd.server_close()
        stop_current_writer_and_nowplaying() # Stelle sicher, dass alle Threads gestoppt werden
        release_lock()
        log("Alles sauber beendet.")

if __name__ == "__main__":
    main()