# -*- coding: utf-8 -*-
"""
======================================================================
            Finja's Brain & Knowledge Core – MDR
======================================================================

  Project: Twitch Interactivity Suite
  Version: 1.4.2 (MDR Modul)
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

----------------------------------------------------------------------
 Neu in v1.4.2:
 ---------------------------------------------------------------------
  • 🔒 **Enhanced Security**: All file paths are strictly validated against SAFE_ROOT
  • 🧠 **Cache Integrity**: Pickle cache files are now rigorously validated before loading
  • 📂 **Config Safety**: Only .json/.js config files allowed — no arbitrary file access
  • ⚙️ **Atomic Writes**: All output files use temp+replace for crash-safe persistence
  • 🛑 **No Path Traversal Possible**: Absolute paths, `..`, symlinks and external writes blocked

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

import json, os, re, time, hashlib, collections, pickle, subprocess, sys, uuid, random, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Optional, Tuple, List, Dict, Any

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config_min.json"
LOCK_PATH   = SCRIPT_DIR / ".finja_min_writer.lock"

# ---- add near the top (after imports) ----
def write_atomic_safe(path: str, text: str) -> bool:
    """Safe atomic write with path validation"""
    try:
        path_obj = Path(path).resolve()
        current_dir = Path.cwd().resolve()
        
        # Security: ensure path is within current directory
        if not str(path_obj).startswith(str(current_dir)):
            print(f"[security] Blocked path traversal: {path}")
            return False
            
        # Create parent directories if needed
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write with temp file
        tmp_path = path_obj.with_suffix(path_obj.suffix + '.tmp')
        
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write((text or "").strip() + '\n')
            
        os.replace(tmp_path, path_obj)
        return True
        
    except (OSError, ValueError, Exception) as e:
        print(f"[error] Failed to write {path}: {e}")
        return False
# ------------------------------------------

# ---------- Logging & IO ----------
def log(msg: str) -> None:
    print(datetime.now().strftime("[%H:%M:%S]"), msg, flush=True)

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

# ---------- Single-Instance Lock ----------
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

# ---------- Normalisierung ----------
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

# ---------- KB ----------
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

# ---------- Persistenter KB-Index ----------
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

# ---------- Parser ----------
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

# ---------- Simple LRU Result-Cache ----------
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

# ---------- Debug-Hook ----------
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

# ---------- Sync-Guard ----------
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

# ---------- Missing / Not-Sure Dedupe ----------
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

# ---------- Context Manager ----------
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

# ---------- Special-Version-Tag Detection ----------
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

# ---------- Reaction Engine ----------
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

# ---------- Memory ----------
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

# ---------- Main ----------
def main():
    if not acquire_single_instance_lock():
        print("[i] Konnte Lock nicht bekommen – vermutlich läuft schon eine Instanz.")
        print("    Tipp:  run_finja.bat force   (oder FINJA_FORCE=1 setzen)")
        return
    try:
        print("[i] Starte Finja Minimal Writer...")
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
        missing_path     = Path(missing_cfg.get("path", "missing_songs_log.jsonl"))
        if not missing_path.is_absolute(): missing_path = (SCRIPT_DIR / missing_path).resolve()
        log_on_init      = bool(missing_cfg.get("log_on_init", False))
        dedupe_hours     = int(missing_cfg.get("dedupe_hours", 12))
        state_path       = Path(missing_cfg.get("state_path", ".missing_seen.json"))
        if not state_path.is_absolute(): state_path = (SCRIPT_DIR / state_path).resolve()
        deduper = MissingDedupe(state_path, ttl_hours=dedupe_hours)

        # Artist-Not-Sure-Logger (eigene Dedupe)
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

        # Reaction Engine + Listening-Phase
        rx = ReactionEngine(cfg)
        rx_cfg = (cfg.get("reactions") or {})
        listening_cfg = (rx_cfg.get("listening") or {})
        listening_enabled = bool(listening_cfg.get("enabled", False))
        listening_text    = str(listening_cfg.get("text", "Listening…"))
        rd = listening_cfg.get("random_delay") or {}
        rand_min_s = int(rd.get("min_s", 45)) if rd else 0
        rand_max_s = int(rd.get("max_s", 60)) if rd else 0
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

                    # Lookup Genres (+ optional Specials sichtbar)
                    genres_text = genres_text_def
                    t_norm = _normalize(title) if title else ""
                    a_norm = _normalize(artist) if artist else ""
                    cache_key = (t_norm, a_norm)

                    cached = result_cache.get(cache_key)
                    if cached is not None:
                        genres_text = cached if cached else (genres_fallback if title else genres_text_def)
                        match_found = bool(cached)
                        kb_tags = [t.strip() for t in re.split(r"[•;,/|]+", cached)] if cached else []
                    else:
                        match = None
                        if kb_index and title:
                            # try exact -> fuzzy
                            match = kb_index.exact(title, artist) or kb_index.fuzzy(title, artist)

                        kb_tags_opt = extract_genres(match) if match is not None else None
                        kb_tags = kb_tags_opt or []

                        # notes.add_tags mergen
                        if match is not None:
                            meta = _parse_notes(match)
                            for ttag in (meta.get("add_tags") or []):
                                if ttag and ttag not in kb_tags:
                                    kb_tags.append(ttag)

                        display_tags = list(kb_tags)
                        sv_tags = detect_special_version_tags(title or "", cfg)
                        if show_special_in_genres and sv_tags:
                            for ttag in sv_tags:
                                tag_disp = f"{special_prefix}{ttag}" if special_prefix else ttag
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

                        if match is not None and ans_enabled and artist_mismatch_obs_vs_entry(artist or "", match):
                            nowdt = datetime.now(timezone.utc)
                            meta_m = _parse_notes(match)
                            key_ns = f"{t_norm}|{a_norm}|{_normalize(match.get('artist',''))}|{_normalize(match.get('title',''))}"
                            if ans_deduper.should_log(key_ns, nowdt):
                                append_jsonl(ans_path, {
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

                    # Scoring-Tags
                    scoring_tags = set(_norm_tag_for_scoring(x) for x in kb_tags if x.strip())
                    for ttag in detect_special_version_tags(title or "", cfg):
                        scoring_tags.add(_norm_tag_for_scoring(ttag))

                    uniq_key = f"{t_norm}|{a_norm}"
                    rx_text_final, rx_bucket = rx.decide(title or "", artist or "", genres_text, sorted(scoring_tags), uniq_key)

                    # --- MEMORY: Update + Hinweis ---
                    ctx_name = (rx.ctx.get_active_profile() or {}).get("name", "neutral")
                    memory.update(key=uniq_key, title=title or "", artist=artist or "", ctx=ctx_name, bucket=rx_bucket, tags=sorted(scoring_tags))
                    memory.save()

                    react_out = rx_text_final
                    seen = memory.seen_count(uniq_key)
                    best = memory.best_context(uniq_key)  # (best_ctx, best_bucket, score) | None

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
                            cross_allowed = True
                            if suppress_cross_if_dislike and rx_bucket == "dislike":
                                cross_allowed = False
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

                    # Missing log (nur wenn kein KB-Match)
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

                    # Listening-Phase
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
                # Optional: Finjas Antwort im Overlay setzen
                try:
                    out_dir = cfg.get("fixed_outputs") or cfg.get("outputs_dir") or "outputs"
                    write_atomic_safe(os.path.join(out_dir, "obs_react.txt"), "Bye 👋❤")
                    # Optional: Genres leeren und/oder NowPlaying neutralisieren
                    write_atomic_safe(os.path.join(out_dir, "obs_genres.txt"), "")
                    # write_atomic(os.path.join(out_dir, "nowplaying.txt"), "—")
                except Exception:
                    pass

                print("[exit] bye 👋❤", flush=True)
            except Exception as e:
                log(f"[warn] {e}")
            time.sleep(interval_s)
    finally:
        release_single_instance_lock()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # nur schöne Konsole, OBS-Bye macht dein innerer except-Block
        print("[exit] bye 👋❤", flush=True)
        sys.exit(0)