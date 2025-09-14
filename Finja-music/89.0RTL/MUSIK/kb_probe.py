# -*- coding: utf-8 -*-
"""
======================================================================
            Finja's Brain & Knowledge Core - 89.0 RTL
======================================================================

  Project: Twitch Interactivity Suite
  Version: 1.0.0 (89.0 RTL Modul)
  Author:  JohnV2002 (J. Apps / Sodakiller1)
  License: MIT License (c) 2025 J. Apps

----------------------------------------------------------------------
 Nutzung:
 ---------------------------------------------------------------------

  python kb_probe.py --line "Hello — Martin Solveig, Dragonette" --kb C:/.../songs_kb.json
  python kb_probe.py --file C:/.../nowplaying.txt --kb C:/.../songs_kb.json

----------------------------------------------------------------------
 Hinweis::
 ---------------------------------------------------------------------

  --idx wird aus Kompatibilitätsgründen akzeptiert, aber ignoriert (kein pickle).

======================================================================
"""

import argparse, json, re, sys
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional, Tuple, List, Dict, Any

# ---------- Pfad-Validierung (gegen Path Traversal) ----------
def validate_user_path(
    p_str: str,
    allowed_suffixes=(".json",),
    must_exist: bool = True,
    base_dir: Optional[Path] = None,
) -> Path:
    """
    Validiert einen vom Nutzer kommenden Pfad:
    - verbietet Null-Bytes & '..' Segmente
    - erzwingt erlaubte Dateiendungen
    - (optional) erzwingt Unterpfad von base_dir
    - prüft Existenz & Datei-Typ
    """
    if p_str is None:
        raise ValueError("Pfad fehlt.")
    if "\x00" in p_str:
        raise ValueError("Ungültiger Pfad (Null-Byte).")
    # Einfacher traversal check auf Rohstring-Ebene
    if re.search(r'(^|[\\/])\.\.([\\/]|$)', p_str):
        raise ValueError("Pfad darf keine '..'-Segmente enthalten.")

    p = Path(p_str)

    # Optional: auf einen sicheren Root einschränken
    if base_dir is not None:
        try:
            p_res = p.resolve()
            base_res = base_dir.resolve()
            if base_res != p_res and base_res not in p_res.parents:
                raise ValueError(f"Pfad liegt nicht unter dem erlaubten Basisordner: {base_res}")
        except Exception:
            raise ValueError("Pfad konnte nicht sicher aufgelöst werden.")

    # Endungen prüfen
    if allowed_suffixes:
        if p.suffix.lower() not in {s.lower() for s in allowed_suffixes}:
            raise ValueError(f"Unerlaubte Dateiendung: {p.suffix} (erlaubt: {', '.join(allowed_suffixes)})")

    if must_exist:
        if not p.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {p}")
        if not p.is_file():
            raise ValueError(f"Pfad ist keine Datei: {p}")

    return p.resolve()


# --------- Normalisierung & Parsing (identisch zum Writer) ----------
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

DASH_SEPS = [" — ", " – ", " - ", " ~ ", " | ", " • "]

def parse_title_artist(text: str) -> Tuple[Optional[str], Optional[str]]:
    text = (text or "").strip()
    if not text:
        return None, None

    # JSON
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
        left = m.group("title")
        by_pos = left.lower().rfind(" by ")
        if by_pos != -1 and left.rfind("(") != -1 and left.rfind("(") < by_pos and left.find(")", by_pos) != -1:
            return left.strip(), m.group("artist").strip()
        return m.group("title").strip(), m.group("artist").strip()

    for sep in DASH_SEPS:
        if sep in line:
            left, right = [p.strip() for p in line.split(sep, 1)]
            if left and right:
                return right, left

    return line or None, None


# --------- KB Index (wie im Writer, aber ohne pickle) ----------
def load_songs_kb(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("songs"), list):
        return data["songs"]
    if isinstance(data, list):
        return data
    raise ValueError("songs_kb.json hat ein unerwartetes Format")

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
        if a and (t, a) in self.by_title_artist:
            return self.by_title_artist[(t, a)]
        if t in self.by_title and self.by_title[t]:
            return self.by_title[t][0]
        return None

    def fuzzy(self, title: Optional[str], artist: Optional[str]) -> Optional[Dict[str, Any]]:
        if not title:
            return None
        t = _normalize(title)
        a = _normalize(artist) if artist else ""
        prefix = t[:8]
        cands = []
        for tt, entries in self.by_title.items():
            if tt.startswith(prefix) or prefix.startswith(tt[:4]):
                cands.extend(entries)
            if len(cands) > 160:
                break
        best, best_score = None, 0.0
        for e in cands:
            et = _normalize(str(e.get(self.title_key, "")))
            aliases = e.get("aliases") or []
            alias_norms = [_normalize(str(x)) for x in aliases if str(x).strip()]
            et_best = max([SequenceMatcher(a=t, b=et).ratio()] + [SequenceMatcher(a=t, b=ax).ratio() for ax in alias_norms])
            ea = _normalize(str(e.get(self.artist_key, "")))
            a_score = SequenceMatcher(a=a, b=ea).ratio() if a else 0.0
            score = (et_best * 0.88) + (a_score * 0.12)
            if score > best_score:
                best, best_score = e, score
        if best and best_score >= 0.92:
            return best
        return None

def extract_genres(entry: Dict[str, Any]) -> Optional[List[str]]:
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

def load_or_build_kb_index(kb_json_path: Path) -> KBIndex:
    entries = load_songs_kb(kb_json_path)
    return KBIndex(entries)

# --------- CLI ---------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", help="Eine Testzeile (z. B. 'Title — Artist').")
    ap.add_argument("--file", help="Pfad zu nowplaying.txt (liest ersten nichtleeren Block).")
    ap.add_argument("--kb", required=True, help="Pfad zu songs_kb.json")
    ap.add_argument("--idx", help="(Ignoriert) Pfad zu altem .pkl Index-Cache")
    args = ap.parse_args()

    # Optional: base_dir auf das Script-Dir einschränken (hier None gelassen, damit deine absoluten Pfade gehen)
    base_dir = None  # Path(__file__).resolve().parent  # <- aktivieren, falls du einschränken willst

    # Sichere Pfade erzeugen
    kb_path = validate_user_path(args.kb, allowed_suffixes=(".json",), must_exist=True, base_dir=base_dir)

    if args.idx:
        print(f"[probe] Hinweis: --idx '{args.idx}' wird ignoriert (kein pickle).")

    idx = load_or_build_kb_index(kb_path)

    if args.file:
        file_path = validate_user_path(args.file, allowed_suffixes=(".txt", ".json"), must_exist=True, base_dir=base_dir)
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
    else:
        raw = args.line or ""

    title, artist = parse_title_artist(raw)
    print(f"[probe] parsed  title={title!r} | artist={artist!r}")

    if not title:
        print("[probe] kein Titel erkannt – Ende.")
        return

    hit_type = "none"
    entry = idx.exact(title, artist)
    if entry:
        hit_type = "exact"
    else:
        entry = idx.fuzzy(title, artist)
        if entry:
            hit_type = "fuzzy"

    if not entry:
        print("[probe] KB-Treffer: NONE")
        return

    genres = extract_genres(entry) or []
    print(f"[probe] KB-Treffer: {hit_type}")
    print(f"[probe] entry.title = {entry.get('title')!r}")
    print(f"[probe] entry.artist= {entry.get('artist')!r}")
    if entry.get('aliases'):
        print(f"[probe] aliases    = {entry.get('aliases')}")
    if entry.get('album'):
        print(f"[probe] album      = {entry.get('album')!r}")
    if entry.get('tags'):
        print(f"[probe] tags       = {entry.get('tags')}")
    if entry.get('genres'):
        print(f"[probe] genres     = {entry.get('genres')}")
    print(f"[probe] Genres out = {', '.join(genres) if genres else '∅'}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[probe] Fehler: {e}", file=sys.stderr)
        sys.exit(1)
