"""
YourAI AI - Tool Router
=======================
Verwendet functiongemma um zu entscheiden welches Tool aufgerufen wird.

Usage:
    from tools.tool_router import should_use_tool, execute_tool
"""

import json
import logging
import time
from typing import Optional, Dict, Any, Tuple

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from display import log, Fore
from config import LLM_HOST_STD
from exceptions import (
    YourAIToolError,
    YourAIToolNotFoundError,
    YourAIToolExecutionError,
    YourAILLMError,
    YourAILLMTimeoutError,
    YourAILLMConnectionError,
    YourAILLMParseError,
)

logger = logging.getLogger("yourai.tools.router")

# ==========================================
# CONFIGURATION
# ==========================================

MODEL_TOOL_ROUTER = "functiongemma"  # Spezialisiert auf Function Calling
USE_TOOLS = True

# ==========================================
# TOOL DEFINITIONS
# ==========================================

AVAILABLE_TOOLS = {
    "update_website_quote": {
        "description": "Updates YourAI's 'Quote of the Day' on her website (your-domain.example.com/yourai.html)",
        "triggers": [
            "neuer spruch", "new quote", "update quote", "spruch des tages",
            "website spruch", "quote of the day", "ändere spruch", "change quote",
            "mach einen spruch", "generiere spruch", "spruch für die website",
            "thought of the day", "daily quote", "tagesspruch"
        ],
        "module": "tools.website",
        "function": "update_quote",
        "requires_generation": True,  # YourAI muss erst Content generieren
    },
    # DM Tool entfernt → ersetzt durch /dm Command + YourAIs [DM:Target] Tags
    "spotify_control": {
        "description": "Controls Spotify: shuffle, sort, skip, pause, queue (ADMIN ONLY)",
        "triggers": [
            "shuffle playlist", "shuffel playlist", "shuffle meine",
            "sort by bpm", "sortiere nach bpm", "bpm sortieren",
            "sort by energy", "chill to hype", "hype to chill",
            "skip song", "skip track", "nächstes lied", "next song", "überspring",
            "pause spotify", "pause musik", "pause music", "stop music", "musik stopp",
            "resume spotify", "weiter spotify", "play spotify", "musik weiter",
            "spotify queue", "was kommt als nächstes", "what's next", "show queue",
            "meine playlists", "show playlists", "list playlists", "welche playlists",
            "volume", "lautstärke", "lauter", "leiser",
            "nur execute", "nur von", "only songs by", "filter artist",
            "spiel meine", "play my playlist",
        ],
        "admin_only": True,  # NUR Admin darf das!
        "module": "tools.spotify_control",
        "function": "execute_spotify_command",
        "requires_generation": False,
    },
    "web_search": {
        "description": "Searches the internet via DuckDuckGo/Tor web crawler",
        "triggers": [
            "such online", "suche online", "such im internet", "suche im internet",
            "google mal", "google nach", "googel mal", "googel nach",
            "schau im internet", "schau online", "such im netz", "suche im netz",
            "search online", "search the web", "look up online", "web search",
            "was sagt das internet", "was sagt google",
            "such mal nach", "kannst du nachschauen", "kannst du nachgucken",
            "schau mal nach", "guck mal nach", "recherchiere",
        ],
        "module": "tools.web_search",
        "function": "web_search",
        "requires_generation": False,
        "extract_query": True,  # Router muss den Suchbegriff extrahieren
    },
    "paperless_search": {
        "description": "Searches Creator's document archive (Paperless-NGX)",
        "triggers": [
            "such in meinen dokumenten", "suche in meinen dokumenten",
            "such in paperless", "suche in paperless",
            "find meine", "finde meine", "finde das dokument",
            "such meine rechnung", "suche meine rechnung",
            "wo ist mein", "wo ist meine",
            "hast du mein dokument", "hast du meine rechnung",
            "search my documents", "find my document", "find my invoice",
            "paperless", "dokumentenarchiv", "dokument suchen",
            "rechnung suchen", "vertrag suchen", "brief suchen",
        ],
        "admin_only": True,
        "module": "tools.paperless",
        "function": "paperless_search",
        "requires_generation": False,
        "extract_query": True,
    },
    "home_assistant": {
        "description": "Controls smart home devices via Home Assistant (lights, switches, scenes, sensors)",
        "triggers": [
            "licht an", "licht aus", "licht einschalten", "licht ausschalten",
            "mach das licht", "mach licht", "schalte das licht",
            "turn on light", "turn off light", "lights on", "lights off",
            "smart home", "smarthome", "home assistant",
            "schalte ein", "schalte aus",
            "welche geräte", "zeig mir die geräte", "show devices",
            "heizung", "thermostat", "temperatur einstellen",
            "rollos", "rolladen", "jalousie",
            "steckdose an", "steckdose aus",
            "szene aktivieren", "activate scene",
        ],
        "admin_only": True,
        "module": "tools.home_assistant",
        "function": "execute_home_command",
        "requires_generation": False,
        "extract_query": True,
    },
}

# ==========================================
# TOOL DETECTION PROMPT
# ==========================================

PROMPT_TOOL_ROUTER = """You are a TOOL ROUTER. Your job is to detect if the user wants YourAI to use a TOOL.

## AVAILABLE TOOLS:
{tool_descriptions}

## RULES:
1. Only return a tool if the user EXPLICITLY wants to trigger it
2. Casual mentions are NOT triggers (e.g., "I like your website quote" is NOT a trigger)
3. Commands/requests ARE triggers (e.g., "make a new quote" IS a trigger)

## OUTPUT FORMAT:
If a tool should be used:
{{"tool": "tool_name", "reason": "why this tool"}}

If NO tool is needed:
{{"tool": null, "reason": "normal conversation"}}

Reply ONLY with JSON, no explanation."""


# ==========================================
# HELPER
# ==========================================

class _DummyDebug:
    """No-op debug client wenn kein Dashboard verbunden ist."""
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def _get_debug(debug: Any) -> Any:
    """Gibt den debug client zurück oder einen Dummy."""
    if debug is None:
        return _DummyDebug()
    return debug


# ==========================================
# FUNCTIONS
# ==========================================

def _build_tool_descriptions() -> str:
    """Baut die Tool-Beschreibungen für den Prompt."""
    descriptions = []
    for name, info in AVAILABLE_TOOLS.items():
        triggers = ", ".join(info["triggers"][:5])  # Max 5 Beispiele
        descriptions.append(f"- {name}: {info['description']} (triggers: {triggers})")

    result = "\n".join(descriptions)
    logger.debug("Tool descriptions built: %d tools, %d chars", len(AVAILABLE_TOOLS), len(result))
    return result


def _quick_trigger_check(text: str) -> Optional[str]:
    """
    Schneller Keyword-Check bevor wir das LLM fragen.
    Spart API calls für offensichtliche Fälle.
    Prüft auch anti_triggers: Wörter die kurz VOR dem Trigger stehen und ihn negieren.
    """
    text_lower = text.lower()
    logger.debug("Quick trigger check on %d chars: '%s'", len(text), text[:80])

    for tool_name, info in AVAILABLE_TOOLS.items():
        for trigger in info["triggers"]:
            pos = text_lower.find(trigger)
            if pos == -1:
                continue

            # Anti-Trigger Check: Schaue ob ein negierendes Wort kurz davor steht
            anti_triggers = info.get("anti_triggers", [])
            if anti_triggers:
                # Prüfe die 30 Zeichen vor dem Trigger
                prefix = text_lower[max(0, pos - 30):pos].strip()
                negated = False
                for anti in anti_triggers:
                    if prefix.endswith(anti) or f" {anti} " in f" {prefix} ":
                        logger.info("Anti-trigger '%s' negated trigger '%s' for tool %s", anti, trigger, tool_name)
                        negated = True
                        break
                if negated:
                    continue

            logger.info("Quick trigger matched: tool=%s, trigger='%s'", tool_name, trigger)
            return tool_name

    logger.debug("No quick trigger matched")
    return None


def should_use_tool(question: str, debug: Any = None) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Prüft ob ein Tool verwendet werden soll.

    Args:
        question: Die User-Frage
        debug: Dashboard debug client

    Returns:
        (tool_name, tool_info) oder (None, None)
    """
    logger.debug("should_use_tool called | USE_TOOLS=%s | question='%s'", USE_TOOLS, question[:100])

    if not USE_TOOLS:
        logger.info("Tools disabled globally (USE_TOOLS=False), skipping")
        return None, None

    debug = _get_debug(debug)

    # Quick check first
    quick_match = _quick_trigger_check(question)
    if quick_match:
        log("TOOLS", f"🔧 Quick match: {quick_match}", Fore.CYAN)
        logger.info("Tool selected via quick match: %s", quick_match)
        return quick_match, AVAILABLE_TOOLS[quick_match]

    # Wenn kein Quick Match, frag functiongemma
    # (Optional - für komplexere Fälle)
    # Für jetzt: Nur Quick Match verwenden um Latenz zu sparen
    logger.debug("No quick match, no LLM fallback configured — returning None")
    return None, None


def should_use_tool_llm(question: str, debug: Any = None) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Verwendet functiongemma für komplexe Tool-Erkennung.
    Nur aufrufen wenn quick check nicht reicht.
    """
    logger.debug("should_use_tool_llm called | model=%s | question='%s'", MODEL_TOOL_ROUTER, question[:100])

    if not USE_TOOLS:
        logger.info("Tools disabled globally (USE_TOOLS=False), skipping LLM router")
        return None, None

    debug = _get_debug(debug)
    debug.node_start("tool_router", model=MODEL_TOOL_ROUTER, input_data=question[:100])
    log("TOOLS", f"🔧 Checking tools with {MODEL_TOOL_ROUTER}...", Fore.CYAN)

    try:
        start_time = time.time()

        tool_descriptions = _build_tool_descriptions()
        prompt = PROMPT_TOOL_ROUTER.format(tool_descriptions=tool_descriptions)
        logger.debug("Tool router prompt built: %d chars, sending to %s at %s", len(prompt), MODEL_TOOL_ROUTER, LLM_HOST_STD)

        llm = ChatOllama(
            model=MODEL_TOOL_ROUTER,
            base_url=LLM_HOST_STD,
            temperature=0,
            keep_alive="0m"
        )

        res = str(llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=question)
        ]).content).strip()

        duration_ms = int((time.time() - start_time) * 1000)
        debug.llm_response("tool_router", res, model=MODEL_TOOL_ROUTER, duration_ms=duration_ms)
        log("TOOLS", f"Tool Router response ({duration_ms}ms): {res[:100]}", Fore.CYAN)
        logger.info("LLM tool router responded in %dms | raw='%s'", duration_ms, res[:120])

        # Parse JSON
        tool_name = _parse_tool_router_response(res)

        if tool_name and tool_name in AVAILABLE_TOOLS:
            log("TOOLS", f"✅ Tool selected: {tool_name}", Fore.GREEN)
            logger.info("LLM selected tool: %s", tool_name)
            debug.node_end("tool_router")
            return tool_name, AVAILABLE_TOOLS[tool_name]

        if tool_name and tool_name not in AVAILABLE_TOOLS:
            logger.warning("LLM returned unknown tool name: '%s' — ignoring", tool_name)

        logger.debug("LLM tool router decided: no tool needed")
        debug.node_end("tool_router")
        return None, None

    except YourAILLMParseError:
        # Bereits geloggt in _parse_tool_router_response, kein Tool = safe fallback
        debug.node_end("tool_router")
        return None, None

    except TimeoutError as e:
        logger.error("Tool router LLM timeout: %s", e)
        debug.error("tool_router", str(e), exception=e)
        raise YourAILLMTimeoutError(model=MODEL_TOOL_ROUTER, timeout_seconds=0, cause=e) from e

    except ConnectionError as e:
        logger.error("Tool router LLM connection failed: %s", e)
        debug.error("tool_router", str(e), exception=e)
        raise YourAILLMConnectionError(model=MODEL_TOOL_ROUTER, host=LLM_HOST_STD, cause=e) from e

    except Exception as e:
        logger.error("Tool router unexpected error: %s: %s", type(e).__name__, e, exc_info=True)
        log("TOOLS", f"❌ Tool router error: {e}", Fore.RED)
        debug.error("tool_router", str(e), exception=e)
        raise YourAILLMError(
            f"Tool router failed: {e}",
            model=MODEL_TOOL_ROUTER,
            cause=e,
        ) from e


def _parse_tool_router_response(res: str) -> Optional[str]:
    """
    Parsed die JSON-Antwort vom Tool Router LLM.

    Returns:
        tool_name oder None

    Raises:
        YourAILLMParseError: Wenn JSON nicht geparst werden kann
    """
    logger.debug("Parsing tool router response: '%s'", res[:120])

    try:
        json_str = res

        # JSON aus Markdown Code Block extrahieren
        if "```json" in res:
            import re
            match = re.search(r"```json\s*(\{.*?\})\s*```", res, re.DOTALL)
            if match:
                json_str = match.group(1)
                logger.debug("Extracted JSON from markdown code block")

        # Nacktes JSON extrahieren
        elif "{" in res:
            start = res.find("{")
            end = res.rfind("}") + 1
            json_str = res[start:end]
            logger.debug("Extracted JSON from raw braces: pos %d-%d", start, end)

        data = json.loads(json_str)
        tool_name = data.get("tool")
        reason = data.get("reason", "no reason given")
        logger.debug("Parsed tool router JSON: tool=%s, reason='%s'", tool_name, reason)
        return tool_name

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse tool router JSON: %s | raw='%s'", e, res[:120])
        log("TOOLS", "⚠️ Could not parse tool router response", Fore.YELLOW)
        raise YourAILLMParseError(
            model=MODEL_TOOL_ROUTER,
            expected="JSON",
            raw_preview=res,
            cause=e,
        ) from e


def execute_tool(tool_name: str, tool_info: Dict, context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """
    Führt ein Tool aus.

    Args:
        tool_name: Name des Tools
        tool_info: Tool-Konfiguration aus AVAILABLE_TOOLS
        context: Kontext (question, user_name, etc.)
        debug: Dashboard debug client

    Returns:
        {"success": bool, "result": str, "error": str|None}
    """
    debug = _get_debug(debug)
    debug.node_start("tool_execute", input_data=f"Executing: {tool_name}")

    module_path = tool_info.get("module", "unknown")
    function_name = tool_info.get("function", "unknown")

    logger.info(
        "execute_tool called | tool=%s | module=%s | function=%s | context_keys=%s",
        tool_name, module_path, function_name, list(context.keys()),
    )
    log("TOOLS", f"🔧 Executing tool: {tool_name}", Fore.CYAN)

    # Validate tool exists
    if tool_name not in AVAILABLE_TOOLS:
        logger.error("Tool not found: '%s' — available: %s", tool_name, list(AVAILABLE_TOOLS.keys()))
        raise YourAIToolNotFoundError(
            f"Tool '{tool_name}' not registered",
            tool_name=tool_name,
        )

    try:
        start_time = time.time()

        # Dynamisch das Modul laden
        import importlib
        logger.debug("Importing module: %s", module_path)
        module = importlib.import_module(module_path)

        if not hasattr(module, function_name):
            logger.error("Function '%s' not found in module '%s'", function_name, module_path)
            raise YourAIToolExecutionError(
                f"Function '{function_name}' not found in '{module_path}'",
                tool_name=tool_name,
            )

        func = getattr(module, function_name)
        logger.debug("Calling %s.%s with context keys: %s", module_path, function_name, list(context.keys()))

        # Execute
        result = func(context, debug)

        duration_ms = int((time.time() - start_time) * 1000)
        success = result.get("success", False) if isinstance(result, dict) else bool(result)

        logger.info(
            "Tool executed | tool=%s | success=%s | duration=%dms | result_type=%s",
            tool_name, success, duration_ms, type(result).__name__,
        )
        log("TOOLS", f"✅ Tool executed successfully", Fore.GREEN)
        debug.node_end("tool_execute")

        return result

    except (YourAIToolNotFoundError, YourAIToolExecutionError):
        # Bereits geloggt, einfach weiterreichen
        raise

    except ImportError as e:
        logger.error("Failed to import tool module '%s': %s", module_path, e, exc_info=True)
        debug.error("tool_execute", str(e), exception=e)
        raise YourAIToolExecutionError(
            f"Cannot import tool module '{module_path}'",
            tool_name=tool_name,
            cause=e,
        ) from e

    except Exception as e:
        logger.error("Tool execution failed | tool=%s | error=%s: %s", tool_name, type(e).__name__, e, exc_info=True)
        log("TOOLS", f"❌ Tool execution failed: {e}", Fore.RED)
        debug.error("tool_execute", str(e), exception=e)
        raise YourAIToolExecutionError(
            f"Tool '{tool_name}' failed: {e}",
            tool_name=tool_name,
            cause=e,
        ) from e


def get_available_tools() -> Dict[str, Dict]:
    """Gibt alle verfügbaren Tools zurück."""
    logger.debug("get_available_tools called — returning %d tools", len(AVAILABLE_TOOLS))
    return AVAILABLE_TOOLS.copy()