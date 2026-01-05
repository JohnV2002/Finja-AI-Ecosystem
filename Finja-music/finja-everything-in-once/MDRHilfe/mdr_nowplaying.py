"""
======================================================================
                Finja's Brain & Knowledge Core - MDR Scraper
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0 (MDR Module)

  ✨ New in 1.1.0:
    • Complete English documentation with docstrings
    • All comments and messages translated to English
    • Copyright updated to 2026
    • Added path validation for security
    • Added extensive inline comments for better code understanding
    • Reduced cognitive complexity throughout (SonarQube S3776)
    • Fixed type hints for Pylance compatibility
    • Fixed reluctant quantifier in regex (SonarQube S6019)

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Fetches the current song from MDR Sachsen-Anhalt using a robust hybrid method.
  • Checks in order: ICY stream metadata, official XML feeds, and HTML page as fallback.
  • Automatically filters out ads, news, and jingles.
  • Writes the detected song to `nowplaying.txt` and the source (icy, xml, html) to `now_source.txt`.
  • Prevents flickering during unstable or brief title changes.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import os
import re
import time
import datetime as dt
import unicodedata
from pathlib import Path
from contextlib import closing
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from defusedxml import ElementTree as ET


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SongResult:
    """Result from a song fetch operation."""
    artist: str
    title: str
    source: str
    
    def is_empty(self) -> bool:
        """Check if result contains no song data."""
        return not (self.artist or self.title)
    
    def to_tuple(self) -> tuple[str, str, str]:
        """Convert to tuple format for backwards compatibility."""
        return (self.artist, self.title, self.source)


@dataclass
class LoopState:
    """State for the main polling loop."""
    last_key: tuple[str, str] = ("", "")
    last_src: str = "none"
    sticky_until: float = 0.0


# Empty result constant
EMPTY_RESULT = SongResult("", "", "")


# =============================================================================
# Path Configuration
# =============================================================================

# Script root directory
ROOT = Path(__file__).parent.absolute()

# Output directory - one level up, then into Nowplaying folder
NOWPLAYING_DIR = ROOT.parent / "Nowplaying"

# Output file paths
NOW_FILE = NOWPLAYING_DIR / "nowplaying.txt"
SRC_FILE = NOWPLAYING_DIR / "now_source.txt"


# =============================================================================
# Security: Path Validation
# =============================================================================

def validate_output_path(path: Path) -> Path:
    """
    Validate that output path is within allowed directories.
    
    Args:
        path: Path to validate
        
    Returns:
        Resolved absolute Path
        
    Raises:
        ValueError: If path is outside allowed directories
    """
    resolved = path.resolve()
    allowed_dirs = [Path.home(), Path.cwd(), ROOT.parent]
    
    for allowed_dir in allowed_dirs:
        try:
            resolved.relative_to(allowed_dir.resolve())
            return resolved
        except ValueError:
            continue
    
    raise ValueError(f"Output path not allowed: {resolved}")


# Validate paths at module load time
try:
    NOW_FILE = validate_output_path(NOW_FILE)
    SRC_FILE = validate_output_path(SRC_FILE)
except ValueError as e:
    print(f"[warn] Path validation failed: {e}")
    # Fall back to current directory
    NOW_FILE = Path.cwd() / "nowplaying.txt"
    SRC_FILE = Path.cwd() / "now_source.txt"


# =============================================================================
# Stream & API Configuration
# =============================================================================

# ICY Stream URL (can be overridden via environment variable)
STREAM_URL = os.environ.get(
    "MDR_STREAM_URL",
    "https://mdr-284290-1.sslcast.mdr.de/mdr/284290/1/mp3/high/stream.mp3"
).strip()

# XML feed URLs (multiple regions/variants for redundancy)
XML_BASES = [
    os.environ.get("MDR_XML_URL") or "https://www.mdr.de/XML/titellisten/mdr1_sa_2.xml",
    "https://www.mdr.de/XML/titellisten/mdr1_sa_0.xml",
    "https://www.mdr.de/XML/titellisten/mdr1_sa_1.xml",
    "https://www.mdr.de/XML/titellisten/mdr1_sa_3.xml",
]
# Strip whitespace from URLs
XML_BASES = [url.strip() for url in XML_BASES]

# HTML fallback URL
HTML_URL = os.environ.get(
    "MDR_HTML_URL",
    "https://www.mdr.de/mdr-sachsen-anhalt/titelliste-mdr-sachsen-anhalt--102.html"
).strip()


# =============================================================================
# Timing & Request Configuration
# =============================================================================

# How often to poll for updates (seconds)
POLL_EVERY_SEC = int(os.environ.get("MDR_POLL_S", "10"))

# Request timeout (seconds)
TIMEOUT = 8

# User-Agent headers for requests
UA = {
    "User-Agent": "FinjaNowPlaying/1.2 (+SodaKiller)",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

# Grace period for stale XML entries (seconds) - 2 minute buffer
STALE_GRACE_SEC = 120

# ICY format hint: MDR sends Title-First
# Options: "title-first" | "artist-first"
ICY_FORMAT = os.environ.get("MDR_ICY_FORMAT", "title-first").lower()

# Source priority ranking (higher = better)
SOURCE_RANK = {"icy": 2, "xml": 1, "html": 0, "none": -1}

# How long to "stick" with the same song before accepting lower-priority source
STICKY_SAME_SONG_SEC = 25


# =============================================================================
# Non-Track Patterns (Ads, News, Jingles, etc.)
# These patterns match content that should be filtered out
# =============================================================================

NON_TRACK_PATTERNS = [
    # Station identification
    r"\bmdr\s*sachsen[- ]anhalt\b",
    r"\bmein\s*radio\.\s*mein\s*zuhause\b",
    
    # News and traffic
    r"\bnachrichten\b",      # News
    r"\bverkehr\b",          # Traffic
    r"\bblitzer\b",          # Speed cameras
    r"\bservice\b",          # Service announcements
    
    # Advertising and promotions
    r"\bwerbung\b",          # Advertising
    r"\bpromo\b",            # Promotions
    r"\bhinweis\b",          # Notices
    r"\bmeldung\b",          # Announcements
    r"\bgewinnspiel\b",      # Contests
    r"\bmdr\s*aktuell\b",    # MDR current affairs
    
    # ARD broadcast segments and contact blocks
    r"\bard[-\s]*hitnacht\b",
    r"\bder\s*ard[-\s]*abend\b",
    r"radio\s*f(?:ü|u)r\s*alle",  # "Radio für alle" (Radio for all)
    r"\btelefon\s*0*800\s*80\s*80\s*110\b",
    r"\be-?\s*mail\s*an\s*ard-?\s*abend@mdr\.de\b",
]

# Compile all patterns into a single regex for efficient matching
NON_TRACK_RE = re.compile(
    "|".join(f"(?:{p})" for p in NON_TRACK_PATTERNS),
    re.IGNORECASE
)

# Regex for HTML text extraction (fixed reluctant quantifier S6019)
# Using greedy [^\n]+ - the character class already limits what can match
HTML_TEXT_PATTERN = re.compile(
    r"Titel\s*:\s*(?P<title>[^\n:]+)\s+(?:Interpret|Künstler)\s*:\s*(?P<artist>[^\n]+)(?:$|\s{2,})"
)


# =============================================================================
# Helper Functions: ICY Metadata Extraction
# Separated into smaller functions to reduce cognitive complexity
# =============================================================================

def _decode_meta_bytes(meta_bytes: bytes) -> str:
    """
    Decode ICY metadata bytes to string.
    
    Args:
        meta_bytes: Raw bytes from ICY metadata block
        
    Returns:
        Decoded string
    """
    try:
        return meta_bytes.decode("utf-8", "ignore")
    except Exception:
        return meta_bytes.decode("latin-1", "ignore")


def _extract_via_regex(s: str) -> str | None:
    """
    Try to extract StreamTitle using regex patterns.
    
    Args:
        s: Decoded metadata string
        
    Returns:
        Extracted title or None if not found
    """
    # Try single quotes first
    m = re.search(r"StreamTitle='((?:\\'|[^'])*)'", s)
    
    # Fall back to double quotes
    if not m:
        m = re.search(r'StreamTitle="((?:\\"|[^"])*)"', s)
    
    if m:
        val = m.group(1).replace("\\'", "'").replace('\\"', '"')
        return val.strip()
    
    return None


def _extract_via_manual_parse(s: str) -> str | None:
    """
    Manually parse StreamTitle handling escaped quotes.
    
    Args:
        s: Decoded metadata string
        
    Returns:
        Extracted title or None if not found
    """
    key = "StreamTitle="
    i = s.find(key)
    
    if i < 0:
        return None
    
    # Find opening quote
    q = s.find("'", i)
    if q < 0:
        q = s.find('"', i)
    
    if q < 0:
        return None
    
    # Parse character by character, handling escapes
    out: list[str] = []
    esc = False
    
    for ch in s[q + 1:]:
        if esc:
            out.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch in ("'", '"'):
            break
        else:
            out.append(ch)
    
    return "".join(out).strip()


def _extract_streamtitle(meta_bytes: bytes) -> str:
    """
    Extract 'StreamTitle' from ICY metadata block.
    
    Handles escaped quotes robustly. The ICY metadata format uses
    'StreamTitle' to contain the current song information.
    
    Args:
        meta_bytes: Raw bytes from ICY metadata block
        
    Returns:
        Extracted stream title string, or empty string if not found
    """
    s = _decode_meta_bytes(meta_bytes)
    
    # Try regex extraction first (most common case)
    result = _extract_via_regex(s)
    if result is not None:
        return result
    
    # Fall back to manual parsing
    result = _extract_via_manual_parse(s)
    if result is not None:
        return result
    
    return ""


# =============================================================================
# Helper Functions: Text Processing
# =============================================================================

def _norm_match(s: str) -> str:
    """
    Normalize string for comparison/matching.
    
    Converts to NFKC form, normalizes quotes and dashes,
    collapses whitespace, and lowercases.
    
    Args:
        s: Input string
        
    Returns:
        Normalized lowercase string
    """
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("'", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def clean_field(s: str) -> str:
    """
    Clean a title/artist field for display.
    
    Removes parenthetical content like "(radio edit)" or "[live]",
    normalizes quotes and dashes, and collapses whitespace.
    
    Args:
        s: Input string
        
    Returns:
        Cleaned string
    """
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("'", "'").replace("–", "-").replace("—", "-")
    # Remove parenthetical content: (radio edit), [live], etc.
    s = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def is_non_track(artist: str, title: str, raw_text: str) -> bool:
    """
    Check if content is a non-track (ad, news, jingle, etc.).
    
    Args:
        artist: Artist name
        title: Track title
        raw_text: Raw text from source
        
    Returns:
        True if this is non-track content that should be filtered
    """
    a = _norm_match(artist)
    t = _norm_match(title)
    raw = _norm_match(raw_text)
    hay = f"{a} {t} {raw}"
    
    # Check against non-track patterns
    if NON_TRACK_RE.search(hay):
        return True
    
    # MDR branding with no real title
    if a.startswith("mdr") and (not t or len(t) <= 2):
        return True
    
    return False


def norm(s: str | None) -> str:
    """
    Strip whitespace from string, handling None.
    
    Args:
        s: Input string or None
        
    Returns:
        Stripped string, or empty string if None
    """
    return (s or "").strip()


def _detect_separator(raw: str) -> str | None:
    """
    Detect the separator used in a raw title string.
    
    Args:
        raw: Raw title string
        
    Returns:
        Separator string or None if not found
    """
    if " - " in raw:
        return " - "
    if " — " in raw:
        return " — "
    return None


def _key(title: str, artist: str) -> tuple[str, str]:
    """
    Create a normalized key for song comparison.
    
    Args:
        title: Song title
        artist: Artist name
        
    Returns:
        Tuple of (normalized_title, normalized_artist)
    """
    def k(x: str) -> str:
        x = unicodedata.normalize("NFKC", x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        return x
    return (k(title), k(artist))


def write_outputs(title: str, artist: str, src: str) -> None:
    """
    Write current song to output files.
    
    Writes in canonical format: "Title — Artist"
    
    Args:
        title: Song title
        artist: Artist name
        src: Source identifier (icy, xml, html, none)
        
    Security Note:
        Output paths are validated at module load time.
    """
    # Canonical format: "Title — Artist"
    line = f"{title} — {artist}".strip(" —")
    
    # Ensure output directory exists
    NOW_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Write nowplaying file
    # Security: Path is pre-validated at module load
    with open(NOW_FILE, "w", encoding="utf-8") as f:  # nosec B108
        f.write(line + "\n")
    
    # Write source file
    with open(SRC_FILE, "w", encoding="utf-8") as f:  # nosec B108
        f.write((src or "none") + "\n")


# =============================================================================
# ICY Stream Metadata Fetcher
# =============================================================================

def get_from_icy() -> SongResult:
    """
    Fetch current song from ICY stream metadata.
    
    ICY (Icecast) streams embed metadata at regular intervals.
    This function reads just enough of the stream to extract
    the current song information.
    
    Returns:
        SongResult with artist, title, source or empty result if not found
    """
    try:
        headers = dict(UA)
        headers["Icy-MetaData"] = "1"  # Request ICY metadata
        
        with closing(requests.get(STREAM_URL, headers=headers, stream=True, timeout=TIMEOUT)) as r:
            r.raise_for_status()
            
            # Get metadata interval from headers
            metaint = int(r.headers.get("icy-metaint", "0"))
            if not metaint:
                return EMPTY_RESULT
            
            # Skip audio data to reach metadata block
            _ = next(r.iter_content(chunk_size=metaint))
            
            # Read metadata length byte (multiply by 16 for actual length)
            meta_len = next(r.iter_content(chunk_size=1))[0] * 16
            
            # Read metadata block
            meta = next(r.iter_content(chunk_size=meta_len)) if meta_len else b""
            
            # Extract stream title
            raw = _extract_streamtitle(meta)
            if not raw:
                return EMPTY_RESULT

            # Detect and split on separator
            sep = _detect_separator(raw)
            if sep:
                left, right = [norm(p) for p in raw.split(sep, 1)]
            else:
                left, right = "", norm(raw)

            # MDR uses Title-first format (configurable)
            if ICY_FORMAT == "title-first":
                title, artist = left, right
            else:
                artist, title = left, right

            # Filter non-track content
            if is_non_track(artist, title, raw):
                return EMPTY_RESULT

            title, artist = clean_field(title), clean_field(artist)
            if title or artist:
                return SongResult(artist, title, "icy")
                
    except Exception:
        pass
    
    return EMPTY_RESULT


# =============================================================================
# XML Feed Fetcher
# =============================================================================

def _parse_hms(hms: str) -> int | None:
    """
    Parse HH:MM:SS time string to seconds.
    
    Args:
        hms: Time string in HH:MM:SS format
        
    Returns:
        Total seconds, or None if parsing fails
    """
    try:
        h, m, s = [int(x) for x in hms.split(":")]
        return h * 3600 + m * 60 + s
    except Exception:
        return None


def _is_xml_fresh(starttime: str, duration: str) -> bool:
    """
    Check if an XML entry is still current (not stale).
    
    Args:
        starttime: Start time in "YYYY-MM-DD HH:MM:SS" format
        duration: Duration in "HH:MM:SS" format
        
    Returns:
        True if entry is still within valid time window
    """
    try:
        st = dt.datetime.strptime(starttime, "%Y-%m-%d %H:%M:%S")
        dur = _parse_hms(duration) or 0
        end = st + dt.timedelta(seconds=dur + STALE_GRACE_SEC)
        return dt.datetime.now() <= end
    except Exception:
        return False


def get_from_one_xml(url: str) -> SongResult:
    """
    Fetch current song from a single XML feed URL.
    
    Args:
        url: XML feed URL
        
    Returns:
        SongResult with artist, title, source or empty result if not found
    """
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    
    # Parse XML using defusedxml for security
    root = ET.fromstring(r.content)
    
    # Find the currently playing track
    now = root.find(".//TAKE[@STATUS='now']")
    if now is None:
        return EMPTY_RESULT
    
    # Extract fields (norm() now handles None properly)
    title = clean_field(norm(now.findtext("title")))
    artist = clean_field(norm(now.findtext("interpret")))
    start = norm(now.findtext("starttime"))
    dur = norm(now.findtext("duration"))
    
    if not (title or artist):
        return EMPTY_RESULT
    
    # Check if entry is still fresh
    if not _is_xml_fresh(start, dur):
        return EMPTY_RESULT
    
    return SongResult(artist, title, "xml")


def get_from_xml() -> SongResult:
    """
    Try all XML feed URLs and return first successful result.
    
    Returns:
        SongResult with artist, title, source or empty result if all fail
    """
    for url in XML_BASES:
        try:
            result = get_from_one_xml(url)
            if not result.is_empty():
                return result
        except Exception:
            continue
    
    return EMPTY_RESULT


# =============================================================================
# HTML Page Scraper (Fallback)
# Split into helper functions to reduce cognitive complexity
# =============================================================================

def _is_header_row(artist: str, title: str) -> bool:
    """
    Check if a table row is a header row (not actual data).
    
    Args:
        artist: Artist cell text
        title: Title cell text
        
    Returns:
        True if this appears to be a header row
    """
    head = (artist + " " + title).lower()
    return "interpret" in head and "titel" in head


def _extract_from_table(soup: BeautifulSoup) -> SongResult:
    """
    Try to extract song from HTML table structure.
    
    Args:
        soup: Parsed BeautifulSoup object
        
    Returns:
        SongResult or EMPTY_RESULT if not found
    """
    table = soup.select_one("table, .contenttable, .table")
    
    if not isinstance(table, Tag):
        return EMPTY_RESULT
    
    for tr in table.select("tr"):
        if not isinstance(tr, Tag):
            continue
            
        tds = [td for td in tr.select("td") if isinstance(td, Tag)]
        
        if len(tds) < 3:
            continue
            
        artist = clean_field(norm(tds[1].get_text()))
        title = clean_field(norm(tds[2].get_text()))
        
        # Skip header rows
        if _is_header_row(artist, title):
            continue
            
        if artist or title:
            return SongResult(artist, title, "html")
    
    return EMPTY_RESULT


def _extract_from_text(soup: BeautifulSoup) -> SongResult:
    """
    Try to extract song using regex on page text.
    
    Args:
        soup: Parsed BeautifulSoup object
        
    Returns:
        SongResult or EMPTY_RESULT if not found
    """
    text = soup.get_text(" ", strip=True)
    m = HTML_TEXT_PATTERN.search(text)
    
    if m:
        return SongResult(
            clean_field(norm(m.group("artist"))),
            clean_field(norm(m.group("title"))),
            "html"
        )
    
    return EMPTY_RESULT


def get_from_html() -> SongResult:
    """
    Fetch current song from HTML page as last resort fallback.
    
    Attempts to parse the MDR playlist page in multiple ways:
    1. Table rows with artist/title columns
    2. Regex pattern matching in page text
    
    Returns:
        SongResult with artist, title, source or empty result if not found
    """
    try:
        r = requests.get(HTML_URL, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Method 1: Try to find table with track listings
        result = _extract_from_table(soup)
        if not result.is_empty():
            return result

        # Method 2: Regex pattern in page text
        return _extract_from_text(soup)

    except Exception:
        pass
    
    return EMPTY_RESULT


# =============================================================================
# Main Loop - Split into helper functions
# =============================================================================

def _fetch_song() -> SongResult:
    """
    Fetch song from all sources in priority order.
    
    Returns:
        SongResult from first successful source
    """
    # 1) Try ICY stream first (fastest, most accurate)
    result = get_from_icy()
    if not result.is_empty():
        return result
    
    # 2) Try XML feeds
    result = get_from_xml()
    if not result.is_empty():
        return result
    
    # 3) Try HTML as last resort
    return get_from_html()


def _should_skip_update(result: SongResult, key: tuple[str, str], state: LoopState) -> bool:
    """
    Check if we should skip this update (anti-flap logic).
    
    Args:
        result: Current song result
        key: Normalized key for current song
        state: Current loop state
        
    Returns:
        True if we should skip this update
    """
    is_same_song = key == state.last_key
    is_within_sticky = time.time() < state.sticky_until
    is_worse_source = SOURCE_RANK.get(result.source, 0) < SOURCE_RANK.get(state.last_src, 0)
    
    return is_same_song and is_within_sticky and is_worse_source


def _process_song(result: SongResult, state: LoopState) -> None:
    """
    Process a song result and update state/outputs if needed.
    
    Args:
        result: Current song result
        state: Current loop state (will be modified)
    """
    title, artist = clean_field(result.title), clean_field(result.artist)
    key = _key(title, artist)
    
    # Anti-flap logic
    if _should_skip_update(result, key, state):
        return
    
    # Check if song or source changed
    if key != state.last_key or result.source != state.last_src:
        write_outputs(title, artist, result.source)
        print(f"[update] {title} — {artist}  ({result.source})", flush=True)
        state.last_key = key
        state.last_src = result.source
        state.sticky_until = time.time() + STICKY_SAME_SONG_SEC


def main() -> None:
    """
    Main polling loop.
    
    Continuously polls all sources (ICY, XML, HTML) and writes
    the current song to output files. Implements anti-flap logic
    to prevent flickering when sources disagree briefly.
    """
    state = LoopState()

    print("[mdr] Starting MDR NowPlaying scraper...", flush=True)
    print(f"[mdr] Output: {NOW_FILE}", flush=True)
    print(f"[mdr] Polling every {POLL_EVERY_SEC}s", flush=True)

    while True:
        result = _fetch_song()

        if result.is_empty():
            # No song found - create empty file if it doesn't exist
            if not NOW_FILE.exists():
                write_outputs("", "", "none")
        else:
            _process_song(result, state)

        time.sleep(POLL_EVERY_SEC)


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[mdr] bye 👋❤", flush=True)