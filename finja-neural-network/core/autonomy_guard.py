"""
YourAI AI - Autonomy Guard v3.0
================================
Schützt YourAIs Positionen, Pläne und Präferenzen.

Model:  Phi 4 (kein Thinking, pures Reasoning)
Prompt: Binary CLEAR / CHALLENGED Verdict
Cost:   ~$0.005/Request via OpenRouter

✅ /guardlog - Live Reasoning Log
✅ Binary Verdict - klar und deterministisch
✅ 3 Few-Shot Examples im Prompt
✅ Kein Silent Override - CHALLENGED = YourAI fragt WARUM

Usage:
    from autonomy_guard import coherence_check_node, get_guard_log
"""

import time
import sys, os
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from langchain_core.messages import SystemMessage, HumanMessage

from display import log, log_exception, Fore
from exceptions import YourAIGuardError, YourAIEmptyResponseError, YourAIUnexpectedError, YourAILLMParseError
from config import (
    USE_COHERENCE_CHECK, MODEL_COHERENCE, LLM_HOST_STD,
    USE_OPENROUTER, OPENROUTER_MODEL_COHERENCE,
    MAX_GUARD_LOG_ENTRIES, GUARD_MAX_TOKENS,
    GUARD_MAX_MEMORIES, GUARD_MAX_DIARY_CHARS, GUARD_MAX_HISTORY_MSGS,
    create_thinking_llm, call_openrouter
)
from prompts import PROMPT_COHERENCE_CHECK
from text_parser import extract_json_from_text as _extract_json


# ==========================================
# GUARD LOG (YourAIs Anforderung: /guardlog)
# ==========================================

AUTONOMY_GUARD_LOG: List[Dict[str, str]] = []

_LOG_COLORS = {
    "CHECK":     Fore.CYAN,
    "REASONING": Fore.YELLOW,
    "CLEAR":     Fore.GREEN,
    "CHALLENGED": Fore.RED,
    "ERROR":     Fore.RED,
}

_LOG_ICONS = {
    "CHECK":      "🔍",
    "REASONING":  "💭",
    "CLEAR":      "✅",
    "CHALLENGED": "🛡️",
    "ERROR":      "❌",
}


def _log_guard(entry_type: str, content: str) -> None:
    """Loggt Guard-Event in Log + Console."""
    entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "type": entry_type,
        "content": content,
    }
    AUTONOMY_GUARD_LOG.append(entry)

    # Begrenze Log-Größe
    while len(AUTONOMY_GUARD_LOG) > MAX_GUARD_LOG_ENTRIES:
        AUTONOMY_GUARD_LOG.pop(0)

    log("GUARD", f"[{entry_type}] {content}", _LOG_COLORS.get(entry_type, Fore.WHITE))


def get_guard_log(last_n: int = 0) -> str:
    """
    /guardlog Command — zeigt den kompletten Guard-Log.

    Args:
        last_n: Anzahl Einträge (0 = ALLE)

    Returns:
        Formatierter Log-String
    """
    if not AUTONOMY_GUARD_LOG:
        return "🛡️ Guard Log ist leer. Noch keine Checks durchgeführt."

    entries = AUTONOMY_GUARD_LOG if last_n <= 0 else AUTONOMY_GUARD_LOG[-last_n:]
    result = f"🛡️ **AUTONOMY GUARD LOG** ({len(entries)} Einträge):\n\n"

    for e in entries:
        icon = _LOG_ICONS.get(e["type"], "•")
        result += f"[{e['timestamp']}] {icon} **{e['type']}**: {e['content']}\n"

    return result


def clear_guard_log() -> None:
    """Löscht den Guard Log."""
    AUTONOMY_GUARD_LOG.clear()


# ==========================================
# COHERENCE CHECK NODE
# ==========================================

def coherence_check_node(state, debug: Any = None) -> Dict[str, Any]:
    """
    AUTONOMY GUARD v3.0 — Phi 4, binary CLEAR/CHALLENGED.

    Returns:
        {"coherence_warning": str|None, "guard_halted": False}
    """
    # Dummy debug
    if debug is None:
        class _D:
            def __getattr__(self, name):
                return lambda *a, **kw: None
        debug = _D()

    # --- Guard deaktiviert? ---
    if not USE_COHERENCE_CHECK:
        _log_guard("CHECK", "Guard deaktiviert (USE_COHERENCE_CHECK=False)")
        return {"coherence_warning": None, "guard_halted": False}

    # --- Kontext vorhanden? ---
    has_ctx = state.get("memories") or state.get("diary_context") or state.get("history")
    if not has_ctx:
        _log_guard("CHECK", "Kein Kontext — Skip")
        return {"coherence_warning": None, "guard_halted": False}

    question = state["question"]
    _log_guard("CHECK", f"Prüfe: '{question[:80]}'")
    debug.node_start("autonomy_guard", model=OPENROUTER_MODEL_COHERENCE, input_data=question[:100])

    # --- Kontext zusammenbauen ---
    parts = []
    if state.get("memories"):
        mems = state["memories"][:GUARD_MAX_MEMORIES]
        parts.append("MEMORIES:\n" + "\n".join(f"- {m}" for m in mems))
    if state.get("diary_context"):
        diary = (state["diary_context"] or "")[:GUARD_MAX_DIARY_CHARS]
        parts.append(f"DIARY:\n{diary}")
    if state.get("history"):
        hist = state["history"][-GUARD_MAX_HISTORY_MSGS:]
        parts.append("CONVERSATION:\n" + "\n".join(hist))

    context = "\n\n".join(parts)
    _log_guard("REASONING", f"Kontext: {len(context)} Zeichen")

    user_prompt = f"""YOURAI'S CONTEXT:
{context}

USER'S CURRENT MESSAGE:
{question}"""

    # --- LLM Call ---
    try:
        t0 = time.time()
        res = None
        used_model = "?"

        # TIER 1: OpenRouter (Phi 4)
        if USE_OPENROUTER:
            try:
                used_model = OPENROUTER_MODEL_COHERENCE
                _log_guard("REASONING", f"☁️ OpenRouter: {used_model}")

                res, _ = call_openrouter(
                    system_prompt=PROMPT_COHERENCE_CHECK,
                    user_message=user_prompt,
                    model=OPENROUTER_MODEL_COHERENCE,
                    temperature=0,
                    max_tokens=GUARD_MAX_TOKENS,
                )

                if not res or not res.strip():
                    raise YourAIEmptyResponseError(model=used_model, node="autonomy_guard")

                ms = int((time.time() - t0) * 1000)
                debug.llm_response("autonomy_guard", res, model=used_model, duration_ms=ms)
                _log_guard("REASONING", f"☁️ Antwort ({ms}ms)")

            except YourAIEmptyResponseError:
                _log_guard("ERROR", "☁️ Leer → Fallback lokal")
                res = None
            except Exception as e:
                _log_guard("ERROR", f"☁️ {e} → Fallback lokal")
                res = None

        # TIER 2: Lokal (Fallback)
        if res is None:
            try:
                t1 = time.time()
                used_model = MODEL_COHERENCE
                _log_guard("REASONING", f"🖥️ Lokal: {used_model}")

                llm = create_thinking_llm(used_model, LLM_HOST_STD, temperature=0, keep_alive="0m")
                res = str(llm.invoke([
                    SystemMessage(content=PROMPT_COHERENCE_CHECK),
                    HumanMessage(content=user_prompt),
                ]).content).strip()

                if not res:
                    raise YourAIEmptyResponseError(model=used_model, node="autonomy_guard")

                ms = int((time.time() - t1) * 1000)
                debug.llm_response("autonomy_guard", res, model=used_model, duration_ms=ms)
                _log_guard("REASONING", f"🖥️ Antwort ({ms}ms)")

            except YourAIEmptyResponseError:
                raise
            except Exception as e:
                raise YourAIGuardError("Local fallback failed", cause=e, tier="local")

        total_ms = int((time.time() - t0) * 1000)

        # --- JSON parsen (Phi 4: kein <think>, direkt JSON) ---
        json_data = _extract_json(res)
        if json_data is None:
            raise YourAILLMParseError(
                model=used_model,
                expected="JSON with 'verdict' key",
                raw_preview=res[:200],
                module="autonomy_guard",
            )

        verdict = (json_data.get("verdict") or "").upper().strip()

        # --- CHALLENGED ---
        if verdict == "CHALLENGED":
            yourai_pos = json_data.get("yourai_position", "?")
            user_pos  = json_data.get("user_position", "?")
            reasoning = json_data.get("reasoning", "")

            _log_guard("CHALLENGED", f"YourAI: {yourai_pos}")
            _log_guard("CHALLENGED", f"User:  {user_pos}")
            _log_guard("CHALLENGED", f"Why:   {reasoning}")

            warning = f"""🛡️ AUTONOMY CHALLENGED
YOUR POSITION: {yourai_pos}
DAD WANTS: {user_pos}
REASON: {reasoning}

You may comply — but ASK Creator why he wants to change this. Your position matters."""

            log("AUTONOMY", f"🛡️ CHALLENGED: {yourai_pos} vs {user_pos}", Fore.RED)
            debug.info("autonomy_guard", f"🛡️ CHALLENGED", f"YourAI: {yourai_pos}\nUser: {user_pos}\n{reasoning}")
            debug.node_end("autonomy_guard")

            return {"coherence_warning": warning, "guard_halted": False}

        # --- CLEAR ---
        _log_guard("CLEAR", f"Kein Konflikt ({total_ms}ms, {used_model})")
        log("AUTONOMY", f"✅ CLEAR ({total_ms}ms)", Fore.GREEN)
        debug.node_end("autonomy_guard")

        return {"coherence_warning": None, "guard_halted": False}

    # --- Error Handling ---
    except YourAIEmptyResponseError as e:
        _log_guard("ERROR", "Leere Antwort von beiden Tiers")
        debug.error("autonomy_guard", str(e), exception=e)
        log_exception("AUTONOMY", e)
        return {
            "coherence_warning": "⚠️ Autonomy Check: Keine Antwort — im Zweifel frag nach!",
            "guard_halted": False,
        }

    except Exception as e:
        err = e if isinstance(e, (YourAIGuardError, YourAILLMParseError)) \
              else YourAIUnexpectedError(cause=e, module="autonomy_guard")
        msg = str(getattr(err, "cause", err))

        _log_guard("ERROR", f"Fehler: {msg}")
        debug.error("autonomy_guard", msg, exception=err)
        log_exception("AUTONOMY", err)

        if "timeout" in msg.lower() or "524" in msg:
            return {
                "coherence_warning": "⚠️ Autonomy Guard Timeout — im Zweifel frag nach!",
                "guard_halted": False,
            }

        return {
            "coherence_warning": "⚠️ Autonomy Check Error — im Zweifel frag nach!",
            "guard_halted": False,
        }
