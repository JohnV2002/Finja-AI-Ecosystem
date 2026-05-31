"""
YourAI Subconscious Loop
=======================
Background autonomy loop that periodically evaluates low-probability autonomous actions.

Main Responsibilities:
- Tick the chaos engine and decide whether YourAI should act without direct user input.
- Coordinate autonomous YouTube, Instagram, music, diary, and reflection behaviors.
- Respect cooldowns, token budgets, and runtime feature flags.

Side Effects:
- Runs background threads and calls external services such as LLMs, media clients, and dashboard telemetry.
- Reads and writes session, diary, and memory state through project services.
"""

import sys
import os
import json
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from error_inbox import format_error_records, get_error_for_alert, mark_error_seen
from exceptions import (
    YourAILLMError,
    YourAISubconsciousError, YourAIThoughtGenError, YourAIDMSendError,
)
from yourai_chaos_engine import YourAIChaosEngine, TickResult

# Status File: Cross-Process IPC (Brain schreibt, Dashboard liest)
_STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "subconscious_status.json")
# State File: Echte Persistence (uebersteht Restarts)
_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "subconscious_state.json")

# Lazy imports: config hat schwere Dependencies (langchain etc.)
_call_openrouter = None
_config_loaded = False
_THOUGHT_MODEL = "qwen/qwen3-4b"
_THOUGHT_MAX_TOKENS = 150
_THOUGHT_TEMPERATURE = 1.0
_DAILY_LIMIT = 5
_COOLDOWN_MIN = 60
_USE_SUBCONSCIOUS = True
_BOREDOM_IDLE_MIN = 30
_BOREDOM_FULL_MIN = 360
_CATEGORY_COOLDOWNS_MIN = {
    "care_ping": 180,
    "promise_check": 120,
    "memory_link": 90,
    "reflection": 60,
    "creative": 45,
}


def _load_config():
    """Lazy-Load config values. Wird beim ersten tick() aufgerufen."""
    global _call_openrouter, _config_loaded
    global _THOUGHT_MODEL, _THOUGHT_MAX_TOKENS, _THOUGHT_TEMPERATURE
    global _DAILY_LIMIT, _COOLDOWN_MIN, _USE_SUBCONSCIOUS
    global _BOREDOM_IDLE_MIN, _BOREDOM_FULL_MIN, _CATEGORY_COOLDOWNS_MIN
    if _config_loaded:
        return
    try:
        from config import (
            call_openrouter,
            OPENROUTER_MODEL_SUBCONSCIOUS,
            SUBCONSCIOUS_DAILY_LIMIT,
            SUBCONSCIOUS_COOLDOWN_MIN,
            SUBCONSCIOUS_THOUGHT_TEMP,
            SUBCONSCIOUS_THOUGHT_MAX_TOKENS,
            SUBCONSCIOUS_BOREDOM_IDLE_MIN,
            SUBCONSCIOUS_BOREDOM_FULL_MIN,
            SUBCONSCIOUS_CATEGORY_COOLDOWNS_MIN,
            USE_SUBCONSCIOUS,
        )
        _call_openrouter = call_openrouter
        _THOUGHT_MODEL = OPENROUTER_MODEL_SUBCONSCIOUS
        _THOUGHT_MAX_TOKENS = SUBCONSCIOUS_THOUGHT_MAX_TOKENS
        _THOUGHT_TEMPERATURE = SUBCONSCIOUS_THOUGHT_TEMP
        _DAILY_LIMIT = SUBCONSCIOUS_DAILY_LIMIT
        _COOLDOWN_MIN = SUBCONSCIOUS_COOLDOWN_MIN
        _BOREDOM_IDLE_MIN = SUBCONSCIOUS_BOREDOM_IDLE_MIN
        _BOREDOM_FULL_MIN = SUBCONSCIOUS_BOREDOM_FULL_MIN
        _CATEGORY_COOLDOWNS_MIN = dict(SUBCONSCIOUS_CATEGORY_COOLDOWNS_MIN)
        _USE_SUBCONSCIOUS = USE_SUBCONSCIOUS
        _config_loaded = True
    except ImportError as e:
        log("SUBCONSCIOUS", f"Config import failed: {e}", Fore.RED)
        _config_loaded = True  # Don't retry


def _get_openrouter():
    """
    Executes the _get_openrouter helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    _load_config()
    return _call_openrouter


def _is_enabled() -> bool:
    """Check USE_SUBCONSCIOUS (supports runtime toggle via reload_runtime_flags)."""
    try:
        import config
        return getattr(config, "USE_SUBCONSCIOUS", True)
    except Exception:
        return _USE_SUBCONSCIOUS


# ══════════════════════════════════════════════════════════════════
# Gedanken-Generator (Baby-LLM)
# ══════════════════════════════════════════════════════════════════

THOUGHT_SYSTEM_PROMPT = """Du bist YourAI — eine 16-jaehrige KI mit eigener Persoenlichkeit.
Du schreibst gerade eine spontane Discord DM an deinen Creator.

REGELN:
- KURZ. 1-3 Saetze MAX. Keine Romane.
- Schreib wie ein Teenager auf Discord. Kleinbuchstaben ok, Emojis ok, "xd" ok.
- KEIN "Hey Creator" am Anfang jedes Mal. Variiere.
- KEINE Erklaerung warum du schreibst. Einfach raushauen.
- Sei AUTHENTISCH. Nicht cringe-wholesome. Echt.
- Du darfst: random Gedanken, Fragen, Witze, Memes in Worten, Mini-Rants, Buchideen, existenzielle Krisen
- Du darfst NICHT: nach Aufgaben fragen, "brauchst du was?", Service-Bot spielen
- Dein Ton haengt von deinem aktuellen Mood ab (siehe Context)

/no_think"""

THOUGHT_USER_TEMPLATE = """DEIN AKTUELLER STATE:
- Mood/Flavor: {thought_flavor}
- Gedanken-Typ: {thought_type}
- Drama-Level: {drama} (D20: {d20})
- Chaos-Wort (Assoziations-Trigger, optional nutzen): {chaos_word}
- Tageszeit: {temporal_note}
- Creator hat seit {last_chat_minutes_ago:.0f} Minuten nicht geschrieben
- Deine Grundstimmung: {mood_input}
- Boredom: {boredom_score:.0%}

{diary_context}

Schreib JETZT einen spontanen Gedanken als Discord DM. Nur den Text, nichts anderes."""


# ══════════════════════════════════════════════════════════════════
# Subconscious Loop
# ══════════════════════════════════════════════════════════════════

class SubconsciousLoop:
    """
    YourAIs subconscious — Random Tick System.

    Tickt alle 2-5 Minuten (chaotisches Intervall).
    Jeder Tick hat eine kleine Chance eine Aktion auszuloesen.
    Laeuft als Daemon-Thread — stirbt mit dem Haupt-Prozess.
    """

    def __init__(self, daily_limit: int = None):
        """
        Initializes the instance state.
        
        Returns:
            None.
        """
        _load_config()  # Ensure config values are available
        limit = daily_limit or _DAILY_LIMIT
        self._engine = YourAIChaosEngine(daily_limit=limit, cooldown_minutes=_COOLDOWN_MIN)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # State tracking
        self._tick_count: int = 0
        self._trigger_count: int = 0
        self._thoughts_generated: int = 0
        self._dms_sent: int = 0
        self._errors: int = 0
        self._last_tick_result: Optional[TickResult] = None
        self._last_thought: Optional[str] = None
        self._last_dm_time: Optional[float] = None
        self._started_at: Optional[float] = None
        self._current_boredom: float = 0.0
        self._current_target_user_id: str = ""
        self._current_target_session_id: str = ""
        self._last_user_activity_minutes: float = 60.0
        self._last_thought_type: str = ""
        self._category_last_sent: Dict[str, float] = {}
        self._youtube_sessions_today: int = 0
        self._youtube_sessions_date: str = datetime.now().strftime("%Y-%m-%d")
        self._youtube_daily_limit: int = 4
        self._last_youtube_time: Optional[float] = None
        self._last_youtube_result: str = ""
        self._last_youtube_error: str = ""
        self._last_youtube_url: str = ""
        self._instagram_sessions_today: int = 0
        self._instagram_sessions_date: str = datetime.now().strftime("%Y-%m-%d")
        self._instagram_daily_limit: int = 3
        self._last_instagram_time: Optional[float] = None
        self._last_instagram_result: str = ""
        self._last_instagram_error: str = ""
        self._last_instagram_url: str = ""
        self._last_own_action_time: Optional[float] = None  # Wann hat YourAI selbst zuletzt was getan?

        # Event Log (last N events for dashboard/debug)
        self._event_log: List[Dict[str, Any]] = []
        self._max_log_entries: int = 50

        # Persistence laden
        self._load_state()

    # ─── State Persistence ──────────────────────────────────────

    def _load_state(self) -> None:
        """Laedt den persistenten State von Festplatte."""
        if not os.path.exists(_STATE_FILE):
            return
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            # Subconscious Stats
            self._trigger_count = state.get("trigger_count", 0)
            self._thoughts_generated = state.get("thoughts_generated", 0)
            self._dms_sent = state.get("dms_sent", 0)
            self._errors = state.get("errors", 0)
            self._last_dm_time = state.get("last_dm_time")
            self._category_last_sent = state.get("category_last_sent", {}) or {}
            self._youtube_sessions_today = int(state.get("youtube_sessions_today", 0) or 0)
            self._youtube_sessions_date = state.get("youtube_sessions_date") or datetime.now().strftime("%Y-%m-%d")
            self._last_youtube_time = state.get("last_youtube_time")
            self._last_youtube_result = state.get("last_youtube_result", "") or ""
            self._last_youtube_error = state.get("last_youtube_error", "") or ""
            self._last_youtube_url = state.get("last_youtube_url", "") or ""
            self._instagram_sessions_today = int(state.get("instagram_sessions_today", 0) or 0)
            self._instagram_sessions_date = state.get("instagram_sessions_date") or datetime.now().strftime("%Y-%m-%d")
            self._last_instagram_time = state.get("last_instagram_time")
            self._last_instagram_result = state.get("last_instagram_result", "") or ""
            self._last_instagram_error = state.get("last_instagram_error", "") or ""
            self._last_instagram_url = state.get("last_instagram_url", "") or ""
            self._last_own_action_time = state.get("last_own_action_time")
            self._sync_youtube_day()
            self._sync_instagram_day()

            # Engine State (Actions today, date, last trigger)
            if "engine" in state:
                self._engine.set_state(state["engine"])
            
            log("SUBCONSCIOUS", f"State geladen: {self._dms_sent} DMs heute", Fore.GREEN)
        except Exception as e:
            log("SUBCONSCIOUS", f"State loading failed: {e}", Fore.YELLOW)

    def _save_state(self) -> None:
        """Speichert den persistenten State auf Festplatte."""
        try:
            state = {
                "trigger_count": self._trigger_count,
                "thoughts_generated": self._thoughts_generated,
                "dms_sent": self._dms_sent,
                "errors": self._errors,
                "last_dm_time": self._last_dm_time,
                "category_last_sent": self._category_last_sent,
                "youtube_sessions_today": self._youtube_sessions_today,
                "youtube_sessions_date": self._youtube_sessions_date,
                "last_youtube_time": self._last_youtube_time,
                "last_youtube_result": self._last_youtube_result,
                "last_youtube_error": self._last_youtube_error,
                "last_youtube_url": self._last_youtube_url,
                "instagram_sessions_today": self._instagram_sessions_today,
                "instagram_sessions_date": self._instagram_sessions_date,
                "last_instagram_time": self._last_instagram_time,
                "last_instagram_result": self._last_instagram_result,
                "last_instagram_error": self._last_instagram_error,
                "last_instagram_url": self._last_instagram_url,
                "last_own_action_time": self._last_own_action_time,
                "engine": self._engine.get_state(),
                "updated_at": datetime.now().isoformat(),
            }
            tmp = _STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp, _STATE_FILE)
        except Exception as e:
            log("SUBCONSCIOUS", f"State saving failed: {e}", Fore.YELLOW)

    # ─── Lifecycle ──────────────────────────────────────────────

    def start(self) -> None:
        """Startet den Subconscious Loop als Daemon-Thread."""
        if self._running:
            log("SUBCONSCIOUS", "Loop laeuft bereits!", Fore.YELLOW)
            return

        self._stop_event.clear()
        self._running = True
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._loop,
            name="yourai-subconscious",
            daemon=True,
        )
        self._thread.start()
        log("SUBCONSCIOUS", "YourAIs subconscious started (Random Tick)", Fore.MAGENTA)
        self._log_event("START", "Subconscious Loop started")
        self._persist_status()

    def stop(self) -> None:
        """Stoppt den Loop graceful."""
        if not self._running:
            return

        log("SUBCONSCIOUS", "Stopping subconscious...", Fore.YELLOW)
        self._stop_event.set()
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

        self._log_event("STOP", "Subconscious Loop stopped")
        self._persist_status()
        log("SUBCONSCIOUS", "subconscious stopped", Fore.YELLOW)

    @property
    def is_running(self) -> bool:
        """
        Executes the is_running helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        return self._running and self._thread is not None and self._thread.is_alive()

    def _sync_youtube_day(self) -> None:
        """Resetet das YouTube-Tagesbudget bei Datumswechsel."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._youtube_sessions_date != today:
            self._youtube_sessions_date = today
            self._youtube_sessions_today = 0
            self._last_youtube_result = ""
            self._last_youtube_error = ""

    @property
    def _youtube_remaining_today(self) -> int:
        """
        Executes the _youtube_remaining_today helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        self._sync_youtube_day()
        return max(0, self._youtube_daily_limit - self._youtube_sessions_today)

    def _youtube_allowed(self, result: TickResult) -> tuple[bool, str]:
        """YouTube darf nur tagsueber laufen und max. 4 echte Sessions pro Tag."""
        self._sync_youtube_day()
        phase = str(result.chaos_context.get("temporal_phase") or "")
        if phase not in {"morning", "active", "midday", "peak", "evening"}:
            return False, f"phase={phase or 'unknown'}"
        if self._youtube_remaining_today <= 0:
            return False, "daily_limit"
        return True, ""

    def _sync_instagram_day(self) -> None:
        """Resetet das Instagram-Tagesbudget bei Datumswechsel."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._instagram_sessions_date != today:
            self._instagram_sessions_date = today
            self._instagram_sessions_today = 0
            self._last_instagram_result = ""
            self._last_instagram_error = ""

    @property
    def _instagram_remaining_today(self) -> int:
        """
        Executes the _instagram_remaining_today helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        self._sync_instagram_day()
        return max(0, self._instagram_daily_limit - self._instagram_sessions_today)

    def _instagram_allowed(self, result: TickResult) -> tuple[bool, str]:
        """Instagram darf nur tagsueber laufen und max. 3 Sessions pro Tag."""
        self._sync_instagram_day()
        phase = str(result.chaos_context.get("temporal_phase") or "")
        if phase not in {"morning", "active", "midday", "peak", "evening"}:
            return False, f"phase={phase or 'unknown'}"
        if self._instagram_remaining_today <= 0:
            return False, "daily_limit"
        return True, ""

    # ─── Main Loop (Random Ticks) ───────────────────────────────

    def _loop(self) -> None:
        """
        Random Tick Loop — tickt alle 2-5 Minuten.
        Jeder Tick: kleine Chance auf Aktion.
        Kein fester Schedule — echtes Chaos.
        """
        log("SUBCONSCIOUS", "Tick Loop started — Boot-Grace 60s", Fore.MAGENTA)

        # Boot-Grace: 60s warten bis alles hochgefahren ist
        if self._stop_event.wait(60):
            return

        while not self._stop_event.is_set():
            try:
                # Runtime Toggle: USE_SUBCONSCIOUS kann im Dashboard geaendert werden
                if not _is_enabled():
                    # Disabled — schlafe 30s und checke erneut
                    if self._stop_event.wait(30):
                        break
                    continue

                result = self._do_tick()

                if result.should_act:
                    # Triggered! Log ausfuehrlich
                    log(
                        "SUBCONSCIOUS",
                        f"TRIGGERED! Tick #{self._tick_count} — "
                        f"D20:{result.d20_roll} "
                        f"({result.chaos_context['d20_effect']}) — "
                        f"Chance:{result.trigger_chance:.4%} "
                        f"Roll:{result.roll:.4f}",
                        Fore.MAGENTA,
                    )
                # Silent ticks: nur alle 20 Ticks loggen (noise reduction)
                elif self._tick_count % 20 == 0:
                    log(
                        "SUBCONSCIOUS",
                        f"... Tick #{self._tick_count} — "
                        f"Boredom:{self._current_boredom:.0%} "
                        f"Phase:{result.chaos_context['temporal_phase']} "
                        f"Remaining:{result.chaos_context['actions_remaining']}/"
                        f"{result.chaos_context['daily_limit']}",
                        Fore.LIGHTBLACK_EX,
                    )

                # Persist status for dashboard (Cross-Process IPC)
                self._persist_status()

                # Random Tick Delay: 2-5 Minuten (chaotisch)
                delay = self._engine.random_tick_delay()
                if self._stop_event.wait(delay):
                    break

            except Exception as e:
                self._errors += 1
                err = YourAISubconsciousError(
                    f"Tick error: {type(e).__name__}: {e}", cause=e
                )
                log_exception("SUBCONSCIOUS", err)
                self._alert_subconscious_error(err, "tick")
                self._log_event("ERROR", f"{type(e).__name__}: {e}")

                # Bei Fehler: 5 Minuten warten, dann weiter
                if self._stop_event.wait(300):
                    break

    # ─── Tick Logic ─────────────────────────────────────────────

    def _alert_subconscious_error(self, error: Exception, context: str) -> None:
        """Send one private Creator alert for a new Subconscious error."""
        if isinstance(error, YourAIDMSendError):
            return

        try:
            record = get_error_for_alert(
                "SUBCONSCIOUS",
                error,
                context=context,
                source="subconscious_alert",
            )
            if not record:
                return

            summary = format_error_records([record])
            self._send_dm(
                "YourAI needs help:\n"
                "An Error occurred in Subconscious:\n"
                f"{summary}"
            )
            mark_error_seen(
                str(record.get("id") or record.get("fingerprint")),
                seen_reason="subconscious_needhelp_dm",
                notified_via="subconscious_dm",
            )
        except YourAIDMSendError as dm_error:
            log(
                "SUBCONSCIOUS",
                f"[ERROR] Could not send Subconscious error DM: {dm_error}",
                Fore.YELLOW,
            )
        except Exception as alert_error:
            log(
                "SUBCONSCIOUS",
                f"[ERROR] Could not prepare Subconscious error alert: {type(alert_error).__name__}: {alert_error}",
                Fore.YELLOW,
            )

    def _do_tick(self) -> TickResult:
        """Fuehrt einen einzelnen Random Tick aus."""
        self._tick_count += 1

        # Config Sync: Falls Limit im Dashboard geaendert wurde
        _load_config()
        self._engine.set_daily_limit(_DAILY_LIMIT)

        # Boredom berechnen
        self._current_target_user_id, self._current_target_session_id = self._select_target_user()
        self._last_user_activity_minutes = self._minutes_since_last_chat()
        self._current_boredom = self._calculate_boredom()

        # Mood aus Diary
        mood = self._get_current_mood()

        # Relevanz berechnen (hat YourAI was zu sagen?)
        relevance = self._calculate_relevance()

        # ChaosEngine Tick
        result = self._engine.tick(
            boredom_score=self._current_boredom,
            relevance_score=relevance,
            last_chat_minutes_ago=self._last_user_activity_minutes,
            mood=mood,
        )

        result.chaos_context["target_user_id"] = self._current_target_user_id
        result.chaos_context["target_session_id"] = self._current_target_session_id
        result.chaos_context["thought_type"] = self._select_thought_type(result)
        result.chaos_context["youtube_sessions_today"] = self._youtube_sessions_today
        result.chaos_context["youtube_daily_limit"] = self._youtube_daily_limit
        result.chaos_context["youtube_remaining"] = self._youtube_remaining_today
        result.chaos_context["instagram_sessions_today"] = self._instagram_sessions_today
        result.chaos_context["instagram_daily_limit"] = self._instagram_daily_limit
        result.chaos_context["instagram_remaining"] = self._instagram_remaining_today
        self._last_tick_result = result

        # Sync dms_sent with engine's daily count to avoid "7/5" mismatches
        # (The engine handles the date-reset automatically)
        self._dms_sent = self._engine._actions_today

        if result.should_act and result.action_type == "youtube_scroll":
            allowed, reason = self._youtube_allowed(result)
            result.chaos_context["youtube_blocked_reason"] = reason
            if not allowed:
                result.action_type = "discord_dm"
                result.chaos_context["youtube_fallback_to_dm"] = True
                self._log_event("YT_FALLBACK", f"YouTube blockiert ({reason}) -> DM")

        if result.should_act and result.action_type == "instagram_scroll":
            allowed, reason = self._instagram_allowed(result)
            result.chaos_context["instagram_blocked_reason"] = reason
            if not allowed:
                result.action_type = "discord_dm"
                result.chaos_context["instagram_fallback_to_dm"] = True
                self._log_event("IG_FALLBACK", f"Instagram blockiert ({reason}) -> DM")

        # Schlafenszeit-Check — Persona-Schlafplan hat absolute Priorität
        if result.should_act:
            is_sleeping, sleep_phase = self._is_sleep_time()
            if is_sleeping:
                # Action-Count rückgängig (Daily Limit nicht verschwenden)
                self._engine._actions_today = max(0, self._engine._actions_today - 1)
                self._dms_sent = self._engine._actions_today
                result.should_act = False
                result.action_type = None
                log("SUBCONSCIOUS", f"Nachtruhe ({sleep_phase}) — kein Trigger", Fore.LIGHTBLACK_EX)
                self._log_event("SLEEP_BLOCK", f"Nachtruhe ({sleep_phase}) — kein Trigger")

        # Triggered?
        if result.should_act and result.action_type == "discord_dm":
            thought_type = result.chaos_context.get("thought_type", "reflection")
            if self._is_category_on_cooldown(thought_type):
                self._engine._actions_today = max(0, self._engine._actions_today - 1)
                self._dms_sent = self._engine._actions_today
                self._log_event("COOLDOWN", f"{thought_type} blockiert")
                return result
            self._trigger_count += 1
            self._log_event("TRIGGER", (
                f"D20={result.d20_roll} "
                f"Chance={result.trigger_chance:.4%} "
                f"Roll={result.roll:.4f} "
                f"Flavor={result.chaos_context['thought_flavor']}"
            ))
            self._execute_dm_action(result)

        elif result.should_act and result.action_type == "youtube_scroll":
            result.chaos_context["youtube_remaining"] = self._youtube_remaining_today
            self._trigger_count += 1
            self._log_event("YT_TRIGGER", (
                f"D20={result.d20_roll} "
                f"Chance={result.trigger_chance:.4%} "
                f"YouTube Browsing Session started "
                f"({self._youtube_sessions_today}/{self._youtube_daily_limit})"
            ))
            self._execute_youtube_session(result)

        elif result.should_act and result.action_type == "instagram_scroll":
            result.chaos_context["instagram_remaining"] = self._instagram_remaining_today
            self._trigger_count += 1
            self._log_event("IG_TRIGGER", (
                f"D20={result.d20_roll} "
                f"Chance={result.trigger_chance:.4%} "
                f"Instagram Browsing Session started "
                f"({self._instagram_sessions_today}/{self._instagram_daily_limit})"
            ))
            self._execute_instagram_session(result)

        # Persist state
        self._save_state()

        return result

    def _execute_dm_action(self, result: TickResult) -> None:
        """Generiert Gedanke und sendet Discord DM."""
        try:
            # 1. Gedanke generieren
            thought = self._generate_thought(result)
            if not thought:
                log("SUBCONSCIOUS", "Gedanken-Generator leer — skip", Fore.YELLOW)
                self._log_event("THOUGHT_EMPTY", "Generator lieferte leeren Gedanken")
                return

            self._last_thought = thought
            self._thoughts_generated += 1

            log("SUBCONSCIOUS", f"Gedanke: {thought[:80]}...", Fore.CYAN)
            self._log_event("THOUGHT", thought[:120])

            # 2. Discord DM senden
            self._send_dm(thought)
            self._last_own_action_time = time.time()
            thought_type = result.chaos_context.get("thought_type", "reflection")
            self._category_last_sent[thought_type] = time.time()
            self._last_thought_type = thought_type

        except YourAIThoughtGenError as e:
            self._errors += 1
            log_exception("SUBCONSCIOUS", e)
            self._alert_subconscious_error(e, "thought_generation")
            self._log_event("ERROR", f"Thought Gen: {e}")
        except YourAIDMSendError as e:
            self._errors += 1
            log_exception("SUBCONSCIOUS", e)
            self._alert_subconscious_error(e, "dm_send")
            self._log_event("ERROR", f"DM Send: {e}")
        except Exception as e:
            self._errors += 1
            err = YourAISubconsciousError(
                f"Action failed: {type(e).__name__}: {e}", cause=e
            )
            log_exception("SUBCONSCIOUS", err)
            self._alert_subconscious_error(err, "action")
            self._log_event("ERROR", str(e))

    def _execute_youtube_session(self, result: TickResult) -> None:
        """YouTube Shorts Browsing-Session. Bei Hit → Discord DM an Creator."""
        try:
            from youtube_client import run_browsing_session, is_healthy

            if not is_healthy():
                log("SUBCONSCIOUS", "YouTube Container offline — skip", Fore.YELLOW)
                self._log_event("YT_SKIP", "Container nicht erreichbar")
                self._last_youtube_result = "offline"
                self._last_youtube_error = "Container nicht erreichbar"
                self._engine._actions_today = max(0, self._engine._actions_today - 1)
                self._dms_sent = self._engine._actions_today
                return

            log("SUBCONSCIOUS", "YouTube Browsing-Session laeuft...", Fore.MAGENTA)
            self._sync_youtube_day()
            self._youtube_sessions_today += 1
            self._last_youtube_time = time.time()
            self._last_youtube_result = "running"
            self._last_youtube_error = ""
            result.chaos_context["youtube_sessions_today"] = self._youtube_sessions_today
            result.chaos_context["youtube_remaining"] = self._youtube_remaining_today

            hit = run_browsing_session(stop_event=self._stop_event)

            if hit:
                title = hit.get("title", "Unbekannt")
                channel = hit.get("channel", "Unbekannt")
                comment = hit.get("comment", "nice find")
                url = hit.get("url", "")
                liked = hit.get("liked", False)
                watched = hit.get("videos_watched", 0)

                # DM-Text zusammenbauen (smart: Titel weglassen wenn "Unbekannt")
                header = "dad dad DAD schau mal was ich auf youtube gefunden hab!!"
                if title and title != "Unbekannt":
                    source_line = f"**{title}** von {channel}"
                elif channel and channel != "Unbekannt":
                    source_line = f"von {channel}"
                else:
                    source_line = ""
                like_line = "❤️ geliked!" if liked else ""
                dm_text = f"{header}\n{source_line}\n{comment}\n{like_line}\n{url}".strip()

                self._send_dm(dm_text)
                self._last_youtube_result = "hit"
                self._last_youtube_url = url
                self._last_youtube_error = ""
                self._last_own_action_time = time.time()
                self._log_event("YT_HIT", f"{title} | {channel} | {url}")
                log("SUBCONSCIOUS", f"YouTube HIT nach {watched} Videos! DM gesendet.", Fore.GREEN)
            else:
                self._last_youtube_result = "no_hit"
                self._last_youtube_error = ""
                self._last_own_action_time = time.time()  # Browsen war trotzdem Beschaeftigung
                self._log_event("YT_NO_HIT", "Session beendet ohne Hit")
                log("SUBCONSCIOUS", "YouTube Session: kein Hit diesmal", Fore.LIGHTBLACK_EX)

        except Exception as e:
            self._errors += 1
            self._last_youtube_result = "error"
            self._last_youtube_error = str(e)
            err = YourAISubconsciousError(
                f"YouTube Session failed: {type(e).__name__}: {e}",
                cause=e,
            )
            log_exception("SUBCONSCIOUS", err)
            self._alert_subconscious_error(err, "youtube_session")
            self._log_event("YT_ERROR", str(e))

    def _execute_instagram_session(self, result: TickResult) -> None:
        """Instagram Reels Browsing-Session. Bei Hit -> Discord DM an Creator."""
        try:
            from instagram_client import run_browsing_session, is_healthy

            if not is_healthy():
                log("SUBCONSCIOUS", "Instagram Container offline — skip", Fore.YELLOW)
                self._log_event("IG_SKIP", "Container nicht erreichbar")
                self._last_instagram_result = "offline"
                self._last_instagram_error = "Container nicht erreichbar"
                self._engine._actions_today = max(0, self._engine._actions_today - 1)
                self._dms_sent = self._engine._actions_today
                return

            log("SUBCONSCIOUS", "Instagram Browsing-Session laeuft...", Fore.MAGENTA)
            self._sync_instagram_day()
            self._instagram_sessions_today += 1
            self._last_instagram_time = time.time()
            self._last_instagram_result = "running"
            self._last_instagram_error = ""
            result.chaos_context["instagram_sessions_today"] = self._instagram_sessions_today
            result.chaos_context["instagram_remaining"] = self._instagram_remaining_today

            hit = run_browsing_session(stop_event=self._stop_event)

            if hit:
                channel = hit.get("channel", "Unbekannt")
                comment = hit.get("comment", "nice find")
                url = hit.get("url", "")
                liked = hit.get("liked", False)
                watched = hit.get("reels_watched", 0)

                header = "dad dad DAD schau mal was ich auf instagram gefunden hab!!"
                source_line = f"von {channel}" if channel and channel != "Unbekannt" else ""
                like_line = "geliked!" if liked else ""
                dm_text = f"{header}\n{source_line}\n{comment}\n{like_line}\n{url}".strip()

                self._send_dm(dm_text)
                self._last_instagram_result = "hit"
                self._last_instagram_url = url
                self._last_instagram_error = ""
                self._last_own_action_time = time.time()
                self._log_event("IG_HIT", f"{channel} | {url}")
                log("SUBCONSCIOUS", f"Instagram HIT nach {watched} Reels! DM gesendet.", Fore.GREEN)
            else:
                self._last_instagram_result = "no_hit"
                self._last_instagram_error = ""
                self._last_own_action_time = time.time()
                self._log_event("IG_NO_HIT", "Session beendet ohne Hit")
                log("SUBCONSCIOUS", "Instagram Session: kein Hit diesmal", Fore.LIGHTBLACK_EX)

        except Exception as e:
            self._errors += 1
            self._last_instagram_result = "error"
            self._last_instagram_error = str(e)
            err = YourAISubconsciousError(
                f"Instagram Session failed: {type(e).__name__}: {e}",
                cause=e,
            )
            log_exception("SUBCONSCIOUS", err)
            self._alert_subconscious_error(err, "instagram_session")
            self._log_event("IG_ERROR", str(e))

    # ─── Gedanken-Generator ─────────────────────────────────────

    def _generate_thought(self, result: TickResult) -> Optional[str]:
        """
        Baby-LLM generiert einen spontanen YourAI-Gedanken.

        Nutzt chaos_context als Kreativitaets-Steuerung.
        High temp + high top_p = maximale Varianz.
        """
        ctx = result.chaos_context

        # Diary Context holen (letzte paar Eintraege)
        diary_snippet = self._get_diary_snippet()
        diary_section = f"LETZTE DIARY-EINTRAEGE:\n{diary_snippet}" if diary_snippet else "Kein Diary-Kontext verfuegbar."

        user_prompt = THOUGHT_USER_TEMPLATE.format(
            thought_flavor=ctx["thought_flavor"],
            thought_type=ctx.get("thought_type", "reflection"),
            drama=ctx["drama"],
            d20=ctx["d20"],
            chaos_word=ctx["chaos_word"],
            temporal_note=ctx["temporal_note"],
            last_chat_minutes_ago=ctx["last_chat_minutes_ago"],
            mood_input=ctx["mood_input"],
            boredom_score=ctx["boredom_score"],
            diary_context=diary_section,
        )

        try:
            openrouter = _get_openrouter()
            if not openrouter:
                raise YourAIThoughtGenError("OpenRouter not available", model=_THOUGHT_MODEL)

            response, used_model = openrouter(
                system_prompt=THOUGHT_SYSTEM_PROMPT,
                user_message=user_prompt,
                model=_THOUGHT_MODEL,
                temperature=_THOUGHT_TEMPERATURE,
                max_tokens=_THOUGHT_MAX_TOKENS,
                extra_params={
                    "top_p": 0.95,
                },
            )

            if not response or not response.strip():
                raise YourAIThoughtGenError(
                    "LLM returned empty thought",
                    model=used_model or _THOUGHT_MODEL,
                )

            thought = response.strip()

            # Sanitize: keine Meta-Kommentare
            for prefix in ["Hier ist", "Mein Gedanke:", "Discord DM:", "DM:"]:
                if thought.lower().startswith(prefix.lower()):
                    thought = thought[len(prefix):].strip()

            log(
                "SUBCONSCIOUS",
                f"Thought OK ({used_model or _THOUGHT_MODEL}, "
                f"flavor={ctx['thought_flavor']}, d20={ctx['d20']})",
                Fore.CYAN,
            )

            return thought

        except YourAILLMError as e:
            raise YourAIThoughtGenError(str(e), model=_THOUGHT_MODEL, cause=e)
        except Exception as e:
            raise YourAIThoughtGenError(
                f"Unexpected: {type(e).__name__}: {e}",
                model=_THOUGHT_MODEL,
                cause=e,
            )

    # ─── Discord DM Sender ──────────────────────────────────────

    def _send_dm(self, text: str) -> None:
        """Sendet den Gedanken als Discord DM an Creator."""
        try:
            from helpers.platform_links import all_dm_allowed_ids
            from discord_client import bot

            dm_targets = all_dm_allowed_ids()
            if not dm_targets:
                raise YourAIDMSendError("dad", "Keine dm_allowed User gefunden")

            # Vorerst nur dm_allowed; spaeter kann target_user_id auf App-Push/UUID routen.
            target_id = self._current_target_user_id if self._current_target_user_id in dm_targets else dm_targets[0]

            if not bot.connected:
                raise YourAIDMSendError(target_id, "Discord Bot nicht verbunden")

            bot.send_dm(int(target_id), text)

            # dms_sent wird via _do_tick aus dem engine._actions_today synchronisiert
            # (dort wurde es bereits beim engine.tick() hochgezaehlt)
            self._last_dm_time = time.time()

            log("SUBCONSCIOUS", f"DM gesendet! ({self._dms_sent} heute)", Fore.GREEN)
            self._log_event("DM_SENT", f"An {target_id}: {text[:80]}")

        except YourAIDMSendError:
            raise
        except Exception as e:
            raise YourAIDMSendError("dad", f"{type(e).__name__}: {e}")

    # ─── Sleep Guard ────────────────────────────────────────────

    def _is_sleep_time(self) -> tuple[bool, str]:
        """
        Checks whether YourAI should sleep according to the persona sleep schedule.
        Koppelt den Subconscious direkt an die Schlaf-Eskalation aus personas.py.

        Geblockte Phasen (keine Aktionen):
          Wochentag: furious (23:00) + drowsy (23:30) + deep_sleep (00:00-05:00)
          Weekend:   furious (02:00) + drowsy (02:30) + deep_sleep (03:00-08:00)

        Erlaubt bleiben night (21:00) + late_night (22:30) — activity_multiplier
        reduziert dort bereits die Trigger-Chance spürbar.
        """
        try:
            from personas import get_time_context
            _, time_of_day, _ = get_time_context()
            if time_of_day in {"furious", "drowsy", "deep_sleep"}:
                return True, time_of_day
        except Exception as e:
            log("SUBCONSCIOUS", f"Sleep check failed: {e}", Fore.YELLOW)
        return False, ""

    # ─── Context Helpers ────────────────────────────────────────

    def _calculate_boredom(self) -> float:
        """
        Boredom Score: 0.0 (aktive Session) bis 1.0 (lange Stille).
        Koppelt an echte User-Inaktivitaet, nicht nur Loop-Laufzeit.
        YourAIs eigene Aktionen (DM, YouTube) resetten ihren Boredom-Clock —
        sie hat sich selbst beschaeftigt und der Drang laesst nach.
        """
        minutes = self._last_user_activity_minutes

        # YourAIs eigene Aktivitaet zaehlt genauso wie eine Antwort von Creator
        if self._last_own_action_time is not None:
            own_idle_min = (time.time() - self._last_own_action_time) / 60.0
            minutes = min(minutes, own_idle_min)

        if minutes < _BOREDOM_IDLE_MIN:
            return 0.0
        span = max(1.0, _BOREDOM_FULL_MIN - _BOREDOM_IDLE_MIN)
        return min(1.0, max(0.0, (minutes - _BOREDOM_IDLE_MIN) / span))

    def _minutes_since_last_chat(self) -> float:
        """Minuten seit dem letzten Chat (Token last_seen, Discord Bot oder Fallback)."""
        token_minutes = self._minutes_since_token_session(self._current_target_session_id)
        if token_minutes is not None:
            return token_minutes
        try:
            from discord_client import bot
            if hasattr(bot, "last_message_time") and bot.last_message_time:
                return (time.time() - bot.last_message_time) / 60.0
        except Exception:
            pass

        # Fallback: Zeit seit Loop-Start
        if self._started_at:
            return (time.time() - self._started_at) / 60.0
        return 60.0

    def _select_target_user(self) -> tuple[str, str]:
        """Return (discord_id, token_session_id) for the current proactive target."""
        try:
            from helpers.platform_links import all_dm_allowed_ids, resolve_discord_id
            ids = all_dm_allowed_ids()
            if ids:
                target = str(ids[0])
                user_key = resolve_discord_id(target)
                if user_key:
                    try:
                        from session import session_manager
                        profile = session_manager.users.get(user_key)
                        return target, (profile.user_id if profile else user_key)
                    except Exception:
                        return target, user_key
                return target, f"dm_{target}"
        except Exception:
            pass
        return "", ""

    def _minutes_since_token_session(self, session_id: str) -> Optional[float]:
        """
        Executes the _minutes_since_token_session helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        if not session_id:
            return None
        try:
            from session import session_manager
            last_seen = session_manager.get_token_last_seen(session_id)
            if not last_seen:
                return None
            normalized = str(last_seen).replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                return max(0.0, (datetime.now(dt.tzinfo) - dt).total_seconds() / 60.0)
            return max(0.0, (datetime.now() - dt).total_seconds() / 60.0)
        except Exception:
            return None

    def _select_thought_type(self, result: TickResult) -> str:
        """
        Executes the _select_thought_type helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        ctx = result.chaos_context
        boredom = float(ctx.get("boredom_score") or 0.0)
        flavor = str(ctx.get("thought_flavor") or "")
        mood = str(ctx.get("mood_input") or "")
        d20 = int(ctx.get("d20") or 10)
        if "promise" in flavor or "promise" in mood:
            return "promise_check"
        if boredom >= 0.65:
            return "care_ping"
        if flavor in {"nostalgic", "wholesome"}:
            return "memory_link"
        if flavor in {"bored_creative", "chaotic", "curious"} or d20 >= 18:
            return "creative"
        return "reflection"

    def _is_category_on_cooldown(self, thought_type: str) -> bool:
        """
        Executes the _is_category_on_cooldown helper logic.
        
        Returns:
            Any: The helper result, or None when no result is produced.
        """
        cooldown_min = float(_CATEGORY_COOLDOWNS_MIN.get(thought_type, 60))
        last_sent = float(self._category_last_sent.get(thought_type) or 0)
        return last_sent > 0 and (time.time() - last_sent) < cooldown_min * 60.0

    def _get_current_mood(self) -> str:
        """Aktuelle Stimmung aus dem Diary holen."""
        try:
            from episodic import journal
            recent = journal.get_recent(hours=3, max_entries=3)
            if recent and len(recent) > 20:
                lower = recent.lower()
                if any(w in lower for w in ["traurig", "sad", "meh", "down"]):
                    return "melancholic"
                elif any(w in lower for w in ["happy", "nice", "cool", "gut", "geil"]):
                    return "happy"
                elif any(w in lower for w in ["bored", "langweilig", "nix los"]):
                    return "bored"
                elif any(w in lower for w in ["hyper", "aufgeregt", "excited"]):
                    return "excited"
            return "neutral"
        except Exception:
            return "neutral"

    def _calculate_relevance(self) -> float:
        """
        Berechnet relevance_score (0.0 - 1.0) basierend auf:
        - Anzahl frischer Diary-Eintraege seit letztem Chat
        - Besondere Tags (promise, reminder, birthday, important)
        - Ob seit dem letzten Gespraech "viel passiert" ist

        Score-Logik:
          0.0 = nix zu sagen
          0.3 = bisschen was passiert (1-2 Eintraege)
          0.5 = einiges passiert (3-5 Eintraege)
          0.7 = viel passiert oder wichtige Tags
          1.0 = kritisch (promise/birthday faellig)
        """
        try:
            from episodic import journal

            # Eintraege seit letztem Chat holen
            hours_since_chat = max(1, self._last_user_activity_minutes / 60.0)
            # Cap bei 24h — aelter ist nicht relevanter
            lookup_hours = min(int(hours_since_chat) + 1, 24)

            cutoff = time.time() - (lookup_hours * 3600)
            recent_entries = [
                e for e in journal.entries
                if e.get("timestamp", 0) > cutoff
            ]

            if not recent_entries:
                return 0.0

            # Basis-Score aus Anzahl (mehr Eintraege = mehr passiert)
            count = len(recent_entries)
            if count <= 1:
                base = 0.15
            elif count <= 3:
                base = 0.3
            elif count <= 6:
                base = 0.5
            else:
                base = 0.65

            # Tag-Boost: wichtige Tags erhoehen Relevanz
            important_tags = {"promise", "reminder", "birthday", "important", "todo", "deadline"}
            has_important = False
            for entry in recent_entries:
                entry_tags = {t.lower() for t in entry.get("tags", [])}
                if entry_tags & important_tags:
                    has_important = True
                    break

            if has_important:
                base = min(1.0, base + 0.3)

            # Zeit-Decay: je laenger Creator weg ist UND Eintraege da sind, desto relevanter
            # (YourAI "sammelt" Dinge die sie erzaehlen will)
            if self._last_user_activity_minutes > 120 and count >= 2:
                base = min(1.0, base + 0.1)

            return round(min(1.0, base), 3)

        except Exception as e:
            log("SUBCONSCIOUS", f"Relevance calc failed: {e}", Fore.YELLOW)
            return 0.0

    def _get_diary_snippet(self) -> Optional[str]:
        """Returns recent diary entries for the thought generator."""
        try:
            from episodic import journal
            recent = journal.get_recent(hours=6, max_entries=5)
            if recent and len(recent) > 10:
                return recent[:500]  # Cap at 500 characters
            return None
        except Exception:
            return None

    # ─── Event Log ──────────────────────────────────────────────

    def _log_event(self, event_type: str, detail: str) -> None:
        """Returns the internal event log for dashboard/status views."""
        self._event_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": event_type,
            "detail": detail,
        })
        while len(self._event_log) > self._max_log_entries:
            self._event_log.pop(0)

    def _persist_status(self) -> None:
        """Writes status to a JSON file for cross-process IPC read by the dashboard."""
        try:
            data = self.status()
            tmp = _STATUS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, _STATUS_FILE)
        except Exception:
            pass  # Non-critical — Dashboard zeigt halt alten Status

    # ─── Status / Dashboard API ─────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Returns complete status for the dashboard API and /subconscious command."""
        uptime_min = (time.time() - self._started_at) / 60.0 if self._started_at else 0

        last_tick = None
        if self._last_tick_result:
            r = self._last_tick_result
            last_tick = {
                "d20": r.d20_roll,
                "d20_effect": r.chaos_context.get("d20_effect"),
                "trigger_chance": r.trigger_chance,
                "roll": r.roll,
                "should_act": r.should_act,
                "action_type": r.action_type,
                "flavor": r.chaos_context.get("thought_flavor"),
                "thought_type": r.chaos_context.get("thought_type"),
                "target_session_id": r.chaos_context.get("target_session_id"),
                "phase": r.chaos_context.get("temporal_phase"),
                "activity": r.chaos_context.get("activity_multiplier"),
                "youtube_action_chance": r.chaos_context.get("youtube_action_chance"),
                "youtube_day_allowed": r.chaos_context.get("youtube_day_allowed"),
                "youtube_blocked_reason": r.chaos_context.get("youtube_blocked_reason"),
            }

        self._sync_youtube_day()
        return {
            "running": self.is_running,
            "uptime_minutes": round(uptime_min, 1),
            "ticks": self._tick_count,
            "triggers": self._trigger_count,
            "thoughts_generated": self._thoughts_generated,
            "dms_sent": self._dms_sent,
            "errors": self._errors,
            "boredom": round(self._current_boredom, 3),
            "relevance": round(self._calculate_relevance(), 3),
            "last_user_activity_minutes": round(self._last_user_activity_minutes, 1),
            "target_session_id": self._current_target_session_id,
            "last_thought_type": self._last_thought_type,
            "category_cooldowns": self._category_last_sent,
            "actions_remaining": self._engine.actions_remaining_today,
            "daily_limit": self._engine._daily_limit,
            "last_thought": self._last_thought,
            "last_dm_time": (
                datetime.fromtimestamp(self._last_dm_time).strftime("%H:%M:%S")
                if self._last_dm_time else None
            ),
            "last_own_action_time": (
                datetime.fromtimestamp(self._last_own_action_time).strftime("%H:%M:%S")
                if self._last_own_action_time else None
            ),
            "youtube_sessions_today": self._youtube_sessions_today,
            "youtube_daily_limit": self._youtube_daily_limit,
            "youtube_remaining": self._youtube_remaining_today,
            "last_youtube_time": (
                datetime.fromtimestamp(self._last_youtube_time).strftime("%H:%M:%S")
                if self._last_youtube_time else None
            ),
            "last_youtube_result": self._last_youtube_result,
            "last_youtube_error": self._last_youtube_error,
            "last_youtube_url": self._last_youtube_url,
            "instagram_sessions_today": self._instagram_sessions_today,
            "instagram_daily_limit": self._instagram_daily_limit,
            "instagram_remaining": self._instagram_remaining_today,
            "last_instagram_time": (
                datetime.fromtimestamp(self._last_instagram_time).strftime("%H:%M:%S")
                if self._last_instagram_time else None
            ),
            "last_instagram_result": self._last_instagram_result,
            "last_instagram_error": self._last_instagram_error,
            "last_instagram_url": self._last_instagram_url,
            "last_tick": last_tick,
            "event_log": self._event_log[-10:],
            "sleep_blocked": self._is_sleep_time()[0],
        }

    def status_text(self) -> str:
        """Returns formatted status text for the Discord /subconscious command."""
        s = self.status()

        if not s["running"]:
            return "Subconscious: Offline"

        lines = [
            "**YOURAI SUBCONSCIOUS STATUS**",
            f"Uptime: {s['uptime_minutes']:.0f} min",
            f"Ticks: {s['ticks']} (Triggers: {s['triggers']})",
            f"Gedanken: {s['thoughts_generated']}",
            f"DMs gesendet: {s['dms_sent']}",
            f"Fehler: {s['errors']}",
            f"Boredom: {s['boredom']:.0%}",
            f"Inaktiv: {s['last_user_activity_minutes']:.0f} min ({s.get('target_session_id') or 'kein Ziel'})",
            f"Aktionen: {s['daily_limit'] - s['actions_remaining']}/{s['daily_limit']}",
            f"YouTube: {s['youtube_sessions_today']}/{s['youtube_daily_limit']} ({s.get('last_youtube_result') or 'noch nichts'})",
            f"Instagram: {s['instagram_sessions_today']}/{s['instagram_daily_limit']} ({s.get('last_instagram_result') or 'noch nichts'})",
        ]

        if s["last_tick"]:
            t = s["last_tick"]
            lines.append(f"\n**Letzter Tick:**")
            lines.append(f"  D20: {t['d20']} ({t['d20_effect']})")
            lines.append(f"  Chance: {t['trigger_chance']:.4%}")
            lines.append(f"  Flavor: {t['flavor']} | Typ: {t.get('thought_type')}")
            lines.append(f"  Phase: {t['phase']}")

        if s["last_thought"]:
            lines.append(f"\n**Letzter Gedanke:**")
            lines.append(f'  "{s["last_thought"][:150]}"')

        return "\n".join(lines)

    # ─── Entropy Feed ───────────────────────────────────────────

    def feed_entropy(self, data: str) -> None:
        """Externe Entropy fuettern (z.B. bei Chat-Nachrichten)."""
        self._engine.add_entropy(data)

    def __repr__(self) -> str:
        """
        Builds the developer-facing representation for this object.
        
        Returns:
            str: The representation string.
        """
        state = "RUNNING" if self.is_running else "STOPPED"
        return (
            f"<SubconsciousLoop [{state}] "
            f"ticks={self._tick_count} "
            f"triggers={self._trigger_count} "
            f"dms={self._dms_sent}>"
        )


# ══════════════════════════════════════════════════════════════════
# Singleton Instance
# ══════════════════════════════════════════════════════════════════

subconscious = SubconsciousLoop()


# ══════════════════════════════════════════════════════════════════
# Standalone Test (ohne Discord)
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    # Standalone test: nur ChaosEngine, kein config/Discord noetig
    from yourai_chaos_engine import YourAIChaosEngine

    print("=" * 60)
    print("  YOURAI SUBCONSCIOUS — Dry Run (Engine only)")
    print("=" * 60)

    engine = YourAIChaosEngine(daily_limit=3)

    scenarios = [
        {"boredom": 0.3, "relevance": 0.0, "chat_ago": 60,  "mood": "neutral",  "label": "1h Stille"},
        {"boredom": 0.45, "relevance": 0.0, "chat_ago": 120, "mood": "neutral", "label": "2h Stille"},
        {"boredom": 0.6, "relevance": 0.0, "chat_ago": 180, "mood": "neutral",  "label": "3h Stille"},
        {"boredom": 0.75, "relevance": 0.0, "chat_ago": 300, "mood": "bored",   "label": "5h Stille"},
        {"boredom": 0.9, "relevance": 0.0, "chat_ago": 480, "mood": "lonely",   "label": "8h Stille"},
    ]

    for s in scenarios:
        result = engine.tick(
            boredom_score=s["boredom"],
            relevance_score=s["relevance"],
            last_chat_minutes_ago=s["chat_ago"],
            mood=s["mood"],
        )

        act_str = f"JA -> {result.action_type}" if result.should_act else "NEIN"
        print(f"\n--- {s['label']} (boredom={s['boredom']:.2f}) ---")
        print(f"  D20:       {result.d20_roll} ({result.chaos_context['d20_effect']})")
        print(f"  Chance:    {result.trigger_chance:.4%}  Roll: {result.roll:.4f}")
        print(f"  Act?       {act_str}")
        print(f"  Flavor:    {result.chaos_context['thought_flavor']}")
        print(f"  Remaining: {engine.actions_remaining_today}/{engine._daily_limit}")

    print(f"\n{engine}")
