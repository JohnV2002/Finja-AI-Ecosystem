"""
YourAI Display Helpers
=====================
Provides terminal logging, exception formatting, and LLM output display helpers.

Main Responsibilities:
- Format console logs with optional colors.
- Render exceptions and raw data for debugging.
- Show LLM output in readable terminal blocks.

Side Effects:
- Writes to stdout/stderr.
- May forward errors to dashboard debug logging.
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
        """Represent MockColor behavior for helper workflows."""

        def __getattr__(self, name):
            """Return an empty ANSI sequence for missing color attributes."""
            return ""
    Fore = Style = MockColor()
    print("Tip: install colorama for colored terminal output.")

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
            """Handle highlight helper behavior."""
            return code
        class _MarkdownLexer:
            """Represent MarkdownLexer behavior for helper workflows."""

            def __init__(self, **options):
                """Initialize the fallback markdown lexer."""
                pass
        class _TerminalFormatter:
            """Represent TerminalFormatter behavior for helper workflows."""

            def __init__(self, **options):
                """Initialize the fallback terminal formatter."""
                pass
        PYGMENTS_AVAILABLE = False
        print(f"{Fore.YELLOW}Tip: install pygments for nicer code highlighting.{Style.RESET_ALL}")


# ==========================================
# LOGGING FUNCTION
# ==========================================

def _console_enabled() -> bool:
    """Check whether console logging is enabled; hot-reload safe."""
    try:
        import config
        return getattr(config, 'USE_CONSOLE_LOG', True)
    except ImportError:
        return True

def log(category: str, message: str, color=None, raw_data=None):
    """
    System logs for status messages and errors.
    Respects USE_CONSOLE_LOG; when false, only errors pass through.
    """
    # Always allow errors; allow everything else only when console logging is enabled.
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
        # Fallback for Windows terminals without UTF-8 support.
        # Replace emoji and special characters with ASCII-compatible markers.
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
    Log an exception with full context.
    
    Supports YourAIError with code/context as well as regular exceptions.
    
    Args:
        category: Log category.
        error: Exception instance.
        context: Optional extra context such as "during memory retrieval".
    """
    import traceback
    
    error_type = type(error).__name__
    
    # YourAIError carries extra information.
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
    
    # Traceback shortened to the last three frames.
    tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
    if tb_lines:
        # Keep only the last few lines, not the full stack.
        short_tb = "".join(tb_lines[-4:]).strip()
        for line in short_tb.splitlines():
            log(category, f"   {line}", Fore.LIGHTBLACK_EX)

    # Persistente Error-Inbox: einmal an YourAI/Creator melden, danach is_seen.
    inbox_record = None
    try:
        from error_inbox import record_error
        inbox_result = record_error(category, error, context=context, source="log_exception")
        inbox_record = (inbox_result or {}).get("record")
    except Exception:
        pass
            
    # Send errors to local dashboard logs while avoiding circular imports.
    try:
        from clients.dashboard_client import debug as dashboard_debug
        
        # Prepare payload for the dashboard.
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
            exception=error,
            input_data=dash_input,
            error_code=(inbox_record or {}).get("code") or code,
            error_module=(inbox_record or {}).get("module") or module or category.lower(),
            error_type=(inbox_record or {}).get("type") or type(error).__name__,
            error_id=(inbox_record or {}).get("id"),
            is_seen=bool((inbox_record or {}).get("is_seen") or (inbox_record or {}).get("isSeen")),
            repeat_count=(inbox_record or {}).get("count"),
            first_seen_at=(inbox_record or {}).get("first_seen"),
            last_seen_at=(inbox_record or {}).get("last_seen"),
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
    Display LLM output in a readable format.
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
    """Print an error message."""
    print(f"{Fore.RED}[ERR] {message}{Style.RESET_ALL}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{Fore.YELLOW}[!] {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Druckt eine Info-Nachricht."""
    print(f"{Fore.CYAN}[i] {message}{Style.RESET_ALL}")
