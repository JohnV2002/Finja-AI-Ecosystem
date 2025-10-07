"""
======================================================================
                Finja's Brain & Knowledge Core - MDR Scraper
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (MDR Modul)

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Ruft den aktuellen Song von MDR Sachsen-Anhalt über eine robuste Hybrid-Methode ab.
  • Prüft nacheinander: ICY-Stream-Metadaten, offizielle XML-Feeds und als Fallback die HTML-Webseite.
  • Filtert automatisch Inhalte wie Werbung, Nachrichten und Jingles heraus.
  • Schreibt den erkannten Song in `nowplaying.txt` und die genutzte Quelle (icy, xml, html) in `now_source.txt`.
  • Verhindert das Flackern bei instabilen oder kurzzeitigen Titeländerungen.

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import os, re, time, datetime as dt, requests, unicodedata
from contextlib import closing
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET
from bs4.element import Tag

ROOT = os.path.dirname(os.path.abspath(__file__))
# Gehe ein Verzeichnis höher und dann in Nowplaying
NOWPLAYING_DIR = os.path.join(os.path.dirname(ROOT), "Nowplaying")
NOW_FILE = os.path.join(NOWPLAYING_DIR, "nowplaying.txt") # <-- Geändert
SRC_FILE = os.path.join(NOWPLAYING_DIR, "now_source.txt") # <-- Geändert

# --- Streams (ICY) ---
STREAM_URL = os.environ.get("MDR_STREAM_URL",
  "https://mdr-284290-1.sslcast.mdr.de/mdr/284290/1/mp3/high/stream.mp3  "
)

# --- XML-Kandidaten (Regionen/Varianten) ---
XML_BASES = [
  os.environ.get("MDR_XML_URL") or "https://www.mdr.de/XML/titellisten/mdr1_sa_2.xml  ",
  "https://www.mdr.de/XML/titellisten/mdr1_sa_0.xml  ",
  "https://www.mdr.de/XML/titellisten/mdr1_sa_1.xml  ",
  "https://www.mdr.de/XML/titellisten/mdr1_sa_3.xml  ",
]

# --- HTML-Fallback ---
HTML_URL = os.environ.get("MDR_HTML_URL",
  "https://www.mdr.de/mdr-sachsen-anhalt/titelliste-mdr-sachsen-anhalt--102.html  "
)

POLL_EVERY_SEC = int(os.environ.get("MDR_POLL_S", "10"))
TIMEOUT = 8
UA = {
  "User-Agent": "FinjaNowPlaying/1.2 (+SodaKiller)",
  "Pragma": "no-cache",
  "Cache-Control": "no-cache",
}
STALE_GRACE_SEC = 120  # 2 min Puffer

# --- ICY-Format-Hinweis: MDR sendet Title-First ---
ICY_FORMAT = os.environ.get("MDR_ICY_FORMAT", "title-first").lower()  # "title-first" | "artist-first"

# ===== Non-Track Patterns =====
NON_TRACK_PATTERNS = [
    r"\bmdr\s*sachsen[- ]anhalt\b",
    r"\bmein\s*radio\.\s*mein\s*zuhause\b",
    r"\bnachrichten\b",
    r"\bverkehr\b",
    r"\bblitzer\b",
    r"\bservice\b",
    r"\bwerbung\b",
    r"\bpromo\b",
    r"\bhinweis\b",
    r"\bmeldung\b",
    r"\bgewinnspiel\b",
    r"\bmdr\s*aktuell\b",
    # ARD-Sendestrecken & Kontaktblöcke
    r"\bard[-\s]*hitnacht\b",
    r"\bder\s*ard[-\s]*abend\b",
    r"radio\s*f(?:ü|u)r\s*alle",
    r"\btelefon\s*0*800\s*80\s*80\s*110\b",
    r"\be-?\s*mail\s*an\s*ard-?\s*abend@mdr\.de\b",
]
NON_TRACK_RE = re.compile("|".join(f"(?:{p})" for p in NON_TRACK_PATTERNS), re.IGNORECASE)

# ===== Helpers =====
def _extract_streamtitle(meta_bytes: bytes) -> str:
    """Robust 'StreamTitle' aus ICY-Metablock ziehen (escapte Quotes erlaubt)."""
    # erst decoden (utf-8, sonst latin-1)
    try:
        s = meta_bytes.decode("utf-8", "ignore")
    except Exception:
        s = meta_bytes.decode("latin-1", "ignore")

    # 1) erst mit Regex (beachtet \' bzw \")
    m = re.search(r"StreamTitle='((?:\\'|[^'])*)'", s)
    if not m:
        m = re.search(r'StreamTitle="((?:\\"|[^"])*)"', s)
    if m:
        val = m.group(1).replace("\\'", "'").replace('\\"', '"')
        return val.strip()

    # 2) Fallback: manuell bis zum *un-escapten* Quote lesen
    key = "StreamTitle="
    i = s.find(key)
    if i >= 0:
        q = s.find("'", i)
        if q < 0:
            q = s.find('"', i)
        if q >= 0:
            out, esc = [], False
            for ch in s[q+1:]:
                if esc:
                    out.append(ch); esc = False
                elif ch == "\\":
                    esc = True
                elif ch in ("'", '"'):
                    break
                else:
                    out.append(ch)
            return "".join(out).strip()

    return ""


def _norm_match(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()

def clean_field(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*", " ", s)  # (radio edit) / [live]
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def is_non_track(artist: str, title: str, raw_text: str) -> bool:
    a = _norm_match(artist)
    t = _norm_match(title)
    raw = _norm_match(raw_text)
    hay = f"{a} {t} {raw}"
    if NON_TRACK_RE.search(hay):
        return True
    if a.startswith("mdr") and (not t or len(t) <= 2):
        return True
    return False

def norm(s): return (s or "").strip()

def write_outputs(title, artist, src):
    # Kanonisch: IMMER "Title — Artist"
    line = f"{title} — {artist}".strip(" —")
    with open(NOW_FILE, "w", encoding="utf-8") as f: f.write(line + "\n")
    with open(SRC_FILE, "w", encoding="utf-8") as f: f.write((src or "none") + "\n")

# ---------- ICY ----------
def get_from_icy():
    try:
        headers = dict(UA); headers["Icy-MetaData"] = "1"
        with closing(requests.get(STREAM_URL, headers=headers, stream=True, timeout=TIMEOUT)) as r:
            r.raise_for_status()
            metaint = int(r.headers.get("icy-metaint","0"))
            if not metaint:
                return "", "", ""
            _ = next(r.iter_content(chunk_size=metaint))
            meta_len = next(r.iter_content(chunk_size=1))[0] * 16
            meta = next(r.iter_content(chunk_size=meta_len)) if meta_len else b""
            raw = _extract_streamtitle(meta)
            if not raw:
                return "", "", ""

            # Split
            sep = " - " if " - " in raw else (" — " if " — " in raw else None)
            if sep:
                left, right = [norm(p) for p in raw.split(sep, 1)]
            else:
                left, right = "", norm(raw)

            # MDR: Title-first (konfigurierbar)
            if ICY_FORMAT == "title-first":
                title, artist = left, right
            else:
                artist, title = left, right

            if is_non_track(artist, title, raw):
                return "", "", ""

            title, artist = clean_field(title), clean_field(artist)
            if title or artist:
                return artist, title, "icy"  # Rückgabe weiterhin (artist, title)
    except Exception:
        pass
    return "", "", ""

# ---------- XML ----------
def _parse_hms(hms: str) -> int|None:
    try:
        h,m,s = [int(x) for x in hms.split(":")]
        return h*3600 + m*60 + s
    except Exception:
        return None

def _is_xml_fresh(starttime: str, duration: str) -> bool:
    try:
        st = dt.datetime.strptime(starttime, "%Y-%m-%d %H:%M:%S")
        dur = _parse_hms(duration) or 0
        end = st + dt.timedelta(seconds=dur + STALE_GRACE_SEC)
        return dt.datetime.now() <= end
    except Exception:
        return False

def get_from_one_xml(url: str):
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    now = root.find(".//TAKE[@STATUS='now']")
    if now is None: return "", "", ""
    title = clean_field(norm(now.findtext("title")))
    artist = clean_field(norm(now.findtext("interpret")))
    start  = norm(now.findtext("starttime"))
    dur    = norm(now.findtext("duration"))
    if not (title or artist):
        return "", "", ""
    if not _is_xml_fresh(start, dur):
        return "", "", ""
    return artist, title, "xml"

def get_from_xml():
    for url in XML_BASES:
        try:
            a,t,s = get_from_one_xml(url)
            if a or t:
                return a,t,s
        except Exception:
            continue
    return "", "", ""

# ---------- HTML ----------
def get_from_html():
    try:
        r = requests.get(HTML_URL, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        table = soup.select_one("table, .contenttable, .table")
        if isinstance(table, Tag):
            for tr in table.select("tr"):
                if not isinstance(tr, Tag):
                    continue
                tds = [td for td in tr.select("td") if isinstance(td, Tag)]
                if len(tds) >= 3:
                    artist = clean_field(norm(tds[1].get_text()))
                    title  = clean_field(norm(tds[2].get_text()))
                    head = (artist + " " + title).lower()
                    if "interpret" in head and "titel" in head:
                        continue
                    if artist or title:
                        return artist, title, "html"

        text = soup.get_text(" ", strip=True)
        m = re.search(
            r"Titel\s*:\s*(?P<title>.+?)\s+(?:Interpret|Künstler)\s*:\s*(?P<artist>.+?)(?:$|\s{2,})",
            text
        )
        if m:
            return clean_field(norm(m.group("artist"))), clean_field(norm(m.group("title"))), "html"

    except Exception:
        pass
    return "", "", ""

# ---------- main loop ----------
SOURCE_RANK = {"icy": 2, "xml": 1, "html": 0, "none": -1}
STICKY_SAME_SONG_SEC = 25

def _key(title, artist):
    def k(x):
        x = unicodedata.normalize("NFKC", x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        return x
    return (k(title), k(artist))

def main():
    last_key = ("","")
    last_src = "none"
    sticky_until = 0.0

    while True:
        # 1) ICY first
        a, t, s = get_from_icy()
        # 2) XML wenn ICY leer
        if not (a or t):
            a, t, s = get_from_xml()
        # 3) HTML wenn beides leer
        if not (a or t):
            a, t, s = get_from_html()

        if not (a or t):
            if not os.path.exists(NOW_FILE):
                write_outputs("", "", "none")
        else:
            # Wir schreiben KANONISCH "Title — Artist"
            title, artist = clean_field(t), clean_field(a)
            key = _key(title, artist)

            # Anti-Flap: gleicher Song + schlechtere Quelle innerhalb Sticky -> skip
            if key == last_key and time.time() < sticky_until and SOURCE_RANK.get(s,0) < SOURCE_RANK.get(last_src,0):
                time.sleep(POLL_EVERY_SEC)
                continue

            if key != last_key or s != last_src:
                write_outputs(title, artist, s)
                print(f"[update] {title} — {artist}  ({s})")
                last_key = key
                last_src = s
                sticky_until = time.time() + STICKY_SAME_SONG_SEC

        time.sleep(POLL_EVERY_SEC)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass