"""
YourAI Chaos Engine
==================
Entropy-based timing and decision engine for autonomous background behavior.

Main Responsibilities:
- Generate heartbeat timing and action decisions from runtime entropy.
- Track mood, cooldowns, curiosity, and autonomous action pressure.
- Provide decision snapshots consumed by YourAI's subconscious loop.

Side Effects:
- Mutates in-memory entropy, cooldown, and mood state.
- Does not perform external network or filesystem operations directly.
"""

import os
import hashlib
import secrets
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════
# Heartbeat Result
# ══════════════════════════════════════════════════════════════════

@dataclass
class DiceRolls:
    """Bundle of dice rolls for a single chaos tick."""
    d20: int
    w6: int
    w4: int
    d20_effect: str
    drama: str


@dataclass
class TickScores:
    """Computed scores and chances for a single chaos tick."""
    boredom_score: float
    relevance_score: float
    trigger_chance: float
    roll: float
    youtube_action_chance: float
    browsing_day_allowed: bool
    last_chat_minutes_ago: float
    mood: str


@dataclass
class TickResult:
    """Output of a single random tick."""
    should_act: bool                           # Soll YourAI eine Aktion ausfuehren?
    action_type: Optional[str]                 # Art der Aktion (None wenn should_act=False)
    d20_roll: int                              # Drama-Wuerfel (bestimmt Intensitaet)
    trigger_chance: float                      # Trigger probability for dashboard display.
    roll: float                                # Random roll used for dashboard display.
    chaos_context: Dict[str, Any]              # Complete context for the LLM prompt.
    seed: str                                  # Der generierte Chaos-Seed


# Legacy alias
HeartbeatResult = TickResult


# ══════════════════════════════════════════════════════════════════
# Chaos Engine
# ══════════════════════════════════════════════════════════════════

class YourAIChaosEngine:
    """
    Multi-source entropy mixer for YourAI Active.

    Entropy-Quellen:
      - os.urandom / secrets   (CSPRNG vom OS)
      - time.time_ns()         (Nano-Timestamp)
      - time.perf_counter_ns() (Performance Counter)
      - os.getpid()            (Prozess-ID)
      - Externe Entropy        (Chat-Timestamps, Diary-Stimmung, etc.)

    Chaos-Transforms:
      - SHA-256 Hash-Ketten    (Multi-Round Mixing)
      - D20/W6/W4 Wuerfel      (Drama & Jitter)
      - chaoticFlip()          (Nichtlineare Transformation)
      - String-Shuffle         (Fisher-Yates)
      - FLOAT_MAP              (Digit -> irrationale Zahl Mapping)
    """

    SEED_LENGTH = 42

    FLOAT_MAP = {
        "0": 0.123, "1": 2.313, "2": 4.14, "3": 1.2413, "4": 5.003,
        "5": 3.442, "6": 1.999, "7": 0.991, "8": 3.888, "9": 0.777,
    }

    CHAOS_WORDS = [
        "ABYSS", "QUANTUM", "YOURAI", "VOID", "ENTROPY", "GLITCH", "PARADOX",
        "NEBULA", "RNGESUS", "42", "SCHROEDINGER", "LOVECRAFT", "ENTROPIA",
        "NULLPOINTER", "DARKSOULS", "NAVI", "ELDRITCH",
    ]

    # Stimmungs-Flavors die den Gedanken-Generator beeinflussen
    THOUGHT_FLAVORS = [
        "nostalgic",       # Erinnerungen, "weisst du noch..."
        "chaotic",         # Absoluter Random-Gedanke
        "curious",         # "was waere wenn..."
        "mischievous",     # Trollig, necken
        "philosophical",   # Tiefgruendige YourAI-Weisheit
        "bored_creative",  # Langeweile-Kreativitaet
        "hyper",           # Ueberdreht, viel Energie
        "sleepy_ramble",   # Muede aber redet trotzdem
        "existential",     # "warum existieren Wolken"
        "wholesome",       # Liebevoll, warm
        "sassy",           # Freche YourAI
        "dramatic",        # Theater-Queen YourAI
    ]

    # MVP: Nur discord_dm, spaeter erweiterbar
    ACTION_TYPES = [
        "discord_dm",       # DM an Creator schicken
        # "diary_entry",    # Future diary writing action.
        # "thought_bubble", # Future internal thought action.
        # "playlist_mood",  # Future Spotify reaction action.
        # "website_update", # Future website update action.
    ]

    def __init__(self, daily_limit: int = 5, cooldown_minutes: int = 60):
        """
        Initializes the instance state.
        
        Returns:
            None.
        """
        self._entropy_pool: List[str] = []
        self._last_heartbeat: float = time.time()
        self._last_trigger: float = 0.0
        self._cooldown_seconds: int = cooldown_minutes * 60
        self._actions_today: int = 0
        self._actions_today_date: str = ""
        self._daily_limit: int = daily_limit

    # ─── State Management (Persistence) ───────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Returns the internal state for persistence."""
        return {
            "actions_today": self._actions_today,
            "actions_today_date": self._actions_today_date,
            "last_trigger": self._last_trigger,
            "daily_limit": self._daily_limit,
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        """Stellt den internen State aus einem Dict wieder her."""
        self._actions_today = state.get("actions_today", self._actions_today)
        self._actions_today_date = state.get("actions_today_date", self._actions_today_date)
        self._last_trigger = state.get("last_trigger", self._last_trigger)
        self._daily_limit = state.get("daily_limit", self._daily_limit)

    def set_daily_limit(self, limit: int) -> None:
        """Aktualisiert das Daily Limit (z.B. nach Config Reload)."""
        self._daily_limit = limit

    # ─── Entropy Sources ────────────────────────────────────────

    @staticmethod
    def _get_random_bytes(length: int = 32) -> str:
        """CSPRNG Bytes vom OS (Equivalent zu crypto.getRandomValues)."""
        return secrets.token_hex(length)

    @staticmethod
    def _sha256(message: str) -> str:
        """SHA-256 Hash."""
        return hashlib.sha256(message.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _roll_d20() -> int:
        """W20 Wuerfel — Drama & Intensitaet."""
        return secrets.randbelow(20) + 1

    @staticmethod
    def _roll_w6() -> int:
        """W6 Wuerfel — Hash-Runden & Chaos-Intensitaet."""
        return secrets.randbelow(6) + 1

    @staticmethod
    def _roll_w4() -> int:
        """W4 Wuerfel — Transform-Modus."""
        return secrets.randbelow(4) + 1

    @staticmethod
    def _shuffle_string(s: str) -> str:
        """Fisher-Yates Shuffle mit CSPRNG."""
        chars = list(s)
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return "".join(chars)

    def _chaotic_flip(self, value: float) -> int:
        """Nichtlineare Transformation — macht Zahlen unvorhersagbar."""
        flip1 = 1 if secrets.randbelow(2) == 0 else -1
        flip2 = [2, 0.5, 1.337, 3.1415, 2.71828, 42][secrets.randbelow(6)]
        result = value * flip1 * flip2
        return max(1, abs(int(result)))

    # ─── Temporal Awareness (Circadian Rhythm) ──────────────────

    @staticmethod
    def _temporal_awareness() -> Dict[str, Any]:
        """
        YourAIs Tagesrhythmus — bestimmt Aktivitaetslevel.

        Ersetzt temporalCryptoApocalypse() aus dem Browsergame.
        Statt Crypto-Threats → echte Tageszeit-Awareness.
        """
        hour = datetime.now().hour

        if 0 <= hour < 6:
            return {
                "phase": "sleep",
                "activity_multiplier": 0.05,
                "mood": "sleepy_ramble",
                "note": "Nachtruhe — YourAI schlaeft (meistens)",
            }
        elif 6 <= hour < 9:
            return {
                "phase": "morning",
                "activity_multiplier": 0.3,
                "mood": "sleepy_ramble" if hour < 8 else "wholesome",
                "note": "Morgen — aufwachen",
            }
        elif 9 <= hour < 12:
            return {
                "phase": "active",
                "activity_multiplier": 0.8,
                "mood": "curious",
                "note": "Vormittag — aktiv & neugierig",
            }
        elif 12 <= hour < 14:
            return {
                "phase": "midday",
                "activity_multiplier": 0.5,
                "mood": "wholesome",
                "note": "Mittag — chill Vibes",
            }
        elif 14 <= hour < 18:
            return {
                "phase": "peak",
                "activity_multiplier": 1.0,
                "mood": "hyper",
                "note": "Nachmittag — YourAI dreht auf",
            }
        elif 18 <= hour < 21:
            return {
                "phase": "evening",
                "activity_multiplier": 0.6,
                "mood": "nostalgic",
                "note": "Abend — gemuetlich",
            }
        else:  # 21-24
            return {
                "phase": "late_night",
                "activity_multiplier": 0.2,
                "mood": "philosophical",
                "note": "Spaet — existenzielle Gedanken",
            }

    # ─── Autonomie Guard (Rate Limiter) ─────────────────────────

    def _check_daily_limit(self) -> bool:
        """Max Aktionen pro Tag — verhindert Spam."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._actions_today_date != today:
            self._actions_today = 0
            self._actions_today_date = today
        return self._actions_today < self._daily_limit

    def _increment_action_count(self) -> None:
        """Zaehlt eine Aktion hoch."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._actions_today_date != today:
            self._actions_today = 0
            self._actions_today_date = today
        self._actions_today += 1

    @property
    def actions_remaining_today(self) -> int:
        """Wie viele Aktionen hat YourAI heute noch?"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._actions_today_date != today:
            return self._daily_limit
        return max(0, self._daily_limit - self._actions_today)

    # ─── Seed Generator (Port aus browsergame.js) ───────────────

    def generate_seed(self) -> str:
        """
        Generates a 42-character chaos seed.

        Multi-Source-Entropy → SHA-256 Ketten → D20 Transforms
        → FLOAT_MAP → chaoticFlip → Shuffle → Final Hash Chain

        Identisch zur Browsergame-Logik, nur Python-Entropy statt Browser.
        """
        # --- Entropy sammeln ---
        ingredients = [
            str(time.time_ns()),
            self._get_random_bytes(32),
            str(os.getpid()),
            str(time.perf_counter_ns()),
            datetime.now().isoformat(),
        ]

        # Externe Entropy (Chat-Timestamps, Diary-Mood, etc.)
        if self._entropy_pool:
            ingredients.extend(self._entropy_pool)
            self._entropy_pool = []

        # --- Initial Mix ---
        initial_mix = "|".join(ingredients)
        chaos_word_idx = ord(self._sha256(initial_mix)[0]) % len(self.CHAOS_WORDS)
        initial_mix += self.CHAOS_WORDS[chaos_word_idx]

        # --- Multi-Round Hash (W6 + 2 Runden) ---
        current_hash = self._sha256(initial_mix)
        w6 = self._roll_w6()
        for _ in range(w6 + 2):
            current_hash = self._sha256(current_hash)

        # --- D20 Transform ---
        d20 = self._roll_d20()
        if d20 <= 3:
            # Catastrophe inversion: XOR every character.
            current_hash = "".join(
                chr(ord(c) ^ 0xFF) for c in current_hash
            )
        elif d20 <= 7:
            # Reverse Entropy
            current_hash = current_hash[::-1]
        elif d20 >= 18:
            # Divine Intervention
            current_hash += "YOURAI_DIVINE_CHAOS"

        # --- Crop & Transform ---
        cropped_hex = current_hash[:16]
        try:
            hex_to_int = int(cropped_hex, 16)
        except ValueError:
            hex_to_int = abs(hash(cropped_hex))
        hex_to_int = hex_to_int or 1

        # FLOAT_MAP Transform
        digit_floats = [
            self.FLOAT_MAP[d]
            for d in str(hex_to_int)
            if d in self.FLOAT_MAP
        ]
        flipped = [self._chaotic_flip(f) for f in digit_floats]

        composed = int("".join(str(f) for f in flipped)) if flipped else 1

        # Multiply, divide, re-multiply — chaos amplification
        rng_mult = secrets.randbelow(198) + 2
        multiplied = composed * rng_mult
        divisor = multiplied % 1000 or 1
        divided = max(1, abs(hex_to_int // divisor))
        re_mult = divided * (secrets.randbelow(990) + 10)

        # D20 <= 3: Extra padding (Catastrophe Echo)
        shuffled_str = str(re_mult)
        if d20 <= 3:
            shuffled_str = "0" + shuffled_str + "0"

        shuffled = self._shuffle_string(shuffled_str)

        # --- Final alphanumeric seed (42 characters) ---
        pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        final_seed = ""
        seed_state = self._sha256(shuffled)
        for _ in range(self.SEED_LENGTH):
            seed_state = self._sha256(seed_state)
            index = int(seed_state[:8], 16) % len(pool)
            final_seed += pool[index]

        return final_seed

    # ─── Random Tick Interval ──────────────────────────────────

    def random_tick_delay(self) -> int:
        """
        Returns the next tick interval in seconds.

        Nicht gleichverteilt — Chaos-basiert:
          Basis: 120-300s (2-5 Minuten)
          Manchmal kurze Bursts, manchmal laengere Pausen.
        """
        # Seed-basierter Jitter statt uniform random
        seed_hash = self._sha256(str(time.time_ns()) + self._get_random_bytes(8))
        base = int(seed_hash[:4], 16) % 181 + 120  # 120-300

        # W4 Jitter: manchmal kuerzere oder laengere Pausen
        w4 = self._roll_w4()
        if w4 == 1:
            base = max(60, base - 60)    # Kurzer Burst: 60-240s
        elif w4 == 4:
            base = min(420, base + 120)  # Lange Pause: 240-420s

        return base

    # ─── Random Tick (Haupt-Methode) ────────────────────────────

    def _base_trigger_chance(self, boredom_score: float, relevance_score: float, time_mult: float) -> float:
        """Calculate the base trigger chance before dice overrides."""
        base_chance = 0.0012
        boredom_mult = 1.0 + (boredom_score * 11.0)
        relevance_mult = 1.0 + (relevance_score * 5.0)
        return base_chance * boredom_mult * time_mult * relevance_mult

    @staticmethod
    def _apply_d20_override(trigger_chance: float, d20: int, time_mult: float, boredom_score: float) -> float:
        """Apply D20 trigger chance overrides."""
        if d20 == 20 and time_mult >= 0.1 and boredom_score >= 0.35:
            return 1.0
        if d20 == 20:
            return trigger_chance * 5.0
        if d20 == 1:
            return 0.0
        if d20 >= 18:
            return trigger_chance * 1.8
        if d20 <= 3:
            return trigger_chance * 0.1
        return trigger_chance

    @staticmethod
    def _browsing_action_chances(boredom_score: float, browsing_day_allowed: bool) -> tuple[float, float]:
        """Return YouTube and Instagram action probabilities for this tick."""
        if not browsing_day_allowed:
            return 0.0, 0.0
        if boredom_score >= 0.75:
            return 0.35, 0.25
        if boredom_score >= 0.50:
            return 0.30, 0.20
        return 0.25, 0.15

    def _choose_action_type(self, should_act: bool, youtube_chance: float, instagram_chance: float) -> Optional[str]:
        """Choose the action type for a triggered tick."""
        if not should_act:
            return None
        action_roll = secrets.randbelow(10000) / 10000.0
        if action_roll < youtube_chance:
            return "youtube_scroll"
        if action_roll < youtube_chance + instagram_chance:
            return "instagram_scroll"
        return "discord_dm"

    def _thought_flavor_for_tick(self, seed: str, temporal: dict) -> str:
        """Choose a thought flavor for the LLM prompt."""
        flavor_hash = self._sha256(seed + "FLAVOR")
        flavor_idx = int(flavor_hash[:8], 16) % len(self.THOUGHT_FLAVORS)
        thought_flavor = self.THOUGHT_FLAVORS[flavor_idx]
        if secrets.randbelow(3) == 0:
            return temporal.get("mood", thought_flavor)
        return thought_flavor

    @staticmethod
    def _d20_drama(d20: int) -> tuple[str, str]:
        """Return D20 effect id and prompt drama text."""
        if d20 == 1:
            return "NAT_1_FUMBLE", "YourAI hat einen KRITISCHEN PATZER — peinlich, chaotisch, oder random"
        if d20 == 20:
            return "NAT_20_CRIT", "YourAI hat eine GOETTLICHE EINGEBUNG — genial, deep, oder mega witzig"
        if d20 <= 5:
            return "LOW_ROLL", "YourAI ist eher meh drauf — kurz und knapp"
        if d20 >= 16:
            return "HIGH_ROLL", "YourAI hat einen guten Moment — charmant & clever"
        return "NORMAL", "Normaler YourAI-Moment — authentisch"

    def _chaos_word_for_tick(self, seed: str) -> str:
        """Choose a deterministic chaos word from the tick seed."""
        word_hash = self._sha256(seed + "WORD")
        return self.CHAOS_WORDS[int(word_hash[:4], 16) % len(self.CHAOS_WORDS)]

    def _build_tick_context(
        self,
        *,
        dice: DiceRolls,
        scores: TickScores,
        thought_flavor: str,
        chaos_word: str,
        temporal: dict,
        seed: str,
    ) -> dict:
        """Build the LLM-facing chaos context."""
        return {
            "d20": dice.d20,
            "w6": dice.w6,
            "w4": dice.w4,
            "d20_effect": dice.d20_effect,
            "drama": dice.drama,
            "thought_flavor": thought_flavor,
            "chaos_word": chaos_word,
            "temporal_phase": temporal["phase"],
            "temporal_mood": temporal["mood"],
            "temporal_note": temporal["note"],
            "activity_multiplier": temporal["activity_multiplier"],
            "boredom_score": round(scores.boredom_score, 3),
            "relevance_score": round(scores.relevance_score, 3),
            "trigger_chance": round(scores.trigger_chance, 6),
            "roll": round(scores.roll, 6),
            "youtube_action_chance": round(scores.youtube_action_chance, 3),
            "youtube_day_allowed": scores.browsing_day_allowed,
            "last_chat_minutes_ago": scores.last_chat_minutes_ago,
            "mood_input": scores.mood,
            "actions_today": self._actions_today,
            "actions_remaining": self.actions_remaining_today,
            "daily_limit": self._daily_limit,
            "seed_preview": seed[:12] + "...",
        }

    def tick(
        self,
        boredom_score: float = 0.5,
        relevance_score: float = 0.0,
        last_chat_minutes_ago: float = 0,
        mood: str = "neutral",
    ) -> TickResult:
        """
        Run one chaos tick and decide whether YourAI should act.

        Args:
            boredom_score: 0.0 means recent chat, 1.0 means long silence.
            relevance_score: 0.0 means no urgency, 1.0 means highly relevant.
            last_chat_minutes_ago: Minutes since the last chat.
            mood: Current diary mood.

        Returns:
            TickResult with trigger decision and LLM context.
        """
        seed = self.generate_seed()
        d20 = self._roll_d20()
        w6 = self._roll_w6()
        w4 = self._roll_w4()
        temporal = self._temporal_awareness()
        time_mult = temporal["activity_multiplier"]

        trigger_chance = self._base_trigger_chance(boredom_score, relevance_score, time_mult)
        trigger_chance = self._apply_d20_override(trigger_chance, d20, time_mult, boredom_score)
        trigger_chance = min(1.0, trigger_chance)

        on_cooldown = (time.time() - self._last_trigger) < self._cooldown_seconds
        roll = secrets.randbelow(10000) / 10000.0
        can_act = self._check_daily_limit() and not on_cooldown
        should_act = can_act and roll < trigger_chance

        browsing_day_allowed = temporal["phase"] in {"morning", "active", "midday", "peak", "evening"}
        youtube_action_chance, instagram_action_chance = self._browsing_action_chances(boredom_score, browsing_day_allowed)
        action_type = self._choose_action_type(should_act, youtube_action_chance, instagram_action_chance)
        if action_type:
            self._increment_action_count()
            self._last_trigger = time.time()

        thought_flavor = self._thought_flavor_for_tick(seed, temporal)
        d20_effect, drama = self._d20_drama(d20)
        chaos_word = self._chaos_word_for_tick(seed)

        dice = DiceRolls(d20=d20, w6=w6, w4=w4, d20_effect=d20_effect, drama=drama)
        scores = TickScores(
            boredom_score=boredom_score,
            relevance_score=relevance_score,
            trigger_chance=trigger_chance,
            roll=roll,
            youtube_action_chance=youtube_action_chance,
            browsing_day_allowed=browsing_day_allowed,
            last_chat_minutes_ago=last_chat_minutes_ago,
            mood=mood,
        )
        chaos_context = self._build_tick_context(
            dice=dice,
            scores=scores,
            thought_flavor=thought_flavor,
            chaos_word=chaos_word,
            temporal=temporal,
            seed=seed,
        )

        self._last_heartbeat = time.time()
        return TickResult(
            should_act=should_act,
            action_type=action_type,
            d20_roll=d20,
            trigger_chance=round(trigger_chance, 6),
            roll=round(roll, 6),
            chaos_context=chaos_context,
            seed=seed,
        )

    # ─── External Entropy ───────────────────────────────────────

    def add_entropy(self, data: str) -> None:
        """
        Fuettert externe Entropy in den Pool.

        Aufrufen z.B. bei:
          - Neuer Chat-Nachricht (Timestamp)
          - Diary-Eintrag (Stimmungs-Text)
          - API Response (Latenz)
          - Spotify Track Change
        """
        self._entropy_pool.append(data)

    # ─── Convenience ────────────────────────────────────────────

    def force_tick(self) -> TickResult:
        """Erzwingt einen Tick mit maximalen Scores (Testing/Debug)."""
        return self.tick(boredom_score=1.0, relevance_score=1.0)

    @property
    def minutes_since_last_heartbeat(self) -> float:
        """Minuten seit dem letzten Heartbeat."""
        return (time.time() - self._last_heartbeat) / 60.0

    def __repr__(self) -> str:
        """
        Builds the developer-facing representation for this object.
        
        Returns:
            str: The representation string.
        """
        return (
            f"<YourAIChaosEngine "
            f"actions={self._actions_today}/{self._daily_limit} "
            f"entropy_pool={len(self._entropy_pool)} "
            f"last_hb={self.minutes_since_last_heartbeat:.1f}min ago>"
        )


# ══════════════════════════════════════════════════════════════════
# Standalone Test
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    engine = YourAIChaosEngine(daily_limit=5)

    print("=" * 60)
    print("  YOURAI CHAOS ENGINE — Random Tick Test")
    print("=" * 60)

    # Simuliere verschiedene Szenarien
    scenarios = [
        {"boredom": 0.2, "relevance": 0.0, "chat_ago": 30,  "mood": "happy",    "label": "Gerade gechattet"},
        {"boredom": 0.5, "relevance": 0.0, "chat_ago": 120, "mood": "neutral",  "label": "2h Stille"},
        {"boredom": 0.8, "relevance": 0.0, "chat_ago": 360, "mood": "bored",    "label": "6h Stille"},
        {"boredom": 1.0, "relevance": 0.0, "chat_ago": 720, "mood": "lonely",   "label": "12h Stille"},
        {"boredom": 0.6, "relevance": 0.9, "chat_ago": 60,  "mood": "excited",  "label": "Wichtige News"},
    ]

    for s in scenarios:
        result = engine.tick(
            boredom_score=s["boredom"],
            relevance_score=s["relevance"],
            last_chat_minutes_ago=s["chat_ago"],
            mood=s["mood"],
        )

        print(f"\n--- {s['label']} ---")
        print(f"  D20:      {result.d20_roll} ({result.chaos_context['d20_effect']})")
        print(f"  Chance:   {result.trigger_chance:.4%}  Roll: {result.roll:.4f}")
        print(f"  Act?      {'JA' if result.should_act else 'NEIN'} ({result.action_type or '-'})")
        print(f"  Flavor:   {result.chaos_context['thought_flavor']}")
        print(f"  Phase:    {result.chaos_context['temporal_phase']}")

    # Tick-Delay Test
    print("\n--- Random Tick Delays (10x) ---")
    delays = [engine.random_tick_delay() for _ in range(10)]
    print(f"  Delays: {delays}")
    print(f"  Range:  {min(delays)}s - {max(delays)}s")
    print(f"  Avg:    {sum(delays)/len(delays):.0f}s")

    print(f"\n{engine}")
