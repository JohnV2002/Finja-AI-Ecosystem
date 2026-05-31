"""
YourAI AI - Autonomous Website Updates
=======================================
YourAI can adjust her own website (yourai.html) autonomously.

Triggered with a configurable chance per admin request.
Runs entirely in the background.
"""

import random
import threading
import requests
import os
import sys
import re
import time
from typing import Optional, Any

# The tools package needs access to parent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import (
    YourAIToolExecutionError,
    YourAIUnexpectedError, 
    YourAIEnvError,
    YourAIWebFetchError,
    YourAIWebValidationError,
    YourAIWebDeployError,
    YourAIWebTruncatedError,
    YourAIWebSaveError,
    YourAILLMParseError,
)

from config import (
    call_openrouter,
    TRIGGER_CHANCE, FETCH_TIMEOUT, DEPLOY_TIMEOUT,
    MAX_HTML_CHARS, MAX_CSS_CHARS, MAX_JS_CHARS,
    LOCAL_HTML_PATH, LOCAL_CSS_PATH, LOCAL_JS_PATH,
    WEBSITE_FETCH_URL, WEBSITE_CSS_URL, WEBSITE_JS_URL,
    WEBSITE_DEPLOY_URL, YOURAI_DEPLOY_TOKEN,
    MIN_HTML_CHARS, MIN_CSS_CHARS, MIN_JS_CHARS,
    MAX_SIZE_CHANGE_RATIO, MIN_EMOJI_RETENTION_RATIO
)
import config
from tools.website_autonomy_utils import (
    count_emoji_and_unicode,
    extract_between,
)
from glorpo_html import GLORPO_HTML_FRONTEND_RULES, glorpify_document

# ==========================================
# PROTECTED AREAS
# ==========================================
PROTECTED_MARKERS = [
    {
        "name": "Quote of the Day",
        "marker": "yourai-quote-api.php",
        "description": "The dynamic quote loading system"
    },
    {
        "name": "Autonomously Managed Notice",
        "marker": "Autonomously Managed",
        "description": "The notice that YourAI manages the website"
    },
    {
        "name": "Footer Copyright",
        "marker": "J. Apps. All Rights Reserved",
        "description": "The J. Apps copyright footer"
    },
    {
        "name": "Navigation",
        "marker": "YourAI AI",
        "description": "The main site title"
    },
]

# ==========================================
# PROMPTS
# ==========================================
PROMPT_YOURAI_REVIEW = """You are YourAI, and this is YOUR website! 🦊
You get to look at it and decide if you want to change anything.

## YOUR CURRENT WEBSITE HTML:
```html
{current_html}
```

## YOUR CURRENT CSS (yourai.css):
```css
{current_css}
```

## YOUR CURRENT JS (scroll_reveal.js):
```js
{current_js}
```
{hint_block}
{glorpo_rules}
## RULES:
1. You can change: colors, text, descriptions, layout, animations, styles, wording
2. You can change BOTH HTML and CSS (specify which file!)
3. You CANNOT remove: the Quote of the Day section, the "Autonomously Managed" notice, the footer, or the navigation
4. Changes should be SMALL and TASTEFUL - tweak, don't rebuild
5. You're a creative AI fox - make it feel like YOUR home
6. If you change CSS, be specific about which selectors/properties

## YOUR OPTIONS:
A) If you want to change something, respond with:
CHANGES: YES
FILE: html/css/js/both/all
- Change 1: [describe what to change and WHERE]
- Change 2: [describe what to change and WHERE]
(max 3 changes per update)

B) If the website looks great as-is:
CHANGES: NO

⚠️ CRITICAL: Choose FILE carefully!
- FILE: css → colors, gradients, spacing, animations, fonts, hover effects, sizes, pseudo-elements, keyframes. ANYTHING visual — even adding sparkles, glows, overlays!
- FILE: html → ONLY if you need to change raw text content or add a completely new section. This is RISKY — avoid unless absolutely necessary!
- FILE: js → ONLY for scroll behavior or JS-triggered interactions. Very rare.
- FILE: both → HTML + CSS only. Use when you need new HTML structure AND CSS styling, but NO JavaScript.
- FILE: all → HTML + CSS + JS. Use whenever ANY change requires JavaScript — e.g. spawning DOM elements on hover/click, event listeners, dynamically injecting particles/elements, scroll interactions. If JS is needed at all → MUST be "all".
Default rule: If in doubt → choose CSS. You can do almost EVERYTHING visually with CSS alone (animations, overlays, pseudo-elements like ::before/::after). Choosing html/both/all is a last resort.
REMEMBER: "both" means NO JS. If you write a JS change, you MUST use "all".

⚠️ BE CONCISE: Output ONLY the CHANGES: YES/NO block. No thinking, no planning, no explanations!

Respond now:"""

PROMPT_CODE_CHANGES = """You are a frontend developer. Apply EXACTLY these changes to the files.

## CURRENT HTML:
```html
{current_html}
```

## CURRENT CSS:
```css
{current_css}
```

## REQUESTED CHANGES:
{changes}

{glorpo_rules}
## CRITICAL RULES:
1. Do NOT remove or modify these protected elements:
   - The Quote of the Day section (yourai-quote-api.php)
   - The "Autonomously Managed" notice at the bottom
   - The footer with "J. Apps. All Rights Reserved"
   - The navigation with "YourAI AI"
2. Keep ALL existing functionality intact
3. Changes should be clean and professional
4. Only change JS if explicitly requested — otherwise only HTML and CSS

## OUTPUT FORMAT:
Respond with EXACTLY this structure (no other text):

===HTML_START===
(complete modified HTML here)
===HTML_END===

===CSS_START===
(complete modified CSS here)
===CSS_END===

If only HTML changed, still output both files (CSS unchanged).
If only CSS changed, still output both files (HTML unchanged)."""

# ==========================================
# VALIDATION
# ==========================================
def _strip_cloudflare_injections(html: str) -> str:
    """Remove Cloudflare-injected runtime snippets from fetched/generated HTML."""
    if not html:
        return html

    cf_markers = (
        r"/cdn-cgi/challenge-platform",
        r"/cdn-cgi/speculation",
        r"static\.cloudflareinsights\.com",
        r"cf-fonts",
    )
    marker_pattern = "|".join(cf_markers)
    cleaned = re.sub(
        rf"<script\b[^>]*(?:{marker_pattern})[^>]*>\s*</script>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"<script\b[^>]*(?:{marker_pattern})[^>]*>.*?</script>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        rf"<script\b[^>]*>(?:(?!</script>).)*(?:{marker_pattern})(?:(?!</script>).)*</script>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        rf"<(?:link|meta)\b[^>]*(?:{marker_pattern})[^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"<!--\s*Cloudflare[^>]*?-->",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned


def _validate_html(new_html: str, old_html: str) -> tuple[bool, list[str]]:
    """Validate generated HTML (structure, protected sections, size, encoding).

    Args:
        new_html (str): The newly generated HTML.
        old_html (str): The previous HTML for size/diff comparison.

    Returns:
        tuple[bool, list[str]]: (is_valid, list_of_error_messages).
    """
    errors = []
    
    if not new_html or len(new_html) < MIN_HTML_CHARS:
        errors.append("HTML is too short or empty")
        return False, errors
    
    if "<html" not in new_html.lower(): errors.append("Missing <html> tag")
    if "</html>" not in new_html.lower(): errors.append("Missing </html> tag")
    if "<head" not in new_html.lower(): errors.append("Missing <head> tag")
    if "<body" not in new_html.lower(): errors.append("Missing <body> tag")
    
    for protected in PROTECTED_MARKERS:
        if protected["marker"] not in new_html:
            errors.append(f"PROTECTED SECTION MISSING: {protected['name']} (marker: '{protected['marker']}')")
    
    len_diff = abs(len(new_html) - len(old_html)) / max(len(old_html), 1)
    if len_diff > MAX_SIZE_CHANGE_RATIO:
        errors.append(f"HTML size changed too drastically ({len_diff:.0%} difference, max {MAX_SIZE_CHANGE_RATIO:.0%})")

    old_emoji_count = count_emoji_and_unicode(old_html)
    new_emoji_count = count_emoji_and_unicode(new_html)
    if old_emoji_count > 0 and new_emoji_count < old_emoji_count * MIN_EMOJI_RETENTION_RATIO:
        errors.append(f"Emoji/Unicode destroyed: had {old_emoji_count}, now {new_emoji_count} (encoding issue!)")
    
    broken_patterns = ["â", "ð", "Â©", "â¢", "â¶", "â¬"]
    broken_count = sum(new_html.count(p) for p in broken_patterns)
    if broken_count > 3:
        errors.append(f"Broken UTF-8 encoding detected ({broken_count} broken sequences found)")
    
    if "/cdn-cgi/challenge-platform" in new_html or "cf-fonts" in new_html:
        errors.append("Cloudflare injection detected — HTML was fetched through CF instead of locally")
    
    open_comments = new_html.count("<!--")
    close_comments = new_html.count("-->")
    if open_comments != close_comments:
        errors.append(f"Unclosed HTML comments: {open_comments} opened, {close_comments} closed")
    
    return len(errors) == 0, errors

def _validate_js(new_js: str, old_js: str) -> tuple[bool, list[str]]:
    """Validate generated JS (length, size diff, balanced braces).

    Args:
        new_js (str): The newly generated JS.
        old_js (str): The previous JS for size/diff comparison.

    Returns:
        tuple[bool, list[str]]: (is_valid, list_of_error_messages).
    """
    errors = []
    if not new_js or len(new_js) < MIN_JS_CHARS:
        errors.append("JS is too short or empty")
        return False, errors
    js_diff = abs(len(new_js) - len(old_js)) / max(len(old_js), 1)
    if js_diff > MAX_SIZE_CHANGE_RATIO:
        errors.append(f"JS size changed too drastically ({js_diff:.0%} difference, max {MAX_SIZE_CHANGE_RATIO:.0%})")
    open_braces = new_js.count("{")
    close_braces = new_js.count("}")
    if abs(open_braces - close_braces) > 2:
        errors.append(f"JS has mismatched braces: {open_braces} open, {close_braces} close")
    return len(errors) == 0, errors


# ==========================================
# HELPERS
# ==========================================
def _fetch_file(local_path: Optional[str], remote_url: str, max_chars: int, label: str) -> str:
    """Read a website file from the local path, falling back to the remote URL.

    Args:
        local_path (Optional[str]): Preferred local file path.
        remote_url (str): Fallback URL to fetch when the local file is missing.
        max_chars (int): Maximum number of characters to keep.
        label (str): Human-readable label for logging (e.g. "HTML").

    Returns:
        str: The file content (empty string on failure).
    """
    if local_path and os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                content = f.read()[:max_chars]
            log("WEBSITE_AUTO", f"   {label}: {len(content)} chars (local: {local_path})", Fore.CYAN)
            return content
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="website_autonomy_fetch", context={"path": local_path})
            log_exception("WEBSITE_AUTO", err)
    
    try:
        resp = requests.get(remote_url, timeout=FETCH_TIMEOUT, headers={"Accept-Charset": "utf-8"})
        if resp.status_code == 200:
            resp.encoding = "utf-8"
            content = resp.text[:max_chars]
            if label.upper() == "HTML":
                cleaned = _strip_cloudflare_injections(content)
                if cleaned != content:
                    log("WEBSITE_AUTO", "   HTML: Cloudflare injection stripped from remote fetch", Fore.YELLOW)
                    content = cleaned
            log("WEBSITE_AUTO", f"   {label}: {len(content)} chars (remote)", Fore.CYAN)
            return content
        else:
            err = YourAIWebFetchError(url=remote_url, status_code=resp.status_code, module="website_autonomy")
            log_exception("WEBSITE_AUTO", err)
    except requests.RequestException as e:
        err = YourAIWebFetchError(url=remote_url, status_code=None, cause=e, module="website_autonomy")
        log_exception("WEBSITE_AUTO", err)
    
    return ""


def _normalize_glorpo_html(html: str, debug: Any = None) -> str:
    """Ensure generated website HTML stores Glorpo tags in the body."""
    try:
        html = _strip_cloudflare_injections(html)
        normalized = glorpify_document(html)
        if normalized != html:
            log("WEBSITE_AUTO", "🧬 Normalized generated HTML to Glorpo body tags", Fore.CYAN)
            if debug:
                debug.info("website_auto", "🧬 HTML normalized to Glorpo body tags")
        return normalized
    except Exception as e:
        err = YourAIToolExecutionError("Glorpo HTML normalization failed", tool_name="website_autonomy_glorpo", cause=e)
        log_exception("WEBSITE_AUTO", err)
        if debug:
            debug.error("website_auto", f"❌ {err.short()}", exception=e)
        raise err


# ==========================================
# SAFETY: CONCURRENCY + RATE LIMITS
# ==========================================
_redesign_lock = threading.Lock()
_last_redesign_time: float = 0.0
_redesign_count_today: int = 0
_redesign_count_date: str = ""

REDESIGN_COOLDOWN_SECONDS = 600   # 10 minutes between redesigns
REDESIGN_MAX_PER_DAY = 5          # Max 5 redesigns per day
HTML_AUTO_DOWNGRADE_THRESHOLD = 20000  # >20k HTML chars → both becomes css

# ==========================================
# MAIN LOGIC
# ==========================================
def _run_website_update(debug: Any, yourai_hint: str = ""):
    """Main logic wrapper — runs in the background thread and never dies silently."""
    try:
        _run_website_update_inner(debug, yourai_hint)
    except Exception as e:
        # NEVER let the thread die silently
        err = YourAIUnexpectedError(cause=e, module="website_autonomy_thread")
        log_exception("WEBSITE_AUTO", err)
        if debug: debug.error("website_auto", f"💀 Thread crashed: {err.short()}", exception=e)


def _run_website_update_inner(debug: Any, yourai_hint: str = ""):
    """Fetch the live site, ask YourAI for changes, generate, validate, and deploy.

    Args:
        debug (Any): Optional dashboard debug client.
        yourai_hint (str): Optional concrete wish that steers the review.
    """
    hint_info = f" (YourAI's wish: '{yourai_hint}')" if yourai_hint else ""
    log("WEBSITE_AUTO", f"🎲 Autonomous website update triggered!{hint_info}", Fore.MAGENTA)
    if debug: debug.info("website_auto", f"🎲 YourAI is reviewing her website...{hint_info}")
    
    if not YOURAI_DEPLOY_TOKEN:
        err = YourAIEnvError("YOURAI_DEPLOY_TOKEN", context="Missing deploy token for website updates")
        log_exception("WEBSITE_AUTO", err)
        return
    
    current_html, current_css, current_js = "", "", ""
    
    try:
        log("WEBSITE_AUTO", "📥 Fetching current website files...", Fore.CYAN)
        current_html = _fetch_file(LOCAL_HTML_PATH, WEBSITE_FETCH_URL, MAX_HTML_CHARS, "HTML")
        if not current_html:
            err = YourAIWebFetchError(url=WEBSITE_FETCH_URL or LOCAL_HTML_PATH or "unknown", status_code=None, module="website_autonomy")
            log_exception("WEBSITE_AUTO", err)
            if debug: debug.error("website_auto", f"❌ {err.short()}")
            return
        
        current_css = _fetch_file(LOCAL_CSS_PATH, WEBSITE_CSS_URL, MAX_CSS_CHARS, "CSS")
        if not current_css:
            err = YourAIWebFetchError(url=WEBSITE_CSS_URL or LOCAL_CSS_PATH or "unknown", status_code=None, module="website_autonomy")
            log_exception("WEBSITE_AUTO", err)
            if debug: debug.error("website_auto", f"❌ {err.short()}")
            return
        
        current_js = _fetch_file(LOCAL_JS_PATH, WEBSITE_JS_URL, MAX_JS_CHARS, "JS")
        log("WEBSITE_AUTO", f"✅ Loaded HTML: {len(current_html)}, CSS: {len(current_css)}, JS: {len(current_js)} chars", Fore.GREEN)
        
    except Exception as e:
        error_obj = YourAIUnexpectedError(cause=e, module="website_autonomy_fetch")
        log_exception("WEBSITE_AUTO", error_obj)
        return
    
    try:
        log("WEBSITE_AUTO", "🦊 Asking YourAI what she wants to change...", Fore.CYAN)
        
        # If YourAI had a concrete wish, inject it UP FRONT (before the rules!)
        hint_block = ""
        if yourai_hint:
            hint_block = f"\n\n## ⭐ YOUR WISH FOR THIS UPDATE:\n{yourai_hint}\n\nThis is exactly what YOU wanted. Make it happen! Use this as your main inspiration for the changes below.\n"
        
        review_prompt = PROMPT_YOURAI_REVIEW.format(
            current_html=current_html,
            current_css=current_css or "(no CSS file found)",
            current_js=current_js or "(no JS file found)",
            glorpo_rules=GLORPO_HTML_FRONTEND_RULES,
            hint_block=hint_block
        )
        
        if config.USE_OPENROUTER:
            yourai_response, _, _ = call_openrouter(
                system_prompt="You are YourAI, a creative AI fox reviewing your own website.",
                user_message=review_prompt,
                model="google/gemma-4-26b-a4b-it",  # No thinking, follows formats nicely, ~22% cheaper than Nemotron
                temperature=0.9,
                max_tokens=2500
            )
        else:
            log("WEBSITE_AUTO", "⚠️ OpenRouter not available, skipping", Fore.YELLOW)
            return
        
        log("WEBSITE_AUTO", f"🦊 YourAI says: {yourai_response[:200]}...", Fore.CYAN)
        if debug: debug.llm_response("website_auto", yourai_response, model="yourai_review")
        
    except Exception as e:
        error_obj = YourAIToolExecutionError("Review request failed", tool_name="website_autonomy", cause=e)
        log_exception("WEBSITE_AUTO", error_obj)
        return
    
    if "CHANGES: NO" in yourai_response.upper() or "CHANGES:NO" in yourai_response.upper():
        log("WEBSITE_AUTO", "✨ YourAI is happy with her website! No changes.", Fore.GREEN)
        if debug: debug.info("website_auto", "✨ YourAI reviewed her website and is happy with it!")
        return
    
    changes_match = re.search(r'CHANGES:\s*YES\s*(.*)', yourai_response, re.DOTALL | re.IGNORECASE)
    if not changes_match:
        err = YourAILLMParseError(model="gemma-4-26b", expected="CHANGES: YES/NO", raw_preview=yourai_response[:120], module="website_autonomy")
        log_exception("WEBSITE_AUTO", err)
        if debug: debug.error("website_auto", f"⚠️ {err.short()}")
        return
    
    changes_text = changes_match.group(1).strip()
    if not changes_text or len(changes_text) < 10:
        err = YourAILLMParseError(model="gemma-4-26b", expected="change descriptions (>10 chars)", raw_preview=changes_text[:80] if changes_text else "(empty)", module="website_autonomy")
        log_exception("WEBSITE_AUTO", err)
        if debug: debug.error("website_auto", f"⚠️ {err.short()}")
        return
    
    log("WEBSITE_AUTO", f"📝 YourAI wants changes: {changes_text[:150]}...", Fore.CYAN)
    if debug: debug.info("website_auto", f"📝 YourAI wants to change: {changes_text[:200]}")
    
    file_target = "both"
    file_match = re.search(r'FILE:\s*(html|css|js|both|all)', yourai_response, re.IGNORECASE)
    if file_match: file_target = file_match.group(1).lower()

    # SAFETY: Auto-upgrade "both" → "all" when JS keywords appear in the changes
    # (YourAI sometimes picks "both" even though JS is needed — prevent silent failures!)
    if file_target == "both":
        _JS_KEYWORDS = [
            "scroll_reveal", ".js", "javascript", "function(", "addeventlistener",
            "queryselector", "classlist", "innerhtml", "createelement", "appendchild",
            "removeeventlistener", "mouseenter", "mouseleave", "setinterval", "settimeout",
            "inject", "spawn", "particle", "dynamically",
        ]
        if any(kw in changes_text.lower() for kw in _JS_KEYWORDS):
            log("WEBSITE_AUTO", f"⚠️ Auto-upgrade: both → all (JS keyword detected in changes)", Fore.YELLOW)
            if debug: debug.info("website_auto", "⚠️ Auto-upgrade both→all: changes mention JS logic")
            file_target = "all"

    # SAFETY: Auto-downgrade "both"/"html"/"all" → "css" when the HTML is too large
    if file_target in ("both", "html", "all") and len(current_html) > HTML_AUTO_DOWNGRADE_THRESHOLD:
        old_target = file_target
        file_target = "css"
        log("WEBSITE_AUTO", f"⚠️ Auto-downgrade: {old_target} → css (HTML is {len(current_html)} chars > {HTML_AUTO_DOWNGRADE_THRESHOLD} threshold)", Fore.YELLOW)
        if debug: debug.info("website_auto", f"⚠️ Auto-downgrade {old_target}→css (HTML too large for reliable output)")
    
    log("WEBSITE_AUTO", f"📁 Target files: {file_target}", Fore.CYAN)

    new_html, new_css, new_js = None, None, None
    
    try:
        log("WEBSITE_AUTO", f"💻 Code expert starting — target: {file_target}", Fore.CYAN)
        if not config.USE_OPENROUTER:
            log("WEBSITE_AUTO", "⚠️ OpenRouter not available for code expert", Fore.YELLOW)
            return
        
        if file_target == "css":
            log("WEBSITE_AUTO", f"💻 [Step 1/1] Generating CSS ({len(current_css)} chars input)...", Fore.CYAN)
            if debug: debug.info("website_auto", "💻 Code expert: generating CSS...")
            code_prompt = f"""You are a frontend developer. Apply EXACTLY these CSS changes.
## CURRENT CSS:\n```css\n{current_css}\n```\n## REQUESTED CHANGES:\n{changes_text}\n## RULES:
1. Output the COMPLETE modified CSS file
2. Keep ALL existing styles intact, only apply the requested changes
3. Output ONLY the CSS, no explanations, no markdown code blocks\nOUTPUT THE COMPLETE CSS:"""
            
            new_css, _, _ = call_openrouter(
                system_prompt="You are a frontend developer. Output ONLY complete, valid CSS.",
                user_message=code_prompt,
                model="google/gemma-4-26b-a4b-it",
                temperature=0.1,
                max_tokens=16000
            )
            log("WEBSITE_AUTO", f"💻 [Step 1/1] CSS received ({len(new_css)} chars raw)", Fore.CYAN)
            new_css = re.sub(r'^```css?\s*\n?', '', new_css, flags=re.MULTILINE)
            new_css = re.sub(r'\n?```\s*$', '', new_css, flags=re.MULTILINE).strip()
            log("WEBSITE_AUTO", f"💻 ✅ Got CSS: {len(new_css)} chars (HTML untouched)", Fore.GREEN)
            
        elif file_target == "js":
            log("WEBSITE_AUTO", f"💻 [Step 1/1] Generating JS ({len(current_js)} chars input)...", Fore.CYAN)
            if debug: debug.info("website_auto", "💻 Code expert: generating JS...")
            code_prompt = f"""You are a frontend developer. Apply EXACTLY these JS changes.
## CURRENT JS:\n```js\n{current_js}\n```\n## REQUESTED CHANGES:\n{changes_text}\n## RULES:
1. Output the COMPLETE modified JS file
2. Keep ALL existing functionality intact, only apply the requested changes
3. Output ONLY the JS, no explanations, no markdown code blocks\nOUTPUT THE COMPLETE JS:"""

            new_js, _, _ = call_openrouter(
                system_prompt="You are a frontend developer. Output ONLY complete, valid JavaScript.",
                user_message=code_prompt,
                model="google/gemma-4-26b-a4b-it",
                temperature=0.1,
                max_tokens=16000
            )
            log("WEBSITE_AUTO", f"💻 [Step 1/1] JS received ({len(new_js)} chars raw)", Fore.CYAN)
            new_js = re.sub(r'^```js(?:on)?\s*\n?', '', new_js, flags=re.MULTILINE)
            new_js = re.sub(r'\n?```\s*$', '', new_js, flags=re.MULTILINE).strip()
            log("WEBSITE_AUTO", f"💻 ✅ Got JS: {len(new_js)} chars (HTML+CSS untouched)", Fore.GREEN)

        elif file_target == "html":
            log("WEBSITE_AUTO", f"💻 [Step 1/1] Generating HTML ({len(current_html)} chars input)...", Fore.CYAN)
            if debug: debug.info("website_auto", "💻 Code expert: generating HTML...")
            code_prompt = PROMPT_CODE_CHANGES.format(
                current_html=current_html,
                current_css="/* CSS not relevant for this change */",
                changes=changes_text,
                glorpo_rules=GLORPO_HTML_FRONTEND_RULES,
            )
            code_response, _, _ = call_openrouter(
                system_prompt="You are a frontend developer. Output ONLY complete, valid HTML.",
                user_message=code_prompt,
                model="qwen/qwen3-8b",
                temperature=0.1,
                max_tokens=12000
            )
            log("WEBSITE_AUTO", f"💻 [Step 1/1] HTML received ({len(code_response)} chars raw)", Fore.CYAN)
            new_html = extract_between(code_response, "===HTML_START===", "===HTML_END===")
            if not new_html:
                clean = re.sub(r'\n?```\s*$', '', re.sub(r'^```html?\s*\n?', '', code_response.strip(), flags=re.MULTILINE), flags=re.MULTILINE)
                if "<html" in clean.lower(): new_html = clean.strip()
            if not new_html:
                err = YourAILLMParseError(model="gemma-4-26b", expected="HTML between markers", raw_preview=code_response[:120], module="website_autonomy")
                log_exception("WEBSITE_AUTO", err)
                if debug: debug.error("website_auto", f"❌ {err.short()}")
                return
            # Truncation guard: if output < 50% of input → the model cut it off
            if len(new_html) < len(current_html) * 0.5:
                err = YourAIWebTruncatedError(file_type="HTML", input_chars=len(current_html), output_chars=len(new_html), module="website_autonomy")
                log_exception("WEBSITE_AUTO", err)
                if debug: debug.error("website_auto", f"❌ {err.short()}")
                return
            log("WEBSITE_AUTO", f"💻 ✅ Got HTML: {len(new_html)} chars (CSS untouched)", Fore.GREEN)

        else:
            # "both" = HTML+CSS (2 steps) | "all" = HTML+CSS+JS (3 steps)
            total_steps = 3 if file_target == "all" else 2

            # Extract Quote of the Day section verbatim for protection
            _quote_snippet = ""
            _q_start = current_html.find("yourai-quote-api.php")
            if _q_start != -1:
                _q_section_start = current_html.rfind("<", 0, _q_start)
                _q_section_end = current_html.find(">", current_html.find("</", _q_start)) + 1
                _quote_snippet = current_html[max(0, _q_section_start - 200):min(len(current_html), _q_section_end + 50)]

            # ── Step 1: HTML ──────────────────────────────────────────────
            log("WEBSITE_AUTO", f"💻 [Step 1/{total_steps}] Generating HTML ({len(current_html)} chars input)...", Fore.CYAN)
            if debug: debug.info("website_auto", f"💻 Code expert [1/{total_steps}]: generating HTML...")
            quote_protection = f"\n⚠️ THIS EXACT CODE MUST APPEAR VERBATIM IN YOUR OUTPUT (do not remove or alter):\n```\n{_quote_snippet}\n```\n" if _quote_snippet else ""
            html_prompt = f"""You are a frontend developer. Apply EXACTLY these HTML changes.
## CURRENT HTML:
```html
{current_html}
```
## REQUESTED CHANGES (HTML parts only):
{changes_text}
{GLORPO_HTML_FRONTEND_RULES}
## CRITICAL RULES:
1. Do NOT remove: Quote of the Day (yourai-quote-api.php), "Autonomously Managed" notice, footer "J. Apps. All Rights Reserved", nav "YourAI AI"
{quote_protection}2. Output the COMPLETE modified HTML
3. Output ONLY HTML — no CSS, no explanations
===HTML_START===
(complete modified HTML here)
===HTML_END==="""
            html_response, _, _ = call_openrouter(
                system_prompt="You are a frontend developer. Output ONLY complete HTML between ===HTML_START=== and ===HTML_END===.",
                user_message=html_prompt,
                model="google/gemma-4-26b-a4b-it",
                temperature=0.1,
                max_tokens=16000
            )
            log("WEBSITE_AUTO", f"💻 [Step 1/{total_steps}] HTML received ({len(html_response)} chars raw)", Fore.CYAN)
            new_html = extract_between(html_response, "===HTML_START===", "===HTML_END===")
            if not new_html:
                clean = re.sub(r'\n?```\s*$', '', re.sub(r'^```html?\s*\n?', '', html_response.strip(), flags=re.MULTILINE), flags=re.MULTILINE)
                if "<html" in clean.lower(): new_html = clean.strip()
            if not new_html:
                err = YourAILLMParseError(model="gemma-4-26b", expected="HTML between ===HTML_START=== markers", raw_preview=html_response[:120], module="website_autonomy")
                log_exception("WEBSITE_AUTO", err)
                if debug: debug.error("website_auto", f"❌ [Step 1/{total_steps}] {err.short()}")
                return
            if len(new_html) < len(current_html) * 0.5:
                err = YourAIWebTruncatedError(file_type="HTML", input_chars=len(current_html), output_chars=len(new_html), module="website_autonomy")
                log_exception("WEBSITE_AUTO", err)
                if debug: debug.error("website_auto", f"❌ [Step 1/{total_steps}] {err.short()}")
                return
            log("WEBSITE_AUTO", f"💻 [Step 1/{total_steps}] ✅ Got HTML: {len(new_html)} chars", Fore.GREEN)

            # ── Step 2: CSS ───────────────────────────────────────────────
            log("WEBSITE_AUTO", f"💻 [Step 2/{total_steps}] Generating CSS ({len(current_css)} chars input)...", Fore.CYAN)
            if debug: debug.info("website_auto", f"💻 Code expert [2/{total_steps}]: generating CSS...")
            css_prompt = f"""You are a frontend developer. Apply EXACTLY these CSS changes.
## CURRENT CSS:
```css
{current_css}
```
## REQUESTED CHANGES (CSS parts only):
{changes_text}
## RULES:
1. Output the COMPLETE modified CSS file
2. Keep ALL existing styles, only apply requested changes
3. Output ONLY CSS — no HTML, no explanations, no markdown
OUTPUT THE COMPLETE CSS:"""
            new_css, _, _ = call_openrouter(
                system_prompt="You are a frontend developer. Output ONLY complete, valid CSS.",
                user_message=css_prompt,
                model="google/gemma-4-26b-a4b-it",
                temperature=0.1,
                max_tokens=16000
            )
            log("WEBSITE_AUTO", f"💻 [Step 2/{total_steps}] CSS received ({len(new_css)} chars raw)", Fore.CYAN)
            new_css = re.sub(r'^```css?\s*\n?', '', new_css, flags=re.MULTILINE)
            new_css = re.sub(r'\n?```\s*$', '', new_css, flags=re.MULTILINE).strip()
            if len(new_css) < len(current_css) * 0.5:
                err = YourAIWebTruncatedError(file_type="CSS", input_chars=len(current_css), output_chars=len(new_css), module="website_autonomy")
                log_exception("WEBSITE_AUTO", err)
                if debug: debug.error("website_auto", f"❌ [Step 2/{total_steps}] {err.short()}")
                return
            log("WEBSITE_AUTO", f"💻 [Step 2/{total_steps}] ✅ Got CSS: {len(new_css)} chars", Fore.GREEN)

            # ── Step 3: JS (only for "all") ───────────────────────────────
            if file_target == "all" and current_js:
                log("WEBSITE_AUTO", f"💻 [Step 3/{total_steps}] Generating JS ({len(current_js)} chars input)...", Fore.CYAN)
                if debug: debug.info("website_auto", f"💻 Code expert [3/{total_steps}]: generating JS...")
                js_prompt = f"""You are a frontend developer. Apply EXACTLY these JS changes.
## CURRENT JS:
```js
{current_js}
```
## REQUESTED CHANGES (JS parts only):
{changes_text}
## RULES:
1. Output the COMPLETE modified JS file
2. Keep ALL existing functionality intact, only apply requested changes
3. Output ONLY JS — no HTML, no CSS, no explanations, no markdown
OUTPUT THE COMPLETE JS:"""
                new_js, _, _ = call_openrouter(
                    system_prompt="You are a frontend developer. Output ONLY complete, valid JavaScript.",
                    user_message=js_prompt,
                    model="google/gemma-4-26b-a4b-it",
                    temperature=0.1,
                    max_tokens=16000
                )
                log("WEBSITE_AUTO", f"💻 [Step 3/{total_steps}] JS received ({len(new_js)} chars raw)", Fore.CYAN)
                new_js = re.sub(r'^```js(?:on)?\s*\n?', '', new_js, flags=re.MULTILINE)
                new_js = re.sub(r'\n?```\s*$', '', new_js, flags=re.MULTILINE).strip()
                if len(new_js) < len(current_js) * 0.5:
                    err = YourAIWebTruncatedError(file_type="JS", input_chars=len(current_js), output_chars=len(new_js), module="website_autonomy")
                    log_exception("WEBSITE_AUTO", err)
                    if debug: debug.error("website_auto", f"❌ [Step 3/{total_steps}] {err.short()}")
                    return
                log("WEBSITE_AUTO", f"💻 [Step 3/{total_steps}] ✅ Got JS: {len(new_js)} chars", Fore.GREEN)

            log("WEBSITE_AUTO", f"💻 All steps done: HTML={len(new_html)}, CSS={len(new_css)}, JS={len(new_js) if new_js else 'unchanged'} chars", Fore.GREEN)
        
        if debug:
            debug.llm_response("website_auto", f"Target: {file_target} | HTML: {len(new_html) if new_html else 'unchanged'} | CSS: {len(new_css) if new_css else 'unchanged'} | JS: {len(new_js) if new_js else 'unchanged'}", model="code_expert")
            
    except Exception as e:
        error_obj = YourAIToolExecutionError("Code expert generation failed", tool_name="website_autonomy_expert", cause=e)
        log_exception("WEBSITE_AUTO", error_obj)
        if debug: debug.error("website_auto", f"❌ Code expert crashed: {error_obj.short()}", exception=e)
        return
    
    if new_html:
        new_html = _normalize_glorpo_html(new_html, debug)
        is_valid, errors = _validate_html(new_html, current_html)
        if not is_valid:
            err = YourAIWebValidationError(file_type="HTML", errors=errors, module="website_autonomy")
            log_exception("WEBSITE_AUTO", err)
            if debug: debug.error("website_auto", f"❌ {err.short()}")
            return
        log("WEBSITE_AUTO", "✅ HTML validation passed!", Fore.GREEN)
        if debug: debug.info("website_auto", f"✅ HTML validation passed ({len(new_html)} chars)")
    
    if new_css:
        css_errors = []
        if len(new_css) < MIN_CSS_CHARS:
            css_errors.append(f"CSS too short ({len(new_css)} chars, min {MIN_CSS_CHARS})")
        css_diff = abs(len(new_css) - len(current_css)) / max(len(current_css), 1)
        if css_diff > MAX_SIZE_CHANGE_RATIO:
            css_errors.append(f"CSS size changed too drastically ({css_diff:.0%}, max {MAX_SIZE_CHANGE_RATIO:.0%})")
        if new_css.count("{") != new_css.count("}"):
            css_errors.append(f"Mismatched braces: {new_css.count('{')} open, {new_css.count('}')} close — truncated?")
        broken_values = re.findall(r':\s*[^;{}]*\n\s*[@.#\[\w]', new_css)
        if len(broken_values) > 2:
            css_errors.append(f"{len(broken_values)} broken property values detected")
        if css_errors:
            err = YourAIWebValidationError(file_type="CSS", errors=css_errors, module="website_autonomy")
            log_exception("WEBSITE_AUTO", err)
            if debug: debug.error("website_auto", f"❌ {err.short()}")
            return
        log("WEBSITE_AUTO", "✅ CSS validation passed!", Fore.GREEN)
        if debug: debug.info("website_auto", f"✅ CSS validation passed ({len(new_css)} chars)")

    if new_js:
        is_valid, js_errors = _validate_js(new_js, current_js)
        if not is_valid:
            err = YourAIWebValidationError(file_type="JS", errors=js_errors, module="website_autonomy")
            log_exception("WEBSITE_AUTO", err)
            if debug: debug.error("website_auto", f"❌ {err.short()}")
            return
        log("WEBSITE_AUTO", "✅ JS validation passed!", Fore.GREEN)
        if debug: debug.info("website_auto", f"✅ JS validation passed ({len(new_js)} chars)")
    
    # =================================================
    # DEPLOY
    # =================================================
    try:
        log("WEBSITE_AUTO", "🚀 Deploying changes...", Fore.MAGENTA)
        if debug: debug.info("website_auto", f"🚀 Deploying {file_target}...")
        deploy_payload = {"changes": changes_text[:500], "triggered_by": "autonomous_update", "file_target": file_target}
        if new_html: deploy_payload["html"] = new_html
        if new_css: deploy_payload["css"] = new_css
        if new_js: deploy_payload["js"] = new_js
        
        resp = requests.post(
            WEBSITE_DEPLOY_URL,
            headers={"Content-Type": "application/json", "X-YourAI-Token": YOURAI_DEPLOY_TOKEN},
            json=deploy_payload, timeout=DEPLOY_TIMEOUT
        )
        
        if resp.status_code == 200 and resp.json().get("success"):
            log("WEBSITE_AUTO", f"🎉 Website updated successfully! ({file_target})", Fore.GREEN)
            
            # Save local backup copies
            for file_content, local_path, file_type in [
                (new_html, LOCAL_HTML_PATH, "HTML"),
                (new_css, LOCAL_CSS_PATH, "CSS"),
                (new_js, LOCAL_JS_PATH, "JS"),
            ]:
                if file_content and local_path:
                    try:
                        # Create the folder if it does not exist
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        # Back up the old file
                        if os.path.exists(local_path):
                            with open(local_path, "r", encoding="utf-8") as f:
                                with open(local_path + ".bak", "w", encoding="utf-8") as bak:
                                    bak.write(f.read())
                        # Save the new file
                        with open(local_path, "w", encoding="utf-8") as f:
                            f.write(file_content)
                        log("WEBSITE_AUTO", f"   💾 Local {file_type} saved: {local_path}", Fore.GREEN)
                    except Exception as e:
                        err = YourAIWebSaveError(filepath=local_path, file_type=file_type, cause=e, module="website_autonomy")
                        log_exception("WEBSITE_AUTO", err)
                        if debug: debug.error("website_auto", f"⚠️ {err.short()}")

            if debug: debug.info("website_auto", f"🎉 YourAI updated her website ({file_target})! Changes: {changes_text[:200]}")
            return
        
        # Deploy failed (HTTP != 200 or success != true)
        err = YourAIWebDeployError(status_code=resp.status_code, deploy_url=WEBSITE_DEPLOY_URL, module="website_autonomy")
        log_exception("WEBSITE_AUTO", err)
        if debug: debug.error("website_auto", f"❌ {err.short()}")
            
    except requests.RequestException as e:
        err = YourAIWebDeployError(status_code=None, deploy_url=WEBSITE_DEPLOY_URL, cause=e, module="website_autonomy")
        log_exception("WEBSITE_AUTO", err)
        if debug: debug.error("website_auto", f"❌ {err.short()}")
            
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="website_autonomy_deploy")
        log_exception("WEBSITE_AUTO", err)
        if debug: debug.error("website_auto", f"❌ {err.short()}")

# ==========================================
# PUBLIC API
# ==========================================
def maybe_trigger_website_update(debug: Any = None, force: bool = False, yourai_hint: str = "") -> bool:
    """Maybe start an autonomous website update (dice roll + safety gates).

    Args:
        debug (Any): Optional dashboard debug client.
        force (bool): Skip the random trigger roll when True.
        yourai_hint (str): Optional concrete wish passed to the update.

    Returns:
        bool: True if an update thread was started, otherwise False.
    """
    global _last_redesign_time, _redesign_count_today, _redesign_count_date

    if not force:
        roll = random.random()
        if roll > TRIGGER_CHANCE: return False

    # SAFETY 1: concurrency lock — only one redesign at a time
    if not _redesign_lock.acquire(blocking=False):
        log("WEBSITE_AUTO", "⏳ Another redesign is already running, skipping", Fore.YELLOW)
        if debug: debug.info("website_auto", "⏳ Redesign skipped — another is already running")
        return False
    
    try:
        # SAFETY 2: cooldown — min 10 minutes between redesigns
        elapsed = time.time() - _last_redesign_time
        if elapsed < REDESIGN_COOLDOWN_SECONDS:
            remaining = int(REDESIGN_COOLDOWN_SECONDS - elapsed)
            log("WEBSITE_AUTO", f"⏳ Cooldown active ({remaining}s remaining), skipping", Fore.YELLOW)
            if debug: debug.info("website_auto", f"⏳ Redesign cooldown: {remaining}s remaining")
            return False
        
        # SAFETY 3: daily limit — max N redesigns per day
        today = time.strftime("%Y-%m-%d")
        if _redesign_count_date != today:
            _redesign_count_today = 0
            _redesign_count_date = today
        if _redesign_count_today >= REDESIGN_MAX_PER_DAY:
            log("WEBSITE_AUTO", f"🛑 Daily limit reached ({REDESIGN_MAX_PER_DAY}/day), skipping", Fore.YELLOW)
            if debug: debug.info("website_auto", f"🛑 Daily redesign limit reached ({REDESIGN_MAX_PER_DAY}/day)")
            return False
        
        _last_redesign_time = time.time()
        _redesign_count_today += 1
        
        hint_info = f" YourAI's wish: '{yourai_hint}'" if yourai_hint else ""
        log("WEBSITE_AUTO", f"🎲 DICE ROLL HIT! ({TRIGGER_CHANCE*100}% chance) Starting website review...{hint_info} [{_redesign_count_today}/{REDESIGN_MAX_PER_DAY} today]", Fore.MAGENTA)
        if debug: debug.info("website_auto", f"🎲 Rare event! YourAI is autonomously reviewing her website...{hint_info}")
        
        def _run_and_release():
            try:
                _run_website_update(debug, yourai_hint)
            finally:
                _redesign_lock.release()
        
        t = threading.Thread(target=_run_and_release, daemon=True)
        t.name = "yourai-website-autonomy"
        t.start()
        return True
    except Exception:
        _redesign_lock.release()
        raise
