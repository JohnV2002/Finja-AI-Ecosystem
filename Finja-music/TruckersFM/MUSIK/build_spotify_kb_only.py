#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# build_spotify_kb_merge.py — Merge neue Spotify-Exports in bestehende songs_kb.json
# Basis: build_spotify_kb_only.py (KB-Builder) :contentReference[oaicite:0]{index=0}

"""
======================================================================
                Finja's Brain & Knowledge Core - TruckersFM
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (TruckersFM Modul)

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations
import sys, os, glob, csv, json, re, random, tempfile, shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from collections import Counter

SCRIPT_DIR = Path(__file__).resolve().parent
random.seed(42)

# --- Settings (aus Original) ---
IGNORE_TAGS_FOR_SFT = {"mix", "playlist", "20s", "10s", "00s"}  # spätere SFT-Ignorierliste
PLAYLIST_HINTS_ONLY_IF_NO_GENRES = True

# ----------------- Helpers -----------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def strip_parens(s: str) -> str:
    return re.sub(r"\s*[\(\[\{].*?[\)\]\}]\s*", " ", s or "").strip()

def basic_aliases(title: str) -> List[str]:
    t0 = title or ""
    t1 = strip_parens(t0)
    al = {
        t0, t1,
        t0.lower(), t1.lower(),
        re.sub(r"[^\w\s]", "", t0).strip().lower(),
        re.sub(r"[^\w\s]", "", t1).strip().lower(),
    }
    return [a for a in sorted({x for x in al if x}) if a]

# --- Genre-Normalisierung (ausgebaut wie im Original) ---
_GENRE_SYNONYMS = {
    # core / chill
    "lofi": "lofi", "lo-fi": "lofi", "lofi hip hop": "lofi", "study beats": "lofi",
    "chill": "chill", "chill out": "chill", "chillout": "chillout",
    "chillhop": "chillhop", "chill hop": "chillhop", "jazzhop": "jazzhop",
    "ambient": "ambient", "bgm": "ambient", "downtempo": "downtempo",
    # soundtrack / games
    "soundtrack": "soundtrack", "score": "soundtrack",
    "ost": "game ost", "game ost": "game ost", "bgm ost": "game ost",
    # hip hop / r&b
    "rap": "rap", "hip hop": "rap", "hip-hop": "rap", "boom bap": "rap",
    "german rap": "german rap", "deutschrap": "german rap",
    "trap": "trap", "trap aggressive": "trap", "drill": "drill", "uk drill": "drill",
    "r&b": "r&b", "rnb": "r&b", "neo-soul": "neo-soul", "soul": "soul", "funk": "funk",
    # pop & regional pop
    "pop": "pop", "dance pop": "dance pop", "indie pop": "indie pop",
    "german pop": "german pop", "deutschpop": "german pop",
    "latin pop": "latin pop", "k-pop": "k-pop", "kpop": "k-pop",
    "j-pop": "j-pop", "jpop": "j-pop", "city pop": "city pop",
    # rock / alt
    "rock": "rock", "indie rock": "indie rock", "alt rock": "alternative rock",
    "alternative rock": "alternative rock", "classic rock": "classic rock",
    "hard rock": "hard rock", "punk": "punk", "pop punk": "pop punk",
    "emo": "emo", "shoegaze": "shoegaze", "dream pop": "dream pop",
    "post punk": "post-punk", "post-punk": "post-punk", "new wave": "new wave",
    "grunge": "grunge", "metal": "metal",
    # edm umbrella
    "edm": "edm", "dance": "dance",
    "bigroom": "big room", "big room": "big room", "festival edm": "big room",
    "future bass": "future bass", "future house": "future house",
    "progressive house": "progressive house", "prog house": "progressive house",
    "deep house": "deep house", "tech house": "tech house",
    "bass house": "bass house",
    "electro house": "electrohouse", "electrohouse": "electrohouse",
    "house": "house",
    # techno family
    "techno": "techno", "hard techno": "hard techno", "peak time techno": "hard techno",
    "melodic techno": "melodic techno", "minimal": "minimal", "minimal techno": "minimal",
    "industrial techno": "industrial techno", "schranz": "hard techno", "hardgroove": "hardgroove",
    "acid": "acid", "acid techno": "acid",
    # trance family
    "trance": "trance", "uplifting trance": "trance",
    "progressive trance": "progressive trance", "psytrance": "psytrance",
    "goa": "psytrance", "hard trance": "hard trance",
    # euro / retro
    "hands up": "hands up", "eurodance": "eurodance",
    "eurobeat": "eurobeat", "italo disco": "italo disco",
    "disco": "disco", "nu-disco": "nu-disco",
    "synthwave": "synthwave", "retrowave": "synthwave", "outrun": "synthwave",
    "vaporwave": "vaporwave",
    # bass music
    "dnb": "dnb", "drum and bass": "dnb", "liquid dnb": "dnb", "neurofunk": "dnb",
    "jungle": "jungle",
    "dubstep": "dubstep", "riddim": "dubstep", "brostep": "dubstep",
    "breakbeat": "breakbeat", "breaks": "breakbeat", "breakcore": "breakcore",
    "garage": "garage", "uk garage": "uk garage", "2-step": "uk garage",
    "bassline": "bassline",
    # harder styles
    "hardstyle": "hardstyle", "rawstyle": "hardstyle",
    "hardcore": "hardcore", "happy hardcore": "happy hardcore",
    "gabber": "gabber", "speedcore": "speedcore",
    "frenchcore": "frenchcore", "terrorcore": "terrorcore",
    "tekno": "tekno",
    # latin / global
    "moombahton": "moombahton", "reggaeton": "reggaeton",
    "dancehall": "dancehall", "afrobeats": "afrobeats", "afrobeat": "afrobeats",
    "baile funk": "baile funk",
    # alt/dark
    "witch house": "witch house", "darkwave": "darkwave",
    "industrial": "industrial", "ebm": "ebm",
    # jp/kr rock
    "j-rock": "j-rock", "jrock": "j-rock", "k-rock": "k-rock",
    # acoustic / orchestral
    "folk": "folk", "acoustic": "acoustic", "singer-songwriter": "singer-songwriter",
    "piano": "piano", "orchestral": "orchestral", "classical": "classical",
    "strings": "orchestral", "symphonic": "orchestral",
    # meme/speed edits
    "nightcore": "nightcore", "sped up": "sped up", "speed up": "sped up",
    "slowed": "slowed", "slowed & reverb": "slowed", "slowed + reverb": "slowed",
    "tiktok": "tiktok", "meme": "meme",
    # versions / mixes
    "radio edit": "radio edit", "radio mix": "radio edit",
    "extended mix": "extended", "extended": "extended",
    "club mix": "club mix", "remix": "remix", "bootleg": "bootleg", "edit": "edit",
    # seasons
    "holiday": "holiday", "christmas": "christmas", "xmas": "christmas",
}

def tags_from_genres(genres_str: str) -> List[str]:
    if not genres_str:
        return []
    parts = re.split(r"[;,/|]+", genres_str.lower())
    out = set()
    def _n(s: str) -> str:
        s = s.strip()
        s = re.sub(r"[–—−]", "-", s)
        s = re.sub(r"\s+", " ", s)
        return s
    for raw in (x for x in parts if x.strip()):
        p = _n(raw)
        if p in _GENRE_SYNONYMS:
            out.add(_GENRE_SYNONYMS[p]); continue
        for k, v in _GENRE_SYNONYMS.items():
            if k in p:
                out.add(v)
    return sorted(out)

def tags_from_bpm(tempo: float) -> List[str]:
    t = tempo
    if t <= 0: return []
    out = []
    if 84<=t<=96: out.append("phonk")
    if 160<=t<=175: out.append("dnb")
    if 125<=t<=132: out.append("house")
    if 132<=t<=150: out.append("techno")
    if 150<=t<=200: out.append("hardstyle")
    return out

def era_tags_from_date(release_date: str) -> List[str]:
    m = re.match(r"(\d{4})", release_date or "")
    if not m: return []
    y = int(m.group(1)); era=[]
    if 1990<=y<=1999: era+=["90s"]
    if 2000<=y<=2009: era+=["2000s","00s","y2k"]
    if 2010<=y<=2019: era+=["2010s","10s"]
    if 2020<=y<=2029: era+=["2020s"]
    return era

def detect_playlist_hint(path: str, had_genres: bool) -> List[str]:
    if PLAYLIST_HINTS_ONLY_IF_NO_GENRES and had_genres:
        return []
    s = (path or "").lower()
    hints = []
    if "truckersfm" in s: hints += ["truckersfm","chart"]
    if "execute" in s: hints += ["execute","german rap","gamer"]
    mapx = {
        "zelda": ["zelda","lofi","ambient","game ost"],
        "lofi": ["lofi","chill"],
        "tekk": ["tekno","hard techno","rave"],
        "techno": ["techno"],
        "house": ["house"],
        "chillout": ["chillout","chill"],
        "breakcore": ["breakcore"],
        "phonk": ["phonk","drift phonk"],
        "hyperpop": ["hyperpop"],
        "witch house": ["witch house"],
        "electrohouse": ["electrohouse"],
        "frenchcore": ["frenchcore"],
        "tekno": ["tekno"],
        "hardstyle": ["hardstyle"],
        "2000er": ["2000s","00s","y2k"],
        "2010er": ["2010s","10s"],
        "2020er": ["2020s"],
        "mix": ["mix","playlist"],
    }
    for k, t in mapx.items():
        if k in s: hints += t
    return sorted(set(hints))

# --- Sicherheit / Schreiben (wie Original) ---
def validate_user_path(
    p_str: str,
    *,
    allowed_suffixes: Optional[tuple]=None,
    must_exist: bool=True,
    base_dir: Optional[Path]=SCRIPT_DIR,
) -> Path:
    if p_str is None:
        raise ValueError("Pfad fehlt.")
    if "\x00" in p_str:
        raise ValueError("Ungültiger Pfad (Null-Byte).")
    if re.search(r'(^|[\\/])\.\.([\\/]|$)', p_str):
        raise ValueError("Pfad darf keine '..'-Segmente enthalten.")
    p = Path(p_str)
    try:
        p_res = p.resolve()
    except Exception:
        raise ValueError(f"Pfad kann nicht aufgelöst werden: {p_str}")
    if base_dir is not None:
        base_res = base_dir.resolve()
        if p_res != base_res and base_res not in p_res.parents:
            raise ValueError(f"Pfad liegt nicht unter dem erlaubten Basisordner: {base_res}")
    if must_exist:
        if not p_res.exists():
            raise FileNotFoundError(f"Datei/Ordner nicht gefunden: {p_res}")
    if allowed_suffixes:
        if not p_res.is_file():
            raise ValueError(f"Erwarte Datei mit {allowed_suffixes}, gefunden Ordner: {p_res}")
        if p_res.suffix.lower() not in {s.lower() for s in allowed_suffixes}:
            raise ValueError(f"Unerlaubte Dateiendung: {p_res.suffix} (erlaubt: {', '.join(allowed_suffixes)})")
    return p_res

def atomic_write_text(path: Path, text: str, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding=encoding, dir=str(path.parent)) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), str(path))

# ----------------- Input Parsing -----------------
@dataclass
class Track:
    title: str
    artist: str
    album: str = ""
    source: str = ""
    added_at: str = ""
    uri: str = ""
    genres: str = ""
    label: str = ""
    tempo: float = 0.0
    release_date: str = ""
    def key(self) -> str: return f"{(self.title or '').lower()}::{(self.artist or '').lower()}"

def parse_row_csv(row: Dict[str, str]) -> Optional[Track]:
    H = {k.lower(): k for k in row.keys()}
    def get(*opts):
        for o in opts:
            if o.lower() in H: return (row.get(H[o.lower()]) or "").strip()
        return ""
    def getf(*opts) -> float:
        v = get(*opts)
        try: return float(v.replace(",", ".")) if v else 0.0
        except: return 0.0
    title = get("Track Name","Title","Song","Name")
    artist = get("Artist Name(s)","Artist","Artists")
    if not title or not artist: return None
    return Track(
        title=title, artist=artist,
        album=get("Album Name","Album"),
        uri=get("Track URI","URI","Url","URL"),
        added_at=get("Added At","Date Added","Added"),
        genres=get("Genres","Genre"),
        label=get("Record Label","Label"),
        tempo=getf("Tempo","BPM"),
        release_date=get("Release Date","Released","Date"),
    )

def parse_txt_line(line: str) -> Optional[Track]:
    s = line.strip()
    if not s: return None
    m = re.match(r"^(?P<artist>.+?)\s*[-—]\s*(?P<title>.+)$", s)
    if m: return Track(title=m.group("title").strip(), artist=m.group("artist").strip())
    return Track(title=s, artist="")

def read_inputs(paths: List[str]) -> List[Track]:
    items: List[Track] = []

    def safe_glob_one(pattern: str) -> List[Path]:
        if "\x00" in pattern or re.search(r'(^|[\\/])\.\.([\\/]|$)', pattern):
            raise ValueError(f"Unsicheres Muster: {pattern}")
        matches = [Path(p) for p in glob.glob(pattern, recursive=True)]
        safe: List[Path] = []
        for m in matches:
            if m.suffix.lower() not in {".csv", ".txt"}:
                continue
            pm = validate_user_path(str(m), allowed_suffixes=None, must_exist=True, base_dir=SCRIPT_DIR)
            if not pm.is_file():
                continue
            safe.append(pm)
        return safe

    for g in paths:
        for fp in safe_glob_one(g):
            ext = fp.suffix.lower()
            if ext == ".csv":
                with fp.open("r", encoding="utf-8", errors="ignore") as f:
                    try:
                        sample = f.read(4096); f.seek(0)
                        try:
                            reader = csv.DictReader(f, dialect=csv.Sniffer().sniff(sample))
                        except Exception:
                            reader = csv.DictReader(f)
                    except Exception:
                        continue
                    for row in reader:
                        tr = parse_row_csv(row)
                        if tr:
                            tr.source = str(fp)
                            items.append(tr)
            elif ext == ".txt":
                with fp.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        tr = parse_txt_line(line)
                        if tr:
                            tr.source = str(fp)
                            items.append(tr)
    return items

# ----------------- Tagging -----------------
def guess_tags(title: str, artist: str, album: str, genres: str = "",
               label: str = "", tempo: float = 0.0) -> List[str]:
    t = (f"{title} {artist} {album} {genres} {label}").lower()
    base = tags_from_genres(genres)
    tags = set(base)

    if not base:
        tags.update(tags_from_bpm(tempo))

    for kw, tg in [
        ("remix","remix"),("radio edit","radio edit"),("instrumental","instrumental"),
        ("lofi","lofi"),("edm","edm"),("trance","trance"),("techno","techno"),
        ("house","house"),("metal","metal"),("rock","rock"),("pop","pop"),("rap","rap"),
        ("hip hop","rap"),("drum and bass","dnb"),("dnb","dnb"),("dubstep","dubstep"),
        ("anthem","anthem"),("theme","theme"),("live","live"),("extended","extended"),
        ("phonk","phonk"),("drift phonk","drift phonk"),("witch house","witch house"),
        ("hyperpop","hyperpop"),("tekno","tekno"),("frenchcore","frenchcore"),
        ("electro house","electrohouse"),("electrohouse","electrohouse"),
        ("breakcore","breakcore"),("chillout","chillout"),("chill","chill"),
    ]:
        if kw in t: tags.add(tg)

    if "execute" in (artist or "").lower():
        tags.update(["german rap","gamer"])
        if "telekom" in t: tags.add("meme")
    if any(k in t for k in ["minecraft","c418","lena raine","pigstep"]):
        tags.add("minecraft")
        if "c418" in t: tags.add("ambient")

    ttl = (title or "").lower()
    for pat, tg in [
        (r"\bsped ?up\b","sped up"),
        (r"\bslowed( & reverb| and reverb)?\b","slowed"),
        (r"\bnightcore\b","nightcore"),
        (r"\bedit\b","edit"),
        (r"\bbootleg\b","bootleg"),
    ]:
        if re.search(pat, ttl): tags.add(tg)

    return sorted(tags)

# ---- KB Merge Logic ----
def track_to_entry(tr: Track) -> Dict:
    genre_tags = tags_from_genres(tr.genres)
    tags = set(guess_tags(tr.title, tr.artist, tr.album, tr.genres, tr.label, tr.tempo))
    tags.update(era_tags_from_date(tr.release_date))
    tags.update(detect_playlist_hint(tr.source, had_genres=bool(genre_tags)))
    notes = "Execute-Track; nur Vibe kommentieren, keine Lyrics/Links." if "execute" in (tr.artist or "").lower() else ""
    return {
        "title": norm(tr.title),
        "artist": norm(tr.artist),
        "album": norm(tr.album),
        "aliases": basic_aliases(tr.title),
        "tags": sorted({x for x in tags if x}),
        "notes": notes,
    }

def kb_key_of(entry: Dict) -> str:
    return f"{(entry.get('title') or '').lower()}::{(entry.get('artist') or '').lower()}"

def merge_entry(base: Dict, newe: Dict) -> Dict:
    # Titel/Artist sind identisch per Key; normalisieren sicherheitshalber
    out = dict(base)
    out["title"] = norm(base.get("title") or newe.get("title") or "")
    out["artist"] = norm(base.get("artist") or newe.get("artist") or "")

    # Album: nur ergänzen, wenn leer
    if not (out.get("album") or "").strip():
        out["album"] = norm(newe.get("album") or "")

    # Aliases: Union (lower-case dedupe, aber Originalform behalten)
    def _dedupe_aliases(a: List[str]) -> List[str]:
        seen=set(); res=[]
        for x in a or []:
            key = x.strip().lower()
            if key and key not in seen:
                seen.add(key); res.append(x.strip())
        return res
    out["aliases"] = _dedupe_aliases((out.get("aliases") or []) + (newe.get("aliases") or []))

    # Tags: Union (alte bleiben, neue kommen dazu)
    old_tags = set(out.get("tags") or [])
    new_tags = set(newe.get("tags") or [])
    out["tags"] = sorted(old_tags | new_tags)

    # Notes: nur ergänzen, wenn leer
    if not (out.get("notes") or "").strip():
        out["notes"] = newe.get("notes") or ""

    return out

def load_existing_kb(kb_path: Optional[str]) -> List[Dict]:
    if not kb_path:
        return []
    p = validate_user_path(kb_path, allowed_suffixes=(".json",), must_exist=True, base_dir=SCRIPT_DIR)
    with p.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("KB muss eine JSON-Liste sein.")
            return data
        except Exception as e:
            raise RuntimeError(f"KB konnte nicht gelesen werden: {e}")

def build_and_merge(existing: List[Dict], tracks: List[Track]) -> List[Dict]:
    # Index bestehende KB per Key
    idx: Dict[str, Dict] = {}
    for e in existing:
        idx[kb_key_of(e)] = {
            "title": norm(e.get("title","")),
            "artist": norm(e.get("artist","")),
            "album": norm(e.get("album","")),
            "aliases": list(e.get("aliases") or []),
            "tags": list(e.get("tags") or []),
            "notes": e.get("notes","") or "",
        }

    # Neue/aktualisierte Einträge einarbeiten
    for tr in tracks:
        if not tr.title or not tr.artist:
            continue
        ne = track_to_entry(tr)
        key = kb_key_of(ne)
        if key in idx:
            idx[key] = merge_entry(idx[key], ne)
        else:
            idx[key] = ne

    # Rückgabe als Liste (stabil sortiert nach Artist, Title)
    out = list(idx.values())
    out.sort(key=lambda e: (e.get("artist","").lower(), e.get("title","").lower()))
    return out

# ----------------- CLI -----------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Merge Spotify-Exports in bestehende songs_kb.json (Genres/Tags nur ergänzen).")
    ap.add_argument("--kb", type=str, required=True, help="Pfad zur bestehenden songs_kb.json")
    ap.add_argument("--inputs", nargs="+", required=True, help="Globs, z.B. exports/*.csv exports/*.txt")
    ap.add_argument("--outdir", type=str, default=None, help="Zielordner (Standard: Ordner der KB)")
    ap.add_argument("--inplace", action="store_true", help="Ergebnis direkt in die gegebene --kb zurückschreiben")
    ap.add_argument("--pretty", action="store_true", help="JSON hübsch formatieren")
    args = ap.parse_args()

    # Inputs expandieren (freundlicher Fehler)
    expanded=[]
    for g in args.inputs: expanded.extend(glob.glob(g))
    if not expanded:
        print("No input files found.", file=sys.stderr); sys.exit(1)

    existing = load_existing_kb(args.kb)
    tracks   = read_inputs(args.inputs)
    if not tracks:
        print("No tracks parsed.", file=sys.stderr); sys.exit(2)

    merged = build_and_merge(existing, tracks)

    # Stats
    artists = sorted({e["artist"] for e in merged})
    tag_counter = Counter()
    for e in merged:
        for t in e.get("tags",[]) or ["untagged"]:
            tag_counter[t] += 1
    print(f"Merged KB size: {len(merged)}")
    print(f"Unique artists: {len(artists)}")
    print("Top tags:", tag_counter.most_common(15))

    # Zielpfad bestimmen
    kb_path = validate_user_path(args.kb, allowed_suffixes=(".json",), must_exist=True, base_dir=SCRIPT_DIR)
    if args.inplace:
        out_path = kb_path
    else:
        if args.outdir:
            outdir = validate_user_path(args.outdir, must_exist=False, base_dir=SCRIPT_DIR)
        else:
            outdir = kb_path.parent
        outdir.mkdir(parents=True, exist_ok=True)
        out_path = outdir / "songs_kb.json"

    # Schreiben
    kb_json = json.dumps(merged, ensure_ascii=False, indent=2 if args.pretty else None)
    atomic_write_text(out_path, kb_json, encoding="utf-8")
    print("Wrote KB:", out_path)

if __name__ == "__main__":
    main()
