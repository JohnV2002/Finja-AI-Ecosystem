"""
======================================================================
            Finja's Brain & Knowledge Core – Docker Spotify
======================================================================

  Project: Twitch Interactivity Suite
  Version: 1.0.0 (Docker Spotify Modul)
  Author:  JohnV2002 (J. Apps / Sodakiller1)
  License: MIT License (c) 2025 J. Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
 • Echtzeit-Verbindung zur Spotify-API zur Überwachung der aktuellen Wiedergabe.
 • Dynamische & intelligente Song-Reaktionen basierend auf einer lokalen Wissensdatenbank (KB).
 • Kontext-sensitives Reaktionssystem, das Stimmungen anpasst (z.B. je nach Spiel).
 • Langzeitgedächtnis für Songs mit "Decay"-Funktion, das Wiederholungen erkennt und darauf reagiert.
 • Hochgradig anpassbares Scoring-System mit Biases für Künstler, Genres und Song-Stimmungen.
 • "Special Rule"-Engine für vordefinierte Reaktionen auf bestimmte Lieder oder Künstler.
 • Automatische Erkennung von Song-Versionen wie "Nightcore", "Speed Up", "Remix" etc.
 • Effizientes Caching des Song-Index für blitzschnelle Ladezeiten.
 • Ausgabe der Reaktionen in Textdateien und über eine integrierte FastAPI-Web-API.
 • Vollständig über JSON-Dateien konfigurierbar für maximale Flexibilität.

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

# Legacy-Kompatibilität: optional doppelt-Underscore
REACTION_TXT_LEGACY = OUTPUT_DIR / "spotify__reaction.txt"

# --- Utils ---
DEBUG = bool(cfg.get("debug", True))

def log(msg): print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg)
def dbg(msg):
    if DEBUG:
        log(msg)

def atomic_write(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8"); tmp.replace(path)

def write_reaction(text: str):
    atomic_write(REACTION_TXT, text)
    try:
        if REACTION_TXT_LEGACY.exists():
            atomic_write(REACTION_TXT_LEGACY, text)
    except Exception as e:
        log(f"[write_reaction] legacy write failed: {e}")

def write_genres(text: str):
    atomic_write(GENRES_TXT, text)

def read_json(path: Path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return default

def write_json(path: Path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2))

# optional nowplaying.txt fallback (not used for Spotify)
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
for p in [RX_PATH, CTX_PATH, MEM_PATH]:
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists(): p.write_text("{}", encoding="utf-8")

DASH_SEPS = [" — ", " – ", " - ", " —", "–", "-"," by "]
def parse_title_artist(raw: str) -> Tuple[str,str]:
    s = (raw or "").strip()
    for sep in DASH_SEPS:
        if sep in s:
            left, right = [x.strip() for x in s.split(sep, 1)]
            if sep.strip() == "by":
                return right, left
            return left, right
    m = re.match(r"^(.*)\s[—\-]\s(.*)$", s)
    if m: return m.group(1).strip(), m.group(2).strip()
    return "", s

class KBIndex:
    def __init__(self, entries: list):
        self.entries = entries
        self.index = {"by_title": {}, "by_title_artist": {}}
        for e in entries:
            t = self._norm(e.get("title",""))
            a = self._norm(e.get("artist",""))
            if t: self.index["by_title"].setdefault(t, []).append(e)
            if t and a: self.index["by_title_artist"][(t,a)] = e
            notes = self._parse_notes(e)
            for aa in notes.get("artist_aliases", []):
                aa = self._norm(aa)
                if t and aa: self.index["by_title_artist"][(t,aa)] = e

    @staticmethod
    def _norm(s: str)->str:
        s = s.lower().strip()
        s = re.sub(r"[\(\[][^()\[\]]*[\)\]]","",s)
        s = s.replace("&","and")
        s = re.sub(r"\bfeat\.?\b|\bfeaturing\b","",s)
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s{2,}"," ",s)
        return s.strip()

    @staticmethod
    def _parse_notes(e: dict) -> dict:
        raw = e.get("notes","")
        if not isinstance(raw,str) or not raw.strip(): return {}
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
            except: return {}
        return {}

def load_kb_index_with_cache(json_path: Path, cache_path: Path) -> KBIndex:
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
        entries = data["songs"] if isinstance(data, dict) and "songs" in data else (data if isinstance(data, list) else [])
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
    parts = [p for p in re.split(r"\s+", (s or "").strip().lower()) if p]
    if not parts:
        return ""
    return r"[\s\-]*".join(re.escape(p) for p in parts)

def detect_special_version_tags(title: str) -> Optional[str]:
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
    if not MEM_CFG.get("decay",{}).get("enabled", False): return
    now = time.time()
    hl = MEM_CFG["decay"].get("half_life_days", 90)
    floor = MEM_CFG["decay"].get("floor", 0.0)
    for ctxd in entry.get("contexts", {}).values():
        ls = ctxd.get("last_seen", 0)
        if not ls: continue
        days = (now - ls)/(24*3600)
        factor = 0.5 ** (days/hl)
        ctxd["score"] = max(ctxd.get("score",0.0)*factor, floor)

def memory_tail(entry, current_ctx, tier) -> str:
    if not MEM_CFG.get("enabled", False): return ""
    v = MEM_CFG.get("variants", {})
    t = MEM_CFG.get("tuning", {})
    contexts = entry.get("contexts", {})
    seen_total = sum(d.get("seen",0) for d in contexts.values())
    seen_here  = contexts.get(current_ctx, {}).get("seen",0)
    if seen_here > 1 and seen_total >= t.get("min_seen_for_repeat",2):
        pool = v.get("repeat", {}).get(tier, [])
        if pool: return " " + random.choice(pool)
    if seen_total >= t.get("min_seen_for_cross_context",2) and len(contexts)>1:
        sorted_ctx = sorted(contexts.items(), key=lambda kv: kv[1].get("score",-999), reverse=True)
        best_ctx, best_data = sorted_ctx[0]
        margin = t.get("confidence_margin", 0.75)
        if best_ctx != current_ctx and best_data.get("score",0.0) > contexts.get(current_ctx,{}).get("score",-999)+margin:
            pool = v.get("better_other", {}).get(tier, [])
            if pool: return " " + random.choice(pool).replace("{best}", best_ctx)
        elif best_ctx == current_ctx:
            pool = v.get("fits_here", {}).get(tier, [])
            if pool: return " " + random.choice(pool).replace("{here}", current_ctx)
    return ""

# --- Reactions + Bias + Specials ---
REACTIONS = read_json(RX_PATH, {})
THRESH = REACTIONS.get("thresholds", {"love":9,"like":3,"dislike":-3,"hate":-9})

def tier_from_score(s: float)->str:
    if s >= THRESH.get("love",9): return "love"
    if s >= THRESH.get("like",3): return "like"
    if s >  THRESH.get("dislike",-3): return "neutral"
    if s >  THRESH.get("hate",-9): return "dislike"
    return "hate"

def reaction_from_tier(tier: str) -> str:
    sets = REACTIONS.get("sets", {}).get(tier, [])
    if sets: return random.choice(sets)
    return REACTIONS.get("fallback", {}).get(tier, "...")

ARTIST_PREFS = REACTIONS.get("artist_preferences", {})  # score_bias + optional flip map per tier
def apply_artist_flip(tier: str, artists_norm: list) -> str:
    for a in artists_norm:
        flip = ARTIST_PREFS.get(a, {}).get("flip", {})
        if tier in flip and random.random() < float(flip[tier]):
            return {"dislike":"neutral","neutral":"like","like":"neutral"}.get(tier, tier)
    return tier

# helper: robust normalize (für Bias & Specials)
def _norm_txt(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("&","and")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s{2,}"," ", s)
    return s.strip()

# Specials aus reactions.json
SPECIAL_RULES = REACTIONS.get("special", [])

def match_special(title: str, artists_csv: str):
    """Return (forced_tier or None, custom_react or None) if any special matches."""
    tnorm = _norm_txt(title)
    anorm = _norm_txt(artists_csv)
    # einzelne Künstler auch gesondert prüfen
    artist_list = [a.strip() for a in re.split(r"[,&;/]+", artists_csv or "") if a.strip()]
    artist_list_norm = [_norm_txt(a) for a in artist_list]

    for rule in SPECIAL_RULES:
        titles = [_norm_txt(x) for x in rule.get("title_contains", []) if str(x).strip()]
        arts   = [_norm_txt(x) for x in rule.get("artist_contains", []) if str(x).strip()]
        cond_t = all((x in tnorm) for x in titles) if titles else True
        cond_a = True
        if arts:
            # match wenn irgendein artist token die vorgabe enthält
            cond_a = any((x in anorm) or any(x in a for a in artist_list_norm) for x in arts)
        if cond_t and cond_a:
            forced = rule.get("force_bucket")
            react  = rule.get("react")
            return forced, react
    return None, None

# --- Context ---
CONTEXTS = read_json(CTX_PATH, {"default_profile":"neutral","profiles":{"neutral":{"bucket_bias":{},"tag_weights":{},"artist_weights":{}}}})
def active_context() -> Tuple[str, dict]:
    source = CONTEXTS.get("source", {})
    current=""
    if source.get("type")=="file":
        p = (SCRIPT_DIR / source.get("path","Memory/game_state.txt")).resolve()
        try: current = p.read_text(encoding="utf-8").strip().lower() if p.exists() else ""
        except: current = ""
        current = source.get("map",{}).get(current, CONTEXTS.get("default_profile","neutral"))
    else:
        current = CONTEXTS.get("default_profile","neutral")
    prof = CONTEXTS.get("profiles", {}).get(current, CONTEXTS["profiles"]["neutral"])
    return current, prof

# --- LRU + TTL ---
class LRUCacheTTL:
    def __init__(self, maxsize=256, ttl=60):
        self.maxsize, self.ttl = maxsize, ttl
        self.data: Dict[tuple, tuple] = {}  # key -> (value, expire_ts)
    def get(self, key):
        v = self.data.get(key)
        if not v: return None
        val, exp = v
        if time.time()>exp: self.data.pop(key, None); return None
        return val
    def set(self, key, value):
        if len(self.data)>=self.maxsize:
            self.data.pop(next(iter(self.data)))
        self.data[key]=(value, time.time()+self.ttl)

RESULT_CACHE = LRUCacheTTL(maxsize=512, ttl=90)

# --- KB load ---
KB = load_kb_index_with_cache(KB_JSON, KB_CACHE)

def get_genres_from_entry(e: dict)->str:
    tags = list(e.get("tags", []))
    notes = KB._parse_notes(e)
    tags += notes.get("add_tags", [])
    return ", ".join(sorted(set(tags))) or "Unbekannt"

def find_kb_entry(title:str, artist_csv:str)->Optional[dict]:
    t = KB._norm(title)
    a = KB._norm(artist_csv)
    if (t,a) in KB.index["by_title_artist"]: return KB.index["by_title_artist"][(t,a)]
    cands = KB.index["by_title"].get(t, [])
    if len(cands)==1: return cands[0]
    if len(cands)>1:
        first = cands[0]; notes = KB._parse_notes(first)
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

def spotify_nowplaying()->Tuple[str,str]:
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
LISTEN_CFG = cfg.get("reactions", {}).get("listening", {"enabled":True,"text":"Listening…","random_delay":{"min_s":40,"max_s":60},"mid_texts":["Listening…"],"mid_switch_after_s":50})
pending_until = 0.0
mid_from = 0.0
cooldown_until = 0.0
last_key = None
last_song_log_ts = 0.0
last_written = None  # Mini-Patch: Write/Log nur bei Änderung
current_output = {"reaction":"","genres":"","title":"","artist":"","context":"","updated_at":""}

def compute_reaction(title:str, artists:str)->Tuple[str,str]:
    ctx, profile = active_context()
    key = (title, artists, ctx)
    cached = RESULT_CACHE.get(key)
    if cached: return cached

    # --- Specials (meme rules) ---
    forced_bucket, special_react = match_special(title, artists)

    # special-version like (nightcore/speed up) hint
    special_version = detect_special_version_tags(title)

    # KB lookup
    kb_entry = find_kb_entry(title, artists)

    # unknown policy (no KB entry)
    if not kb_entry and not forced_bucket:
        rx_cfg = read_json(RX_PATH, {})
        pol = rx_cfg.get("unknown_policy", {"enabled":True,"like":0.35,"neutral":0.40,"dislike":0.25})
        if pol.get("enabled",True):
            bucket = random.choices(["like","neutral","dislike"], weights=[pol["like"],pol["neutral"],pol["dislike"]], k=1)[0]
        else:
            bucket="neutral"
        reaction = reaction_from_tier(bucket)
        genres="Unbekannt"
        # Append special-version tag if any
        if special_version and cfg.get("show_special_version_in_genres", True):
            pref = cfg.get("special_version_prefix","")
            genres = f"{genres}{', ' if genres else ''}{pref}{special_version}"
        # If special forced bucket exists but no KB, still allow reaction override
        if forced_bucket:
            bucket = forced_bucket
            if special_react:
                reaction = special_react
        reaction = reaction.replace("{title}", title).replace("{artist}", artists).replace("{genres}", genres)
        RESULT_CACHE.set(key, (reaction, genres))
        return reaction, genres

    # --- Memory load/update
    mem = load_mem()
    if kb_entry:
        ekey = f"{KB._norm(kb_entry.get('title',''))} - {KB._norm(kb_entry.get('artist',''))}"
    else:
        ekey = f"{KB._norm(title)} - {KB._norm(artists)}"
    ment = mem.get(ekey, {"contexts":{}})
    apply_decay(ment)

    # --- Score-Breakdown (if no forced bucket)
    if not forced_bucket:
        ctx_data = ment.get("contexts", {}).get(ctx, {})
        base = ctx_data.get("score", 0.0)

        all_artists = [a.strip() for a in artists.split(",") if a.strip()]
        artist_weights = profile.get("artist_weights", {})
        artist_biases = []
        for a in all_artists:
            na = KB._norm(a)
            bias_ctx  = artist_weights.get(na, 0.0)
            bias_pref = ARTIST_PREFS.get(na, {}).get("score_bias", 0.0)
            artist_biases.append(bias_ctx + bias_pref)
        artist_bias = max(artist_biases) if artist_biases else 0.0

        tags = set(kb_entry.get("tags", [])) if kb_entry else set()
        tag_bias = sum(profile.get("tag_weights", {}).get(t, 0.0) for t in tags)

        # --- Normalisierte Bias-Sets (robust gegen 8-bit/8 bit & Sonderzeichen)
        bias_cfg = REACTIONS.get("bias", {})
        def _norm(s):  # inline helper
            s = s.lower().strip()
            s = s.replace("&","and")
            s = re.sub(r"[^\w\s]", " ", s)
            s = re.sub(r"\s{2,}"," ", s)
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

        prelim = base + artist_bias + tag_bias + extra_bias
        prelim_tier = tier_from_score(prelim)
        bucket_bias = profile.get("bucket_bias", {}).get(prelim_tier, 0.0)
        final_score = prelim + bucket_bias
        tier = tier_from_score(final_score)

        # EXPLORE policy (optional)
        expl = REACTIONS.get("explore", {"enabled": False})
        tier_before_explore = tier
        if expl.get("enabled", False):
            chance = float(expl.get("chance", 0.0))
            if random.random() < chance:
                w = expl.get("weights", {"like":0.45, "neutral":0.35, "dislike":0.20})
                tier = random.choices(["like","neutral","dislike"],
                                      weights=[w.get("like",0), w.get("neutral",0), w.get("dislike",0)], k=1)[0]

        # probabilistischer Flip
        tier_before_flip = tier
        tier = apply_artist_flip(tier, [KB._norm(a) for a in all_artists])

        # Debug / Sanity
        dbg(
            f"[score] base={base:+.2f} | artist_bias={artist_bias:+.2f} | tag_bias={tag_bias:+.2f} "
            f"| extra_bias={extra_bias:+.2f} | prelim={prelim:+.2f} ({prelim_tier}) "
            f"| bucket_bias={bucket_bias:+.2f} | final={final_score:+.2f} → tier={tier_before_explore}"
        )
        if expl.get("enabled", False):
            dbg(f"[explore] chance={expl.get('chance')} → tier_after_explore={tier_before_flip}")
        dbg(f"[flip] tier_before_flip={tier_before_flip} → tier_final={tier}")

    else:
        # Special forces a bucket (e.g., like)
        tier = forced_bucket

    # Reaction + Genres
    genres = "Unbekannt"
    if kb_entry:
        genres = get_genres_from_entry(kb_entry)
    if special_version and cfg.get("show_special_version_in_genres", True):
        pref = cfg.get("special_version_prefix","")
        genres = f"{genres}{', ' if genres else ''}{pref}{special_version}"

    if special_react:
        reaction = special_react
    else:
        reaction = reaction_from_tier(tier)

    # memory tail
    tail = memory_tail(ment, ctx, tier)
    reaction = reaction.replace("{title}", title).replace("{artist}", artists).replace("{genres}", genres) + tail

    # persist memory
    now = time.time()
    c = ment.setdefault("contexts", {}).setdefault(ctx, {"seen":0,"score":0.0,"last_seen":0})
    c["seen"] += 1
    c["last_seen"] = now
    c["score"] = max(-10.0, min(10.0, c.get("score",0.0) + ( 1.0 if tier in ["love","like"] else (-1.0 if tier in ["dislike","hate"] else 0.1) )))
    mem[ekey]=ment; save_mem(mem)

    RESULT_CACHE.set(key, (reaction, genres))
    return reaction, genres

def tick_loop():
    global pending_until, mid_from, cooldown_until, last_key, last_song_log_ts, last_written, current_output
    while True:
        try:
            title, artists = spotify_nowplaying()
            if not title and not artists:
                time.sleep(INTERVAL_S); continue

            ctx, _ = active_context()
            key = (title, artists, ctx)
            now = time.time()

            # New song? -> Listening & Genres sofort + einmalig loggen
            if key != last_key:
                last_key = key
                pending_until = now + random.uniform(LISTEN_CFG.get("random_delay",{}).get("min_s",40),
                                                     LISTEN_CFG.get("random_delay",{}).get("max_s",60))
                mid_from = now + float(LISTEN_CFG.get("mid_switch_after_s",50))
                cooldown_until = now + 4.0

                # Listening sofort
                write_reaction(LISTEN_CFG.get("text","Listening…"))

                # Genres sofort
                special = detect_special_version_tags(title)
                kb_entry = find_kb_entry(title, artists)
                if kb_entry:
                    genres_now = get_genres_from_entry(kb_entry)
                    if special and cfg.get("show_special_version_in_genres", True):
                        pref = cfg.get("special_version_prefix","")
                        genres_now = f"{genres_now}{', ' if genres_now else ''}{pref}{special}"
                else:
                    genres_now = "Unbekannt"
                write_genres(genres_now)

                current_output = {
                    "reaction": LISTEN_CFG.get("text","Listening…"),
                    "genres": genres_now,
                    "title": title, "artist": artists, "context": ctx,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

                last_song_log_ts = now
                dbg(f"[song] ▶ {title} — {artists} | ctx={ctx} | genres='{genres_now}' (reaction pending)")
            else:
                # Keep-alive: höchstens alle 20s
                if now - last_song_log_ts > 20:
                    dbg(f"[song-keepalive] ▶ {title} — {artists} | ctx={ctx} (still pending)")
                    last_song_log_ts = now

            # still pending?
            if now < pending_until:
                if now > mid_from and random.random()<0.25:
                    mids = LISTEN_CFG.get("mid_texts", ["Listening…"])
                    mid = random.choice(mids)
                    if time.time()>cooldown_until:
                        write_reaction(mid)
                        cooldown_until = time.time()+1.5
                        current_output["reaction"]=mid
                time.sleep(INTERVAL_S); continue

            # final compute
            reaction, genres = compute_reaction(title, artists)
            state_tuple = (reaction, genres, title, artists, ctx)

            if state_tuple != last_written:
                if time.time()>cooldown_until:
                    write_reaction(reaction)
                    write_genres(genres)
                    cooldown_until = time.time()+1.5
                    dbg(f"[final] {title} — {artists} | ctx={ctx} | reaction='{reaction}' | genres='{genres}'")

                current_output = {
                    "reaction": reaction,
                    "genres": genres,
                    "title": title, "artist": artists, "context": ctx,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                last_written = state_tuple

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
