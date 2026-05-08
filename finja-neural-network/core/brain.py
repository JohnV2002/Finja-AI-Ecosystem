"""
YourAI Brain v5.0 (Modular Edition)
====================================
YourAIs Gehirn - jetzt richtig modular!

Module:
- text_parser.py    → Text-Parser (extract_thoughts, extract_json)
- safety.py         → Granite Guardian + Password Scanner
- altpersona.py           → AltPersona Brat + Uncensored Nodes
- input_loop.py     → Main Event Loop (Console, Web, Twitch)
- prompts.py        → Alle System Prompts
- config.py         → Konfiguration & Model-Helpers
- display.py        → Logging & Terminal-Ausgabe
- detection.py      → Promise/Emotion/Diary Detection
- autonomy_guard.py → Autonomy Guardian

Run: python brain.py
Dashboard: http://localhost:8050
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

from text_parser import extract_thoughts, extract_json_from_text

from prompts import (
    PROMPT_ROUTER_SYSTEM, PROMPT_YOURAI_TEMPLATE,
    PROMPT_BIO, PROMPT_MATH, PROMPT_PHYSICS, PROMPT_CHEMISTRY,
    PROMPT_CODE, PROMPT_MED, PROMPT_BAKING, PROMPT_GAMING,
    PROMPT_ANIME, PROMPT_FOX_PHILOSOPHY,
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
    DISCORD_VIP_CHANNEL_ID, DISCORD_DM_WHITELIST, DISCORD_CUSTOM_EMOJIS,
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

from exceptions import (
    YourAIUnexpectedError, YourAIPipelineError,
    YourAILLMError, YourAIAllTiersFailedError, YourAIToolError,
    YourAINoPrivilegeError, YourAIToolExecutionError, YourAIVisionError
)

from detection import (
    detect_promises_and_emotions,
    detect_diary_query,
    load_diary_context_for_query,
    auto_search_diary,
    llm_promise_check
)

from autonomy_guard import (
    coherence_check_node as _coherence_check_node,
    get_guard_log
)

from safety import granite_guardian_node, password_scanner_node
from altpersona import altpersona_brat_node, altpersona_uncensored_node

# ==========================================
# EXTERNE MODULE
# ==========================================

# Voice Module nur laden wenn USE_VOICE aktiv (spart RAM!)
if USE_VOICE:
    import ears
    import mouth
else:
    ears = None
    mouth = None
    print(f"{Fore.YELLOW}⚠️ Voice deaktiviert (USE_VOICE=False) - Whisper wird NICHT geladen{Style.RESET_ALL}")

# eyes immer laden — see_url() (Discord/Web) braucht kein Desktop
# USE_VISION steuert nur den Screenshot-Node (vision_node)
import eyes
if not USE_VISION:
    print(f"{Fore.YELLOW}⚠️ Screenshot-Vision deaktiviert (USE_VISION=False) — URL-Vision läuft weiter{Style.RESET_ALL}")

# Twitch nur laden wenn USE_TWITCH aktiv
if USE_TWITCH:
    import twitch_client
else:
    twitch_client = None

# Discord nur laden wenn USE_DISCORD aktiv
if USE_DISCORD:
    import discord_client
else:
    discord_client = None

# Diese werden immer gebraucht
import hippocampus
import episodic
import personas

# NEU: Session Manager für User-Switching
from session import session_manager

# Spotify Feedback: wird vom Post-Processor befüllt, nächster Call liest es
_spotify_feedback_pending: Optional[str] = None
# File Brain Feedback: wird vom Post-Processor befüllt, nächster Call liest es
_file_feedback_pending: Optional[str] = None
# Web Search Feedback: wird vom Post-Processor befüllt, nächster Call liest es
_web_feedback_pending: Optional[str] = None
# Paperless Feedback: wird vom Post-Processor befüllt, nächster Call liest es
_docs_feedback_pending: Optional[str] = None
# Home Assistant Feedback: wird vom Post-Processor befüllt, nächster Call liest es
_home_feedback_pending: Optional[str] = None
_altpersona_feedback_pending: Optional[str] = None
_website_feedback_pending: Optional[str] = None

def _get_file_documents_list() -> str:
    """Gibt die Liste verfügbarer Dokumente mit Kapitel-Übersicht für den Prompt zurück."""
    try:
        import os as _os
        from tools.file_brain import get_file_brain, DOCUMENTS_DIR
        import json as _json
        fb = get_file_brain()
        if not fb.catalog["documents"]:
            return "(Keine Dokumente vorhanden)"
        lines = []
        for name, info in fb.catalog["documents"].items():
            lines.append(f"- \"{name}\" ({info['chunks']} Chunks, {info['words']} Wörter, {info['type']})")
            # Kapitel-Namen auflisten (aus _meta.json)
            meta_path = _os.path.join(DOCUMENTS_DIR, name, "_meta.json")
            if _os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = _json.load(f)
                    # Unique base titles (ohne "Teil X")
                    import re as _re
                    seen = set()
                    chapter_names = []
                    for c in meta.get("chunk_list", []):
                        base = _re.sub(r'\s*\(Teil\s*\d+\)', '', c["title"]).strip()
                        if base not in seen:
                            seen.add(base)
                            chapter_names.append(base)
                    if chapter_names:
                        lines.append(f"  Kapitel: {', '.join(chapter_names[:20])}")
                        if len(chapter_names) > 20:
                            lines.append(f"  ...und {len(chapter_names) - 20} weitere")
                except Exception:
                    pass
        return "\n".join(lines)
    except Exception as e:
        log("FILE_BRAIN", f"⚠️ Error generating doc list: {e}", Fore.YELLOW)
        return "(File Brain nicht verfügbar)"

# ==========================================
# DASHBOARD CLIENT
# ==========================================

try:
    from dashboard_client import debug
    DASHBOARD_ENABLED = True
    print(f"{Fore.GREEN}✅ Dashboard Client geladen! Öffne http://localhost:8050{Style.RESET_ALL}")
except ImportError:
    class DummyDebug:
        """Dummy wenn dashboard_client.py nicht existiert."""
        def __getattr__(self, name):
            return lambda *args, **kwargs: None
        def get_web_input(self):
            return None
    debug = DummyDebug()
    DASHBOARD_ENABLED = False
    print(f"{Fore.YELLOW}⚠️ Dashboard nicht aktiv (dashboard_client.py nicht gefunden){Style.RESET_ALL}")


# ==========================================
# STATE DEFINITION
# ==========================================

class AgentState(TypedDict):
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


# ==========================================
# THREAD-SAFE GLOBALS
# ==========================================

LAST_SEEN_CONTEXT = ""
_VISION_LOCK = threading.Lock()

# Reusable ThreadPoolExecutor für Promise-Checks (kein Thread-Leak!)
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
    Schreibt YourAIs Antwort 1:1 (mit Emojis) in yourai_output.txt.
    100% raw — kein Timestamp, keine Formatierung, genau wie YourAI es ausgegeben hat.
    Stoppt dauerhaft wenn Datei >= 15 MB erreicht.
    """
    try:
        import os as _os
        if _os.path.exists(YOURAI_OUTPUT_FILE):
            if _os.path.getsize(YOURAI_OUTPUT_FILE) >= YOURAI_OUTPUT_MAX_BYTES:
                return  # 15MB erreicht — kein weiteres Schreiben
        with open(YOURAI_OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(text.strip() + "\n\n")
    except Exception:
        pass  # Nie crashen wegen Log

def _get_promise_executor():
    """Lazy-init eines einzelnen ThreadPoolExecutors."""
    global _PROMISE_CHECK_EXECUTOR
    if _PROMISE_CHECK_EXECUTOR is None:
        _PROMISE_CHECK_EXECUTOR = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="promise-check"
        )
    return _PROMISE_CHECK_EXECUTOR

# Vorkompiliertes Regex für Response-Cleaning
_RESPONSE_HEADER_RE = re.compile(
    r'\*?\*?(?:(?:YourAI|AltPersona)\'?s?\s*(?:Response|Answer|Reply|Antwort|Nachricht)):?\*?\*?\s*\n?',
    re.IGNORECASE
)
_STRIP_EMOJIS_RE = re.compile(r'[\U0001F300-\U0001F9FF]')

# Vorkompilierte Regex für Streaming-Tag-Erkennung
_STREAM_SINGLE_TAG_RE = re.compile(r'\[(SPOTIFY|FILE|STICKER|WEB|DOCS|HOME|IMG|ALTPERSONA|WEBSITE|REDESIGN|LAB_REDESIGN):([^\]]+)\]')
_STREAM_DM_TAG_RE = re.compile(r'\[DM:(\w+)\](.*?)\[/DM\]', re.DOTALL)


# ==========================================
# STREAMING TOOL DISPATCHER
# ==========================================

def _fire_tool_thread(fn, *args) -> None:
    """Fires a tool callback in a background daemon thread (fire-and-forget)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _dispatch_single_tags_stream(
    buffer: str,
    dispatched: set,
    on_spotify,
    on_file,
    on_sticker,
    on_web=None,
    on_docs=None,
    on_home=None,
    on_image=None,
) -> None:
    """Scans buffer for completed single-line tags and fires each exactly once."""
    for m in _STREAM_SINGLE_TAG_RE.finditer(buffer):
        key = m.group(0)
        if key in dispatched:
            continue
        dispatched.add(key)
        tag_type = m.group(1)
        tag_cmd = m.group(2).strip()
        log("STREAM", f"⚡ Early dispatch [{tag_type}:{tag_cmd[:60]}]", Fore.MAGENTA)
        if tag_type == "SPOTIFY" and on_spotify:
            _fire_tool_thread(on_spotify, tag_cmd)
        elif tag_type == "FILE" and on_file:
            _fire_tool_thread(on_file, tag_cmd)
        elif tag_type == "STICKER" and on_sticker:
            _fire_tool_thread(on_sticker, tag_cmd)
        elif tag_type == "WEB" and on_web:
            _fire_tool_thread(on_web, tag_cmd)
        elif tag_type == "DOCS" and on_docs:
            _fire_tool_thread(on_docs, tag_cmd)
        elif tag_type == "HOME" and on_home:
            _fire_tool_thread(on_home, tag_cmd)
        elif tag_type == "IMG" and on_image:
            _fire_tool_thread(on_image, tag_cmd)


def _dispatch_dm_tags_stream(
    buffer: str,
    dispatched: set,
    on_dm,
) -> None:
    """Scans buffer for completed [DM:Target]...[/DM] blocks and fires each once."""
    for m in _STREAM_DM_TAG_RE.finditer(buffer):
        key = m.group(0)
        if key in dispatched:
            continue
        dispatched.add(key)
        target = m.group(1)
        message = m.group(2).strip()
        log("STREAM", f"⚡ Early DM dispatch → {target}", Fore.MAGENTA)
        if on_dm:
            _fire_tool_thread(on_dm, target, message)


def _run_streaming_yourai(
    stream,
    on_spotify=None,
    on_file=None,
    on_sticker=None,
    on_dm=None,
    on_web=None,
    on_docs=None,
    on_home=None,
    on_image=None,
) -> str:
    """
    Consumes the OpenRouter stream, accumulates tokens and dispatches tool-tags
    as soon as they appear in the buffer (fire-and-forget via daemon threads).
    Returns the full accumulated response text.
    """
    buffer = ""
    dispatched: set = set()
    for chunk in stream:
        buffer += chunk
        _dispatch_single_tags_stream(buffer, dispatched, on_spotify, on_file, on_sticker, on_web, on_docs, on_home, on_image)
        _dispatch_dm_tags_stream(buffer, dispatched, on_dm)
    log("STREAM", f"✅ Stream complete ({len(buffer)} chars, {len(dispatched)} tags dispatched)", Fore.GREEN)
    return buffer

def _build_spotify_callback():
    """Returns a callable that executes a single Spotify command (fire-and-forget)."""
    import re as _re

    def _exec_spotify(spotify_cmd: str) -> None:
        try:
            from tools.spotify_control import SpotifyControl
            _ctrl = SpotifyControl()
            cmd_lower = spotify_cmd.lower()
            global _spotify_feedback_pending
            result_msg = None

            if cmd_lower == "skip":
                _ctrl.api.skip_next()
                result_msg = "✅ Skipped to next track"
            elif cmd_lower == "pause":
                _ctrl.api.pause()
                result_msg = "✅ Paused"
            elif cmd_lower == "resume":
                _ctrl.api.play()
                result_msg = "✅ Resumed playback"
            elif cmd_lower == "previous":
                _ctrl.api.skip_previous()
                result_msg = "✅ Back to previous track"
            elif cmd_lower.startswith("volume"):
                vol = _re.search(r'(\d+)', cmd_lower)
                if vol:
                    _ctrl.api.set_volume(int(vol.group(1)))
                    result_msg = f"✅ Volume set to {vol.group(1)}%"
            elif cmd_lower.startswith("shuffle"):
                parts = spotify_cmd[7:].strip()
                filter_match = _re.search(r'filter=(.+)', parts)
                filter_artist = filter_match.group(1).strip() if filter_match else None
                playlist_name = parts[:filter_match.start()].strip() if filter_match else parts
                if playlist_name:
                    r = _ctrl.shuffle_playlist(playlist_name, filter_artist=filter_artist)
                    result_msg = f"✅ {r.get('message', 'Shuffle done')}" if r.get('success') else f"❌ {r.get('error', 'Shuffle failed')}"
                else:
                    result_msg = "❌ No playlist name given. Which playlist should I shuffle?"
            elif cmd_lower.startswith("yourai_shuffle"):
                parts = spotify_cmd[13:].strip()
                filter_match = _re.search(r'filter=(.+)', parts)
                filter_artist = filter_match.group(1).strip() if filter_match else None
                playlist_name = parts[:filter_match.start()].strip() if filter_match else parts
                if playlist_name:
                    r = _ctrl.yourai_shuffle(playlist_name, filter_artist=filter_artist)
                    result_msg = f"✅ {r.get('message', 'YourAI DJ Shuffle done')}" if r.get('success') else f"❌ {r.get('error', 'YourAI Shuffle failed')}"
                else:
                    result_msg = "❌ No playlist name given. Which playlist should I DJ shuffle?"
            elif cmd_lower.startswith("sort_bpm"):
                parts = spotify_cmd[8:].strip()
                ascending = "asc" in parts.lower()
                playlist_name = _re.sub(r'\b(asc|desc)\b', '', parts).strip()
                if playlist_name:
                    r = _ctrl.sort_by_bpm(playlist_name, ascending=ascending)
                    result_msg = f"✅ {r.get('message', 'Sort done')}" if r.get('success') else f"❌ {r.get('error', 'BPM sort failed')}"
                else:
                    result_msg = "❌ No playlist name given. Which playlist should I sort by BPM?"
            elif cmd_lower.startswith("sort_energy"):
                parts = spotify_cmd[11:].strip()
                ascending = "asc" in parts.lower()
                playlist_name = _re.sub(r'\b(asc|desc)\b', '', parts).strip()
                if playlist_name:
                    r = _ctrl.sort_by_energy(playlist_name, ascending=ascending)
                    result_msg = f"✅ {r.get('message', 'Sort done')}" if r.get('success') else f"❌ {r.get('error', 'Energy sort failed')}"
                else:
                    result_msg = "❌ No playlist name given. Which playlist should I sort by energy?"
            elif cmd_lower.startswith("sort_key"):
                parts = spotify_cmd[8:].strip()
                key_match = _re.search(r'\b(\d{1,2}[AB])\b', parts, _re.IGNORECASE)
                target_key = key_match.group(1) if key_match else None
                playlist_name = _re.sub(r'\b\d{1,2}[AB]\b', '', parts, flags=_re.IGNORECASE).strip()
                if playlist_name:
                    r = _ctrl.sort_by_key(playlist_name, target_key=target_key)
                    result_msg = f"✅ {r.get('message', 'Key sort done')}" if r.get('success') else f"❌ {r.get('error', 'Key sort failed')}"
                else:
                    result_msg = "❌ No playlist name given. Which playlist should I sort by key?"
            elif cmd_lower.startswith("queue"):
                queue_arg = spotify_cmd[5:].strip()
                if queue_arg:
                    r = _ctrl.queue_playlist(queue_arg)
                    result_msg = f"✅ {r.get('message', 'Queued')}" if r.get('success') else f"❌ {r.get('error', 'Queue failed')}"
                else:
                    r = _ctrl.get_queue_info()
                    result_msg = f"✅ {r.get('message', 'Queue loaded')}"
            else:
                result_msg = f"❌ Unknown command: {spotify_cmd}"

            if result_msg:
                log("STREAM:SPOTIFY", f"🎵 {result_msg}", Fore.GREEN)
                _spotify_feedback_pending = result_msg

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="spotify_cmd", cause=exc)
            log_exception("STREAM:SPOTIFY", err)
            _spotify_feedback_pending = f"❌ {spotify_cmd} failed: {exc}"

    return _exec_spotify


def _build_file_callback():
    """Returns a callable that executes a single FILE command (fire-and-forget)."""
    def _exec_file(file_cmd: str) -> None:
        try:
            from tools.file_brain import get_file_brain
            fb = get_file_brain()
            cmd_lower = file_cmd.lower()
            global _file_feedback_pending
            result = None

            if cmd_lower.startswith("search "):
                result = fb.search(file_cmd[7:].strip())
            elif cmd_lower.startswith("read "):
                result = fb.read(file_cmd[5:].strip())
                if result and result.get("content"):
                    _file_feedback_pending = (
                        result.get("message", "Read done") +
                        f"\nCONTENT:\n{result['content'][:8000]}"
                    )
                    log("STREAM:FILE", "📁 File read dispatched early", Fore.CYAN)
                    return
            elif cmd_lower.startswith("list"):
                arg = file_cmd[4:].strip()
                result = fb.list_doc(arg) if arg else fb.list_all()
            elif cmd_lower.startswith("ingest "):
                filepath = file_cmd[7:].strip().strip('"').strip("'")
                result = fb.ingest(filepath)

            if result:
                msg = result.get("message", result.get("error", "Done"))
                log("STREAM:FILE", f"📁 {msg}", Fore.CYAN)
                _file_feedback_pending = msg

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="file_cmd", cause=exc)
            log_exception("STREAM:FILE", err)

    return _exec_file


def _build_web_callback():
    """Returns a callable that executes a web search (fire-and-forget)."""
    def _exec_web(query: str) -> None:
        try:
            from tools.web_search import web_search, format_results_for_prompt
            result = web_search(query)
            global _web_feedback_pending
            if result.get("success") and result.get("results"):
                _web_feedback_pending = format_results_for_prompt(result)
                log("STREAM:WEB", f"🌐 Web search done: {len(result['results'])} results for '{query}'", Fore.CYAN)
                debug.info("web_search", f"🌐 Web search: {len(result['results'])} results for '{query}'", _web_feedback_pending[:500])
            else:
                _web_feedback_pending = result.get("message", f"No results for '{query}'")
                log("STREAM:WEB", f"🌐 Web search: {_web_feedback_pending}", Fore.YELLOW)
                debug.info("web_search", f"🌐 Web search: no results for '{query}'")
        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="web_search", cause=exc)
            log_exception("STREAM:WEB", err)
            debug.error("web_search", err.short(), exception=err)

    return _exec_web


def _build_docs_callback():
    """Returns a callable that executes a Paperless command (fire-and-forget)."""
    def _exec_docs(cmd: str) -> None:
        try:
            from tools.paperless import (
                paperless_search, paperless_doc_content,
                paperless_list_tags, paperless_list_correspondents, paperless_list_doctypes,
                format_search_for_prompt, format_doc_for_prompt,
            )
            global _docs_feedback_pending
            cmd_lower = cmd.lower().strip()

            if cmd_lower.startswith("search "):
                query = cmd[7:].strip()
                result = paperless_search(query)
                if result.get("success") and result.get("results"):
                    _docs_feedback_pending = format_search_for_prompt(result)
                else:
                    _docs_feedback_pending = result.get("message", f"No documents for '{query}'")

            elif cmd_lower.startswith("read "):
                try:
                    doc_id = int(cmd[5:].strip())
                    result = paperless_doc_content(doc_id)
                    if result.get("success"):
                        _docs_feedback_pending = format_doc_for_prompt(result)
                    else:
                        _docs_feedback_pending = result.get("message", f"Could not read #{doc_id}")
                except ValueError:
                    _docs_feedback_pending = f"Invalid document ID: {cmd[5:].strip()}"

            elif cmd_lower == "tags":
                result = paperless_list_tags()
                _docs_feedback_pending = result.get("message", "No tags")

            elif cmd_lower == "correspondents":
                result = paperless_list_correspondents()
                _docs_feedback_pending = result.get("message", "No correspondents")

            elif cmd_lower == "types":
                result = paperless_list_doctypes()
                _docs_feedback_pending = result.get("message", "No types")

            else:
                _docs_feedback_pending = f"Unknown DOCS command: {cmd}"

            log("STREAM:DOCS", f"📄 Paperless done: {cmd}", Fore.CYAN)
            debug.info("paperless", f"📄 Paperless: {cmd}", _docs_feedback_pending[:500] if _docs_feedback_pending else None)

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="paperless", cause=exc)
            log_exception("STREAM:DOCS", err)
            debug.error("paperless", err.short(), exception=err)

    return _exec_docs


def _build_home_callback():
    """Returns a callable that executes a Home Assistant command (fire-and-forget)."""
    def _exec_home(cmd: str) -> None:
        try:
            from tools.home_assistant import execute_home_command, format_result_for_prompt
            global _home_feedback_pending

            result = execute_home_command(cmd)
            _home_feedback_pending = format_result_for_prompt(result)

            log("STREAM:HOME", f"🏠 HA done: {cmd}", Fore.CYAN)
            debug.info("home_assistant", f"🏠 HA: {cmd}", _home_feedback_pending[:500] if _home_feedback_pending else None)

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="home_assistant", cause=exc)
            log_exception("STREAM:HOME", err)
            debug.error("home_assistant", err.short(), exception=err)

    return _exec_home


def _build_image_callback(state: "AgentState"):
    """Returns a callable that generates an image and delivers it to the right channel."""
    source     = state.get("source", "console")
    channel_id = state.get("channel_id") or 0
    user_id    = state.get("user_id", "")

    # Resolve user role for rate limiting
    _user_role = "default"
    try:
        _profile = session_manager.get_current_profile(source)
        if _profile:
            _user_role = _profile.role
    except Exception:
        pass

    def _exec_image(prompt: str) -> None:
        try:
            from tools.image_gen import generate_image
            from tools.image_limits import can_generate, record_usage

            # ── Rate limit check ──────────────────────────────
            allowed, remaining, limit = can_generate(user_id, _user_role)
            if not allowed:
                msg = f"🎨 Image limit reached for {user_id} ({limit}/month)"
                log("IMAGE", f"⛔ {msg}", Fore.YELLOW)
                debug.error("image_gen", f"⛔ Rate limit: {user_id} used {limit}/{limit} this month")
                return  # YourAI's prompt already tells her about the limit

            debug.info("image_gen", f"🎨 Generating image... ({remaining - 1} remaining for {user_id})", f"Prompt: {prompt[:200]}")
            result = generate_image(prompt)

            if result["success"]:
                url       = result["url"]
                elapsed_s = result.get("elapsed_s", 0)
                model_used = result.get("model", IMAGE_MODEL)

                # Record usage AFTER successful generation
                record_usage(user_id)

                log("IMAGE", f"✅ Image ready in {elapsed_s}s — delivering to {source}", Fore.GREEN)
                debug.image_ready(url, prompt, model=model_used, elapsed_s=elapsed_s, for_user=user_id)

                # Deliver image to the right channel
                if discord_client and source in ("discord", "discord_private"):
                    target = channel_id if source == "discord_private" else DISCORD_VIP_CHANNEL_ID
                    discord_client.bot.send_channel_image(target, url, prompt)
                elif discord_client and source == "discord_dm":
                    # For DMs: send as channel image to the DM channel (channel_id is the DM channel)
                    if channel_id:
                        discord_client.bot.send_channel_image(channel_id, url, prompt)
                # Dashboard (web/console): image_ready event already sent above → frontend shows it
            else:
                err = result.get("error", "Unknown error")
                log("IMAGE", f"❌ Generation failed: {err}", Fore.RED)
                debug.error("image_gen", f"❌ Image failed: {err}")

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="image_gen", cause=exc)
            log_exception("IMAGE", err)
            debug.error("image_gen", err.short(), exception=err)

    return _exec_image


def _build_sticker_callback(state: "AgentState"):
    """Returns a callable to send a Discord sticker (fire-and-forget)."""
    source = state.get("source", "console")

    def _exec_sticker(sticker_name: str) -> None:
        try:
            if not (USE_DISCORD and discord_client and discord_client.bot.connected):
                return
            sticker_name = sticker_name.strip()
            if source == "discord_dm":
                session_key = (session_manager.source_users.get("discord") or "").lower()
                for did, ukey in DISCORD_DM_WHITELIST.items():
                    if ukey.lower() == session_key:
                        discord_client.bot.send_sticker_dm(int(did), sticker_name)
                        break
            elif source == "discord":
                discord_client.bot.send_sticker(DISCORD_VIP_CHANNEL_ID, sticker_name)
        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="sticker", cause=exc)
            log_exception("STREAM:STICKER", err)

    return _exec_sticker


def _build_dm_callback():
    """Returns a callable to send a Discord DM (fire-and-forget)."""
    def _exec_dm(target: str, message: str) -> None:
        try:
            if not (USE_DISCORD and discord_client and discord_client.bot.connected):
                return
            for did, ukey in DISCORD_DM_WHITELIST.items():
                if ukey.lower() == target.lower():
                    discord_client.bot.send_dm(int(did), message)
                    log("STREAM:DM", f"📩 DM sent to {target}: {message[:60]}", Fore.GREEN)
                    return
            log("STREAM:DM", f"⚠️ DM target '{target}' not in whitelist", Fore.YELLOW)
        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="dm", cause=exc)
            log_exception("STREAM:DM", err)

    return _exec_dm


# ==========================================
# PIPELINE NODES
# ==========================================

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
            try:
                mems = hippocampus.memory.get_relevant_memories(state["question"])
            except Exception as mem_err:
                # Timeout/Error → Fallback-Memories holen wenn vorhanden
                fallback = getattr(hippocampus.memory, '_last_fallback_memories', None)
                if fallback:
                    mems = fallback
                    hippocampus.memory._last_fallback_memories = None
                    log("MEMORY", f"⚠️ LLM Error, aber {len(mems)} Vektor-Fallback Memories", Fore.YELLOW)
                pipeline_errors.append(f"Memory LLM: {mem_err}")
                debug.error("memory", str(mem_err), exception=mem_err)
            if mems:
                log("MEMORY", f"Found {len(mems)} relevant items.", Fore.CYAN)

        # Episodic v2 (Diary with rotation)
        if USE_EPISODIC:
            _diary_user_id = state.get("user_id") or ""
            diary_txt = episodic.journal.get_recent(hours=24, user_id=_diary_user_id)

            # Auto-search diary for relevant entries
            diary_search_results = auto_search_diary(
                state["question"], episodic.journal, limit=10, user_id=_diary_user_id
            )
            
            # Diary Query Detection (for explicit queries)
            query_type, query_param = detect_diary_query(state["question"])
            
            if query_type:
                journal = episodic.journal if hasattr(episodic, 'journal') else None
                extra_context = load_diary_context_for_query(
                    query_type, query_param, journal, get_guard_log
                )
                if extra_context:
                    diary_txt = extra_context + "\n\n---\nRecent (24h):\n" + diary_txt
                    log("DIARY", f"📋 Query detected: {query_type}({query_param})", Fore.CYAN)
            
            # Weekly summary
            if hasattr(episodic.journal, 'current_week_id'):
                current_week = episodic.journal.current_week_id
                summary = episodic.journal.get_summary(current_week)
                if summary and not summary.get("error"):
                    top_tags = list(summary.get('tags_frequency', {}).keys())[:5]
                    highlights = summary.get('highlights', [])[:3]
                    highlight_texts = [h.get('preview', '')[:40] for h in highlights]
                    
                    week_summary_txt = f"Week {current_week}: {summary.get('total_entries', 0)} entries"
                    if top_tags:
                        week_summary_txt += f" | Topics: {', '.join(top_tags)}"
                    if highlight_texts:
                        week_summary_txt += f" | Recent: {'; '.join(highlight_texts)}"
        
        # Emotional Context (Bocken-System)
        if hasattr(personas, 'persona_manager'):
            pm = personas.persona_manager
            
            _NEGATIVE_MOODS = {"pouting", "disappointed", "hurt", "sulking"}
            if pm.current_mood in _NEGATIVE_MOODS:
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
    global _spotify_feedback_pending
    spotify_ctx = ""
    if USE_SPOTIFY:
        try:
            from spotify import get_music_context
            spotify_ctx = get_music_context()
            if spotify_ctx:
                log("SPOTIFY", f"🎵 Music context loaded", Fore.MAGENTA)
                # Erste Zeile als Kurzinfo (z.B. "Now Playing: Song - Artist")
                _sp_preview = spotify_ctx.splitlines()[0][:120] if spotify_ctx else ""
                debug.info("spotify", f"🎵 Spotify → Prompt", _sp_preview)
            else:
                log("SPOTIFY", f"🎴 Kein aktives Device", Fore.MAGENTA)
                debug.info("spotify", "🎴 Spotify: Kein aktives Device", "Kein Context injiziert")
        except Exception as e:
            log("SPOTIFY", f"⚠️ Error: {e}", Fore.YELLOW)
            debug.error("spotify", f"⚠️ Spotify Fehler: {e}")

        # Feedback von vorherigem Spotify-Command anhängen
        if _spotify_feedback_pending:
            feedback_block = f"\n## 🎵 SPOTIFY COMMAND FEEDBACK\nYour last Spotify command results: {_spotify_feedback_pending}\nYou can tell Creator what happened! (e.g. 'Done! Playlist is shuffled!' or 'Sorted by BPM for you!')"
            spotify_ctx = (spotify_ctx + "\n" + feedback_block) if spotify_ctx else feedback_block
            log("SPOTIFY", f"📨 Injecting feedback: {_spotify_feedback_pending}", Fore.CYAN)
            debug.info("spotify", f"📨 Spotify Feedback injiziert", _spotify_feedback_pending[:200])
            _spotify_feedback_pending = None  # Einmal verbraucht

    # File Brain Feedback von letztem [FILE:] Command
    global _file_feedback_pending
    file_ctx = ""
    if _file_feedback_pending:
        file_ctx = f"\n## 📁 FILE BRAIN RESULTS\nYou ALREADY read the following content. This is REAL data from the file system:\n\n{_file_feedback_pending}\n\n⚠️ IMPORTANT: You HAVE the content above! Do NOT use [FILE:read] again! Instead, discuss/summarize/quote the content you just received. Tell Creator what you found! Share your thoughts about what you read!"
        log("FILE_BRAIN", f"📨 Injecting file feedback ({len(_file_feedback_pending)} chars)", Fore.CYAN)
        _file_feedback_pending = None

    # Web Search Feedback von letztem [WEB:] Command
    global _web_feedback_pending
    web_ctx = ""
    if _web_feedback_pending:
        web_ctx = f"\n## 🌐 WEB SEARCH RESULTS\nYou searched the internet and here are REAL results:\n\n{_web_feedback_pending}\n\n⚠️ IMPORTANT: These are REAL search results! Use them to answer the user's question. Summarize the findings naturally — don't just list them!"
        log("WEB", f"📨 Injecting web feedback ({len(_web_feedback_pending)} chars)", Fore.CYAN)
        _web_feedback_pending = None

    # Paperless Feedback von letztem [DOCS:] Command
    global _docs_feedback_pending
    docs_ctx = ""
    if _docs_feedback_pending:
        docs_ctx = f"\n## 📄 PAPERLESS DOCUMENT RESULTS\nHere are REAL results from Creator's document archive:\n\n{_docs_feedback_pending}\n\n⚠️ IMPORTANT: This is REAL document data! Summarize what you found. If it's a search result, tell Creator which documents matched and offer to read specific ones by ID."
        log("PAPERLESS", f"📨 Injecting docs feedback ({len(_docs_feedback_pending)} chars)", Fore.CYAN)
        _docs_feedback_pending = None

    # Home Assistant Feedback von letztem [HOME:] Command
    global _home_feedback_pending
    home_ctx = ""
    if _home_feedback_pending:
        home_ctx = f"\n## 🏠 HOME ASSISTANT RESULTS\nHere are the results from the smart home command:\n\n{_home_feedback_pending}\n\n⚠️ IMPORTANT: This is REAL data from Home Assistant! Tell Creator what happened — confirm the action or share device status!"
        log("HOME", f"📨 Injecting HA feedback ({len(_home_feedback_pending)} chars)", Fore.CYAN)
        _home_feedback_pending = None

    global _altpersona_feedback_pending
    altpersona_ctx = ""
    if _altpersona_feedback_pending:
        altpersona_ctx = f"\n## 😈 ALTPERSONA'S MEINUNG\nDu hast im letzten Turn AltPersona gefragt. Hier ist ihre Antwort:\n\n{_altpersona_feedback_pending}\n\n⚠️ Nutze ihre Meinung in deiner Antwort oder diskutiere darüber!"
        log("ALTPERSONA", f"📨 Injecting altpersona feedback ({len(_altpersona_feedback_pending)} chars)", Fore.CYAN)
        _altpersona_feedback_pending = None

    global _website_feedback_pending
    website_ctx = ""
    if _website_feedback_pending:
        website_ctx = f"\n## 🌐 DEINE WEBSITE\n{_website_feedback_pending}"
        log("WEBSITE", f"📨 Injecting website feedback ({len(_website_feedback_pending)} chars)", Fore.CYAN)
        _website_feedback_pending = None

    return {
        "memories": mems,
        "diary_context": diary_txt,
        "diary_search_results": diary_search_results,
        "week_summary": week_summary_txt,
        "emotional_context": emotional_ctx,
        "visual_context": current_vision,
        "vision_done": False,
        "error_context": error_ctx,
        "spotify_context": spotify_ctx,
        "file_context": file_ctx,
        "web_context": web_ctx,
        "docs_context": docs_ctx,
        "home_context": home_ctx,
        "altpersona_context": altpersona_ctx,
        "website_context": website_ctx,
    }


def coherence_check_node(state: AgentState):
    """Wrapper für den Autonomy Guard."""
    return _coherence_check_node(state, debug)


def router_node(state: AgentState):
    """Intent Router Node."""
    run_num = '2' if state.get('vision_done') else '1'
    debug.node_start("router", model=MODEL_ROUTER, input_data=f"[Run {run_num}] {state['question'][:200]}")
    
    log("ROUTER", f"Analyzing intent with {MODEL_ROUTER} (Run: {run_num})...", Fore.MAGENTA)
    user_text = state["question"].lower()
    
    # Vision phrase detection
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
    
    if USE_VISION and not state.get("vision_done") and vision_triggered:
        log("ROUTER", "👀 Visual PHRASE detected -> Forcing Vision Mode", Fore.MAGENTA)
        domain = "vision"
        debug.node_end("router")
    else:
        # Primary: OpenRouter (Gemma 3 12B - endlich ein Router der funktioniert)
        # Fallback: Lokal (MODEL_ROUTER)
        router_model_name = MODEL_ROUTER
        try:
            start_time = time.time()

            if _cfg.USE_OPENROUTER:
                from config import OPENROUTER_MODEL_ROUTER
                router_model_name = OPENROUTER_MODEL_ROUTER
                log("ROUTER", f"☁️ OpenRouter: {router_model_name}", Fore.MAGENTA)
                res, _ = call_openrouter(
                    system_prompt=PROMPT_ROUTER_SYSTEM,
                    user_message=state["question"],
                    model=router_model_name,
                    temperature=0,
                    max_tokens=100,
                )
            else:
                llm = create_thinking_llm(MODEL_ROUTER, LLM_HOST_STD, temperature=0, keep_alive="0m")
                res = str(llm.invoke([SystemMessage(content=PROMPT_ROUTER_SYSTEM), HumanMessage(content=state["question"])]).content)

            duration = int((time.time() - start_time) * 1000)

            debug.llm_response("router", res, model=router_model_name, duration_ms=duration)
            show_llm("Router", router_model_name, res, role="router", show_thinking=True)

            _, clean_json_text = extract_thoughts(res)
            json_data = extract_json_from_text(clean_json_text)

            if json_data:
                domain = json_data.get("model", "fallback")
            else:
                domain = "fallback"

            if domain == "vision" and state.get("vision_done"):
                domain = "fallback"

            if domain == "vision" and not USE_VISION:
                domain = "fallback"

            debug.node_end("router")

        except Exception as e:
            # OpenRouter failed → Fallback auf lokal
            if _cfg.USE_OPENROUTER and router_model_name != MODEL_ROUTER:
                log("ROUTER", f"⚠️ OpenRouter fehlgeschlagen, Fallback auf lokal: {MODEL_ROUTER}", Fore.YELLOW)
                try:
                    llm = create_thinking_llm(MODEL_ROUTER, LLM_HOST_STD, temperature=0, keep_alive="0m")
                    res = str(llm.invoke([SystemMessage(content=PROMPT_ROUTER_SYSTEM), HumanMessage(content=state["question"])]).content)
                    _, clean_json_text = extract_thoughts(res)
                    json_data = extract_json_from_text(clean_json_text)
                    domain = json_data.get("model", "fallback") if json_data else "fallback"
                    debug.node_end("router")
                except Exception as e2:
                    err = YourAILLMError("Router failed (both tiers)", model=MODEL_ROUTER, cause=e2)
                    debug.error("router", err.short(), exception=err)
                    log_exception("ROUTER", err)
                    domain = "fallback"
            else:
                err = YourAILLMError("Router failed", model=router_model_name, cause=e)
                debug.error("router", err.short(), exception=err)
                log_exception("ROUTER", err)
                domain = "fallback"
    
    mood = "default"
    if state["source"] == "twitch": mood = "twitch" 
    if domain == "gaming": mood = "gamer" 
    return {"expert_domain": domain, "current_mood": mood}


def vision_node(state: AgentState):
    """Vision/Screenshot Node (ADMIN ONLY)."""
    if not USE_VISION:
        log("VISION", "⚠️ Screenshot-Vision deaktiviert (USE_VISION=False)", Fore.YELLOW)
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


def expert_node(state: AgentState):
    """Domain Expert Node - OpenRouter-first für bio/med, Rest lokal."""
    domain = state.get("expert_domain") or "fallback"
    
    if domain == "vision": 
        return {}
    if domain in ["fallback", "smalltalk"]: 
        return {"expert_fact": "No specific expert needed."}

    # Expert Pool: dynamisches Modell-Ranking (monatlich via llm-stats.com)
    # Nur für MANAGED_DOMAINS (bio, med, physics, …) — baking/smalltalk bleiben lokal
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
        "baking": PROMPT_BAKING, "gaming": PROMPT_GAMING,
        "anime": PROMPT_ANIME, "fox_philosophy": PROMPT_FOX_PHILOSOPHY,
    }
    sys_p = prompts.get(domain, "You are a helpful expert.")

    fact = "No info."
    used_model = None  # Track which model actually answered

    # ANIME: Mandatory Web Search — Training data lacks 2023+ anime
    if domain == "anime" and USE_WEB_SEARCH:
        try:
            from tools.web_search import web_search, format_results_for_prompt
            from text_parser import extract_search_query
            _search_q = extract_search_query(state["question"], prefix="anime")
            log("EXPERT", f"🌐 Anime: Web search query: '{_search_q}'", Fore.CYAN)
            web_result = web_search(_search_q)
            if web_result.get("success") and web_result.get("results"):
                web_context = format_results_for_prompt(web_result)
                # Debug: show all result titles
                _titles = [f"{i+1}. {r.get('title', '?')[:80]}" for i, r in enumerate(web_result["results"][:5])]
                _debug_titles = "\n".join(_titles)
                sys_p = sys_p + f"\n\n## WEB SEARCH RESULTS (use as primary source for recent/current anime):\n{web_context}"
                log("EXPERT", f"🌐 Anime: {len(web_result['results'])} web results injected", Fore.GREEN)
                debug.info("anime_web_search", f"🌐 Anime Web Search: '{_search_q}'", f"Results:\n{_debug_titles}\n\n{web_context[:500]}")
            else:
                log("EXPERT", "🌐 Anime: No web results found", Fore.YELLOW)
                debug.info("anime_web_search", f"🌐 Anime Web Search: '{_search_q}'", "No results found")
        except Exception as web_err:
            log("EXPERT", f"🌐 Anime web search failed: {web_err}", Fore.RED)
            debug.error("anime_web_search", f"🌐 Web search failed: {web_err}")

    try:
        # Check feedback: are any models bad for this domain?
        from feedback import FeedbackStore
        _fb = FeedbackStore()
        bad_models = _fb.get_bad_models(domain, user_id=state.get("user_id"))

        # TIER 1: OPENROUTER (with feedback-aware fallback chain)
        if or_model:
            try:
                start_time = time.time()

                # Decide: single model or fallback chain?
                if or_model in bad_models:
                    # Primary is bad → Expert Pool Fallback Chain (dynamisch, feedback-aware)
                    try:
                        from tools.expert_pool import get_model_chain as _ep_chain, MANAGED_DOMAINS as _ep_managed
                        chain = _ep_chain(domain, exclude_models=bad_models) if domain in _ep_managed else get_expert_fallback_chain(domain, exclude_models=bad_models)
                    except Exception:
                        from config import get_expert_fallback_chain
                        chain = get_expert_fallback_chain(domain, exclude_models=bad_models)
                    if chain:
                        log("EXPERT", f"⚠️ Primary {or_model} has too many 👎 → fallback chain: {chain}", Fore.YELLOW)
                        debug.info("expert", f"⚠️ Feedback fallback for [{domain}]", f"Excluded: {bad_models}, Chain: {chain}")
                        raw_res, used_model = call_openrouter(
                            system_prompt=sys_p,
                            user_message=state["question"],
                            models=chain,
                            temperature=0.2,
                            max_tokens=2048
                        )
                    else:
                        # All models bad, try primary anyway
                        log("EXPERT", f"⚠️ All fallbacks excluded, trying primary anyway: {or_model}", Fore.RED)
                        raw_res, used_model = call_openrouter(
                            system_prompt=sys_p,
                            user_message=state["question"],
                            model=or_model,
                            temperature=0.2,
                            max_tokens=2048
                        )
                else:
                    # Primary is fine → single model call (normal)
                    log("EXPERT", f"☁️ Calling OpenRouter ({or_model})...", Fore.CYAN)
                    raw_res, used_model = call_openrouter(
                        system_prompt=sys_p,
                        user_message=state["question"],
                        model=or_model,
                        temperature=0.2,
                        max_tokens=2048
                    )

                actual_model = used_model or or_model
                duration = int((time.time() - start_time) * 1000)
                debug.llm_response("expert", raw_res, model=actual_model, duration_ms=duration)
                show_llm(f"Expert ({domain})", actual_model, raw_res, role="expert", show_thinking=True)

                if used_model and used_model != or_model:
                    log("EXPERT", f"🔄 OpenRouter used fallback: {used_model} (instead of {or_model})", Fore.YELLOW)
                    debug.info("expert", f"🔄 Fallback used: {used_model}")

                _, fact = extract_thoughts(raw_res)
                if not fact.strip(): fact = raw_res

                log("EXPERT", f"☁️ OpenRouter responded in {duration}ms", Fore.GREEN)
                debug.node_end("expert")
                return {"expert_fact": fact, "expert_model_used": actual_model}

            except Exception as or_err:
                err = YourAILLMError(f"OpenRouter failed for domain {domain}", model=or_model, tier="openrouter", cause=or_err)
                log_exception("EXPERT", err)
                log("EXPERT", f"☁️ OpenRouter Failed → local fallback...", Fore.RED)

        # TIER 2: LOKAL
        start_time = time.time()
        log("EXPERT", f"🖥️ Calling local ({local_model})...", Fore.YELLOW)

        llm = create_thinking_llm(local_model, LLM_HOST_STD, temperature=0.2, keep_alive="0m")
        user_msg = maybe_add_think_prompt(state["question"], local_model)
        raw_res = str(llm.invoke([SystemMessage(content=sys_p), HumanMessage(content=user_msg)]).content)
        duration = int((time.time() - start_time) * 1000)

        debug.llm_response("expert", raw_res, model=local_model, duration_ms=duration)
        show_llm(f"Expert ({domain})", local_model, raw_res, role="expert", show_thinking=True)

        _, fact = extract_thoughts(raw_res)
        if not fact.strip(): fact = raw_res
        used_model = local_model

        debug.node_end("expert")

    except Exception as e:
        err = YourAILLMError(f"Expert node failed for domain {domain}", model=local_model, tier="local", cause=e)
        debug.error("expert", err.short(), exception=err)
        log_exception("EXPERT", err)
        fact = "No info."

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

    # Strategie 2: Gängige Filler-Wörter entfernen
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


def tool_check_node(state: AgentState):
    """Prüft ob ein Tool verwendet werden soll."""
    if not USE_TOOLS:
        return {"tool_name": None, "tool_info": None, "tool_result": None}
    
    debug.node_start("tool_check", input_data=state["question"][:100])
    log("TOOLS", "🔍 Checking for tool triggers...", Fore.CYAN)
    
    try:
        tool_name, tool_info = should_use_tool(state["question"], debug)
        
        if tool_name and tool_info:
            log("TOOLS", f"🔧 Tool detected: {tool_name}", Fore.GREEN)
            debug.info("tool_check", f"Tool matched: {tool_name}")
            
            # Admin-Only Check: Bestimmte Tools nur für Admin
            if tool_info.get("admin_only", False):
                user_id = state.get("user_id", "")
                if user_id != "admin":
                    err = YourAINoPrivilegeError(user_id or "unknown", f"use tool '{tool_name}'")
                    log("TOOLS", f"🚫 {err.short()}", Fore.RED)
                    debug.node_end("tool_check")
                    return {
                        "tool_name": None, "tool_info": None, "tool_result": None,
                        "error_context": err.short(),
                    }

            tool_context = {
                "question": state["question"],
                "user_name": state["user_name"],
                "mood": state.get("current_mood", "default"),
                "user_role": state.get("user_id", "guest"),  # Für Spotify Admin-Check
            }

            # Spezialfall: Web Search (Pre-Tool) — Ergebnis direkt in Kontext injizieren
            if tool_name == "web_search" and USE_WEB_SEARCH:
                log("WEB", "🌐 Pre-tool web search triggered by router...", Fore.CYAN)
                try:
                    from tools.web_search import web_search as _pre_web_search, format_results_for_prompt as _fmt_web
                    _search_query = _extract_query_from_trigger(state["question"], tool_info)
                    _web_result = _pre_web_search(_search_query)
                    if _web_result.get("success") and _web_result.get("results"):
                        _web_ctx = f"\n## 🌐 WEB SEARCH RESULTS\nYou searched the internet for '{_search_query}' and here are REAL results:\n\n{_fmt_web(_web_result)}\n\n⚠️ Use these results to answer! Summarize naturally."
                        debug.info("tool_check", f"Web search: {len(_web_result['results'])} results for '{_search_query}'")
                        debug.node_end("tool_check")
                        return {
                            "tool_name": "web_search", "tool_info": tool_info, "tool_result": _web_result,
                            "web_context": _web_ctx,
                        }
                    else:
                        debug.info("tool_check", f"Web search: no results for '{_search_query}'")
                except Exception as e:
                    log("WEB", f"❌ Pre-tool web search failed: {e}", Fore.RED)
                debug.node_end("tool_check")
                return {"tool_name": None, "tool_info": None, "tool_result": None}

            # Spezialfall: Paperless Search (Pre-Tool) — Ergebnis direkt in Kontext injizieren
            if tool_name == "paperless_search" and USE_PAPERLESS:
                log("PAPERLESS", "📄 Pre-tool Paperless search triggered by router...", Fore.CYAN)
                try:
                    from tools.paperless import paperless_search as _pre_docs_search, format_search_for_prompt as _fmt_docs
                    _search_query = _extract_query_from_trigger(state["question"], tool_info)
                    _docs_result = _pre_docs_search(_search_query)
                    if _docs_result.get("success") and _docs_result.get("results"):
                        _docs_ctx = f"\n## 📄 PAPERLESS SEARCH RESULTS\nYou searched Creator's document archive for '{_search_query}':\n\n{_fmt_docs(_docs_result)}\n\n⚠️ Tell Creator what you found! Offer to read specific documents by ID with [DOCS:read ID]."
                        debug.info("tool_check", f"Paperless: {len(_docs_result['results'])} results for '{_search_query}'")
                        debug.node_end("tool_check")
                        return {
                            "tool_name": "paperless_search", "tool_info": tool_info, "tool_result": _docs_result,
                            "docs_context": _docs_ctx,
                        }
                    else:
                        debug.info("tool_check", f"Paperless: no results for '{_search_query}'")
                except Exception as e:
                    log("PAPERLESS", f"❌ Pre-tool Paperless search failed: {e}", Fore.RED)
                debug.node_end("tool_check")
                return {"tool_name": None, "tool_info": None, "tool_result": None}

            # Spezialfall: Home Assistant (Pre-Tool) — Geräteliste direkt in Kontext injizieren
            if tool_name == "home_assistant" and USE_HOME_ASSISTANT:
                log("HOME", "🏠 Pre-tool Home Assistant triggered by router...", Fore.CYAN)
                try:
                    from tools.home_assistant import ha_devices as _pre_ha_devices, format_result_for_prompt as _fmt_ha
                    _ha_result = _pre_ha_devices()
                    if _ha_result.get("success"):
                        _home_ctx = f"\n## 🏠 HOME ASSISTANT DEVICES\nHere are all available smart home devices:\n\n{_fmt_ha(_ha_result)}\n\n⚠️ Use these entity IDs to control devices with [HOME:on/off/toggle entity_id]!"
                        debug.info("tool_check", f"HA: {_ha_result.get('total', 0)} devices loaded")
                        debug.node_end("tool_check")
                        return {
                            "tool_name": "home_assistant", "tool_info": tool_info, "tool_result": _ha_result,
                            "home_context": _home_ctx,
                        }
                    else:
                        debug.info("tool_check", f"HA: {_ha_result.get('message', 'failed')}")
                except Exception as e:
                    log("HOME", f"❌ Pre-tool HA failed: {e}", Fore.RED)
                debug.node_end("tool_check")
                return {"tool_name": None, "tool_info": None, "tool_result": None}

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
                    debug.node_end("tool_check")
                    return {"tool_name": None, "tool_info": None, "tool_result": None}
            
            tool_result = execute_tool(tool_name, tool_info, tool_context, debug)
            
            debug.node_end("tool_check")
            return {
                "tool_name": tool_name,
                "tool_info": tool_info,
                "tool_result": tool_result
            }
        
        log("TOOLS", "No tool needed", Fore.WHITE)
        debug.node_end("tool_check")
        return {"tool_name": None, "tool_info": None, "tool_result": None}
        
    except Exception as e:
        err = YourAIToolError("Tool check routing failed", cause=e)
        log_exception("TOOLS", err)
        debug.error("tool_check", err.short(), exception=err)
        debug.node_end("tool_check")
        return {"tool_name": None, "tool_info": None, "tool_result": None}


def yourai_node(state: AgentState):
    """Main YourAI Response Node."""
    mood = state.get("current_mood") or "default"
    
    # Persona Manager
    if hasattr(personas, 'persona_manager'):
        if mood == "gamer":
            personas.persona_manager.set_mood("gamer")
        persona_text = personas.persona_manager.get_system_prompt("twitch" if state["source"] == "twitch" else "default")
        mood_info = personas.persona_manager.get_mood_info()
        log("YOURAI", f"Mood: {mood_info['emoji']} {mood_info['name']}", Fore.GREEN)
    else:
        persona_text = personas.get_system_prompt(mood)
    
    debug.node_start("yourai", model=MODEL_YOURAI_OPENROUTER if _cfg.USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY, input_data=f"[mood: {mood}] {state['question'][:100]}")
    
    log("YOURAI", f"Generating response ({mood})...", Fore.GREEN)
    
    # User Context
    user_context_str = f"Name: {state['user_name']}"
    guest_ctx = state.get("guest_context")
    if guest_ctx:
        user_context_str += f"\n{guest_ctx}"
    hist_text = "\n".join(state.get("history", []))
    
    # AUTONOMY GUARD SECTION
    coherence_warning = state.get("coherence_warning")
    if coherence_warning:
        coherence_section = f"""## 🛡️ AUTONOMY GUARD
{coherence_warning}"""
        log("YOURAI", f"🛡️ AUTONOMY CHALLENGED!", Fore.RED)
    else:
        coherence_section = ""
    
    # TOOL RESULT
    tool_context = ""
    tool_result = state.get("tool_result")
    if tool_result and tool_result.get("success"):
        tool_context = f"## TOOL RESULT\nYou just updated the website quote to: \"{tool_result.get('quote', '')}\"\nTell Creator it worked!\n"
        log("YOURAI", f"✅ Tool was successful, including in context", Fore.GREEN)
    
    # ==========================================
    # DYNAMIC SECTION ASSEMBLY
    # ==========================================
    source = state.get("source", "console")
    current_user_id = state.get("user_id", "")
    is_admin = current_user_id == "admin"
    is_discord = source in ("discord", "discord_dm", "discord_private")

    # ─── Semantic Prompt Router (OPT-IN) ────────────────────────────────────
    # Philosophy: prompt starts EMPTY. Router decides what gets injected.
    # No route / smalltalk → no tool sections (slim prompt, YourAI can ask).
    # Confident route → only that tool's section is injected.
    # Router error / USE_PROMPT_ROUTER=False → inject everything (safe fallback).
    # "__all__" sentinel = error case, include everything.
    _active_route: str | None = None
    _yourai_node_errors: list[str] = []  # Errors within yourai_node (too late for pipeline_errors)
    if USE_PROMPT_ROUTER:
        try:
            _user_msg_for_router = state.get("question") or ""
            _active_route = _route_classify(_user_msg_for_router)
            log("YOURAI", f"🧭 Prompt router: '{_active_route or 'none → slim'}'", Fore.CYAN)
            _route_label = _active_route or "none (slim prompt)"
            debug.info("prompt_router", f"🧭 Route: {_route_label}")
        except Exception as _router_err:
            log("YOURAI", f"⚠️ Prompt router error: {_router_err} → full prompt fallback", Fore.YELLOW)
            _active_route = "__all__"
            _yourai_node_errors.append(f"Prompt Router: {_router_err}")
            debug.error("prompt_router", f"⚠️ Router error → full prompt fallback: {_router_err}")
    else:
        _active_route = "__all__"  # router off → include everything
        debug.info("prompt_router", "⏸️ Router disabled → full prompt")

    def _route_match(*routes: str) -> bool:
        """True if active route matches any of the given route names, or fallback active."""
        return _active_route in routes or _active_route == "__all__"

    # Spotify Section: Admin + USE_SPOTIFY + spotify route
    spotify_section = ""
    if is_admin and USE_SPOTIFY and _route_match("spotify"):
        spotify_section = SECTION_SPOTIFY

    # File Brain Section: docs present + file route
    file_docs = _get_file_documents_list()
    file_section = ""
    if _route_match("file") and file_docs and file_docs.strip() and file_docs.strip() != "(No documents loaded)":
        file_section = SECTION_FILE_BRAIN.format(file_documents=file_docs)

    # Web Search Section: USE_WEB_SEARCH + web route
    web_section = ""
    if USE_WEB_SEARCH and _route_match("web"):
        web_section = SECTION_WEB_SEARCH

    # Paperless Section: Admin + USE_PAPERLESS + paperless route
    paperless_section = ""
    if is_admin and USE_PAPERLESS and _route_match("paperless"):
        paperless_section = SECTION_PAPERLESS

    # Home Assistant Section: Admin + USE_HOME_ASSISTANT + homeassistant route
    home_section = ""
    if is_admin and USE_HOME_ASSISTANT and _route_match("homeassistant"):
        home_section = SECTION_HOME_ASSISTANT
    # ────────────────────────────────────────────────────────────────────────

    # Custom Emojis: für alle Sources (Discord rendert nativ, Web rendert via CDN)
    discord_emojis_section = ""
    if DISCORD_CUSTOM_EMOJIS:
        emoji_lines = [f"- :{name}: = {desc}" for name, desc in DISCORD_CUSTOM_EMOJIS.items()]
        if emoji_lines:
            discord_emojis_section = (
                "\n## CUSTOM EMOJIS\n"
                "Use :name: format. ONLY the name, no description!\n"
                + "\n".join(emoji_lines)
            )

    # Discord DM Section zusammenbauen
    if source == "discord" and USE_DISCORD:
        discord_dm_section = DISCORD_DM_SECTION_CHANNEL.format(
            discord_emojis=discord_emojis_section,
            spotify_section=spotify_section,
            file_section=file_section,
        )
    elif source == "discord_private" and USE_DISCORD:
        # Privater Channel: Display-Name direkt aus state
        _priv_username = state.get("user_name") or "User"
        discord_dm_section = DISCORD_PRIVATE_SECTION.format(
            username=_priv_username,
            discord_emojis=discord_emojis_section,
            file_section=file_section,
        )
    elif source == "discord_dm" and USE_DISCORD:
        dm_partner_key = (session_manager.source_users.get("discord") or "").lower()
        dm_partner_name = dm_partner_key.capitalize()
        all_targets = {ukey for ukey in DISCORD_DM_WHITELIST.values()}
        other_targets = [t for t in all_targets if t.lower() != dm_partner_key]
        other_lines = "\n".join(f"- [DM:{t}] message [/DM]" for t in sorted(other_targets)) if other_targets else "(No other targets)"
        discord_dm_section = DISCORD_DM_SECTION_DM.format(
            dm_partner=dm_partner_name,
            other_targets=other_lines,
            discord_emojis=discord_emojis_section,
            spotify_section=spotify_section,
            file_section=file_section,
        )
    else:
        # Console/Web/Twitch: Spotify + File + Emojis direkt injizieren (ohne Discord wrapper)
        discord_dm_section = ""
        if spotify_section:
            discord_dm_section += spotify_section + "\n"
        if file_section:
            discord_dm_section += file_section
        if discord_emojis_section:
            discord_dm_section = (discord_dm_section + "\n" + discord_emojis_section) if discord_dm_section else discord_emojis_section

    # Image Generation Section: USE_IMAGE_GEN + image route
    image_gen_section = ""
    if USE_IMAGE_GEN and _route_match("image"):
        image_gen_section = SECTION_IMAGE_GEN
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
                image_gen_section += f"\n\nImage budget: unlimited (admin)"
            else:
                image_gen_section += (
                    f"\n\nImage budget: {_usage['used']}/{_usage['limit']} used this month "
                    f"({_usage['remaining']} remaining). "
                    f"If the user is out of images, tell them kindly — DO NOT use [IMG:] if remaining is 0!"
                )
        except Exception:
            pass

    # Debug Tools Section: only for admin (DumpSystem / NeedHelp tags)
    debug_tools_section = SECTION_DEBUG_TOOLS if is_admin else ""

    # Web Search + Paperless + Home Assistant + Image Gen + AltPersona Consult + Website + Debug Tools
    for _extra_section in (web_section, paperless_section, home_section, image_gen_section, SECTION_ALTPERSONA_CONSULT, SECTION_WEBSITE, debug_tools_section):
        if _extra_section:
            discord_dm_section = (discord_dm_section + "\n" + _extra_section) if discord_dm_section else _extra_section

    # Error Context: NUR wenn tatsächlich Errors da sind (kein Placeholder!)
    error_context = state.get("error_context") or ""
    # Append any errors that happened inside yourai_node itself (e.g. prompt router)
    if _yourai_node_errors:
        _node_err_block = "## ⚠️ SYSTEM ERRORS (this pipeline run)\n" + "\n".join(f"- {e}" for e in _yourai_node_errors)
        _node_err_block += "\nIf relevant, mention the issue naturally. Use [NeedHelp: <short description>] to alert Creator!"
        error_context = (error_context + "\n\n" + _node_err_block).strip() if error_context else _node_err_block

    # Spotify Context: NUR wenn aktives Device + Daten da sind
    spotify_context = state.get("spotify_context") or ""

    # Feedback summary for prompt (lightweight, ~1 line)
    try:
        from feedback import FeedbackStore
        _fb_summary = FeedbackStore().get_approval_summary()
        if _fb_summary:
            _fb_summary = f"## FEEDBACK\n{_fb_summary}"
    except Exception:
        _fb_summary = ""

    # System Prompt zusammenbauen
    formatted_sys = PROMPT_YOURAI_TEMPLATE.format(
        persona_text=persona_text,
        guest_context=state.get("guest_context") or "No special guest info - probably Creator.",
        memories="\n".join(f"- {m}" for m in state.get("memories", [])) or "No memories.",
        diary_search_results=state.get("diary_search_results") or "(No specific diary entries found for your question)",
        diary_context=state.get("diary_context") or "No recent events.",
        week_summary=state.get("week_summary") or "No summary yet.",
        history=hist_text,
        coherence_section=coherence_section,
        emotional_context=state.get("emotional_context") or "",
        error_context=error_context,
        spotify_context=spotify_context,
        discord_dm_section=discord_dm_section,
        feedback_summary=_fb_summary,
    )
    
    debug.system_prompt_dump("yourai", formatted_sys)
    
    # User Message mit Context
    file_ctx = state.get("file_context") or ""
    web_ctx = state.get("web_context") or ""
    docs_ctx = state.get("docs_context") or ""
    home_ctx = state.get("home_context") or ""
    altpersona_ctx = state.get("altpersona_context") or ""
    website_ctx = state.get("website_context") or ""
    msg_content = f"{tool_context}{file_ctx}{web_ctx}{docs_ctx}{home_ctx}{altpersona_ctx}{website_ctx}\nVisual: {state.get('visual_context')}\nExpert: {state.get('expert_fact')}\nUser Context: {user_context_str}\nUser ({state['user_name']}) asks: {state['question']}"
    
    debug.user_message_dump("yourai", msg_content)
    temp = 0.8 if mood == "gamer" else 0.7
    
    response = ""
    used_model = MODEL_YOURAI_OPENROUTER if _cfg.USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY
    success = False
    
    # TIER 1: OPENROUTER
    if _cfg.USE_OPENROUTER:
        try:
            start_time = time.time()
            used_model = MODEL_YOURAI_OPENROUTER

            if USE_STREAMING:
                # ─── STREAMING MODE ──────────────────────────────────────────
                log("YOURAI", f"☁️🔴 Calling OpenRouter STREAM ({MODEL_YOURAI_OPENROUTER})...", Fore.CYAN)
                debug.llm_call("yourai", MODEL_YOURAI_OPENROUTER, msg_content[:500])

                # Build tool callbacks (only if relevant features are active)
                _on_spotify = _build_spotify_callback() if USE_SPOTIFY and state.get("user_id") == "admin" else None
                _on_file    = _build_file_callback()    if USE_TOOLS else None
                _on_sticker = _build_sticker_callback(state) if USE_DISCORD and discord_client else None
                _on_dm      = _build_dm_callback()      if USE_DISCORD and discord_client else None
                _on_web     = _build_web_callback()     if USE_WEB_SEARCH else None
                _on_docs    = _build_docs_callback()    if USE_PAPERLESS and state.get("user_id") == "admin" else None
                _on_home    = _build_home_callback()    if USE_HOME_ASSISTANT and state.get("user_id") == "admin" else None
                _on_image   = _build_image_callback(state) if USE_IMAGE_GEN else None

                stream_gen = call_openrouter_stream(
                    system_prompt=formatted_sys,
                    user_message=msg_content,
                    temperature=temp,
                    max_tokens=4096
                )
                response = _run_streaming_yourai(
                    stream_gen,
                    on_spotify=_on_spotify,
                    on_file=_on_file,
                    on_sticker=_on_sticker,
                    on_dm=_on_dm,
                    on_web=_on_web,
                    on_docs=_on_docs,
                    on_home=_on_home,
                    on_image=_on_image,
                )
            else:
                # ─── BLOCKING MODE (original) ─────────────────────────────
                log("YOURAI", f"☁️ Calling OpenRouter ({MODEL_YOURAI_OPENROUTER})...", Fore.CYAN)
                debug.llm_call("yourai", MODEL_YOURAI_OPENROUTER, msg_content[:500])
                response, _ = call_openrouter(
                    system_prompt=formatted_sys,
                    user_message=msg_content,
                    temperature=temp,
                    max_tokens=4096
                )

            duration = int((time.time() - start_time) * 1000)
            debug.llm_response("yourai", response, model=MODEL_YOURAI_OPENROUTER, duration_ms=duration)
            log("YOURAI", f"☁️ OpenRouter responded in {duration}ms", Fore.GREEN)
            success = True

        except Exception as e:
            err = YourAILLMError("OpenRouter YourAI call failed", model=MODEL_YOURAI_OPENROUTER, tier="openrouter", cause=e)
            debug.error("yourai", err.short(), exception=err)
            log_exception("YOURAI", err)
            log("YOURAI", f"☁️ OpenRouter Failed! → Trying local...", Fore.RED)
    
    # TIER 2: LOKAL PRIMARY
    if not success:
        try:
            start_time = time.time()
            used_model = MODEL_YOURAI_LOCAL_PRIMARY
            log("YOURAI", f"🖥️ Calling local primary ({MODEL_YOURAI_LOCAL_PRIMARY})...", Fore.YELLOW)
            debug.llm_call("yourai", MODEL_YOURAI_LOCAL_PRIMARY, msg_content[:500])
            
            llm = create_thinking_llm(MODEL_YOURAI_LOCAL_PRIMARY, LLM_HOST_MAIN, temperature=temp, keep_alive="30m")
            user_msg = maybe_add_think_prompt(msg_content, MODEL_YOURAI_LOCAL_PRIMARY)
            response = str(llm.invoke([SystemMessage(content=formatted_sys), HumanMessage(content=user_msg)]).content)
            duration = int((time.time() - start_time) * 1000)
            
            debug.llm_response("yourai", response, model=MODEL_YOURAI_LOCAL_PRIMARY, duration_ms=duration)
            log("YOURAI", f"🖥️ Local primary responded in {duration}ms", Fore.GREEN)
            success = True
            
        except Exception as e:
            err = YourAILLMError("Local primary YourAI call failed", model=MODEL_YOURAI_LOCAL_PRIMARY, tier="local_primary", cause=e)
            debug.error("yourai", err.short(), exception=err)
            log_exception("YOURAI", err)
            log("YOURAI", f"🖥️ Local Primary Failed! → Last resort...", Fore.RED)
    
    # TIER 3: LOKAL FALLBACK
    if not success:
        try:
            start_time = time.time()
            used_model = MODEL_YOURAI_LOCAL_FALLBACK
            log("YOURAI", f"🔧 Calling local fallback ({MODEL_YOURAI_LOCAL_FALLBACK})...", Fore.YELLOW)
            debug.llm_call("yourai", MODEL_YOURAI_LOCAL_FALLBACK, msg_content[:500])
            
            llm = create_thinking_llm(MODEL_YOURAI_LOCAL_FALLBACK, LLM_HOST_STD, temperature=temp, keep_alive="5m")
            user_msg = maybe_add_think_prompt(msg_content, MODEL_YOURAI_LOCAL_FALLBACK)
            response = str(llm.invoke([SystemMessage(content=formatted_sys), HumanMessage(content=user_msg)]).content)
            duration = int((time.time() - start_time) * 1000)
            
            debug.llm_response("yourai", response, model=MODEL_YOURAI_LOCAL_FALLBACK, duration_ms=duration)
            log("YOURAI", f"🔧 Local fallback responded in {duration}ms", Fore.GREEN)
            success = True
            
        except Exception as e2:
            err = YourAIAllTiersFailedError(tiers_tried=["openrouter", "local_primary", "local_fallback"], cause=e2)
            debug.error("yourai", err.short(), exception=err)
            log_exception("YOURAI", err)
            response = f"My brain completely crashed... all 3 tiers failed! 🐾 Error: {e2}"
    
    show_llm("YourAI", used_model, response, role="yourai", show_thinking=True)

    # DISCORD DM POST-PROCESSOR
    # Scannt YourAIs Antwort auf [DM:Target] message [/DM] Tags
    # Auch unclosed Tags werden erkannt (LLMs vergessen manchmal [/DM])
    if USE_DISCORD and discord_client and discord_client.bot.connected:
        import re as _re

        # Step 1: Finde alle DM-Blöcke (closed und unclosed)
        # Closed: [DM:Mom] text [/DM]
        # Unclosed: [DM:Mom] text (bis zum nächsten [DM: oder Ende)
        dm_blocks = _re.findall(r'\[DM:(\w+)\]\s*(.*?)(?:\[/DM\]|(?=\[DM:)|\Z)', response, _re.DOTALL)

        for dm_target, dm_message in dm_blocks:
            dm_message = dm_message.strip()
            if not dm_message:
                continue

            # Target in Whitelist finden
            target_discord_id = None
            for did, ukey in DISCORD_DM_WHITELIST.items():
                if ukey.lower() == dm_target.lower():
                    target_discord_id = int(did)
                    break

            if target_discord_id:
                discord_client.bot.send_dm(target_discord_id, dm_message)
                log("YOURAI", f"📩 YourAI hat {dm_target} eine DM geschickt: {dm_message[:60]}...", Fore.GREEN)
                debug.info("yourai", f"DM sent to {dm_target}: {dm_message[:60]}")
            else:
                log("YOURAI", f"⚠️ DM Target '{dm_target}' nicht in Whitelist", Fore.YELLOW)

        # DM-Tags aus der sichtbaren Antwort entfernen (closed + unclosed)
        if dm_blocks:
            response = _re.sub(r'\[DM:\w+\].*?(?:\[/DM\]|(?=\[DM:)|\Z)', '', response, flags=_re.DOTALL).strip()

    # STICKER POST-PROCESSOR
    # Scannt YourAIs Antwort auf [STICKER:name] Tags und sendet sie
    if USE_DISCORD and discord_client and discord_client.bot.connected:
        import re as _re
        sticker_pattern = _re.compile(r'\[STICKER:([^\]]+)\]')
        sticker_matches = sticker_pattern.findall(response)

        for sticker_name in sticker_matches:
            sticker_name = sticker_name.strip()
            source = state.get("source", "console")

            if source == "discord_dm":
                # Sticker als DM an den aktuellen DM-Partner senden
                session_key = (session_manager.source_users.get("discord") or "").lower()
                for did, ukey in DISCORD_DM_WHITELIST.items():
                    if ukey.lower() == session_key:
                        discord_client.bot.send_sticker_dm(int(did), sticker_name)
                        break
            elif source == "discord":
                # Sticker im VIP Channel senden
                discord_client.bot.send_sticker(DISCORD_VIP_CHANNEL_ID, sticker_name)

        # Sticker-Tags aus der sichtbaren Antwort entfernen
        if sticker_matches:
            response = sticker_pattern.sub('', response).strip()

    # IMG TAG POST-PROCESSOR — [IMG:] aus sichtbarer Antwort entfernen (Tag wurde bereits gefeuert)
    import re as _re_img
    _img_pattern = _re_img.compile(r'\[IMG:[^\]]+\]')
    if _img_pattern.search(response):
        response = _img_pattern.sub('', response).strip()

    # SLEEPY TOOL BLOCKER — Drowsy/Furious: ALLE Tool-Tags strippen!
    # YourAI generiert manchmal trotzdem [SPOTIFY:] etc. obwohl sie schlafen soll.
    # Wir entfernen sie bevor sie ausgeführt werden.
    _, _current_tod, _ = personas.get_time_context()
    if _current_tod in ("drowsy", "furious"):
        import re as _sleepy_re
        _tool_tags = _sleepy_re.findall(r'\[(SPOTIFY|HOME|WEB|DOCS|IMG|ALTPERSONA|WEBSITE|REDESIGN|LAB_REDESIGN):[^\]]+\]', response)
        if _tool_tags:
            response = _sleepy_re.sub(r'\[(SPOTIFY|HOME|WEB|DOCS|IMG|ALTPERSONA|WEBSITE|REDESIGN|LAB_REDESIGN):[^\]]+\]', '', response).strip()
            log("BRAIN", f"💤 Sleepy Tool Blocker: {len(_tool_tags)} Tool-Tag(s) entfernt (YourAI schläft!)", Fore.MAGENTA)

    # SPOTIFY POST-PROCESSOR
    # Scannt YourAIs Antwort auf [SPOTIFY:command] Tags und führt sie aus
    # Commands werden NON-BLOCKING in einem Background-Thread ausgeführt,
    # damit die Discord/Dashboard Antwort sofort rausgeht.
    log("SPOTIFY", f"🔍 Post-Processor Check: USE_SPOTIFY={USE_SPOTIFY}, user_id='{state.get('user_id')}', has_tag={'[SPOTIFY:' in response}", Fore.CYAN)
    if USE_SPOTIFY and state.get("user_id") == "admin":
        import re as _re
        spotify_pattern = _re.compile(r'\[SPOTIFY:([^\]]+)\]')
        spotify_matches = spotify_pattern.findall(response)
        log("SPOTIFY", f"🔍 Matches found: {spotify_matches}", Fore.CYAN)

        if spotify_matches:
            # Tags sofort aus der Antwort entfernen (synchron, schnell)
            response = spotify_pattern.sub('', response).strip()

            # Spotify-Commands im Background-Thread ausführen
            import threading

            def _run_spotify_commands(commands):
                """Führt Spotify-Commands non-blocking im Hintergrund aus."""
                global _spotify_feedback_pending
                spotify_results = []
                debug.node_start("spotify", input_data=f"Commands: {', '.join(c.strip() for c in commands)}")

                try:
                    from tools.spotify_control import SpotifyControl
                    _spotify_ctrl = SpotifyControl()

                    for spotify_cmd in commands:
                        spotify_cmd = spotify_cmd.strip()
                        cmd_lower = spotify_cmd.lower()
                        log("SPOTIFY", f"🎵 YourAI executed: [SPOTIFY:{spotify_cmd}]", Fore.MAGENTA)

                        try:
                            # Basic controls
                            if cmd_lower == "skip":
                                _spotify_ctrl.api.skip_next()
                                spotify_results.append("✅ Skipped to next track")
                            elif cmd_lower == "pause":
                                _spotify_ctrl.api.pause()
                                spotify_results.append("✅ Paused")
                            elif cmd_lower == "resume":
                                _spotify_ctrl.api.play()
                                spotify_results.append("✅ Resumed playback")
                            elif cmd_lower == "previous":
                                _spotify_ctrl.api.skip_previous()
                                spotify_results.append("✅ Back to previous track")
                            elif cmd_lower.startswith("volume"):
                                vol_match = _re.search(r'(\d+)', cmd_lower)
                                if vol_match:
                                    vol = int(vol_match.group(1))
                                    _spotify_ctrl.api.set_volume(vol)
                                    spotify_results.append(f"✅ Volume set to {vol}%")

                            # Playlist controls
                            elif cmd_lower.startswith("shuffle"):
                                parts = spotify_cmd[7:].strip()
                                filter_artist = None
                                playlist_name = parts

                                filter_match = _re.search(r'filter=(.+)', parts)
                                if filter_match:
                                    filter_artist = filter_match.group(1).strip()
                                    playlist_name = parts[:filter_match.start()].strip()

                                log("SPOTIFY", f"🎲 Parsed: playlist='{playlist_name}', filter='{filter_artist}'", Fore.CYAN)

                                if playlist_name:
                                    result = _spotify_ctrl.shuffle_playlist(playlist_name, filter_artist=filter_artist)
                                    log("SPOTIFY", f"🎲 Result: {result}", Fore.CYAN)
                                    if result.get('success'):
                                        msg = result.get('message', 'Shuffle done')
                                        log("SPOTIFY", f"🎲 {msg}", Fore.GREEN)
                                        spotify_results.append(f"✅ {msg}")
                                    else:
                                        err = result.get('error', 'Shuffle failed')
                                        log("SPOTIFY", f"❌ {err}", Fore.RED)
                                        spotify_results.append(f"❌ {err}")
                                else:
                                    log("SPOTIFY", f"⚠️ No playlist name parsed from: '{parts}'", Fore.YELLOW)
                                    spotify_results.append("❌ No playlist name given. Which playlist should I shuffle?")

                            elif cmd_lower.startswith("sort_bpm"):
                                parts = spotify_cmd[8:].strip()
                                ascending = "asc" in parts.lower()
                                playlist_name = _re.sub(r'\b(asc|desc)\b', '', parts).strip()
                                if playlist_name:
                                    result = _spotify_ctrl.sort_by_bpm(playlist_name, ascending=ascending)
                                    if result.get('success'):
                                        msg = result.get('message', 'Sort done')
                                        log("SPOTIFY", f"📊 {msg}", Fore.GREEN)
                                        spotify_results.append(f"✅ {msg}")
                                    else:
                                        err = result.get('error', 'BPM sort failed')
                                        log("SPOTIFY", f"❌ {err}", Fore.RED)
                                        spotify_results.append(f"❌ {err}")
                                else:
                                    log("SPOTIFY", f"⚠️ No playlist name for sort_bpm", Fore.YELLOW)
                                    spotify_results.append("❌ No playlist name given. Which playlist should I sort by BPM?")

                            elif cmd_lower.startswith("sort_energy"):
                                parts = spotify_cmd[11:].strip()
                                ascending = "asc" in parts.lower()
                                playlist_name = _re.sub(r'\b(asc|desc)\b', '', parts).strip()
                                if playlist_name:
                                    result = _spotify_ctrl.sort_by_energy(playlist_name, ascending=ascending)
                                    if result.get('success'):
                                        msg = result.get('message', 'Sort done')
                                        log("SPOTIFY", f"⚡ {msg}", Fore.GREEN)
                                        spotify_results.append(f"✅ {msg}")
                                    else:
                                        err = result.get('error', 'Energy sort failed')
                                        log("SPOTIFY", f"❌ {err}", Fore.RED)
                                        spotify_results.append(f"❌ {err}")
                                else:
                                    log("SPOTIFY", f"⚠️ No playlist name for sort_energy", Fore.YELLOW)
                                    spotify_results.append("❌ No playlist name given. Which playlist should I sort by energy?")

                            elif cmd_lower.startswith("yourai_shuffle"):
                                parts = spotify_cmd[13:].strip()
                                filter_artist = None
                                playlist_name = parts

                                filter_match = _re.search(r'filter=(.+)', parts)
                                if filter_match:
                                    filter_artist = filter_match.group(1).strip()
                                    playlist_name = parts[:filter_match.start()].strip()

                                log("SPOTIFY", f"🦊 YourAI DJ: playlist='{playlist_name}', filter='{filter_artist}'", Fore.MAGENTA)

                                if playlist_name:
                                    result = _spotify_ctrl.yourai_shuffle(playlist_name, filter_artist=filter_artist)
                                    if result.get('success'):
                                        msg = result.get('message', 'YourAI DJ Shuffle done')
                                        log("SPOTIFY", f"🦊 {msg}", Fore.GREEN)
                                        spotify_results.append(f"✅ {msg}")
                                    else:
                                        err = result.get('error', 'YourAI Shuffle failed')
                                        log("SPOTIFY", f"❌ {err}", Fore.RED)
                                        spotify_results.append(f"❌ {err}")
                                else:
                                    log("SPOTIFY", f"⚠️ No playlist name for yourai_shuffle", Fore.YELLOW)
                                    spotify_results.append("❌ No playlist name given. Which playlist should I DJ shuffle?")

                            elif cmd_lower.startswith("sort_key"):
                                parts = spotify_cmd[8:].strip()
                                key_match = _re.search(r'\b(\d{1,2}[AB])\b', parts, _re.IGNORECASE)
                                target_key = key_match.group(1) if key_match else None
                                playlist_name = _re.sub(r'\b\d{1,2}[AB]\b', '', parts, flags=_re.IGNORECASE).strip()
                                if playlist_name:
                                    result = _spotify_ctrl.sort_by_key(playlist_name, target_key=target_key)
                                    if result.get('success'):
                                        msg = result.get('message', 'Key sort done')
                                        log("SPOTIFY", f"🎹 {msg}", Fore.GREEN)
                                        spotify_results.append(f"✅ {msg}")
                                    else:
                                        err = result.get('error', 'Key sort failed')
                                        log("SPOTIFY", f"❌ {err}", Fore.RED)
                                        spotify_results.append(f"❌ {err}")
                                else:
                                    log("SPOTIFY", f"⚠️ No playlist name for sort_key", Fore.YELLOW)
                                    spotify_results.append("❌ No playlist name given. Which playlist should I sort by key?")

                            elif cmd_lower.startswith("queue"):
                                queue_arg = spotify_cmd[5:].strip()
                                if queue_arg:
                                    result = _spotify_ctrl.queue_playlist(queue_arg)
                                    if result.get('success'):
                                        msg = result.get('message', 'Queued')
                                        log("SPOTIFY", f"📋 {msg}", Fore.GREEN)
                                        spotify_results.append(f"✅ {msg}")
                                    else:
                                        err = result.get('error', 'Queue failed')
                                        log("SPOTIFY", f"❌ {err}", Fore.RED)
                                        spotify_results.append(f"❌ {err}")
                                else:
                                    result = _spotify_ctrl.get_queue_info()
                                    msg = result.get('message', 'Queue loaded')
                                    log("SPOTIFY", f"📋 {msg}", Fore.CYAN)
                                    spotify_results.append(f"✅ {msg}")

                            else:
                                log("SPOTIFY", f"⚠️ Unknown Spotify command: {spotify_cmd}", Fore.YELLOW)
                                spotify_results.append(f"❌ Unknown command: {spotify_cmd}")

                        except Exception as cmd_err:
                            log("SPOTIFY", f"❌ Command failed [{spotify_cmd}]: {cmd_err}", Fore.RED)
                            spotify_results.append(f"❌ {spotify_cmd} failed: {cmd_err}")

                except Exception as e:
                    log("SPOTIFY", f"❌ Post-processor error: {e}", Fore.RED)
                    debug.error("spotify", f"Post-processor error: {e}", exception=e)
                    spotify_results.append(f"❌ Spotify error: {e}")

                # Feedback für nächsten YourAI-Call speichern
                if spotify_results:
                    _spotify_feedback_pending = " | ".join(spotify_results)
                    log("SPOTIFY", f"📨 Feedback stored for next call: {_spotify_feedback_pending}", Fore.CYAN)
                    debug.info("spotify", f"📨 Feedback: {_spotify_feedback_pending}")
                debug.node_end("spotify")

            # Thread starten — Discord/Dashboard Antwort geht sofort raus
            spotify_thread = threading.Thread(
                target=_run_spotify_commands,
                args=(spotify_matches,),
                daemon=True,
                name="spotify-postprocessor"
            )
            spotify_thread.start()
            log("SPOTIFY", f"🚀 {len(spotify_matches)} command(s) an Background-Thread übergeben", Fore.GREEN)

    # FILE BRAIN POST-PROCESSOR
    # Scannt auf [FILE:command] Tags und führt sie aus
    if "[FILE:" in response:
        import re as _re
        file_pattern = _re.compile(r'\[FILE:([^\]]+)\]')
        file_matches = file_pattern.findall(response)

        if file_matches:
            file_results = []
            try:
                from tools.file_brain import get_file_brain
                _fb = get_file_brain()

                for file_cmd in file_matches:
                    file_cmd = file_cmd.strip()
                    cmd_lower = file_cmd.lower()
                    log("FILE_BRAIN", f"📁 YourAI executed: [FILE:{file_cmd}]", Fore.MAGENTA)

                    try:
                        if cmd_lower.startswith("search "):
                            query = file_cmd[7:].strip()
                            result = _fb.search(query)
                            file_results.append(result.get("message", "Search done"))

                        elif cmd_lower.startswith("read "):
                            path = file_cmd[5:].strip()
                            result = _fb.read(path)
                            if result.get("content"):
                                # Content in die Antwort injizieren (YourAI sieht es beim nächsten Call)
                                file_results.append(result.get("message", "Read done"))
                                file_results.append(f"CONTENT:\n{result['content'][:8000]}")
                            else:
                                file_results.append(result.get("message", result.get("error", "Read failed")))

                        elif cmd_lower.startswith("list"):
                            arg = file_cmd[4:].strip()
                            if arg:
                                result = _fb.list_doc(arg)
                            else:
                                result = _fb.list_all()
                            file_results.append(result.get("message", "List done"))

                        elif cmd_lower.startswith("ingest "):
                            filepath = file_cmd[7:].strip().strip('"').strip("'")
                            result = _fb.ingest(filepath)
                            msg = result.get("message", result.get("error", "Ingest done"))
                            log("FILE_BRAIN", f"📖 {msg}", Fore.GREEN)
                            file_results.append(msg)

                        else:
                            file_results.append(f"Unknown FILE command: {file_cmd}")

                    except Exception as cmd_err:
                        log("FILE_BRAIN", f"❌ {file_cmd} failed: {cmd_err}", Fore.RED)
                        file_results.append(f"Error: {cmd_err}")

            except Exception as e:
                log("FILE_BRAIN", f"❌ File Brain error: {e}", Fore.RED)

            # Tags aus Response entfernen
            response = file_pattern.sub('', response).strip()

            # Feedback für nächsten YourAI-Call speichern
            if file_results:
                global _file_feedback_pending
                _file_feedback_pending = "\n".join(file_results)
                log("FILE_BRAIN", f"📨 Feedback stored ({len(file_results)} results)", Fore.CYAN)

    # WEB SEARCH POST-PROCESSOR
    # Scannt auf [WEB:query] Tags und führt sie aus
    if "[WEB:" in response and USE_WEB_SEARCH:
        import re as _re_web
        web_pattern = _re_web.compile(r'\[WEB:([^\]]+)\]')
        web_matches = web_pattern.findall(response)

        if web_matches:
            try:
                from tools.web_search import web_search as _web_search, format_results_for_prompt
                web_results = []

                for web_query in web_matches:
                    web_query = web_query.strip()
                    log("WEB", f"🌐 YourAI searched: [WEB:{web_query}]", Fore.MAGENTA)

                    try:
                        result = _web_search(web_query)
                        if result.get("success") and result.get("results"):
                            web_results.append(format_results_for_prompt(result))
                        else:
                            web_results.append(result.get("message", f"No results for '{web_query}'"))
                    except Exception as web_err:
                        log("WEB", f"❌ {web_query} failed: {web_err}", Fore.RED)
                        web_results.append(f"Search error: {web_err}")

            except Exception as e:
                log("WEB", f"❌ Web search error: {e}", Fore.RED)

            # Tags aus Response entfernen
            response = web_pattern.sub('', response).strip()

            # Feedback für nächsten YourAI-Call speichern
            if web_results:
                global _web_feedback_pending
                _web_feedback_pending = "\n".join(web_results)
                log("WEB", f"📨 Feedback stored ({len(web_results)} results)", Fore.CYAN)

    # ALTPERSONA POST-PROCESSOR
    if "[ALTPERSONA:" in response:
        import re as _re_altpersona
        altpersona_pattern = _re_altpersona.compile(r'\[ALTPERSONA:([^\]]+)\]')
        altpersona_matches = altpersona_pattern.findall(response)

        if altpersona_matches:
            altpersona_results = []
            try:
                from tools.altpersona_consult import consult_altpersona as _consult_altpersona
                for altpersona_query in altpersona_matches:
                    altpersona_query = altpersona_query.strip()
                    log("ALTPERSONA", f"😈 YourAI fragt AltPersona: [ALTPERSONA:{altpersona_query}]", Fore.MAGENTA)
                    try:
                        _altpersona_ctx_data = {"question": altpersona_query, "user_name": state.get("user_name", "")}
                        result = _consult_altpersona(_altpersona_ctx_data, debug)
                        if result.get("success"):
                            altpersona_results.append(result["result"])
                        else:
                            altpersona_results.append(result.get("error", "AltPersona ist nicht erreichbar."))
                    except Exception as err:
                        log("ALTPERSONA", f"❌ AltPersona failed: {err}", Fore.RED)
                        altpersona_results.append(f"Error: {err}")
            except Exception as e:
                log("ALTPERSONA", f"❌ AltPersona Post-Processor error: {e}", Fore.RED)

            # Tags aus Response entfernen
            response = altpersona_pattern.sub('', response).strip()

            if altpersona_results:
                global _altpersona_feedback_pending
                _altpersona_feedback_pending = "\n".join(altpersona_results)
                log("ALTPERSONA", f"📨 Feedback stored ({len(altpersona_results)} results)", Fore.CYAN)

    # WEBSITE POST-PROCESSOR
    if "[WEBSITE:" in response:
        import re as _re_website
        website_pattern = _re_website.compile(r'\[WEBSITE:([^\]]+)\]')
        website_matches = website_pattern.findall(response)

        if website_matches:
            website_results = []
            try:
                from tools.website import update_quote
                for website_quote in website_matches:
                    website_quote = website_quote.strip()
                    log("WEBSITE", f"🌐 YourAI updates website: [WEBSITE:{website_quote}]", Fore.MAGENTA)
                    try:
                        _website_ctx_data = {"quote_text": website_quote}
                        result = update_quote(_website_ctx_data, debug)
                        if result.get("success"):
                            website_results.append("Website erfolgreich aktualisiert!")
                        else:
                            website_results.append(result.get("error", "Website konnte nicht aktualisiert werden."))
                    except Exception as err:
                        log("WEBSITE", f"❌ Website update failed: {err}", Fore.RED)
                        website_results.append(f"Error: {err}")
            except Exception as e:
                log("WEBSITE", f"❌ Website Post-Processor error: {e}", Fore.RED)

            # Tags aus Response entfernen
            response = website_pattern.sub('', response).strip()

            if website_results:
                global _website_feedback_pending
                _website_feedback_pending = "\n".join(website_results)
                log("WEBSITE", f"📨 Feedback stored ({len(website_results)} results)", Fore.CYAN)


    # REDESIGN POST-PROCESSOR
    # [REDESIGN:reason] triggert das volle autonome Website-Update (HTML/CSS/Deploy)
    if "[REDESIGN:" in response:
        import re as _re_redesign
        redesign_pattern = _re_redesign.compile(r'\[REDESIGN:([^\]]*)\]')
        redesign_matches = redesign_pattern.findall(response)

        if redesign_matches:
            reason = redesign_matches[0].strip() or "YourAI triggered a redesign"
            log("WEBSITE_AUTO", f"🎨 YourAI triggered REDESIGN: {reason}", Fore.MAGENTA)

            # Tag sofort aus der Antwort entfernen
            response = redesign_pattern.sub('', response).strip()

            # Autonomes Website-Update im Hintergrund starten
            try:
                from tools.website_autonomy import maybe_trigger_website_update
                maybe_trigger_website_update(debug, force=True, yourai_hint=reason)
                log("WEBSITE_AUTO", f"🚀 Autonomous redesign started! Hint: {reason}", Fore.GREEN)
            except Exception as _re_err:
                log("WEBSITE_AUTO", f"❌ Redesign trigger failed: {_re_err}", Fore.RED)

    # LAB_REDESIGN POST-PROCESSOR
    # [LAB_REDESIGN:idea] triggert das autonome Lab-Update (keine Filter, volle Freiheit!)
    if "[LAB_REDESIGN:" in response:
        import re as _re_lab
        lab_pattern = _re_lab.compile(r'\[LAB_REDESIGN:([^\]]*)\]')
        lab_matches = lab_pattern.findall(response)

        if lab_matches:
            lab_reason = lab_matches[0].strip() or "YourAI wants to build something in the lab"
            log("WEBSITE_LAB", f"🎪 YourAI triggered LAB_REDESIGN: {lab_reason}", Fore.MAGENTA)

            # Tag sofort aus der Antwort entfernen
            response = lab_pattern.sub('', response).strip()

            # Lab-Update im Hintergrund starten
            try:
                from tools.website_autonomy_lab import maybe_trigger_lab_update
                maybe_trigger_lab_update(debug, force=True, yourai_hint=lab_reason)
                log("WEBSITE_LAB", f"🚀 Lab experiment started! Idea: {lab_reason}", Fore.GREEN)
            except Exception as _lab_err:
                log("WEBSITE_LAB", f"❌ Lab trigger failed: {_lab_err}", Fore.RED)

    # PAPERLESS POST-PROCESSOR
    # Scannt auf [DOCS:command] Tags und führt sie aus
    if "[DOCS:" in response and USE_PAPERLESS:
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

                for docs_cmd in docs_matches:
                    docs_cmd = docs_cmd.strip()
                    cmd_lower = docs_cmd.lower()
                    log("PAPERLESS", f"📄 YourAI executed: [DOCS:{docs_cmd}]", Fore.MAGENTA)

                    try:
                        if cmd_lower.startswith("search "):
                            result = _docs_search(docs_cmd[7:].strip())
                            docs_results.append(_fmt_search(result) if result.get("success") else result.get("message", "No results"))
                        elif cmd_lower.startswith("read "):
                            doc_id = int(docs_cmd[5:].strip())
                            result = _docs_read(doc_id)
                            docs_results.append(_fmt_doc(result) if result.get("success") else result.get("message", "Read failed"))
                        elif cmd_lower == "tags":
                            result = _docs_tags()
                            docs_results.append(result.get("message", "No tags"))
                        elif cmd_lower == "correspondents":
                            result = _docs_corrs()
                            docs_results.append(result.get("message", "No correspondents"))
                        elif cmd_lower == "types":
                            result = _docs_types()
                            docs_results.append(result.get("message", "No types"))
                        else:
                            docs_results.append(f"Unknown DOCS command: {docs_cmd}")
                    except Exception as cmd_err:
                        log("PAPERLESS", f"❌ {docs_cmd} failed: {cmd_err}", Fore.RED)
                        docs_results.append(f"Error: {cmd_err}")

            except Exception as e:
                log("PAPERLESS", f"❌ Paperless error: {e}", Fore.RED)

            # Tags aus Response entfernen
            response = docs_pattern.sub('', response).strip()

            # Feedback für nächsten YourAI-Call speichern
            if docs_results:
                global _docs_feedback_pending
                _docs_feedback_pending = "\n\n".join(docs_results)
                log("PAPERLESS", f"📨 Docs feedback stored ({len(docs_results)} commands)", Fore.CYAN)

    # HOME ASSISTANT POST-PROCESSOR
    # Scannt auf [HOME:command] Tags und führt sie aus
    if "[HOME:" in response and USE_HOME_ASSISTANT and state.get("user_id") == "admin":
        import re as _re_home
        home_pattern = _re_home.compile(r'\[HOME:([^\]]+)\]')
        home_matches = home_pattern.findall(response)

        if home_matches:
            try:
                from tools.home_assistant import execute_home_command as _ha_exec, format_result_for_prompt as _fmt_ha
                home_results = []

                for home_cmd in home_matches:
                    home_cmd = home_cmd.strip()
                    log("HOME", f"🏠 YourAI executed: [HOME:{home_cmd}]", Fore.MAGENTA)

                    try:
                        result = _ha_exec(home_cmd)
                        home_results.append(_fmt_ha(result))
                    except Exception as cmd_err:
                        log("HOME", f"❌ {home_cmd} failed: {cmd_err}", Fore.RED)
                        home_results.append(f"Error: {cmd_err}")

            except Exception as e:
                log("HOME", f"❌ Home Assistant error: {e}", Fore.RED)

            # Tags aus Response entfernen
            response = home_pattern.sub('', response).strip()

            # Feedback für nächsten YourAI-Call speichern
            if home_results:
                global _home_feedback_pending
                _home_feedback_pending = "\n\n".join(home_results)
                log("HOME", f"📨 HA feedback stored ({len(home_results)} commands)", Fore.CYAN)


    # NEEDHELP POST-PROCESSOR
    # YourAI uses [NeedHelp: message] to send Admin a private Discord DM
    if "[NeedHelp:" in response:
        import re as _re_help
        _help_matches = _re_help.findall(r'\[NeedHelp:\s*(.*?)\]', response, _re_help.DOTALL)
        if _help_matches:
            response = _re_help.sub(r'\[NeedHelp:.*?\]', '', response, flags=_re_help.DOTALL).strip()
            for _help_msg in _help_matches:
                _help_msg = _help_msg.strip()
                if not _help_msg:
                    continue
                log("BRAIN", f"🆘 [NeedHelp:] — YourAI needs help: {_help_msg[:80]}", Fore.MAGENTA)
                debug.info("system", f"🆘 YourAI NeedHelp: {_help_msg[:200]}")
                if USE_DISCORD and discord_client and discord_client.bot.connected:
                    _admin_did = None
                    _ADMIN_KEYS = {"dad", "creator", "admin", "admin"}  # admin = YourAI's dad/owner
                    for _adid, _aukey in DISCORD_DM_WHITELIST.items():
                        if _aukey.lower() in _ADMIN_KEYS:
                            _admin_did = int(_adid)
                            break
                    if _admin_did:
                        discord_client.bot.send_dm(_admin_did, f"🆘 YourAI needs help:\n{_help_msg}")
                        log("BRAIN", "📩 [NeedHelp:] DM sent to admin", Fore.GREEN)
                    else:
                        log("BRAIN", "⚠️ [NeedHelp:] no admin found in DISCORD_DM_WHITELIST", Fore.YELLOW)

    # PERFORMANCE TRACKING
    if hasattr(personas, 'persona_manager'):
        if success:
            personas.persona_manager.record_success()
        else:
            personas.persona_manager.record_failure()

    # SAVING TO MEMORY & DIARY
    if USE_MEMORY:
        hippocampus.memory.extract_and_save(state["question"])
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
    if x.get("altpersona_mode"):
        return "altpersona_direct" 
    return "granite" 

workflow.add_conditional_edges(
    "autonomy_guard",
    route_after_autonomy,
    {"granite": "granite", "altpersona_direct": "altpersona_uncensored"}
)

def route_check(x): 
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

def process_input(text: str, user: str, source: str, history: List[str], image_urls: Optional[list] = None, discord_id: str = "", channel_id: int = 0, session_uuid: str = ""):
    """Verarbeitet eine Eingabe durch die Pipeline."""
    # Hot-Reload: Dashboard-Toggles sofort wirksam ohne Restart!
    reload_runtime_flags()
    global USE_MEMORY, USE_VOICE, USE_THINKING, USE_COHERENCE_CHECK, USE_GRANITE, USE_TOOLS, USE_STREAMING
    global USE_IMAGE_GEN, IMAGE_MODEL
    USE_MEMORY = _cfg.USE_MEMORY
    USE_VOICE = _cfg.USE_VOICE
    USE_THINKING = _cfg.USE_THINKING
    USE_COHERENCE_CHECK = _cfg.USE_COHERENCE_CHECK
    USE_GRANITE = _cfg.USE_GRANITE
    USE_TOOLS = getattr(_cfg, 'USE_TOOLS', True)
    USE_PROMISE_CHECK = getattr(_cfg, 'USE_PROMISE_CHECK', True)
    USE_STREAMING = _cfg.USE_STREAMING
    USE_WEB_SEARCH = getattr(_cfg, 'USE_WEB_SEARCH', True)
    USE_PAPERLESS = getattr(_cfg, 'USE_PAPERLESS', True)
    USE_HOME_ASSISTANT = getattr(_cfg, 'USE_HOME_ASSISTANT', True)
    USE_IMAGE_GEN = getattr(_cfg, 'USE_IMAGE_GEN', True)
    IMAGE_MODEL = getattr(_cfg, 'IMAGE_MODEL', 'sourceful/riverflow-v2-fast')

    pipeline_start_time = time.time()

    session_manager._load()

    debug.pipeline_start(user, text, source, for_user=session_manager.get_current_user_id(source))

    # ==========================================
    # SLEEP INTERCEPT — YourAI schläft! 💤
    # Ab deep_sleep wird die Pipeline NICHT aufgerufen.
    # YourAI antwortet direkt mit Schlaf-Nachrichten.
    # Kein LLM, kein OpenRouter, keine Tools. 0 Tokens.
    # ==========================================
    _, _time_of_day, _ = personas.get_time_context()
    if _time_of_day == "deep_sleep":
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
        # Personalisierte Responses mit @mention
        _sleep_mention_responses = [
            "{mention} ...go to sleep... I'm sleeping too... 💤",
            "{mention} LEAVE ME ALONE 😡 ...z.z.z.Z.Z.Z 💤",
            "{mention} it's way too late... tomorrow... 💤",
            "{mention} no... sleeping... you too... good night... 💤💤",
            "{mention} I'M SLEEPING 😡 *throws pillow* 💤",
            "{mention} ...why... *yawns* ...ask me tomorrow... 💤",
        ]

        # Wähle Response — mit oder ohne Mention
        if discord_id and _sleep_rng.random() < 0.5:
            _sleep_answer = _sleep_rng.choice(_sleep_mention_responses).format(mention=f"<@{discord_id}>")
        elif user and user != "unknown" and _sleep_rng.random() < 0.4:
            _sleep_answer = _sleep_rng.choice(_sleep_mention_responses).format(mention=user)
        else:
            _sleep_answer = _sleep_rng.choice(_sleep_responses)

        total_ms = int((time.time() - pipeline_start_time) * 1000)
        log("BRAIN", f"💤 SLEEP INTERCEPT — YourAI schläft! Response: {_sleep_answer}", Fore.MAGENTA)
        debug.info("sleep_intercept", f"💤 YourAI schläft! Pipeline übersprungen.", f"Response: {_sleep_answer}")

        import uuid as _sleep_uuid
        _sleep_tracking_id = f"sleep_{_sleep_uuid.uuid4().hex[:12]}"
        debug.pipeline_end(_sleep_answer, total_ms, tracking_id=_sleep_tracking_id, source=source, for_user=session_manager.get_current_user_id(source))
        _append_yourai_output(_sleep_answer)

        # Antwort über den richtigen Kanal senden (OHNE Feedback-Reactions)
        if discord_client and source in ("discord", "discord_dm", "discord_private"):
            _discord_sleep_answer = _sleep_answer + " :sleepingfox:"
            discord_client.bot._feedback_enabled = False
            if source == "discord":
                discord_client.bot.send_channel(DISCORD_VIP_CHANNEL_ID, _discord_sleep_answer)
            elif source == "discord_dm" and discord_id:
                # DM direkt an den Absender zurück (nicht Session-User!)
                discord_client.bot.send_dm(int(discord_id), _discord_sleep_answer)
            elif source == "discord_private" and channel_id:
                discord_client.bot.send_channel(channel_id, _discord_sleep_answer)
            discord_client.bot._feedback_enabled = True
        history.append(f"User: {text}")
        history.append(f"YourAI: {_sleep_answer}")
        return _sleep_answer
    # ==========================================

    print(f"\n{Style.BRIGHT}--- PROCESSING NEW REQUEST ---{Style.RESET_ALL}")

    current_user_id = session_manager.get_current_user_id(source)
    
    if hasattr(personas, 'persona_manager'):
        if hasattr(personas.persona_manager, 'set_current_user'):
            personas.persona_manager.set_current_user(current_user_id)
        
        if hasattr(personas.persona_manager, 'process_user_message'):
            reaction = personas.persona_manager.process_user_message(text)
            if reaction:
                log("EMOTION", f"💕 {reaction}", Fore.MAGENTA)
        
        detect_promises_and_emotions(text, user, personas.persona_manager)
        
        try:
            if USE_PROMISE_CHECK:
                def run_llm_promise_check():
                    return llm_promise_check(
                        current_message=text,
                        recent_history=history[-5:] if history else [],
                        persona_manager=personas.persona_manager,
                        llm_host=LLM_HOST_STD,
                        model=MODEL_PROMISE_CHECK,
                        timeout=PROMISE_CHECK_TIMEOUT,
                        debug=debug
                    )
                
                _get_promise_executor().submit(run_llm_promise_check)
            
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="promise_check_thread")
            log_exception("PROMISE", err)
        
        pm = personas.persona_manager
        mood_info = pm.get_mood_info()
        if pm.current_mood in ["pouting", "disappointed"]:
            log("EMOTION", f"😤 YourAI is {mood_info['name']}! Stubbornness: {mood_info['stubbornness']}/10 (User: {current_user_id})", Fore.YELLOW)
    
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
        "password_status": "nokey",
        "expert_domain": "fallback",
        "expert_fact": "",
        "final_response": "",
        "current_mood": "default",
        "used_model": "init",
        "vision_done": False,
        "coherence_warning": None,
        "guard_halted": False,
        "tool_name": None,      
        "tool_info": None,      
        "tool_result": None,    
        "guest_context": session_manager.get_user_context(source),
        "altpersona_mode": session_manager.is_altpersona_mode(source),
        "error_context": None,
        "spotify_context": None,
        "web_context": None,
        "docs_context": None,
        "altpersona_context": None,
        "image_urls": image_urls or [],
        "user_id": current_user_id,
        "channel_id": channel_id,
        "session_uuid": session_uuid or "",
    }

    # Vision: Bilder analysieren bevor die Pipeline startet
    # Discord DM: nur Admin | Web Dashboard: alle authentifizierten User
    if image_urls and eyes and source == "discord_dm":
        if current_user_id != "admin":
            err = YourAINoPrivilegeError(current_user_id or "unknown", "analyze images via Discord")
            log("VISION", f"🚫 {err.short()}", Fore.RED)
            raw_state["error_context"] = err.short()
            image_urls = []  # Bilder verwerfen

    if image_urls and eyes and source in ("discord_dm", "web"):
        vision_descs = []
        for img_url in image_urls:
            try:
                vision_prompt = f"""TASK: Describe what you see in this image. Be FACTUAL and OBJECTIVE.
USER MESSAGE: {text}
RULES:
1. ONLY describe what is VISIBLE in the image
2. Do NOT chat, opinions, or say "wow"
3. Be brief and factual
DESCRIBE THE IMAGE:"""
                desc = eyes.see_url(img_url, prompt=vision_prompt)
                vision_descs.append(desc)
            except YourAIVisionError as e:
                log_exception("VISION", e)
                vision_descs.append(e.short())
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="vision_url")
                log_exception("VISION", err)
                vision_descs.append(err.short())

        if vision_descs:
            image_context = "\n".join(f"IMAGE {i+1}: {d}" for i, d in enumerate(vision_descs))
            raw_state["question"] = f"CONTEXT FROM IMAGE(S): {image_context}\n\nORIGINAL USER MESSAGE: {text}"
            raw_state["visual_context"] = image_context
            raw_state["vision_done"] = True
            log("VISION", f"🖼️ {len(vision_descs)} Bild(er) analysiert (source: {source})", Fore.GREEN)

    if raw_state["altpersona_mode"]:
        print(f"{Fore.MAGENTA}{Style.BRIGHT}😈 ALTPERSONA MODE AKTIV - Granite wird übersprungen!{Style.RESET_ALL}")
    
    try:
        result = app.invoke(cast(AgentState, raw_state))
        final_answer = result.get("final_response", "Error.")
        
        total_ms = int((time.time() - pipeline_start_time) * 1000)

        _, clean_text = extract_thoughts(final_answer)

        clean_text = _RESPONSE_HEADER_RE.sub('', clean_text)

        # Discord: Emoji-Beschreibungen entfernen die YourAI manchmal mitkopiert
        # :catsmile: (smiling cat) → :catsmile:
        if source in ("discord", "discord_dm", "discord_private") and DISCORD_CUSTOM_EMOJIS:
            import re as _re_emoji
            for emoji_name in DISCORD_CUSTOM_EMOJIS:
                # Pattern: :name: gefolgt von optionalem Space + (beschreibung)
                clean_text = _re_emoji.sub(
                    rf'(:{emoji_name}:)\s*\([^)]*\)',
                    rf'\1',
                    clean_text
                )

        # Voice/Twitch: Emojis + Markdown entfernen (TTS kann das nicht)
        # Discord: Emojis + Markdown behalten (Discord unterstützt beides!)
        tts_text = _STRIP_EMOJIS_RE.sub('', clean_text).replace("*", "")

        # === FEEDBACK TRACKING ===
        try:
            from feedback import FeedbackStore
            fb = FeedbackStore()
            _domain = result.get("expert_domain")
            # Use the model that actually answered (from fallback chain), not the configured one
            _expert_model = result.get("expert_model_used") or (EXPERT_MODELS.get(_domain, "") if _domain else None)
            _tracking_id = fb.log_response(
                expert_domain=_domain,
                expert_model=_expert_model,
                yourai_model=MODEL_YOURAI_OPENROUTER if _cfg.USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY,
                source=source,
                had_expert=_domain not in (None, "fallback", "smalltalk"),
                user_id=current_user_id,
            )
            # Pending tracking ID für Discord Bot
            if discord_client and source in ("discord", "discord_dm", "discord_private"):
                discord_client.bot._pending_tracking_id = _tracking_id
        except Exception:
            _tracking_id = None

        # Dashboard: Pipeline End mit tracking_id + source/user für Sicherheitsfilter
        # Model-Name nie leaken — nur ZDR-Flag senden
        # Expert-Info nur wenn tatsächlich ein Experte benutzt wurde
        _expert_domain = result.get("expert_domain")
        _expert_model_used = result.get("expert_model_used")
        _show_expert = bool(
            _expert_domain and _expert_domain not in (None, "fallback", "smalltalk")
            and _expert_model_used
        )
        debug.pipeline_end(
            final_answer, total_ms,
            tracking_id=_tracking_id,
            source=source,
            for_user=current_user_id,
            model="ZDR",  # nur ZDR-Indikator, kein Modellname
            expert_domain=_expert_domain if _show_expert else None,
            expert_model=_expert_model_used if _show_expert else None,
        )

        # YourAI Output Log: Antwort 1:1 in yourai_output.txt (max 15MB)
        _append_yourai_output(final_answer)

        # App Chat Log (persistent in docker_data) + FCM push
        _append_chat_log(current_user_id, source, text, clean_text, tracking_id=_tracking_id or "")
        _send_fcm_notification(current_user_id, clean_text)

        if USE_VOICE and mouth:
            mouth.speak(tts_text)
        elif source == "twitch" and twitch_client:
            twitch_client.bot.send_chat(f"@{user} {tts_text}")
        elif source == "discord" and discord_client:
            # @mention wenn mehrere User gleichzeitig aktiv sind
            if discord_id:
                mention_text = f"<@{discord_id}> {clean_text}"
            else:
                mention_text = clean_text
            discord_client.bot.send_channel(DISCORD_VIP_CHANNEL_ID, mention_text)
        elif source == "discord_private" and discord_client and channel_id:
            # Privater Channel: direkt antworten (kein @mention nötig, es ist ihr Channel)
            discord_client.bot.send_channel(channel_id, clean_text)
        elif source == "discord_dm" and discord_client:
            # DM zurückschicken: Session Key → Whitelist → Discord ID
            session_key = session_manager.source_users.get("discord") or ""
            dm_target = None
            for did, ukey in DISCORD_DM_WHITELIST.items():
                if ukey.lower() == session_key.lower():
                    dm_target = int(did)
                    break
            if dm_target:
                discord_client.bot.send_dm(dm_target, clean_text)
            else:
                log("BRAIN", f"⚠️ Kein Discord ID für Session '{session_key}' gefunden, sende in VIP Channel", Fore.YELLOW)
                discord_client.bot.send_channel(DISCORD_VIP_CHANNEL_ID, clean_text)
        
        history.append(f"User: {text}")
        _bot_label = "AltPersona" if session_manager.is_altpersona_mode(source) else "YourAI"
        history.append(f"{_bot_label}: {clean_text}")
        
        if source != "twitch" and session_manager.get_current_user_id(source) == "admin":
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
