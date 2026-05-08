"""
YourAI AI - Display & Logging System
====================================
Schöne Terminal-Ausgaben mit Farben, Thinking-Blocks und Markdown.

Usage:
    from display import log, show_llm
"""

import re
import sys
import time

# --- COLORAMA (robust import) ---
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class MockColor:
        def __getattr__(self, name): return ""
    Fore = Style = MockColor()
    print("⚠️ Tipp: 'pip install colorama' für bunte Ausgaben!")

# --- PYGMENTS (robust & Pylance-safe) ---
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pygments import highlight as _highlight
    from pygments.lexers import MarkdownLexer as _MarkdownLexer
    from pygments.formatters import TerminalFormatter as _TerminalFormatter
    PYGMENTS_AVAILABLE = True
else:
    try:
        from pygments import highlight as _highlight
        from pygments.lexers import MarkdownLexer as _MarkdownLexer
        from pygments.formatters import TerminalFormatter as _TerminalFormatter
        PYGMENTS_AVAILABLE = True
    except ImportError:
        def _highlight(code: str, lexer=None, formatter=None, outfile=None) -> str:
            return code
        class _MarkdownLexer:
            def __init__(self, **options): pass
        class _TerminalFormatter:
            def __init__(self, **options): pass
        PYGMENTS_AVAILABLE = False
        print(f"{Fore.YELLOW}⚠️ Tipp: 'pip install pygments' für schöneres Code-Highlighting!{Style.RESET_ALL}")


# ==========================================
# LOGGING FUNCTION
# ==========================================

def _console_enabled() -> bool:
    """Check ob Console-Logging aktiv ist (hot-reload safe)."""
    try:
        import config
        return getattr(config, 'USE_CONSOLE_LOG', True)
    except ImportError:
        return True

def log(category: str, message: str, color=None, raw_data=None):
    """
    System-Logs (Statusmeldungen, Errors).
    Respektiert USE_CONSOLE_LOG — wenn False, nur Errors durchlassen.
    """
    # Errors immer durchlassen, Rest nur wenn Console Log aktiv
    is_error = "[ERROR]" in message or "[ERR]" in message or color == Fore.RED
    if not is_error and not _console_enabled():
        return

    if color is None:
        color = Fore.WHITE

    timestamp = time.strftime("%H:%M:%S")
    log_line = f"{Style.DIM}[{timestamp}]{Style.RESET_ALL} {color}{Style.BRIGHT}[{category}]{Style.RESET_ALL} {message}"
    
    try:
        print(log_line)
    except UnicodeEncodeError:
        # Fallback für Windows-Terminals ohne UTF-8 Support
        # Emojis/Sonderzeichen durch ASCII-kompatible Zeichen ersetzen
        safe_line = log_line.encode("ascii", "replace").decode("ascii")
        print(safe_line)
    
    if raw_data:
        raw_str = str(raw_data)
        if len(raw_str) > 200:
            raw_str = raw_str[:200] + "..."
        try:
            print(f"{Fore.LIGHTBLACK_EX}   └─RAW: {raw_str}{Style.RESET_ALL}")
        except UnicodeEncodeError:
            print(f"{Fore.LIGHTBLACK_EX}   └─RAW: {raw_str.encode('ascii', 'replace').decode('ascii')}{Style.RESET_ALL}")
    
    sys.stdout.flush()


def log_exception(category: str, error: Exception, context: str | None = None):
    """
    Loggt eine Exception mit vollem Kontext.
    
    Unterstützt YourAIError (mit Code + Kontext) und normale Exceptions.
    
    Args:
        category: Log-Kategorie
        error: Die Exception
        context: Optionaler Zusatzkontext (z.B. "during memory retrieval")
    """
    import traceback
    
    error_type = type(error).__name__
    
    # YourAIError hat Extra-Info
    code = getattr(error, 'code', None)
    module = getattr(error, 'module', None)
    cause = getattr(error, 'cause', None)
    
    # Header
    if code:
        header = f"[{code}] {error_type}: {error}"
    else:
        header = f"{error_type}: {error}"
    
    if context:
        header = f"{context} → {header}"
    
    log(category, f"[ERROR] {header}", Fore.RED)
    
    # Kontext (nur bei YourAIError)
    err_context = getattr(error, 'context', None)
    if err_context:
        ctx_str = ", ".join(f"{k}={v}" for k, v in err_context.items() if v is not None)
        if ctx_str:
            log(category, f"   Context: {ctx_str}", Fore.LIGHTBLACK_EX)
    
    # Cause chain
    if cause:
        log(category, f"   Caused by: {type(cause).__name__}: {cause}", Fore.LIGHTBLACK_EX)
    
    # Traceback (gekürzt auf letzte 3 Frames)
    tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
    if tb_lines:
        # Nur die letzten paar Zeilen, nicht den ganzen Stack
        short_tb = "".join(tb_lines[-4:]).strip()
        for line in short_tb.splitlines():
            log(category, f"   {line}", Fore.LIGHTBLACK_EX)
            
    # Sende Fehler an lokales Dashboard-Log (vermeide Circular Imports)
    try:
        from clients.dashboard_client import debug as dashboard_debug
        
        # Aufbereiten für Dashboard
        dash_title = f"[{code}] {type(error).__name__}: {error}" if code else f"{type(error).__name__}: {error}"
        if context:
            dash_title = f"{context} -> {dash_title}"
            
        dash_input = None
        err_context = getattr(error, 'context', None)
        if err_context:
            dash_input = ", ".join(f"{k}={v}" for k, v in err_context.items() if v is not None)
            
        dashboard_debug.error(
            node_name=module or category.lower(),
            message=dash_title,
            exception=error if not cause else cause,  # Original Cause im Stacktrace
            input_data=dash_input
        )
    except ImportError:
        pass
    except Exception:
        pass


# ==========================================
# LLM OUTPUT DISPLAY
# ==========================================

# Role-to-Color Mapping
ROLE_COLORS = {
    "router": Fore.MAGENTA,
    "yourai": Fore.GREEN,
    "expert": Fore.YELLOW,
    "granite": Fore.RED,
    "vision": Fore.BLUE,
    "altpersona": Fore.CYAN,
    "guard": Fore.YELLOW,
    "system": Fore.WHITE,
}


def show_llm(name: str, model: str, raw_output: str, role: str = "assistant", show_thinking: bool = True):
    """
    Zeigt einen LLM-Output übersichtlich an.
    Respektiert USE_CONSOLE_LOG.
    """
    if not _console_enabled():
        return
    timestamp = time.strftime("%H:%M:%S")
    color = ROLE_COLORS.get(role, Fore.WHITE)

    # Header
    header = f"[{timestamp}] Brain: {name} ({model})"
    print(f"\n{color}{Style.BRIGHT}{header}{Style.RESET_ALL}")
    print(f"{color}{'─' * (len(header) + 2)}{Style.RESET_ALL}")

    # Extract thinking blocks
    thoughts = []
    
    thinking_pattern = re.compile(
        r'<(think|thinking|thought|thoughts|scratchpad|reasoning|analysis|internal|reflection)>'
        r'(.*?)'
        r'</\1>', 
        re.DOTALL | re.IGNORECASE
    )
    
    for match in thinking_pattern.finditer(raw_output):
        tag_name = match.group(1).upper()
        thought_block = match.group(2).strip()
        if thought_block:
            thoughts.append(f"[{tag_name}] {thought_block}")
    
    # Check for italic inner voice
    italic_pattern = re.compile(r'<i>(.*?)</i>', re.DOTALL)
    for match in italic_pattern.finditer(raw_output):
        italic_text = match.group(1).strip()
        if len(italic_text.split()) > 10:
            thoughts.append(f"[INNER VOICE] {italic_text}")

    # Implicit thinking for router (text before JSON)
    if not thoughts and show_thinking and role == "router":
        json_start = raw_output.find("```json")
        if json_start == -1: 
            json_start = raw_output.find("{")
        if json_start > 20:
            thoughts.append(f"[IMPLICIT] {raw_output[:json_start].strip()}")

    # Show thinking if available
    if show_thinking and thoughts:
        print(f"{Fore.LIGHTBLACK_EX}{Style.DIM}Thinking Process:{Style.RESET_ALL}")
        for t in thoughts:
            indented = "\n".join("   " + line for line in t.splitlines())
            print(f"{Fore.LIGHTBLACK_EX}{indented}{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}{'-'*20}{Style.RESET_ALL}\n")

    # Clean output (remove thinking tags)
    clean_display = thinking_pattern.sub('', raw_output).strip()
    clean_display = italic_pattern.sub('', clean_display).strip()

    # Render with Pygments if available
    if PYGMENTS_AVAILABLE:
        try:
            lexer = _MarkdownLexer()
            formatter = _TerminalFormatter()
            formatted = _highlight(clean_display, lexer, formatter)
            print(formatted, end="")
        except Exception as e:
            print(f"{Fore.RED}Pygments Error: {e}{Style.RESET_ALL}")
            print(clean_display)
    else:
        print(clean_display)


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def print_header(title: str, char: str = "="):
    """Druckt einen formatierten Header."""
    line = char * (len(title) + 4)
    print(f"\n{Fore.CYAN}{line}")
    print(f"{Fore.CYAN}{char} {title} {char}")
    print(f"{Fore.CYAN}{line}{Style.RESET_ALL}\n")


def print_section(title: str):
    """Druckt einen Section-Header."""
    print(f"\n{Fore.YELLOW}── {title} ──{Style.RESET_ALL}")


def print_success(message: str):
    """Druckt eine Erfolgsmeldung."""
    print(f"{Fore.GREEN}[OK] {message}{Style.RESET_ALL}")


def print_error(message: str):
    """Druckt eine Fehlermeldung."""
    print(f"{Fore.RED}[ERR] {message}{Style.RESET_ALL}")


def print_warning(message: str):
    """Druckt eine Warnung."""
    print(f"{Fore.YELLOW}[!] {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Druckt eine Info-Nachricht."""
    print(f"{Fore.CYAN}[i] {message}{Style.RESET_ALL}")