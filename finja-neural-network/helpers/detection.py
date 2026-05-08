"""
YourAI AI - Detection System v2.0
==================================
Erkennt Versprechen, Emotionen und Diary-Queries.

Promise System v2: Phi 4 via OpenRouter, Guardian-Architektur
Moods: pouting, disappointed, hurt, sulking

Usage:
    from detection import (
        detect_promises_and_emotions,
        detect_diary_query,
        load_diary_context_for_query,
        auto_search_diary,
        extract_keywords,
        llm_promise_check
    )
"""

import re
import json
import sys, os
from typing import Tuple, Optional, Any, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

# Display wird für Logging gebraucht
from display import log, log_exception, Fore

# Custom Exceptions für sauberes Error Handling
from exceptions import (
    YourAIUnexpectedError,
    YourAILLMError,
    YourAILLMParseError,
    YourAIEmptyResponseError,
    YourAIImportError
)

# Config für Host & Model Defaults
from config import (
    LLM_HOST_STD, MODEL_PROMISE_CHECK, PROMISE_CHECK_TIMEOUT,
    PROMISE_CHECK_MAX_TOKENS, APOLOGY_MIN_WORDS_FOR_SINCERITY,
    MAX_GUARD_LOG_ENTRIES,
    USE_OPENROUTER, OPENROUTER_MODEL_PROMISE,
    USE_DIARY_SEMANTIC_SEARCH, DIARY_SEMANTIC_CANDIDATE_LIMIT,
    DIARY_SEMANTIC_TOP_N, DIARY_SEMANTIC_MIN_SCORE,
    call_openrouter
)
from text_parser import extract_json_from_text as _extract_json


# ==========================================
# PROMISE & EMOTION DETECTION
# ==========================================

def detect_promises_and_emotions(text: str, user: str, persona_manager: Any) -> None:
    """
    Erkennt Versprechen, gebrochene Versprechen und Entschuldigungen.
    Aktualisiert automatisch YourAIs emotionalen Zustand.
    
    Args:
        text: Der User-Input
        user: Username
        persona_manager: personas.persona_manager Instanz
    """
    if persona_manager is None:
        return
    
    pm = persona_manager
    text_lower = text.lower()
    
    # === PROMISE DETECTION ===
    # NUR spezifische Aktivitäts-Versprechen! Keine generic_promise mehr!
    promise_patterns = [
        # DE: Spielen/Zocken
        (r"(?:wir |ich )?(?:spielen?|zocken?) (?:gleich|später|heute|morgen|bald|nachher|dann)", "play_game"),
        (r"lass (?:uns |mal )?(?:spielen|zocken)", "play_game"),
        # DE: Schauen/Gucken
        (r"(?:wir |ich )?(?:schauen?|gucken?) (?:gleich|später|heute|morgen|nachher)", "watch_something"),
        (r"lass (?:uns |mal )?(?:schauen|gucken|anschauen)", "watch_something"),
        # DE: Kochen/Backen
        (r"(?:wir )?(?:kochen?|backen?) (?:gleich|später|heute|morgen|nachher)", "cook_together"),
        (r"lass (?:uns |mal )?(?:kochen|backen)", "cook_together"),
        # DE: Bauen/Basteln
        (r"(?:wir )?(?:bauen?|basteln?) (?:gleich|später|heute|morgen)", "build_something"),
        (r"lass (?:uns |mal )?(?:bauen|basteln)", "build_something"),
        # DE: Allgemein
        (r"(?:wir )?machen? (?:gleich|später|heute|morgen|nachher) (?:was|etwas)", "do_something"),
        (r"lass (?:uns |mal )?(?:was|etwas) (?:machen|unternehmen)", "do_something"),
        # EN
        (r"(?:let'?s|we'?ll|we should|we could) (?:play|watch|cook|build|make) ", "play_game"),
        (r"(?:i'?ll|i will|i promise) (?:play|watch|cook|build) ", "play_game"),
    ]
    
    for pattern, promise_type in promise_patterns:
        if re.search(pattern, text_lower):
            # Spezifischere Typen basierend auf Kontext
            if "minecraft" in text_lower:
                promise_type = "play_minecraft"
            elif "roblox" in text_lower:
                promise_type = "play_roblox"
            elif "fortnite" in text_lower:
                promise_type = "play_fortnite"
            elif "film" in text_lower or "movie" in text_lower or "serie" in text_lower or "anime" in text_lower:
                promise_type = "watch_movie"
            elif "essen" in text_lower or "pizza" in text_lower or "food" in text_lower or "kochen" in text_lower:
                promise_type = "get_food"
            elif "spazier" in text_lower or "raus" in text_lower or "park" in text_lower:
                promise_type = "go_outside"
            elif "lego" in text_lower or "basteln" in text_lower or "bauen" in text_lower:
                promise_type = "build_something"
            
            pm.make_promise(promise_type, f"Promised by {user}: {text[:50]}")
            log("PROMISE", f"📝 New promise detected: {promise_type}", Fore.CYAN)
            break
    
    # === PROMISE BREAKING DETECTION ===
    cancel_patterns = [
        r"(?:doch )?nicht mehr",
        r"(?:geht |können? )?(?:leider )?nicht",
        r"(?:sorry|tut mir leid).*(?:nicht|kann nicht|geht nicht)",
        r"(?:können?|kann) (?:wir )?(?:doch )?nicht",
        r"(?:i |we )?can'?t",
        r"never ?mind",
        r"(?:lass|lassen wir) (?:es )?(?:sein|lieber)",
        r"(?:muss|müssen) (?:erst|leider)",
        r"(?:hab|habe) keine (?:zeit|lust)",
        r"fällt (?:leider )?aus",
        r"schaffen wir (?:heute )?nicht",
        r"wird (?:heute |leider )?nichts",
        # NEU: Deutsche Idiome
        r"muss (?:leider )?ausfallen",
        r"(?:geht|klappt) (?:leider )?(?:doch )?nicht mehr",
        r"(?:verschieben|verlegen) wir",
        r"(?:ein )?anderes? mal",
        r"(?:vielleicht |lieber )?(?:morgen|nächste woche|ein andermal)",
        r"keine lust",
        r"(?:ich )?(?:mag|will) (?:gerade |heute )?nicht",
        # NEU: Englisch
        r"(?:can'?t|won'?t|not going to) (?:do|make|play|watch)",
        r"(?:rain ?check|forget (?:about )?it|skip (?:it|that))",
        r"(?:maybe |some ?)?(?:other|another) time",
    ]
    
    for pattern in cancel_patterns:
        if re.search(pattern, text_lower):
            # Finde aktive (nicht erfüllte, nicht gebrochene) Promises
            active = [(name, p) for name, p in pm.promises.items() 
                      if not p.fulfilled and not p.broken]
            
            if active:
                # Extrahiere Grund
                reason = _extract_reason(text_lower)
                
                # Wenn kein Grund gefunden, nimm den ganzen Text
                if not reason:
                    reason = text[:100] if len(text) > 5 else None
                
                # Breche das erste aktive Versprechen
                name, _ = active[0]
                result = pm.break_promise(name, reason)
                
                log("PROMISE", f"💔 Promise broken: {name}", Fore.RED)
                log("PROMISE", f"   Reason: {reason or 'NONE'} ({result.get('reason_quality', '?')})", Fore.YELLOW)
                log("EMOTION", f"   YourAI: {result.get('response', '')[:60]}...", Fore.MAGENTA)
            break
    
    # === APOLOGY DETECTION ===
    _detect_apology(text_lower, pm)


def _extract_reason(text_lower: str) -> Optional[str]:
    """Extrahiert den Grund aus einem Text."""
    reason_patterns = [
        r"(?:weil|because|da)\s+(.+)",
        r"(?:muss|müssen) erst\s+(.+)",
        r"(?:hab|habe)\s+(.+)",
    ]
    for rp in reason_patterns:
        reason_match = re.search(rp, text_lower)
        if reason_match:
            return reason_match.group(1).strip()
    return None


def _detect_apology(text_lower: str, pm: Any) -> None:
    """Erkennt Entschuldigungen."""
    apology_patterns = [
        r"(?:es )?tut mir (?:wirklich |echt |so )?leid",
        r"entschuldig",
        r"(?:i'?m )?(?:so |really )?sorry",
        r"verzeihe?",
        r"(?:bitte )?nicht (?:böse|sauer|mad)",
    ]
    
    sincere_indicators = [
        "wirklich", "echt", "ehrlich", "really", "truly", 
        "aufrichtig", "von herzen", "so sorry"
    ]
    
    for pattern in apology_patterns:
        if re.search(pattern, text_lower):
            # Check if it seems sincere
            is_sincere = any(w in text_lower for w in sincere_indicators)
            # Longer apologies tend to be more sincere
            if len(text_lower.split()) >= APOLOGY_MIN_WORDS_FOR_SINCERITY:
                is_sincere = True
            
            if pm.current_mood in ("pouting", "disappointed", "hurt", "sulking"):
                response = pm.apologize(sincere=is_sincere)
                log("EMOTION", f"🙏 Apology detected (sincere={is_sincere})", Fore.CYAN)
                log("EMOTION", f"   YourAI: {response}", Fore.MAGENTA)
            break


# ==========================================
# DIARY QUERY DETECTION
# ==========================================

def detect_diary_query(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Erkennt wenn jemand nach alten Diary-Einträgen fragt.
    
    Args:
        text: Der User-Input
        
    Returns:
        (query_type, parameter) oder (None, None)
        
        query_type kann sein:
        - "guardlog": Guard Log anzeigen
        - "list": Alle Wochen auflisten
        - "week": Spezifische Woche (parameter = "last", "W03", etc.)
        - "search": Suche in History (parameter = Suchbegriff)
    """
    text_lower = text.lower()
    
    # === GUARDLOG COMMAND (YourAIs Anforderung!) ===
    if "/guardlog" in text_lower or "guard log" in text_lower or "zeig guard" in text_lower:
        return ("guardlog", None)
    
    # === LIST ALL WEEKS ===
    list_patterns = [
        r"(?:zeig|liste|show|list).*(?:wochen|weeks|diary|tagebuch|rotations?)",
        r"(?:welche|what|which).*(?:wochen|weeks).*(?:habe ich|gibt es|exist)",
        r"(?:list|zeig).*(?:backups?|sicherungen)",
        r"/list_rotations",
        r"/list_backups",
    ]
    for pattern in list_patterns:
        if re.search(pattern, text_lower):
            return ("list", None)
    
    # === SPECIFIC WEEK ===
    # Check for relative weeks first
    if re.search(r"(?:letzte|last|vorige|previous)\s*woche", text_lower):
        return ("week", "last")
    if re.search(r"(?:vorletzte|week before last)", text_lower):
        return ("week", "before_last")
    
    week_patterns = [
        r"(?:woche|week|kw)\s*[#]?(\d{1,2})",
        r"w(\d{2})",
    ]
    
    for pattern in week_patterns:
        match = re.search(pattern, text_lower)
        if match:
            week_num = match.group(1)
            return ("week", f"W{int(week_num):02d}")
    
    # === SEARCH IN HISTORY ===
    search_patterns = [
        r"(?:wann|when).*(?:haben wir|did we|habe ich).*(?:zuletzt|last)",
        r"(?:such|find|search).*(?:nach|for)\s+['\"]?(\w+)['\"]?",
    ]
    
    for pattern in search_patterns:
        match = re.search(pattern, text_lower)
        if match:
            groups = match.groups()
            search_term = groups[0] if groups and groups[0] else None
            
            if not search_term:
                keywords = ["minecraft", "stream", "coding", "game", "movie", "film", "programming"]
                for kw in keywords:
                    if kw in text_lower:
                        search_term = kw
                        break
            
            if search_term:
                return ("search", search_term)
    
    return (None, None)


def load_diary_context_for_query(
    query_type: str, 
    parameter: Optional[str], 
    journal: Any,
    get_guard_log_func: Any = None
) -> str:
    """
    Lädt den entsprechenden Diary-Kontext basierend auf der Query.
    
    Args:
        query_type: "list", "week", "search", oder "guardlog"
        parameter: Parameter für die Query
        journal: episodic.journal Instanz
        get_guard_log_func: Funktion zum Holen des Guard Logs
        
    Returns:
        Formatierter Kontext-String
    """
    # === GUARDLOG COMMAND ===
    if query_type == "guardlog":
        if get_guard_log_func:
            return get_guard_log_func(last_n=MAX_GUARD_LOG_ENTRIES)
        return "Guard Log nicht verfügbar."
    
    if journal is None:
        return ""
    
    if query_type == "list":
        return _format_list_rotations(journal)
    
    elif query_type == "week":
        return _format_week_entries(journal, parameter)
    
    elif query_type == "search":
        results = journal.search_all(parameter, limit=10)
        return f"🔍 **SUCHE NACH '{parameter}':**\n\n{results}"
    
    return ""


def _format_list_rotations(journal: Any) -> str:
    """Formatiert die Liste aller Wochen."""
    rotations = journal.list_rotations()
    
    result = "📋 **DEINE TAGEBUCH-ÜBERSICHT:**\n\n"
    result += f"**Aktuelle Woche:** {rotations['current_week']['week_id']} ({rotations['current_week']['entries']} Einträge)\n\n"
    
    if rotations['available_weeks']:
        result += "**Archivierte Wochen:**\n"
        for week in rotations['available_weeks']:
            result += f"- {week['week_id']}: {week['entries']} Einträge\n"
    else:
        result += "Keine archivierten Wochen (noch keine Rotation passiert)\n"
    
    result += f"\n**Backups:** {len(rotations['available_backups'])} vorhanden"
    result += f"\n**Einträge gesamt:** {rotations['total_entries_all_time']}"
    
    return result


def _format_week_entries(journal: Any, parameter: Optional[str]) -> str:
    """Formatiert die Einträge einer Woche."""
    current_week = journal.current_week_id
    year = current_week.split("_W")[0]
    current_week_num = int(current_week.split("_W")[1])
    
    if parameter == "last":
        week_num = current_week_num - 1
        if week_num < 1:
            week_num = 52
            year = str(int(year) - 1)
        target_week = f"{year}_W{week_num:02d}"
    elif parameter == "before_last":
        week_num = current_week_num - 2
        if week_num < 1:
            week_num = 52 + week_num
            year = str(int(year) - 1)
        target_week = f"{year}_W{week_num:02d}"
    elif parameter and parameter.startswith("W"):
        target_week = f"{year}_{parameter}"
    else:
        target_week = parameter or current_week
    
    entries = journal.get_week(target_week)
    summary = journal.get_summary(target_week)
    
    result = f"📖 **TAGEBUCH WOCHE {target_week}:**\n\n"
    
    if isinstance(summary, dict) and not summary.get("error"):
        result += f"**Zusammenfassung:**\n"
        result += f"- Einträge: {summary.get('total_entries', 0)}\n"
        tags = list(summary.get('tags_frequency', {}).keys())[:5]
        if tags:
            result += f"- Themen: {', '.join(tags)}\n"
    
    result += f"\n**Einträge:**\n{entries}"
    
    return result


# ==========================================
# AUTO KEYWORD EXTRACTION & SEARCH
# ==========================================

# Words to ignore when extracting keywords
STOP_WORDS = {
    # English
    "i", "me", "my", "you", "your", "we", "our", "the", "a", "an", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above", "below", "between",
    "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "about", "also", "now", "well", "hey",
    "hi", "hello", "okay", "ok", "yes", "yeah", "no", "nope", "please", "thanks", "thank",
    "what", "who", "which", "this", "that", "these", "those", "it", "its", "and", "but", "or",
    "if", "because", "while", "although", "though", "even", "still", "already", "always",
    "really", "actually", "anyway", "something", "anything", "everything", "nothing",
    # English - common verbs & words that pollute search
    "let", "lets", "get", "got", "put", "set", "run", "say", "said", "tell", "told",
    "know", "knew", "think", "thought", "come", "came", "take", "took", "make", "made",
    "give", "gave", "look", "see", "saw", "seen", "want", "need", "try", "keep", "kept",
    "test", "remember", "remind", "recall", "forget", "show", "talk", "speak", "ask",
    "asked", "tell", "answer", "help", "start", "stop", "open", "close", "turn",
    "thing", "things", "stuff", "way", "time", "right", "like", "going", "gonna",
    "cutie", "sweetie", "honey", "dear", "babe", "love",
    # German
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mich", "dich", "sich", "uns", "euch",
    "mein", "dein", "sein", "ihr", "unser", "euer", "der", "die", "das", "ein", "eine",
    "und", "oder", "aber", "denn", "weil", "wenn", "als", "ob", "dass", "nicht", "kein",
    "auch", "noch", "schon", "nur", "sehr", "viel", "mehr", "wenig", "ganz", "gar",
    "ja", "nein", "doch", "mal", "halt", "eben", "wohl", "etwa", "fast", "kaum",
    "hier", "dort", "da", "wo", "wie", "was", "wer", "wann", "warum", "woher", "wohin",
    "jetzt", "heute", "gestern", "morgen", "immer", "nie", "oft", "manchmal", "bitte",
    "danke", "hallo", "hey", "na", "also", "gut", "okay", "alles", "etwas", "nichts",
    # German - common verbs that pollute search
    "lass", "lassen", "lass", "gib", "geben", "mach", "machen", "sag", "sagen",
    "zeig", "zeigen", "schau", "schauen", "guck", "gucken", "weiß", "weißt",
    "kannst", "könntest", "willst", "möchtest", "musst", "sollst",
    "erzähl", "erzählen", "erinnerst", "erinnern",
    # Common chat words & greetings
    "lol", "xd", "haha", "hmm", "uhm", "uh", "oh", "ah", "wow", "yay", "aww", "ugh",
    "hii", "hiii", "hiiii", "heyyy", "sooo", "soo", "sooooo",
    "yeahhh", "yeahh", "yesss", "yess", "noo", "nooo",
    "ohhh", "ahhh", "oooh", "ooo", "ehh", "ehhh",
    "anyways", "anyway", "btw", "omg", "omgg", "bruh",
    "back", "fine", "good", "great", "nice", "cool", "cute",
    "happy", "feeling", "missed", "hope", "better", "worse",
    "ready", "sure", "maybe", "idk", "dunno",
    # YourAI-specific to ignore
    "yourai", "altpersona", "dad", "admin", "user", "bot",
}

# Minimum word length to consider as keyword
MIN_KEYWORD_LENGTH = 3


def extract_keywords(text: str, max_keywords: int = 5) -> list:
    """
    Extract meaningful keywords from text for searching.
    
    Args:
        text: User input text
        max_keywords: Maximum number of keywords to return
        
    Returns:
        List of keywords sorted by relevance
    """
    # Clean and tokenize
    text_clean = re.sub(r'[^\w\s]', ' ', text.lower())
    words = text_clean.split()
    
    # Filter out stop words, short words, and greeting noise
    keywords = []
    for word in words:
        if len(word) < MIN_KEYWORD_LENGTH or word.isdigit():
            continue
        if word in STOP_WORDS:
            continue
        # Greeting noise: repeated chars like "hiiiii", "sooooo", "yeahhh", "nooooo"
        # If removing repeated chars leaves a stopword → skip
        collapsed = re.sub(r'(.)\1{2,}', r'\1', word)  # "hiiiii" → "hi", "sooooo" → "so"
        if collapsed in STOP_WORDS or len(collapsed) <= 2:
            continue
        keywords.append(word)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    # Prioritize proper nouns (names) - words that are capitalized MID-SENTENCE
    # Words at start of sentence or after punctuation don't count as names!
    original_words = text.split()
    prioritized = []
    regular = []
    
    for kw in unique_keywords:
        is_name = False
        for i, w in enumerate(original_words):
            if w.lower() == kw and len(w) > 0 and w[0].isupper():
                # Only count as name if NOT at sentence start
                if i > 0:
                    prev = original_words[i - 1]
                    # If previous word ends with sentence-ending punctuation, it's sentence start
                    if prev[-1] in ".!?:":
                        continue
                    # If previous word is a lowercase word, this IS a real mid-sentence capital = name
                    is_name = True
                    break
                # First word of text is never treated as a name
        
        if is_name:
            prioritized.append(kw)
        else:
            regular.append(kw)
    
    return (prioritized + regular)[:max_keywords]


def _parse_diary_entries(text: str) -> list:
    """
    Parsed formatierten diary-search-Text in (content, full_text) Tuples.

    Erwartet Format:
        [Keyword: xyz]              ← übersprungen
        🔍 Found N entries for ...  ← übersprungen
        [2026-04-10 Thu] (current (2026_W15))
          Diary content here

    Returns:
        List of (content_for_ranking, full_display_text)
    """
    entries = []
    current_lines = []

    for line in text.split('\n'):
        if line.startswith('🔍') or line.startswith('[Keyword:'):
            continue
        # Diary-Eintrag-Header: [irgendwas] (irgendwas)
        if re.match(r'\[.+\]\s*\(.+\)', line):
            if current_lines:
                full = '\n'.join(current_lines).strip()
                if full:
                    parts = full.split('\n', 1)
                    content = parts[1].strip() if len(parts) > 1 else full
                    entries.append((content, full))
            current_lines = [line]
        elif current_lines:
            current_lines.append(line)

    if current_lines:
        full = '\n'.join(current_lines).strip()
        if full:
            parts = full.split('\n', 1)
            content = parts[1].strip() if len(parts) > 1 else full
            entries.append((content, full))

    return entries


def _format_diary_entry(entry: dict) -> str:
    source = entry.get("_source", "unknown")
    return f"[{entry.get('date_readable', '?')}] ({source})\n  {entry.get('content', '')}"


def _entry_rank_text(entry: dict) -> str:
    tags = ", ".join(entry.get("tags", []) or [])
    content = entry.get("content", "")
    date = entry.get("date_readable", "")
    return f"{date}\nTags: {tags}\n{content}"[:1200]


def _candidate_key(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())[:220]


def semantic_search_diary(question: str, journal: Any, user_id: str = "") -> str:
    """
    Semantic first-stage diary recall using Cohere embeddings.

    This broadens recall beyond literal keywords. The caller still reranks the
    combined candidate set before injecting prompt context.
    """
    if not USE_DIARY_SEMANTIC_SEARCH or journal is None or not hasattr(journal, "iter_entries"):
        return ""

    try:
        entries = journal.iter_entries(user_id=user_id, include_archives=True, limit=DIARY_SEMANTIC_CANDIDATE_LIMIT)
        if not entries:
            return ""

        from tools.cohere_embeddings import cosine_similarity, embed_texts

        query_vecs = embed_texts([question], input_type="search_query")
        if not query_vecs:
            return ""

        docs = [_entry_rank_text(entry) for entry in entries]
        doc_vecs = embed_texts(docs, input_type="search_document")
        if not doc_vecs:
            return ""

        scored = []
        query_vec = query_vecs[0]
        for idx, doc_vec in enumerate(doc_vecs):
            score = cosine_similarity(query_vec, doc_vec)
            if score >= DIARY_SEMANTIC_MIN_SCORE:
                scored.append((score, entries[idx]))

        if not scored:
            return ""

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:DIARY_SEMANTIC_TOP_N]
        scores = ", ".join(f"{score:.3f}" for score, _ in top[:8])
        log("DIARY", f"Semantic search found {len(top)} candidates [{scores}]", Fore.GREEN)
        return "\n---\n".join(_format_diary_entry(entry) for _, entry in top)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="diary_semantic_search", context={"question": question[:80]})
        log_exception("DIARY", err)
        return ""


def auto_search_diary(question: str, journal: Any, limit: int = 10, user_id: str = "") -> str:
    """
    Automatically extract keywords from question and search diary.

    Args:
        question: User's question
        journal: episodic.journal instance
        limit: Max entries to return
        user_id: If set, only search entries belonging to this user

    Returns:
        Formatted search results or empty string if nothing found
    """
    if journal is None:
        return ""

    keywords = extract_keywords(question)
    semantic_results = semantic_search_diary(question, journal, user_id=user_id)

    if not keywords and not semantic_results:
        return ""
    
    log("DIARY", f"🔍 Auto-searching for: {keywords}", Fore.CYAN)
    try:
        from clients.dashboard_client import debug as _dbg
    except Exception:
        _dbg = None

    # Reranker verfügbar? → mehr Ergebnisse holen, dann nach Relevanz sortieren
    _use_rerank = False
    try:
        from config import USE_RERANKER
        _use_rerank = USE_RERANKER
    except Exception:
        pass

    _per_keyword  = 6 if _use_rerank else 3   # Pro Keyword — 5 Keywords × 6 = 30 Kandidaten
    _max_keywords = 5 if _use_rerank else 3   # Mehr Keywords → breiteres Netz

    all_results = []

    if semantic_results:
        all_results.append(f"[Semantic]\n{semantic_results}")
        if _dbg:
            _dbg.info("diary", "Semantic diary candidates found", details=semantic_results[:500])

    for keyword in keywords[:_max_keywords]:
        try:
            if hasattr(journal, 'search_all'):
                results_text = journal.search_all(keyword, limit=_per_keyword, user_id=user_id)

                if results_text and "No entries found" not in results_text:
                    all_results.append(f"[Keyword: {keyword}]\n{results_text}")
                    if _dbg:
                        _dbg.info("diary", f"🔍 Keyword '{keyword}': found entries", details=results_text[:500])
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="diary_search", context={"keyword": keyword})
            log_exception("DIARY", err)

    if not all_results:
        log("DIARY", f"📭 No diary entries found for: {keywords}", Fore.YELLOW)
        if _dbg:
            _dbg.info("diary", f"📭 No diary entries for: {', '.join(keywords)}")
        return ""  # Leerer String statt Placeholder → spart Tokens

    # RERANKER: Einzelne Einträge parsen und nach Relevanz zur Frage sortieren
    if _use_rerank:
        try:
            from tools.reranker import rerank_documents

            # Alle Blöcke in einzelne Einträge aufteilen
            all_entries = []
            by_key = {}
            for block in all_results:
                source = "semantic" if block.startswith("[Semantic]") else "keyword"
                for content, full in _parse_diary_entries(block):
                    key = _candidate_key(content)
                    if key not in by_key:
                        by_key[key] = {
                            "content": content,
                            "full": full,
                            "sources": set(),
                        }
                        all_entries.append(by_key[key])
                    by_key[key]["sources"].add(source)

            if all_entries and len(all_entries) > 1:
                docs = []
                for entry in all_entries:
                    source_note = ""
                    if len(entry["sources"]) > 1:
                        source_note = "Recall signals: semantic embedding + keyword match.\n"
                    docs.append(source_note + entry["content"])
                ranked = rerank_documents(question, docs, top_n=min(16, len(docs)))

                if ranked:
                    for r in ranked:
                        sources = all_entries[r["index"]]["sources"]
                        if len(sources) > 1:
                            r["relevance_score"] = min(1.0, r["relevance_score"] + 0.08)
                    ranked.sort(key=lambda r: r["relevance_score"], reverse=True)
                    # Threshold: nur Einträge mit echter Relevanz behalten
                    ranked = [r for r in ranked if r["relevance_score"] >= 0.05]
                    if not ranked:
                        log("DIARY", "📭 Reranker: alle Scores unter Threshold → kein Diary-Kontext", Fore.YELLOW)
                        return ""
                    reranked = [all_entries[r["index"]]["full"] for r in ranked]
                    scores = [
                        f"{r['relevance_score']:.3f}/{'+' if len(all_entries[r['index']]['sources']) > 1 else '-'}"
                        for r in ranked
                    ]
                    combined = "\n---\n".join(reranked)
                    log("DIARY", f"✅ Reranked {len(all_entries)} → {len(ranked)} entries {scores}", Fore.GREEN)
                    if _dbg:
                        _dbg.info("diary_rerank", f"📊 Reranked {len(all_entries)} → {len(ranked)} entries", f"Scores: {scores}")
                    return combined
        except Exception as e:
            log("DIARY", f"⚠️ Reranker failed ({e}), using original order", Fore.YELLOW)

    # Fallback: Original-Reihenfolge (kein Reranker oder Fehler)
    combined = "\n---\n".join(all_results[:2])  # Max 2 keyword results

    log("DIARY", f"✅ Found diary entries for {len(all_results)} keywords", Fore.GREEN)

    return combined


def auto_search_memory(question: str, hippocampus: Any, limit: int = 5) -> list:
    """
    Automatically extract keywords from question and search memory.
    
    Args:
        question: User's question
        hippocampus: hippocampus module
        limit: Max memories to return
        
    Returns:
        List of relevant memories
    """
    if hippocampus is None:
        return []
    
    keywords = extract_keywords(question)
    
    if not keywords:
        return []
    
    # The hippocampus already does semantic search on the question
    # But we can enhance it by also searching for specific keywords
    all_memories = []
    
    try:
        # Search with the full question (semantic)
        if hasattr(hippocampus, 'memory') and hasattr(hippocampus.memory, 'search'):
            mems = hippocampus.memory.search(question, n_results=limit)
            all_memories.extend(mems)
        
        # Also search for each keyword individually for better coverage
        for keyword in keywords[:3]:  # Top 3 keywords
            if hasattr(hippocampus, 'memory') and hasattr(hippocampus.memory, 'search'):
                kw_mems = hippocampus.memory.search(keyword, n_results=2)
                for mem in kw_mems:
                    if mem not in all_memories:
                        all_memories.append(mem)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="memory_search", context={"question": question[:50]})
        log_exception("MEMORY", err)
    
    return all_memories[:limit]


# ==========================================
# LLM-BASED PROMISE DETECTION
# ==========================================

def llm_promise_check(
    current_message: str,
    recent_history: List[str],
    persona_manager: Any,
    llm_host: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    debug: Any = None
) -> Optional[Dict]:
    """
    Promise Check v2 — Phi 4 via OpenRouter, Guardian-Architektur.

    Tier 1: OpenRouter (Phi 4)  → schnell, zuverlässig
    Tier 2: Lokal (gemma3:4b)   → Fallback wenn OpenRouter down

    Returns:
        Dict with action result or None on error
    """
    import time
    from prompts import PROMPT_PROMISE_CHECK

    if llm_host is None:
        llm_host = LLM_HOST_STD
    if model is None:
        model = MODEL_PROMISE_CHECK
    if timeout is None:
        timeout = PROMISE_CHECK_TIMEOUT

    # --- Active Promises sammeln ---
    active_promises_text = "(No active promises)"
    active_promise_names = set()
    if persona_manager and hasattr(persona_manager, 'promises'):
        active = []
        for name, p in persona_manager.promises.items():
            if not p.fulfilled and not p.broken:
                active.append(f"- {name}: {p.description or name}")
                active_promise_names.add(name)
        if active:
            active_promises_text = "\n".join(active)

    # --- Prompt formatieren ---
    user_prompt = PROMPT_PROMISE_CHECK.format(
        active_promises=active_promises_text,
        current_message=current_message
    )

    log("PROMISE", f"🔍 Check: '{current_message[:60]}' | Active: {active_promise_names or 'none'}", Fore.CYAN)

    # --- LLM Call (Tier 1 → Tier 2) ---
    try:
        t0 = time.time()
        res = None
        used_model = "?"

        # TIER 1: OpenRouter (Phi 4)
        if USE_OPENROUTER:
            try:
                used_model = OPENROUTER_MODEL_PROMISE
                log("PROMISE", f"☁️ OpenRouter: {used_model}", Fore.CYAN)

                res, _ = call_openrouter(
                    system_prompt="You are YourAI's strict Promise Tracker. Output JSON only.",
                    user_message=user_prompt,
                    model=OPENROUTER_MODEL_PROMISE,
                    temperature=0,
                    max_tokens=PROMISE_CHECK_MAX_TOKENS,
                )

                if not res or not res.strip():
                    raise YourAIEmptyResponseError(model=used_model, node="promise_check")

                ms = int((time.time() - t0) * 1000)
                log("PROMISE", f"☁️ Antwort ({ms}ms)", Fore.CYAN)

            except YourAIEmptyResponseError:
                log("PROMISE", "☁️ Leer → Fallback lokal", Fore.YELLOW)
                res = None
            except Exception as e:
                log("PROMISE", f"☁️ {e} → Fallback lokal", Fore.YELLOW)
                res = None

        # TIER 2: Lokal (Fallback)
        if res is None:
            try:
                from langchain_ollama import ChatOllama
                from langchain_core.messages import HumanMessage

                t1 = time.time()
                used_model = model
                log("PROMISE", f"🖥️ Lokal: {used_model}", Fore.CYAN)

                llm = ChatOllama(
                    model=model,
                    base_url=llm_host,
                    temperature=0,
                    num_predict=PROMISE_CHECK_MAX_TOKENS,
                )
                res = str(llm.invoke([HumanMessage(content=user_prompt)]).content or "").strip()

                if not res:
                    raise YourAIEmptyResponseError(model=used_model, node="promise_check")

                ms = int((time.time() - t1) * 1000)
                log("PROMISE", f"🖥️ Antwort ({ms}ms)", Fore.CYAN)

            except YourAIEmptyResponseError:
                raise
            except Exception as e:
                log("PROMISE", f"🖥️ Lokal fehlgeschlagen: {e}", Fore.RED)
                return None

        total_ms = int((time.time() - t0) * 1000)

        # --- JSON parsen (Phi 4: kein <think>, direkt JSON) ---
        json_data = _extract_json(res)
        if json_data is None:
            err = YourAILLMParseError(
                model=used_model,
                expected="JSON with 'action' key",
                raw_preview=res[:200],
                module="promise_check",
            )
            log_exception("PROMISE", err)
            return None

        action = (json_data.get("action") or "NONE").upper().strip()
        promise_name = json_data.get("promise", "none")
        reason_text = json_data.get("reason", "none")
        reason_quality = (json_data.get("reason_quality") or "NONE").upper().strip()

        # --- NONE: Nichts passiert ---
        if action == "NONE":
            log("PROMISE", f"✅ NONE ({total_ms}ms, {used_model})", Fore.GREEN)
            return json_data

        # --- HARD OVERRIDE: Halluzinations-Schutz ---
        if not active_promise_names and action in ("BROKEN", "FULFILLED"):
            log("PROMISE", f"⚠️ LLM halluziniert '{action}' für '{promise_name}' — KEINE aktiven Promises! Ignoriert.", Fore.YELLOW)
            return None

        log("PROMISE", f"🔍 {action}: {promise_name} (quality={reason_quality}, {total_ms}ms)", Fore.CYAN)

        if not persona_manager:
            return json_data

        # === FULFILLED: Promise eingelöst! ===
        if action == "FULFILLED":
            _handle_fulfilled(promise_name, active_promise_names, persona_manager, debug)

        # === BROKEN: Promise gebrochen ===
        elif action == "BROKEN":
            _handle_broken(promise_name, reason_text, reason_quality, active_promise_names, persona_manager, current_message, debug)

        # === MADE: Neues Promise ===
        elif action == "MADE":
            _handle_made(promise_name, persona_manager, current_message, debug)

        return json_data

    except YourAIEmptyResponseError as e:
        log_exception("PROMISE", e)
        return None
    except Exception as e:
        err = YourAILLMError("Promise check failed", model=used_model if 'used_model' in dir() else "?", module="promise_check", cause=e)
        log_exception("PROMISE", err)
        return None


# ==========================================
# PROMISE ACTION HANDLERS
# ==========================================

def _handle_fulfilled(promise_name: str, active_names: set, pm: Any, debug: Any) -> None:
    """Promise eingelöst — exakter oder fuzzy Match."""
    # Exakter Match
    if pm.promises.get(promise_name):
        pm.fulfill_promise(promise_name)
        log("PROMISE", f"🎉 Fulfilled: {promise_name}", Fore.GREEN)
        if debug and hasattr(debug, 'promise_event'):
            debug.promise_event("fulfilled", promise_name)
        return

    # Fuzzy Match
    for active_name in active_names:
        if (promise_name in active_name or
            active_name in promise_name or
            promise_name.replace("_", " ") in active_name.replace("_", " ")):
            pm.fulfill_promise(active_name)
            log("PROMISE", f"🎉 Fulfilled (fuzzy): {active_name} ← '{promise_name}'", Fore.GREEN)
            if debug and hasattr(debug, 'promise_event'):
                debug.promise_event("fulfilled", active_name, details=f"fuzzy: '{promise_name}'")
            return

    log("PROMISE", f"⚠️ Fulfilled '{promise_name}' — kein Match gefunden", Fore.YELLOW)


def _handle_broken(promise_name: str, reason: str, quality: str, active_names: set,
                    pm: Any, message: str, debug: Any) -> None:
    """Promise gebrochen — mit Emotions-Mapping."""
    # Vage Namen ignorieren
    if promise_name in ("none", "generic_promise", "previous_activity"):
        log("PROMISE", f"⚠️ Ignoriere vagen Break: '{promise_name}'", Fore.YELLOW)
        return

    # Muss aktiv sein
    if promise_name not in active_names:
        log("PROMISE", f"⚠️ '{promise_name}' ist nicht aktiv — Halluzination ignoriert", Fore.YELLOW)
        return

    # Reason fallback
    if not reason or reason == "none":
        reason = message[:80] if len(message) > 5 else None

    pm.break_promise(promise_name, reason=reason)

    log("PROMISE", f"💔 Broken: {promise_name} | Quality: {quality} | Reason: {reason}", Fore.RED)
    if debug and hasattr(debug, 'promise_event'):
        debug.promise_event("broken", promise_name, reason=reason, details=f"quality: {quality}")


_JUNK_PROMISE_WORDS = {
    "dm", "test", "fix", "bug", "code", "error", "debug",
    "api", "server", "bot", "config", "update", "deploy",
    "commit", "push", "pull", "merge", "build", "run",
    "check", "log", "send", "message", "chat", "system",
    "prompt", "model", "token", "response", "request",
    "generic_promise", "previous_activity", "activity", "none",
}


def _handle_made(promise_name: str, pm: Any, message: str, debug: Any) -> None:
    """Neues Promise erstellt — mit Junk-Filter."""
    name_words = set(promise_name.lower().replace("_", " ").split())
    if name_words.issubset(_JUNK_PROMISE_WORDS):
        log("PROMISE", f"⚠️ Fake-Promise ignoriert: '{promise_name}'", Fore.YELLOW)
        return

    pm.make_promise(promise_name)
    log("PROMISE", f"🤝 Made: {promise_name}", Fore.GREEN)
    if debug and hasattr(debug, 'promise_event'):
        debug.promise_event("made", promise_name, details=message[:80])
