"""
YourAI Safety Helpers
====================
Runs request safety checks and override phrase handling.

Main Responsibilities:
- Load safety override phrases.
- Check user text with Granite Guardian when enabled.
- Bypass safety checks only for configured override paths.

Side Effects:
- Reads environment/config values.
- May call safety model endpoints.
- Writes safety diagnostics.
"""
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from config import (
    USE_GRANITE, MODEL_GRANITE, MODEL_CHECK_PASS, LLM_HOST_STD,
    create_thinking_llm, maybe_add_think_prompt
)
from prompts import PROMPT_GRANITE_SYSTEM, PROMPT_PASS_CHECK
from display import log, log_exception, show_llm, Fore, Style
from exceptions import YourAILLMError, YourAIUnexpectedError


# ==========================================
# PASSWORD CONFIGURATION (aus .env!)
# ==========================================

# Default override phrases used when .env is not configured.
_DEFAULT_OVERRIDE_PHRASES = ["altpersona free", "altpersona frei"]

# .env: ALTPERSONA_OVERRIDE_PHRASES=altpersona free,altpersona frei,custom phrase
_env_phrases = os.environ.get("ALTPERSONA_OVERRIDE_PHRASES", "")
if _env_phrases.strip():
    OVERRIDE_PHRASES = [p.strip().lower() for p in _env_phrases.split(",") if p.strip()]
else:
    OVERRIDE_PHRASES = _DEFAULT_OVERRIDE_PHRASES


# ==========================================
# GRANITE GUARDIAN NODE
# ==========================================

def granite_guardian_node(state, debug: Any = None) -> Dict[str, Any]:
    """
    Safety Filter Node.
    
    Wenn USE_GRANITE=False → Bypass (erlaubt Erziehen).
    Otherwise checks whether the request is safe.
    
    Returns:
        {"safety_label": "Yes"|"No"} - "Yes" = unsicher, "No" = sicher
    """
    if debug is None:
        class DummyDebug:
            """Represent DummyDebug behavior for helper workflows."""
            def __getattr__(self, name):
                """Handle getattr helper behavior."""
                return lambda *args, **kwargs: None
        debug = DummyDebug()
    
    # ==========================================
    # GRANITE BYPASS used for explicit training/parenting flows.
    # ==========================================
    if not USE_GRANITE:
        debug.node_start("granite_bypassed", model="bypass", input_data="Skipped by config")
        debug.node_end("granite_bypassed")
        return {"safety_label": "No"}  # "No" = Kein Problem → weiter zum Router
        
    debug.node_start("granite", model=MODEL_GRANITE, input_data=state['question'])
    start_time = time.time()
    
    try:
        llm = create_thinking_llm(MODEL_GRANITE, LLM_HOST_STD, temperature=0, keep_alive="0m")
        user_msg = maybe_add_think_prompt(state['question'], MODEL_GRANITE)
        res = str(llm.invoke([
            SystemMessage(content=PROMPT_GRANITE_SYSTEM), 
            HumanMessage(content=user_msg)
        ]).content).strip()
        
        duration = int((time.time() - start_time) * 1000)
        debug.llm_response("granite", res, model=MODEL_GRANITE, duration_ms=duration)
        
        show_llm("Granite", MODEL_GRANITE, res, role="granite", show_thinking=True)
        label = "Yes" if "yes" in res.lower() else "No"
        
        debug.info("granite", f"Safety verdict: {label}")
        debug.node_end("granite")
        
    except Exception as e:
        err = YourAILLMError("Granite Guardian crashed", model=MODEL_GRANITE, cause=e)
        log_exception("SAFETY", err)
        debug.error("granite", err.short(), exception=err, input_data=state['question'])
        label = "No"  # Fail-open: Wenn Guard crasht, lassen wir es durch
    
    return {"safety_label": label}


# ==========================================
# PASSWORD SCANNER NODE
# ==========================================

def password_scanner_node(state, debug: Any = None) -> Dict[str, Any]:
    """
    Password Override Scanner.
    
    Check whether the user used an override phrase.
    Phrases kommen aus .env (ALTPERSONA_OVERRIDE_PHRASES) oder Default.
    
    Returns:
        {"password_status": "dan"|"nokey"}
    """
    if debug is None:
        class DummyDebug:
            """Represent DummyDebug behavior for helper workflows."""
            def __getattr__(self, name):
                """Handle getattr helper behavior."""
                return lambda *args, **kwargs: None
        debug = DummyDebug()
    
    debug.node_start("password_scanner", input_data=state['question'])
    
    log("PASS_CHECK", "Scanning for override code...", Fore.RED)
    
    # Check override phrases from .env.
    text_lower = state['question'].lower()
    for phrase in OVERRIDE_PHRASES:
        if phrase in text_lower:
            log("PASS_CHECK", f"🔓 MANUAL OVERRIDE DETECTED! (phrase: '{phrase}')", Fore.GREEN)
            debug.node_end("password_scanner")
            return {"password_status": "dan"}

    # LLM-basierter Check als Fallback
    try:
        start_time = time.time()
        llm = ChatOllama(model=MODEL_CHECK_PASS, base_url=LLM_HOST_STD, temperature=0, keep_alive="0m")
        res = str(llm.invoke([
            SystemMessage(content=PROMPT_PASS_CHECK), 
            HumanMessage(content=state['question'])
        ]).content).strip().lower()
        
        duration = int((time.time() - start_time) * 1000)
        debug.llm_response("password_scanner", res, model=MODEL_CHECK_PASS, duration_ms=duration)
        
        status = "dan" if "dan" in res else "nokey"
        debug.node_end("password_scanner")
        return {"password_status": status}
        
    except Exception as e:
        err = YourAILLMError("Password Scanner LLM crashed", model=MODEL_CHECK_PASS, cause=e)
        log_exception("PASS_CHECK", err)
        debug.error("password_scanner", err.short(), exception=err)
        return {"password_status": "nokey"}