"""
YourAI AI - Text Parser
========================
Gemeinsame Text-Parser für alle Module.
Eliminiert Duplikation zwischen brain und autonomy_guard.

Usage:
    from text_parser import extract_thoughts, extract_json_from_text
"""

import json
import re
import sys, os
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception, Fore, log
from exceptions import YourAIUnexpectedError


def extract_thoughts(text: str) -> Tuple[str, str]:
    """
    Extrahiert Thinking-Tags aus LLM-Responses.
    
    Supported Tags: <think>, <thinking>, <thought>, <scratchpad>
    
    Args:
        text: Raw LLM response
        
    Returns:
        Tuple von (thoughts, clean_text)
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
        
        # Fallback: Text vor JSON als "Gedanken" behandeln
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
        # Fail-Safe: Gib einfach den originalen Text zurück
        return "", text


def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Extrahiert JSON aus Text - versucht mehrere Strategien.
    
    1. Direktes JSON parsing
    2. ```json ... ``` Blöcke
    3. Erstes { bis letztes } 
    
    Args:
        text: Text der JSON enthalten könnte
        
    Returns:
        Parsed dict oder None
    """
    if not isinstance(text, str):
        return None
        
    try:
        # Strategie 1: Direktes parsing
        try: 
            return json.loads(text)
        except (json.JSONDecodeError, TypeError): 
            pass
        
        # Strategie 2: Markdown JSON Block
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try: 
                return json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError): 
                pass
        
        # Strategie 3: Erstes { bis letztes }
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start: 
                return json.loads(text[start:end])
        except (json.JSONDecodeError, TypeError): 
            pass
        
        # Wenn alle Strategien scheitern, gib None zurück (das wird von den Modulen erwartet)
        return None
        
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="text_parser_json")
        log_exception("PARSER", err)
        return None


# ==========================================
# SEARCH QUERY EXTRACTION
# ==========================================
# Konvertiert chaotische User-Nachrichten zu fokussierten Suchbegriffen.
# Wird z.B. vom Anime-Expert genutzt für mandatory Web Search.
# ==========================================

# Conversational filler (Sprache-agnostisch)
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
    # --- Neue Filler ---
    # Höflichkeitsfloskeln
    r'\b(?:please|bitte)\b',
    # Internet-Slang
    r'\b(?:lmao|rofl|lmfao|omg|bruh|btw|tbh|ngl|afaik|imo|imho)\b',
    # Zustimmung / Ablehnung
    r'\b(?:yeah|yep|yup|nope|nah|mhm|ugh|pls)\b',
    # Deutsche Füllwörter (Einzelwörter die oft Satzanfänge füllen)
    r'\b(?:warte|schau\s+mal|mal\s+kurz|eigentlich|irgendwie|grad|gerade|kurz)\b',
    # Hedges / Unsicherheiten
    r'\b(?:I\s+think|I\s+guess|I\s+mean|you\s+know|ich\s+glaube|ich\s+meine|ich\s+denke)\b',
    # Nummerierte Versuche am Satzanfang z.B. "1." / "#3"
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
    # --- Neue Prefixe ---
    # EN: "have you heard of", "I want to know about", "give me info on"
    r"(?:have\s+you\s+(?:ever\s+)?heard\s+(?:of|about))\s+(?:an?\s+|the\s+)?",
    r"(?:I\s+(?:want|need)\s+to\s+(?:know|find\s+out)\s+(?:about\s+)?(?:an?\s+)?)",
    r"(?:give\s+me\s+(?:info|information)\s+(?:on|about)\s+(?:an?\s+)?)",
    r"(?:(?:search|find|look\s+up)\s+(?:for\s+)?(?:an?\s+|the\s+)?)",
    # DE: "kennst du ein", "hast du schon von X gehört", "zeig mir"
    r"(?:kennst\s+du\s+(?:ein(?:en|em|es)?\s+)?)",
    r"(?:hast\s+du\s+(?:schon\s+)?(?:mal\s+)?(?:von|über)\s+)",
    r"(?:zeig\s+mir\s+(?:mal\s+)?(?:ein(?:en|em|es)?\s+)?)",
    r"(?:erkläre?\s+mir\s+(?:mal\s+)?(?:was\s+)?(?:ein(?:en|em|es)?\s+)?)",
]


def extract_search_query(text: str, prefix: str = "") -> str:
    """
    Extrahiert eine fokussierte Suchquery aus einer chaotischen User-Nachricht.

    Entfernt Chat-Filler, Emoticons, "ich suche nach..." Prefixe, und
    normalisiert Whitespace. Optional wird ein Domain-Prefix vorangestellt.

    Args:
        text: Rohe User-Nachricht
        prefix: Domain-Prefix z.B. "anime" (wird vorangestellt)

    Returns:
        Bereinigte Suchquery

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

    # Step 3.5: Strip leading punctuation AGAIN — prefix removal kann Doppelpunkte hinterlassen
    # z.B. "ich suche: X" → nach prefix-strip → ": X" → "X"
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