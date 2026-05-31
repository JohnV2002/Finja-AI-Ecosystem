"""
YourAI Autonomy Guard
====================
Autonomy and coherence guard that checks whether user requests conflict with YourAI's stated positions.

Main Responsibilities:
- Evaluate user requests against YourAI's recent context and preferences.
- Return deterministic CLEAR or CHALLENGED guard outcomes.
- Maintain guard logs for dashboard and slash-command inspection.

Side Effects:
- Calls local or OpenRouter LLM providers for guard reasoning.
- Writes in-memory guard log entries and dashboard telemetry.
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
        last_n: Number of entries to show (0 = all entries)

    Returns:
        Formatted log string
    """
    if not AUTONOMY_GUARD_LOG:
        return "🛡️ Guard Log ist leer. Noch keine Checks durchgeführt."

    entries = AUTONOMY_GUARD_LOG if last_n <= 0 else AUTONOMY_GUARD_LOG[-last_n:]
    result = f"🛡️ **AUTONOMY GUARD LOG** ({len(entries)} entries):\n\n"

    for e in entries:
        icon = _LOG_ICONS.get(e["type"], "•")
        result += f"[{e['timestamp']}] {icon} **{e['type']}**: {e['content']}\n"

    return result


def clear_guard_log() -> None:
    """Clears the guard log."""
    AUTONOMY_GUARD_LOG.clear()


# ==========================================
# COHERENCE CHECK NODE
# ==========================================

class _NoopDebug:
    """Provide no-op debug methods when no dashboard debug object is passed."""

    def __getattr__(self, name):
        """Return a no-op callable for any debug method."""
        return lambda *a, **kw: None


def _guard_result(warning: str | None = None) -> Dict[str, Any]:
    """Build a standard guard node result."""
    return {"coherence_warning": warning, "guard_halted": False}


def _has_guard_context(state: Dict[str, Any]) -> bool:
    """Return True when the guard has enough context to inspect."""
    return bool(state.get("memories") or state.get("diary_context") or state.get("history"))


def _build_guard_context(state: Dict[str, Any]) -> str:
    """Build compact context text for the coherence check."""
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
    return "\n\n".join(parts)


def _build_guard_prompt(context: str, question: str) -> str:
    """Build the user prompt sent to the guard model."""
    return f"""YOURAI'S CONTEXT:
{context}

USER'S CURRENT MESSAGE:
{question}"""


def _try_openrouter_guard(user_prompt: str, debug: Any) -> tuple[str | None, str | None]:
    """Try the OpenRouter guard tier and return response/model on success."""
    if not USE_OPENROUTER:
        return None, None
    used_model = OPENROUTER_MODEL_COHERENCE
    try:
        t0 = time.time()
        _log_guard("REASONING", f"☁️ OpenRouter: {used_model}")
        res, _, _ = call_openrouter(
            system_prompt=PROMPT_COHERENCE_CHECK,
            user_message=user_prompt,
            model=used_model,
            temperature=0,
            max_tokens=GUARD_MAX_TOKENS,
        )
        if not res or not res.strip():
            raise YourAIEmptyResponseError(model=used_model, node="autonomy_guard")
        ms = int((time.time() - t0) * 1000)
        debug.llm_response("autonomy_guard", res, model=used_model, duration_ms=ms)
        _log_guard("REASONING", f"☁️ Response ({ms}ms)")
        return res, used_model
    except YourAIEmptyResponseError:
        _log_guard("ERROR", "☁️ Empty response -> local fallback")
        return None, None
    except Exception as e:
        _log_guard("ERROR", f"☁️ {e} -> local fallback")
        return None, None


def _call_local_guard(user_prompt: str, debug: Any) -> tuple[str, str]:
    """Run the local guard fallback tier."""
    used_model = MODEL_COHERENCE
    try:
        t1 = time.time()
        _log_guard("REASONING", f"🖥️ Local: {used_model}")
        llm = create_thinking_llm(used_model, LLM_HOST_STD, temperature=0, keep_alive="0m")
        res = str(llm.invoke([
            SystemMessage(content=PROMPT_COHERENCE_CHECK),
            HumanMessage(content=user_prompt),
        ]).content).strip()
        if not res:
            raise YourAIEmptyResponseError(model=used_model, node="autonomy_guard")
        ms = int((time.time() - t1) * 1000)
        debug.llm_response("autonomy_guard", res, model=used_model, duration_ms=ms)
        _log_guard("REASONING", f"🖥️ Response ({ms}ms)")
        return res, used_model
    except YourAIEmptyResponseError:
        raise
    except Exception as e:
        raise YourAIGuardError("Local fallback failed", cause=e, tier="local")


def _run_guard_llm(user_prompt: str, debug: Any) -> tuple[str, str, int]:
    """Run the configured guard tiers and return response, model, and total duration."""
    t0 = time.time()
    res, used_model = _try_openrouter_guard(user_prompt, debug)
    if res is None:
        res, used_model = _call_local_guard(user_prompt, debug)
    return res, used_model or "?", int((time.time() - t0) * 1000)


def _parse_guard_response(res: str, used_model: str) -> dict:
    """Parse the guard model JSON response."""
    json_data = _extract_json(res)
    if json_data is None:
        raise YourAILLMParseError(
            model=used_model,
            expected="JSON with 'verdict' key",
            raw_preview=res[:200],
            module="autonomy_guard",
        )
    return json_data


def _challenged_result(json_data: dict, debug: Any) -> Dict[str, Any]:
    """Handle a CHALLENGED guard verdict."""
    yourai_pos = json_data.get("yourai_position", "?")
    user_pos = json_data.get("user_position", "?")
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
    debug.info("autonomy_guard", "🛡️ CHALLENGED", f"YourAI: {yourai_pos}\nUser: {user_pos}\n{reasoning}")
    debug.node_end("autonomy_guard")
    return _guard_result(warning)


def _clear_result(total_ms: int, used_model: str, debug: Any) -> Dict[str, Any]:
    """Handle a CLEAR guard verdict."""
    _log_guard("CLEAR", f"No conflict ({total_ms}ms, {used_model})")
    log("AUTONOMY", f"✅ CLEAR ({total_ms}ms)", Fore.GREEN)
    debug.node_end("autonomy_guard")
    return _guard_result()


def _guard_error_result(error: Exception, debug: Any) -> Dict[str, Any]:
    """Convert guard exceptions into a non-halting guard result."""
    if isinstance(error, YourAIEmptyResponseError):
        _log_guard("ERROR", "Empty response from both tiers")
        debug.error("autonomy_guard", str(error), exception=error)
        log_exception("AUTONOMY", error)
        return _guard_result("⚠️ Autonomy Check: No response — ask if unsure!")

    err = error if isinstance(error, (YourAIGuardError, YourAILLMParseError)) else YourAIUnexpectedError(cause=error, module="autonomy_guard")
    msg = str(getattr(err, "cause", err))
    _log_guard("ERROR", f"Error: {msg}")
    debug.error("autonomy_guard", msg, exception=err)
    log_exception("AUTONOMY", err)
    if "timeout" in msg.lower() or "524" in msg:
        return _guard_result("⚠️ Autonomy Guard Timeout — ask if unsure!")
    return _guard_result("⚠️ Autonomy Check Error — ask if unsure!")


def coherence_check_node(state, debug: Any = None) -> Dict[str, Any]:
    """
    Run the autonomy coherence guard and return a non-halting warning result.

    Returns:
        {"coherence_warning": str|None, "guard_halted": False}
    """
    debug = debug or _NoopDebug()

    if not USE_COHERENCE_CHECK:
        _log_guard("CHECK", "Guard disabled (USE_COHERENCE_CHECK=False)")
        return _guard_result()

    if not _has_guard_context(state):
        _log_guard("CHECK", "No context - skip")
        return _guard_result()

    question = state["question"]
    _log_guard("CHECK", f"Checking: '{question[:80]}'")
    debug.node_start("autonomy_guard", model=OPENROUTER_MODEL_COHERENCE, input_data=question[:100])

    context = _build_guard_context(state)
    _log_guard("REASONING", f"Context: {len(context)} characters")
    user_prompt = _build_guard_prompt(context, question)

    try:
        res, used_model, total_ms = _run_guard_llm(user_prompt, debug)
        json_data = _parse_guard_response(res, used_model)
        verdict = (json_data.get("verdict") or "").upper().strip()
        if verdict == "CHALLENGED":
            return _challenged_result(json_data, debug)
        return _clear_result(total_ms, used_model, debug)
    except Exception as e:
        return _guard_error_result(e, debug)
