"""
YourAI Text Parser Helpers
=========================
Shared parsing helpers for JSON, search queries, and domain-specific extraction.

Main Responsibilities:
- Extract JSON objects from model output.
- Build focused web-search queries.
- Parse titles, artists, and current-track requests.

Side Effects:
- Returns normalized strings for downstream tools.
"""
import json
import re
import sys, os
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception, Fore, log
from exceptions import YourAIUnexpectedError

_TEMP_UPLOAD_FILENAME_RE = re.compile(r"^[a-f0-9\-]{36}\.(jpg|png|gif|webp)$")
_DASHBOARD_THINKING_PATTERNS = [
    re.compile(
        r'<(think|thinking|thought|thoughts|scratchpad|reasoning|analysis|internal|reflection)>(.*?)</\1>',
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r'<i>(.*?)</i>', re.DOTALL | re.IGNORECASE),
]
_TWITCH_PRIVMSG_RE = re.compile(r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.*)")
_DISCORD_CUSTOM_EMOJI_RE = re.compile(r'<a?:(\w+):(\d+)>')
_DISCORD_COLON_EMOJI_RE = re.compile(r':(\w+):')
_DISCORD_EMOJI_ID_RE = re.compile(r':(\d+)>')
_TENOR_RE = re.compile(r'https?://tenor\.com/view/([\w-]+?)(?:-\d+)?$', re.IGNORECASE)
_GIPHY_RE = re.compile(
    r'https?://(?:media\.)?giphy\.com/media/\w+/giphy|https?://giphy\.com/gifs/([\w-]+?)(?:-\w+)?$',
    re.IGNORECASE,
)


def is_temp_upload_filename(filename: str) -> bool:
    """Return True for YourAI temp image upload filenames."""
    if not isinstance(filename, str):
        return False
    return bool(_TEMP_UPLOAD_FILENAME_RE.match(filename))


def extract_dashboard_thinking(raw_output: str) -> tuple[str, str]:
    """Split dashboard-visible LLM output into thinking text and clean content."""
    if not raw_output:
        return "", ""

    thinking_parts = []
    clean = raw_output

    for pattern in _DASHBOARD_THINKING_PATTERNS:
        matches = pattern.findall(raw_output)
        for match in matches:
            value = match[-1] if isinstance(match, tuple) else match
            value = value.strip()
            if value and (pattern.pattern.startswith("<i>") and len(value.split()) <= 10):
                continue
            if value:
                thinking_parts.append(value)

    for pattern in _DASHBOARD_THINKING_PATTERNS:
        clean = pattern.sub("", clean)

    return "\n---\n".join(thinking_parts) if thinking_parts else "", clean.strip()


def parse_twitch_privmsg(response: str) -> Optional[tuple[str, str]]:
    """Parse a Twitch IRC PRIVMSG line into (user, message)."""
    if not isinstance(response, str):
        return None
    match = _TWITCH_PRIVMSG_RE.search(response)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def resolve_discord_custom_emojis(text: str, emoji_descriptions: dict) -> str:
    """Convert Discord custom emoji markup into readable :name: text."""
    if not isinstance(text, str):
        return ""

    def _replace(match):
        """Handle replace helper behavior."""
        name = match.group(1)
        desc = emoji_descriptions.get(name) if emoji_descriptions else None
        if desc:
            return f":{name}: ({desc})"
        return f":{name}:"

    return _DISCORD_CUSTOM_EMOJI_RE.sub(_replace, text)


def replace_discord_colon_emojis(text: str, emoji_formats: dict) -> str:
    """Replace :emoji_name: tokens with cached Discord emoji markup."""
    if not isinstance(text, str) or not emoji_formats:
        return text

    def _replace(match):
        """Handle replace helper behavior."""
        name = match.group(1)
        return emoji_formats.get(name, match.group(0))

    return _DISCORD_COLON_EMOJI_RE.sub(_replace, text)


def extract_discord_gif_keywords(url: str) -> str:
    """Extract readable keywords from known Discord GIF provider URLs."""
    if not isinstance(url, str) or not url:
        return ""
    for pattern in (_TENOR_RE, _GIPHY_RE):
        match = pattern.search(url)
        if match and match.group(1):
            return match.group(1).replace("-", " ")
    return ""


def extract_discord_emoji_id(discord_format: str) -> str:
    """Extract numeric emoji id from <:name:id> or <a:name:id> format."""
    if not isinstance(discord_format, str):
        return ""
    match = _DISCORD_EMOJI_ID_RE.search(discord_format)
    return match.group(1) if match else ""


def extract_thoughts(text: str) -> Tuple[str, str]:
    """
    Extract thinking tags from LLM responses.
    
    Supported Tags: <think>, <thinking>, <thought>, <scratchpad>
    
    Args:
        text: Raw LLM response
        
    Returns:
        Tuple of (thoughts, clean_text).
    """
    if not isinstance(text, str):
        return "", str(text)
        
    try:
        thoughts = ""
        clean_text = text
        
        # Pattern: <think>...</think> etc.
        pattern = re.compile(
            r'<(think|thinking|thought|scratchpad)>(.*?)</\1>', 
            re.DOTALL | re.IGNORECASE
        )
        match = pattern.search(text)
        if match:
            thoughts = match.group(2).strip()
            clean_text = pattern.sub('', text).strip()
            return thoughts, clean_text
        
        # Fallback: treat text before JSON as thoughts.
        json_indicators = [r"```json", r"\{"]
        first_match_pos = len(text)
        found_json = False
        
        for indicator in json_indicators:
            match = re.search(indicator, text)
            if match and match.start() < first_match_pos:
                first_match_pos = match.start()
                found_json = True
        
        if found_json and first_match_pos > 10:
            thoughts = text[:first_match_pos].strip()
            clean_text = text[first_match_pos:].strip()

        return thoughts, clean_text
        
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="text_parser_thoughts")
        log_exception("PARSER", err)
        # Fail-safe: return the original text.
        return "", text


def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Extract JSON from text using multiple strategies.
    
    1. Direct JSON parsing.
    2. ```json ... ``` blocks.
    3. First { through last }.
    
    Args:
        text: Text that may contain JSON.
        
    Returns:
        Parsed dict or None.
    """
    if not isinstance(text, str):
        return None
        
    try:
        # Strategy 1: direct parsing.
        try: 
            return json.loads(text)
        except (json.JSONDecodeError, TypeError): 
            pass
        
        # Strategy 2: Markdown JSON block.
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try: 
                return json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError): 
                pass
        
        # Strategy 3: last valid JSON object for thinking models.
        # Work backward to find the last complete {...} object in the output.
        try:
            search_end = len(text)
            while search_end > 0:
                end = text.rfind("}", 0, search_end)
                if end == -1:
                    break
                start = text.rfind("{", 0, end + 1)
                if start == -1:
                    break
                try:
                    result = json.loads(text[start:end + 1])
                    if isinstance(result, dict):
                        return result
                except (json.JSONDecodeError, TypeError):
                    pass
                search_end = end  # Try the next } further left.
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="text_parser_json_reverse_scan")
            log_exception("PARSER", err)

        # Strategy 4: first { through last } as final fallback.
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, TypeError):
            pass

        # If every strategy fails, return None as expected by callers.
        return None
        
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="text_parser_json")
        log_exception("PARSER", err)
        return None


# ==========================================
# SEARCH QUERY EXTRACTION
# ==========================================
# Convert messy user messages into focused search terms.
# Used by expert modules, such as Anime, for mandatory web search.
# ==========================================

# Conversational filler, language-agnostic.
_FILLER_PATTERNS = [
    # DE + EN Chat-Filler (WORD BOUNDARIES to avoid eating letters inside words!)
    r'\b(?:okay+|okey|hey|hmm+|ehm+|ähm+|hm+|well|also|naja|halt|dann?|jetzt|next)\b',
    # Standalone short words (only match as whole words, NOT inside other words)
    r'(?<!\w)(?:hi|so)(?!\w)',
    # Retry / Test / Next phrases
    r'\b(?:lets?\s+try\s+again|try\s+again|noch\s*mal|nächster?\s+test|next\s+test|anime\s+test|test\s*\d*)\b',
    # Emoticons & Discord-style (these are safe without \b)
    r'(?::\w+:|[;:][3D\)P]|XD+|lol+|haha+|hehe+|:3+)',
    # Ellipsis & repeated punctuation
    r'(?:\.{2,}|!{2,}|\?{2,})',
    # --- Additional filler ---
    # Politeness phrases.
    r'\b(?:please|bitte)\b',
    # Internet-Slang
    r'\b(?:lmao|rofl|lmfao|omg|bruh|btw|tbh|ngl|afaik|imo|imho)\b',
    # Agreement / rejection.
    r'\b(?:yeah|yep|yup|nope|nah|mhm|ugh|pls)\b',
    # German filler words that often start sentences.
    r'\b(?:warte|schau\s+mal|mal\s+kurz|eigentlich|irgendwie|grad|gerade|kurz)\b',
    # Hedges / uncertainty.
    r'\b(?:I\s+think|I\s+guess|I\s+mean|you\s+know|ich\s+glaube|ich\s+meine|ich\s+denke)\b',
    # Numbered attempts at sentence start, e.g. "1." / "#3".
    r'(?:^|\s)(?:\d+\s*[.):]|#\d+)\s*',
]

# "I'm searching for..." prefixes
_SEARCH_PREFIX_PATTERNS = [
    # EN
    r"i(?:'?m| am)\s+(?:searching|looking)\s+(?:about|for)\s+(?:an?\s+)?",
    r"(?:can|could)\s+you\s+(?:find|search|look\s+(?:for|up))\s+",
    r"(?:do\s+you\s+know|what(?:'s| is))\s+(?:an?\s+)?",
    r"(?:tell|show)\s+me\s+(?:about\s+)?(?:an?\s+)?",
    # DE
    r"(?:ich\s+such[e]?\s*(?:mal\s*)?(?:nach\s+)?(?:eine[mn]?\s+)?)",
    r"(?:kennt?\s+(?:ihr|du|jemand)\s+(?:eine[mn]?\s+)?)",
    r"(?:weißt\s+du\s+(?:was\s+)?(?:eine?[mn]?\s+)?)",
    r"(?:was\s+(?:ist|war)\s+(?:das?\s+)?(?:eine?[mn]?\s+)?)",
    # --- Additional prefixes ---
    # EN: "have you heard of", "I want to know about", "give me info on"
    r"(?:have\s+you\s+(?:ever\s+)?heard\s+(?:of|about))\s+(?:an?\s+|the\s+)?",
    r"(?:I\s+(?:want|need)\s+to\s+(?:know|find\s+out)\s+(?:about\s+)?(?:an?\s+)?)",
    r"(?:give\s+me\s+(?:info|information)\s+(?:on|about)\s+(?:an?\s+)?)",
    r"(?:(?:search|find|look\s+up)\s+(?:for\s+)?(?:an?\s+|the\s+)?)",
    # DE prefixes such as "kennst du ein", "hast du schon von X gehört", "zeig mir".
    r"(?:kennst\s+du\s+(?:ein(?:en|em|es)?\s+)?)",
    r"(?:hast\s+du\s+(?:schon\s+)?(?:mal\s+)?(?:von|über)\s+)",
    r"(?:zeig\s+mir\s+(?:mal\s+)?(?:ein(?:en|em|es)?\s+)?)",
    r"(?:erkläre?\s+mir\s+(?:mal\s+)?(?:was\s+)?(?:ein(?:en|em|es)?\s+)?)",
]


def extract_search_query(text: str, prefix: str = "") -> str:
    """
    Extract a focused search query from a messy user message.

    Remove chat filler, emoticons, search prefixes, and
    normalize whitespace. Optionally prepend a domain prefix.

    Args:
        text: Raw user message.
        prefix: Domain prefix, e.g. "anime".

    Returns:
        Cleaned search query.

    Examples:
        >>> extract_search_query("okay lets try again :3 Im searching about an funny anime with deer horns", "anime")
        'anime funny anime with deer horns'
        >>> extract_search_query("kennst du ein anime mit einem mädchen das renntiergeweih hat?", "anime")
        'anime anime mit einem mädchen das renntiergeweih hat?'
    """
    if not text or not isinstance(text, str):
        return prefix.strip() if prefix else ""

    clean = text

    # Step 1: Remove filler patterns (case-insensitive, word boundaries)
    for pattern in _FILLER_PATTERNS:
        clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)

    # Step 2: Strip leading punctuation/colons left by filler removal
    clean = re.sub(r'^[\s:;,\-–—]+', '', clean).strip()

    # Step 3: Remove "Im searching for..." prefixes (anchored to start after cleanup)
    for pattern in _SEARCH_PREFIX_PATTERNS:
        clean = re.sub(r'^\s*' + pattern, '', clean, flags=re.IGNORECASE)

    # Step 3.5: Strip leading punctuation again because prefix removal can leave colons.
    # Example: "ich suche: X" -> prefix strip -> ": X" -> "X".
    clean = re.sub(r'^[\s:;,\-–—]+', '', clean).strip()

    # Step 4: Collapse whitespace, trim
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Step 5: If cleanup ate everything, fall back to original
    if len(clean) < 5:
        clean = re.sub(r'\s+', ' ', text).strip()

    # Step 6: Limit length for search engines
    clean = clean[:150]

    # Step 7: Prefix
    if prefix:
        return f"{prefix} {clean}"
    return clean


# ==========================================
# SPOTIFY COMMAND PARSING
# ==========================================

def extract_spotify_volume(text: str) -> str | None:
    """Return the first volume number from a Spotify command."""
    if not text:
        return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None


def extract_spotify_playlist_name(text: str) -> str | None:
    """Extract a playlist name from a natural language Spotify command."""
    if not text:
        return None

    patterns = [
        r'playlist\s+["\']?([^"\']+?)["\']?\s*(?:nach|by|filter|nur|$)',
        r'playlist\s+["\']?(.+?)["\']?$',
        r'meine\s+["\']?([^"\']+?)["\']?\s*(?:nach|by|filter|nur|shuffle|$)',
        r'spiel(?:e)?\s+["\']?(.+?)["\']?\s*(?:nach|by|ab|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            for word in [
                "shuffle",
                "shuffel",
                "sort",
                "sortiere",
                "nach bpm",
                "nach energy",
                "nur von",
                "filter",
                "only",
                "by bpm",
                "langsam",
                "schnell",
            ]:
                name = name.replace(word, "").strip()
            if name:
                return name

    for keyword in ["shuffle", "shuffel", "mischen", "sortiere", "sort", "spiel", "play"]:
        if keyword in text:
            rest = text.split(keyword, 1)[1].strip()
            for prefix in ["meine", "my", "playlist", "die"]:
                if rest.lower().startswith(prefix):
                    rest = rest[len(prefix):].strip()
            for suffix in [
                "nach bpm",
                "by bpm",
                "nach energy",
                "by energy",
                "langsam",
                "schnell",
                "chill",
                "hype",
                "nur von",
                "filter",
                "only by",
            ]:
                if suffix in rest.lower():
                    rest = rest[:rest.lower().find(suffix)].strip()
            if rest:
                return rest

    return None


def extract_spotify_artist_filter(text: str) -> str | None:
    """Extract an artist filter from a natural language Spotify command."""
    if not text:
        return None

    patterns = [
        r'nur\s+(?:von\s+)?["\']?(.+?)["\']?$',
        r'only\s+(?:songs?\s+)?(?:by\s+)?["\']?(.+?)["\']?$',
        r'filter\s+(?:artist\s+)?["\']?(.+?)["\']?$',
        r'von\s+["\']?(.+?)["\']?$',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


# ==========================================
# EXPERT SEARCH COMMAND EXTRACTION
# ==========================================
# Expert LLMs (Nutrition, Mechanic, History, Law) emit [SEARCH: ...] commands.
# This function extracts the query string.
# ==========================================

def extract_expert_search_command(text: str) -> Optional[str]:
    """
    Extract [SEARCH: ...] or [WEB: ...] commands from expert LLM outputs.

    Nutrition, Mechanic, History, and Law experts all use the same format:
      [SEARCH: <query>]

    Returns:
        Search query string, or None when no command was found.
    """
    if not text:
        return None
    match = re.search(r"\[(?:SEARCH|WEB)\s*:\s*([^\]]{3,220})\]", text, flags=re.IGNORECASE)
    if not match:
        return None
    query = re.sub(r"\s+", " ", match.group(1)).strip()
    return query or None


# ==========================================
# EXPERT SEARCH QUERY BUILDERS
# ==========================================
# Build focused web-search queries for different expert domains.
# Used by brain.py expert_node when a [SEARCH: ...] command appears.
# ==========================================

def build_writing_search_query(text: str) -> str:
    """Build a focused search query for book and author lookups."""
    raw = (text or "").strip()

    quoted = re.findall(r'"([^"]{3,80})"|\'([^\']{3,80})\'', raw)
    quoted_terms = [a or b for a, b in quoted]
    if quoted_terms:
        return " ".join(f'"{term.strip()}"' for term in quoted_terms[:3]) + " author book"

    clean = raw
    clean = re.sub(r"(?is)^.*?\b(?:expert should trigger|new test|try again|lets try|let's try)\b\s*:?", " ", clean)
    clean = re.sub(r"(?i)\b(?:what book is|which book is|welches buch ist|wer schrieb|who wrote it|who wrote|what do they do|worum gehts|worum geht es|um wen gehts|um wen geht es)\b", " ", clean)
    clean = re.sub(r"[:?;!]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" -")

    dash_parts = [part.strip(" -") for part in re.split(r"\s+-\s+", clean) if part.strip(" -")]
    if len(dash_parts) >= 2:
        return " ".join(f'"{part[:80]}"' for part in dash_parts[:2]) + " author book"

    titleish = re.findall(
        r"\b[A-ZÄÖÜ][\wÄÖÜäöüß']+(?:\s+(?:of|the|der|die|das|des|den|dem|von|vom|im|in|ohne|mit|und|[A-ZÄÖÜ][\wÄÖÜäöüß']+)){1,8}",
        clean,
    )
    if titleish:
        seen_titles: list = []
        for item in sorted(titleish, key=len, reverse=True):
            item = item.strip(" -")
            if item and not any(
                item.lower() in existing.lower() or existing.lower() in item.lower()
                for existing in seen_titles
            ):
                seen_titles.append(item)
            if len(seen_titles) >= 2:
                break
        return " ".join(f'"{title}"' for title in seen_titles) + " author book"

    return f"{clean[:120]} author book" if clean else "book author"


def build_nutrition_search_query(text: str) -> str:
    """Build a focused search query for nutrition and barcode lookups."""
    raw = (text or "").strip()
    barcode = re.search(r"\b\d{8,14}\b", raw)
    if barcode:
        return f"{barcode.group(0)} nutrition ingredients calories"
    clean = re.sub(
        r"(?i)\b(?:nutrions?|nutrition facts?|nährwerte|naehrwerte|kalorien|calories|inhaltstoffe|ingredients|was sind|what are|von|of|bitte|please|:3|hehe)\b",
        " ", raw,
    )
    clean = re.sub(r"\s+", " ", clean).strip(" ?:;-")
    return f"{clean[:120]} nutrition ingredients calories" if clean else "nutrition ingredients calories"


def build_mechanic_search_query(text: str) -> str:
    """Build a focused search query for mechanic and OBD-code lookups."""
    raw = (text or "").strip()
    obd = re.search(r"\bP[0-9A-F]{4}\b", raw, flags=re.IGNORECASE)
    clean = re.sub(
        r"(?i)\b(?:mechanic|auto|car|vehicle|fahrzeug|reparatur|repair|symptom|problem|was bedeutet|what means|bitte|please|:3|hehe)\b",
        " ", raw,
    )
    clean = re.sub(r"\s+", " ", clean).strip(" ?:;-")
    if obd and clean:
        return f"{clean[:120]} {obd.group(0).upper()} mechanic symptoms repair manual"
    return f"{clean[:140]} mechanic symptoms repair manual" if clean else "mechanic symptoms repair manual"


def build_history_search_query(text: str) -> str:
    """Build a focused search query for history/source lookups."""
    raw = (text or "").strip()
    quoted = re.findall(r'"([^"]{3,100})"|\'([^\']{3,100})\'', raw)
    quoted_terms = [a or b for a, b in quoted]
    if quoted_terms:
        return " ".join(f'"{term.strip()}"' for term in quoted_terms[:3]) + " history sources timeline"

    clean = re.sub(
        r"(?i)\b(?:history|historisch|historical|was passierte|what happened|wer war|who was|wann|when|warum|why|timeline|ursachen|causes|quellen|sources|bitte|please|:3|hehe)\b",
        " ", raw,
    )
    clean = re.sub(r"\s+", " ", clean).strip(" ?:;-")
    return f"{clean[:140]} history sources timeline" if clean else "history sources timeline"


def build_law_search_query(text: str) -> str:
    """Build a focused search query for legal/source lookups."""
    raw = (text or "").strip()
    raw_l = raw.lower()
    section = re.search(r"(?:§\s*\d+[a-zA-Z]?|Art\.?\s*\d+[a-zA-Z]?)", raw, flags=re.IGNORECASE)
    quoted = re.findall(r'"([^"]{3,100})"|\'([^\']{3,100})\'', raw)
    quoted_terms = [a or b for a, b in quoted]
    site_hint = ""
    if any(term in raw_l for term in ["sachsen-anhalt", "lsa", "landesrecht"]):
        site_hint = " site:landesrecht.sachsen-anhalt.de"
    elif any(term in raw_l for term in ["urteil", "beschluss", "gericht", "rechtsprechung", "aktenzeichen", "fall", "fälle", "faelle", "case law", "court decision"]):
        site_hint = " site:openjur.de"

    if section:
        return f"{section.group(0)} {raw[:100]} official law source{site_hint}"
    if quoted_terms:
        return " ".join(f'"{term.strip()}"' for term in quoted_terms[:3]) + f" official law source{site_hint}"

    clean = re.sub(
        r"(?i)\b(?:law|legal|recht|gesetz|paragraph|paragraf|artikel|article|juristisch|recherchiere|research|was steht|what says|bedeutet|means|bitte|please|:3|hehe)\b",
        " ", raw,
    )
    clean = re.sub(r"\s+", " ", clean).strip(" ?:;-")
    return f"{clean[:140]} official law source{site_hint}" if clean else f"official law source{site_hint}".strip()


# ==========================================
# JSON / EXPERT RESPONSE COMPACT
# ==========================================

def compact_json_response(text: str) -> str:
    """
    Extract the JSON object from expert LLM output.

    Remove reasoning tags (<think>, etc.) and return only JSON.
    If no JSON is found, return cleaned text.
    """
    parsed = extract_json_from_text(text)
    if parsed is not None:
        return json.dumps(parsed, ensure_ascii=False)
    _, clean = extract_thoughts(text)
    return clean.strip() if clean.strip() else text.strip()


# ==========================================
# MUSIC QUERY HELPERS
# ==========================================

def extract_music_title_artist(question: str) -> tuple:
    """
    Extract song title and artist from a user request.
    Best effort for requests such as 'Rockstar - Ado' or '"Song" by Artist'.

    Returns:
        Tuple (title, artist), or (None, None) when not recognized.
    """
    raw = (question or "").strip()
    quoted = re.findall(r'"([^"]{2,120})"|\'([^\']{2,120})\'', raw)
    terms = [a or b for a, b in quoted]
    candidates = terms or [raw]

    for candidate in candidates:
        text = re.sub(
            r"(?i)\b(?:song|track|lied|musik|music|analysiere|analyze|was ist|what is|wer ist|who is|bpm|key|genre|release|by|von|bitte|please|:3|hehe)\b",
            " ", candidate,
        )
        text = re.sub(r"\s+", " ", text).strip(" ?:;")
        parts = [p.strip(" -") for p in re.split(r"\s+[-–—]\s+", text) if p.strip(" -")]
        if len(parts) >= 2:
            return parts[0][:120], parts[1][:120]
        m = re.search(r"(?i)\b(.{2,120}?)\s+(?:by|von)\s+(.{2,80})\b", text)
        if m:
            return m.group(1).strip(" -"), m.group(2).strip(" -")
    return None, None


def music_asks_current_track(question: str) -> bool:
    """
    Return True when the user explicitly asks about the currently playing song.
    Prevent unnecessary Spotify data injection into the expert prompt.
    """
    q = (question or "").lower()
    patterns = [
        r"\b(this|that|current|currently playing)\s+(song|track|music)\b",
        r"\bwhat'?s?\s+(playing|this song|that song)\b",
        r"\bwas\s+l[äa]uft\s+(gerade|da)\b",
        r"\bwelcher\s+(song|track)\s+l[äa]uft\b",
        r"\b(dieser|der)\s+(song|track|lied)\b",
        r"\bwas\s+ist\s+das\s+f[üu]r\s+(ein\s+)?(song|lied|track)\b",
    ]
    return any(re.search(p, q, flags=re.IGNORECASE) for p in patterns)


def build_music_search_query(question: str, music_data: dict, spotify_data: dict) -> str:
    """
    Build a focused search query for music facts when local sources are empty.

    Args:
        question:     User question.
        music_data:   Music Brain metadata, may be empty.
        spotify_data: Spotify API metadata, may be empty.

    Returns:
        Focused web-search query.
    """
    source = music_data or spotify_data or {}
    title = (source.get("title") or "").strip()
    artist = (source.get("artist") or "").strip()
    if title or artist:
        return f'"{title}" "{artist}" song release genre BPM key'.strip()

    raw = (question or "").strip()
    quoted = re.findall(r'"([^"]{2,100})"|\'([^\']{2,100})\'', raw)
    quoted_terms = [a or b for a, b in quoted]
    if quoted_terms:
        return " ".join(f'"{term.strip()}"' for term in quoted_terms[:3]) + " music artist song"

    clean = re.sub(
        r"(?i)\b(?:was laeuft|was läuft|what is this song|welcher song|welches lied|who is|wer ist|analysiere|analysis|bpm|key|genre|release|song|artist|music|musik|lied|track|bitte|please|:3|hehe)\b",
        " ", raw,
    )
    clean = re.sub(r"\s+", " ", clean).strip(" ?:;-")
    return f"{clean[:120]} music artist song" if clean else "music artist song"
