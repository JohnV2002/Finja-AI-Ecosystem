"""
YourAI Style Analyzer
====================
Builds and stores per-user writing-style summaries.

Main Responsibilities:
- Collect lightweight realtime style signals.
- Trigger snapshot analysis at configured intervals.
- Merge and expose user style profiles.

Side Effects:
- Reads and writes style profile JSON files.
- May call an LLM for snapshot analysis.
- Writes style error logs.
"""
import json
import os
import re
import threading
import time
import unicodedata
from collections import deque
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError
from config import OPENROUTER_MODEL_STYLE, call_openrouter as _call_openrouter

_BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STYLES_DIR = os.path.join(_BASE, "docker_data", "user_styles")

SNAPSHOT_MODEL = OPENROUTER_MODEL_STYLE
EARLY_SNAPSHOT_COUNTS = (10, 20, 30, 40, 70, 100)
FIRST_SNAPSHOT = EARLY_SNAPSHOT_COUNTS[0]   # First quick impression
INTENSIVE_UNTIL = EARLY_SNAPSHOT_COUNTS[-1] # Learn quickly until this many messages
LONG_TERM_EVERY = 100 # Then keep costs low and refine slowly
SNAPSHOT_OUTPUT_TOKENS = 850
STYLE_WINDOW_MAX = 150 # Hard cap so long-term snapshots cannot explode
MSG_BUFFER_MAX = STYLE_WINDOW_MAX # Messages kept per user for snapshot context

# Per-user state (in-memory, resets on restart — fine, re-triggers at msg #10)
_counters: dict[str, int] = {}
_counter_deletes: set[str] = set()
_buffers:  dict[str, deque] = {}   # uuid → deque of last N message strings
_errors:   dict[str, str] = {}     # uuid → last error (surfaced to YourAI via style context)
_realtime: dict[str, dict] = {}    # uuid -> latest local style summary
_lock = threading.Lock()


def _log_style_error(message: str, cause: Optional[Exception] = None) -> YourAIToolExecutionError:
    """Handle log style error helper behavior."""
    err = YourAIToolExecutionError(
        message,
        tool_name="style_analyzer",
        cause=cause,
    )
    log_exception("STYLE", err)
    return err


def _read_json_file(path: str, fallback):
    """Handle read json file helper behavior."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log_style_error(f"Style JSON could not be read: {path}", e)
        return fallback


def _write_json_atomic(path: str, data, *, indent: int | None = None) -> None:
    """Handle write json atomic helper behavior."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)


def _clip_context_text(value, limit: int = 180) -> str:
    """Handle clip context text helper behavior."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


# ── Realtime Signals (no LLM) ────────────────────────────────────────────────

_SLANG_WORDS = {
    "bruh", "ngl", "lowkey", "highkey", "deadass", "istg", "imo", "irl",
    "tbh", "smh", "oof", "rip", "gg", "fr", "nocap", "slay", "fam",
    "based", "cope", "ratio", "sus", "cringe", "bussin", "sheesh",
}

_KAOMOJI_PATTERNS = [
    r"\(╯[°□]+°\）╯",           # table flip
    r"\(╥﹏╥\)",                  # crying kaomoji
    r"\(◕‿◕\)",                  # happy kaomoji
    r"\(´[•·][ωω][•·]`\)",       # soft kaomoji
    r"[≥≤][._][≥≤]",             # ≥.≤
    r"[>＞][._][<＜]",   # >_< and fullwidth
    r"[oO][wW][oO]",             # OwO
    r"[uU][wW][uU]",             # UwU
    r";[.][;.]",                 # ;.; ;.;
    r"[T][_][T]",                # T_T
    r"[>]\^[<]",                 # >^<
    r"\^\^",                     # ^^
    r"-[_]+-",                   # -_-
    r"[=][_][=]",                # =_=
    r"[oO][_][oO]",              # o_o
    r":[Pp\(\)DdOo3]",           # ASCII faces :) :D :( :P :3 :o
    r"[xX][Dd]",                 # xD XD
    r";\)",                      # ;)
    r":['][\(]",                 # :'(
]

_SOFT_DISMISSAL_PATTERNS = [
    r"\bja\s+ja\b",
    r"\bjaja\b",
    r"\bpasst\s+schon\b",
    r"\bschon\s+gut\b",
    r"\balles\s+gut\b",
    r"\bist\s+gut\b",
    r"\begal\b",
    r"\bwhatever\b",
]

_HESITATION_PATTERNS = [
    r"\bhm+\b",
    r"\bhmm+\b",
    r"\behm+\b",
    r"\buhm+\b",
    r"\bnaja\b",
    r"\bwell\b",
]

_CONTACT_PING_PATTERNS = [
    r"\bhii+\b",
    r"\bhi+\b",
    r"\bhey+\b",
    r"\bgo+d\s+morning\b",
    r"\bguten\s+morgen\b",
    r"\bmorgen\b",
]

_ACTION_CODE_RE = re.compile(r"\*[^*\n]{1,48}\*")
_TABLE_FLIP_RE = re.compile(r"(┻━┻|╯[^\n]{0,12}╯|table\s*flip|throws?\s+table)", re.IGNORECASE)
_SOFT_DISTRESS_RE = re.compile(r"(;[.;]|T_T|:'\(|╥|﹏|😭|🥲|ㅠㅠ)")


def _has_any_pattern(patterns: list[str], text: str) -> bool:
    """Handle has any pattern helper behavior."""
    return any(bool(re.search(pattern, text)) for pattern in patterns)


def extract_realtime_signals(text: str) -> dict:
    """Per-message feature extraction. ~5µs, no model needed."""
    words     = text.split()
    chars     = len(text)
    tl        = text.lower()
    emojis    = sum(1 for c in text if unicodedata.category(c) in ("So", "Cs", "Co"))

    # Caps: words ≥2 chars that are fully uppercase alpha
    cap_words   = [w for w in words if len(w) >= 2 and w.isupper() and w.isalpha()]
    caps_ratio  = round(len(cap_words) / max(len(words), 1), 2)

    # Internet slang (word-boundary safe)
    tl_words    = {re.sub(r"[^\w]", "", w) for w in tl.split()}
    has_slang   = bool(tl_words & _SLANG_WORDS)
    has_soft_dismissal = _has_any_pattern(_SOFT_DISMISSAL_PATTERNS, tl)
    has_hesitation = _has_any_pattern(_HESITATION_PATTERNS, tl)
    has_contact_ping = _has_any_pattern(_CONTACT_PING_PATTERNS, tl)

    return {
        # ── existing ──────────────────────────────────────────────────────────
        "has_colon3":         bool(re.search(r":3", text)),
        "emoji_density":      round(emojis / max(len(words), 1), 2),
        "length_bucket":      "short" if chars < 60 else "medium" if chars < 200 else "long",
        "has_laughter":       bool(re.search(
                                  r"\b(haha+|lol+|lmao+|hihi|hehe+|kekw|lmfao|hahaha)\b", tl)),
        "lowercase_start":    bool(text) and text[0].islower(),
        "question_count":     text.count("?"),
        "ellipsis":           bool(re.search(r"\.\.\.|…", text)),
        # ── new ───────────────────────────────────────────────────────────────
        "has_kaomoji":        any(bool(re.search(p, text)) for p in _KAOMOJI_PATTERNS),
        "has_uwu":            bool(re.search(r"\b(uwu|owo|UwU|OwO)\b", text)),
        "caps_ratio":         caps_ratio,
        "has_repeated_chars": bool(re.search(r"(.)\1{2,}", text)),   # noooo whyyy !!!
        "has_multi_exclaim":  bool(re.search(r"!{2,}", text)),
        "has_multi_question": bool(re.search(r"\?{2,}", text)),
        "has_internet_slang": has_slang,
        "has_action_code":    bool(_ACTION_CODE_RE.search(text)),
        "has_table_flip":     bool(_TABLE_FLIP_RE.search(text)),
        "has_soft_distress":  bool(_SOFT_DISTRESS_RE.search(text)),
        "has_soft_dismissal": has_soft_dismissal,
        "has_hesitation":     has_hesitation,
        "has_contact_ping":   has_contact_ping,
    }


# ── LLM Snapshot ─────────────────────────────────────────────────────────────

def _signal_score(signals: dict) -> int:
    """Tiny local mood-energy score for trend estimation."""
    score = 0
    if signals.get("has_colon3"):        score += 1
    if signals.get("has_laughter"):      score += 2
    if signals.get("emoji_density", 0) >= 0.3: score += 1
    if signals.get("length_bucket") == "short": score += 1
    if signals.get("question_count", 0) >= 2:   score += 1
    if signals.get("ellipsis"):          score -= 1
    # new
    if signals.get("has_uwu"):           score += 1
    if signals.get("has_kaomoji"):       score += 1
    if signals.get("caps_ratio", 0) >= 0.25:    score += 2   # CAPS = high energy or frustration
    if signals.get("has_repeated_chars"):        score += 1   # nooooo = amplified emotion
    if signals.get("has_multi_exclaim"):         score += 1
    if signals.get("has_multi_question"):        score -= 1   # ??? = confusion / frustration
    if signals.get("has_table_flip"):            score += 1   # theatrical frustration
    if signals.get("has_action_code"):           score += 1
    if signals.get("has_soft_distress"):         score -= 2
    if signals.get("has_soft_dismissal"):        score -= 1
    if signals.get("has_hesitation"):            score -= 1
    if signals.get("has_contact_ping"):          score += 1
    return score


def _labels_from_signals(signals: dict) -> list[str]:
    """Handle labels from signals helper behavior."""
    labels: list[str] = []
    # length
    if signals.get("length_bucket") == "short":   labels.append("short_msgs")
    elif signals.get("length_bucket") == "long":  labels.append("long_msgs")
    # emojis
    if signals.get("emoji_density", 0) >= 0.3:    labels.append("many_emojis")
    elif signals.get("emoji_density", 0) == 0:    labels.append("few_emojis")
    # text markers
    if signals.get("has_colon3"):          labels.append("uses_:3")
    if signals.get("has_laughter"):        labels.append("laughs_often")
    if signals.get("lowercase_start"):     labels.append("casual")
    if signals.get("ellipsis"):            labels.append("ellipsis_heavy")
    # new markers
    if signals.get("has_kaomoji"):         labels.append("kaomoji_user")
    if signals.get("has_uwu"):             labels.append("uwu_user")
    if signals.get("caps_ratio", 0) >= 0.25:      labels.append("caps_outbursts")
    if signals.get("has_repeated_chars"):  labels.append("repeated_chars")
    if signals.get("has_multi_exclaim"):   labels.append("multi_exclaim")
    if signals.get("has_multi_question"):  labels.append("multi_question")
    if signals.get("has_internet_slang"):  labels.append("internet_slang")
    if signals.get("has_action_code"):     labels.append("action_code")
    if signals.get("has_table_flip"):      labels.append("table_flip")
    if signals.get("has_soft_distress"):   labels.append("soft_distress")
    if signals.get("has_soft_dismissal"):  labels.append("soft_dismissal")
    if signals.get("has_hesitation"):      labels.append("hesitation")
    if signals.get("has_contact_ping"):    labels.append("contact_ping")
    # energy summary
    score = _signal_score(signals)
    if score >= 3:    labels.append("high_energy")
    elif score <= -1: labels.append("low_energy")
    return labels


def _trend_from_scores(scores: list[int]) -> tuple[str, str]:
    """Handle trend from scores helper behavior."""
    if len(scores) < 4:
        return "stable", "->"
    recent = sum(scores[-3:]) / min(3, len(scores))
    previous = sum(scores[-6:-3]) / max(1, len(scores[-6:-3]))
    delta = recent - previous
    spread = max(scores[-6:]) - min(scores[-6:])
    if spread >= 5:
        return "volatile", "<>"
    if delta >= 1.0:
        return "rising", "^"
    if delta <= -1.0:
        return "falling", "v"
    return "stable", "->"


def _mood_from_score(score: float, signals: dict) -> str:
    """Handle mood from score helper behavior."""
    if signals.get("has_table_flip"):
        return "playful_frustrated"
    if signals.get("has_soft_distress") and signals.get("has_contact_ping"):
        return "sad_contact"
    if signals.get("has_soft_distress") and score >= 1:
        return "sad_high_energy"
    if signals.get("has_soft_dismissal") and signals.get("ellipsis"):
        return "guarded"
    if signals.get("has_hesitation") and signals.get("ellipsis"):
        return "uncertain"
    if signals.get("caps_ratio", 0) >= 0.4 and score >= 2:
        return "excited"   # CAPS + high energy = hype
    if signals.get("caps_ratio", 0) >= 0.4 and score < 1:
        return "frustrated"  # CAPS + low energy = frustration
    if score >= 4:
        return "excited"
    if score >= 2:
        return "happy"
    if score <= -1:
        return "tired"
    if signals.get("has_multi_question") and signals.get("question_count", 0) >= 3:
        return "frustrated"
    if signals.get("question_count", 0) >= 2:
        return "curious"
    return "neutral"


def _energy_from_score(score: float, signals: dict) -> str:
    """Handle energy from score helper behavior."""
    if (
        signals.get("has_table_flip")
        or (signals.get("has_soft_distress") and signals.get("has_contact_ping"))
        or (signals.get("has_multi_exclaim") and signals.get("has_multi_question"))
    ):
        return "spiky"
    if score >= 3:
        return "high"
    if score <= -1:
        return "low"
    return "medium"


_SNAPSHOT_SYSTEM = """\
You are YourAI's companion-style reader. Analyze how this user communicates so YourAI can understand, adapt, and respond with care. Do NOT mimic quirks blindly.

Goal: infer the user's emotional writing language, subtext, energy, volatility, and likely response needs. This is not clinical diagnosis. Avoid medical labels unless the user explicitly says them. Prefer nuanced companion labels such as sad_high_energy, happy_soft, annoyed_playful, tired_attached, frustrated_still_joking, curious_impatient, guarded, overwhelmed_soft.

If a previous analysis is provided, treat it as the user's baseline. Refine it with the new messages: keep stable traits, add new signals, and correct only when the new messages clearly contradict the baseline.

READ SUBTEXT, NOT ONLY TOKENS:
  ":3"                 -> warmth/play OR softening criticism OR forced smile after hesitation
  "XD" / "xD"          -> real laughter OR tension release after frustration
  "..."                -> trailing thought, tiredness, held-back irritation, sadness, or careful wording
  "ja ja danke..."     -> often not gratitude; can mean guarded, annoyed, hurt, tired, or politely ending topic
  "passt schon..."     -> can mean okay OR please stop / I am overloaded
  "Gooood morning ;.;" -> contact-seeking + soft distress; sad but still has energy
  "hm" / "hm..."       -> processing, skepticism, low engagement, or quiet discomfort
  "???"                -> confusion, disbelief, or escalating frustration
  "!!!"                -> excitement, urgency, or comedic overstatement
  CAPS                 -> intensity: hype OR frustration; use surrounding tone
  repeated chars       -> emotional amplification ("noooo", "yesss", "goooood")
  Kaomoji/emotes       -> emotional shorthand, often playful but meaningful
  "(╯°□°)╯︵ ┻━┻"       -> theatrical frustration, usually partly comic
  "*throws table*"     -> action-code / stage direction; read as performed emotion, not literal
  "-_-" / "=_="        -> deadpan, mild annoyance, tiredness
  ";.;" / "T_T"        -> soft sadness, disappointment, or half-joking pain

Predict how YourAI should write next:
  - If the user is volatile, be warm and grounded, not too intense.
  - If the user is sad_high_energy, acknowledge softly and keep momentum.
  - If the user is annoyed_playful, allow humor but do not clown over the frustration.
  - If the user is guarded, be brief, concrete, and do not over-question.
  - If the user uses humor as a buffer, respect the real issue underneath.

OUTPUT: ONLY valid compact JSON. No markdown fences, no explanation.
{
  "mood": "<nuanced short label, e.g. happy_soft|sad_high_energy|annoyed_playful|tired_attached|guarded|neutral>",
  "energy": "<low|medium|high|spiky>",
  "trend": "<stable|rising|falling|volatile>",
  "volatile": <true|false>,
  "signals": "<comma-separated labels; invent useful ones when needed: soft_distress,soft_dismissal,humor_buffer,contact_ping,action_code,table_flip,ellipsis_heavy,dry_humor,ironic,high_energy,low_energy,guarded,rambling,curious_impatient>",
  "subtext": "<one concise sentence: what the user likely means beyond literal words>",
  "baseline": "<one concise sentence: stable user communication trait YourAI should remember>",
  "response_tuning": "<one concise sentence: how YourAI should answer right now>",
  "prediction": "<one concise sentence: likely mood shift or risk in the next replies>",
  "note": "<one concise sentence: notable pattern or correction to previous baseline>",
  "compact": "<Mood=X/Energy=Y[↑↓→↕] | signal1,signal2 | response hint>"
}

Trend arrows: ↑=rising ↓=falling →=stable ↕=volatile"""

_SNAPSHOT_USER_TEMPLATE = """\
Previous analysis:
{previous_analysis}

Recent messages (newest last):
{messages}"""


def _run_snapshot(
    user_uuid: str,
    messages: list[str],
    snapshot_count: int,
    window_target: int,
) -> None:
    """Calls LLM, merges with history, saves JSON. Runs in background thread."""
    os.makedirs(_STYLES_DIR, exist_ok=True)
    path = os.path.join(_STYLES_DIR, f"{user_uuid}.json")

    old: dict = {}
    history: list[dict] = []
    if os.path.exists(path):
        try:
            old = _read_json_file(path, {})
            if old.get("merged_into"):
                old = {}
            history = old.get("history", [])[-4:]
        except Exception as e:
            _log_style_error(f"Old style snapshot could not be read: {user_uuid}", e)
            old = {}
            history = []

    previous_analysis = "(none yet)"
    if old:
        previous_analysis = json.dumps({
            "mood": old.get("mood"),
            "energy": old.get("energy"),
            "trend": old.get("trend"),
            "volatile": old.get("volatile"),
            "signals": old.get("signals"),
            "subtext": old.get("subtext"),
            "baseline": old.get("baseline"),
            "response_tuning": old.get("response_tuning"),
            "prediction": old.get("prediction"),
            "note": old.get("note"),
            "compact": old.get("compact"),
            "history": old.get("history", [])[-4:],
        }, ensure_ascii=False)

    try:
        msg_block = "\n".join(f"- {m[:250]}" for m in messages[-window_target:])
        user_msg = _SNAPSHOT_USER_TEMPLATE.format(
            previous_analysis=previous_analysis,
            messages=msg_block,
        )
        raw, _, _ = _call_openrouter(
            system_prompt=_SNAPSHOT_SYSTEM,
            user_message=user_msg,
            model=SNAPSHOT_MODEL,
            temperature=0.2,
            max_tokens=SNAPSHOT_OUTPUT_TOKENS,
        )
    except Exception as e:
        err = YourAIToolExecutionError(
            f"Stil-Snapshot fehlgeschlagen: {e}",
            tool_name="style_analyzer",
            cause=e,
        )
        log_exception("STYLE", err)
        with _lock:
            _errors[user_uuid] = "Stilanalyse: Snapshot fehlgeschlagen"
        return

    # Strip possible markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        err = YourAIToolExecutionError(
            f"Stil-Snapshot JSON parse error: {raw[:80]}",
            tool_name="style_analyzer",
        )
        log_exception("STYLE", err)
        with _lock:
            _errors[user_uuid] = f"Style analysis: LLM response is not parseable"
        return

    data.setdefault("mood", "neutral")
    data.setdefault("energy", "medium")
    data.setdefault("trend", "stable")
    data.setdefault("volatile", False)
    data.setdefault("signals", "")
    data.setdefault("subtext", "")
    data.setdefault("baseline", "")
    data.setdefault("response_tuning", "")
    data.setdefault("prediction", "")
    data.setdefault("note", "")
    data.setdefault(
        "compact",
        f"Mood={data.get('mood')}/Energy={data.get('energy')} | {data.get('signals') or 'plain'}",
    )

    history.append({
        "mood":  data.get("mood"),
        "energy": data.get("energy"),
        "trend": data.get("trend"),
        "volatile": data.get("volatile"),
        "at":    time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    data["user_uuid"]      = user_uuid
    data["snapshot_at"]    = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["msg_count"]      = snapshot_count
    data["window_target"]  = window_target
    data["window_messages"] = len(messages[-window_target:])
    data["history"]        = history

    _write_json_atomic(path, data, indent=2)

    # Snapshot succeeded → clear any previous error for this user
    with _lock:
        _errors.pop(user_uuid, None)

    log("STYLE", f"📊 Snapshot: {user_uuid[:14]}… → {data.get('compact', '?')}", Fore.CYAN)


def _snapshot_bg(
    user_uuid: str,
    messages: list[str],
    snapshot_count: int,
    window_target: int,
) -> None:
    """Handle snapshot bg helper behavior."""
    threading.Thread(
        target=_run_snapshot,
        args=(user_uuid, list(messages), snapshot_count, window_target),
        daemon=True,
    ).start()


# ── Public API ────────────────────────────────────────────────────────────────

_COUNTER_FILE = os.path.join(_STYLES_DIR, "_counters.json")
_REALTIME_FILE = os.path.join(_STYLES_DIR, "_realtime.json")


def _restore_counter(user_uuid: str) -> int:
    """Loads msg_count from counter file (survives brain restarts)."""
    # Try dedicated counter file first (always persisted)
    if os.path.exists(_COUNTER_FILE):
        try:
            data = _read_json_file(_COUNTER_FILE, {})
            if user_uuid in data:
                return int(data[user_uuid] or 0)
        except Exception as e:
            _log_style_error(f"Counter could not be restored: {user_uuid}", e)
    # Fallback: old snapshot-based counter
    path = os.path.join(_STYLES_DIR, f"{user_uuid}.json")
    if os.path.exists(path):
        try:
            data = _read_json_file(path, {})
            if data.get("merged_into"):
                return 0
            return int(data.get("msg_count") or 0)
        except Exception as e:
            _log_style_error(f"Snapshot-Counter could not be restored: {user_uuid}", e)
    return 0


def _persist_counters() -> None:
    """Saves all counters to disk so they survive restarts."""
    try:
        os.makedirs(_STYLES_DIR, exist_ok=True)
        existing = {}
        if os.path.exists(_COUNTER_FILE):
            try:
                existing = _read_json_file(_COUNTER_FILE, {})
            except Exception as e:
                _log_style_error("Counter file could not be read", e)
                existing = {}
        with _lock:
            data = dict(existing)
            for key in _counter_deletes:
                data.pop(key, None)
            data.update(_counters)
            _counter_deletes.clear()
        _write_json_atomic(_COUNTER_FILE, data)
    except Exception as e:
        _log_style_error("Counter file could not be saved", e)


def _load_realtime_all() -> dict:
    """Handle load realtime all helper behavior."""
    if os.path.exists(_REALTIME_FILE):
        try:
            return _read_json_file(_REALTIME_FILE, {})
        except Exception as e:
            _log_style_error("Realtime style file could not be read", e)
            return {}
    return {}


def _persist_realtime() -> None:
    """Handle persist realtime helper behavior."""
    try:
        os.makedirs(_STYLES_DIR, exist_ok=True)
        with _lock:
            data = dict(_realtime)
        _write_json_atomic(_REALTIME_FILE, data, indent=2)
    except Exception as e:
        _log_style_error("Realtime style file could not be saved", e)


def _mark_profile_merged(source_path: str, source_id: str, target_id: str) -> None:
    """Handle mark profile merged helper behavior."""
    if not os.path.exists(source_path):
        return
    try:
        data = _read_json_file(source_path, {})
        if not isinstance(data, dict):
            data = {}
        if data.get("merged_into") == target_id:
            return
        data.setdefault("user_uuid", source_id)
        data["merged_into"] = target_id
        data["merged_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write_json_atomic(source_path, data, indent=2)
    except Exception as e:
        _log_style_error(f"Style profile could not be marked as merged: {source_id} -> {target_id}", e)


def merge_style_profile(source_id: str, target_id: str) -> None:
    """
    Move lightweight style state from an old device/platform id into the
    canonical account id. Snapshot JSON is preserved as an archive unless the
    target has no snapshot yet.
    """
    source_id = str(source_id or "").strip()
    target_id = str(target_id or "").strip()
    if not source_id or not target_id or source_id == target_id:
        return

    os.makedirs(_STYLES_DIR, exist_ok=True)
    source_count = _restore_counter(source_id)
    target_count = _restore_counter(target_id)

    with _lock:
        if not _realtime:
            _realtime.update(_load_realtime_all())

        source_rt = _realtime.pop(source_id, None)
        target_rt = _realtime.get(target_id)
        if source_rt and (
            not target_rt
            or int(source_rt.get("msg_count") or 0) > int(target_rt.get("msg_count") or 0)
        ):
            merged_rt = dict(source_rt)
            merged_rt["user_uuid"] = target_id
            merged_rt["source_merged_from"] = source_id
            merged_rt["msg_count"] = max(
                int(merged_rt.get("msg_count") or 0),
                source_count + target_count,
            )
            _realtime[target_id] = merged_rt

        if source_count:
            _counters[target_id] = max(
                int(_counters.get(target_id) or target_count or 0),
                int(target_count or 0) + int(source_count or 0),
            )
            _counters.pop(source_id, None)
            _counter_deletes.add(source_id)

    source_path = os.path.join(_STYLES_DIR, f"{source_id}.json")
    target_path = os.path.join(_STYLES_DIR, f"{target_id}.json")
    if os.path.exists(source_path) and not os.path.exists(target_path):
        try:
            data = _read_json_file(source_path, {})
            if not isinstance(data, dict):
                data = {}
            data.pop("merged_into", None)
            data.pop("merged_at", None)
            data["user_uuid"] = target_id
            data["source_merged_from"] = source_id
            _write_json_atomic(target_path, data, indent=2)
        except Exception as e:
            _log_style_error(f"Style profile could not be copied: {source_id} -> {target_id}", e)

    _mark_profile_merged(source_path, source_id, target_id)

    _persist_realtime()
    _persist_counters()


def _update_realtime_summary(user_uuid: str, signals: dict, count: int) -> dict:
    """Handle update realtime summary helper behavior."""
    with _lock:
        if not _realtime:
            _realtime.update(_load_realtime_all())
        old = _realtime.get(user_uuid, {})
        scores = list(old.get("scores", []))[-11:]
        score = _signal_score(signals)
        scores.append(score)
        trend, arrow = _trend_from_scores(scores)
        avg = sum(scores[-6:]) / min(6, len(scores))
        labels = _labels_from_signals(signals)
        mood = _mood_from_score(avg, signals)
        energy = _energy_from_score(avg, signals)
        compact = f"Mood={mood}/Energy={energy}[{arrow}] | {','.join(labels[:5]) or 'plain'} | {trend}"
        summary = {
            "user_uuid": user_uuid,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "msg_count": count,
            "mood": mood,
            "energy": energy,
            "trend": trend,
            "arrow": arrow,
            "signals": labels,
            "score": score,
            "scores": scores,
            "compact": compact,
            "next_snapshot_in": _next_snapshot_in(count),
        }
        _realtime[user_uuid] = summary
    _persist_realtime()
    return summary


def _next_snapshot_in(count: int) -> int:
    """Handle next snapshot in helper behavior."""
    next_count = _next_snapshot_count(count)
    return max(0, next_count - count)


def _next_snapshot_count(count: int) -> int:
    """Handle next snapshot count helper behavior."""
    for target in EARLY_SNAPSHOT_COUNTS:
        if count < target:
            return target
    steps = ((count - INTENSIVE_UNTIL) // LONG_TERM_EVERY) + 1
    return INTENSIVE_UNTIL + steps * LONG_TERM_EVERY


def _previous_snapshot_count(count: int) -> int:
    """Handle previous snapshot count helper behavior."""
    previous = 0
    for target in EARLY_SNAPSHOT_COUNTS:
        if count <= target:
            return previous
        previous = target
    steps = ((count - INTENSIVE_UNTIL - 1) // LONG_TERM_EVERY)
    return INTENSIVE_UNTIL + steps * LONG_TERM_EVERY


def _snapshot_window_size(count: int) -> int:
    """Handle snapshot window size helper behavior."""
    previous_count = _previous_snapshot_count(count)
    gap = count - previous_count if previous_count else count
    return min(STYLE_WINDOW_MAX, max(FIRST_SNAPSHOT, gap))


def _should_snapshot(count: int) -> bool:
    """Handle should snapshot helper behavior."""
    if count in EARLY_SNAPSHOT_COUNTS:
        return True
    if count > INTENSIVE_UNTIL:
        return (count - INTENSIVE_UNTIL) % LONG_TERM_EVERY == 0
    return False


def track_message(user_uuid: str, text: str) -> dict:
    """
    Call after every user message.
    Extracts realtime signals, buffers message, triggers snapshot if needed.
    Returns realtime signals dict.
    """
    if not user_uuid:
        return {}

    signals = extract_realtime_signals(text)

    with _lock:
        if user_uuid not in _counters:
            _counters[user_uuid] = _restore_counter(user_uuid)
        count = _counters[user_uuid] + 1
        _counters[user_uuid] = count

        if user_uuid not in _buffers:
            _buffers[user_uuid] = deque(maxlen=MSG_BUFFER_MAX)
        _buffers[user_uuid].append(text)
        snapshot_msgs = list(_buffers[user_uuid])

    _update_realtime_summary(user_uuid, signals, count)

    # Persist counters to disk every 3 messages (survives restarts)
    if count % 3 == 0:
        _persist_counters()

    trigger = _should_snapshot(count)

    if trigger:
        log("STYLE", f"🔍 Snapshot #{count} for {user_uuid[:14]}…", Fore.CYAN)
        window_target = _snapshot_window_size(count)
        snapshot_msgs = snapshot_msgs[-window_target:]
        _persist_counters()
        _snapshot_bg(user_uuid, snapshot_msgs, count, window_target)

    return signals


def get_style_context(user_uuid: str) -> str:
    """
    Returns compact style one-liner for system prompt injection.
    Includes error info if the last snapshot failed — YourAI sees her own errors.
    Empty string if no snapshot exists yet and no errors occurred.
    """
    if not user_uuid:
        return ""

    parts: list[str] = []

    # Realtime style is updated every message, so YourAI does not wait for
    # the slower LLM snapshot before adapting to user energy.
    summary = get_style_summary(user_uuid)
    snapshot = summary.get("snapshot") or {}
    snapshot_compact = str(snapshot.get("compact") or "").strip()
    if snapshot_compact:
        parts.append(f"User-Basis: {snapshot_compact}")
    for key, label in (
        ("baseline", "Baseline"),
        ("subtext", "Subtext"),
        ("response_tuning", "YourAI-Tuning"),
        ("prediction", "Prediction"),
    ):
        value = _clip_context_text(snapshot.get(key), 180)
        if value:
            parts.append(f"{label}: {value}")

    realtime = summary.get("realtime") or {}
    realtime_compact = str(realtime.get("compact") or "").strip()
    if realtime_compact:
        parts.append(f"Live-Trend: {realtime_compact}")

    # Style data (if available)
    path = os.path.join(_STYLES_DIR, f"{user_uuid}.json")
    if os.path.exists(path):
        try:
            data = _read_json_file(path, {})
            compact = data.get("compact", "").strip()
            if compact and not data.get("merged_into") and not snapshot_compact and not realtime_compact:
                parts.append(f"User-Stil: {compact}")
        except Exception as e:
            _log_style_error(f"Style context could not be read: {user_uuid}", e)

    # Error state (if last snapshot failed — YourAI should know)
    with _lock:
        error = _errors.get(user_uuid)
    if error:
        parts.append(f"⚠️ {error}")

    if not parts:
        return ""
    return f"[{' | '.join(parts)}]"


def get_style_summary(user_uuid: str) -> dict:
    """Return realtime + snapshot style data for dashboard/profile UI."""
    if not user_uuid:
        return {"available": False}

    realtime_all = _load_realtime_all()
    realtime = dict(_realtime.get(user_uuid) or realtime_all.get(user_uuid) or {})
    if realtime:
        realtime.pop("scores", None)

    snapshot = None
    merged_into = None
    path = os.path.join(_STYLES_DIR, f"{user_uuid}.json")
    if os.path.exists(path):
        try:
            data = _read_json_file(path, {})
            merged_into = data.get("merged_into")
            if not merged_into:
                snapshot = {
                    "snapshot_at": data.get("snapshot_at"),
                    "msg_count": data.get("msg_count"),
                    "mood": data.get("mood"),
                    "energy": data.get("energy"),
                    "trend": data.get("trend"),
                    "volatile": data.get("volatile"),
                    "signals": data.get("signals"),
                    "compact": data.get("compact"),
                    "subtext": data.get("subtext"),
                    "baseline": data.get("baseline"),
                    "response_tuning": data.get("response_tuning"),
                    "prediction": data.get("prediction"),
                    "note": data.get("note"),
                    "window_target": data.get("window_target"),
                    "window_messages": data.get("window_messages"),
                }
        except Exception as e:
            _log_style_error(f"Style summary could not be read: {user_uuid}", e)
            snapshot = None

    count = _counters.get(user_uuid)
    if count is None:
        count = _restore_counter(user_uuid)
    count = max(
        int(count or 0),
        int((realtime or {}).get("msg_count") or 0),
        int((snapshot or {}).get("msg_count") or 0),
    )

    with _lock:
        error = _errors.get(user_uuid)

    return {
        "available": bool(realtime or snapshot),
        "user_uuid": user_uuid,
        "msg_count": count,
        "next_snapshot_in": _next_snapshot_in(int(count or 0)),
        "realtime": realtime,
        "snapshot": snapshot,
        "error": error,
        "merged_into": merged_into,
    }
