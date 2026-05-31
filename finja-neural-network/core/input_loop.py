"""
YourAI Input Loop
================
Main dispatcher for console, web dashboard, Twitch, and Discord input sources.

Main Responsibilities:
- Poll input sources and normalize messages for the central brain pipeline.
- Manage worker concurrency, active users, and platform-specific metadata.
- Handle slash commands and Discord data deletion actions.

Side Effects:
- Starts background input threads and pipeline worker tasks.
- Reads from and writes to queues, Discord channel maps, diary storage, and memory services.
- Sends responses through dashboard, Discord, Twitch, and console integrations.
"""

import time
import threading
import queue
import traceback
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore, Style
from exceptions import YourAIPipelineError, YourAISystemError, YourAIToolExecutionError

from config import (
    USE_VOICE, USE_TWITCH, USE_DISCORD, USE_EPISODIC, USE_GRANITE, USE_OPENROUTER,
    USE_SUBCONSCIOUS,
    DISCORD_CHANNELS_FILE,
    MODEL_YOURAI_OPENROUTER, MODEL_YOURAI_LOCAL_PRIMARY, MODEL_YOURAI_LOCAL_FALLBACK,
    MODEL_ROUTER, LLM_HOST_STD
)

# These are required for session and memory sync.
import hippocampus
import episodic
import personas

from session import session_manager
from helpers.platform_links import resolve_discord_id, unlink_discord_id


# ==========================================
# BOOT BANNER
# ==========================================

def _print_boot_banner(dashboard_enabled: bool) -> None:
    """Zeigt den Boot-Banner mit System-Info."""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}✨ YourAI Brain v5.0 (Modular Edition) ONLINE{Style.RESET_ALL}")
    
    if USE_OPENROUTER:
        print(f"{Fore.CYAN}{Style.BRIGHT}   ☁️ Primary: {MODEL_YOURAI_OPENROUTER} (OpenRouter){Style.RESET_ALL}")
        print(f"{Fore.WHITE}   🖥️ Fallback 1: {MODEL_YOURAI_LOCAL_PRIMARY} (lokal) | Fallback 2: {MODEL_YOURAI_LOCAL_FALLBACK} (lokal){Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}   ⚠️ OpenRouter DEAKTIVIERT (kein API Key) - nur lokale Models{Style.RESET_ALL}")
        print(f"{Fore.WHITE}   Main Brain: {MODEL_YOURAI_LOCAL_PRIMARY} | Fallback: {MODEL_YOURAI_LOCAL_FALLBACK}{Style.RESET_ALL}")
    
    print(f"{Fore.WHITE}   Router: {MODEL_ROUTER}{Style.RESET_ALL}")
    
    if hasattr(personas, 'persona_manager'):
        mood_info = personas.persona_manager.get_mood_info()
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M")
        print(f"{Fore.YELLOW}   🎭 Mood: {mood_info['emoji']} {mood_info['name']} | ⏰ Time: {current_time}{Style.RESET_ALL}")
    
    if dashboard_enabled:
        print(f"{Fore.CYAN}   📊 Dashboard: http://localhost:8050{Style.RESET_ALL}")

    if USE_DISCORD:
        print(f"{Fore.BLUE}   🔵 Discord: AKTIV (VIP Channel + DMs){Style.RESET_ALL}")

    if not USE_GRANITE:
        print(f"{Fore.RED}   ⚠️ Granite Safety Filter: OFF (Du kannst YourAI jetzt ausschimpfen!){Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}   🛡️ Granite Safety Filter: ON{Style.RESET_ALL}")

    if USE_SUBCONSCIOUS:
        print(f"{Fore.MAGENTA}   💭 YourAI Active: subconscious random tick{Style.RESET_ALL}")

    print(f"{Fore.RED}   😈 AltPersona Mode: /altpersona | 🌸 YourAI Mode: /yourai{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}   🎲 Force website review: /website_update{Style.RESET_ALL}")


# ==========================================
# SLASH COMMANDS
# ==========================================

def _handle_slash_command(text: str) -> bool:
    """
    Handles slash commands.
    
    Returns:
        True wenn ein Command erkannt und verarbeitet wurde.
    """
    cmd = text.lower().strip()
    
    if cmd == "/diary_rotate":
        print(f"\n{Fore.YELLOW}🔄 Starting diary reorganization...{Style.RESET_ALL}")
        if USE_EPISODIC and hasattr(episodic, 'journal'):
            result = episodic.journal.force_reorganize()
            print(f"{Fore.GREEN}{result}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ Episodic diary not enabled{Style.RESET_ALL}")
        return True
    
    if cmd == "/diary_status":
        if USE_EPISODIC and hasattr(episodic, 'journal'):
            episodic.journal.print_status()
        else:
            print(f"{Fore.RED}❌ Episodic diary not enabled{Style.RESET_ALL}")
        return True
    
    if cmd == "/website_update":
        print(f"\n{Fore.MAGENTA}🎲 Forcing autonomous website review...{Style.RESET_ALL}")
        try:
            from tools.website_autonomy import maybe_trigger_website_update
            # debug wird von brain importiert
            from brain import debug
            maybe_trigger_website_update(debug, force=True)
            print(f"{Fore.GREEN}✅ Website review started in background!{Style.RESET_ALL}")
        except ImportError:
            print(f"{Fore.RED}❌ website_autonomy.py not found{Style.RESET_ALL}")
        except Exception as e:
            err = YourAISystemError("Website update failed", cause=e, module="slash_website")
            log_exception("WEBSITE", err)
        return True

    # /dm <name> - Erste DM an einen Whitelisted User senden
    if cmd.startswith("/dm "):
        target_name = text[4:].strip()  # Original case behalten
        if not target_name:
            print(f"{Fore.YELLOW}Usage: /dm <name> (z.B. /dm Mom, /dm Bendy, /dm admin){Style.RESET_ALL}")
            return True

        if not USE_DISCORD:
            print(f"{Fore.RED}❌ Discord ist nicht aktiviert{Style.RESET_ALL}")
            return True

        # Target in platform_links finden (user_key → erste discord_id mit dm_allowed)
        from helpers.platform_links import _load as _pl_load, all_dm_allowed_ids
        pl_data = _pl_load()
        target_discord_id = None
        matched_name = None
        for ukey, info in pl_data.items():
            if ukey.lower() == target_name.lower() and info.get("dm_allowed") and info.get("discord_ids"):
                target_discord_id = int(info["discord_ids"][0])
                matched_name = ukey
                break

        if not target_discord_id:
            dm_users = [k for k, v in pl_data.items() if v.get("dm_allowed") and v.get("discord_ids")]
            names = ", ".join(dm_users) if dm_users else "(keine)"
            print(f"{Fore.RED}❌ '{target_name}' nicht in platform_links oder dm_allowed=false. Verfügbar: {names}{Style.RESET_ALL}")
            return True

        # Importiere discord_client aus dem laufenden System
        try:
            from brain import discord_client
            if not discord_client or not discord_client.bot.connected:
                print(f"{Fore.RED}❌ Discord Bot nicht verbunden{Style.RESET_ALL}")
                return True

            discord_client.bot.send_dm(target_discord_id, f"Hey! 🦊💜 YourAI here! Creator gave me Discord access and I can now chat with you! 😸✨")
            print(f"{Fore.GREEN}✅ Erste DM an {matched_name} gesendet! DM-Kanal ist jetzt offen.{Style.RESET_ALL}")
            print(f"{Fore.CYAN}   ℹ️ YourAI kann ab jetzt [DM:{matched_name}] nutzen und {matched_name} kann YourAI per DM schreiben.{Style.RESET_ALL}")
        except Exception as e:
            err = YourAIToolExecutionError("discord_dm", cause=e)
            log_exception("DISCORD", err)
        return True

    return False


def _sync_hippocampus(user_id: str) -> None:
    """Synct Hippocampus zum aktuellen User wenn nötig."""
    if hippocampus.memory.user_id != user_id:
        hippocampus.memory.user_id = user_id
        print(f"{Fore.CYAN}🧠 Hippocampus synced to: {user_id}{Style.RESET_ALL}")


# ==========================================
# MAIN LOOP
# ==========================================

def run_main_loop(process_input_fn, debug, dashboard_enabled: bool,
                  mouth=None, twitch_client=None, discord_client=None) -> None:
    """
    Main Event Loop - Console, Web, Twitch, Discord.

    Args:
        process_input_fn: Die process_input Funktion aus brain.py
        debug: Dashboard debug client
        dashboard_enabled: Ob das Dashboard aktiv ist
        mouth: TTS Modul (oder None)
        twitch_client: Twitch Client (oder None)
        discord_client: Discord Client (oder None)
    """
    _print_boot_banner(dashboard_enabled)
    debug.info("system", "🚀 YourAI Brain v5.0 booting...", "Startup sequence initiated")

    # Session Reset
    session_manager.source_users["console"] = "admin"
    session_manager.source_users["web"] = "admin"
    session_manager.source_users["discord"] = None
    # Reset all user modes to yourai on startup
    session_manager.user_modes = {}
    session_manager._default_mode = "yourai"
    session_manager._save()
    session_manager._sync_hippocampus("admin")
    debug.info("session", "🔄 Sessions reset", "User=Admin, Mode=YourAI")
    print(f"{Fore.CYAN}   🔄 Sessions reset: User=Admin, Mode=YourAI{Style.RESET_ALL}")
    print()
    
    # Model Warmup: qwen3.5:2b vorladen damit Memory nicht timeout
    def _warmup_models():
        """Lädt häufig genutzte Models in Ollama vor (Background)."""
        import requests
        models_to_warm = [MODEL_ROUTER]
        debug.node_start("warmup", input_data=f"Models: {', '.join(models_to_warm)}")
        for model in models_to_warm:
            try:
                # Leerer Request → Ollama lädt das Model in RAM
                requests.post(
                    f"{LLM_HOST_STD.rstrip('/')}/api/chat",
                    json={"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False, "keep_alive": "10m"},
                    timeout=180
                )
                debug.info("warmup", f"🔥 {model} geladen")
                print(f"{Fore.GREEN}   🔥 Warmup: {model} geladen{Style.RESET_ALL}")
            except Exception as e:
                debug.error("warmup", f"Warmup {model} failed: {e}")
                print(f"{Fore.YELLOW}   ⚠️ Warmup {model} failed: {e}{Style.RESET_ALL}")
        debug.node_end("warmup")

    warmup_thread = threading.Thread(target=_warmup_models, daemon=True, name="model-warmup")
    warmup_thread.start()

    # Module starten (sicher, auch wenn Dashboard offline ist)
    if USE_VOICE and mouth:
        try:
            mouth.speak("System initialized.")
            debug.info("tts", "🔊 TTS initialized")
        except Exception as e:
            debug.error("tts", f"TTS startup failed: {e}", exception=e)
            print(f"{Fore.YELLOW}⚠️ TTS startup failed (non-critical): {type(e).__name__}: {e}{Style.RESET_ALL}")
    if USE_TWITCH and twitch_client:
        try:
            twitch_client.bot.start()
            debug.info("twitch", "🟣 Twitch Bot connected")
        except Exception as e:
            debug.error("twitch", f"Twitch start failed: {e}", exception=e)
            print(f"{Fore.RED}❌ Twitch start failed: {type(e).__name__}: {e}{Style.RESET_ALL}")
    if USE_DISCORD and discord_client:
        try:
            discord_client.bot.start()
            debug.info("discord", "🔵 Discord Bot connected")
        except Exception as e:
            debug.error("discord", f"Discord start failed: {e}", exception=e)
            print(f"{Fore.RED}❌ Discord start failed: {type(e).__name__}: {e}{Style.RESET_ALL}")

    # ── Subconscious: YourAI subconscious (Random Tick Loop) ──
    _subconscious_ref = None
    if USE_SUBCONSCIOUS:
        try:
            from yourai_subconscious import subconscious as _subconscious_ref
            _subconscious_ref.start()
            debug.info("subconscious", "💭 YourAI Aktiv (subconscious) started")
            print(f"{Fore.MAGENTA}   💭 Subconscious: Random Tick Loop AKTIV{Style.RESET_ALL}")
        except Exception as e:
            debug.error("subconscious", f"Subconscious start failed: {e}", exception=e)
            print(f"{Fore.YELLOW}   ⚠️ Subconscious start failed (non-critical): {type(e).__name__}: {e}{Style.RESET_ALL}")

    debug.info("system", "✅ YourAI Brain ready!", f"Voice={'ON' if USE_VOICE else 'OFF'}, Discord={'ON' if USE_DISCORD else 'OFF'}, Twitch={'ON' if USE_TWITCH else 'OFF'}, Subconscious={'ON' if USE_SUBCONSCIOUS else 'OFF'}")
    
    input_queue: queue.Queue = queue.Queue()

    # ==========================================
    # PIPELINE WORKER
    # ==========================================

    # Safety first: brain/persona/hippocampus still contain process-global state.
    # Until those are fully per-session or moved into real subprocess workers,
    # run one brain request at a time to prevent cross-user bleeding.
    MAX_WORKERS = 1
    _pipeline_lock = threading.Lock()  # Protects shared state (session, persona)
    _active_workers = threading.Semaphore(MAX_WORKERS)
    _active_users: List[str] = []  # Trackt wer gerade verarbeitet wird
    _active_users_lock = threading.Lock()

    def _is_multi_user() -> bool:
        """Sind gerade mehrere User in der Pipeline?"""
        with _active_users_lock:
            unique = set(_active_users)
            return len(unique) > 1

    def _run_pipeline_task(text: str, user: str, source: str,
                           display_name: str = "",
                           discord_id: str = "", image_urls: Optional[list] = None,
                           text_attachments: Optional[list] = None,
                           channel_id: int = 0, session_uuid: str = "",
                           account_user_key: str = "", account_user_id: str = ""):
        """
        Pipeline-Task der in einem Worker-Thread läuft.
        Handelt Session-Setup + Pipeline-Call + Cleanup + Context Flush.
        """
        source_label = {
            "console": "Console",
            "web": "Web",
            "twitch": "Twitch",
            "discord": "Discord",
            "discord_dm": "Discord DM",
            "discord_private": "Discord Private",
        }.get(source, source)

        # Track active user
        with _active_users_lock:
            _active_users.append(display_name or user)

        try:
            resolved_user_id = account_user_id or ""
            resolved_user_key = account_user_key or ""

            # Session setup braucht Lock (shared state)
            with _pipeline_lock:
                if source in ("discord", "discord_dm", "discord_private"):
                    user_key = resolve_discord_id(discord_id)
                    if user_key:
                        # Verknüpfter User → richtigen User-Key nutzen
                        if session_manager.source_users.get("discord") != user_key:
                            session_manager.switch_user(user_key, "discord")
                    else:
                        # Anonymer User → stabiler Key basierend auf channel_id (nicht display_name!)
                        auto_key = f"discord_{channel_id}" if channel_id else f"discord_{discord_id}"
                        if session_manager.source_users.get("discord") != auto_key:
                            session_manager.switch_user(auto_key, "discord")

                    user = session_manager.get_current_user("discord")
                    resolved_user_key = session_manager.source_users.get("discord") or resolved_user_key
                    resolved_user_id = session_manager.get_current_user_id("discord")
                    _sync_hippocampus(resolved_user_id)

                elif source == "web":
                    if resolved_user_key:
                        if session_manager.source_users.get("web") != resolved_user_key:
                            session_manager.switch_user(resolved_user_key, "web")
                        profile = session_manager.users.get(resolved_user_key)
                        if profile:
                            resolved_user_id = profile.user_id
                            user = profile.display_name
                            display_name = display_name or profile.display_name
                    if not resolved_user_id:
                        resolved_user_id = session_manager.get_current_user_id("web")
                    _sync_hippocampus(resolved_user_id)

                elif source == "console":
                    resolved_user_key = session_manager.source_users.get("console") or resolved_user_key
                    resolved_user_id = session_manager.get_current_user_id("console")
                    _sync_hippocampus(resolved_user_id)

                current_mode = session_manager.get_mode(source)

            # Session ID ermitteln (UUID > User > Channel > System)
            if session_uuid:
                session_id = session_uuid
            elif source in ("discord_dm", "discord_private"):
                session_id = f"dm_{discord_id}"
            elif source == "discord" and channel_id:
                session_id = f"chan_{channel_id}"
            else:
                session_id = resolved_user_id or session_manager.get_current_user_id(source) or "system"
            session_user_source = "discord" if source in ("discord", "discord_dm", "discord_private") else source
            token_session_id = resolved_user_id or session_manager.get_current_user_id(session_user_source) or "system"
            if source in ("discord", "discord_dm", "discord_private") and not resolve_discord_id(discord_id):
                token_session_id = session_id
            session_manager.merge_tokens(session_id, token_session_id)
            session_manager.touch_token_session(token_session_id)

            # ─── PHASE 2: 80K SOFT FLUSH ──────────────────────────────
            current_tokens = session_manager.get_tokens(token_session_id)
            if current_tokens > 80000:
                log("TOKEN", f"🚨 Session {session_id[:8]} überschreitet 80k Tokens ({current_tokens}). Führe Context Flush aus!", Fore.RED)
                try:
                    debug.queue_status(
                        "YourAI räumt gerade auf...",
                        f"Wir komprimieren das Kontextfenster ({current_tokens} / 80000 Tokens). Deine Nachricht ist gespeichert.",
                        source=source,
                        for_user=token_session_id,
                        status="info",
                        phase="flush",
                    )
                except Exception:
                    pass
                session_manager.clear_history(session_id)
                session_manager.clear_tokens(token_session_id)

            history = session_manager.get_history(session_id)

            # Pipeline Call - serialized by MAX_WORKERS=1 for global brain state safety.
            log("PIPELINE", f"▶️ Processing: {display_name or user} ({source_label}) [mode={current_mode}]", Fore.CYAN)
            process_input_fn(
                text, user, source, history,
                image_urls=image_urls,
                text_attachments=text_attachments,
                discord_id=discord_id,
                channel_id=channel_id,
                session_uuid=session_uuid,
                token_session_id=token_session_id,
                account_user_id=resolved_user_id or token_session_id,
            )
            log("PIPELINE", f"✅ Done: {display_name or user} ({source_label})", Fore.GREEN)

        except Exception as e:
            err = YourAIPipelineError(f"Worker crashed handling {source_label}", cause=e)
            log_exception("PIPELINE", err)
        finally:
            # Cleanup: remove user from the active list.
            with _active_users_lock:
                if (display_name or user) in _active_users:
                    _active_users.remove(display_name or user)
            _active_workers.release()

    def _handle_discord_data_deletion(channel_id: int, discord_id: str) -> None:
        """
        Deletes all YourAI data for a Discord user under GDPR/DSGVO Art. 17.

        Args:
            channel_id (int): Discord channel ID used for private-channel diary records.
            discord_id (str): Discord user ID used for DM diary records and platform links.

        Returns:
            None.
        """
        import json
        import requests
        from helpers.platform_links import unlink_discord_id, resolve_discord_id
        from config import MEMORY_API_BASE, MEMORY_API_KEY

        deleted = 0
        # Delete diary entries by session UUID: str(channel_id) for private channels, dm_{id} for DMs.
        if channel_id:
            deleted += episodic.journal.delete_by_uuid(str(channel_id))
        if discord_id:
            deleted += episodic.journal.delete_by_uuid(f"dm_{discord_id}")

        # Remove the private channel mapping from discord_channels.json.
        if discord_id and os.path.exists(DISCORD_CHANNELS_FILE):
            try:
                with open(DISCORD_CHANNELS_FILE, "r", encoding="utf-8") as f:
                    channels = json.load(f)
                if discord_id in channels:
                    del channels[discord_id]
                    with open(DISCORD_CHANNELS_FILE, "w", encoding="utf-8") as f:
                        json.dump(channels, f, indent=2, ensure_ascii=False)
            except Exception as e:
                log("DISCORD", f"discord_channels.json cleanup failed: {e}", Fore.YELLOW)

        # Memory Server: Fakten löschen (discord_id → user_key → user_id)
        user_key = resolve_discord_id(discord_id) if discord_id else None
        user_id = None
        if user_key:
            profile = session_manager.users.get(user_key)
            user_id = profile.user_id if profile else user_key
        if user_id and MEMORY_API_BASE and MEMORY_API_KEY:
            try:
                resp = requests.post(
                    f"{MEMORY_API_BASE}/delete_user_memories",
                    headers={"X-API-Key": MEMORY_API_KEY, "Content-Type": "application/json"},
                    json={"user_id": user_id},
                    timeout=10,
                )
                if resp.status_code == 200:
                    log("DISCORD", f"Memory server facts deleted for '{user_id}'", Fore.GREEN)
                else:
                    log("DISCORD", f"⚠️ Memory Server Löschung HTTP {resp.status_code}: {resp.text[:200]}", Fore.YELLOW)
            except Exception as e:
                log("DISCORD", f"Memory server deletion failed: {e}", Fore.YELLOW)

        # Aus platform_links entfernen (falls verknüpft)
        unlinked = unlink_discord_id(discord_id) if discord_id else None

        log("DISCORD", f"GDPR/DSGVO Art.17: {deleted} diary entries deleted | memories={'yes' if user_id else 'no'} | channel={channel_id} | user={unlinked or 'anon'}", Fore.YELLOW)

        # Bestätigung im Discord-Channel
        if discord_client and channel_id:
            discord_client.bot.send_channel(channel_id, "All of your data has been deleted.")

    def _submit_to_pipeline(text: str, user: str, source: str,
                            display_name: str = "",
                            discord_id: str = "",
                            image_urls: Optional[list] = None,
                            text_attachments: Optional[list] = None,
                            channel_id: int = 0,
                            session_uuid: str = "",
                            account_user_key: str = "",
                            account_user_id: str = "") -> bool:
        """
        Submits a pipeline task. Blocks when YourAI is busy so Discord does
        not tight-loop requeue while global brain state is protected.

        Args:
            text (str): User message text.
            user (str): User label passed into the pipeline.
            source (str): Source platform identifier.
            display_name (str): Optional display name for logs and telemetry.
            discord_id (str): Optional Discord user ID.
            image_urls (Optional[list]): Optional image URLs attached to the message.
            text_attachments (Optional[list]): Optional text attachments.
            channel_id (int): Optional Discord channel ID.
            session_uuid (str): Optional session UUID for diary isolation.
            account_user_key (str): Optional linked account key.
            account_user_id (str): Optional linked account user ID.

        Returns:
            bool: True if the task was submitted, False if the queue slot could not be acquired.
        """
        got_slot = _active_workers.acquire(blocking=True)
        if not got_slot:
            log("PIPELINE", f"Queue full. {display_name or user} must wait.", Fore.YELLOW)
            return False

        _pipeline_executor.submit(
            _run_pipeline_task, text, user, source,
            display_name, discord_id, image_urls, text_attachments, channel_id,
            session_uuid, account_user_key, account_user_id
        )
        return True

    _pipeline_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="yourai-pipeline")

    # ==========================================
    # INPUT WORKER THREAD
    # ==========================================

    def input_worker():
        """
        Reads console input in a background thread and places messages on the input queue.

        Returns:
            None.
        """
        while True:
            try:
                current = session_manager.get_current_user("console")
                short_name = current.split(" ")[0] if " " in current else current
                text = input(f"{Fore.GREEN}{short_name}: {Style.RESET_ALL}")
                text = text.strip()
                if text:
                    input_queue.put(text)
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                err = YourAISystemError(cause=e, module="input_worker")
                log_exception("INPUT", err)

    t = threading.Thread(target=input_worker, daemon=True, name="input-worker")
    t.start()

    # ==========================================
    # EVENT LOOP (non-blocking dispatcher)
    # ==========================================

    while True:
        try:
            processed = False

            # ===== CONSOLE =====
            try:
                text = input_queue.get_nowait()
                text = text.strip()
                if text:
                    # Slash commands are handled first and synchronously.
                    if text.startswith("/") and _handle_slash_command(text):
                        processed = True
                        continue

                    # Session commands.
                    cmd_response = session_manager.parse_command(text, "console")
                    if cmd_response:
                        print(f"\n{Fore.CYAN}{cmd_response}{Style.RESET_ALL}")
                        current_user_id = session_manager.get_current_user_id("console")
                        _sync_hippocampus(current_user_id)
                    else:
                        current_user = session_manager.get_current_user("console")
                        print(f"\n{Fore.GREEN}User ({current_user}): {text}{Style.RESET_ALL}")
                        _submit_to_pipeline(text, current_user, "console", display_name=current_user)

                    processed = True
            except queue.Empty:
                pass

            # ===== WEB =====
            if not processed and dashboard_enabled:
                text = debug.get_web_input()
                web_image_urls = debug.get_last_web_image_urls()
                web_text_attachments = getattr(debug, "get_last_web_text_attachments", lambda: [])()
                # text is None when no input, "" when image-only
                if text is not None and (text.strip() or web_image_urls or web_text_attachments):
                    web_user_key = debug.get_last_web_user_key()
                    web_session_uuid = debug.get_last_web_session_uuid()
                    if web_user_key:
                        if session_manager.source_users.get("web") != web_user_key:
                            session_manager.switch_user(web_user_key, "web")

                    current_user = session_manager.get_current_user("web")
                    web_account_user_id = session_manager.get_current_user_id("web")
                    display_msg = text.strip() or f"[{len(web_image_urls)} image(s)]"
                    print(f"\n{Fore.CYAN}User ({current_user}): {display_msg}{Style.RESET_ALL}")
                    if web_image_urls:
                        print(f"{Fore.CYAN}   {len(web_image_urls)} image(s) attached{Style.RESET_ALL}")
                    if web_text_attachments:
                        print(f"{Fore.CYAN}   Text file(s): {len(web_text_attachments)} attached{Style.RESET_ALL}")
                    _submit_to_pipeline(
                        text, current_user, "web",
                        display_name=current_user,
                        image_urls=web_image_urls,
                        text_attachments=web_text_attachments,
                        session_uuid=web_session_uuid,
                        account_user_key=web_user_key,
                        account_user_id=web_account_user_id,
                    )
                    processed = True

            # ===== TWITCH =====
            if USE_TWITCH and twitch_client:
                msg = twitch_client.bot.get_next_message()
                if msg:
                    text = msg["text"].strip()
                    print(f"\n{Fore.MAGENTA}User (Twitch {msg['user']}): {text}{Style.RESET_ALL}")
                    _submit_to_pipeline(text, msg["user"], "twitch", display_name=msg["user"])
                    processed = True

            # ===== DISCORD (prüft IMMER, nicht nur wenn nichts anderes da war!) =====
            if USE_DISCORD and discord_client:
                msg = discord_client.bot.get_next_message()
                if msg:
                    # Subconscious: Entropy füttern bei jeder Discord-Nachricht
                    if _subconscious_ref and _subconscious_ref.is_running:
                        _subconscious_ref.feed_entropy(f"{time.time()}-{msg.get('discord_id','')}-{msg.get('text','')[:20]}")

                    # Special actions do not submit to the pipeline.
                    if msg.get("action") == "delete_discord_data":
                        _handle_discord_data_deletion(
                            channel_id=msg.get("channel_id", 0),
                            discord_id=msg.get("discord_id", ""),
                        )
                        processed = True
                        continue

                    text = msg["text"].strip()
                    discord_id = msg.get("discord_id", "")
                    source = msg.get("source", "discord")
                    display_name = msg.get("user", "Unknown")
                    image_urls = msg.get("image_urls", [])
                    text_attachments = msg.get("text_attachments", [])
                    channel_id = msg.get("channel_id", 0)

                    # Session UUID controls diary isolation and GDPR/DSGVO deletion.
                    if source == "discord_private":
                        session_uuid = str(channel_id)
                        source_label = "Discord Private"
                    elif source == "discord_dm":
                        session_uuid = f"dm_{discord_id}"
                        source_label = "Discord DM"
                    else:
                        session_uuid = ""
                        source_label = "Discord"

                    print(f"\n{Fore.BLUE}User ({source_label} {display_name}): {text}{Style.RESET_ALL}")
                    if image_urls:
                        print(f"{Fore.CYAN}   {len(image_urls)} image(s) attached{Style.RESET_ALL}")

                    if text_attachments:
                        print(f"{Fore.CYAN}   Text file(s): {len(text_attachments)} attached{Style.RESET_ALL}")

                    submitted = _submit_to_pipeline(
                        text, display_name, source,
                        display_name=display_name, discord_id=discord_id,
                        image_urls=image_urls, text_attachments=text_attachments,
                        channel_id=channel_id,
                        session_uuid=session_uuid,
                    )
                    if not submitted:
                        discord_client.bot.message_queue.put(msg)
                        log("PIPELINE", f"⏳ Re-queued message from {display_name}", Fore.YELLOW)

                    processed = True

            if not processed:
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("\n👋 Bye bye!")
            _pipeline_executor.shutdown(wait=False)
            break
        except Exception as e:
            err = YourAISystemError(cause=e, module="event_loop")
            log_exception("SYSTEM", err)
            print(f"{Fore.YELLOW}Loop continues...{Style.RESET_ALL}")
            time.sleep(1)
