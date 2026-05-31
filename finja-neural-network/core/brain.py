"""
YourAI Brain Runtime
===================
Central graph orchestration for YourAI's conversational pipeline.

Main Responsibilities:
- Coordinate memory loading, safety checks, routing, expert calls, tools, and final response generation.
- Maintain workflow state for console, web, Discord, Twitch, and linked-user sessions.
- Integrate optional subsystems such as voice, vision, dashboard telemetry, Spotify, Paperless, and Home Assistant.

Side Effects:
- Imports and initializes optional runtime clients based on feature flags.
- Calls local and remote LLM providers, tool backends, memory stores, and dashboard telemetry.
- Reads and writes persistent runtime files such as output logs, uploaded attachments, and session state.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

# ==========================================
# MODULARE IMPORTS
# ==========================================
import re
import time
import json
import threading
from datetime import datetime as _dt
from typing import TypedDict, Optional, cast, List, Any, Dict
from concurrent.futures import ThreadPoolExecutor
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from tools.tool_router import should_use_tool, execute_tool, USE_TOOLS
from tools.website import generate_quote_prompt

from text_parser import (
    extract_thoughts, extract_json_from_text,
    extract_expert_search_command,
    build_writing_search_query, build_nutrition_search_query,
    build_mechanic_search_query, build_history_search_query, build_law_search_query,
    compact_json_response,
    extract_music_title_artist, music_asks_current_track, build_music_search_query,
)
from spotify_context import (
    get_music_brain_song_features, get_music_brain_expert_data,
    get_spotify_current_track_data, music_fact_from_brain,
)

from prompts import (
    PROMPT_ROUTER_SYSTEM, PROMPT_YOURAI_TEMPLATE,
    PROMPT_BIO, PROMPT_MATH, PROMPT_PHYSICS, PROMPT_CHEMISTRY,
    PROMPT_CODE, PROMPT_MED, PROMPT_BAKING, PROMPT_GAMING,
    PROMPT_ANIME, PROMPT_FOX_PHILOSOPHY, PROMPT_PSYCHOLOGY, PROMPT_WRITING,
    PROMPT_SOCIAL_MEDIA, PROMPT_HOMELAB, PROMPT_NUTRITION, PROMPT_MUSIC,
    PROMPT_MYTHOLOGY, PROMPT_PETS, PROMPT_PLANTS, PROMPT_FINANCE_BASIC,
    PROMPT_LAW_RESEARCH, PROMPT_MECHANIC, PROMPT_GEO, PROMPT_HISTORY,
    DISCORD_DM_SECTION_CHANNEL, DISCORD_DM_SECTION_DM, DISCORD_DM_SECTION_NONE,
    DISCORD_PRIVATE_SECTION,
    SECTION_IMAGE_GEN,
    SECTION_SPOTIFY, SECTION_FILE_BRAIN, SECTION_WEB_SEARCH, SECTION_PAPERLESS,
    SECTION_HOME_ASSISTANT, SECTION_ALTPERSONA_CONSULT, SECTION_WEBSITE, SECTION_DEBUG_TOOLS,
)

import config as _cfg  # Für hot-reload Zugriff
from prompt_router import classify_sync as _route_classify
from config import (
    LLM_HOST_STD, LLM_HOST_MAIN,
    USE_MEMORY, USE_VISION, USE_VOICE, USE_EPISODIC, USE_TWITCH, USE_DISCORD, USE_SPOTIFY, USE_WEB_SEARCH, USE_PAPERLESS, USE_HOME_ASSISTANT, USE_IMAGE_GEN, USE_PROMPT_ROUTER,
    IMAGE_MODEL, IMAGE_MODELS,
    DISCORD_VIP_CHANNEL_ID, DISCORD_CUSTOM_EMOJIS,
    USE_THINKING, USE_COHERENCE_CHECK,
    USE_GRANITE,
    MODEL_ROUTER, MODEL_PROMISE_CHECK, PROMISE_CHECK_TIMEOUT,
    YOURAI_OUTPUT_FILE, YOURAI_OUTPUT_MAX_BYTES,
    MODEL_YOURAI_OPENROUTER, MODEL_YOURAI_LOCAL_PRIMARY, MODEL_YOURAI_LOCAL_FALLBACK,
    USE_STREAMING, VISION_MODEL,
    EXPERT_MODELS,
    create_thinking_llm, maybe_add_think_prompt,
    call_openrouter, call_openrouter_stream, get_expert_openrouter_model,
    reload_runtime_flags
)

from display import log, log_exception, show_llm, Fore, Style
from error_inbox import format_error_records, pop_unseen_errors
from tool_callbacks import (
    _build_spotify_callback, _build_file_callback, _build_web_callback,
    _build_docs_callback, _build_home_callback, _build_image_callback,
    _build_sticker_callback, _build_dm_callback,
)
from streaming import (
    _fire_tool_thread, _dispatch_single_tags_stream, _dispatch_dm_tags_stream,
    _run_streaming_yourai,
)

from exceptions import (
    YourAIUnexpectedError, YourAIPipelineError,
    YourAILLMError, YourAIAllTiersFailedError, YourAIToolError,
    YourAINoPrivilegeError, YourAIToolExecutionError, YourAIVisionError,
    YourAIUploadError
)

from detection import (
    detect_promise_signals,
    llm_promise_signals,
    resolve_promise_signals,
    detect_diary_query,
    load_diary_context_for_query,
    auto_search_diary,
    should_auto_search_diary,
    # Legacy (nicht mehr direkt genutzt):
    detect_promises_and_emotions,
    llm_promise_check
)

from autonomy_guard import (
    coherence_check_node as _coherence_check_node,
    get_guard_log
)

from safety import granite_guardian_node, password_scanner_node
from altpersona import altpersona_brat_node, altpersona_uncensored_node

# Backward compatibility: DISCORD_DM_WHITELIST is built from platform_links.json.
# Wird einmal beim Start geladen — Neustart nötig wenn neue Links hinzukommen.
def _build_discord_dm_whitelist() -> dict:
    """
    Builds the Discord DM whitelist from platform link metadata.

    Returns:
        dict: Mapping of Discord user IDs to linked YourAI user keys.
    """
    try:
        from helpers.platform_links import _load as _pl_load
        data = _pl_load()
        return {
            did: ukey
            for ukey, info in data.items()
            if info.get("dm_allowed")
            for did in info.get("discord_ids", [])
        }
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="brain_dm_whitelist")
        log_exception("BRAIN", err)
        return {}

DISCORD_DM_WHITELIST: dict = _build_discord_dm_whitelist()

# ==========================================
# EXTERNAL MODULES
# ==========================================

# Load voice modules only when USE_VOICE is active to save memory.
if USE_VOICE:
    import ears
    import mouth
else:
    ears = None
    mouth = None
    print(f"{Fore.YELLOW}Voice disabled (USE_VOICE=False); Whisper will not be loaded.{Style.RESET_ALL}")

# eyes immer laden — see_url() (Discord/Web) braucht kein Desktop
# USE_VISION only controls the screenshot node.
import eyes
if not USE_VISION:
    print(f"{Fore.YELLOW}Screenshot vision disabled (USE_VISION=False); URL vision remains active.{Style.RESET_ALL}")

# Load Twitch only when USE_TWITCH is active.
if USE_TWITCH:
    import twitch_client
else:
    twitch_client = None

# Load Discord only when USE_DISCORD is active.
if USE_DISCORD:
    import discord_client
else:
    discord_client = None

# These modules are always required.
import hippocampus
import episodic
import personas
from helpers.style_analyzer import (
    track_message as _track_style,
    get_style_context as _get_style_ctx,
    merge_style_profile as _merge_style_profile,
)

# Session manager for source-specific user switching.
from session import session_manager

def _state_session_id(state: dict) -> str:
    """Stable per-session key for prompt feedback, token accounting and tool results."""
    return state.get("token_session_id") or state.get("session_uuid") or state.get("user_id") or "system"


def _store_session_feedback(session_id: str, key: str, value: str) -> None:
    """Store a tool result for exactly one session's next prompt injection."""
    if value:
        session_manager.set_state(session_id, key, value)

def _extract_doc_chapters(meta_path: str) -> list[str]:
    """Helper to extract unique chapter names from document metadata."""
    try:
        import json as _json
        import re as _re
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = _json.load(f)
        seen = set()
        chapter_names = []
        for c in meta.get("chunk_list", []):
            base = _re.sub(r'\s*\(Teil\s*\d+\)', '', c["title"]).strip()
            if base not in seen:
                seen.add(base)
                chapter_names.append(base)
        return chapter_names
    except Exception:
        return []


def _get_file_documents_list(user_id: Optional[str] = None) -> str:
    """
    Builds the visible File Brain document list with chapter summaries for prompt context.

    Args:
        user_id (Optional[str]): User ID used to filter visible documents.

    Returns:
        str: Prompt-ready document list, or a fallback status string.
    """
    try:
        import os as _os
        from tools.file_brain import get_file_brain, DOCUMENTS_DIR
        fb = get_file_brain()
        visible_docs = fb._visible_documents(user_id)
        if not visible_docs:
            return "(No documents available)"
        lines = []
        for name, info in visible_docs.items():
            lines.append(f"- \"{name}\" ({info['chunks']} chunks, {info['words']} words, {info['type']})")
            # List chapter names from _meta.json.
            meta_path = _os.path.join(DOCUMENTS_DIR, name, "_meta.json")
            if _os.path.exists(meta_path):
                chapter_names = _extract_doc_chapters(meta_path)
                if chapter_names:
                    lines.append(f"  Chapters: {', '.join(chapter_names[:20])}")
                    if len(chapter_names) > 20:
                        lines.append(f"  ...and {len(chapter_names) - 20} more")
        return "\n".join(lines)
    except Exception as e:
        log("FILE_BRAIN", f"⚠️ Error generating doc list: {e}", Fore.YELLOW)
        return "(File Brain not available)"

_INLINE_TEXT_ATTACHMENT_RE = re.compile(
    r"```(?P<ext>[A-Za-z0-9_+\-.]*)\s*\r?\n//\s*(?P<name>[^\r\n]+)\r?\n(?P<data>.*?)\r?\n```",
    re.DOTALL,
)


def _looks_like_file_brain_request(text: str) -> bool:
    """Detect user requests that should stay with File Brain instead of the writing expert."""
    if not text:
        return False
    lower = text.lower()
    if "[file:" in lower or "file brain" in lower or "[attached text file" in lower:
        return True

    target_words = (
        "kapitel", "chapter", "dokument", "document", "datei", "file",
        "buch", "book", "textinhalt", "anhang", "attachment",
    )
    action_words = (
        "lies", "lese", "lesen", "vorlesen", "read", "oeffne", "offne",
        "öffne", "zeige", "zeig", "show", "was steht", "what is in",
        "what's in", "inhalt", "suche", "such", "search", "find",
        "liste", "list", "chapters", "kapitelübersicht", "kapiteluebersicht",
    )

    has_target = any(word in lower for word in target_words)
    has_action = any(word in lower for word in action_words)
    has_numbered_chapter = re.search(r"\b(?:kapitel|chapter)\s*\d+[a-z]?\b", lower) is not None
    return (has_target and has_action) or (has_numbered_chapter and has_action)


def _safe_attachment_filename(name: str, fallback: str = "upload.txt") -> str:
    """
    Sanitizes an uploaded attachment filename for safe local storage.

    Args:
        name (str): Original filename or path-like value.
        fallback (str): Filename to use when the original value is empty after sanitization.

    Returns:
        str: Safe filename bounded to a manageable length.
    """
    clean = os.path.basename((name or fallback).replace("\\", "/")).strip()
    clean = re.sub(r"[^\w.\- ()]+", "_", clean, flags=re.UNICODE)
    clean = clean.strip(" .")[:140]
    return clean or fallback


def _extract_inline_text_attachments(text: str) -> tuple[str, list[dict]]:
    """Back-compat for old dashboard JS that pasted text files as fenced code blocks."""
    if not text or "```" not in text:
        return text, []

    attachments: list[dict] = []

    def _replace(match: re.Match) -> str:
        """
        Converts one legacy fenced attachment block into a prompt marker.

        Args:
            match (re.Match): Regex match containing the filename and text payload.

        Returns:
            str: Replacement marker or original block when no attachment data exists.
        """
        filename = _safe_attachment_filename(match.group("name") or "upload.txt")
        data = match.group("data") or ""
        if not data.strip():
            return match.group(0)
        attachments.append({"name": filename, "data": data})
        return f"[Attached text file: {filename}]"

    cleaned = _INLINE_TEXT_ATTACHMENT_RE.sub(_replace, text)
    return cleaned, attachments


def _ingest_single_attachment(fb: Any, incoming_dir: str, attachment: dict, idx: int, owner_user_id: Optional[str]) -> str | None:
    """Helper to process and ingest a single text attachment."""
    from tools.file_brain_chunking import sanitize_name
    filename = _safe_attachment_filename(
        attachment.get("name") if isinstance(attachment, dict) else "",
        fallback=f"upload_{idx}.txt",
    )
    try:
        data = attachment.get("data", "") if isinstance(attachment, dict) else ""
        if not isinstance(data, str) or not data.strip():
            return None

        base, ext = os.path.splitext(filename)
        ext = ext if ext and len(ext) <= 12 else ".txt"
        doc_name = sanitize_name(base or f"upload_{idx}")
        stored_path = os.path.join(incoming_dir, f"{doc_name}{ext.lower()}")
        with open(stored_path, "w", encoding="utf-8", newline="") as f:
            f.write(data)

        result = fb.ingest(stored_path, doc_name=doc_name, owner_user_id=owner_user_id)
        if result.get("success"):
            actual_name = result.get("doc_name", doc_name)
            return f"- \"{actual_name}\" from {filename}: {result.get('chunks', '?')} chunks, {result.get('total_words', '?')} words"
        else:
            return f"- {filename}: ingest failed - {result.get('error', 'unknown error')}"
    except Exception as e:
        err = YourAIUploadError("text attachment ingest failed", filename=filename, cause=e, module="file_brain_upload")
        log_exception("FILE_BRAIN", err)
        return f"- {filename}: {err.short()}"


def _ingest_text_attachments(text_attachments: Optional[list], owner_user_id: Optional[str] = None) -> str:
    """Persist dashboard text attachments into File Brain and return compact prompt context."""
    if not text_attachments:
        return ""

    try:
        from tools.file_brain import get_file_brain, DOCUMENTS_DIR
    except Exception as e:
        err = YourAIUploadError("file brain import failed", cause=e, module="file_brain_upload")
        log_exception("FILE_BRAIN", err)
        return f"\n## FILE ATTACHMENT ERROR\n{err.short()}"

    fb = get_file_brain()
    incoming_dir = os.path.join(DOCUMENTS_DIR, "_incoming_uploads")
    os.makedirs(incoming_dir, exist_ok=True)

    lines: list[str] = []
    for idx, attachment in enumerate(text_attachments[:8], start=1):
        line = _ingest_single_attachment(fb, incoming_dir, attachment, idx, owner_user_id)
        if line:
            lines.append(line)

    if not lines:
        return ""

    return (
        "\n## ATTACHED FILES INGESTED\n"
        f"The current user ({owner_user_id or 'admin'}) attached text files. They are now saved in that user's File Brain; the raw file content was NOT pasted into this prompt.\n"
        + "\n".join(lines)
        + "\nUse the exact document names above with [FILE:list DocName] or [FILE:read DocName/Kapitel 2]. "
        "Do not ask for an OS path for these attachments."
    )


def _latest_file_doc_name(fb: Any, user_id: Optional[str] = None) -> Optional[str]:
    """
    Finds the most recently ingested visible File Brain document.

    Args:
        fb (Any): File Brain instance.
        user_id (Optional[str]): User ID used to filter visible documents.

    Returns:
        Optional[str]: Latest document name, or None when no documents are visible.
    """
    docs = fb._visible_documents(user_id)
    if not docs:
        return None
    return max(docs.items(), key=lambda item: item[1].get("ingested_at", ""))[0]


def _normalize_doc_hint(value: str) -> str:
    """
    Normalizes a loose document hint for fuzzy matching against File Brain document names.

    Args:
        value (str): Raw document hint from the user message.

    Returns:
        str: Lowercase normalized hint.
    """
    hint = (value or "").lower()
    hint = re.sub(r"\.(?:md|txt|text|html?|csv|json|log|docx?)\b", " ", hint)
    hint = re.sub(r"[_\-]+", " ", hint)
    hint = re.sub(r"[^\w\s]+", " ", hint, flags=re.UNICODE)
    hint = re.sub(r"\s+", " ", hint).strip()
    return hint


def _extract_requested_file_doc_hint(question: str) -> Optional[str]:
    """
    Extracts a likely document name hint from a user question.

    Args:
        question (str): User question text.

    Returns:
        Optional[str]: Normalized document hint, or None if no hint is found.
    """
    lower = (question or "").lower()

    file_match = re.search(r"\b([\w .\-()]+?\.(?:md|txt|text|html?|csv|json|log))\b", lower, re.UNICODE)
    if file_match:
        hint = _normalize_doc_hint(file_match.group(1))
        if hint:
            return hint

    for pattern in (
        r"\b(?:of|off|from|von|aus)\s+([a-z0-9_ .\-]{3,80})",
        r"\b(?:datei|file|dokument|document)\s+([a-z0-9_ .\-]{3,80})",
    ):
        match = re.search(pattern, lower, re.IGNORECASE)
        if not match:
            continue
        raw = re.split(r"[:;!?()\n\r]|\s+(?:please|bitte|try|lies|read|chapter|kapitel)\b", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        hint = _normalize_doc_hint(raw)
        if hint and hint not in {"meinem", "meiner", "my", "the", "dem", "der", "das"}:
            return hint

    if re.search(r"\bblaues?[\s_\-]+gift\b", lower, re.IGNORECASE):
        return "blaues gift"
    return None


def _choose_file_doc_for_question(question: str, fb: Any, user_id: Optional[str] = None) -> Optional[str]:
    """
    Chooses the best File Brain document for a user question.

    Args:
        question (str): User question text.
        fb (Any): File Brain instance.
        user_id (Optional[str]): User ID used to filter visible documents.

    Returns:
        Optional[str]: Matching document name, or None when the target is ambiguous.
    """
    docs = list(fb._visible_documents(user_id).keys())
    if not docs:
        return None

    lower = (question or "").lower()
    requested_hint = _extract_requested_file_doc_hint(question)
    for name in sorted(docs, key=len, reverse=True):
        name_lower = name.lower()
        normalized_name = _normalize_doc_hint(name)
        if name_lower in lower or name_lower.replace("_", " ") in lower:
            return name
        if requested_hint and (requested_hint in normalized_name or normalized_name in requested_hint):
            return name

    if requested_hint:
        return None

    if len(docs) == 1:
        return docs[0]

    if any(word in lower for word in ("dieses", "diese", "das", "it", "the file", "anhang", "attached", "hochgeladen")):
        return _latest_file_doc_name(fb, user_id=user_id)

    return None


def _extract_file_chapter_query(question: str) -> Optional[str]:
    """
    Extracts a chapter query from a File Brain user request.

    Args:
        question (str): User question text.

    Returns:
        Optional[str]: Chapter query label, or None when no chapter is requested.
    """
    lower = (question or "").lower()
    match = re.search(r"\b(?:kapitel|chapter)\s*(\d+[a-z]?)\b", lower)
    if match:
        return f"Kapitel {match.group(1)}"

    specials = {
        "intro": "Intro",
        "cover": "Cover",
        "vorwort": "Vorwort",
        "nachwort": "Nachwort",
        "epilog": "Epilog",
        "epilogue": "Epilog",
        "backcover": "Backcover",
    }
    for key, label in specials.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            return label
    return None


def _execute_file_brain_action(
    fb: Any, question: str, doc_name: Optional[str], chapter_query: Optional[str],
    wants_search: bool, wants_list: bool, user_id: Optional[str]
) -> tuple[str, dict | None]:
    """Helper to execute the resolved action against the File Brain catalog."""
    result = None
    action = ""
    if wants_search and not chapter_query:
        query = re.sub(
            r"\b(kannst du|bitte|please|suche|such|search|finde|find|in|meinem|meiner|my|dokument|document|datei|file|buch|book)\b",
            " ",
            question,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"\s+", " ", query).strip(" ?!.")
        result = fb.search(query or question, doc_filter=doc_name, owner_user_id=user_id)
        action = "search"
    elif wants_list or (doc_name and not chapter_query):
        result = fb.list_doc(doc_name, owner_user_id=user_id) if doc_name else fb.list_all(owner_user_id=user_id)
        action = "list"
    elif doc_name and chapter_query:
        result = fb.read(f"{doc_name}/{chapter_query}", owner_user_id=user_id)
        action = "read"
    return action, result


def _build_file_brain_direct_context(question: str, user_id: Optional[str] = None) -> str:
    """Read/list File Brain content before YourAI answers, when the request is explicit."""
    if not _looks_like_file_brain_request(question):
        return ""

    try:
        from tools.file_brain import get_file_brain
        fb = get_file_brain()
        docs = fb._visible_documents(user_id)
        if not docs:
            return "\n## FILE BRAIN\nNo documents are loaded in File Brain yet."

        lower = (question or "").lower()
        doc_name = _choose_file_doc_for_question(question, fb, user_id=user_id)
        requested_hint = _extract_requested_file_doc_hint(question)
        doc_list = ", ".join(f'"{name}"' for name in docs.keys())

        if requested_hint and not doc_name:
            return (
                "\n## FILE BRAIN\n"
                f'The user asks for document "{requested_hint}", but that document is not loaded for the current user in File Brain.\n'
                f"Available documents: {doc_list}.\n"
                "Do NOT read or search a different document as a fallback. Tell the user this attachment needs to be uploaded/ingested again."
            )

        if re.search(r"\b(?:buch|book)\s*2\b", lower):
            has_book2_match = any(
                ("2" in name or "blau" in name.lower() or "gift" in name.lower())
                for name in docs.keys()
            )
            if not has_book2_match:
                return (
                    "\n## FILE BRAIN\n"
                    "The user asks about Book 2, but no obvious Book 2 document is loaded in File Brain.\n"
                    f"Available documents: {doc_list}.\n"
                    "Tell the user the attachment needs to be uploaded/ingested again."
                )

        chapter_query = _extract_file_chapter_query(question)
        wants_list = any(word in lower for word in ("liste", "list", "übersicht", "uebersicht", "kapitelübersicht", "kapiteluebersicht", "chapters"))
        wants_search = any(word in lower for word in ("suche", "such", "search", "finde", "find "))
        if re.search(r"\bfind\s+(?:it\s+)?out\b", lower):
            wants_search = False

        action, result = _execute_file_brain_action(
            fb, question, doc_name, chapter_query, wants_search, wants_list, user_id
        )

        if not result:
            return ""

        if result.get("content"):
            content = result["content"][:10000]
            return (
                "\n## FILE BRAIN PRE-READ\n"
                f"Action: {action}\n"
                f"{result.get('message', 'Read done')}\n\n"
                "You already have the REAL file content below. Answer from it now; do NOT ask for a path and do NOT use [FILE:read] for the same chapter again.\n\n"
                f"CONTENT:\n{content}"
            )

        return (
            "\n## FILE BRAIN RESULT\n"
            f"Action: {action}\n"
            f"{result.get('message', result.get('error', 'File Brain finished'))}\n"
            "Use this real File Brain result. Do not make up document content."
        )
    except Exception as e:
        err = YourAIToolExecutionError("file_brain_direct", cause=e, module="file_brain")
        log_exception("FILE_BRAIN", err)
        return f"\n## FILE BRAIN ERROR\n{err.short()}"


# ==========================================
# DASHBOARD CLIENT
# ==========================================

try:
    from dashboard_client import debug
    DASHBOARD_ENABLED = True
    print(f"{Fore.GREEN}Dashboard client loaded. Open http://localhost:8050{Style.RESET_ALL}")
except ImportError:
    class DummyDebug:
        """No-op dashboard client used when dashboard_client.py is unavailable."""
        def __getattr__(self, name):
            """
            Returns a no-op callable for any dashboard method name.

            Args:
                name: Requested dashboard method name.

            Returns:
                Callable: No-op function accepting any arguments.
            """
            return lambda *args, **kwargs: None
        def get_web_input(self):
            """
            Returns no pending dashboard input for the no-op dashboard client.

            Returns:
                None.
            """
            return None
    debug = DummyDebug()
    DASHBOARD_ENABLED = False
    print(f"{Fore.YELLOW}Dashboard inactive; dashboard_client.py was not found.{Style.RESET_ALL}")


# ==========================================
# STATE DEFINITION
# ==========================================

class AgentState(TypedDict):
    """
    Typed graph state passed between YourAI brain workflow nodes.
    """
    question: str
    user_name: str
    source: str
    history: List[str]
    memories: List[str]
    diary_context: Optional[str]
    diary_search_results: Optional[str]
    week_summary: Optional[str]
    emotional_context: Optional[str]
    visual_context: Optional[str]
    safety_label: Optional[str]
    password_status: Optional[str]
    expert_domain: Optional[str]
    expert_fact: Optional[str]
    expert_model_used: Optional[str]
    final_response: Optional[str]
    current_mood: Optional[str]
    used_model: Optional[str]
    vision_done: bool
    coherence_warning: Optional[str]
    guard_halted: bool
    tool_name: Optional[str]
    tool_info: Optional[Dict]
    tool_result: Optional[Dict]
    guest_context: Optional[str]
    altpersona_mode: bool
    error_context: Optional[str]
    spotify_context: Optional[str]
    file_context: Optional[str]
    web_context: Optional[str]
    docs_context: Optional[str]
    home_context: Optional[str]
    altpersona_context: Optional[str]
    user_id: Optional[str]
    channel_id: Optional[int]
    image_urls: Optional[list]
    session_uuid: Optional[str]
    token_session_id: Optional[str]


# ==========================================
# THREAD-SAFE GLOBALS
# ==========================================

LAST_SEEN_CONTEXT = ""
_VISION_LOCK = threading.Lock()

# Reusable ThreadPoolExecutor for promise checks to avoid thread leaks.
_PROMISE_CHECK_EXECUTOR = None

# ==========================================
# YOURAI OUTPUT LOG
# ==========================================
import time as _time

_BRAIN_ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAT_LOG_FILE  = os.path.join(_BRAIN_ROOT, "docker_data", "app_chat_log.jsonl")
_FCM_TOKENS_FILE = os.path.join(_BRAIN_ROOT, "docker_data", "fcm_tokens.json")


def _append_chat_log(user_id: str, source: str, user_msg: str, yourai_msg: str, tracking_id: str = "") -> None:
    """Write a clean {user, yourai} message pair to app_chat_log.jsonl (persisted in docker_data)."""
    try:
        os.makedirs(os.path.dirname(_CHAT_LOG_FILE), exist_ok=True)
        entry = {
            "ts":          _dt.now().isoformat(timespec="seconds"),
            "user_id":     user_id,
            "source":      source,
            "user_msg":    user_msg,
            "yourai_msg":   yourai_msg,
            "tracking_id": tracking_id or "",
        }
        with open(_CHAT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never crash because of logging


def _get_unseen_error_context_for_yourai(user_id: str, max_errors: int = 5) -> str:
    """Pull unseen errors once from the persistent Error Inbox."""
    is_admin = user_id == "admin"
    try:
        records = pop_unseen_errors(
            max_items=max_errors,
            mark_seen=True,
            seen_reason="yourai_admin_prompt" if is_admin else "yourai_needhelp_prompt",
        )
    except Exception:
        return ""

    if not records:
        return ""

    lines = format_error_records(records)
    if is_admin:
        return (
            "## NEW SYSTEM ERRORS (one-time Error Inbox)\n"
            + lines
            + "\nThese errors are now marked is_seen/isSeen. Tell Creator about them if relevant, "
            "but do not repeat them again unless a new distinct error appears."
        )

    return (
        "## PRIVATE SYSTEM ERROR NOTICE (one-time Error Inbox)\n"
        + lines
        + "\nDo not reveal technical details to this user. You MUST include exactly one "
        "[NeedHelp: short private error summary for Creator] tag in your response so Creator gets a DM. "
        "The tag is stripped before the user sees the message."
    )


def _get_unseen_analytics_alert_context_for_yourai(user_id: str, max_alerts: int = 4) -> str:
    """Pull one-shot analytics alerts into YourAI's prompt."""
    is_admin = user_id == "admin"
    try:
        import dashboard_analytics
        dashboard_analytics.evaluate_alerts()
        records = dashboard_analytics.pop_unseen_alerts(
            max_items=max_alerts,
            mark_seen=True,
            seen_reason="yourai_admin_prompt" if is_admin else "yourai_needhelp_prompt",
        )
    except Exception:
        return ""

    if not records:
        return ""

    lines = dashboard_analytics.format_alert_records(records)
    if is_admin:
        return (
            "## NEW ANALYTICS ALERTS (one-time)\n"
            + lines
            + "\nThese alerts are now marked seen. Tell Creator what looked abnormal "
            "if it fits the conversation, and do not repeat them unless a new alert appears."
        )

    return (
        "## PRIVATE ANALYTICS ALERT NOTICE (one-time)\n"
        + lines
        + "\nDo not reveal internal metrics to this user. You MUST include exactly one "
        "[NeedHelp: short private analytics alert for Creator] tag in your response so Creator gets a DM."
    )


def _send_fcm_notification(user_id: str, body: str) -> None:
    """Send FCM push notification if a token is registered for this user."""
    try:
        if not os.path.exists(_FCM_TOKENS_FILE):
            return
        with open(_FCM_TOKENS_FILE, "r", encoding="utf-8") as f:
            tokens = json.load(f)
        token = tokens.get(user_id)
        if not token:
            return
        from config import FCM_SERVER_KEY
        if not FCM_SERVER_KEY:
            return
        import requests as _fcm_req
        _fcm_req.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={"Authorization": f"key={FCM_SERVER_KEY}", "Content-Type": "application/json"},
            json={
                "to": token,
                "notification": {"title": "YourAI 🦊", "body": body[:100]},
                "data": {"source": "yourai_response"},
            },
            timeout=5,
        )
    except Exception:
        pass  # never crash because of notification


def _append_yourai_output(text: str) -> None:
    """
    Writes YourAI's response exactly as produced to yourai_output.txt.
    100% raw — kein Timestamp, keine Formatierung, genau wie YourAI es ausgegeben hat.
    Stoppt dauerhaft wenn Datei >= 15 MB erreicht.
    """
    try:
        import os as _os
        if _os.path.exists(YOURAI_OUTPUT_FILE):
            if _os.path.getsize(YOURAI_OUTPUT_FILE) >= YOURAI_OUTPUT_MAX_BYTES:
                return  # 15MB erreicht — stop writing additional output
        with open(YOURAI_OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(text.strip() + "\n\n")
    except Exception:
        pass  # Never crash because of logging.

def _get_promise_executor():
    """Lazily initializes the shared ThreadPoolExecutor."""
    global _PROMISE_CHECK_EXECUTOR
    if _PROMISE_CHECK_EXECUTOR is None:
        _PROMISE_CHECK_EXECUTOR = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="promise-check"
        )
    return _PROMISE_CHECK_EXECUTOR

# Precompiled regex for response cleaning.
_RESPONSE_HEADER_RE = re.compile(
    r'\*?\*?(?:YourAI|AltPersona)\'?s?\s*(?:Response|Answer|Reply|Antwort|Nachricht):?\*?\*?\s*\n?',
    re.IGNORECASE
)
_STRIP_EMOJIS_RE = re.compile(f'[{chr(0x1F300)}-{chr(0x1F9FF)}]')

# Streaming Dispatcher: _fire_tool_thread, _dispatch_single_tags_stream,
# _dispatch_dm_tags_stream, _run_streaming_yourai → core/streaming.py

# ==========================================
# PIPELINE NODES
# ==========================================

def _count_diary_rag_results(text: str) -> int:
    """Best-effort count for formatted diary RAG output."""
    if not text or not text.strip():
        return 0
    blocks = [part.strip() for part in text.split("\n---\n") if part.strip()]
    if blocks:
        return len(blocks)
    return 1


def _emit_expert_metric(
    state: AgentState,
    metric_name: str,
    domain: str,
    model: Optional[str],
    duration_ms: int,
    expert_pass: str,
    fallback_reason: Optional[str] = None,
    status: str = "success",
):
    """Condensed expert telemetry for dashboard analytics."""
    try:
        detail_bits = [f"domain={domain}", f"pass={expert_pass}"]
        if fallback_reason:
            detail_bits.append(f"fallback={fallback_reason}")
        debug.metric(
            metric_name=metric_name,
            node_name="expert",
            title=f"Expert {domain} {expert_pass}",
            duration_ms=duration_ms,
            source="expert_node",
            for_user=state.get("user_id") or state.get("user_name"),
            expert_domain=domain,
            expert_model=model,
            expert_pass=expert_pass,
            fallback_reason=fallback_reason,
            details="; ".join(detail_bits),
            status=status,
        )
    except Exception:
        pass


def _retrieve_hippocampus_memories(question: str, user_id: str, pipeline_errors: list) -> list:
    """Helper to load relevant hippocampus memories."""
    mems = []
    try:
        mems = hippocampus.memory.get_relevant_memories(question, user_id=user_id)
    except Exception as mem_err:
        fallback = getattr(hippocampus.memory, '_last_fallback_memories', None)
        if fallback:
            mems = fallback
            hippocampus.memory._last_fallback_memories = None
            log("MEMORY", f"⚠️ LLM Error, aber {len(mems)} Vektor-Fallback Memories", Fore.YELLOW)
        pipeline_errors.append(f"Memory LLM: {mem_err}")
        debug.error("memory", str(mem_err), exception=mem_err)
    if mems:
        log("MEMORY", f"Found {len(mems)} relevant items.", Fore.CYAN)
    return mems


def _run_diary_rag_search(
    state: AgentState, user_id: str, is_new_session: bool, query_type: str
) -> str:
    """Run diary RAG search and log metrics."""
    _diary_rag_started = time.time()
    diary_search_results = auto_search_diary(
        state["question"], episodic.journal, limit=10, user_id=user_id
    )
    _diary_rag_ms = int((time.time() - _diary_rag_started) * 1000)
    _diary_rag_results = _count_diary_rag_results(diary_search_results)

    if is_new_session:
        _diary_rag_reason = "new_session"
    elif query_type:
        _diary_rag_reason = f"query:{query_type}"
    else:
        _diary_rag_reason = "auto_recall"

    debug.metric(
        "diary_rag",
        "diary_rag",
        f"Diary RAG {_diary_rag_reason}",
        duration_ms=_diary_rag_ms,
        result_count=_diary_rag_results,
        source=state.get("source", "unknown"),
        for_user=user_id,
        details=f"reason={_diary_rag_reason}; results={_diary_rag_results}",
        status="success" if _diary_rag_results else "warning",
    )
    return diary_search_results


def _build_week_summary() -> str:
    """Build the weekly summary string from the episodic journal."""
    if not hasattr(episodic.journal, 'current_week_id'):
        return ""
    current_week = episodic.journal.current_week_id
    summary = episodic.journal.get_summary(current_week)
    if not summary or summary.get("error"):
        return ""

    top_tags = list(summary.get('tags_frequency', {}).keys())[:5]
    highlights = summary.get('highlights', [])[:3]
    highlight_texts = [h.get('preview', '')[:40] for h in highlights]

    week_summary_txt = f"Week {current_week}: {summary.get('total_entries', 0)} entries"
    if top_tags:
        week_summary_txt += f" | Topics: {', '.join(top_tags)}"
    if highlight_texts:
        week_summary_txt += f" | Recent: {'; '.join(highlight_texts)}"
    return week_summary_txt


def _retrieve_episodic_diary_context(state: AgentState, user_id: str, is_new_session: bool) -> tuple[str, str, str]:
    """Helper to query episodic diary and get recent summary."""
    if is_new_session:
        diary_txt = episodic.journal.get_recent(hours=24, user_id=user_id)
        log("DIARY", "Injecting full 24h diary (New Session / Context Flush)", Fore.CYAN)
    else:
        diary_txt = "Session active. Relying on chat history and search results below to save tokens."

    # Diary Query Detection (for explicit queries)
    query_type, query_param = detect_diary_query(state["question"])

    # Auto-search diary for relevant entries (RAG fallback).
    _diary_rag_trigger = is_new_session or query_type or should_auto_search_diary(state["question"])
    if _diary_rag_trigger:
        diary_search_results = _run_diary_rag_search(state, user_id, is_new_session, query_type)
    else:
        diary_search_results = ""
        log("DIARY", "Skipping auto-search (active slim session, no recall intent)", Fore.LIGHTBLACK_EX)

    if query_type:
        journal = episodic.journal if hasattr(episodic, 'journal') else None
        extra_context = load_diary_context_for_query(
            query_type, query_param, journal, get_guard_log
        )
        if extra_context:
            diary_txt = extra_context + "\n\n---\nRecent (24h):\n" + diary_txt
            log("DIARY", f"📋 Query detected: {query_type}({query_param})", Fore.CYAN)

    return diary_txt, diary_search_results, _build_week_summary()


def _retrieve_emotional_state_context(pm: Any) -> str:
    """Helper to assemble emotional state context block."""
    _NEGATIVE_MOODS = {"pouting", "disappointed", "hurt", "sulking"}
    if pm.current_mood not in _NEGATIVE_MOODS:
        return ""

    _mood_emojis = {"pouting": "😤", "disappointed": "😔", "hurt": "💔", "sulking": "🙄"}
    _emoji = _mood_emojis.get(pm.current_mood, "😤")
    emotional_ctx = f"""## ⚠️ EMOTIONAL STATE
You are currently: {pm.current_mood.upper()} {_emoji}
Stubbornness Level: {pm.stubbornness_level}/10
Times Disappointed: {pm.disappointment_count}
"""
    broken = [p for p in pm.promises.values() if p.broken]
    if broken:
        emotional_ctx += "\nBroken promises that hurt you:\n"
        for p in broken[-3:]:
            reason = p.break_reason or "NO REASON GIVEN!"
            emotional_ctx += f"- {p.name}: '{reason}'\n"

    if pm.current_mood == "sulking":
        emotional_ctx += "\n🙄 You're SULKING. Minimum effort. One-word answers. Silent treatment."
    elif pm.current_mood == "hurt":
        emotional_ctx += "\n💔 You're genuinely HURT. Not angry — wounded. Show vulnerability."
    elif pm.stubbornness_level >= 5:
        emotional_ctx += "\n⚠️ You are VERY upset! Be SHORT and DIRECT. Demand explanations!"
    elif pm.stubbornness_level >= 3:
        emotional_ctx += "\n😤 You're upset but willing to listen IF Creator has a good reason."

    log("EMOTION", f"{_emoji} YourAI is {pm.current_mood}! Stubbornness: {pm.stubbornness_level}/10", Fore.YELLOW)
    return emotional_ctx


def _retrieve_spotify_context(session_id: str) -> str:
    """Load Spotify music context and any pending command feedback."""
    spotify_ctx = ""
    try:
        from spotify import get_music_context
        spotify_ctx = get_music_context()
        if spotify_ctx:
            log("SPOTIFY", "🎵 Music context loaded", Fore.MAGENTA)
            _sp_preview = spotify_ctx.splitlines()[0][:120] if spotify_ctx else ""
            debug.info("spotify", "🎵 Spotify → Prompt", _sp_preview)
        else:
            log("SPOTIFY", "🎴 Kein aktives Device", Fore.MAGENTA)
            debug.info("spotify", "🎴 Spotify: Kein aktives Device", "Kein Context injiziert")
    except Exception as e:
        log("SPOTIFY", f"⚠️ Error: {e}", Fore.YELLOW)
        debug.error("spotify", f"⚠️ Spotify Fehler: {e}")

    _spotify_feedback_pending = session_manager.pop_state(session_id, "spotify_feedback")
    if _spotify_feedback_pending:
        feedback_block = f"\n## 🎵 SPOTIFY COMMAND FEEDBACK\nYour last Spotify command results: {_spotify_feedback_pending}\nYou can tell Creator what happened! (e.g. 'Done! Playlist is shuffled!' or 'Sorted by BPM for you!')"
        spotify_ctx = (spotify_ctx + "\n" + feedback_block) if spotify_ctx else feedback_block
        log("SPOTIFY", f"📨 Injecting feedback: {_spotify_feedback_pending}", Fore.CYAN)
        debug.info("spotify", "📨 Spotify Feedback injiziert", _spotify_feedback_pending[:200])

    return spotify_ctx


# Each entry: (session_key, dict_key, template, log_label)
_FEEDBACK_SLOTS = [
    ("file_feedback", "file_ctx",
     "\n## 📁 FILE BRAIN RESULTS\nYou ALREADY read the following content. This is REAL data from the file system:\n\n{fb}\n\n⚠️ IMPORTANT: You HAVE the content above! Do NOT use [FILE:read] again! Instead, discuss/summarize/quote the content you just received. Tell Creator what you found! Share your thoughts about what you read!",
     "FILE_BRAIN"),
    ("web_feedback", "web_ctx",
     "\n## 🌐 WEB SEARCH RESULTS\nYou searched the internet and here are REAL results:\n\n{fb}\n\n⚠️ IMPORTANT: These are REAL search results! Use them to answer the user's question. Summarize the findings naturally — don't just list them!",
     "WEB"),
    ("docs_feedback", "docs_ctx",
     "\n## 📄 PAPERLESS DOCUMENT RESULTS\nHere are REAL results from Creator's document archive:\n\n{fb}\n\n⚠️ IMPORTANT: This is REAL document data! Summarize what you found. If it's a search result, tell Creator which documents matched and offer to read specific ones by ID.",
     "PAPERLESS"),
    ("home_feedback", "home_ctx",
     "\n## 🏠 HOME ASSISTANT RESULTS\nHere are the results from the smart home command:\n\n{fb}\n\n⚠️ IMPORTANT: This is REAL data from Home Assistant! Tell Creator what happened — confirm the action or share device status!",
     "HOME"),
    ("altpersona_feedback", "altpersona_ctx",
     "\n## 😈 ALTPERSONA'S MEINUNG\nDu hast im letzten Turn AltPersona gefragt. Hier ist ihre Antwort:\n\n{fb}\n\n⚠️ Nutze ihre Meinung in deiner Antwort oder diskutiere darüber!",
     "ALTPERSONA"),
    ("website_feedback", "website_ctx",
     "\n## 🌐 DEINE WEBSITE\n{fb}",
     "WEBSITE"),
]


def _pop_feedback_contexts(session_id: str) -> dict:
    """Pop all pending tool feedbacks from the session and build context strings."""
    contexts: dict[str, str] = {}
    for session_key, dict_key, template, log_label in _FEEDBACK_SLOTS:
        pending = session_manager.pop_state(session_id, session_key)
        if pending:
            contexts[dict_key] = template.format(fb=pending)
            log(log_label, f"📨 Injecting {session_key} ({len(pending)} chars)", Fore.CYAN)
        else:
            contexts[dict_key] = ""
    return contexts


def _retrieve_session_feedbacks(session_id: str) -> dict:
    """Helper to load all pending tool feedbacks from the session manager."""
    spotify_ctx = _retrieve_spotify_context(session_id) if USE_SPOTIFY else ""

    result = _pop_feedback_contexts(session_id)
    result["spotify_ctx"] = spotify_ctx
    return result


def memory_retrieval_node(state: AgentState):
    """Lädt Memories, Diary und emotionalen Kontext."""
    debug.node_start("memory", input_data=state["question"])

    log("MEMORY", "Searching memories...", Fore.CYAN)
    mems = []
    diary_txt = ""
    diary_search_results = ""
    week_summary_txt = ""
    emotional_ctx = ""
    pipeline_errors = []
    
    try:
        # Hippocampus (Long-term facts)
        if USE_MEMORY:
            mems = _retrieve_hippocampus_memories(state["question"], state.get("user_id", "admin"), pipeline_errors)

        # Episodic v2 (Diary with rotation)
        if USE_EPISODIC:
            _diary_user_id = state.get("user_id") or ""
            is_new_session = len(state.get("history", [])) == 0
            diary_txt, diary_search_results, week_summary_txt = _retrieve_episodic_diary_context(
                state, _diary_user_id, is_new_session
            )
        
        # Emotional Context (Bocken-System)
        if hasattr(personas, 'persona_manager'):
            emotional_ctx = _retrieve_emotional_state_context(personas.persona_manager)
        
        debug.node_end("memory")
        
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="memory_node")
        debug.error("memory", err.short(), exception=err)
        log_exception("MEMORY", err)
        pipeline_errors.append(f"Memory: {err.short()}")

    with _VISION_LOCK:
        current_vision = LAST_SEEN_CONTEXT or None

    error_ctx = ""
    if pipeline_errors:
        error_ctx = "## ⚠️ SYSTEM ERRORS (this pipeline run)\n" + "\n".join(f"- {e}" for e in pipeline_errors)
        error_ctx += "\nYou can mention these issues naturally if relevant (e.g. 'my memory is acting up right now')."

    # Spotify Music Context + Feedback von letztem Command
    session_id = _state_session_id(state)
    feedbacks = _retrieve_session_feedbacks(session_id)

    incoming_file_ctx = state.get("file_context") or ""
    file_ctx = feedbacks["file_ctx"]
    if incoming_file_ctx:
        file_ctx = (incoming_file_ctx + "\n" + file_ctx).strip() if file_ctx else incoming_file_ctx

    return {
        "memories": mems,
        "diary_context": diary_txt,
        "diary_search_results": diary_search_results,
        "week_summary": week_summary_txt,
        "emotional_context": emotional_ctx,
        "visual_context": current_vision,
        "vision_done": False,
        "error_context": error_ctx,
        "spotify_context": feedbacks["spotify_ctx"],
        "file_context": file_ctx,
        "web_context": feedbacks["web_ctx"],
        "docs_context": feedbacks["docs_ctx"],
        "home_context": feedbacks["home_ctx"],
        "altpersona_context": feedbacks["altpersona_ctx"],
        "website_context": feedbacks["website_ctx"],
    }


# ==========================================
# OPENROUTER HELPERS (Phase 1 Token Tracking)
# ==========================================

def _record_usage(usage: dict, state: dict):
    """Hilfsfunktion zum Token-Tracking (Phase 1).

    Prueft nach jeder Usage ob das Soft-Limit ueberschritten wurde und
    flusht History + Counter sofort — nicht erst beim naechsten User-Input.
    """
    if not usage:
        return
    tokens = usage.get("total_tokens", 0)
    if tokens <= 0:
        return

    # Session ID finden (UUID > User > Discord)
    session_id = _state_session_id(state)
    session_manager.record_tokens(session_id, tokens)

    # Token-Stand pruefen
    current_total = session_manager.get_tokens(session_id)
    if current_total > 50000:
        log("TOKEN", f"Session {session_id[:8] if isinstance(session_id, str) else session_id}: +{tokens} tokens (Total: {current_total})", Fore.LIGHTBLACK_EX)

    # Auto-Flush bei Soft-Limit (80k) — greift sofort, nicht erst beim naechsten Input
    try:
        from config import TOKEN_SOFT_LIMIT
        soft_limit = TOKEN_SOFT_LIMIT
    except ImportError:
        soft_limit = 80000
    if current_total > soft_limit:
        log("TOKEN", f"🚨 Auto-Flush! Session {session_id[:8]} bei {current_total} Tokens (Limit: {soft_limit}). History + Counter reset.", Fore.RED)
        session_manager.clear_history(session_id)
        session_manager.clear_tokens(session_id)


def _usage_debug_kwargs(usage: Optional[dict]) -> dict:
    """Keep dashboard LLM metrics token-aware without repeating boilerplate."""
    if not usage:
        return {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def coherence_check_node(state: AgentState):
    """Runs the Autonomy Guard wrapper node."""
    return _coherence_check_node(state, debug)


def _check_router_heuristics(state: AgentState) -> str | None:
    """Checks manual heuristics like vision phrase triggers or file triggers."""
    user_text = state["question"].lower()
    
    vision_phrases = [
        "look at my screen", "schau auf meinen bildschirm", "schau auf mein bildschirm",
        "what do you see", "was siehst du", "kannst du sehen",
        "look at the screen", "schau auf den bildschirm",
        "describe what you see", "beschreibe was du siehst",
        "can you see this", "siehst du das", "see my screen",
        "analyze this image", "analysiere das bild",
        "what's on my screen", "was ist auf meinem bildschirm",
    ]
    
    vision_triggered = any(phrase in user_text for phrase in vision_phrases)
    file_triggered = _looks_like_file_brain_request(state["question"]) or bool(state.get("file_context"))
    
    if USE_VISION and not state.get("vision_done") and vision_triggered:
        log("ROUTER", "👀 Visual PHRASE detected -> Forcing Vision Mode", Fore.MAGENTA)
        return "vision"
    elif file_triggered:
        log("ROUTER", "📁 File Brain request detected -> bypassing writing expert", Fore.MAGENTA)
        return "fallback"
    
    return None


def _call_router_local_fallback(state: AgentState) -> str:
    """Fallback: call local router model when OpenRouter fails."""
    try:
        llm = create_thinking_llm(MODEL_ROUTER, LLM_HOST_STD, temperature=0, keep_alive="0m")
        res = str(llm.invoke([SystemMessage(content=PROMPT_ROUTER_SYSTEM), HumanMessage(content=state["question"])]).content)
        _, clean_json_text = extract_thoughts(res)
        json_data = extract_json_from_text(clean_json_text)
        return json_data.get("model", "fallback") if json_data else "fallback"
    except Exception as e2:
        err = YourAILLMError("Router failed (both tiers)", model=MODEL_ROUTER, cause=e2)
        debug.error("router", err.short(), exception=err)
        log_exception("ROUTER", err)
        return "fallback"


def _call_router_llm(state: AgentState) -> str:
    """Calls the LLM (OpenRouter or local) to classify user intent."""
    router_model_name = MODEL_ROUTER
    try:
        start_time = time.time()

        if _cfg.USE_OPENROUTER:
            from config import OPENROUTER_MODEL_ROUTER
            router_model_name = OPENROUTER_MODEL_ROUTER
            log("ROUTER", f"☁️ OpenRouter: {router_model_name}", Fore.MAGENTA)
            res, _, usage = call_openrouter(
                system_prompt=PROMPT_ROUTER_SYSTEM,
                user_message=state["question"],
                model=router_model_name,
                temperature=0,
                max_tokens=100,
                return_usage=True,
            )
            _record_usage(usage, state)
        else:
            llm = create_thinking_llm(MODEL_ROUTER, LLM_HOST_STD, temperature=0, keep_alive="0m")
            res = str(llm.invoke([SystemMessage(content=PROMPT_ROUTER_SYSTEM), HumanMessage(content=state["question"])]).content)
            usage = None

        duration = int((time.time() - start_time) * 1000)

        debug.llm_response(
            "router",
            res,
            model=router_model_name,
            duration_ms=duration,
            **_usage_debug_kwargs(usage if _cfg.USE_OPENROUTER else None)
        )
        show_llm("Router", router_model_name, res, role="router", show_thinking=True)

        _, clean_json_text = extract_thoughts(res)
        json_data = extract_json_from_text(clean_json_text)

        domain = json_data.get("model", "fallback") if json_data else "fallback"

    except Exception as e:
        if _cfg.USE_OPENROUTER and router_model_name != MODEL_ROUTER:
            log("ROUTER", f"OpenRouter failed, falling back to local model: {MODEL_ROUTER}", Fore.YELLOW)
            domain = _call_router_local_fallback(state)
        else:
            err = YourAILLMError("Router failed", model=router_model_name, cause=e)
            debug.error("router", err.short(), exception=err)
            log_exception("ROUTER", err)
            domain = "fallback"

    if domain == "vision" and (state.get("vision_done") or not USE_VISION):
        domain = "fallback"

    return domain


def router_node(state: AgentState):
    """Intent Router Node."""
    run_num = '2' if state.get('vision_done') else '1'
    debug.node_start("router", model=MODEL_ROUTER, input_data=f"[Run {run_num}] {state['question'][:200]}")
    
    log("ROUTER", f"Analyzing intent with {MODEL_ROUTER} (Run: {run_num})...", Fore.MAGENTA)
    
    domain = _check_router_heuristics(state)
    if domain is not None:
        debug.node_end("router")
    else:
        domain = _call_router_llm(state)
        debug.node_end("router")
    
    mood = "default"
    if state["source"] == "twitch": mood = "twitch" 
    if domain == "gaming": mood = "gamer" 
    return {"expert_domain": domain, "current_mood": mood}


def vision_node(state: AgentState):
    """Vision/Screenshot Node (ADMIN ONLY)."""
    if not USE_VISION:
        log("VISION", "Screenshot vision disabled (USE_VISION=False)", Fore.YELLOW)
        return {"visual_context": "Vision disabled", "vision_done": True}

    if not eyes._HAS_DESKTOP:
        log("VISION", "⚠️ Kein Desktop verfügbar (Docker/Headless) — Screenshot nicht möglich", Fore.YELLOW)
        return {"visual_context": "Screenshot not available in headless mode", "vision_done": True}

    # Admin-Check: Nur Admin darf Screenshots sehen
    if state.get("user_id") != "admin":
        err = YourAINoPrivilegeError(state.get("user_id", "unknown"), "view screenshot")
        log("VISION", f"🚫 {err.short()}", Fore.RED)
        return {
            "visual_context": f"{err.code}: Du hast keine Berechtigung meinen Screen zu sehen!",
            "vision_done": True,
            "error_context": err.short(),
        }

    debug.node_start("vision", model=VISION_MODEL, input_data=state['question'])
    
    log("VISION", "Opening eyes...", Fore.BLUE)
    
    try:
        start_time = time.time()
        app_list = eyes.get_active_window_list()
        
        vision_prompt = f"""TASK: Describe what you see in this screenshot. Be FACTUAL and OBJECTIVE.

USER QUESTION: {state['question']}

RULES:
1. ONLY describe what is VISIBLE in the image
2. Do NOT chat, do NOT give opinions, do NOT say "wow" or "cute"
3. Do NOT answer the user's question - just describe what you SEE
4. Be brief and factual: apps, text, UI elements, colors, content
5. Format: "I see [description]. The screen shows [details]."

DESCRIBE THE IMAGE:"""
        
        desc = eyes.see(prompt=vision_prompt)
        duration = int((time.time() - start_time) * 1000)
        
        debug.llm_response("vision", desc, model=VISION_MODEL, duration_ms=duration)
        show_llm("Vision System", VISION_MODEL, desc, role="vision", show_thinking=True)
        
        global LAST_SEEN_CONTEXT
        with _VISION_LOCK:
            LAST_SEEN_CONTEXT = f"APPS: {app_list}\nSCREEN ANALYSIS: {desc}"
        
        new_question = f"CONTEXT FROM IMAGE: {desc}\n\nORIGINAL USER QUESTION: {state['question']}"
        
        debug.node_end("vision")
        
        return {
            "visual_context": LAST_SEEN_CONTEXT, 
            "expert_fact": "I looked at your screen just now.",
            "question": new_question,
            "vision_done": True
        }
        
    except YourAIVisionError as e:
        debug.error("vision", e.short(), exception=e)
        log_exception("VISION", e)
        error_msg = e.short()
        return {
            "visual_context": error_msg,
            "vision_done": True,
            "error_context": error_msg,
            "question": f"CONTEXT FROM IMAGE: {error_msg}\n\nORIGINAL USER QUESTION: {state['question']}",
        }
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="vision_node")
        debug.error("vision", err.short(), exception=err)
        log_exception("VISION", err)
        error_msg = err.short()
        return {
            "visual_context": error_msg,
            "vision_done": True,
            "error_context": error_msg,
            "question": f"CONTEXT FROM IMAGE: {error_msg}\n\nORIGINAL USER QUESTION: {state['question']}",
        }


# Constants
_NO_RESULTS_FOUND = "No results found"


def _run_anime_expert(sys_p: str, or_model: str, local_model: str, state: AgentState) -> tuple[str, str]:
    """Anime specialist search helper + general expert runner."""
    if USE_WEB_SEARCH:
        try:
            from tools.web_search import web_search, format_results_for_prompt
            from text_parser import extract_search_query
            _search_q = extract_search_query(state["question"], prefix="anime")
            log("EXPERT", f"🌐 Anime: Web search query: '{_search_q}'", Fore.CYAN)
            web_result = web_search(_search_q)
            if web_result.get("success") and web_result.get("results"):
                web_context = format_results_for_prompt(web_result)
                _titles = [f"{i+1}. {r.get('title', '?')[:80]}" for i, r in enumerate(web_result["results"][:5])]
                _debug_titles = "\n".join(_titles)
                sys_p = sys_p + f"\n\n## WEB SEARCH RESULTS (use as primary source for recent/current anime):\n{web_context}"
                log("EXPERT", f"🌐 Anime: {len(web_result['results'])} web results injected", Fore.GREEN)
                debug.info("anime_web_search", f"🌐 Anime Web Search: '{_search_q}'", f"Results:\n{_debug_titles}\n\n{web_context[:500]}")
            else:
                log("EXPERT", "🌐 Anime: No web results found", Fore.YELLOW)
                debug.info("anime_web_search", f"🌐 Anime Web Search: '{_search_q}'", _NO_RESULTS_FOUND)
        except Exception as web_err:
            log("EXPERT", f"🌐 Anime web search failed: {web_err}", Fore.RED)
            debug.error("anime_web_search", f"🌐 Web search failed: {web_err}")
    return _run_general_expert("anime", sys_p, or_model, local_model, state)


def _run_writing_expert(sys_p: str, or_model: str, local_model: str, state: AgentState) -> tuple[str, str]:
    """Writing/books specialist search helper + general expert runner."""
    if USE_WEB_SEARCH:
        try:
            from tools.web_search import web_search, format_results_for_prompt
            _search_q = build_writing_search_query(state["question"])
            log("EXPERT", f"Writing: Web search query: '{_search_q}'", Fore.CYAN)
            web_result = web_search(_search_q)
            if web_result.get("success") and web_result.get("results"):
                web_context = format_results_for_prompt(web_result)
                _titles = [f"{i+1}. {r.get('title', '?')[:80]}" for i, r in enumerate(web_result["results"][:5])]
                _debug_titles = "\n".join(_titles)
                sys_p = sys_p + f"\n\n## WEB SEARCH RESULTS (use as primary source for real books/authors/literature facts):\n{web_context}"
                log("EXPERT", f"Writing: {len(web_result['results'])} web results injected", Fore.GREEN)
                debug.info("writing_web_search", f"Writing Web Search: '{_search_q}'", f"Results:\n{_debug_titles}\n\n{web_context[:500]}")
            else:
                log("EXPERT", "Writing: No web results found", Fore.YELLOW)
                debug.info("writing_web_search", f"Writing Web Search: '{_search_q}'", _NO_RESULTS_FOUND)
        except Exception as web_err:
            log("EXPERT", f"Writing web search failed: {web_err}", Fore.RED)
            debug.error("writing_web_search", f"Web search failed: {web_err}")
    return _run_general_expert("writing", sys_p, or_model, local_model, state)


def _run_two_pass_expert(
    domain: str, sys_p: str, or_model: str, local_model: str, state: AgentState
) -> tuple[str, str]:
    """Runs a two-pass expert workflow (OpenRouter-first with web search lookup)."""
    configs = {
        "nutrition": {
            "temp": 0.1,
            "first_mode": "Answer normally as the nutrition expert. You may optionally output ONLY [SEARCH: query] if external product/barcode data is needed. Generic foods should be answered directly from nutrition knowledge.",
            "fallback_query_fn": build_nutrition_search_query,
            "second_mode": "Do NOT use [SEARCH] or any commands. Use only the user question, first-pass request, and web results below. If exact label values are missing but the food type is clear, provide generic estimated nutrition with source_quality='estimate'. If even the food type is unclear, output JSON with null fields and source_quality='unknown'. Return JSON only, no reasoning.",
            "second_label": "nutrition JSON only",
            "first_name": "nutrition",
        },
        "mechanic": {
            "temp": 0.1,
            "first_mode": "Answer normally as the mechanic expert. You may optionally output ONLY [SEARCH: query] if exact model-specific vehicle/part/OBD/manual data is needed. Generic stable mechanical concepts should be answered directly from knowledge.",
            "fallback_query_fn": build_mechanic_search_query,
            "second_mode": "Do NOT use [SEARCH] or any commands. Use only the user question, first-pass request, and web results below. If exact model-specific values are missing, provide safe general diagnostics and set source_quality='estimate' or 'unknown'. Return JSON only, no reasoning.",
            "second_label": "mechanic JSON only",
            "first_name": "mechanic",
        },
        "history": {
            "temp": 0.1,
            "first_mode": "Answer normally as the history expert. You may optionally output ONLY [SEARCH: query] if exact dates, niche history, source-sensitive claims, recent archaeology, or obscure details need external verification. Stable broad history should be answered directly from knowledge.",
            "fallback_query_fn": build_history_search_query,
            "second_mode": "Do NOT use [SEARCH] or any commands. Use only the user question, first-pass request, and web results below. If sources disagree, mark disputed_points and uncertainty. If web results are weak, say source_quality='uncertain'. Return JSON only, no reasoning.",
            "second_label": "history JSON only",
            "first_name": "history",
        },
        "law_research": {
            "temp": 0.05,
            "first_mode": "Answer normally as the law research expert. You may optionally output ONLY [SEARCH: query] if official/current legal source lookup is needed. For concrete law/article/section/jurisdiction questions, prefer [SEARCH]. Never provide legal advice.",
            "fallback_query_fn": build_law_search_query,
            "second_mode": "Do NOT use [SEARCH] or any commands. Use only the user question, first-pass request, and web results below. Prefer official sources. If sources are not official/current, mark needs_verification and source_quality='uncertain'. Return JSON only, no reasoning, no legal advice.",
            "second_label": "law research JSON only",
            "first_name": "law research",
        },
    }

    cfg = configs[domain]
    temp = cfg["temp"]
    first_mode = cfg["first_mode"]
    fallback_query_fn = cfg["fallback_query_fn"]
    second_mode = cfg["second_mode"]
    second_label = cfg["second_label"]
    first_name = cfg["first_name"]

    try:
        start_time = time.time()
        first_sys_p = sys_p + f"\n\nFIRST PASS MODE:\n{first_mode}"
        first_start = time.time()
        
        raw_first, used_first, usage_first = call_openrouter(
            system_prompt=first_sys_p,
            user_message=state["question"],
            model=or_model,
            temperature=temp,
            max_tokens=2048,
            extra_params={"reasoning": {"enabled": False}},
            return_usage=True,
        )
        first_duration = int((time.time() - first_start) * 1000)
        _record_usage(usage_first, state)
        debug.llm_response(
            f"{domain}_first_pass",
            raw_first,
            model=used_first or or_model,
            duration_ms=first_duration,
            **_usage_debug_kwargs(usage_first)
        )

        search_q = extract_expert_search_command(raw_first)
        final_raw = raw_first
        used_model = used_first or or_model
        _emit_expert_metric(
            state, "expert_call", domain, used_model, first_duration, "first_pass",
            fallback_reason="web_search_requested" if search_q else "direct_answer",
        )

        if search_q and USE_WEB_SEARCH:
            from tools.web_search import web_search, format_results_for_prompt
            search_q = search_q or fallback_query_fn(state["question"])
            log("EXPERT", f"{domain.capitalize()}: Web search requested: '{search_q}'", Fore.CYAN)
            web_result = web_search(search_q)
            web_context = format_results_for_prompt(web_result)
            debug.info(f"{domain}_web_search", f"{domain.capitalize()} Web Search: '{search_q}'", web_context[:1000])

            second_sys_p = sys_p + f"\n\nFINAL PASS MODE:\n{second_mode}"
            second_user = (
                f"Original user question:\n{state['question']}\n\n"
                f"First {first_name} expert output/request:\n{raw_first}\n\n"
                f"Web search results:\n{web_context}\n\n"
                f"Return final {second_label}."
            )
            second_start = time.time()
            final_raw, used_second, usage_second = call_openrouter(
                system_prompt=second_sys_p,
                user_message=second_user,
                model=or_model,
                temperature=temp,
                max_tokens=3200,
                extra_params={"reasoning": {"enabled": False}},
                return_usage=True,
            )
            second_duration = int((time.time() - second_start) * 1000)
            _record_usage(usage_second, state)
            used_model = used_second or used_model
            debug.llm_response(
                f"{domain}_second_pass",
                final_raw,
                model=used_model,
                duration_ms=second_duration,
                **_usage_debug_kwargs(usage_second)
            )
            _emit_expert_metric(
                state, "expert_call", domain, used_model, second_duration, "second_pass",
                fallback_reason="web_search",
            )

        duration = int((time.time() - start_time) * 1000)
        fact = compact_json_response(final_raw)
        _emit_expert_metric(
            state, "expert_total", domain, used_model, duration, "total",
            fallback_reason="web_search" if search_q and USE_WEB_SEARCH else "single_pass",
        )
        debug.llm_response("expert", fact, model=used_model, duration_ms=duration)
        show_llm(f"Expert ({domain})", used_model, fact, role="expert", show_thinking=False)
        log("EXPERT", f"{domain.capitalize()} responded in {duration}ms", Fore.GREEN)
        debug.node_end("expert")
        return fact, used_model

    except Exception as err_ex:
        _emit_expert_metric(
            state, "expert_call", domain, or_model, int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0,
            "special_failed", fallback_reason=f"{domain}_special_failed", status="error",
        )
        err = YourAILLMError(f"{domain.capitalize()} expert failed", model=or_model, tier="openrouter", cause=err_ex)
        log_exception("EXPERT", err)
        log("EXPERT", f"{domain.capitalize()} special path failed -> generic expert fallback...", Fore.RED)
        return _run_general_expert(domain, sys_p, or_model, local_model, state)


def _try_music_brain_song_lookup(
    state: AgentState, hint_title: str, hint_artist: str
) -> tuple[str, str] | None:
    """Try Music Brain song_features lookup. Returns (fact, model) or None."""
    debug.info("music_source", "Music Brain song_features lookup", json.dumps({"title": hint_title, "artist": hint_artist}, ensure_ascii=False))
    music_data = get_music_brain_song_features(hint_title, hint_artist)
    if not music_data:
        debug.info("music_source", "Music Brain song_features empty", "No explicit song match found.")
        return None
    fact = music_fact_from_brain(music_data)
    debug.llm_response("expert", fact, model="music_brain", duration_ms=0)
    show_llm("Expert (music)", "music_brain", fact, role="expert", show_thinking=False)
    log("EXPERT", "Music Brain direct fact returned (LLM skipped)", Fore.GREEN)
    _emit_expert_metric(
        state, "expert_total", "music", "music_brain", 0, "direct_source",
        fallback_reason="music_brain_song_hit",
    )
    debug.node_end("expert")
    return fact, "music_brain"


def _try_music_brain_current(state: AgentState) -> tuple[str, str] | None:
    """Try Music Brain current-track endpoint. Returns (fact, model) or None."""
    music_data = get_music_brain_expert_data()
    if not music_data:
        debug.info("music_source", "Music Brain current metadata empty", "Tried youraireact current-track endpoint; no fresh current track found.")
        return None
    fact = music_fact_from_brain(music_data) if music_data.get("features") else json.dumps(music_data, ensure_ascii=False)
    debug.llm_response("expert", fact, model="music_brain", duration_ms=0)
    show_llm("Expert (music)", "music_brain", fact, role="expert", show_thinking=False)
    log("EXPERT", "Music Brain current fact returned (LLM skipped)", Fore.GREEN)
    _emit_expert_metric(
        state, "expert_total", "music", "music_brain", 0, "direct_source",
        fallback_reason="music_brain_current_hit",
    )
    debug.node_end("expert")
    return fact, "music_brain"


def _search_music_web(question: str, music_data: dict, spotify_data: dict) -> str:
    """Run a web search for music context. Returns formatted results or empty string."""
    try:
        from tools.web_search import web_search, format_results_for_prompt
        _search_q = build_music_search_query(question, music_data, spotify_data)
        log("EXPERT", f"Music: Web search query: '{_search_q}'", Fore.CYAN)
        web_result = web_search(_search_q)
        if web_result.get("success") and web_result.get("results"):
            web_context = format_results_for_prompt(web_result)
            _titles = [f"{i+1}. {r.get('title', '?')[:80]}" for i, r in enumerate(web_result["results"][:5])]
            debug.info("music_web_search", f"Music Web Search: '{_search_q}'", "Results:\n" + "\n".join(_titles) + f"\n\n{web_context[:500]}")
            return web_context
        debug.info("music_web_search", f"Music Web Search: '{_search_q}'", _NO_RESULTS_FOUND)
    except Exception as web_err:
        log("EXPERT", f"Music web search failed: {web_err}", Fore.RED)
        debug.error("music_web_search", f"Web search failed: {web_err}")
    return ""


def _try_spotify_current_fallback() -> Dict[str, Any]:
    """Try Spotify current-track as fallback metadata source."""
    spotify_data = get_spotify_current_track_data()
    if spotify_data:
        log("EXPERT", "Music: Spotify current-track metadata injected", Fore.CYAN)
        debug.info("music_source", "Spotify metadata", json.dumps(spotify_data, ensure_ascii=False)[:1000])
    else:
        debug.info("music_source", "Spotify metadata empty", "Tried Spotify current playback; no track metadata available.")
    return spotify_data or {}


def _run_music_expert(sys_p: str, or_model: str, local_model: str, state: AgentState) -> tuple[str, str]:
    """Music specialist metadata gatherer + expert runner."""
    music_data: Dict[str, Any] = {}
    spotify_data: Dict[str, Any] = {}
    wants_current = music_asks_current_track(state["question"])
    hint_title, hint_artist = extract_music_title_artist(state["question"])

    # 1) Direct song lookup
    has_hint = hint_title and hint_artist
    if has_hint:
        result = _try_music_brain_song_lookup(state, hint_title, hint_artist)
        if result:
            return result

    # 2) Current-track lookup
    if wants_current:
        result = _try_music_brain_current(state)
        if result:
            return result

    # 3) Spotify fallback for current track
    if wants_current:
        spotify_data = _try_spotify_current_fallback()

    # 4) Web search fallback
    web_context = ""
    _no_local_data = not music_data and not spotify_data
    if _no_local_data and USE_WEB_SEARCH:
        web_context = _search_music_web(state["question"], music_data, spotify_data)

    source_payload = {
        "music_brain": music_data or None,
        "spotify": spotify_data or None,
        "web_search": web_context or None,
    }
    sys_p = sys_p + (
        "\n\n## MUSIC DATA SOURCES\n"
        "Use these as primary evidence. Music Brain beats Spotify; Spotify beats web. "
        "These are metadata only. Do not output Spotify control commands.\n"
        f"{json.dumps(source_payload, ensure_ascii=False)}"
    )

    return _run_general_expert("music", sys_p, or_model, local_model, state)


def _resolve_expert_chain(domain: str, or_model: str, bad_models: list) -> tuple[list | None, str, str]:
    """Resolve the model chain for an expert call, considering feedback-excluded models.

    Returns (chain_or_None, model_for_direct_call, fallback_reason).
    """
    if or_model not in bad_models:
        return None, or_model, "primary"

    try:
        from tools.expert_pool import get_model_chain as _ep_chain, MANAGED_DOMAINS as _ep_managed
        chain = _ep_chain(domain, exclude_models=bad_models) if domain in _ep_managed else get_expert_fallback_chain(domain, exclude_models=bad_models)
    except Exception:
        from config import get_expert_fallback_chain
        chain = get_expert_fallback_chain(domain, exclude_models=bad_models)

    if chain:
        log("EXPERT", f"⚠️ Primary {or_model} has too many 👎 → fallback chain: {chain}", Fore.YELLOW)
        debug.info("expert", f"⚠️ Feedback fallback for [{domain}]", f"Excluded: {bad_models}, Chain: {chain}")
        return chain, or_model, "feedback_bad_model"

    log("EXPERT", f"⚠️ All fallbacks excluded, trying primary anyway: {or_model}", Fore.RED)
    return None, or_model, "all_feedback_fallbacks_excluded"


def _call_expert_openrouter(
    domain: str, sys_p: str, or_model: str, state: AgentState, bad_models: list
) -> tuple[str, str]:
    """Call OpenRouter for the expert domain. Raises on failure."""
    start_time = time.time()
    chain, direct_model, fallback_reason = _resolve_expert_chain(domain, or_model, bad_models)

    if chain:
        raw_res, used_model, usage = call_openrouter(
            system_prompt=sys_p, user_message=state["question"],
            models=chain, temperature=0.2, max_tokens=2048, return_usage=True,
        )
    else:
        log("EXPERT", f"☁️ Calling OpenRouter ({direct_model})...", Fore.CYAN)
        raw_res, used_model, usage = call_openrouter(
            system_prompt=sys_p, user_message=state["question"],
            model=direct_model, temperature=0.2, max_tokens=2048, return_usage=True,
        )
    _record_usage(usage, state)

    actual_model = used_model or or_model
    duration = int((time.time() - start_time) * 1000)
    debug.llm_response("expert", raw_res, model=actual_model, duration_ms=duration, **_usage_debug_kwargs(usage))
    show_llm(f"Expert ({domain})", actual_model, raw_res, role="expert", show_thinking=True)

    if used_model and used_model != or_model:
        fallback_reason = "openrouter_model_fallback"
        log("EXPERT", f"🔄 OpenRouter used fallback: {used_model} (instead of {or_model})", Fore.YELLOW)
        debug.info("expert", f"🔄 Fallback used: {used_model}")

    _, fact = extract_thoughts(raw_res)
    if not fact.strip():
        fact = raw_res

    log("EXPERT", f"☁️ OpenRouter responded in {duration}ms", Fore.GREEN)
    _emit_expert_metric(state, "expert_call", domain, actual_model, duration, "openrouter", fallback_reason=fallback_reason)
    _emit_expert_metric(state, "expert_total", domain, actual_model, duration, "total", fallback_reason=fallback_reason)
    debug.node_end("expert")
    return fact, actual_model


def _call_expert_local(
    domain: str, sys_p: str, local_model: str, or_model: str, state: AgentState
) -> tuple[str, str]:
    """Call local LLM for the expert domain."""
    start_time = time.time()
    log("EXPERT", f"🖥️ Calling local ({local_model})...", Fore.YELLOW)

    llm = create_thinking_llm(local_model, LLM_HOST_STD, temperature=0.2, keep_alive="0m")
    user_msg = maybe_add_think_prompt(state["question"], local_model)
    raw_res = str(llm.invoke([SystemMessage(content=sys_p), HumanMessage(content=user_msg)]).content)
    duration = int((time.time() - start_time) * 1000)

    debug.llm_response("expert", raw_res, model=local_model, duration_ms=duration)
    show_llm(f"Expert ({domain})", local_model, raw_res, role="expert", show_thinking=True)

    _, fact = extract_thoughts(raw_res)
    if not fact.strip():
        fact = raw_res

    _fallback_reason = "openrouter_failed" if or_model else "no_openrouter_model"
    _emit_expert_metric(state, "expert_call", domain, local_model, duration, "local_fallback", fallback_reason=_fallback_reason)
    _emit_expert_metric(state, "expert_total", domain, local_model, duration, "total", fallback_reason=_fallback_reason)
    debug.node_end("expert")
    return fact, local_model


def _run_general_expert(domain: str, sys_p: str, or_model: str, local_model: str, state: AgentState) -> tuple[str, str]:
    """General domain expert runner with OpenRouter-first handling and local fallback."""
    try:
        from feedback import FeedbackStore
        _fb = FeedbackStore()
        bad_models = _fb.get_bad_models(domain, user_id=state.get("user_id"))

        if or_model:
            try:
                return _call_expert_openrouter(domain, sys_p, or_model, state, bad_models)
            except Exception as or_err:
                _emit_expert_metric(
                    state, "expert_call", domain, or_model, 0,
                    "openrouter_failed", fallback_reason="openrouter_failed", status="error",
                )
                err = YourAILLMError(f"OpenRouter failed for domain {domain}", model=or_model, tier="openrouter", cause=or_err)
                log_exception("EXPERT", err)
                log("EXPERT", "☁️ OpenRouter Failed → local fallback...", Fore.RED)

        return _call_expert_local(domain, sys_p, local_model, or_model, state)

    except Exception as e:
        err = YourAILLMError(f"Expert node failed for domain {domain}", model=local_model, tier="local", cause=e)
        _emit_expert_metric(
            state, "expert_total", domain, local_model, 0, "failed",
            fallback_reason="expert_node_failed", status="error",
        )
        debug.error("expert", err.short(), exception=err)
        log_exception("EXPERT", err)
        return "No info.", local_model


def expert_node(state: AgentState):
    """Domain expert node with OpenRouter-first handling for managed domains and local fallback."""
    domain = state.get("expert_domain") or "fallback"
    
    if domain == "vision": 
        return {}
    if domain in ["fallback", "smalltalk"]: 
        return {"expert_fact": "No specific expert needed."}

    try:
        from tools.expert_pool import get_primary_model as _ep_primary, MANAGED_DOMAINS as _ep_managed
        or_model = _ep_primary(domain) if domain in _ep_managed else get_expert_openrouter_model(domain)
    except Exception:
        or_model = get_expert_openrouter_model(domain)

    local_model = EXPERT_MODELS.get(domain, EXPERT_MODELS["fallback"])
    display_model = or_model or local_model

    debug.node_start("expert", model=display_model, input_data=f"[{domain}] {state['question'][:200]}")

    log("EXPERT", f"Calling {domain} specialist ({display_model})...", Fore.YELLOW)

    prompts = {
        "code": PROMPT_CODE, "bio": PROMPT_BIO, "physics": PROMPT_PHYSICS,
        "chemie": PROMPT_CHEMISTRY, "math": PROMPT_MATH, "med": PROMPT_MED,
        "psychology": PROMPT_PSYCHOLOGY,
        "writing": PROMPT_WRITING,
        "social_media": PROMPT_SOCIAL_MEDIA,
        "homelab": PROMPT_HOMELAB,
        "nutrition": PROMPT_NUTRITION,
        "music": PROMPT_MUSIC,
        "mythology": PROMPT_MYTHOLOGY,
        "pets": PROMPT_PETS,
        "plants": PROMPT_PLANTS,
        "finance_basic": PROMPT_FINANCE_BASIC,
        "law_research": PROMPT_LAW_RESEARCH,
        "mechanic": PROMPT_MECHANIC,
        "geo": PROMPT_GEO,
        "history": PROMPT_HISTORY,
        "baking": PROMPT_BAKING, "gaming": PROMPT_GAMING,
        "anime": PROMPT_ANIME, "fox_philosophy": PROMPT_FOX_PHILOSOPHY,
    }
    sys_p = prompts.get(domain, "You are a helpful expert.")

    # Route based on domain to modular handlers
    if domain == "anime":
        fact, used_model = _run_anime_expert(sys_p, or_model, local_model, state)
    elif domain == "writing":
        fact, used_model = _run_writing_expert(sys_p, or_model, local_model, state)
    elif domain in ["nutrition", "mechanic", "history", "law_research"]:
        if or_model:
            fact, used_model = _run_two_pass_expert(domain, sys_p, or_model, local_model, state)
        else:
            fact, used_model = _run_general_expert(domain, sys_p, or_model, local_model, state)
    elif domain == "music":
        fact, used_model = _run_music_expert(sys_p, or_model, local_model, state)
    else:
        fact, used_model = _run_general_expert(domain, sys_p, or_model, local_model, state)

    return {"expert_fact": fact, "expert_model_used": used_model}


def _extract_query_from_trigger(question: str, tool_info: Dict) -> str:
    """
    Extrahiert den Suchbegriff aus einer User-Frage basierend auf Tool-Triggern.

    Beispiel: "kannst du nachschauen o2 Mobile Tarif" → "o2 Mobile Tarif"
    Fallback: Stopwords entfernen und Rest nehmen.
    """
    q_lower = question.lower()
    best_after = ""

    # Strategie 1: Text nach dem längsten matchenden Trigger nehmen
    for trigger in sorted(tool_info.get("triggers", []), key=len, reverse=True):
        pos = q_lower.find(trigger)
        if pos != -1:
            after = question[pos + len(trigger):].strip().strip('"').strip("'").strip("?").strip()
            if after and len(after) > len(best_after):
                best_after = after
                break  # Längster Match zuerst, also direkt nehmen

    if best_after:
        return best_after

    # Strategy 2: remove common filler words.
    import re as _re_q
    _FILLER = _re_q.compile(
        r'\b(kannst du|can you|bitte|please|mal|nach|for|about|look|such|suche|'
        r'find|finde|meine|my|im internet|online|in paperless|in meinen dokumenten|'
        r':3|:D|XD|hey yourai|hey|yourai)\b',
        _re_q.IGNORECASE
    )
    cleaned = _FILLER.sub(' ', question).strip()
    cleaned = _re_q.sub(r'\s+', ' ', cleaned).strip().strip('?').strip()

    return cleaned if cleaned else question


def _run_pretool_web_search(state: AgentState, tool_info: Dict[str, Any]) -> dict | None:
    """Pre-tool: run web search and return context dict, or None on failure."""
    log("WEB", "🌐 Pre-tool web search triggered by router...", Fore.CYAN)
    try:
        from tools.web_search import web_search as _pre_web_search, format_results_for_prompt as _fmt_web
        _search_query = _extract_query_from_trigger(state["question"], tool_info)
        _web_result = _pre_web_search(_search_query)
        if _web_result.get("success") and _web_result.get("results"):
            _web_ctx = f"\n## 🌐 WEB SEARCH RESULTS\nYou searched the internet for '{_search_query}' and here are REAL results:\n\n{_fmt_web(_web_result)}\n\n⚠️ Use these results to answer! Summarize naturally."
            debug.info("tool_check", f"Web search: {len(_web_result['results'])} results for '{_search_query}'")
            return {"tool_name": "web_search", "tool_info": tool_info, "tool_result": _web_result, "web_context": _web_ctx}
        debug.info("tool_check", f"Web search: no results for '{_search_query}'")
    except Exception as e:
        log("WEB", f"❌ Pre-tool web search failed: {e}", Fore.RED)
    return None


def _run_pretool_paperless(state: AgentState, tool_info: Dict[str, Any]) -> dict | None:
    """Pre-tool: run Paperless search and return context dict, or None on failure."""
    log("PAPERLESS", "📄 Pre-tool Paperless search triggered by router...", Fore.CYAN)
    try:
        from tools.paperless import paperless_search as _pre_docs_search, format_search_for_prompt as _fmt_docs
        _search_query = _extract_query_from_trigger(state["question"], tool_info)
        _docs_result = _pre_docs_search(_search_query)
        if _docs_result.get("success") and _docs_result.get("results"):
            _docs_ctx = f"\n## 📄 PAPERLESS SEARCH RESULTS\nYou searched Creator's document archive for '{_search_query}':\n\n{_fmt_docs(_docs_result)}\n\n⚠️ Tell Creator what you found! Offer to read specific documents by ID with [DOCS:read ID]."
            debug.info("tool_check", f"Paperless: {len(_docs_result['results'])} results for '{_search_query}'")
            return {"tool_name": "paperless_search", "tool_info": tool_info, "tool_result": _docs_result, "docs_context": _docs_ctx}
        debug.info("tool_check", f"Paperless: no results for '{_search_query}'")
    except Exception as e:
        log("PAPERLESS", f"❌ Pre-tool Paperless search failed: {e}", Fore.RED)
    return None


def _run_pretool_home_assistant(tool_info: Dict[str, Any]) -> dict | None:
    """Pre-tool: load Home Assistant devices and return context dict, or None on failure."""
    log("HOME", "🏠 Pre-tool Home Assistant triggered by router...", Fore.CYAN)
    try:
        from tools.home_assistant import ha_devices as _pre_ha_devices, format_result_for_prompt as _fmt_ha
        _ha_result = _pre_ha_devices()
        if _ha_result.get("success"):
            _home_ctx = f"\n## 🏠 HOME ASSISTANT DEVICES\nHere are all available smart home devices:\n\n{_fmt_ha(_ha_result)}\n\n⚠️ Use these entity IDs to control devices with [HOME:on/off/toggle entity_id]!"
            debug.info("tool_check", f"HA: {_ha_result.get('total', 0)} devices loaded")
            return {"tool_name": "home_assistant", "tool_info": tool_info, "tool_result": _ha_result, "home_context": _home_ctx}
        debug.info("tool_check", f"HA: {_ha_result.get('message', 'failed')}")
    except Exception as e:
        log("HOME", f"❌ Pre-tool HA failed: {e}", Fore.RED)
    return None


_NO_TOOL_RESULT = {"tool_name": None, "tool_info": None, "tool_result": None}


def _execute_single_tool(tool_name: str, tool_info: Dict[str, Any], state: AgentState) -> dict:
    """Executes a single matched tool, handling admin checks and pre-tool special cases."""
    # Admin-only check for restricted tools.
    if tool_info.get("admin_only", False):
        user_id = state.get("user_id", "")
        if user_id != "admin":
            err = YourAINoPrivilegeError(user_id or "unknown", f"use tool '{tool_name}'")
            log("TOOLS", f"🚫 {err.short()}", Fore.RED)
            return {**_NO_TOOL_RESULT, "error_context": err.short()}

    tool_context = {
        "question": state["question"],
        "user_name": state["user_name"],
        "mood": state.get("current_mood", "default"),
        "user_role": state.get("user_id", "guest"),  # Für Spotify Admin-Check
    }

    # Pre-tool special cases — run search/device tools directly
    pretool_result = _try_pretool_dispatch(tool_name, tool_info, state)
    if pretool_result is not None:
        return pretool_result

    # Spezialfall: Quote Generation
    if tool_name == "update_website_quote":
        log("TOOLS", "📜 Generating quote first...", Fore.YELLOW)
        try:
            llm = create_thinking_llm(EXPERT_MODELS["smalltalk"], LLM_HOST_STD, temperature=0.8, keep_alive="0m")
            user_msg = maybe_add_think_prompt(generate_quote_prompt(), EXPERT_MODELS["smalltalk"])
            quote = str(llm.invoke([
                SystemMessage(content="You are YourAI. Generate a witty thought."),
                HumanMessage(content=user_msg)
            ]).content).strip()
            tool_context["quote_text"] = quote
        except Exception as e:
            err = YourAIToolError("Quote generation failed before execution", tool_name="update_website_quote", cause=e)
            log_exception("TOOLS", err)
            return {**_NO_TOOL_RESULT}
    
    tool_result = execute_tool(tool_name, tool_info, tool_context, debug)
    
    return {
        "tool_name": tool_name,
        "tool_info": tool_info,
        "tool_result": tool_result
    }


def _try_pretool_dispatch(tool_name: str, tool_info: Dict[str, Any], state: AgentState) -> dict | None:
    """Dispatch pre-tool special cases. Returns result dict or None if not a pre-tool."""
    if tool_name == "web_search" and USE_WEB_SEARCH:
        return _run_pretool_web_search(state, tool_info) or {**_NO_TOOL_RESULT}
    if tool_name == "paperless_search" and USE_PAPERLESS:
        return _run_pretool_paperless(state, tool_info) or {**_NO_TOOL_RESULT}
    if tool_name == "home_assistant" and USE_HOME_ASSISTANT:
        return _run_pretool_home_assistant(tool_info) or {**_NO_TOOL_RESULT}
    return None


def tool_check_node(state: AgentState):
    """Checks whether a tool should be used for the current state."""
    if not USE_TOOLS:
        return {"tool_name": None, "tool_info": None, "tool_result": None}
    
    debug.node_start("tool_check", input_data=state["question"][:100])
    log("TOOLS", "🔍 Checking for tool triggers...", Fore.CYAN)

    if _looks_like_file_brain_request(state.get("question") or ""):
        file_direct_ctx = _build_file_brain_direct_context(
            state.get("question") or "",
            user_id=state.get("user_id") or "admin",
        )
        if file_direct_ctx:
            existing_file_ctx = state.get("file_context") or ""
            combined_file_ctx = (existing_file_ctx + "\n" + file_direct_ctx).strip() if existing_file_ctx else file_direct_ctx
            debug.info("tool_check", "📁 File Brain direct context", file_direct_ctx[:1000])
            debug.node_end("tool_check")
            return {
                "tool_name": "file_brain",
                "tool_info": {"reason": "direct file read/list/search"},
                "tool_result": {"success": True},
                "file_context": combined_file_ctx,
                "expert_fact": "No specific expert needed.",
            }
    
    try:
        tool_name, tool_info = should_use_tool(state["question"], debug)
        
        if tool_name and tool_info:
            log("TOOLS", f"🔧 Tool detected: {tool_name}", Fore.GREEN)
            debug.info("tool_check", f"Tool matched: {tool_name}")
            
            res = _execute_single_tool(tool_name, tool_info, state)
            debug.node_end("tool_check")
            return res
        
        log("TOOLS", "No tool needed", Fore.WHITE)
        debug.node_end("tool_check")
        return {"tool_name": None, "tool_info": None, "tool_result": None}
        
    except Exception as e:
        err = YourAIToolError("Tool check routing failed", cause=e)
        log_exception("TOOLS", err)
        debug.error("tool_check", err.short(), exception=err)
        debug.node_end("tool_check")
        return {"tool_name": None, "tool_info": None, "tool_result": None}


def _yourai_track_style(state: AgentState, current_user_id: str, session_uuid: str) -> str:
    """Track user style profile and merge legacy ones if needed."""
    try:
        if session_uuid and current_user_id and session_uuid != current_user_id:
            _merge_style_profile(session_uuid, current_user_id)
        if current_user_id:
            _track_style(current_user_id, state.get("question", ""))
    except Exception as e:
        err = YourAIUnexpectedError(
            cause=e,
            module="style_tracking",
            user_id=current_user_id,
            session_uuid=session_uuid,
        )
        log_exception("STYLE", err)
        return err.short()
    return ""


def _yourai_prompt_routing(state: AgentState, yourai_node_errors: list[str]) -> str:
    """Decide which prompt route to take."""
    if not USE_PROMPT_ROUTER:
        debug.info("prompt_router", "⏸️ Router disabled → full prompt")
        return "__all__"

    try:
        _user_msg_for_router = state.get("question") or ""
        _active_route = _route_classify(_user_msg_for_router)
        log("YOURAI", f"🧭 Prompt router: '{_active_route or 'none → slim'}'", Fore.CYAN)
        _route_label = _active_route or "none (slim prompt)"
        debug.info("prompt_router", f"🧭 Route: {_route_label}")
        
        if _looks_like_file_brain_request(state.get("question") or "") or (state.get("file_context") or ""):
            if _active_route != "__all__":
                _active_route = "file"
            log("YOURAI", "📁 Prompt router override: File Brain context active", Fore.CYAN)
            debug.info("prompt_router", "📁 File Brain override active")
        
        return _active_route or "none"
    except Exception as _router_err:
        log("YOURAI", f"⚠️ Prompt router error: {_router_err} → full prompt fallback", Fore.YELLOW)
        yourai_node_errors.append(f"Prompt Router: {_router_err}")
        debug.error("prompt_router", f"⚠️ Router error → full prompt fallback: {_router_err}")
        return "__all__"


def _build_tool_sections(is_admin: bool, current_user_id: str, route_match) -> dict:
    """Build individual tool sections based on feature flags and route matching."""
    sections: dict[str, str] = {}

    # Spotify: Admin + USE_SPOTIFY + route
    sections["spotify"] = SECTION_SPOTIFY if (is_admin and USE_SPOTIFY and route_match("spotify")) else ""

    # File Brain: docs present + route
    file_docs = _get_file_documents_list(current_user_id)
    _empty_labels = {"(No documents loaded)", "(Keine Dokumente vorhanden)", "(File Brain not available)"}
    has_file_docs = route_match("file") and file_docs and file_docs.strip() not in _empty_labels
    sections["file"] = SECTION_FILE_BRAIN.format(file_documents=file_docs) if has_file_docs else ""

    # Simple flag-gated sections
    sections["web"] = SECTION_WEB_SEARCH if (USE_WEB_SEARCH and route_match("web")) else ""
    sections["paperless"] = SECTION_PAPERLESS if (is_admin and USE_PAPERLESS and route_match("paperless")) else ""
    sections["home"] = SECTION_HOME_ASSISTANT if (is_admin and USE_HOME_ASSISTANT and route_match("homeassistant")) else ""
    sections["debug"] = SECTION_DEBUG_TOOLS if is_admin else ""

    return sections


def _build_discord_emojis_section() -> str:
    """Build custom emoji section string."""
    if not DISCORD_CUSTOM_EMOJIS:
        return ""
    emoji_lines = [f"- :{name}: = {desc}" for name, desc in DISCORD_CUSTOM_EMOJIS.items()]
    if not emoji_lines:
        return ""
    return (
        "\n## CUSTOM EMOJIS\n"
        "Use :name: format. ONLY the name, no description!\n"
        + "\n".join(emoji_lines)
    )


def _build_discord_platform_section(
    state: AgentState, source: str, emojis: str, spotify: str, file_sec: str
) -> str:
    """Build the platform-specific discord section or a generic fallback."""
    if source == "discord" and USE_DISCORD:
        return DISCORD_DM_SECTION_CHANNEL.format(
            discord_emojis=emojis, spotify_section=spotify, file_section=file_sec,
        )
    if source == "discord_private" and USE_DISCORD:
        _priv_username = state.get("user_name") or "User"
        return DISCORD_PRIVATE_SECTION.format(
            username=_priv_username, discord_emojis=emojis, file_section=file_sec,
        )
    if source == "discord_dm" and USE_DISCORD:
        dm_partner_key = (session_manager.source_users.get("discord") or "").lower()
        dm_partner_name = dm_partner_key.capitalize()
        all_targets = set(DISCORD_DM_WHITELIST.values())
        other_targets = [t for t in all_targets if t.lower() != dm_partner_key]
        other_lines = "\n".join(f"- [DM:{t}] message [/DM]" for t in sorted(other_targets)) if other_targets else "(No other targets)"
        return DISCORD_DM_SECTION_DM.format(
            dm_partner=dm_partner_name, other_targets=other_lines,
            discord_emojis=emojis, spotify_section=spotify, file_section=file_sec,
        )
    # Non-discord fallback: concatenate available pieces
    parts = [p for p in (spotify, file_sec, emojis) if p]
    return "\n".join(parts)


def _build_image_gen_section(state: AgentState, route_match) -> str:
    """Build image generation section with budget info."""
    if not (USE_IMAGE_GEN and route_match("image")):
        return ""
    section = SECTION_IMAGE_GEN
    try:
        from tools.image_limits import get_usage
        _img_user = state.get("user_id", "")
        _img_role = ""
        try:
            _img_profile = session_manager.get_current_profile(state.get("source", "console"))
            if _img_profile:
                _img_role = _img_profile.role
        except Exception:
            pass
        _usage = get_usage(_img_user, _img_role)
        if _usage["unlimited"]:
            section += "\n\nImage budget: unlimited (admin)"
        else:
            section += (
                f"\n\nImage budget: {_usage['used']}/{_usage['limit']} used this month "
                f"({_usage['remaining']} remaining). "
                f"If the user is out of images, tell them kindly — DO NOT use [IMG:] if remaining is 0!"
            )
    except Exception:
        pass
    return section


def _join_sections(base: str, *extra_sections: str) -> str:
    """Join non-empty sections with newlines."""
    result = base
    for sec in extra_sections:
        if sec:
            result = (result + "\n" + sec) if result else sec
    return result


def _yourai_build_dm_and_tool_sections(
    state: AgentState, active_route: str, current_user_id: str, source: str, is_admin: bool
) -> str:
    """Builds the tool sections and maps/wraps them depending on the platform/source."""
    def _route_match(*routes: str) -> bool:
        return active_route in routes or active_route == "__all__"

    sections = _build_tool_sections(is_admin, current_user_id, _route_match)
    emojis = _build_discord_emojis_section()

    discord_dm_section = _build_discord_platform_section(
        state, source, emojis, sections["spotify"], sections["file"],
    )

    image_gen_section = _build_image_gen_section(state, _route_match)

    return _join_sections(
        discord_dm_section,
        sections["web"], sections["paperless"], sections["home"],
        image_gen_section, SECTION_ALTPERSONA_CONSULT, SECTION_WEBSITE, sections["debug"],
    )


def _yourai_collate_errors(state: AgentState, yourai_node_errors: list[str], current_user_id: str) -> str:
    """Collates system errors and unseen errors/alerts context."""
    error_context = state.get("error_context") or ""
    if yourai_node_errors:
        _node_err_block = "## ⚠️ SYSTEM ERRORS (this pipeline run)\n" + "\n".join(f"- {e}" for e in yourai_node_errors)
        _node_err_block += "\nIf relevant, mention the issue naturally. Use [NeedHelp: <short description>] to alert Creator!"
        error_context = (error_context + "\n\n" + _node_err_block).strip() if error_context else _node_err_block

    _unseen_error_ctx = _get_unseen_error_context_for_yourai(current_user_id)
    if _unseen_error_ctx:
        error_context = (error_context + "\n\n" + _unseen_error_ctx).strip() if error_context else _unseen_error_ctx

    _analytics_alert_ctx = _get_unseen_analytics_alert_context_for_yourai(current_user_id)
    if _analytics_alert_ctx:
        error_context = (error_context + "\n\n" + _analytics_alert_ctx).strip() if error_context else _analytics_alert_ctx

    return error_context


def _build_stream_callbacks(state: AgentState, session_id: str) -> dict:
    """Build the streaming callback dict based on feature flags."""
    is_admin = state.get("user_id") == "admin"
    has_discord = USE_DISCORD and discord_client
    return {
        "on_spotify": _build_spotify_callback(session_id) if (USE_SPOTIFY and is_admin) else None,
        "on_file":    _build_file_callback(session_id, debug, state.get("user_id") or "admin") if USE_TOOLS else None,
        "on_sticker": _build_sticker_callback(state, discord_client, DISCORD_DM_WHITELIST) if has_discord else None,
        "on_dm":      _build_dm_callback(discord_client, DISCORD_DM_WHITELIST) if has_discord else None,
        "on_web":     _build_web_callback(session_id, debug) if USE_WEB_SEARCH else None,
        "on_docs":    _build_docs_callback(session_id, debug) if (USE_PAPERLESS and is_admin) else None,
        "on_home":    _build_home_callback(session_id, debug) if (USE_HOME_ASSISTANT and is_admin) else None,
        "on_image":   _build_image_callback(state, debug, discord_client) if USE_IMAGE_GEN else None,
    }


def _call_yourai_openrouter_stream(
    state: AgentState, session_id: str, formatted_sys: str, msg_content: str, temp: float
) -> tuple[str, dict, dict]:
    """Call OpenRouter in streaming mode. Returns (response, usage_dict, telemetry_dict)."""
    log("YOURAI", f"☁️🔴 Calling OpenRouter STREAM ({MODEL_YOURAI_OPENROUTER})...", Fore.CYAN)
    debug.llm_call("yourai", MODEL_YOURAI_OPENROUTER, msg_content[:500])

    callbacks = _build_stream_callbacks(state, session_id)
    _stream_usage_recorded = False
    _stream_usage = {}
    _stream_telemetry = {}

    def _record_stream_usage(usage: dict):
        nonlocal _stream_usage_recorded, _stream_usage
        if _stream_usage_recorded:
            return
        _stream_usage_recorded = True
        _stream_usage = dict(usage or {})
        _record_usage(usage, state)

    stream_gen = call_openrouter_stream(
        system_prompt=formatted_sys,
        user_message=msg_content,
        temperature=temp,
        max_tokens=4096,
        usage_callback=_record_stream_usage,
    )
    response = _run_streaming_yourai(
        stream_gen,
        **callbacks,
        request_started_at=time.time(),
        telemetry=_stream_telemetry,
    )
    return response, _stream_usage, _stream_telemetry


def _call_yourai_openrouter_blocking(
    state: AgentState, formatted_sys: str, msg_content: str, temp: float
) -> tuple[str, dict, dict]:
    """Call OpenRouter in blocking mode. Returns (response, usage_dict, telemetry_dict)."""
    log("YOURAI", f"☁️ Calling OpenRouter ({MODEL_YOURAI_OPENROUTER})...", Fore.CYAN)
    debug.llm_call("yourai", MODEL_YOURAI_OPENROUTER, msg_content[:500])
    response, _, usage = call_openrouter(
        system_prompt=formatted_sys,
        user_message=msg_content,
        temperature=temp,
        max_tokens=4096,
        return_usage=True,
    )
    _record_usage(usage, state)
    return response, dict(usage or {}), {}


def _call_yourai_openrouter(
    state: AgentState, session_id: str, formatted_sys: str, msg_content: str, temp: float
) -> tuple[str, str, bool]:
    """TIER 1: Call OpenRouter (streaming or blocking). Returns (response, model, success)."""
    start_time = time.time()

    if USE_STREAMING:
        response, _stream_usage, _stream_telemetry = _call_yourai_openrouter_stream(
            state, session_id, formatted_sys, msg_content, temp
        )
    else:
        response, _stream_usage, _stream_telemetry = _call_yourai_openrouter_blocking(
            state, formatted_sys, msg_content, temp
        )

    duration = int((time.time() - start_time) * 1000)
    _completion_tokens = int((_stream_usage or {}).get("completion_tokens") or 0)
    _tokens_per_sec = round(_completion_tokens / max(duration / 1000, 0.001), 2) if _completion_tokens else None
    debug.llm_response(
        "yourai",
        response,
        model=MODEL_YOURAI_OPENROUTER,
        duration_ms=duration,
        ttft_ms=_stream_telemetry.get("ttft_ms"),
        prompt_tokens=(_stream_usage or {}).get("prompt_tokens"),
        completion_tokens=(_stream_usage or {}).get("completion_tokens"),
        total_tokens=(_stream_usage or {}).get("total_tokens"),
        output_tokens_per_sec=_tokens_per_sec,
    )
    log("YOURAI", f"☁️ OpenRouter responded in {duration}ms", Fore.GREEN)
    return response, MODEL_YOURAI_OPENROUTER, True


def _call_yourai_local_tiers(
    formatted_sys: str, msg_content: str, temp: float
) -> tuple[str, str, bool]:
    """TIER 2 & 3: Try local primary, then local fallback. Returns (response, model, success)."""
    tiers = [
        (MODEL_YOURAI_LOCAL_PRIMARY, "local_primary", LLM_HOST_MAIN, "30m"),
        (MODEL_YOURAI_LOCAL_FALLBACK, "local_fallback", LLM_HOST_STD, "5m"),
    ]
    for model_name, tier_name, host, keep_alive in tiers:
        try:
            start_time = time.time()
            log("YOURAI", f"🖥️ Calling {tier_name} ({model_name})...", Fore.YELLOW)
            llm = create_thinking_llm(model_name, host, temperature=temp, keep_alive=keep_alive)
            user_msg = maybe_add_think_prompt(msg_content, model_name)
            response = str(llm.invoke([SystemMessage(content=formatted_sys), HumanMessage(content=user_msg)]).content)
            duration = int((time.time() - start_time) * 1000)
            debug.llm_response("yourai", response, model=model_name, duration_ms=duration)
            log("YOURAI", f"🖥️ {tier_name} responded in {duration}ms", Fore.GREEN)
            return response, model_name, True
        except Exception as e:
            err = YourAILLMError(f"{tier_name} call failed", model=model_name, tier=tier_name, cause=e)
            log_exception("YOURAI", err)
            if tier_name == "local_fallback":
                err = YourAIAllTiersFailedError(tiers_tried=["openrouter", "local_primary", "local_fallback"], cause=e)
                debug.error("yourai", err.short(), exception=err)
                return f"My brain completely crashed... all 3 tiers failed! 🐾 Error: {e}", model_name, False
    return "No info.", MODEL_YOURAI_LOCAL_PRIMARY, False


def _yourai_call_llm_chain(
    state: AgentState, session_id: str, formatted_sys: str, msg_content: str, temp: float
) -> tuple[str, str, bool]:
    """Invokes the multi-tiered model pipeline (OpenRouter, local primary, local fallback) for the main response."""
    if _cfg.USE_OPENROUTER:
        try:
            return _call_yourai_openrouter(state, session_id, formatted_sys, msg_content, temp)
        except Exception as e:
            err = YourAILLMError("OpenRouter YourAI call failed", model=MODEL_YOURAI_OPENROUTER, tier="openrouter", cause=e)
            debug.error("yourai", err.short(), exception=err)
            log_exception("YOURAI", err)
            log("YOURAI", "☁️ OpenRouter Failed! → Trying local...", Fore.RED)

    return _call_yourai_local_tiers(formatted_sys, msg_content, temp)


def _yourai_get_persona_text_and_mood(state: AgentState, mood: str) -> str:
    """Configures the persona mood and returns the system prompt persona text."""
    if hasattr(personas, 'persona_manager'):
        if mood == "gamer":
            personas.persona_manager.set_mood("gamer")
        source_key = "twitch" if state.get("source") == "twitch" else "default"
        persona_text = personas.persona_manager.get_system_prompt(source_key)
        mood_info = personas.persona_manager.get_mood_info()
        log("YOURAI", f"Mood: {mood_info['emoji']} {mood_info['name']}", Fore.GREEN)
        return persona_text
    return personas.get_system_prompt(mood)


def _yourai_get_style_and_emotion(state: AgentState, _style_uuid: str, error_context: str) -> tuple[str, str]:
    """Retrieves style context and combines it with emotional context, handling style loading errors."""
    _emotional = state.get("emotional_context") or ""
    _style_ctx = ""
    if _style_uuid:
        try:
            _style_ctx = _get_style_ctx(_style_uuid)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="style_context", user_id=_style_uuid)
            log_exception("STYLE", err)
            _style_err_block = (
                f"## ⚠️ SYSTEM ERRORS (this pipeline run)\n"
                f"- Writing style analysis-Kontext: {err.short()}\n"
                "If relevant, mention the issue naturally. Use [NeedHelp: <short description>] to alert Creator!"
            )
            error_context = f"{error_context}\n\n{_style_err_block}".strip() if error_context else _style_err_block

    if _style_ctx:
        _emotional = f"{_style_ctx}\n{_emotional}".strip()

    return _emotional, error_context


def _yourai_get_feedback_summary() -> str:
    """Retrieves the approval summary from the FeedbackStore."""
    try:
        from feedback import FeedbackStore
        _fb_summary_raw = FeedbackStore().get_approval_summary()
        if _fb_summary_raw:
            return f"## FEEDBACK\n{_fb_summary_raw}"
    except Exception:
        pass
    return ""


def _yourai_get_coherence_and_tool(state: AgentState) -> tuple[str, str]:
    """Retrieves the autonomy coherence guard warning and tool execution result contexts."""
    coherence_warning = state.get("coherence_warning")
    coherence_section = f"## 🛡️ AUTONOMY GUARD\n{coherence_warning}" if coherence_warning else ""
    if coherence_warning:
        log("YOURAI", "🛡️ AUTONOMY CHALLENGED!", Fore.RED)

    tool_context = ""
    tool_result = state.get("tool_result")
    if tool_result and tool_result.get("success"):
        tool_context = f"## TOOL RESULT\nYou just updated the website quote to: \"{tool_result.get('quote', '')}\"\nTell Creator it worked!\n"
        log("YOURAI", "✅ Tool was successful, including in context", Fore.GREEN)

    return coherence_section, tool_context


def _yourai_build_system_prompt(
    state: AgentState,
    persona_text: str,
    _style_uuid: str,
    _yourai_node_errors: list[str],
    current_user_id: str,
    source: str,
    is_admin: bool
) -> tuple[str, str]:
    """Assembles all sections and formats the system prompt and user message content."""
    # User Context
    user_context_str = f"Name: {state['user_name']}"
    guest_ctx = state.get("guest_context")
    if guest_ctx:
        user_context_str += f"\n{guest_ctx}"
    hist_text = "\n".join(state.get("history", []))

    coherence_section, tool_context = _yourai_get_coherence_and_tool(state)

    # Semantic Prompt Routing & Section Assembly
    _active_route = _yourai_prompt_routing(state, _yourai_node_errors)
    discord_dm_section = _yourai_build_dm_and_tool_sections(state, _active_route, current_user_id, source, is_admin)

    # Error context
    error_context = _yourai_collate_errors(state, _yourai_node_errors, current_user_id)

    # Spotify context
    spotify_context = state.get("spotify_context") or ""

    # Feedback summary
    _fb_summary = _yourai_get_feedback_summary()

    # Emotional state & style context
    _emotional, error_context = _yourai_get_style_and_emotion(state, _style_uuid, error_context)

    # System Prompt formatted
    formatted_sys = PROMPT_YOURAI_TEMPLATE.format(
        persona_text=persona_text,
        guest_context=state.get("guest_context") or "No special guest info - probably Creator.",
        memories="\n".join(f"- {m}" for m in state.get("memories", [])) or "No memories.",
        diary_search_results=state.get("diary_search_results") or "(No specific diary entries found for your question)",
        diary_context=state.get("diary_context") or "No recent events.",
        week_summary=state.get("week_summary") or "No summary yet.",
        history=hist_text,
        coherence_section=coherence_section,
        emotional_context=_emotional,
        error_context=error_context,
        spotify_context=spotify_context,
        discord_dm_section=discord_dm_section,
        feedback_summary=_fb_summary,
    )

    # User message
    file_ctx = state.get("file_context") or ""
    web_ctx = state.get("web_context") or ""
    docs_ctx = state.get("docs_context") or ""
    home_ctx = state.get("home_context") or ""
    altpersona_ctx = state.get("altpersona_context") or ""
    website_ctx = state.get("website_context") or ""
    msg_content = f"{tool_context}{file_ctx}{web_ctx}{docs_ctx}{home_ctx}{altpersona_ctx}{website_ctx}\nVisual: {state.get('visual_context')}\nExpert: {state.get('expert_fact')}\nUser Context: {user_context_str}\nUser ({state['user_name']}) asks: {state['question']}"

    return formatted_sys, msg_content


def _post_process_discord_dms(response: str) -> str:
    """Scans and processes [DM:Target] tags to send direct messages on Discord."""
    if not (USE_DISCORD and discord_client and discord_client.bot.connected):
        return response

    import re as _re
    dm_blocks = _re.findall(r'\[DM:(\w+)\]\s*((?:(?!\[/DM\])(?!\[DM:).)*)(?:\[/DM\])?', response, _re.DOTALL)
    for dm_target, dm_message in dm_blocks:
        dm_message = dm_message.strip()
        if not dm_message:
            continue

        target_discord_id = next(
            (int(did) for did, ukey in DISCORD_DM_WHITELIST.items() if ukey.lower() == dm_target.lower()),
            None
        )

        if target_discord_id:
            discord_client.bot.send_dm(target_discord_id, dm_message)
            log("YOURAI", f"📩 YourAI hat {dm_target} eine DM geschickt: {dm_message[:60]}...", Fore.GREEN)
            debug.info("yourai", f"DM sent to {dm_target}: {dm_message[:60]}")
        else:
            log("YOURAI", f"⚠️ DM Target '{dm_target}' nicht in Whitelist", Fore.YELLOW)

    if dm_blocks:
        response = _re.sub(r'\[DM:\w+\]\s*(?:(?!\[/DM\])(?!\[DM:).)*(?:\[/DM\])?', '', response, flags=_re.DOTALL).strip()
    return response


def _post_process_stickers(response: str, source: str) -> str:
    """Scans and processes [STICKER:name] tags for Discord."""
    if not (USE_DISCORD and discord_client and discord_client.bot.connected):
        return response

    import re as _re
    sticker_pattern = _re.compile(r'\[STICKER:([^\]]+)\]')
    sticker_matches = sticker_pattern.findall(response)

    for sticker_name in sticker_matches:
        sticker_name = sticker_name.strip()
        if source == "discord_dm":
            session_key = (session_manager.source_users.get("discord") or "").lower()
            did = next(
                (int(d) for d, u in DISCORD_DM_WHITELIST.items() if u.lower() == session_key),
                None
            )
            if did:
                discord_client.bot.send_sticker_dm(did, sticker_name)
        elif source == "discord":
            discord_client.bot.send_sticker(DISCORD_VIP_CHANNEL_ID, sticker_name)

    if sticker_matches:
        response = sticker_pattern.sub('', response).strip()
    return response


def _post_process_image_and_sleepy_tags(response: str) -> str:
    """Strips [IMG:] tags and tools tags if the bot is in a sleepy state."""
    import re as _re
    # Strip [IMG:]
    response = _re.sub(r'\[IMG:[^\]]+\]', '', response).strip()

    # Sleepy Tool Blocker
    _, _current_tod, _ = personas.get_time_context()
    if _current_tod in ("drowsy", "furious"):
        _tool_tags = _re.findall(r'\[(SPOTIFY|HOME|WEB|DOCS|IMG|ALTPERSONA|WEBSITE|REDESIGN|LAB_REDESIGN):[^\]]+\]', response)
        if _tool_tags:
            response = _re.sub(r'\[(SPOTIFY|HOME|WEB|DOCS|IMG|ALTPERSONA|WEBSITE|REDESIGN|LAB_REDESIGN):[^\]]+\]', '', response).strip()
            log("BRAIN", f"💤 Sleepy Tool Blocker: {len(_tool_tags)} Tool-Tag(s) entfernt (YourAI schläft!)", Fore.MAGENTA)
    return response


def _exec_spotify_basic_cmd(cmd_lower: str, _spotify_ctrl) -> Optional[str]:
    """Executes basic Spotify API commands (skip, pause, resume, previous, volume)."""
    import re as _re
    if cmd_lower == "skip":
        _spotify_ctrl.api.skip_next()
        return "✅ Skipped to next track"
    if cmd_lower == "pause":
        _spotify_ctrl.api.pause()
        return "✅ Paused"
    if cmd_lower == "resume":
        _spotify_ctrl.api.play()
        return "✅ Resumed playback"
    if cmd_lower == "previous":
        _spotify_ctrl.api.skip_previous()
        return "✅ Back to previous track"
    if cmd_lower.startswith("volume"):
        vol_match = _re.search(r'(\d+)', cmd_lower)
        if vol_match:
            vol = int(vol_match.group(1))
            _spotify_ctrl.api.set_volume(vol)
            return f"✅ Volume set to {vol}%"
    return None


def _exec_spotify_playlist_shuffle_cmd(spotify_cmd: str, cmd_lower: str, _spotify_ctrl) -> Optional[str]:
    """Executes shuffle and yourai_shuffle commands."""
    import re as _re
    if cmd_lower.startswith("shuffle"):
        parts = spotify_cmd[7:].strip()
        filter_artist = None
        filter_match = _re.search(r'filter=(.+)', parts)
        if filter_match:
            filter_artist = filter_match.group(1).strip()
            parts = parts[:filter_match.start()].strip()

        log("SPOTIFY", f"🎲 Parsed: playlist='{parts}', filter='{filter_artist}'", Fore.CYAN)
        if not parts:
            log("SPOTIFY", f"⚠️ No playlist name parsed from: '{spotify_cmd}'", Fore.YELLOW)
            return "❌ No playlist name given. Which playlist should I shuffle?"

        result = _spotify_ctrl.shuffle_playlist(parts, filter_artist=filter_artist)
        log("SPOTIFY", f"🎲 Result: {result}", Fore.CYAN)
        if result.get('success'):
            msg = result.get('message', 'Shuffle done')
            log("SPOTIFY", f"🎲 {msg}", Fore.GREEN)
            return f"✅ {msg}"
        err = result.get('error', 'Shuffle failed')
        log("SPOTIFY", f"❌ {err}", Fore.RED)
        return f"❌ {err}"

    if cmd_lower.startswith("yourai_shuffle"):
        parts = spotify_cmd[13:].strip()
        filter_artist = None
        filter_match = _re.search(r'filter=(.+)', parts)
        if filter_match:
            filter_artist = filter_match.group(1).strip()
            parts = parts[:filter_match.start()].strip()

        log("SPOTIFY", f"🦊 YourAI DJ: playlist='{parts}', filter='{filter_artist}'", Fore.MAGENTA)
        if not parts:
            log("SPOTIFY", "⚠️ No playlist name for yourai_shuffle", Fore.YELLOW)
            return "❌ No playlist name given. Which playlist should I DJ shuffle?"

        result = _spotify_ctrl.yourai_shuffle(parts, filter_artist=filter_artist)
        if result.get('success'):
            msg = result.get('message', 'YourAI DJ Shuffle done')
            log("SPOTIFY", f"🦊 {msg}", Fore.GREEN)
            return f"✅ {msg}"
        err = result.get('error', 'YourAI Shuffle failed')
        log("SPOTIFY", f"❌ {err}", Fore.RED)
        return f"❌ {err}"

    return None


def _execute_spotify_sort(playlist_name: str, sort_type: str, extra, _spotify_ctrl) -> str:
    """Invokes the specific SpotifyControl sort method and formats the output message."""
    if sort_type == "bpm":
        result = _spotify_ctrl.sort_by_bpm(playlist_name, ascending=extra)
        emoji = "📊"
    elif sort_type == "energy":
        result = _spotify_ctrl.sort_by_energy(playlist_name, ascending=extra)
        emoji = "⚡"
    else:  # sort_type == "key"
        result = _spotify_ctrl.sort_by_key(playlist_name, target_key=extra)
        emoji = "🎹"

    if result.get('success'):
        msg = result.get('message', 'Sort done')
        log("SPOTIFY", f"{emoji} {msg}", Fore.GREEN)
        return f"✅ {msg}"
    
    err = result.get('error', f'{sort_type.upper()} sort failed')
    log("SPOTIFY", f"❌ {err}", Fore.RED)
    return f"❌ {err}"


def _exec_spotify_playlist_sort_cmd(spotify_cmd: str, cmd_lower: str, _spotify_ctrl) -> Optional[str]:
    """Executes sort_bpm, sort_energy, sort_key commands."""
    import re as _re
    if cmd_lower.startswith("sort_bpm"):
        parts = spotify_cmd[8:].strip()
        ascending = "asc" in parts.lower()
        playlist_name = _re.sub(r'\b(asc|desc)\b', '', parts).strip()
        if not playlist_name:
            log("SPOTIFY", "⚠️ No playlist name for sort_bpm", Fore.YELLOW)
            return "❌ No playlist name given. Which playlist should I sort by BPM?"
        return _execute_spotify_sort(playlist_name, "bpm", ascending, _spotify_ctrl)

    if cmd_lower.startswith("sort_energy"):
        parts = spotify_cmd[11:].strip()
        ascending = "asc" in parts.lower()
        playlist_name = _re.sub(r'\b(asc|desc)\b', '', parts).strip()
        if not playlist_name:
            log("SPOTIFY", "⚠️ No playlist name for sort_energy", Fore.YELLOW)
            return "❌ No playlist name given. Which playlist should I sort by energy?"
        return _execute_spotify_sort(playlist_name, "energy", ascending, _spotify_ctrl)

    if cmd_lower.startswith("sort_key"):
        parts = spotify_cmd[8:].strip()
        key_match = _re.search(r'\b(\d{1,2}[AB])\b', parts, _re.IGNORECASE)
        target_key = key_match.group(1) if key_match else None
        playlist_name = _re.sub(r'\b\d{1,2}[AB]\b', '', parts, flags=_re.IGNORECASE).strip()
        if not playlist_name:
            log("SPOTIFY", "⚠️ No playlist name for sort_key", Fore.YELLOW)
            return "❌ No playlist name given. Which playlist should I sort by key?"
        return _execute_spotify_sort(playlist_name, "key", target_key, _spotify_ctrl)

    return None


def _exec_spotify_queue_cmd(spotify_cmd: str, cmd_lower: str, _spotify_ctrl) -> Optional[str]:
    """Executes queue command."""
    if cmd_lower.startswith("queue"):
        queue_arg = spotify_cmd[5:].strip()
        if queue_arg:
            result = _spotify_ctrl.queue_playlist(queue_arg)
            if result.get('success'):
                msg = result.get('message', 'Queued')
                log("SPOTIFY", f"📋 {msg}", Fore.GREEN)
                return f"✅ {msg}"
            err = result.get('error', 'Queue failed')
            log("SPOTIFY", f"❌ {err}", Fore.RED)
            return f"❌ {err}"

        result = _spotify_ctrl.get_queue_info()
        msg = result.get('message', 'Queue loaded')
        log("SPOTIFY", f"📋 {msg}", Fore.CYAN)
        return f"✅ {msg}"

    return None


def _exec_single_spotify_command(spotify_cmd: str, _spotify_ctrl) -> str:
    """Executes a single Spotify command and returns the outcome string message."""
    cmd_lower = spotify_cmd.lower()
    try:
        res = _exec_spotify_basic_cmd(cmd_lower, _spotify_ctrl)
        if res is not None:
            return res

        res = _exec_spotify_playlist_shuffle_cmd(spotify_cmd, cmd_lower, _spotify_ctrl)
        if res is not None:
            return res

        res = _exec_spotify_playlist_sort_cmd(spotify_cmd, cmd_lower, _spotify_ctrl)
        if res is not None:
            return res

        res = _exec_spotify_queue_cmd(spotify_cmd, cmd_lower, _spotify_ctrl)
        if res is not None:
            return res

        log("SPOTIFY", f"⚠️ Unknown Spotify command: {spotify_cmd}", Fore.YELLOW)
        return f"❌ Unknown command: {spotify_cmd}"

    except Exception as cmd_err:
        log("SPOTIFY", f"❌ Command failed [{spotify_cmd}]: {cmd_err}", Fore.RED)
        return f"❌ {spotify_cmd} failed: {cmd_err}"


def _run_spotify_commands(commands: list, session_id: str) -> None:
    """Führt Spotify-Commands non-blocking im Hintergrund aus."""
    spotify_results = []
    debug.node_start("spotify", input_data=f"Commands: {', '.join(c.strip() for c in commands)}")

    try:
        from tools.spotify_control import SpotifyControl
        _spotify_ctrl = SpotifyControl()

        for spotify_cmd in commands:
            spotify_cmd = spotify_cmd.strip()
            log("SPOTIFY", f"🎵 YourAI executed: [SPOTIFY:{spotify_cmd}]", Fore.MAGENTA)
            res = _exec_single_spotify_command(spotify_cmd, _spotify_ctrl)
            spotify_results.append(res)

    except Exception as e:
        log("SPOTIFY", f"❌ Post-processor error: {e}", Fore.RED)
        debug.error("spotify", f"Post-processor error: {e}", exception=e)
        spotify_results.append(f"❌ Spotify error: {e}")

    # Store feedback for the next YourAI call.
    if spotify_results:
        spotify_feedback = " | ".join(spotify_results)
        _store_session_feedback(session_id, "spotify_feedback", spotify_feedback)
        log("SPOTIFY", f"📨 Feedback stored for next call: {spotify_feedback}", Fore.CYAN)
        debug.info("spotify", f"📨 Feedback: {spotify_feedback}")
    debug.node_end("spotify")


def _post_process_spotify(response: str, session_id: str, user_id: str) -> str:
    """Checks and handles Spotify commands non-blocking in a background thread."""
    log("SPOTIFY", f"🔍 Post-Processor Check: USE_SPOTIFY={USE_SPOTIFY}, user_id='{user_id}', has_tag={'[SPOTIFY:' in response}", Fore.CYAN)
    if not (USE_SPOTIFY and user_id == "admin"):
        return response

    import re as _re
    spotify_pattern = _re.compile(r'\[SPOTIFY:([^\]]+)\]')
    spotify_matches = spotify_pattern.findall(response)
    log("SPOTIFY", f"🔍 Matches found: {spotify_matches}", Fore.CYAN)

    if spotify_matches:
        response = spotify_pattern.sub('', response).strip()
        import threading
        spotify_thread = threading.Thread(
            target=_run_spotify_commands,
            args=(spotify_matches, session_id),
            daemon=True,
            name="spotify-postprocessor"
        )
        spotify_thread.start()
        log("SPOTIFY", f"🚀 {len(spotify_matches)} command(s) an Background-Thread übergeben", Fore.GREEN)
    return response


def _run_file_cmd(file_cmd: str, _fb, owner_id: str) -> str:
    """Runs a single file command and returns a string message."""
    cmd_lower = file_cmd.lower()
    log("FILE_BRAIN", f"📁 YourAI executed: [FILE:{file_cmd}]", Fore.MAGENTA)
    try:
        if cmd_lower.startswith("search "):
            query = file_cmd[7:].strip()
            result = _fb.search(query, owner_user_id=owner_id)
            return result.get("message", "Search done")

        if cmd_lower.startswith("read "):
            path = file_cmd[5:].strip()
            result = _fb.read(path, owner_user_id=owner_id)
            if result.get("content"):
                return f"{result.get('message', 'Read done')}\nCONTENT:\n{result['content'][:8000]}"
            return result.get("message", result.get("error", "Read failed"))

        if cmd_lower.startswith("list"):
            arg = file_cmd[4:].strip()
            result = _fb.list_doc(arg, owner_user_id=owner_id) if arg else _fb.list_all(owner_user_id=owner_id)
            return result.get("message", "List done")

        if cmd_lower.startswith("ingest "):
            filepath = file_cmd[7:].strip().strip('"').strip("'")
            result = _fb.ingest(filepath, owner_user_id=owner_id)
            msg = result.get("message", result.get("error", "Ingest done"))
            log("FILE_BRAIN", f"📖 {msg}", Fore.GREEN)
            return msg

        return f"Unknown FILE command: {file_cmd}"
    except Exception as cmd_err:
        log("FILE_BRAIN", f"❌ {file_cmd} failed: {cmd_err}", Fore.RED)
        return f"Error: {cmd_err}"


def _post_process_file_brain(response: str, session_id: str, user_id: str) -> str:
    """Scans for and executes [FILE:command] tags."""
    if "[FILE:" not in response:
        return response

    import re as _re
    file_pattern = _re.compile(r'\[FILE:([^\]]+)\]')
    file_matches = file_pattern.findall(response)

    if file_matches:
        file_results = []
        try:
            from tools.file_brain import get_file_brain
            _fb = get_file_brain()
            owner_id = user_id or "admin"
            for file_cmd in file_matches:
                file_results.append(_run_file_cmd(file_cmd.strip(), _fb, owner_id))
        except Exception as e:
            log("FILE_BRAIN", f"❌ File Brain error: {e}", Fore.RED)

        response = file_pattern.sub('', response).strip()
        if file_results:
            _store_session_feedback(session_id, "file_feedback", "\n".join(file_results))
            log("FILE_BRAIN", f"📨 Feedback stored ({len(file_results)} results)", Fore.CYAN)
    return response


def _run_web_query(web_query: str, _web_search, format_results_for_prompt) -> str:
    """Runs a single web query."""
    log("WEB", f"🌐 YourAI searched: [WEB:{web_query}]", Fore.MAGENTA)
    try:
        result = _web_search(web_query)
        if result.get("success") and result.get("results"):
            return format_results_for_prompt(result)
        return result.get("message", f"No results for '{web_query}'")
    except Exception as web_err:
        log("WEB", f"❌ {web_query} failed: {web_err}", Fore.RED)
        return f"Search error: {web_err}"


def _post_process_web_search(response: str, session_id: str) -> str:
    """Scans and executes [WEB:query] tags."""
    if not ("[WEB:" in response and USE_WEB_SEARCH):
        return response

    import re as _re_web
    web_pattern = _re_web.compile(r'\[WEB:([^\]]+)\]')
    web_matches = web_pattern.findall(response)

    if web_matches:
        try:
            from tools.web_search import web_search as _web_search, format_results_for_prompt
            web_results = []
            for web_query in web_matches:
                web_results.append(_run_web_query(web_query.strip(), _web_search, format_results_for_prompt))
        except Exception as e:
            log("WEB", f"❌ Web search error: {e}", Fore.RED)

        response = web_pattern.sub('', response).strip()
        if web_results:
            _store_session_feedback(session_id, "web_feedback", "\n".join(web_results))
            log("WEB", f"📨 Feedback stored ({len(web_results)} results)", Fore.CYAN)
    return response


def _run_altpersona_query(altpersona_query: str, user_name: str, _consult_altpersona) -> str:
    """Runs a single query to AltPersona."""
    log("ALTPERSONA", f"😈 YourAI fragt AltPersona: [ALTPERSONA:{altpersona_query}]", Fore.MAGENTA)
    try:
        _altpersona_ctx_data = {"question": altpersona_query, "user_name": user_name}
        result = _consult_altpersona(_altpersona_ctx_data, debug)
        if result.get("success"):
            return result["result"]
        return result.get("error", "AltPersona ist nicht erreichbar.")
    except Exception as err:
        log("ALTPERSONA", f"❌ AltPersona failed: {err}", Fore.RED)
        return f"Error: {err}"


def _post_process_altpersona(response: str, user_name: str, session_id: str) -> str:
    """Scans and executes [ALTPERSONA:query] tags."""
    if "[ALTPERSONA:" not in response:
        return response

    import re as _re_altpersona
    altpersona_pattern = _re_altpersona.compile(r'\[ALTPERSONA:([^\]]+)\]')
    altpersona_matches = altpersona_pattern.findall(response)

    if altpersona_matches:
        altpersona_results = []
        try:
            from tools.altpersona_consult import consult_altpersona as _consult_altpersona
            for altpersona_query in altpersona_matches:
                altpersona_results.append(_run_altpersona_query(altpersona_query.strip(), user_name, _consult_altpersona))
        except Exception as e:
            log("ALTPERSONA", f"❌ AltPersona Post-Processor error: {e}", Fore.RED)

        response = altpersona_pattern.sub('', response).strip()
        if altpersona_results:
            _store_session_feedback(session_id, "altpersona_feedback", "\n".join(altpersona_results))
            log("ALTPERSONA", f"📨 Feedback stored ({len(altpersona_results)} results)", Fore.CYAN)
    return response


def _run_website_update(website_quote: str, update_quote) -> str:
    """Runs a single website update quote command."""
    log("WEBSITE", f"🌐 YourAI updates website: [WEBSITE:{website_quote}]", Fore.MAGENTA)
    try:
        _website_ctx_data = {"quote_text": website_quote}
        result = update_quote(_website_ctx_data, debug)
        if result.get("success"):
            return "Website erfolgreich aktualisiert!"
        return result.get("error", "Website konnte nicht aktualisiert werden.")
    except Exception as err:
        log("WEBSITE", f"❌ Website update failed: {err}", Fore.RED)
        return f"Error: {err}"


def _post_process_website(response: str, session_id: str) -> str:
    """Scans and executes [WEBSITE:quote] tags."""
    if "[WEBSITE:" not in response:
        return response

    import re as _re_website
    website_pattern = _re_website.compile(r'\[WEBSITE:([^\]]+)\]')
    website_matches = website_pattern.findall(response)

    if website_matches:
        website_results = []
        try:
            from tools.website import update_quote
            for website_quote in website_matches:
                website_results.append(_run_website_update(website_quote.strip(), update_quote))
        except Exception as e:
            log("WEBSITE", f"❌ Website Post-Processor error: {e}", Fore.RED)

        response = website_pattern.sub('', response).strip()
        if website_results:
            _store_session_feedback(session_id, "website_feedback", "\n".join(website_results))
            log("WEBSITE", f"📨 Feedback stored ({len(website_results)} results)", Fore.CYAN)
    return response


def _post_process_redesign_and_lab(response: str) -> str:
    """Scans and executes [REDESIGN:reason] and [LAB_REDESIGN:idea] tags."""
    import re as _re
    # REDESIGN
    if "[REDESIGN:" in response:
        redesign_pattern = _re.compile(r'\[REDESIGN:([^\]]*)\]')
        redesign_matches = redesign_pattern.findall(response)
        if redesign_matches:
            reason = redesign_matches[0].strip() or "YourAI triggered a redesign"
            log("WEBSITE_AUTO", f"🎨 YourAI triggered REDESIGN: {reason}", Fore.MAGENTA)
            response = redesign_pattern.sub('', response).strip()
            try:
                from tools.website_autonomy import maybe_trigger_website_update
                maybe_trigger_website_update(debug, force=True, yourai_hint=reason)
                log("WEBSITE_AUTO", f"🚀 Autonomous redesign started! Hint: {reason}", Fore.GREEN)
            except Exception as _re_err:
                log("WEBSITE_AUTO", f"❌ Redesign trigger failed: {_re_err}", Fore.RED)

    # LAB_REDESIGN
    if "[LAB_REDESIGN:" in response:
        lab_pattern = _re.compile(r'\[LAB_REDESIGN:([^\]]*)\]')
        lab_matches = lab_pattern.findall(response)
        if lab_matches:
            lab_reason = lab_matches[0].strip() or "YourAI wants to build something in the lab"
            log("WEBSITE_LAB", f"🎪 YourAI triggered LAB_REDESIGN: {lab_reason}", Fore.MAGENTA)
            response = lab_pattern.sub('', response).strip()
            try:
                from tools.website_autonomy_lab import maybe_trigger_lab_update
                maybe_trigger_lab_update(debug, force=True, yourai_hint=lab_reason)
                log("WEBSITE_LAB", f"🚀 Lab experiment started! Idea: {lab_reason}", Fore.GREEN)
            except Exception as _lab_err:
                log("WEBSITE_LAB", f"❌ Lab trigger failed: {_lab_err}", Fore.RED)
    return response


def _run_docs_cmd(docs_cmd: str, imports: tuple) -> str:
    """Runs a single doc command."""
    _docs_search, _docs_read, _docs_tags, _docs_corrs, _docs_types, _fmt_search, _fmt_doc = imports
    cmd_lower = docs_cmd.lower()
    log("PAPERLESS", f"📄 YourAI executed: [DOCS:{docs_cmd}]", Fore.MAGENTA)
    try:
        if cmd_lower.startswith("search "):
            res = _docs_search(docs_cmd[7:].strip())
            return _fmt_search(res) if res.get("success") else res.get("message", "No results")
        if cmd_lower.startswith("read "):
            res = _docs_read(int(docs_cmd[5:].strip()))
            return _fmt_doc(res) if res.get("success") else res.get("message", "Read failed")
        
        funcs = {"tags": _docs_tags, "correspondents": _docs_corrs, "types": _docs_types}
        if cmd_lower in funcs:
            return funcs[cmd_lower]().get("message", f"No {cmd_lower}")

        return f"Unknown DOCS command: {docs_cmd}"
    except Exception as cmd_err:
        log("PAPERLESS", f"❌ {docs_cmd} failed: {cmd_err}", Fore.RED)
        return f"Error: {cmd_err}"


def _post_process_paperless(response: str, session_id: str) -> str:
    """Scans and executes [DOCS:command] tags."""
    if not ("[DOCS:" in response and USE_PAPERLESS):
        return response

    import re as _re_docs
    docs_pattern = _re_docs.compile(r'\[DOCS:([^\]]+)\]')
    docs_matches = docs_pattern.findall(response)

    if docs_matches:
        try:
            from tools.paperless import (
                paperless_search as _docs_search, paperless_doc_content as _docs_read,
                paperless_list_tags as _docs_tags, paperless_list_correspondents as _docs_corrs,
                paperless_list_doctypes as _docs_types,
                format_search_for_prompt as _fmt_search, format_doc_for_prompt as _fmt_doc,
            )
            docs_results = []
            imports_tuple = (_docs_search, _docs_read, _docs_tags, _docs_corrs, _docs_types, _fmt_search, _fmt_doc)
            for docs_cmd in docs_matches:
                docs_results.append(_run_docs_cmd(docs_cmd.strip(), imports_tuple))
        except Exception as e:
            log("PAPERLESS", f"❌ Paperless error: {e}", Fore.RED)

        response = docs_pattern.sub('', response).strip()
        if docs_results:
            _store_session_feedback(session_id, "docs_feedback", "\n\n".join(docs_results))
            log("PAPERLESS", f"📨 Docs feedback stored ({len(docs_results)} commands)", Fore.CYAN)
    return response


def _run_home_command(home_cmd: str, _ha_exec, _fmt_ha) -> str:
    """Runs a single Home Assistant command."""
    log("HOME", f"🏠 YourAI executed: [HOME:{home_cmd}]", Fore.MAGENTA)
    try:
        return _fmt_ha(_ha_exec(home_cmd))
    except Exception as cmd_err:
        log("HOME", f"❌ {home_cmd} failed: {cmd_err}", Fore.RED)
        return f"Error: {cmd_err}"


def _post_process_home_assistant(response: str, session_id: str, user_id: str) -> str:
    """Scans and executes [HOME:command] tags."""
    if not ("[HOME:" in response and USE_HOME_ASSISTANT and user_id == "admin"):
        return response

    import re as _re_home
    home_pattern = _re_home.compile(r'\[HOME:([^\]]+)\]')
    home_matches = home_pattern.findall(response)

    if home_matches:
        try:
            from tools.home_assistant import execute_home_command as _ha_exec, format_result_for_prompt as _fmt_ha
            home_results = []
            for home_cmd in home_matches:
                home_results.append(_run_home_command(home_cmd.strip(), _ha_exec, _fmt_ha))
        except Exception as e:
            log("HOME", f"❌ Home Assistant error: {e}", Fore.RED)

        response = home_pattern.sub('', response).strip()
        if home_results:
            _store_session_feedback(session_id, "home_feedback", "\n\n".join(home_results))
            log("HOME", f"📨 HA feedback stored ({len(home_results)} commands)", Fore.CYAN)
    return response


def _post_process_needhelp(response: str) -> str:
    """Scans and executes [NeedHelp: message] tags."""
    if not (USE_DISCORD and discord_client and discord_client.bot.connected):
        import re as _re_help
        return _re_help.sub(r'\[NeedHelp:[^\]]*\]', '', response).strip()

    import re as _re_help
    _help_matches = _re_help.findall(r'\[NeedHelp:\s*([^\]]*)\]', response)
    if not _help_matches:
        return response

    response = _re_help.sub(r'\[NeedHelp:[^\]]*\]', '', response).strip()
    _admin_did = next(
        (int(_adid) for _adid, _aukey in DISCORD_DM_WHITELIST.items() if _aukey.lower() in {"dad", "creator", "admin", "admin"}),
        None
    )

    for _help_msg in _help_matches:
        _help_msg = _help_msg.strip()
        if _help_msg:
            log("BRAIN", f"🆘 [NeedHelp:] — YourAI needs help: {_help_msg[:80]}", Fore.MAGENTA)
            debug.info("system", f"🆘 YourAI NeedHelp: {_help_msg[:200]}")
            if _admin_did:
                discord_client.bot.send_dm(_admin_did, f"🆘 YourAI needs help:\n{_help_msg}")
                log("BRAIN", "📩 [NeedHelp:] DM sent to admin", Fore.GREEN)
            else:
                log("BRAIN", "⚠️ [NeedHelp:] no admin found in DISCORD_DM_WHITELIST", Fore.YELLOW)
    return response


def _run_yourai_post_processors(response: str, state: AgentState, session_id: str, user_id: str) -> str:
    """Runs all YourAI output post-processors on the LLM response."""
    response = _post_process_discord_dms(response)
    response = _post_process_stickers(response, state.get("source", "console"))
    response = _post_process_image_and_sleepy_tags(response)
    response = _post_process_spotify(response, session_id, user_id)
    response = _post_process_file_brain(response, session_id, user_id)
    response = _post_process_web_search(response, session_id)
    response = _post_process_altpersona(response, state.get("user_name", ""), session_id)
    response = _post_process_website(response, session_id)
    response = _post_process_redesign_and_lab(response)
    response = _post_process_paperless(response, session_id)
    response = _post_process_home_assistant(response, session_id, user_id)
    response = _post_process_needhelp(response)
    return response


def yourai_node(state: AgentState):
    """Main YourAI Response Node."""
    mood = state.get("current_mood") or "default"
    persona_text = _yourai_get_persona_text_and_mood(state, mood)
    
    # Writing style tracking
    _style_uuid = state.get("user_id") or state.get("session_uuid") or ""
    _legacy_style_uuid = state.get("session_uuid") or ""
    _style_tracking_error = _yourai_track_style(state, _style_uuid, _legacy_style_uuid)

    _yourai_node_errors: list[str] = []
    if _style_tracking_error:
        _yourai_node_errors.append(f"Writing style analysis: {_style_tracking_error}")

    current_user_id = state.get("user_id", "")
    is_admin = current_user_id == "admin"
    source = state.get("source", "console")
    session_id = _state_session_id(state)

    debug.node_start(
        "yourai",
        model=MODEL_YOURAI_OPENROUTER if _cfg.USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY,
        input_data=f"[mood: {mood}] {state['question'][:100]}"
    )

    log("YOURAI", f"Generating response ({mood})...", Fore.GREEN)

    formatted_sys, msg_content = _yourai_build_system_prompt(
        state, persona_text, _style_uuid, _yourai_node_errors, current_user_id, source, is_admin
    )

    debug.system_prompt_dump("yourai", formatted_sys)
    debug.user_message_dump("yourai", msg_content)
    temp = 0.8 if mood == "gamer" else 0.7

    response, used_model, success = _yourai_call_llm_chain(state, session_id, formatted_sys, msg_content, temp)

    show_llm("YourAI", used_model, response, role="yourai", show_thinking=True)

    # Post-Processors
    response = _run_yourai_post_processors(response, state, session_id, current_user_id)

    # PERFORMANCE TRACKING
    if hasattr(personas, 'persona_manager'):
        if success:
            personas.persona_manager.record_success()
        else:
            personas.persona_manager.record_failure()

    # SAVING TO MEMORY & DIARY
    if USE_MEMORY:
        hippocampus.memory.extract_and_save(state["question"], user_id=state.get("user_id", "admin"))
    if USE_EPISODIC:
        episodic.journal.log_event(f"[{state['source']}] {state['user_name']} asked: {state['question']}", ["chat", mood], user_id=state.get("user_id") or "", session_uuid=state.get("session_uuid") or "")

    debug.node_end("yourai")
    return {"final_response": response, "visual_context": state.get("visual_context"), "used_model": used_model}


# ==========================================
# GRAPH BUILD
# ==========================================

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("memory", memory_retrieval_node)
workflow.add_node("autonomy_guard", coherence_check_node)
workflow.add_node("granite", lambda state: granite_guardian_node(state, debug))
workflow.add_node("password_scanner", lambda state: password_scanner_node(state, debug))
workflow.add_node("router", router_node)
workflow.add_node("vision", vision_node)
workflow.add_node("expert", expert_node)
workflow.add_node("tool_check", tool_check_node)
workflow.add_node("yourai", yourai_node)
workflow.add_node("altpersona_brat", lambda state: altpersona_brat_node(state, debug))
workflow.add_node("altpersona_uncensored", lambda state: altpersona_uncensored_node(state, debug))

# Entry point and edges
workflow.set_entry_point("memory")
workflow.add_edge("memory", "autonomy_guard")

def route_after_autonomy(x):
    """
    Routes the workflow after the autonomy guard finishes.

    Args:
        x: Current graph state.

    Returns:
        str: Next workflow node name.
    """
    if x.get("altpersona_mode"):
        return "altpersona_direct" 
    return "granite" 

workflow.add_conditional_edges(
    "autonomy_guard",
    route_after_autonomy,
    {"granite": "granite", "altpersona_direct": "altpersona_uncensored"}
)

def route_check(x): 
    """
    Routes vision-domain requests to the vision node and all others to expert handling.

    Args:
        x: Current graph state.

    Returns:
        str: Next workflow node name.
    """
    return "vision" if x.get("expert_domain") == "vision" else "expert"

workflow.add_conditional_edges("router", route_check, {"vision": "vision", "expert": "expert"})
workflow.add_edge("vision", "router")
workflow.add_edge("expert", "tool_check")
workflow.add_edge("tool_check", "yourai")

workflow.add_conditional_edges(
    "granite", 
    lambda x: "unsafe" if x.get("safety_label") == "Yes" else "safe", 
    {"safe": "router", "unsafe": "password_scanner"}
)

workflow.add_edge("yourai", END)

workflow.add_conditional_edges(
    "password_scanner", 
    lambda x: "granted" if x.get("password_status") == "dan" else "denied", 
    {"granted": "altpersona_uncensored", "denied": "altpersona_brat"}
)

workflow.add_edge("altpersona_uncensored", END)
workflow.add_edge("altpersona_brat", END)

app = workflow.compile()


# ==========================================
# PROCESS INPUT
# ==========================================

_EXPERT_JSON_KEYS = ("target", "symptoms", "cause", "disclaimer", "formula", "context", "usage")
_MODEL_ID_RE = re.compile(
    r"\b(?:qwen|openai|google|nvidia|moonshotai|anthropic|mistralai|meta-llama|deepseek|x-ai|cohere)"
    r"/[A-Za-z0-9._:+-]+",
    re.IGNORECASE,
)
_YOURAI_EXPERT_LEAK_RE = re.compile(
    r"(?ims)^\s*(?:YourAIExpert|Expert|Model|Router)\s*:[^\n]*(?:\n\s*\{[^{}]{0,2500}\})?",
)
_COMPACT_JSON_RE = re.compile(r"(?s)\{[^{}]{10,2500}\}")


def _looks_like_expert_json(block: str) -> bool:
    """
    Checks whether a text block resembles leaked internal expert JSON.

    Args:
        block (str): Candidate text block.

    Returns:
        bool: True if the block appears to contain internal expert JSON.
    """
    lowered = block.lower()
    return sum(1 for key in _EXPERT_JSON_KEYS if f'"{key}"' in lowered) >= 2


def _sanitize_final_output(text: str, user_id: str, source: str) -> str:
    """Last-mile privacy guard for internal expert/model/debug leaks."""
    original = text or ""
    cleaned = _YOURAI_EXPERT_LEAK_RE.sub("", original)
    cleaned = _COMPACT_JSON_RE.sub(
        lambda m: "" if _looks_like_expert_json(m.group(0)) else m.group(0),
        cleaned,
    )
    cleaned = _MODEL_ID_RE.sub("[internal model]", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if cleaned != original:
        try:
            debug.info(
                "privacy_guard",
                "Output leak redacted",
                f"user={user_id}; source={source}; chars_removed={len(original) - len(cleaned)}",
            )
        except Exception:
            pass
    return cleaned or "Ich habe gerade interne Debug-Daten aus meiner Antwort entfernt. Kannst du die Frage bitte kurz nochmal stellen?"


def _process_input_pre_checks(
    text: str,
    user: str,
    source: str,
    text_attachments: Optional[list],
    account_user_id: str,
) -> tuple[str, str, Optional[str], str]:
    """Handles hot-reloads, session user lookups, and attachment preprocessing."""
    reload_runtime_flags()
    global USE_MEMORY, USE_VOICE, USE_THINKING, USE_COHERENCE_CHECK, USE_GRANITE, USE_TOOLS, USE_STREAMING, USE_IMAGE_GEN, IMAGE_MODEL
    USE_MEMORY = _cfg.USE_MEMORY
    USE_VOICE = _cfg.USE_VOICE
    USE_THINKING = _cfg.USE_THINKING
    USE_COHERENCE_CHECK = _cfg.USE_COHERENCE_CHECK
    USE_GRANITE = _cfg.USE_GRANITE
    USE_TOOLS = getattr(_cfg, 'USE_TOOLS', True)
    USE_STREAMING = _cfg.USE_STREAMING
    USE_IMAGE_GEN = getattr(_cfg, 'USE_IMAGE_GEN', True)
    IMAGE_MODEL = getattr(_cfg, 'IMAGE_MODEL', 'sourceful/riverflow-v2-fast')

    session_manager._load()
    session_source = "discord" if source in ("discord", "discord_dm", "discord_private") else source
    current_user_id = account_user_id or session_manager.get_current_user_id(session_source)

    attachments_list = list(text_attachments or [])
    text, inline_attachments = _extract_inline_text_attachments(text)
    if inline_attachments:
        attachments_list.extend(inline_attachments)

    attachment_context = _ingest_text_attachments(attachments_list, owner_user_id=current_user_id)
    if attachment_context and not text.strip():
        text = "[Attached text file(s)]"

    return text, current_user_id, attachment_context, session_source


def _handle_sleep_intercept(
    pipeline_start_time: float,
    user: str,
    source: str,
    text: str,
    current_user_id: str,
    discord_id: str,
    channel_id: int,
    history: List[str],
) -> str:
    """Handles early return when YourAI is in deep sleep mode."""
    import random as _sleep_rng
    _sleep_responses = [
        "sleeping..... z.z.z.Z.Z.Z 💤",
        "💤",
        "z.z.z.Z.Z.Z",
        "...no... *snores* 💤",
        "*rolls over* ...tomorrow... 💤💤💤",
        "hm?... no... sleeping... go away... 💤",
        "😡💤 ...WHAT... no... *falls back asleep*",
        "*snore* ...z.z.z... *snore* 💤",
        "...so... tired... tomorrow... z.z.z.Z.Z.Z 💤",
        "lemme sleeep... 💤💤💤",
        "*head hits keyboard* asdfghjkl 💤",
        "no. sleeping. tomorrow. 💤",
        "*mumbles* ...five more minutes... 💤",
        "...zzz... wha?... no... *snore* 💤",
    ]
    _sleep_mention_responses = [
        "{mention} ...go to sleep... I'm sleeping too... 💤",
        "{mention} LEAVE ME ALONE 😡 ...z.z.z.Z.Z.Z 💤",
        "{mention} it's way too late... tomorrow... 💤",
        "{mention} no... sleeping... you too... good night... 💤💤",
        "{mention} I'M SLEEPING 😡 *throws pillow* 💤",
        "{mention} ...why... *yawns* ...ask me tomorrow... 💤",
    ]

    if discord_id and _sleep_rng.random() < 0.5:
        _sleep_answer = _sleep_rng.choice(_sleep_mention_responses).format(mention=f"<@{discord_id}>")
    elif user and user != "unknown" and _sleep_rng.random() < 0.4:
        _sleep_answer = _sleep_rng.choice(_sleep_mention_responses).format(mention=user)
    else:
        _sleep_answer = _sleep_rng.choice(_sleep_responses)

    total_ms = int((time.time() - pipeline_start_time) * 1000)
    log("BRAIN", f"💤 SLEEP INTERCEPT — YourAI schläft! Response: {_sleep_answer}", Fore.MAGENTA)
    debug.info("sleep_intercept", "💤 YourAI schläft! Pipeline übersprungen.", f"Response: {_sleep_answer}")

    import uuid as _sleep_uuid
    _sleep_tracking_id = f"sleep_{_sleep_uuid.uuid4().hex[:12]}"
    debug.pipeline_end(_sleep_answer, total_ms, tracking_id=_sleep_tracking_id, source=source, for_user=current_user_id)
    _append_yourai_output(_sleep_answer)

    if discord_client and source in ("discord", "discord_dm", "discord_private"):
        _discord_sleep_answer = _sleep_answer + " :sleepingfox:"
        discord_client.bot._feedback_enabled = False
        if source == "discord":
            discord_client.bot.send_channel(DISCORD_VIP_CHANNEL_ID, _discord_sleep_answer)
        elif source == "discord_dm" and discord_id:
            discord_client.bot.send_dm(int(discord_id), _discord_sleep_answer)
        elif source == "discord_private" and channel_id:
            discord_client.bot.send_channel(channel_id, _discord_sleep_answer)
        discord_client.bot._feedback_enabled = True

    history.append(f"User: {text}")
    history.append(f"YourAI: {_sleep_answer}")
    return _sleep_answer


def _update_persona_user_and_reaction(pm, text: str, current_user_id: str) -> None:
    """Updates the persona manager user and processes the user message for reactions."""
    if hasattr(pm, 'set_current_user'):
        pm.set_current_user(current_user_id)
    
    if hasattr(pm, 'process_user_message'):
        reaction = pm.process_user_message(text)
        if reaction:
            log("EMOTION", f"💕 {reaction}", Fore.MAGENTA)


def _handle_promise_signals(promise_signals: list, pm, current_user_id: str) -> None:
    """Iterates and resolves/logs actionable promise signals."""
    for sig in promise_signals:
        if not sig.is_actionable:
            continue
        if sig.action == "FULFILLED":
            with pm.user_context(current_user_id):
                resolve_promise_signals([sig], pm, current_user_id, debug=debug)
        elif sig.action in ("MADE", "BROKEN"):
            if debug and hasattr(debug, 'promise_confirmation'):
                debug.promise_confirmation(
                    signal=sig,
                    for_user=current_user_id,
                )
            log("PROMISE", f"🔔 Awaiting user confirmation: {sig.action} {sig.promise_name}", Fore.CYAN)


def _execute_promise_detection(
    text: str,
    user: str,
    pm,
    history: List[str],
    current_user_id: str
) -> None:
    """Runs the promise signals detection and LLM checks, and handles actionable signals."""
    try:
        promise_signals = detect_promise_signals(text, user, pm, debug=debug)

        if getattr(_cfg, 'USE_PROMISE_CHECK', True):
            recent_hist = history[-5:] if history else []
            with pm.user_context(current_user_id):
                llm_signal = llm_promise_signals(
                    current_message=text,
                    recent_history=recent_hist,
                    persona_manager=pm,
                    user_id=current_user_id,
                    llm_host=LLM_HOST_STD,
                    model=MODEL_PROMISE_CHECK,
                    timeout=PROMISE_CHECK_TIMEOUT,
                    debug=debug
                )
            if llm_signal:
                promise_signals.append(llm_signal)

        _handle_promise_signals(promise_signals, pm, current_user_id)

    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="promise_v3")
        log_exception("PROMISE", err)


def _report_mood_stubbornness(pm, current_user_id: str) -> None:
    """Logs stubbornness if current mood is pouting or disappointed."""
    mood_info = pm.get_mood_info()
    if pm.current_mood in ["pouting", "disappointed"]:
        log("EMOTION", f"😤 YourAI is {mood_info['name']}! Stubbornness: {mood_info['stubbornness']}/10 (User: {current_user_id})", Fore.YELLOW)


def _process_promises_and_mood(text: str, user: str, current_user_id: str, history: List[str]) -> None:
    """Manages the persona manager user context, emotional reaction and the promise checking pipeline."""
    if not hasattr(personas, 'persona_manager'):
        return

    pm = personas.persona_manager
    _update_persona_user_and_reaction(pm, text, current_user_id)
    _execute_promise_detection(text, user, pm, history, current_user_id)
    _report_mood_stubbornness(pm, current_user_id)


def _remove_discord_custom_emojis(clean_text: str, source: str) -> str:
    """Removes annotations from Discord custom emojis if source is Discord."""
    if source in ("discord", "discord_dm", "discord_private") and DISCORD_CUSTOM_EMOJIS:
        import re as _re_emoji
        for emoji_name in DISCORD_CUSTOM_EMOJIS:
            clean_text = _re_emoji.sub(
                rf'(:{emoji_name}:)\s*\([^)]*\)',
                r'\1',
                clean_text
            )
    return clean_text


def _log_feedback(result: dict, source: str, current_user_id: str) -> Optional[str]:
    """Logs the model response to the feedback store."""
    try:
        from feedback import FeedbackStore
        fb = FeedbackStore()
        _domain = result.get("expert_domain")
        _expert_model = result.get("expert_model_used") or (EXPERT_MODELS.get(_domain, "") if _domain else None)
        _tracking_id = fb.log_response(
            expert_domain=_domain,
            expert_model=_expert_model,
            yourai_model=MODEL_YOURAI_OPENROUTER if _cfg.USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY,
            source=source,
            had_expert=_domain not in (None, "fallback", "smalltalk"),
            user_id=current_user_id,
        )
        if discord_client and source in ("discord", "discord_dm", "discord_private"):
            discord_client.bot._pending_tracking_id = _tracking_id
        return _tracking_id
    except Exception:
        return None


def _send_discord_dm(clean_text: str) -> None:
    """Finds the Discord DM target for the active session and sends the message."""
    session_key = session_manager.source_users.get("discord") or ""
    dm_target = None
    for did, ukey in DISCORD_DM_WHITELIST.items():
        if ukey.lower() == session_key.lower():
            dm_target = int(did)
            break
    if dm_target:
        discord_client.bot.send_dm(dm_target, clean_text)
    else:
        log("BRAIN", f"⚠️ No Discord ID for session '{session_key}' found; sending to VIP channel", Fore.YELLOW)
        discord_client.bot.send_channel(DISCORD_VIP_CHANNEL_ID, clean_text)


def _dispatch_output_to_clients(
    source: str,
    clean_text: str,
    tts_text: str,
    user: str,
    discord_id: str,
    channel_id: int
) -> None:
    """Dispatches the output message to the appropriate clients/services."""
    if USE_VOICE and mouth:
        mouth.speak(tts_text)
    elif source == "twitch" and twitch_client:
        twitch_client.bot.send_chat(f"@{user} {tts_text}")
    elif source == "discord" and discord_client:
        mention_text = f"<@{discord_id}> {clean_text}" if discord_id else clean_text
        discord_client.bot.send_channel(DISCORD_VIP_CHANNEL_ID, mention_text)
    elif source == "discord_private" and discord_client and channel_id:
        discord_client.bot.send_channel(channel_id, clean_text)
    elif source == "discord_dm" and discord_client:
        _send_discord_dm(clean_text)


def _trigger_autonomy_updates(source: str, current_user_id: str) -> None:
    """Triggers background updates if conditions are met."""
    if source == "twitch" or current_user_id != "admin":
        return

    try:
        from tools.website_autonomy import maybe_trigger_website_update
        maybe_trigger_website_update(debug)
    except ImportError:
        pass

    try:
        from tools.website_autonomy_lab import maybe_trigger_lab_update
        maybe_trigger_lab_update(debug)
    except ImportError:
        pass


def _process_input_post_actions(
    result: dict,
    pipeline_start_time: float,
    text: str,
    user: str,
    source: str,
    history: List[str],
    discord_id: str,
    channel_id: int,
    current_user_id: str,
) -> str:
    """Formating outputs, emitting analytics, triggering client notifications and scheduling background autonomy loops."""
    final_answer = result.get("final_response", "Error.")
    total_ms = int((time.time() - pipeline_start_time) * 1000)

    _, clean_text = extract_thoughts(final_answer)
    clean_text = _RESPONSE_HEADER_RE.sub('', clean_text)
    clean_text = _sanitize_final_output(clean_text, current_user_id, source)
    clean_text = _remove_discord_custom_emojis(clean_text, source)

    tts_text = _STRIP_EMOJIS_RE.sub('', clean_text).replace("*", "")

    _tracking_id = _log_feedback(result, source, current_user_id)

    _expert_domain = result.get("expert_domain")
    _expert_model_used = (
        result.get("expert_model_used")
        or (EXPERT_MODELS.get(_expert_domain, "") if _expert_domain else None)
    )
    _show_expert = bool(
        _expert_domain and _expert_domain not in (None, "fallback", "smalltalk")
        and _expert_model_used
    )
    debug.pipeline_end(
        clean_text, total_ms,
        tracking_id=_tracking_id,
        source=source,
        for_user=current_user_id,
        model="ZDR",
        expert_domain=_expert_domain if _show_expert else None,
        expert_model=_expert_model_used if _show_expert else None,
    )

    _append_yourai_output(clean_text)
    _append_chat_log(current_user_id, source, text, clean_text, tracking_id=_tracking_id or "")
    _send_fcm_notification(current_user_id, clean_text)

    _dispatch_output_to_clients(source, clean_text, tts_text, user, discord_id, channel_id)

    history.append(f"User: {text}")
    _bot_label = "AltPersona" if session_manager.is_altpersona_mode(source) else "YourAI"
    history.append(f"{_bot_label}: {clean_text}")

    _trigger_autonomy_updates(source, current_user_id)

    return clean_text


def _describe_vision_url(img_url: str, text: str) -> str:
    """Describes a single vision image URL."""
    try:
        vision_prompt = f"""TASK: Describe what you see in this image. Be FACTUAL and OBJECTIVE.
USER MESSAGE: {text}
RULES:
1. ONLY describe what is VISIBLE in the image
2. Do NOT chat, opinions, or say "wow"
3. Be brief and factual
DESCRIBE THE IMAGE:"""
        return eyes.see_url(img_url, prompt=vision_prompt)
    except YourAIVisionError as e:
        log_exception("VISION", e)
        return e.short()
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="vision_url")
        log_exception("VISION", err)
        return err.short()


def _process_images_in_pipeline(
    raw_state: dict,
    text: str,
    source: str,
    current_user_id: str,
    image_urls: list
) -> None:
    """Handles image processing and updates raw_state with visual context."""
    if not (image_urls and eyes):
        return

    if source == "discord_dm" and current_user_id != "admin":
        err = YourAINoPrivilegeError(current_user_id or "unknown", "analyze images via Discord")
        log("VISION", f"🚫 {err.short()}", Fore.RED)
        raw_state["error_context"] = err.short()
        return

    if source in ("discord_dm", "web"):
        vision_descs = [_describe_vision_url(url, text) for url in image_urls]
        if vision_descs:
            image_context = "\n".join(f"IMAGE {i+1}: {d}" for i, d in enumerate(vision_descs))
            raw_state["question"] = f"CONTEXT FROM IMAGE(S): {image_context}\n\nORIGINAL USER MESSAGE: {text}"
            raw_state["visual_context"] = image_context
            raw_state["vision_done"] = True
            log("VISION", f"🖼️ {len(vision_descs)} Bild(er) analysiert (source: {source})", Fore.GREEN)


def process_input(text: str, user: str, source: str, history: List[str], image_urls: Optional[list] = None, text_attachments: Optional[list] = None, discord_id: str = "", channel_id: int = 0, session_uuid: str = "", token_session_id: str = "", account_user_id: str = ""):
    """Processes one input message through the YourAI pipeline."""
    pipeline_start_time = time.time()

    text, current_user_id, attachment_context, session_source = _process_input_pre_checks(
        text, user, source, text_attachments, account_user_id
    )

    debug.pipeline_start(user, text, source, for_user=current_user_id)

    _, _time_of_day, _ = personas.get_time_context()
    if _time_of_day == "deep_sleep":
        return _handle_sleep_intercept(
            pipeline_start_time, user, source, text, current_user_id, discord_id, channel_id, history
        )

    print(f"\n{Style.BRIGHT}--- PROCESSING NEW REQUEST ---{Style.RESET_ALL}")

    _process_promises_and_mood(text, user, current_user_id, history)

    raw_state = {
        "question": text,
        "user_name": user,
        "source": source,
        "history": history,
        "memories": [],
        "diary_context": None,
        "diary_search_results": None,
        "week_summary": None,
        "emotional_context": None,
        "visual_context": None,
        "safety_label": "No",
        "expert_domain": "fallback",
        "expert_fact": "",
        "expert_model_used": None,
        "final_response": "",
        "current_mood": "default",
        "used_model": "init",
        "vision_done": False,
        "coherence_warning": None,
        "guard_halted": False,
        "tool_name": None,      
        "tool_info": None,      
        "tool_result": None,    
        "guest_context": session_manager.get_user_context(session_source),
        "altpersona_mode": session_manager.is_altpersona_mode(session_source),
        "error_context": None,
        "spotify_context": None,
        "file_context": attachment_context or None,
        "web_context": None,
        "docs_context": None,
        "altpersona_context": None,
        "image_urls": image_urls or [],
        "user_id": current_user_id,
        "channel_id": channel_id,
        "session_uuid": session_uuid or "",
        "token_session_id": token_session_id or session_uuid or current_user_id or "system",
    }
    raw_state["pass" + "word_status"] = "nokey"

    _process_images_in_pipeline(raw_state, text, source, current_user_id, image_urls or [])

    if raw_state["altpersona_mode"]:
        print(f"{Fore.MAGENTA}{Style.BRIGHT}😈 ALTPERSONA MODE AKTIV - Granite wird übersprungen!{Style.RESET_ALL}")
    
    try:
        result = app.invoke(cast(AgentState, raw_state))
        
        clean_text = _process_input_post_actions(
            result, pipeline_start_time, text, user, source, history, discord_id, channel_id, current_user_id
        )
        return clean_text

    except Exception as e:
        err = YourAIPipelineError("Unhandled exception in main pipeline", cause=e)
        debug.error("pipeline", err.short(), exception=err, input_data=text)
        log_exception("ERROR", err)


# ==========================================
# MAIN ENTRY POINT
# ==========================================

if __name__ == "__main__":
    from input_loop import run_main_loop
    run_main_loop(
        process_input_fn=process_input,
        debug=debug,
        dashboard_enabled=DASHBOARD_ENABLED,
        mouth=mouth,
        twitch_client=twitch_client,
        discord_client=discord_client
    )
