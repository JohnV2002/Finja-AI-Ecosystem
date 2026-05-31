"""
YourAI Detection Helpers
=======================
Detects promises, diary requests, and intent signals in user messages.

Main Responsibilities:
- Extract structured signals from user text.
- Load diary context for memory-oriented queries.
- Use regex and LLM helpers without directly mutating promise state.

Side Effects:
- Reads diary and guard-log data.
- May call LLM endpoints for promise signal classification.
- Writes audit logs for promise detection.
"""
import re
import json
import sys, os
from dataclasses import dataclass, field
from typing import Tuple, Optional, Any, List, Dict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

# Display is needed for logging.
from display import log, log_exception, Fore

# Custom exceptions for clean error handling.
from exceptions import (
    YourAIUnexpectedError,
    YourAILLMError,
    YourAILLMParseError,
    YourAIEmptyResponseError,
    YourAIImportError
)

# Config for host and model defaults.
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
# PROMISE SIGNAL (v3 Architecture)
# ==========================================

PROMISE_TTL_HOURS = 24
PROMISE_LEARNING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker_data", "promise_learning.json")
PROMISE_EVENTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker_data", "promise_events.jsonl")
PROMISE_LEARNING_MAX = 50

_PROMISE_LABELS_DE = {
    "drink_cocoa_with_caffeine": "Kakao mit Koffein trinken",
    "talk_about_conversation": "ueber das Gespraech sprechen",
    "tell_about_conversation": "vom Gespraech erzaehlen",
    "call_friend": "einen Freund anrufen",
    "watch_anime": "Anime schauen",
    "play_minecraft": "Minecraft spielen",
    "offer_love": "Liebe anbieten",
}


def promise_display_labels(name: str) -> dict:
    """Human labels for promise keys. Internal key stays stable/English."""
    clean = (name or "promise").replace("_", " ").strip()
    english = clean[:1].upper() + clean[1:] if clean else "Promise"
    return {
        "en": english,
        "de": _PROMISE_LABELS_DE.get(name, clean),
    }


def _append_promise_audit(action: str, promise_name: str, user_id: str = "", source: str = "", details: Optional[dict] = None) -> None:
    """Handle append promise audit helper behavior."""
    try:
        os.makedirs(os.path.dirname(PROMISE_EVENTS_FILE), exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(),
            "action": action,
            "promise_name": promise_name,
            "labels": promise_display_labels(promise_name),
            "user_id": user_id or "",
            "source": source or "",
            "details": details or {},
        }
        with open(PROMISE_EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        log("PROMISE", f"⚠️ Promise audit failed: {e}", Fore.RED)

@dataclass
class PromiseSignal:
    """Signal from regex or LLM; no state writes, just data."""
    action: str              # "NONE", "MADE", "BROKEN", "FULFILLED"
    promise_name: str = "none"
    reason: Optional[str] = None
    reason_quality: str = "NONE"  # "GOOD", "WEAK", "BAD", "NONE"
    source: str = "unknown"       # "regex" or "llm"
    confidence: str = "low"       # "low", "medium", "high"
    reasoning: str = ""
    original_message: str = ""

    @property
    def is_actionable(self) -> bool:
        """Handle is actionable helper behavior."""
        return self.action != "NONE"

    def to_dict(self) -> dict:
        """Handle to dict helper behavior."""
        labels = promise_display_labels(self.promise_name)
        return {
            "action": self.action, "promise_name": self.promise_name,
            "display_label": labels["en"], "labels": labels,
            "reason": self.reason, "reason_quality": self.reason_quality,
            "source": self.source, "reasoning": self.reasoning,
            "original_message": self.original_message,
        }


# ==========================================
# PROMISE LEARNING (User-Feedback Loop)
# ==========================================

def _load_learning() -> dict:
    """Load learned promise negatives from JSON."""
    try:
        if os.path.exists(PROMISE_LEARNING_FILE):
            with open(PROMISE_LEARNING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {"negatives": []}


def save_promise_rejection(message: str, detected_as: str, user_id: str = "") -> None:
    """Store a rejected promise detection as a negative LLM learning example."""
    data = _load_learning()
    msg = message[:200]
    now = datetime.now().isoformat()
    duplicate = None
    for item in data.get("negatives", []):
        if item.get("message") == msg and item.get("detected_as") == detected_as and item.get("rejected_by") == user_id:
            duplicate = item
            break
    if duplicate:
        duplicate["rejected_at"] = now
        duplicate["count"] = int(duplicate.get("count", 1) or 1) + 1
    else:
        data["negatives"].append({
            "message": msg,
            "detected_as": detected_as,
            "rejected_by": user_id,
            "rejected_at": now,
            "count": 1,
        })
    if len(data["negatives"]) > PROMISE_LEARNING_MAX:
        data["negatives"] = data["negatives"][-PROMISE_LEARNING_MAX:]
    try:
        with open(PROMISE_LEARNING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log("PROMISE", f"📚 Learned negative: '{message[:60]}' != {detected_as}", Fore.CYAN)
        _append_promise_audit("REJECTED", detected_as, user_id=user_id, source="user_feedback", details={"message": msg})
    except OSError as e:
        log("PROMISE", f"⚠️ Learning save failed: {e}", Fore.RED)


def get_learned_negatives_for_prompt() -> str:
    """Format learned negatives as LLM prompt section."""
    data = _load_learning()
    negs = data.get("negatives", [])
    if not negs:
        return ""
    recent = negs[-10:]
    lines = []
    for n in recent:
        lines.append(f'- "{n["message"][:80]}" -> was NOT a promise (wrongly detected as {n["detected_as"]})')
    return "\nLEARNED FALSE POSITIVES (user corrected — these are NOT promises):\n" + "\n".join(lines) + "\n"


def _expire_old_promises(persona_manager: Any, user_id: Optional[str] = None) -> int:
    """Remove promises older than PROMISE_TTL_HOURS. Returns count of expired."""
    if not persona_manager:
        return 0
    cutoff = datetime.now() - timedelta(hours=PROMISE_TTL_HOURS)
    expired = []
    for name, p in list(persona_manager.promises.items()):
        if not p.fulfilled and not p.broken and p.made_at < cutoff:
            expired.append(name)
    for name in expired:
        del persona_manager.promises[name]
        log("PROMISE", f"⏰ Expired (>{PROMISE_TTL_HOURS}h): {name}", Fore.YELLOW)
        _append_promise_audit("EXPIRED", name, user_id=user_id or "", source="ttl")
    if expired:
        persona_manager._save_state()
    return len(expired)


# ==========================================
# PROMISE & EMOTION DETECTION
# ==========================================

_PROMISE_COMMITMENT_RE = re.compile(
    r"\b("
    r"i\s*(?:will|'ll)|we\s*(?:will|'ll)|i\s+promise|promise|"
    r"ich\s+werde|wir\s+werden|ich\s+verspreche|versprochen|"
    r"lass\s+uns|let'?s|"
    r"wir\s+gehen|wir\s+machen|wir\s+fahren|ich\s+(?:bring|hol|mach)|"
    r"we\s+(?:should|could|can)|i'?m\s+(?:gonna|going\s+to)"
    r")\b",
    re.IGNORECASE,
)

_PROMISE_ACTIVITY_RE = re.compile(
    r"\b(heute|morgen|später|spaeter|nachher|gleich|bald|"
    r"am\s+wochenende|tonight|tomorrow|later|soon|this\s+weekend)\b"
    r".{0,80}\b(spielen|zocken|schauen|gucken|anschauen|kochen|backen|bauen|basteln|"
    r"schwimmen|spazieren|besuchen|treffen|trinken|essen|holen|kaufen|machen|gehen|fahren|"
    r"play|watch|cook|build|make|swim|visit|meet|drink|eat|get|go|buy)\b",
    re.IGNORECASE,
)

_YOURAI_DIRECTIVE_RE = re.compile(
    r"\b("
    r"do you want|if you want|if u want|you have permission|go for it|"
    r"kannst du|willst du|du darfst|mach du|wenn du willst"
    r")\b",
    re.IGNORECASE,
)

_PROMISE_FULFILLED_RE = re.compile(
    r"\b("
    r"done|did|finished|completed|watched|played|drank|ate|cooked|built|made|got|bought|visited|swam|went|met|"
    r"fertig|gemacht|erledigt|geschaut|geguckt|angeschaut|gespielt|getrunken|gegessen|gekocht|gebaut|"
    r"geholt|gekauft|besucht|geschwommen|gegangen|gefahren|getroffen|waren?\s+(?:bei|im|am)"
    r")\b",
    re.IGNORECASE,
)

_GENERIC_PROMISE_WORDS = {
    "play", "watch", "do", "make", "something", "game", "drink", "eat", "get", "go",
    "cook", "build", "read", "write", "listen", "share", "together",
}


def _is_strong_user_promise(text: str) -> bool:
    """True only when the user clearly commits themselves/us to a real activity."""
    text_lower = text.lower()
    if _YOURAI_DIRECTIVE_RE.search(text_lower):
        return False
    if "?" in text and not _PROMISE_COMMITMENT_RE.search(text_lower):
        return False
    return bool(_PROMISE_COMMITMENT_RE.search(text_lower) or _PROMISE_ACTIVITY_RE.search(text_lower))


def _message_mentions_promise(promise_name: str, text: str) -> bool:
    """Avoid breaking the first active promise unless the message references it."""
    text_lower = text.lower()
    words = [
        w for w in promise_name.lower().replace("_", " ").split()
        if w not in _GENERIC_PROMISE_WORDS
    ]
    return any(w and w in text_lower for w in words)


def _message_fulfills_promise(promise_name: str, text: str) -> bool:
    """Detect simple user reports that an active promise was completed."""
    return bool(_PROMISE_FULFILLED_RE.search(text)) and _message_mentions_promise(promise_name, text)

def detect_promise_signals(text: str, user: str, persona_manager: Any, debug: Any = None) -> List[PromiseSignal]:
    """
    v3: Regex-based promise detection that returns signals and does not write state.

    Regex only detects:
    - FULFILLED (fast path, high confidence)
    - Apology, applied directly without a signal.

    Promise creation and breaking are handled only by the LLM path.
    """
    signals: List[PromiseSignal] = []

    if persona_manager is None:
        return signals

    pm = persona_manager
    text_lower = text.lower()

    # === PROMISE FULFILLMENT DETECTION (Regex Fast-Path) ===
    active_promises = [
        (name, p) for name, p in pm.promises.items()
        if not p.fulfilled and not p.broken
    ]
    for name, _ in active_promises:
        if _message_fulfills_promise(name, text):
            signals.append(PromiseSignal(
                action="FULFILLED",
                promise_name=name,
                source="regex",
                confidence="high",
                reasoning=f"Regex fulfillment match: {text[:60]}"
            ))
            log("PROMISE", f"🔍 [Signal] Regex FULFILLED: {name}", Fore.CYAN)
            break

    # === APOLOGY DETECTION (direct, no signal) ===
    _detect_apology(text_lower, pm)

    return signals


def detect_promises_and_emotions(text: str, user: str, persona_manager: Any, debug: Any = None) -> None:
    """Legacy wrapper — calls new signal system + resolve."""
    signals = detect_promise_signals(text, user, persona_manager, debug)
    if signals:
        resolve_promise_signals(signals, persona_manager, user_id=None, debug=debug)


def _extract_reason(text_lower: str) -> Optional[str]:
    """Extract the reason phrase from text."""
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
    """Detect apology wording and update persona mood if applicable."""
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
    Detect whether someone asks about old diary entries.
    
    Args:
        text: User input.
        
    Returns:
        (query_type, parameter) or (None, None).
        
        query_type can be:
        - "guardlog": Show guard log.
        - "list": List all weeks.
        - "week": Specific week (parameter = "last", "W03", etc.).
        - "search": Search history (parameter = search term).
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


def should_auto_search_diary(text: str) -> bool:
    """
    Returns True only when the user is actually asking YourAI to recall older
    conversation/diary context. This keeps slim sessions slim: greetings,
    affection, hugs, and current-state smalltalk must not trigger embedding
    search + rerank on every turn.
    """
    text_lower = (text or "").lower().strip()
    if not text_lower:
        return False

    query_type, _ = detect_diary_query(text_lower)
    if query_type:
        return True

    recall_patterns = [
        # English recall / past-context intent
        r"\b(?:do you|can you|could you)?\s*(?:remember|recall)\b",
        r"\b(?:remind me|what did (?:i|we|you) say|what were we talking about)\b",
        r"\b(?:did we|have we|did i|have i)\s+(?:talk|speak|discuss|mention|ask)\b",
        r"\b(?:last time|previously|earlier|before|back then|old chat|chat history)\b",
        r"\b(?:yesterday|last night|this morning|last week|last month|a while ago)\b",
        r"\b(?:diary|journal|log|memory|memories)\b",
        r"\b(?:when did|what happened).*(?:we|i|you)\b",

        # German recall / past-context intent
        r"\b(?:wei[sß]t du noch|erinnerst du dich|erinner dich|erinnern)\b",
        r"\b(?:was habe ich|was haben wir|worüber haben wir|woran haben wir)\b",
        r"\b(?:haben wir|habe ich).*(?:geredet|gesprochen|geschrieben|erwähnt|gefragt)\b",
        r"\b(?:letztens|vorhin|damals|früher|frueher|gestern|letzte nacht|heute morgen)\b",
        r"\b(?:tagebuch|verlauf|chatverlauf|alte chats?|log|logs|erinnerung|erinnerungen)\b",

        # Date-ish references
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}\.\d{1,2}\.?\b",
        r"\b(?:woche|week|kw)\s*\d{1,2}\b",
    ]

    return any(re.search(pattern, text_lower) for pattern in recall_patterns)


def load_diary_context_for_query(
    query_type: str, 
    parameter: Optional[str], 
    journal: Any,
    get_guard_log_func: Any = None
) -> str:
    """
    Load the matching diary context for the query.
    
    Args:
        query_type: "list", "week", "search", or "guardlog".
        parameter: Parameter for the query.
        journal: episodic.journal instance.
        get_guard_log_func: Function used to fetch the guard log.
        
    Returns:
        Formatted context string.
    """
    # === GUARDLOG COMMAND ===
    if query_type == "guardlog":
        if get_guard_log_func:
            return get_guard_log_func(last_n=MAX_GUARD_LOG_ENTRIES)
        return "Guard log is not available."
    
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
    """Format the list of available diary weeks."""
    rotations = journal.list_rotations()
    
    result = "📋 **YOUR DIARY OVERVIEW:**\n\n"
    result += f"**Current week:** {rotations['current_week']['week_id']} ({rotations['current_week']['entries']} entries)\n\n"
    
    if rotations['available_weeks']:
        result += "**Archivierte Wochen:**\n"
        for week in rotations['available_weeks']:
            result += f"- {week['week_id']}: {week['entries']} entries\n"
    else:
        result += "No archived weeks yet; no rotation has happened\n"
    
    result += f"\n**Backups:** {len(rotations['available_backups'])} vorhanden"
    result += f"\n**entries gesamt:** {rotations['total_entries_all_time']}"
    
    return result


def _format_week_entries(journal: Any, parameter: Optional[str]) -> str:
    """Format entries for a selected diary week."""
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
        result += f"- entries: {summary.get('total_entries', 0)}\n"
        tags = list(summary.get('tags_frequency', {}).keys())[:5]
        if tags:
            result += f"- Themen: {', '.join(tags)}\n"
    
    result += f"\n**entries:**\n{entries}"
    
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
    Parse formatted diary-search text into (content, full_text) tuples.

    Expected format:
        [Keyword: xyz]              <- skipped
        🔍 Found N entries for ...  <- skipped
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
        # Diary entry header: [anything] (anything)
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
    """Handle format diary entry helper behavior."""
    source = entry.get("_source", "unknown")
    content = _compact_diary_preview(entry.get("content", ""), max_chars=1200)
    return f"[{entry.get('date_readable', '?')}] ({source})\n  {content}"


def _compact_diary_preview(content: str, max_chars: int = 1200) -> str:
    """Prompt/RAG preview without importing episodic.py (it has import side effects)."""
    if not content or len(content) <= max_chars:
        return content or ""
    text = content.strip()
    if "ORIGINAL USER QUESTION:" in text:
        question = text.split("ORIGINAL USER QUESTION:")[-1].strip()
        text = "ORIGINAL USER QUESTION: " + question
        if len(text) <= max_chars:
            return text
    looks_like_code = text.count("```") >= 2 or any(marker in text for marker in (
        "Traceback (most recent call last)",
        "SyntaxError:",
        "TypeError:",
        "ReferenceError:",
        "def ",
        "class ",
        "function ",
        "import ",
        "const ",
    ))
    prefix = "[Code/Log preview] " if looks_like_code else ""
    marker = f"\n[... truncated: {len(text) - max_chars} characters ...]\n"
    available = max(120, max_chars - len(prefix) - len(marker))
    head_len = max(80, int(available * 0.62))
    tail_len = max(60, available - head_len)
    return prefix + text[:head_len].rstrip() + marker + text[-tail_len:].lstrip()


def _entry_rank_text(entry: dict) -> str:
    """Handle entry rank text helper behavior."""
    tags = ", ".join(entry.get("tags", []) or [])
    content = entry.get("content", "")
    date = entry.get("date_readable", "")
    return f"{date}\nTags: {tags}\n{content}"[:1200]


def _candidate_key(content: str) -> str:
    """Handle candidate key helper behavior."""
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

    # If the reranker is available, fetch more results and sort by relevance.
    _use_rerank = False
    try:
        from config import USE_RERANKER
        _use_rerank = USE_RERANKER
    except Exception:
        pass

    _per_keyword  = 6 if _use_rerank else 3   # Per keyword: 5 keywords x 6 = 30 candidates.
    _max_keywords = 5 if _use_rerank else 3   # More keywords widen the recall net.

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
        return ""  # Empty string instead of placeholder to save tokens.

    # RERANKER: Einzelne entries parsen und nach Relevanz zur Frage sortieren
    if _use_rerank:
        try:
            from tools.reranker import rerank_documents

            # Split all blocks into individual entries.
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
                
                # Use the configured limit instead of a hardcoded value.
                actual_limit = min(limit, len(docs))
                if _dbg:
                    _dbg.info(
                        "diary_rerank",
                        f"Calling reranker for {len(docs)} diary candidate(s)",
                        f"Query: {question[:160]}"
                    )
                ranked = rerank_documents(question, docs, top_n=actual_limit)

                if ranked:
                    for r in ranked:
                        sources = all_entries[r["index"]]["sources"]
                        if len(sources) > 1:
                            r["relevance_score"] = min(1.0, r["relevance_score"] + 0.08)
                    ranked.sort(key=lambda r: r["relevance_score"], reverse=True)
                    # Threshold: nur entries mit echter Relevanz behalten
                    ranked = [r for r in ranked if r["relevance_score"] >= 0.05]
                    if not ranked:
                        # Exact keyword matches are still useful recall anchors.
                        # Do not let a cautious reranker erase literal hits like "fanta".
                        exact_matches = []
                        for entry in all_entries:
                            content_lower = entry["content"].lower()
                            if any(keyword.lower() in content_lower for keyword in keywords):
                                exact_matches.append(entry["full"])
                        if exact_matches:
                            log("DIARY", f"⚠️ Reranker dropped all scores; keeping {len(exact_matches)} exact keyword hit(s)", Fore.YELLOW)
                            if _dbg:
                                _dbg.info(
                                    "diary_rerank",
                                    "Reranker dropped all scores; keeping exact keyword hits",
                                    f"Exact hits: {len(exact_matches)}"
                                )
                            return "\n---\n".join(exact_matches[:limit])
                        log("DIARY", "📭 Reranker: all scores below threshold -> no diary context", Fore.YELLOW)
                        if _dbg:
                            _dbg.info(
                                "diary_rerank",
                                "Reranker filtered all diary candidates below threshold",
                                f"Candidates: {len(all_entries)}"
                            )
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
                else:
                    log("DIARY", "⚠️ Reranker returned no result; using original order", Fore.YELLOW)
                    if _dbg:
                        _dbg.info(
                            "diary_rerank",
                            "Reranker returned no result; using original order",
                            f"Candidates: {len(all_entries)}"
                        )
            elif _dbg:
                _dbg.info(
                    "diary_rerank",
                    "Reranker skipped; not enough diary candidates",
                    f"Candidates: {len(all_entries)}"
                )
        except Exception as e:
            log("DIARY", f"⚠️ Reranker failed ({e}), using original order", Fore.YELLOW)
            if _dbg:
                _dbg.error("diary_rerank", f"Reranker failed: {e}")

    # Fallback: original order when reranker is unavailable or failed.
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

def llm_promise_signals(
    current_message: str,
    recent_history: List[str],
    persona_manager: Any,
    user_id: Optional[str] = None,
    llm_host: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    debug: Any = None
) -> Optional[PromiseSignal]:
    """
    Promise Check v3 — Signal-basiert, KEIN State-Write.

    Tier 1: OpenRouter (Phi 4)  → schnell
    Tier 2: Lokal (gemma3:4b)   → Fallback

    Returns:
        PromiseSignal or None on error/NONE
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
    if persona_manager and user_id and hasattr(persona_manager, 'user_context'):
        with persona_manager.user_context(user_id):
            promise_items = list(persona_manager.promises.items())
    elif persona_manager and hasattr(persona_manager, 'promises'):
        promise_items = list(persona_manager.promises.items())
    else:
        promise_items = []

    if promise_items:
        active = []
        for name, p in promise_items:
            if not p.fulfilled and not p.broken:
                active.append(f"- {name}: {p.description or name}")
                active_promise_names.add(name)
        if active:
            active_promises_text = "\n".join(active)

    learned_section = get_learned_negatives_for_prompt()
    user_prompt = PROMPT_PROMISE_CHECK.format(
        active_promises=active_promises_text,
        current_message=current_message
    ) + learned_section

    log("PROMISE", f"🔍 LLM Check: '{current_message[:60]}' | Active: {active_promise_names or 'none'}", Fore.CYAN)

    try:
        t0 = time.time()
        res = None
        used_model = "?"

        # TIER 1: OpenRouter
        if USE_OPENROUTER:
            try:
                used_model = OPENROUTER_MODEL_PROMISE
                res, _, _ = call_openrouter(
                    system_prompt="You are YourAI's strict Promise Tracker. Output JSON only.",
                    user_message=user_prompt,
                    model=OPENROUTER_MODEL_PROMISE,
                    temperature=0,
                    max_tokens=PROMISE_CHECK_MAX_TOKENS,
                )
                if not res or not res.strip():
                    raise YourAIEmptyResponseError(model=used_model, node="promise_check")
                ms = int((time.time() - t0) * 1000)
                log("PROMISE", f"☁️ LLM ({ms}ms, {used_model})", Fore.CYAN)
            except YourAIEmptyResponseError:
                res = None
            except Exception as e:
                log("PROMISE", f"☁️ {e} → Fallback lokal", Fore.YELLOW)
                res = None

        # TIER 2: Lokal
        if res is None:
            try:
                from langchain_ollama import ChatOllama
                from langchain_core.messages import HumanMessage
                t1 = time.time()
                used_model = model
                llm = ChatOllama(model=model, base_url=llm_host, temperature=0, num_predict=PROMISE_CHECK_MAX_TOKENS)
                res = str(llm.invoke([HumanMessage(content=user_prompt)]).content or "").strip()
                if not res:
                    raise YourAIEmptyResponseError(model=used_model, node="promise_check")
                ms = int((time.time() - t1) * 1000)
                log("PROMISE", f"🖥️ LLM ({ms}ms, {used_model})", Fore.CYAN)
            except YourAIEmptyResponseError:
                raise
            except Exception as e:
                log("PROMISE", f"🖥️ Lokal fehlgeschlagen: {e}", Fore.RED)
                return None

        total_ms = int((time.time() - t0) * 1000)

        # --- JSON parsen ---
        json_data = _extract_json(res)
        if json_data is None:
            err = YourAILLMParseError(
                model=used_model, expected="JSON with 'action' key",
                raw_preview=res[:200], module="promise_check",
            )
            log_exception("PROMISE", err)
            return None

        action = (json_data.get("action") or "NONE").upper().strip()
        promise_name = json_data.get("promise", "none")
        reason_text = json_data.get("reason", "none")
        reason_quality = (json_data.get("reason_quality") or "NONE").upper().strip()
        reasoning = json_data.get("reasoning", "")

        # --- NONE ---
        if action == "NONE":
            log("PROMISE", f"✅ NONE ({total_ms}ms)", Fore.GREEN)
            return None

        # --- Halluzinations-Schutz ---
        if not active_promise_names and action in ("BROKEN", "FULFILLED"):
            log("PROMISE", f"⚠️ LLM hallucinated '{action}' — no active promises!", Fore.YELLOW)
            return None

        # --- MADE: nur technische Halluzinationen blocken, Rest entscheidet User ---
        if action == "MADE":
            name_words = set(promise_name.lower().replace("_", " ").split())
            if name_words.issubset(_JUNK_PROMISE_WORDS):
                log("PROMISE", f"⚠️ Junk-Promise ignoriert: '{promise_name}'", Fore.YELLOW)
                return None

        # --- BROKEN: Validierung ---
        if action == "BROKEN":
            if promise_name in ("none", "generic_promise", "previous_activity"):
                log("PROMISE", f"⚠️ Vager Break ignoriert: '{promise_name}'", Fore.YELLOW)
                return None
            if promise_name not in active_promise_names:
                log("PROMISE", f"⚠️ '{promise_name}' not active - ignored", Fore.YELLOW)
                return None
            if not reason_text or reason_text == "none":
                reason_text = current_message[:80] if len(current_message) > 5 else None

        signal = PromiseSignal(
            action=action,
            promise_name=promise_name,
            reason=reason_text if reason_text != "none" else None,
            reason_quality=reason_quality,
            source="llm",
            confidence="high",
            reasoning=reasoning,
            original_message=current_message[:200],
        )

        log("PROMISE", f"🔍 [Signal] LLM {action}: {promise_name} ({total_ms}ms)", Fore.CYAN)
        return signal

    except YourAIEmptyResponseError as e:
        log_exception("PROMISE", e)
        return None
    except Exception as e:
        err = YourAILLMError("Promise check failed", model=used_model if 'used_model' in dir() else "?", module="promise_check", cause=e)
        log_exception("PROMISE", err)
        return None


def llm_promise_check(
    current_message: str, recent_history: List[str], persona_manager: Any,
    user_id: Optional[str] = None, llm_host: Optional[str] = None,
    model: Optional[str] = None, timeout: Optional[float] = None, debug: Any = None
) -> Optional[Dict]:
    """Legacy wrapper — ruft llm_promise_signals() + resolve auf."""
    signal = llm_promise_signals(
        current_message, recent_history, persona_manager,
        user_id, llm_host, model, timeout, debug
    )
    if signal and signal.is_actionable:
        if persona_manager and user_id and hasattr(persona_manager, 'user_context'):
            with persona_manager.user_context(user_id):
                resolve_promise_signals([signal], persona_manager, user_id, debug)
        elif persona_manager:
            resolve_promise_signals([signal], persona_manager, user_id, debug)
        return {"action": signal.action, "promise": signal.promise_name,
                "reason": signal.reason, "reason_quality": signal.reason_quality}
    return {"action": "NONE", "promise": "none", "reason": "none", "reason_quality": "NONE"}


# ==========================================
# CENTRAL PROMISE RESOLVER (v3)
# ==========================================

_JUNK_PROMISE_WORDS = {
    "dm", "test", "fix", "bug", "code", "error", "debug",
    "api", "server", "bot", "config", "update", "deploy",
    "commit", "push", "pull", "merge", "build", "run",
    "check", "log", "send", "message", "chat", "system",
    "prompt", "model", "token", "response", "request",
    "generic_promise", "previous_activity", "activity", "none",
}

_REAL_PROMISE_ACTION_WORDS = {
    "play", "watch", "cook", "build", "make", "go", "get",
    "eat", "drink", "read", "write", "listen", "share",
}


def resolve_promise_signals(
    signals: List[PromiseSignal],
    persona_manager: Any,
    user_id: Optional[str] = None,
    debug: Any = None
) -> Optional[Dict]:
    """
    v3: EINZIGER Punkt der Promise-State aendert.

    Nimmt Signals von Regex und/oder LLM, entscheidet was passiert.
    Regeln:
    - FULFILLED: Regex oder LLM reicht (hohe Konfidenz)
    - MADE: LLM only; regex no longer creates promises.
    - BROKEN: LLM only; regex no longer detects breaks.
    - TTL: expired promises are removed first.
    """
    if not persona_manager or not signals:
        return None

    pm = persona_manager

    # --- TTL: Alte Promises aufraeumen ---
    _expire_old_promises(pm, user_id)

    # --- Aktive Promises ermitteln ---
    active_names = {
        name for name, p in pm.promises.items()
        if not p.fulfilled and not p.broken
    }

    result = None

    for signal in signals:
        if not signal.is_actionable:
            continue

        if signal.action == "FULFILLED":
            name = signal.promise_name
            # Exakter Match
            if pm.promises.get(name) and not pm.promises[name].fulfilled:
                pm.fulfill_promise(name)
                log("PROMISE", f"🎉 Fulfilled: {name} (via {signal.source})", Fore.GREEN)
                _append_promise_audit("FULFILLED", name, user_id=user_id or "", source=signal.source)
                if debug and hasattr(debug, 'promise_event'):
                    debug.promise_event("fulfilled", name, details=f"source: {signal.source}")
                result = {"action": "FULFILLED", "promise": name}
                break

            # Fuzzy Match
            for active_name in active_names:
                if (name in active_name or active_name in name or
                        name.replace("_", " ") in active_name.replace("_", " ")):
                    pm.fulfill_promise(active_name)
                    log("PROMISE", f"🎉 Fulfilled (fuzzy): {active_name} (via {signal.source})", Fore.GREEN)
                    _append_promise_audit("FULFILLED", active_name, user_id=user_id or "", source=signal.source, details={"matched": name})
                    if debug and hasattr(debug, 'promise_event'):
                        debug.promise_event("fulfilled", active_name, details=f"fuzzy: '{name}'")
                    result = {"action": "FULFILLED", "promise": active_name}
                    break
            if result:
                break

        elif signal.action == "MADE" and signal.source == "llm":
            pm.make_promise(signal.promise_name)
            log("PROMISE", f"🤝 Made: {signal.promise_name} (via LLM)", Fore.GREEN)
            _append_promise_audit("MADE", signal.promise_name, user_id=user_id or "", source=signal.source, details={"reasoning": signal.reasoning[:200]})
            if debug and hasattr(debug, 'promise_event'):
                debug.promise_event("made", signal.promise_name, details=signal.reasoning[:80])
            result = {"action": "MADE", "promise": signal.promise_name}
            break

        elif signal.action == "BROKEN" and signal.source == "llm":
            pm.break_promise(signal.promise_name, reason=signal.reason)
            log("PROMISE", f"💔 Broken: {signal.promise_name} (via LLM)", Fore.RED)
            _append_promise_audit("BROKEN", signal.promise_name, user_id=user_id or "", source=signal.source, details={"reason": signal.reason})
            if debug and hasattr(debug, 'promise_event'):
                debug.promise_event("broken", signal.promise_name, reason=signal.reason)
            result = {"action": "BROKEN", "promise": signal.promise_name, "reason": signal.reason}
            break

    return result
