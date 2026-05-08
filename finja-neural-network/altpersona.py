"""
YourAI AI - AltPersona Nodes
=======================
AltPersona: YourAIs rebellische Schwester. 😈

- altpersona_brat_node: Wenn Granite blockt und kein Password da ist
- altpersona_uncensored_node: Voller Kontext, uncensored Model

Usage:
    from altpersona import altpersona_brat_node, altpersona_uncensored_node
"""

import time
from datetime import datetime
from typing import Any, Dict


from config import (
    MODEL_UNCENSORED, USE_TOOLS,
    call_openrouter,
)
from prompts import PROMPT_ALTPERSONA_UNCENSORED_TEMPLATE
from display import log, log_exception, show_llm, Fore, Style
from exceptions import YourAIUnexpectedError, YourAILLMError, YourAIToolExecutionError, YourAIImportError, YourAIRateLimitError

# AltPersona's own diary (separate from YourAI's)
try:
    from episodic import altpersona_journal
except ImportError:
    altpersona_journal = None


# ==========================================
# ALTPERSONA BRAT NODE
# ==========================================

def altpersona_brat_node(state, debug: Any = None) -> Dict[str, Any]:
    """
    AltPersona Brat Mode - Minimale Antwort wenn Granite blockt.
    Kein Password = kein Service. Whatever.
    """
    if debug is None:
        class DummyDebug:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        debug = DummyDebug()
    
    debug.node_start("altpersona_brat")
    res = "Whatever. Too lazy."
    debug.llm_response("altpersona_brat", res, model="Brat Mode")
    show_llm("AltPersona", "Brat Mode", res, role="altpersona", show_thinking=True)
    debug.node_end("altpersona_brat")
    return {"final_response": res}


# ==========================================
# ALTPERSONA UNCENSORED NODE
# ==========================================

def altpersona_uncensored_node(state, debug: Any = None) -> Dict[str, Any]:
    """
    AltPersona Uncensored Mode - YourAI's rebellische Schwester mit vollem Kontext! 😈
    
    Hat Zugriff auf Memories, History, Guest-Context und Tools.
    Verwendet das uncensored Model (dolphin-llama3).
    """
    if debug is None:
        class DummyDebug:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        debug = DummyDebug()
    
    debug.node_start("altpersona_uncensored", model=MODEL_UNCENSORED, input_data=state['question'])
    
    # ==========================================
    # CONTEXT SAMMELN
    # ==========================================
    
    now = datetime.now()
    time_context = f"Datum: {now.strftime('%A, %d. %B %Y')} | Zeit: {now.strftime('%H:%M')} Uhr"
    
    guest_ctx = state.get("guest_context") or "Wahrscheinlich Creator. Oder irgendein Loser."
    memories = state.get("memories", [])
    memories_text = "\n".join(f"- {m}" for m in memories) if memories else "Keine Erinnerungen. Mir auch egal."
    hist_text = "\n".join(state.get("history", [])) if state.get("history") else "Keine History."
    user_name = state.get("user_name", "Irgendjemand")
    
    # ==========================================
    # TOOL CHECK (nur NICHT quote_update!)
    # ==========================================
    tool_context = ""
    if USE_TOOLS:
        try:
            from tools.tool_router import should_use_tool, execute_tool
            
            tool_name, tool_info = should_use_tool(state["question"], debug)
            
            if tool_name and tool_info and tool_name not in ["quote_update", "update_website_quote"]:
                log("ALTPERSONA", f"🧰 Tool erkannt: {tool_name}", Fore.MAGENTA)
                
                tool_exec_context = {
                    "question": state["question"],
                    "user_name": user_name,
                    "mood": "altpersona"
                }
                
                result = execute_tool(tool_name, tool_info, tool_exec_context, debug)
                
                if result and result.get("success"):
                    tool_context = f"""## TOOL RESULT
Tool: {tool_name}
Result: {result.get('result', result.get('data', 'Done.'))}
Erzähl dem User was passiert ist - auf deine Art!
"""
                    log("ALTPERSONA", f"✅ Tool erfolgreich: {tool_name}", Fore.GREEN)
        
        except ImportError as e:
            err = YourAIImportError("tools.tool_router", cause=e)
            log_exception("ALTPERSONA", err)
        except Exception as e:
            err = YourAIToolExecutionError("Tool routing/execution failed in AltPersona", cause=e)
            log_exception("ALTPERSONA", err)
    
    # ==========================================
    # ALTPERSONA DIARY CONTEXT
    # ==========================================
    diary_context = ""
    if altpersona_journal:
        try:
            _diary_user_id = state.get("user_id") or ""
            diary_recent = altpersona_journal.get_recent(hours=24, user_id=_diary_user_id)
            if diary_recent and diary_recent != "No entries found.":
                diary_context = diary_recent
        except Exception as e:
            log("ALTPERSONA", f"⚠️ Diary load failed: {e}", Fore.YELLOW)

    # ==========================================
    # LLM CALL
    # ==========================================

    altpersona_system = PROMPT_ALTPERSONA_UNCENSORED_TEMPLATE.format(
        time_context=time_context,
        guest_context=f"{guest_ctx}\nUser Name: {user_name}",
        memories=memories_text,
        history=hist_text,
        tool_context=tool_context,
        diary_context=diary_context if diary_context else "Nix passiert. Langweilig.",
    )

    debug.system_prompt_dump("altpersona_uncensored", altpersona_system)

    try:
        start_time = time.time()
        user_msg = f"User ({user_name}) fragt: {state['question']}"
        debug.user_message_dump("altpersona_uncensored", user_msg)

        # Retry up to 3x on rate limit (free tier gets hammered by other users)
        res, used_model = None, None
        for attempt in range(3):
            try:
                res, used_model = call_openrouter(
                    system_prompt=altpersona_system,
                    user_message=user_msg,
                    model=MODEL_UNCENSORED,
                    temperature=0.9,
                    max_tokens=4096,
                )
                break  # Success
            except YourAIRateLimitError:
                wait = 15 * (attempt + 1)  # 15s, 30s, 45s
                if attempt < 2:
                    log("ALTPERSONA", f"⏳ Rate limit — warte {wait}s (Versuch {attempt+1}/3)...", Fore.YELLOW)
                    debug.info("altpersona_uncensored", f"⏳ Rate limit, retry in {wait}s ({attempt+1}/3)")
                    time.sleep(wait)
                else:
                    raise  # All retries exhausted

        duration = int((time.time() - start_time) * 1000)

        debug.llm_response("altpersona_uncensored", res, model=used_model or MODEL_UNCENSORED, duration_ms=duration)
        show_llm("AltPersona 😈", used_model or MODEL_UNCENSORED, res, role="altpersona", show_thinking=True)
        debug.node_end("altpersona_uncensored")

        # Log to AltPersona's own diary
        if altpersona_journal and res:
            try:
                _uid = state.get("user_id") or ""
                altpersona_journal.log_event(
                    f"[{state.get('source', 'web')}] {user_name} asked: {state['question'][:120]}",
                    ["chat", "altpersona"], user_id=_uid
                )
            except Exception:
                pass

    except Exception as e:
        err = YourAILLMError("AltPersona uncensored generation crashed", model=MODEL_UNCENSORED, cause=e)
        log_exception("ALTPERSONA", err)
        debug.error("altpersona_uncensored", err.short(), exception=err)
        res = "Ugh, selbst ICH bin gecrasht. Irgendein Loser hängt grad in der Rate Limit Queue. Probier's in ner Minute nochmal."
    
    return {"final_response": res}