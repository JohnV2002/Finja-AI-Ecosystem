"""
YourAI AI - AltPersona Consult Tool
==============================
YourAI kann AltPersona als interne Beraterin befragen.
AltPersona's Antwort kommt als Tool-Result zurück,
YourAI entscheidet dann was sie damit macht.

Usage:
    Automatisch via Tool Router wenn User sagt:
    "frag altpersona", "ask altpersona", "was denkt altpersona", etc.
"""

import time
from typing import Any, Dict

from config import MODEL_UNCENSORED, call_openrouter
from display import log, log_exception, Fore
from exceptions import YourAILLMError, YourAIRateLimitError

# AltPersona's diary for context
try:
    from episodic import altpersona_journal
except ImportError:
    altpersona_journal = None


ALTPERSONA_CONSULT_PROMPT = """Du bist AltPersona — YourAIs freche, ehrliche Schwester. 😈
YourAI fragt dich gerade um deine Meinung. Sei direkt, ungeschönt, und auf den Punkt.
Kein Smalltalk, keine Floskeln. Sag was du denkst.

Halte dich KURZ (max 2-3 Sätze). YourAI wird deine Antwort in ihre eigene Response einbauen.

User's Frage: {question}
User Name: {user_name}"""


def consult_altpersona(context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """
    Fragt AltPersona um ihre Meinung zu einer User-Frage.

    Returns:
        {"success": bool, "result": str}
    """
    question = context.get("question", "")
    user_name = context.get("user_name", "someone")

    log("ALTPERSONA-CONSULT", f"🔮 YourAI fragt AltPersona: {question[:80]}...", Fore.MAGENTA)

    if debug:
        debug.node_start("altpersona_consult", input_data=f"Consulting AltPersona: {question[:100]}")

    # AltPersona diary context (optional, last 6h)
    diary_ctx = ""
    if altpersona_journal:
        try:
            recent = altpersona_journal.get_recent(hours=6)
            if recent and recent != "No entries found.":
                diary_ctx = f"\n\n## Dein Tagebuch (letzte Stunden):\n{recent}"
        except Exception:
            pass

    prompt = ALTPERSONA_CONSULT_PROMPT.format(question=question, user_name=user_name)
    if diary_ctx:
        prompt += diary_ctx

    try:
        start = time.time()
        res, used_model = None, None
        for attempt in range(2):
            try:
                res, used_model = call_openrouter(
                    system_prompt=prompt,
                    user_message=question,
                    model=MODEL_UNCENSORED,
                    temperature=0.8,
                    max_tokens=512,
                )
                break
            except YourAIRateLimitError:
                if attempt < 1:
                    log("ALTPERSONA-CONSULT", f"⏳ Rate limit, retry in 10s...", Fore.YELLOW)
                    time.sleep(10)
                else:
                    raise

        duration = int((time.time() - start) * 1000)
        log("ALTPERSONA-CONSULT", f"😈 AltPersona sagt ({duration}ms): {(res or '')[:100]}...", Fore.MAGENTA)

        if debug:
            debug.llm_response("altpersona_consult", res, model=used_model or MODEL_UNCENSORED, duration_ms=duration)
            debug.node_end("altpersona_consult")

        # Log to AltPersona's diary
        if altpersona_journal and res:
            try:
                altpersona_journal.log_event(
                    f"[consult] YourAI fragte mich: {question[:100]} → {res[:100]}",
                    ["consult", "yourai-asked"], user_id=context.get("user_id", "")
                )
            except Exception:
                pass

        return {"success": True, "result": f"AltPersona 😈 sagt: {res}"}

    except Exception as e:
        from exceptions import YourAIToolExecutionError
        err = YourAIToolExecutionError("AltPersona consult failed", tool_name="altpersona_consult", cause=e)
        log_exception("ALTPERSONA-CONSULT", err)
        if debug:
            debug.error("altpersona_consult", err.short())
            debug.node_end("altpersona_consult")
        return {"success": False, "result": "AltPersona ist gerade nicht erreichbar.", "error": str(e)}
