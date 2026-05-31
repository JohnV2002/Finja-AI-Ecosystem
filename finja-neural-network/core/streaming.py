"""
YourAI Streaming Dispatcher
==========================
Streaming response dispatcher that detects tool tags and invokes callback handlers.

Main Responsibilities:
- Parse streamed model text for supported command tags.
- Start tool callbacks in daemon threads without blocking text streaming.
- Preserve visible response text while extracting hidden command tags.

Side Effects:
- Starts background threads for tool execution.
- Calls injected callback functions that may perform network, filesystem, or Discord actions.
"""

import re
import threading
import time

from display import log, Fore


# ─── Vorkompilierte Regex ────────────────────────────────────────────────────
# Erkennt alle einzeiligen Tool-Tags: [SPOTIFY:...], [FILE:...], [IMG:...], ...
_STREAM_SINGLE_TAG_RE = re.compile(
    r'\[(SPOTIFY|FILE|STICKER|WEB|DOCS|HOME|IMG|ALTPERSONA|WEBSITE|REDESIGN|LAB_REDESIGN):([^\]]+)\]'
)

# Erkennt DM-Blöcke: [DM:Target]message[/DM]
_STREAM_DM_TAG_RE = re.compile(r'\[DM:(\w+)\](.*?)\[/DM\]', re.DOTALL)


# ─── Core ────────────────────────────────────────────────────────────────────

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
        log("STREAM", f"Early dispatch [{tag_type}:{tag_cmd[:60]}]", Fore.MAGENTA)
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
        log("STREAM", f"Early DM dispatch to {target}", Fore.MAGENTA)
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
    request_started_at=None,
    telemetry=None,
) -> str:
    """
    Consumes the OpenRouter stream, accumulates tokens and dispatches tool-tags
    as soon as they appear in the buffer (fire-and-forget via daemon threads).
    Returns the full accumulated response text.
    """
    buffer = ""
    dispatched: set = set()
    chunk_count = 0
    first_chunk_seen = False
    for chunk in stream:
        if not first_chunk_seen:
            first_chunk_seen = True
            if isinstance(telemetry, dict) and request_started_at:
                telemetry["ttft_ms"] = int((time.time() - request_started_at) * 1000)
        chunk_count += 1
        buffer += chunk
        _dispatch_single_tags_stream(
            buffer, dispatched, on_spotify, on_file, on_sticker,
            on_web, on_docs, on_home, on_image,
        )
        _dispatch_dm_tags_stream(buffer, dispatched, on_dm)
    if isinstance(telemetry, dict):
        telemetry["stream_chunks"] = chunk_count
        telemetry["stream_chars"] = len(buffer)
    log("STREAM", f"Stream complete ({len(buffer)} chars, {len(dispatched)} tags dispatched)", Fore.GREEN)
    return buffer
