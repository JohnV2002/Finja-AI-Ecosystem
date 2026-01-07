#!/usr/bin/env python3
"""
======================================================================
          Finja's Brain & Knowledge Core - Docker Spotify
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-music-docker-spotify
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.1
  Description: Core logic for Spotify integration, knowledge base
               lookups, and reaction generation.

  ✨ New in 1.0.1:
    • Translated all comments, logs, and documentation to English
    • Updated fallback text to "Unknown"
    • Updated copyright to 2026 and standard file header
    • Fixed SonarQube issue python:S5754 (replaced bare excepts)
    • Fixed SonarQube issue python:S1192 (defined regex constants)
    • Fixed SonarQube issue python:S3358 (refactored nested ternary)
    • Fixed SonarQube issue python:S3776 (reduced cognitive complexity)

  📜 Features:
    • Real-time connection to Spotify API for monitoring playback.
    • Dynamic & intelligent song reactions based on a local Knowledge Base (KB).
    • Context-sensitive reaction system adapting to moods (e.g., game state).
    • Long-term memory for songs with "Decay" function to handle repetitions.
    • Highly customizable scoring system with biases for artists, genres, and moods.
    • "Special Rule" engine for predefined reactions to specific songs/artists.
    • Automatic detection of song versions like "Nightcore", "Speed Up", "Remix".
    • Efficient caching of the song index for fast load times.
    • Output of reactions to text files and via integrated FastAPI Web API.
    • Fully configurable via JSON files for maximum flexibility.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import os, time, json, random, re, pickle, hashlib, threading
from pathlib import Path
from typing import Optional, Tuple, Dict
from datetime import datetime, timezone

import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# --- Paths & Config ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config_min.json"
cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

OUTPUT_DIR = (SCRIPT_DIR / cfg.get("fixed_outputs", "Nowplaying")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REACTION_TXT = OUTPUT_DIR / "spotify_reaction.txt"
GENRES_TXT   = OUTPUT_DIR / "spotify_genre.txt"

# Legacy compatibility: optional double underscore
REACTION_TXT_LEGACY = OUTPUT_DIR / "spotify__reaction.txt"

# --- Utils ---
DEBUG = bool(cfg.get("debug", True))

# Regex patterns (SonarQube S1192)
RE_NON_ALPHANUMERIC = r"[^\w\s]"
RE_MULTI_SPACE = r"\s{2,}"

def log(msg):
    """Prints a log message with timestamp."""
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg)

def dbg(msg):
    """Prints a debug message if debug mode is enabled."""
    if DEBUG:
        log(msg)

def atomic_write(path: Path, text: str):
    """Writes text to a file atomically (write to temp, then rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

def write_reaction(text: str):
    """Writes the reaction text to the output file(s)."""
    atomic_write(REACTION_TXT, text)
    try:
        if REACTION_TXT_LEGACY.exists():
            atomic_write(REACTION_TXT_LEGACY, text)
    except Exception as e:
        log(f"[write_reaction] legacy write failed: {e}")

def write_genres(text: str):
    """Writes the genre text to the output file."""
    atomic_write(GENRES_TXT, text)

def read_json(path: Path, default):
    """Reads a JSON file safely, returning default on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def write_json(path: Path, obj):
    """Writes an object as JSON to a file atomically."""
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2))

# Optional nowplaying.txt fallback (not used for Spotify, but kept for stability)
def read_file_stable(path: Path, settle_ms=cfg.get("sync_guard",{}).get("settle_ms",200), retries=cfg.get("sync_guard",{}).get("retries",3)):
    last = None
    for _ in range(max(1, retries)):
        data = path.read_text(encoding="utf-8") if path.exists() else ""
        if data == last: return data
        last = data
        time.sleep(settle_ms/1000.0)
    return last or ""

# --- KB / Index + Cache ---
KB_JSON  = (SCRIPT_DIR / cfg.get("songs_kb_path", "SongsDB/songs_kb.json")).resolve()
KB_CACHE = (SCRIPT_DIR / cfg.get("kb_index_cache_path", "cache/kb_index.pkl")).resolve()
KB_CACHE.parent.mkdir(parents=True, exist_ok=True)

RX_PATH  = (SCRIPT_DIR / cfg.get("reactions", {}).get("path", "Memory/reactions.json")).resolve()
CTX_PATH = (SCRIPT_DIR / cfg.get("reactions", {}).get("context", {}).get("path", "Memory/contexts.json")).resolve()
MEM_PATH = (SCRIPT_DIR / cfg.get("memory", {}).get("path","Memory/memory.json")).resolve()

# Ensure directories and basic files exist
for p in [RX_PATH, CTX_PATH, MEM_PATH]:
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("{}", encoding="utf-8")

DASH_SEPS = [" — ", " – ", " - ", " —", "–", "-"," by "]

def parse_title_artist(raw: str) -> Tuple[str,str]:
    """Splits a raw string into title and artist based on common separators."""
    s = (raw or "").strip()
    for sep in DASH_SEPS:
        if sep in s:
            left, right = [x.strip() for x in s.split(sep, 1)]
            if sep.strip() == "by":
                return right, left
            return left, right
    m = re.match(r"^(.*)\s[—\-]\s(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", s

class KBIndex:
    """In-memory index for the Knowledge Base."""
    def __init__(self, entries: list):
        self.entries = entries
        self.index = {"by_title": {}, "by_title_artist": {}}
        for e in entries:
            t = self._norm(e.get("title",""))
            a = self._norm(e.get("artist",""))
            if t:
                self.index["by_title"].setdefault(t, []).append(e)
            if t and a:
                self.index["by_title_artist"][(t,a)] = e
            
            notes = self._parse_notes(e)
            for aa in notes.get("artist_aliases", []):
                aa = self._norm(aa)
                if t and aa:
                    self.index["by_title_artist"][(t,aa)] = e

    @staticmethod
    def _norm(s: str) -> str:
        """Normalizes strings for comparison (lowercase, remove parens, etc.)."""
        s = s.lower().strip()
        s = re.sub(r"[\(\[][^()\[\]]*[\)\]]","",s)
        s = s.replace("&","and")
        s = re.sub(r"\bfeat\.?\b|\bfeaturing\b","",s)
        s = re.sub(RE_NON_ALPHANUMERIC, " ", s)
        s = re.sub(RE_MULTI_SPACE," ",s)
        return s.strip()

    @staticmethod
    def _parse_notes(e: dict) -> dict:
        """Parses the 'notes' field if it contains JSON config."""
        raw = e.get("notes","")
        if not isinstance(raw, str) or not raw.strip():
            return {}
        s = raw.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                data = json.loads(s)
                out = {}
                if isinstance(data.get("artist_aliases"), list):
                    out["artist_aliases"] = [str(x).strip() for x in data["artist_aliases"] if str(x).strip()]
                if isinstance(data.get("add_tags"), list):
                    out["add_tags"] = [str(x).strip() for x in data["add_tags"] if str(x).strip()]
                out["allow_title_only"] = bool(data.get("allow_title_only", False))
                out["max_ambiguous_candidates"] = int(data.get("max_ambiguous_candidates", 1))
                out["score_bias"] = float(data.get("score_bias", 0.0))
                return out
            except Exception:
                return {}
        return {}

def load_kb_index_with_cache(json_path: Path, cache_path: Path) -> KBIndex:
    """Loads the Knowledge Base, using a pickle cache if available and valid."""
    jhash = ""
    try:
        jhash = hashlib.sha256(json_path.read_bytes()).hexdigest()
        if cache_path.exists():
            obj = pickle.loads(cache_path.read_bytes())
            if obj.get("json_hash") == jhash and isinstance(obj.get("index"), KBIndex):
                return obj["index"]
    except Exception as e:
        log(f"[KB] cache probe failed: {e}")

    entries = []
    raw_bytes = b""
    try:
        raw_bytes = json_path.read_bytes()
        data = json.loads(raw_bytes.decode("utf-8"))
        # Fixed SonarQube S3358: Refactored nested conditional expression
        if isinstance(data, dict) and "songs" in data:
            entries = data["songs"]
        elif isinstance(data, list):
            entries = data
        else:
            entries = []

        if not jhash:
            jhash = hashlib.sha256(raw_bytes).hexdigest()
    except Exception as e:
        log(f"[KB] load error: {e}")
        entries = []

    idx = KBIndex(entries)
    try:
        payload = {"json_hash": jhash or "nohash", "index": idx}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    except Exception as e:
        log(f"[KB] cache save failed: {e}")

    return idx

# --- Special-Version matcher (tolerant) ---
SPECIAL_TAGS = cfg.get("special_version_tags", {})  # e.g. {"nightcore":[...], "speed up":[...]}

def _ws_pat(s: str) -> str:
    """Creates a regex pattern for whitespace-tolerant matching."""
    parts = [p for p in re.split(r"\s+", (s or "").strip().lower()) if p]
    if not parts:
        return ""
    return r"[\s\-]*".join(re.escape(p) for p in parts)

def detect_special_version_tags(title: str) -> Optional[str]:
    """Detects tags like Nightcore or Speed Up in the title."""
    low = (title or "").lower()
    for label, variants in SPECIAL_TAGS.items():
        for v in variants or []:
            pat = _ws_pat(v)
            if pat and re.search(pat, low):
                return label
    return None

# --- Memory (simple JSON), Decay, Tails ---
MEM_CFG = cfg.get("memory", {})
def load_mem(): return read_json(MEM_PATH, {})
def save_mem(d): write_json(MEM_PATH, d)

def apply_decay(entry: dict):
    """Applies time-based score decay to memory entries."""
    if not MEM_CFG.get("decay",{}).get("enabled", False):
        return
    now = time.time()
    hl = MEM_CFG["decay"].get("half_life_days", 90)
    floor = MEM_CFG["decay"].get("floor", 0.0)
    for ctxd in entry.get("contexts", {}).values():
        ls = ctxd.get("last_seen", 0)
        if not ls: continue
        days = (now - ls)/(24*3600)
        factor = 0.5 ** (days/hl)
        ctxd["score"] = max(ctxd.get("score",0.0)*factor, floor)

def _resolve_cross_context_tail(contexts: dict, current_ctx: str, tier: str, t: dict, v: dict) -> str:
    """Helper to resolve cross-context tail logic (reduces complexity of memory_tail)."""
    sorted_ctx = sorted(contexts.items(), key=lambda kv: kv[1].get("score", -999), reverse=True)
    best_ctx, best_data = sorted_ctx[0]
    margin = t.get("confidence_margin", 0.75)
    current_score = contexts.get(current_ctx, {}).get("score", -999)

    if best_ctx != current_ctx and best_data.get("score", 0.0) > current_score + margin:
        pool = v.get("better_other", {}).get(tier, [])
        if pool:
            return " " + random.choice(pool).replace("{best}", best_ctx)
    elif best_ctx == current_ctx:
        pool = v.get("fits_here", {}).get(tier, [])
        if pool:
            return " " + random.choice(pool).replace("{here}", current_ctx)
    return ""

def memory_tail(entry, current_ctx, tier) -> str:
    """Generates a 'tail' reaction (e.g., 'heard this yesterday') based on memory."""
    if not MEM_CFG.get("enabled", False):
        return ""
    v = MEM_CFG.get("variants", {})
    t = MEM_CFG.get("tuning", {})
    contexts = entry.get("contexts", {})
    seen_total = sum(d.get("seen",0) for d in contexts.values())
    seen_here  = contexts.get(current_ctx, {}).get("seen",0)
    
    # Check for repeat reaction
    if seen_here > 1 and seen_total >= t.get("min_seen_for_repeat",2):
        pool = v.get("repeat", {}).get(tier, [])
        if pool:
            return " " + random.choice(pool)
    
    # Check for cross-context reaction (extracted to helper for S3776)
    if seen_total >= t.get("min_seen_for_cross_context",2) and len(contexts) > 1:
        return _resolve_cross_context_tail(contexts, current_ctx, tier, t, v)
        
    return ""

# --- Reactions + Bias + Specials ---
REACTIONS = read_json(RX_PATH, {})
THRESH = REACTIONS.get("thresholds", {"love":9,"like":3,"dislike":-3,"hate":-9})

def tier_from_score(s: float) -> str:
    """Converts a numerical score to a tier (love, like, neutral, etc.)."""
    if s >= THRESH.get("love",9): return "love"
    if s >= THRESH.get("like",3): return "like"
    if s >  THRESH.get("dislike",-3): return "neutral"
    if s >  THRESH.get("hate",-9): return "dislike"
    return "hate"

def reaction_from_tier(tier: str) -> str:
    """Selects a random reaction string for a given tier."""
    sets = REACTIONS.get("sets", {}).get(tier, [])
    if sets:
        return random.choice(sets)
    return REACTIONS.get("fallback", {}).get(tier, "...")

ARTIST_PREFS = REACTIONS.get("artist_preferences", {})  # score_bias + optional flip map per tier

def apply_artist_flip(tier: str, artists_norm: list) -> str:
    """Applies artist-specific tier flips (e.g. force dislike to neutral)."""
    for a in artists_norm:
        flip = ARTIST_PREFS.get(a, {}).get("flip", {})
        if tier in flip and random.random() < float(flip[tier]):
            return {"dislike":"neutral","neutral":"like","like":"neutral"}.get(tier, tier)
    return tier

# helper: robust normalize (for Bias & Specials)
def _norm_txt(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("&","and")
    s = re.sub(RE_NON_ALPHANUMERIC, " ", s)
    s = re.sub(RE_MULTI_SPACE, " ", s)
    return s.strip()

# Specials from reactions.json
SPECIAL_RULES = REACTIONS.get("special", [])

def match_special(title: str, artists_csv: str):
    """Return (forced_tier or None, custom_react or None) if any special rule matches."""
    tnorm = _norm_txt(title)
    anorm = _norm_txt(artists_csv)
    # Check individual artists
    artist_list = [a.strip() for a in re.split(r"[,&;/]+", artists_csv or "") if a.strip()]
    artist_list_norm = [_norm_txt(a) for a in artist_list]

    for rule in SPECIAL_RULES:
        titles = [_norm_txt(x) for x in rule.get("title_contains", []) if str(x).strip()]
        arts   = [_norm_txt(x) for x in rule.get("artist_contains", []) if str(x).strip()]
        
        cond_t = all((x in tnorm) for x in titles) if titles else True
        cond_a = True
        if arts:
            # Match if any artist token contains the requirement
            cond_a = any((x in anorm) or any(x in a for a in artist_list_norm) for x in arts)
            
        if cond_t and cond_a:
            forced = rule.get("force_bucket")
            react  = rule.get("react")
            return forced, react
    return None, None

# --- Context ---
CONTEXTS = read_json(CTX_PATH, {"default_profile":"neutral","profiles":{"neutral":{"bucket_bias":{},"tag_weights":{},"artist_weights":{}}}})

def active_context() -> Tuple[str, dict]:
    """Determines the current active context (e.g., from game_state.txt)."""
    source = CONTEXTS.get("source", {})
    current=""
    if source.get("type")=="file":
        p = (SCRIPT_DIR / source.get("path","Memory/game_state.txt")).resolve()
        try:
            current = p.read_text(encoding="utf-8").strip().lower() if p.exists() else ""
        except Exception:
            current = ""
        current = source.get("map",{}).get(current, CONTEXTS.get("default_profile","neutral"))
    else:
        current = CONTEXTS.get("default_profile","neutral")
    prof = CONTEXTS.get("profiles", {}).get(current, CONTEXTS["profiles"]["neutral"])
    return current, prof

# --- LRU + TTL Cache ---
class LRUCacheTTL:
    def __init__(self, maxsize=256, ttl=60):
        self.maxsize, self.ttl = maxsize, ttl
        self.data: Dict[tuple, tuple] = {}  # key -> (value, expire_ts)
    
    def get(self, key):
        v = self.data.get(key)
        if not v: return None
        val, exp = v
        if time.time()>exp:
            self.data.pop(key, None)
            return None
        return val
    
    def set(self, key, value):
        if len(self.data)>=self.maxsize:
            self.data.pop(next(iter(self.data)))
        self.data[key]=(value, time.time()+self.ttl)

RESULT_CACHE = LRUCacheTTL(maxsize=512, ttl=90)

# --- KB load ---
KB = load_kb_index_with_cache(KB_JSON, KB_CACHE)

def get_genres_from_entry(e: dict) -> str:
    tags = list(e.get("tags", []))
    notes = KB._parse_notes(e)
    tags += notes.get("add_tags", [])
    return ", ".join(sorted(set(tags))) or "Unknown"

def find_kb_entry(title:str, artist_csv:str) -> Optional[dict]:
    t = KB._norm(title)
    a = KB._norm(artist_csv)
    if (t,a) in KB.index["by_title_artist"]: return KB.index["by_title_artist"][(t,a)]
    
    cands = KB.index["by_title"].get(t, [])
    if len(cands)==1: return cands[0]
    if len(cands)>1:
        first = cands[0]
        notes = KB._parse_notes(first)
        if notes.get("allow_title_only", False) and len(cands)<=notes.get("max_ambiguous_candidates",1):
            return first
    return None

# --- Spotify client (ENV-only) ---
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID","")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET","")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN","")
ACCESS_TOKEN = ""
ACCESS_TOKEN_TS = 0
TOKEN_REFRESH_INTERVAL_S = int(cfg.get("token_refresh_interval_s", 25*60))

def refresh_token():
    """Refreshes the Spotify OAuth token."""
    global ACCESS_TOKEN, ACCESS_TOKEN_TS
    url = 'https://accounts.spotify.com/api/token'
    try:
        r = requests.post(
            url,
            data={'grant_type': 'refresh_token', 'refresh_token': SPOTIFY_REFRESH_TOKEN},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10
        )
        if r.status_code != 200:
            log(f"[spotify] refresh error {r.status_code}: {r.text}")
            r.raise_for_status()
        payload = r.json()
        ACCESS_TOKEN = payload['access_token']
        ACCESS_TOKEN_TS = time.time()
        log("[spotify] token refreshed")
    except Exception as e:
        log(f"[spotify] refresh exception: {e}")
        raise

def spotify_nowplaying() -> Tuple[str,str]:
    """Fetches the currently playing song from Spotify."""
    if not ACCESS_TOKEN or time.time()-ACCESS_TOKEN_TS>TOKEN_REFRESH_INTERVAL_S:
        refresh_token()
    r = requests.get('https://api.spotify.com/v1/me/player/currently-playing',
                     headers={'Authorization': f'Bearer {ACCESS_TOKEN}'}, timeout=10)
    if r.status_code==204: return "",""
    r.raise_for_status()
    data = r.json()
    item = data.get("item") or {}
    title = item.get("name","")
    artists = ", ".join([a.get("name","") for a in item.get("artists",[])])
    return title, artists

# --- Listening Phase State ---
INTERVAL_S = int(cfg.get("interval_s", 5))
DEFAULT_LISTENING_TEXT = "Listening…"  # S1192: Defined constant
LISTEN_CFG = cfg.get("reactions", {}).get("listening", {
    "enabled": True,
    "text": DEFAULT_LISTENING_TEXT,
    "random_delay": {"min_s": 40, "max_s": 60},
    "mid_texts": [DEFAULT_LISTENING_TEXT],
    "mid_switch_after_s": 50
})
pending_until = 0.0
mid_from = 0.0
cooldown_until = 0.0
last_key = None
last_song_log_ts = 0.0
last_written = None  # Mini-Patch: Write/Log only on change
current_output = {"reaction":"","genres":"","title":"","artist":"","context":"","updated_at":""}

def _handle_unknown_policy(rx_cfg: dict, special_version: Optional[str], config: dict) -> Tuple[str, str]:
    """Helper: Handles logic when no KB entry is found (Unknown Policy)."""
    pol = rx_cfg.get("unknown_policy", {"enabled": True, "like": 0.35, "neutral": 0.40, "dislike": 0.25})
    if pol.get("enabled", True):
        bucket = random.choices(["like", "neutral", "dislike"], 
                              weights=[pol["like"], pol["neutral"], pol["dislike"]], k=1)[0]
    else:
        bucket = "neutral"
        
    reaction = reaction_from_tier(bucket)
    genres = "Unknown"
    
    # Append special-version tag if any
    if special_version and config.get("show_special_version_in_genres", True):
        pref = config.get("special_version_prefix", "")
        # Fixed S5797: Genres is always 'Unknown' here, so it's always true. Removed conditional.
        genres = f"{genres}, {pref}{special_version}"
        
    return reaction, genres

def _calculate_dynamic_tier(ctx: str, ment: dict, profile: dict, kb_entry: Optional[dict], artists: str) -> str:
    """Helper: Calculates the score and determines the tier (Love, Like, etc.)."""
    ctx_data = ment.get("contexts", {}).get(ctx, {})
    base = ctx_data.get("score", 0.0)

    all_artists = [a.strip() for a in artists.split(",") if a.strip()]
    
    # 1. Artist Bias
    artist_weights = profile.get("artist_weights", {})
    artist_biases = []
    for a in all_artists:
        na = KB._norm(a)
        bias_ctx  = artist_weights.get(na, 0.0)
        bias_pref = ARTIST_PREFS.get(na, {}).get("score_bias", 0.0)
        artist_biases.append(bias_ctx + bias_pref)
    artist_bias = max(artist_biases) if artist_biases else 0.0

    # 2. Tag Bias
    tags = set(kb_entry.get("tags", [])) if kb_entry else set()
    tag_bias = sum(profile.get("tag_weights", {}).get(t, 0.0) for t in tags)

    # 3. Global Bias Config (Like/Dislike lists)
    bias_cfg = REACTIONS.get("bias", {})
    def _norm(s):
        s = s.lower().strip()
        s = s.replace("&","and")
        s = re.sub(RE_NON_ALPHANUMERIC, " ", s)
        s = re.sub(RE_MULTI_SPACE, " ", s)
        return s.strip()

    like_tags      = { _norm(x) for x in bias_cfg.get("like_tags", []) }
    dislike_tags   = { _norm(x) for x in bias_cfg.get("dislike_tags", []) }
    like_artists   = { _norm(x) for x in bias_cfg.get("like_artists", []) }
    dislike_artists= { _norm(x) for x in bias_cfg.get("dislike_artists", []) }

    bias_bonus_tags = 0.0
    if tags:
        lowtags = { _norm(t) for t in tags }
        if lowtags & like_tags:    bias_bonus_tags += 0.5
        if lowtags & dislike_tags: bias_bonus_tags -= 0.5

    arts_norm = [ _norm(a) for a in all_artists ]
    bias_bonus_art = 0.0
    if any(a in like_artists for a in arts_norm):     bias_bonus_art += 1.0
    if any(a in dislike_artists for a in arts_norm):  bias_bonus_art -= 1.0

    extra_bias = bias_bonus_tags + bias_bonus_art

    # 4. Final Calculation
    prelim = base + artist_bias + tag_bias + extra_bias
    prelim_tier = tier_from_score(prelim)
    bucket_bias = profile.get("bucket_bias", {}).get(prelim_tier, 0.0)
    final_score = prelim + bucket_bias
    tier = tier_from_score(final_score)

    # 5. Explore Policy
    expl = REACTIONS.get("explore", {"enabled": False})
    tier_before_explore = tier
    if expl.get("enabled", False):
        chance = float(expl.get("chance", 0.0))
        if random.random() < chance:
            w = expl.get("weights", {"like":0.45, "neutral":0.35, "dislike":0.20})
            tier = random.choices(["like","neutral","dislike"],
                                  weights=[w.get("like",0), w.get("neutral",0), w.get("dislike",0)], k=1)[0]

    # 6. Probabilistic Flip
    tier_before_flip = tier
    tier = apply_artist_flip(tier, [KB._norm(a) for a in all_artists])

    # Debug / Sanity
    dbg(
        f"[score] base={base:+.2f} | artist_bias={artist_bias:+.2f} | tag_bias={tag_bias:+.2f} "
        f"| extra_bias={extra_bias:+.2f} | prelim={prelim:+.2f} ({prelim_tier}) "
        f"| bucket_bias={bucket_bias:+.2f} | final={final_score:+.2f} -> tier={tier_before_explore}"
    )
    if expl.get("enabled", False):
        dbg(f"[explore] chance={expl.get('chance')} -> tier_after_explore={tier_before_flip}")
    dbg(f"[flip] tier_before_flip={tier_before_flip} -> tier_final={tier}")
    
    return tier

def _construct_genres_string(kb_entry: Optional[dict], special_version: Optional[str]) -> str:
    """Helper: Constructs the genre string."""
    genres = "Unknown"
    if kb_entry:
        genres = get_genres_from_entry(kb_entry)
        
    if special_version and cfg.get("show_special_version_in_genres", True):
        pref = cfg.get("special_version_prefix","")
        sep = ", " if genres else ""
        genres = f"{genres}{sep}{pref}{special_version}"
    return genres

def _update_memory_score(ment: dict, ctx: str, tier: str):
    """Helper: Updates the memory score for a song based on the reaction tier."""
    now = time.time()
    c = ment.setdefault("contexts", {}).setdefault(ctx, {"seen": 0, "score": 0.0, "last_seen": 0})
    c["seen"] += 1
    c["last_seen"] = now

    # Fixed S3358: Replaced nested ternary with explicit if/elif/else
    score_delta = 0.1
    if tier in ["love", "like"]:
        score_delta = 1.0
    elif tier in ["dislike", "hate"]:
        score_delta = -1.0
        
    c["score"] = max(-10.0, min(10.0, c.get("score", 0.0) + score_delta))

def compute_reaction(title:str, artists:str) -> Tuple[str,str]:
    """Core logic to determine reaction and genre for a song."""
    # Refactored for S3776: Reduced complexity by extracting sub-logic
    ctx, profile = active_context()
    key = (title, artists, ctx)
    cached = RESULT_CACHE.get(key)
    if cached: return cached

    # --- Specials (meme rules) ---
    forced_bucket, special_react = match_special(title, artists)
    special_version = detect_special_version_tags(title)
    kb_entry = find_kb_entry(title, artists)

    # Case A: Unknown policy (no KB entry and no forced special rule)
    if not kb_entry and not forced_bucket:
        rx_cfg = read_json(RX_PATH, {})
        reaction, genres = _handle_unknown_policy(rx_cfg, special_version, cfg)
        
        # Apply special react override if it exists (though forced_bucket is False here)
        if forced_bucket and special_react: # Should technically not be reached due to condition above, but kept safe
             reaction = special_react

        reaction = reaction.replace("{title}", title).replace("{artist}", artists).replace("{genres}", genres)
        RESULT_CACHE.set(key, (reaction, genres))
        return reaction, genres

    # Case B: Known Song or Forced Bucket
    # Load Memory
    mem = load_mem()
    ekey = f"{KB._norm(kb_entry.get('title',''))} - {KB._norm(kb_entry.get('artist',''))}" if kb_entry else f"{KB._norm(title)} - {KB._norm(artists)}"
    ment = mem.get(ekey, {"contexts":{}})
    apply_decay(ment)

    # Determine Tier
    if not forced_bucket:
        tier = _calculate_dynamic_tier(ctx, ment, profile, kb_entry, artists)
    else:
        tier = forced_bucket

    # Determine Reaction & Genres
    genres = _construct_genres_string(kb_entry, special_version)

    if special_react:
        reaction = special_react
    else:
        reaction = reaction_from_tier(tier)

    # Add Memory Tail
    tail = memory_tail(ment, ctx, tier)
    reaction = reaction.replace("{title}", title).replace("{artist}", artists).replace("{genres}", genres) + tail

    # Persist Memory
    _update_memory_score(ment, ctx, tier)
    mem[ekey]=ment
    save_mem(mem)

    RESULT_CACHE.set(key, (reaction, genres))
    return reaction, genres

# --- Helpers for tick_loop (Refactored for S3776) ---
def _init_new_song_state(title: str, artists: str, ctx: str, now: float) -> Tuple[float, float, float, dict]:
    """Helper: Initializes state when a new song is detected."""
    # Timings
    p_until = now + random.uniform(LISTEN_CFG.get("random_delay", {}).get("min_s", 40),
                                   LISTEN_CFG.get("random_delay", {}).get("max_s", 60))
    m_from = now + float(LISTEN_CFG.get("mid_switch_after_s", 50))
    c_until = now + 4.0

    # Write Listening
    listen_text = LISTEN_CFG.get("text", DEFAULT_LISTENING_TEXT)
    write_reaction(listen_text)

    # Write Genres
    special = detect_special_version_tags(title)
    kb_entry = find_kb_entry(title, artists)
    genres_now = _construct_genres_string(kb_entry, special)
    write_genres(genres_now)

    # Output Dict
    curr_out = {
        "reaction": listen_text,
        "genres": genres_now,
        "title": title, "artist": artists, "context": ctx,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    dbg(f"[song] > {title} - {artists} | ctx={ctx} | genres='{genres_now}' (reaction pending)")
    return p_until, m_from, c_until, curr_out

def _process_pending_mode(now: float, mid_from: float, cooldown_until: float, current_output: dict) -> Tuple[float, dict]:
    """Helper: Handles updates during the listening/pending phase."""
    if now > mid_from and random.random() < 0.25:
        mids = LISTEN_CFG.get("mid_texts", [DEFAULT_LISTENING_TEXT])
        mid = random.choice(mids)
        if time.time() > cooldown_until:
            write_reaction(mid)
            cooldown_until = time.time() + 1.5
            current_output["reaction"] = mid
    return cooldown_until, current_output

def _process_final_result(title: str, artists: str, ctx: str, last_written: Optional[Tuple], cooldown_until: float, current_output: dict) -> Tuple[Optional[Tuple], float, dict]:
    """Helper: Computes and writes the final reaction."""
    reaction, genres = compute_reaction(title, artists)
    state_tuple = (reaction, genres, title, artists, ctx)

    if state_tuple != last_written:
        if time.time() > cooldown_until:
            write_reaction(reaction)
            write_genres(genres)
            cooldown_until = time.time() + 1.5
            dbg(f"[final] {title} - {artists} | ctx={ctx} | reaction='{reaction}' | genres='{genres}'")

        current_output = {
            "reaction": reaction,
            "genres": genres,
            "title": title, "artist": artists, "context": ctx,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        last_written = state_tuple
        
    return last_written, cooldown_until, current_output

def tick_loop():
    """Main background loop to monitor Spotify and trigger updates."""
    global pending_until, mid_from, cooldown_until, last_key, last_song_log_ts, last_written, current_output
    while True:
        try:
            title, artists = spotify_nowplaying()
            if not title and not artists:
                time.sleep(INTERVAL_S)
                continue

            ctx, _ = active_context()
            key = (title, artists, ctx)
            now = time.time()

            # New song? -> Listening & Genres immediately + log once
            if key != last_key:
                last_key = key
                pending_until, mid_from, cooldown_until, current_output = _init_new_song_state(title, artists, ctx, now)
                last_song_log_ts = now
            else:
                # Keep-alive: at most every 20s
                if now - last_song_log_ts > 20:
                    dbg(f"[song-keepalive] > {title} - {artists} | ctx={ctx} (still pending)")
                    last_song_log_ts = now

            # still pending?
            if now < pending_until:
                cooldown_until, current_output = _process_pending_mode(now, mid_from, cooldown_until, current_output)
                time.sleep(INTERVAL_S)
                continue

            # final compute
            last_written, cooldown_until, current_output = _process_final_result(title, artists, ctx, last_written, cooldown_until, current_output)

        except Exception as e:
            log(f"[loop] {e}")
        finally:
            time.sleep(INTERVAL_S)

# --- FastAPI ---
app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}

@app.get("/get/Finja")
def get_finja():
    return JSONResponse(current_output)

# --- Background worker ---
t = threading.Thread(target=tick_loop, daemon=True)
t.start()