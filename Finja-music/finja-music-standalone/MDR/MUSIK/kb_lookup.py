# kb_lookup.py

"""
======================================================================
                Finja's Brain & Knowledge Core - MDR
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (MDR Modul)

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations
import json, re
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional, Tuple, Dict, Any, List

NORMALIZE_RE = re.compile(r"[\s\-\_\.\,\;\:\!\?\|/]+")

def _strip_parens(s: str) -> str:
    # Entfernt (feat. …), (Remix), [Live], etc.
    return re.sub(r"[\(\[].*?[\)\]]", "", s)

def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = _strip_parens(s)
    s = s.replace("&", "and")
    s = re.sub(r"feat\.?|featuring", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = NORMALIZE_RE.sub(" ", s)
    return s.strip()

def _title_artist_keys(title: str, artist: Optional[str]) -> Tuple[str, Optional[str]]:
    t = _normalize(title)
    a = _normalize(artist) if artist else None
    return t, a

def _best_match(
    target_title: str,
    target_artist: Optional[str],
    entries: List[Dict[str, Any]],
    title_key: str = "title",
    artist_key: str = "artist"
) -> Optional[Dict[str, Any]]:
    """
    Heuristik:
    1) exakter Normalized-Match (title+artist)
    2) exakter Normalized-Match (nur title)
    3) fuzzy (title+artist)
    4) fuzzy (nur title)
    """
    t_norm, a_norm = _title_artist_keys(target_title, target_artist)

    # Vorindex: Normalisierte Keys
    def norm_entry(e: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        et = _normalize(str(e.get(title_key, "")))
        ea_raw = e.get(artist_key)
        ea = _normalize(str(ea_raw)) if ea_raw else None
        return et, ea

    # 1) exact title+artist
    for e in entries:
        et, ea = norm_entry(e)
        if et == t_norm and ea and a_norm and ea == a_norm:
            return e

    # 2) exact title
    for e in entries:
        et, _ = norm_entry(e)
        if et == t_norm:
            return e

    # 3) fuzzy title+artist
    best = None
    best_score = 0.0
    for e in entries:
        et, ea = norm_entry(e)
        title_score = SequenceMatcher(a=t_norm, b=et).ratio()
        artist_score = SequenceMatcher(a=a_norm or "", b=ea or "").ratio()
        score = (title_score * 0.8) + (artist_score * 0.2)
        if score > best_score:
            best, best_score = e, score
    if best and best_score >= 0.86:
        return best

    # 4) fuzzy title only
    best = None
    best_score = 0.0
    for e in entries:
        et, _ = norm_entry(e)
        score = SequenceMatcher(a=t_norm, b=et).ratio()
        if score > best_score:
            best, best_score = e, score
    if best and best_score >= 0.92:
        return best

    return None

def load_songs_kb(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"songs_kb not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Akzeptiere sowohl {"songs":[...]} als auch direkt eine Liste
    if isinstance(data, dict) and "songs" in data and isinstance(data["songs"], list):
        return data["songs"]
    if isinstance(data, list):
        return data
    raise ValueError("songs_kb.json hat ein unerwartetes Format")

def genres_for_track(
    title: str,
    artist: Optional[str],
    kb_path: str | Path = "songs_kb.json"
) -> Optional[List[str]]:
    entries = load_songs_kb(kb_path)
    match = _best_match(title, artist, entries)
    if not match:
        return None

    # Unterstütze verschiedene Feldnamen: "genres", "genre", "primary_genres"
    for key in ("genres", "genre", "primary_genres"):
        if key in match:
            g = match[key]
            if isinstance(g, str):
                # split by comma/semicolon
                parts = [x.strip() for x in re.split(r"[;,]", g) if x.strip()]
                return parts or None
            if isinstance(g, list):
                parts = [str(x).strip() for x in g if str(x).strip()]
                return parts or None
    return None
