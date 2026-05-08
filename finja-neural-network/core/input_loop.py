"""
YourAI AI - Input Loop
======================
Main Event Loop: Console, Web Dashboard, Twitch.
Alle Commands und Input-Handling an einem Ort.

Commands:
    /diary_rotate    - Tagebuch reorganisieren
    /diary_status    - Tagebuch-Status anzeigen
    /website_update  - Website-Review erzwingen
    /altpersona            - AltPersona Mode aktivieren (via session_manager)
    /yourai           - YourAI Mode aktivieren (via session_manager)
    /guardlog        - Autonomy Guard Log anzeigen
    /dm <name>       - Erste DM an User senden (öffnet DM-Kanal)

Run: python brain.py (oder direkt: python input_loop.py)
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
    DISCORD_DM_WHITELIST,
    MODEL_YOURAI_OPENROUTER, MODEL_YOURAI_LOCAL_PRIMARY, MODEL_YOURAI_LOCAL_FALLBACK,
    MODEL_ROUTER, LLM_HOST_STD, HIPPOCAMPUS_RELEVANCE_MODEL
)

# Diese werden für Session/Memory-Sync gebraucht
import hippocampus
import episodic
import personas

from session import session_manager


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
    
    print(f"{Fore.RED}   😈 AltPersona Mode: /altpersona | 🌸 YourAI Mode: /yourai{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}   🎲 Force website review: /website_update{Style.RESET_ALL}")


# ==========================================
# SLASH COMMANDS
# ==========================================

def _handle_slash_command(text: str) -> bool:
    """
    Verarbeitet Slash-Commands.
    
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
            err = YourAISystemError(cause=e, module="slash_website")
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

        # Target in Whitelist finden
        target_discord_id = None
        matched_name = None
        for did, ukey in DISCORD_DM_WHITELIST.items():
            if ukey.lower() == target_name.lower():
                target_discord_id = int(did)
                matched_name = ukey
                break

        if not target_discord_id:
            names = ", ".join(DISCORD_DM_WHITELIST.values())
            print(f"{Fore.RED}❌ '{target_name}' nicht in Whitelist. Verfügbar: {names}{Style.RESET_ALL}")
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
        models_to_warm = [HIPPOCAMPUS_RELEVANCE_MODEL, MODEL_ROUTER]
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

    debug.info("system", "✅ YourAI Brain ready!", f"Voice={'ON' if USE_VOICE else 'OFF'}, Discord={'ON' if USE_DISCORD else 'OFF'}, Twitch={'ON' if USE_TWITCH else 'OFF'}")
    
    chat_history: dict = {"yourai": [], "altpersona": []}
    input_queue: queue.Queue = queue.Queue()

    # ==========================================
    # PARALLEL PIPELINE (max 10 gleichzeitig)
    # ==========================================

    MAX_WORKERS = 10
    _pipeline_lock = threading.Lock()  # Schützt shared state (session, persona)
    _active_workers = threading.Semaphore(MAX_WORKERS)
    _active_users: List[str] = []  # Trackt wer gerade verarbeitet wird
    _active_users_lock = threading.Lock()

    def _is_multi_user() -> bool:
        """Sind gerade mehrere User in der Pipeline?"""
        with _active_users_lock:
            unique = set(_active_users)
            return len(unique) > 1

    def _run_pipeline_task(text: str, user: str, source: str,
                           history_dict: dict, display_name: str = "",
                           discord_id: str = "", image_urls: Optional[list] = None,
                           channel_id: int = 0, session_uuid: str = ""):
        """
        Pipeline-Task der in einem Worker-Thread läuft.
        Handelt Session-Setup + Pipeline-Call + Cleanup.
        """
        source_label = {
            "console": "Console",
            "web": "Web",
            "twitch": "Twitch",
            "discord": "Discord",
            "discord_dm": "Discord DM",
            "discord_private": "Discord Privat",
        }.get(source, source)

        # Track active user
        with _active_users_lock:
            _active_users.append(display_name or user)

        try:
            # Session setup braucht Lock (shared state)
            with _pipeline_lock:
                if source in ("discord", "discord_dm", "discord_private"):
                    user_key = DISCORD_DM_WHITELIST.get(discord_id)
                    if user_key:
                        if session_manager.source_users.get("discord") != user_key:
                            session_manager.switch_user(user_key, "discord")
                    else:
                        auto_key = f"discord_{display_name.lower().replace(' ', '_')}"
                        if session_manager.source_users.get("discord") != auto_key:
                            session_manager.switch_user(auto_key, "discord")

                    user = session_manager.get_current_user("discord")
                    _sync_hippocampus(session_manager.get_current_user_id("discord"))

                elif source == "web":
                    _sync_hippocampus(session_manager.get_current_user_id("web"))

                elif source == "console":
                    _sync_hippocampus(session_manager.get_current_user_id("console"))

                # Mode-spezifische History auswählen (per-User!)
                current_mode = session_manager.get_mode(source)

            # Die richtige History-Liste für den aktiven Mode
            history = history_dict.get(current_mode, history_dict.get("yourai", []))

            # Pipeline Call - das ist der lange Teil, OHNE Lock!
            # Damit kann parallel ein zweiter Request laufen
            log("PIPELINE", f"▶️ Processing: {display_name or user} ({source_label}) [mode={current_mode}]", Fore.CYAN)
            process_input_fn(text, user, source, history, image_urls=image_urls, discord_id=discord_id, channel_id=channel_id, session_uuid=session_uuid)
            log("PIPELINE", f"✅ Done: {display_name or user} ({source_label})", Fore.GREEN)

        except Exception as e:
            err = YourAIPipelineError(f"Worker crashed handling {source_label}", cause=e)
            log_exception("PIPELINE", err)
        finally:
            # Cleanup: User aus active list entfernen
            with _active_users_lock:
                if (display_name or user) in _active_users:
                    _active_users.remove(display_name or user)
            _active_workers.release()

    def _submit_to_pipeline(text: str, user: str, source: str,
                            display_name: str = "", discord_id: str = "",
                            image_urls: Optional[list] = None,
                            channel_id: int = 0,
                            session_uuid: str = "") -> bool:
        """
        Submitted einen Pipeline-Task. Returns False wenn alle Worker voll.
        """
        # Versuche einen Worker-Slot zu bekommen (non-blocking)
        got_slot = _active_workers.acquire(blocking=False)
        if not got_slot:
            # Alle Worker voll → "YourAI denkt nach" senden
            log("PIPELINE", f"⏳ Queue full! {display_name or user} muss warten...", Fore.YELLOW)
            if source in ("discord", "discord_dm", "discord_private") and discord_client:
                # Typing indicator senden (Discord zeigt "YourAI tippt...")
                # Message wird trotzdem in die Queue gepackt und beim nächsten Loop verarbeitet
                return False
            # Blocking wait für non-Discord (Console/Web)
            _active_workers.acquire(blocking=True)

        _pipeline_executor.submit(
            _run_pipeline_task, text, user, source, chat_history,
            display_name, discord_id, image_urls, channel_id, session_uuid
        )
        return True

    _pipeline_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="yourai-pipeline")

    # ==========================================
    # INPUT WORKER THREAD
    # ==========================================

    def input_worker():
        """Background Thread für Console Input."""
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
                    # Slash Commands zuerst (immer synchron)
                    if text.startswith("/") and _handle_slash_command(text):
                        processed = True
                        continue

                    # Session Commands
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
                # text is None when no input, "" when image-only
                if text is not None and (text.strip() or web_image_urls):
                    web_user_key = debug.get_last_web_user_key()
                    web_session_uuid = debug.get_last_web_session_uuid()
                    if web_user_key:
                        if session_manager.source_users.get("web") != web_user_key:
                            session_manager.switch_user(web_user_key, "web")

                    current_user = session_manager.get_current_user("web")
                    display_msg = text.strip() or f"[{len(web_image_urls)} Bild(er)]"
                    print(f"\n{Fore.CYAN}User ({current_user}): {display_msg}{Style.RESET_ALL}")
                    if web_image_urls:
                        print(f"{Fore.CYAN}   🖼️ {len(web_image_urls)} Bild(er) angehängt{Style.RESET_ALL}")
                    _submit_to_pipeline(text, current_user, "web", display_name=current_user, image_urls=web_image_urls, session_uuid=web_session_uuid)
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
                    text = msg["text"].strip()
                    discord_id = msg.get("discord_id", "")
                    source = msg.get("source", "discord")
                    display_name = msg.get("user", "Unknown")
                    image_urls = msg.get("image_urls", [])
                    channel_id = msg.get("channel_id", 0)

                    if source == "discord_dm":
                        source_label = "Discord DM"
                    elif source == "discord_private":
                        source_label = "Discord Privat"
                    else:
                        source_label = "Discord"
                    print(f"\n{Fore.BLUE}User ({source_label} {display_name}): {text}{Style.RESET_ALL}")
                    if image_urls:
                        print(f"{Fore.CYAN}   🖼️ {len(image_urls)} Bild(er) angehängt{Style.RESET_ALL}")

                    submitted = _submit_to_pipeline(
                        text, display_name, source,
                        display_name=display_name, discord_id=discord_id,
                        image_urls=image_urls, channel_id=channel_id
                    )
                    if not submitted:
                        # Worker voll - Message zurück in die Queue
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