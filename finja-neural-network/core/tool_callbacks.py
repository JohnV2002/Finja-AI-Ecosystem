"""
YourAI Tool Callback Builders
============================
Factory functions for fire-and-forget handlers used by streaming tool tags.

Main Responsibilities:
- Build callbacks for Spotify, File Brain, Web, Paperless, Home Assistant, image generation, stickers, and DMs.
- Inject runtime dependencies such as dashboard telemetry, Discord clients, and session state.
- Store tool feedback for the next prompt turn.

Side Effects:
- Executes tool commands that may call external APIs, write session state, send Discord messages, or generate images.
"""

import re as _re
from typing import Any, Dict

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError
from session import session_manager
from config import DISCORD_VIP_CHANNEL_ID, USE_DISCORD, IMAGE_MODEL


# ─── Shared Helper ────────────────────────────────────────────────────────────

def _store_feedback(session_id: str, key: str, value: str) -> None:
    """Stores a tool result in the session for the next prompt injection."""
    if value:
        session_manager.set_state(session_id, key, value)


# ─── Spotify ──────────────────────────────────────────────────────────────────

def _build_spotify_callback(session_id: str):
    """Returns a callable that executes a single Spotify command (fire-and-forget)."""

    def _exec_spotify(spotify_cmd: str) -> None:
        """
        Executes the _exec_spotify helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            from tools.spotify_control import SpotifyControl
            _ctrl = SpotifyControl()
            cmd_lower = spotify_cmd.lower()
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
                _store_feedback(session_id, "spotify_feedback", result_msg)

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="spotify_cmd", cause=exc)
            log_exception("STREAM:SPOTIFY", err)
            _store_feedback(session_id, "spotify_feedback", f"❌ {spotify_cmd} failed: {exc}")

    return _exec_spotify


# ─── File Brain ───────────────────────────────────────────────────────────────

def _build_file_callback(session_id: str, debug: Any, user_id: str = "admin"):
    """Returns a callable that executes a single FILE command (fire-and-forget)."""

    def _exec_file(file_cmd: str) -> None:
        """
        Executes the _exec_file helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            from tools.file_brain import get_file_brain
            fb = get_file_brain()
            cmd_lower = file_cmd.lower()
            result = None

            if cmd_lower.startswith("search "):
                result = fb.search(file_cmd[7:].strip(), owner_user_id=user_id)
            elif cmd_lower.startswith("read "):
                result = fb.read(file_cmd[5:].strip(), owner_user_id=user_id)
                if result and result.get("content"):
                    _store_feedback(session_id, "file_feedback", (
                        result.get("message", "Read done") +
                        f"\nCONTENT:\n{result['content'][:8000]}"
                    ))
                    log("STREAM:FILE", "📁 File read dispatched early", Fore.CYAN)
                    return
            elif cmd_lower.startswith("list"):
                arg = file_cmd[4:].strip()
                result = fb.list_doc(arg, owner_user_id=user_id) if arg else fb.list_all(owner_user_id=user_id)
            elif cmd_lower.startswith("ingest "):
                filepath = file_cmd[7:].strip().strip('"').strip("'")
                result = fb.ingest(filepath, owner_user_id=user_id)

            if result:
                msg = result.get("message", result.get("error", "Done"))
                log("STREAM:FILE", f"📁 {msg}", Fore.CYAN)
                _store_feedback(session_id, "file_feedback", msg)

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="file_cmd", cause=exc)
            log_exception("STREAM:FILE", err)

    return _exec_file


# ─── Web Search ───────────────────────────────────────────────────────────────

def _build_web_callback(session_id: str, debug: Any):
    """Returns a callable that executes a web search (fire-and-forget)."""

    def _exec_web(query: str) -> None:
        """
        Executes the _exec_web helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            from tools.web_search import web_search, format_results_for_prompt
            result = web_search(query)
            if result.get("success") and result.get("results"):
                web_feedback = format_results_for_prompt(result)
                _store_feedback(session_id, "web_feedback", web_feedback)
                log("STREAM:WEB", f"🌐 Web search done: {len(result['results'])} results for '{query}'", Fore.CYAN)
                debug.info("web_search", f"🌐 Web search: {len(result['results'])} results for '{query}'", web_feedback[:500])
            else:
                web_feedback = result.get("message", f"No results for '{query}'")
                _store_feedback(session_id, "web_feedback", web_feedback)
                log("STREAM:WEB", f"🌐 Web search: {web_feedback}", Fore.YELLOW)
                debug.info("web_search", f"🌐 Web search: no results for '{query}'")
        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="web_search", cause=exc)
            log_exception("STREAM:WEB", err)
            debug.error("web_search", err.short(), exception=err)

    return _exec_web


# ─── Paperless ────────────────────────────────────────────────────────────────

def _build_docs_callback(session_id: str, debug: Any):
    """Returns a callable that executes a Paperless command (fire-and-forget)."""

    def _exec_docs(cmd: str) -> None:
        """
        Executes the _exec_docs helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            from tools.paperless import (
                paperless_search, paperless_doc_content,
                paperless_list_tags, paperless_list_correspondents, paperless_list_doctypes,
                format_search_for_prompt, format_doc_for_prompt,
            )
            docs_feedback = ""
            cmd_lower = cmd.lower().strip()

            if cmd_lower.startswith("search "):
                query = cmd[7:].strip()
                result = paperless_search(query)
                if result.get("success") and result.get("results"):
                    docs_feedback = format_search_for_prompt(result)
                else:
                    docs_feedback = result.get("message", f"No documents for '{query}'")

            elif cmd_lower.startswith("read "):
                try:
                    doc_id = int(cmd[5:].strip())
                    result = paperless_doc_content(doc_id)
                    if result.get("success"):
                        docs_feedback = format_doc_for_prompt(result)
                    else:
                        docs_feedback = result.get("message", f"Could not read #{doc_id}")
                except ValueError:
                    docs_feedback = f"Invalid document ID: {cmd[5:].strip()}"

            elif cmd_lower == "tags":
                result = paperless_list_tags()
                docs_feedback = result.get("message", "No tags")

            elif cmd_lower == "correspondents":
                result = paperless_list_correspondents()
                docs_feedback = result.get("message", "No correspondents")

            elif cmd_lower == "types":
                result = paperless_list_doctypes()
                docs_feedback = result.get("message", "No types")

            else:
                docs_feedback = f"Unknown DOCS command: {cmd}"

            _store_feedback(session_id, "docs_feedback", docs_feedback)
            log("STREAM:DOCS", f"📄 Paperless done: {cmd}", Fore.CYAN)
            debug.info("paperless", f"📄 Paperless: {cmd}", docs_feedback[:500] if docs_feedback else None)

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="paperless", cause=exc)
            log_exception("STREAM:DOCS", err)
            debug.error("paperless", err.short(), exception=err)

    return _exec_docs


# ─── Home Assistant ───────────────────────────────────────────────────────────

def _build_home_callback(session_id: str, debug: Any):
    """Returns a callable that executes a Home Assistant command (fire-and-forget)."""

    def _exec_home(cmd: str) -> None:
        """
        Executes the _exec_home helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            from tools.home_assistant import execute_home_command, format_result_for_prompt
            result = execute_home_command(cmd)
            home_feedback = format_result_for_prompt(result)
            _store_feedback(session_id, "home_feedback", home_feedback)
            log("STREAM:HOME", f"🏠 HA done: {cmd}", Fore.CYAN)
            debug.info("home_assistant", f"🏠 HA: {cmd}", home_feedback[:500] if home_feedback else None)

        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="home_assistant", cause=exc)
            log_exception("STREAM:HOME", err)
            debug.error("home_assistant", err.short(), exception=err)

    return _exec_home


# ─── Image Generation ─────────────────────────────────────────────────────────

def _build_image_callback(state: Dict[str, Any], debug: Any, discord_client: Any):
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
        """
        Executes the _exec_image helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
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
                url        = result["url"]
                elapsed_s  = result.get("elapsed_s", 0)
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


# ─── Discord Sticker ──────────────────────────────────────────────────────────

def _build_sticker_callback(state: Dict[str, Any], discord_client: Any, discord_dm_whitelist: Dict[str, str]):
    """Returns a callable to send a Discord sticker (fire-and-forget)."""
    source = state.get("source", "console")

    def _exec_sticker(sticker_name: str) -> None:
        """
        Executes the _exec_sticker helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            if not (USE_DISCORD and discord_client and discord_client.bot.connected):
                return
            sticker_name = sticker_name.strip()
            if source == "discord_dm":
                session_key = (session_manager.source_users.get("discord") or "").lower()
                for did, ukey in discord_dm_whitelist.items():
                    if ukey.lower() == session_key:
                        discord_client.bot.send_sticker_dm(int(did), sticker_name)
                        break
            elif source == "discord":
                discord_client.bot.send_sticker(DISCORD_VIP_CHANNEL_ID, sticker_name)
        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="sticker", cause=exc)
            log_exception("STREAM:STICKER", err)

    return _exec_sticker


# ─── Discord DM ───────────────────────────────────────────────────────────────

def _build_dm_callback(discord_client: Any, discord_dm_whitelist: Dict[str, str]):
    """Returns a callable to send a Discord DM (fire-and-forget)."""

    def _exec_dm(target: str, message: str) -> None:
        """
        Executes the _exec_dm helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        try:
            if not (USE_DISCORD and discord_client and discord_client.bot.connected):
                return
            for did, ukey in discord_dm_whitelist.items():
                if ukey.lower() == target.lower():
                    discord_client.bot.send_dm(int(did), message)
                    log("STREAM:DM", f"📩 DM sent to {target}: {message[:60]}", Fore.GREEN)
                    return
            log("STREAM:DM", f"⚠️ DM target '{target}' not in whitelist", Fore.YELLOW)
        except Exception as exc:
            err = YourAIToolExecutionError(tool_name="dm", cause=exc)
            log_exception("STREAM:DM", err)

    return _exec_dm
