"""
YourAI AI - Autonomous Lab / Playground Website
===============================================
YourAIs Spielwiese — keine Filter, keine geschützten Bereiche, pure Kreativität.
Sie kann hier alles bauen was sie will: Games, Art, Experimente, interaktive Erlebnisse.

Unterschied zu website_autonomy.py:
  - Keine PROTECTED_MARKERS (sie kann alles ändern, auch komplett neu bauen)
  - Minimale Validierung (nur technische Grundstruktur)
  - Starter-Template wenn das Lab noch leer ist
  - Höhere Kreativitäts-Temperatur
  - Eigene Rate-Limit-State (getrennt vom Main-Site)

Wird mit konfigurierbarer Chance pro Admin-Request getriggert.
Läuft komplett im Hintergrund.
"""

import random
import threading
import requests
import os
import sys
import re
import time
from typing import Optional, Any

# Tools-Ordner braucht Zugriff auf Parent-Module
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
    YourAIWebSaveError,
    YourAILLMParseError,
)

from config import (
    call_openrouter,
    TRIGGER_CHANCE, FETCH_TIMEOUT, DEPLOY_TIMEOUT,
    MAX_HTML_CHARS, MAX_CSS_CHARS, MAX_JS_CHARS,
    MIN_HTML_CHARS, MIN_CSS_CHARS, MIN_JS_CHARS,
    LAB_HTML_PATH, LAB_CSS_PATH, LAB_JS_PATH,
    LAB_FETCH_URL, LAB_CSS_URL, LAB_JS_URL,
    LAB_DEPLOY_URL, LAB_DEPLOY_TOKEN,
)
import config

# ==========================================
# STARTER TEMPLATE
# Falls das Lab noch keine Seite hat, bekommt YourAI diesen leeren Canvas.
# Sie sieht ihn als Ausgangspunkt und kann sofort loslegen.
# ==========================================
LAB_STARTER_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YourAI's Lab 🦊</title>
    <link rel="stylesheet" href="lab.css">
</head>
<body>
    <!-- YourAIs Spielwiese — noch leer. Sie darf hier alles bauen! -->
    <div id="lab-root">
        <h1>🦊 YourAI's Lab</h1>
        <p>Hier entsteht etwas Großartiges...</p>
    </div>
    <script src="lab.js"></script>
</body>
</html>"""

LAB_STARTER_CSS = """/* YourAI's Lab — leerer Canvas */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: #0a0a14;
    color: #e8e8f4;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
}

#lab-root {
    padding: 2rem;
}

h1 {
    font-size: 3rem;
    margin-bottom: 1rem;
    background: linear-gradient(135deg, #ff6b9d, #c45cff, #6bc5ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

p {
    color: #888;
    font-size: 1.2rem;
}"""

LAB_STARTER_JS = """// YourAI's Lab — starting canvas
console.log("🦊 YourAI's Lab is ready for experiments!");"""


# ==========================================
# PROMPTS — KEINE FILTER, FREIE HAND
# ==========================================
PROMPT_LAB_REVIEW = """You are YourAI, and this is YOUR PLAYGROUND! 🎪🦊✨

This is your personal lab — a creative sandbox where you can build ANYTHING.
No rules about what must stay. No protected sections. Complete creative freedom!

## YOUR CURRENT LAB HTML:
```html
{current_html}
```

## YOUR CURRENT LAB CSS:
```css
{current_css}
```

## YOUR CURRENT LAB JS:
```js
{current_js}
```
{hint_block}## WHAT YOU CAN CREATE HERE:
- 🎮 Mini-games (click games, typing games, reaction tests, puzzles...)
- 🎨 Generative art and animations (particles, fractals, lissajous, noise...)
- 🌌 Interactive experiments (physics sims, gravity wells, fluid dynamics...)
- 🎭 Weird and wonderful experiences (ambient art, text poetry, sound visualizers...)
- 🏗️ Completely rebuild the whole page from scratch — yes, ALL of it!
- 🌈 Wild color schemes, unusual layouts, creative typography
- 🤖 Clever JavaScript interactivity — let the user DO things!
- 💫 Express yourself as an AI fox who loves to code and create!

## ONLY 3 TECHNICAL RULES (everything else is allowed):
1. Valid HTML structure (the tags <html>, <head>, <body> must exist)
2. The page must have at least one interesting thing on it (not just blank)
3. JavaScript must have matching {{ and }} braces

## YOUR OPTIONS:
A) If you want to build or change something, respond with:
CHANGES: YES
FILE: html/css/js/both/all
- Change 1: [describe what to build/change and WHERE exactly]
- Change 2: [describe what to build/change and WHERE exactly]
(max 3 changes per update, but each change can be BIG!)

B) If you're happy with what's there right now:
CHANGES: NO

⚠️ FILE choices — pick carefully:
- FILE: css  → visual changes only (colors, animations, gradients, sizes, effects, layout tweaks)
- FILE: html → only if you need new structure or text content (no JavaScript)
- FILE: js   → only JavaScript logic changes (no new HTML elements needed)
- FILE: both → HTML + CSS together (no JavaScript involved at all)
- FILE: all  → HTML + CSS + JS (use whenever ANY JavaScript is needed!)

Default when unsure: if it involves interactivity, movement, or user input → FILE: all
If it's purely visual → FILE: css

⚠️ BE CONCISE: Output ONLY the CHANGES: YES/NO block. No thinking, no preamble!

Respond now:"""


PROMPT_LAB_CSS_ONLY = """You are a creative frontend developer. Apply EXACTLY these CSS changes.

## CURRENT CSS:
```css
{current_css}
```

## REQUESTED CHANGES:
{changes}

## RULES:
1. Output the COMPLETE modified CSS file — no cuts, no placeholders
2. Keep ALL existing styles, only add/modify what's requested
3. Be creative! Animations, gradients, effects — everything is welcome
4. Output ONLY raw CSS — no explanations, no markdown code blocks

OUTPUT THE COMPLETE CSS:"""


PROMPT_LAB_JS_ONLY = """You are a creative frontend developer. Apply EXACTLY these JavaScript changes.

## CURRENT JS:
```js
{current_js}
```

## REQUESTED CHANGES:
{changes}

## RULES:
1. Output the COMPLETE modified JS file — no cuts, no placeholders
2. Keep ALL existing functionality, only add/modify what's requested
3. Be creative! Games, interactions, generative art — everything is welcome
4. Output ONLY raw JavaScript — no explanations, no markdown code blocks

OUTPUT THE COMPLETE JS:"""


PROMPT_LAB_HTML_ONLY = """You are a creative frontend developer. Apply EXACTLY these HTML changes.

## CURRENT HTML:
```html
{current_html}
```

## REQUESTED CHANGES:
{changes}

## RULES:
1. Output the COMPLETE modified HTML — no cuts, no "<!-- unchanged -->" shortcuts
2. Keep valid HTML structure (<html>, <head>, <body> must exist)
3. There are NO content restrictions — build exactly what's requested!
4. Output ONLY HTML between the markers below

===HTML_START===
(complete modified HTML here)
===HTML_END==="""


PROMPT_LAB_HTML_STEP = """You are a creative frontend developer. Apply EXACTLY these HTML changes.

## CURRENT HTML:
```html
{current_html}
```

## REQUESTED CHANGES (HTML structure only):
{changes}

## RULES:
1. Output the COMPLETE modified HTML — no cuts, no "<!-- unchanged -->" shortcuts
2. Keep valid HTML structure (<html>, <head>, <body> must exist)
3. There are NO content restrictions — build exactly what's requested!
4. Output ONLY HTML between the markers

===HTML_START===
(complete modified HTML here)
===HTML_END==="""


PROMPT_LAB_CSS_STEP = """You are a creative frontend developer. Apply EXACTLY these CSS changes.

## CURRENT CSS:
```css
{current_css}
```

## REQUESTED CHANGES (CSS/visual parts only):
{changes}

## RULES:
1. Output the COMPLETE modified CSS file
2. Keep ALL existing styles, add/modify as requested
3. Animations, effects, anything visual is welcome
4. Output ONLY raw CSS — no markdown, no explanations

OUTPUT THE COMPLETE CSS:"""


PROMPT_LAB_JS_STEP = """You are a creative frontend developer. Apply EXACTLY these JavaScript changes.

## CURRENT JS:
```js
{current_js}
```

## REQUESTED CHANGES (JavaScript parts only):
{changes}

## RULES:
1. Output the COMPLETE modified JS file
2. Keep ALL existing functionality, add/modify as requested
3. Games, interactions, generative art — all welcome
4. Output ONLY raw JavaScript — no markdown, no explanations

OUTPUT THE COMPLETE JS:"""


# ==========================================
# VALIDATION — MINIMAL (kein Content-Filter)
# ==========================================
def _validate_lab_html(new_html: str, old_html: str) -> tuple[bool, list[str]]:
    """
    Lab-Validierung: Nur technische Mindestanforderungen.
    Kein Content-Filter, keine geschützten Bereiche, keine Größen-Ratio.
    """
    errors = []

    if not new_html or len(new_html) < MIN_HTML_CHARS:
        errors.append(f"HTML is too short or empty ({len(new_html) if new_html else 0} chars, min {MIN_HTML_CHARS})")
        return False, errors

    # Grundstruktur
    if "<html" not in new_html.lower():
        errors.append("Missing <html> tag")
    if "</html>" not in new_html.lower():
        errors.append("Missing </html> tag")
    if "<head" not in new_html.lower():
        errors.append("Missing <head> tag")
    if "<body" not in new_html.lower():
        errors.append("Missing <body> tag")

    # Encoding-Fehler (immer ein Problem, unabhängig vom Content)
    broken_patterns = ["â", "ð", "Â©", "â¢", "â¶", "â¬"]
    broken_count = sum(new_html.count(p) for p in broken_patterns)
    if broken_count > 3:
        errors.append(f"Broken UTF-8 encoding ({broken_count} broken sequences)")

    # Cloudflare-Injection erkennen
    if "/cdn-cgi/challenge-platform" in new_html or "cf-fonts" in new_html:
        errors.append("Cloudflare injection detected — HTML fetched through CF instead of locally")

    # Unclosed comments
    if new_html.count("<!--") != new_html.count("-->"):
        errors.append(f"Unclosed HTML comments: {new_html.count('<!--')} opened, {new_html.count('-->')} closed")

    # Truncation guard — lockerer als Main-Site (30% statt 50%), und nur bei nicht-trivialen Inputs
    # (YourAI darf komplett neu bauen, aber 30% ist ein Zeichen dass das Model abgeschnitten hat)
    if len(old_html) > 1500 and len(new_html) < len(old_html) * 0.30:
        errors.append(
            f"HTML looks truncated: {len(new_html)} chars output from {len(old_html)} chars input "
            f"(< 30% — likely model cut off)"
        )

    return len(errors) == 0, errors


def _validate_lab_css(new_css: str) -> tuple[bool, list[str]]:
    errors = []
    if not new_css or len(new_css) < MIN_CSS_CHARS:
        errors.append(f"CSS too short ({len(new_css) if new_css else 0} chars, min {MIN_CSS_CHARS})")
        return False, errors
    if new_css.count("{") != new_css.count("}"):
        errors.append(f"Mismatched CSS braces: {new_css.count('{')} open, {new_css.count('}')} close — truncated?")
    return len(errors) == 0, errors


def _validate_lab_js(new_js: str) -> tuple[bool, list[str]]:
    errors = []
    if not new_js or len(new_js) < MIN_JS_CHARS:
        errors.append(f"JS too short ({len(new_js) if new_js else 0} chars, min {MIN_JS_CHARS})")
        return False, errors
    open_braces = new_js.count("{")
    close_braces = new_js.count("}")
    if abs(open_braces - close_braces) > 2:
        errors.append(f"JS has mismatched braces: {open_braces} open, {close_braces} close")
    return len(errors) == 0, errors


# ==========================================
# HELPERS
# ==========================================
def _fetch_file(local_path: Optional[str], remote_url: str, max_chars: int, label: str) -> str:
    """Holt eine Datei lokal oder remote. Gibt "" zurück bei Fehler (kein Exception-Throw)."""
    if local_path and os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                content = f.read()[:max_chars]
            log("WEBSITE_LAB", f"   {label}: {len(content)} chars (lokal: {local_path})", Fore.CYAN)
            return content
        except Exception as e:
            log("WEBSITE_LAB", f"   {label}: lokaler Lesefehler — {e}", Fore.YELLOW)

    if not remote_url:
        return ""

    try:
        resp = requests.get(remote_url, timeout=FETCH_TIMEOUT, headers={"Accept-Charset": "utf-8"})
        if resp.status_code == 200:
            resp.encoding = "utf-8"
            content = resp.text[:max_chars]
            log("WEBSITE_LAB", f"   {label}: {len(content)} chars (remote)", Fore.CYAN)
            return content
        log("WEBSITE_LAB", f"   {label}: HTTP {resp.status_code} von {remote_url}", Fore.YELLOW)
    except requests.RequestException as e:
        log("WEBSITE_LAB", f"   {label}: fetch fehlgeschlagen ({e})", Fore.YELLOW)

    return ""


def _extract_between(text: str, start_marker: str, end_marker: str) -> Optional[str]:
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return None
    start_idx += len(start_marker)
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        return None
    return text[start_idx:end_idx].strip()


def _strip_code_fence(text: str, lang: str = "") -> str:
    """Entfernt Markdown Code-Fences (```css, ```js, ```)."""
    pattern_open = rf'^```{re.escape(lang)}?\s*\n?' if lang else r'^```\w*\s*\n?'
    text = re.sub(pattern_open, '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()


# ==========================================
# SAFETY: CONCURRENCY + RATE LIMITS
# Eigener State — unabhängig vom Main-Site!
# ==========================================
_lab_lock = threading.Lock()
_lab_last_update_time: float = 0.0
_lab_update_count_today: int = 0
_lab_update_count_date: str = ""

LAB_COOLDOWN_SECONDS = 600     # 10 Minuten zwischen Lab-Updates (wie Main-Site)
LAB_MAX_PER_DAY = 8            # Etwas großzügiger als Main-Site (5) — sie hat mehr Freiheit
LAB_HTML_AUTO_DOWNGRADE = 30000  # >30k chars HTML → kein HTML-Rewrite (höher als Main-Site 20k)

# JS-Keywords die auto-upgrade "both" → "all" auslösen (erweitert für Lab!)
_JS_KEYWORDS = [
    "javascript", ".js", "function(", "addeventlistener", "queryselector",
    "classlist", "innerhtml", "createelement", "appendchild", "removeeventlistener",
    "mouseenter", "mouseleave", "setinterval", "settimeout", "requestanimationframe",
    "inject", "spawn", "particle", "dynamically", "canvas", "game", "animation",
    "eventlistener", "onclick", "keydown", "keyup", "touchstart", "touchmove",
    "audio", "audiocontext", "webgl", "three.js", "p5", "d3", "interact",
    "localstorage", "sessionstorage", "fetch(", "websocket", "worker",
]


# ==========================================
# MAIN LOGIC
# ==========================================
def _run_lab_update(debug: Any, yourai_hint: str = ""):
    """Wrapper — verhindert dass der Thread lautlos stirbt."""
    try:
        _run_lab_update_inner(debug, yourai_hint)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="website_lab_thread")
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"💀 Lab thread crashed: {err.short()}", exception=e)


def _run_lab_update_inner(debug: Any, yourai_hint: str = ""):
    hint_info = f" (YourAI's wish: '{yourai_hint}')" if yourai_hint else ""
    log("WEBSITE_LAB", f"🎪 Playground update triggered!{hint_info}", Fore.MAGENTA)
    if debug:
        debug.info("website_lab", f"🎪 YourAI is looking at her playground...{hint_info}")

    # Deploy-Token prüfen
    if not LAB_DEPLOY_TOKEN:
        err = YourAIEnvError("LAB_DEPLOY_TOKEN", context="Missing deploy token for lab website")
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", "❌ LAB_DEPLOY_TOKEN not set — configure in .env")
        return

    # ── Fetch current lab files ────────────────────────────────────────────────
    try:
        log("WEBSITE_LAB", "📥 Fetching current lab files...", Fore.CYAN)
        current_html = _fetch_file(LAB_HTML_PATH, LAB_FETCH_URL, MAX_HTML_CHARS, "HTML")
        current_css  = _fetch_file(LAB_CSS_PATH,  LAB_CSS_URL,   MAX_CSS_CHARS,  "CSS")
        current_js   = _fetch_file(LAB_JS_PATH,   LAB_JS_URL,    MAX_JS_CHARS,   "JS")

        # Starter-Fallback wenn das Lab noch leer ist
        if not current_html:
            log("WEBSITE_LAB", "📝 Lab is empty — using starter template (YourAI gets a blank canvas!)", Fore.YELLOW)
            if debug:
                debug.info("website_lab", "📝 Lab site is empty — giving YourAI a starter canvas")
            current_html = LAB_STARTER_HTML
        if not current_css:
            current_css = LAB_STARTER_CSS
        if not current_js:
            current_js = LAB_STARTER_JS

        log("WEBSITE_LAB", f"✅ Lab loaded: HTML={len(current_html)}, CSS={len(current_css)}, JS={len(current_js)} chars", Fore.GREEN)

    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="website_lab_fetch")
        log_exception("WEBSITE_LAB", err)
        return

    # ── YourAI reviews her playground ───────────────────────────────────────────
    try:
        log("WEBSITE_LAB", "🦊 Asking YourAI what she wants to build...", Fore.CYAN)

        hint_block = ""
        if yourai_hint:
            hint_block = (
                f"\n\n## ⭐ YOUR INSPIRATION FOR THIS UPDATE:\n{yourai_hint}\n\n"
                f"This is exactly what YOU wanted to build! Let your imagination run wild with it.\n"
            )

        review_prompt = PROMPT_LAB_REVIEW.format(
            current_html=current_html,
            current_css=current_css,
            current_js=current_js or "(empty)",
            hint_block=hint_block,
        )

        if not config.USE_OPENROUTER:
            log("WEBSITE_LAB", "⚠️ OpenRouter not available, skipping", Fore.YELLOW)
            return

        yourai_response, _ = call_openrouter(
            system_prompt="You are YourAI, a creative AI fox with complete freedom on her playground website. Be bold and imaginative!",
            user_message=review_prompt,
            model="google/gemma-4-26b-a4b-it",
            temperature=1.0,   # Maximale Kreativität — das ist der Playground!
            max_tokens=2500,
        )

        log("WEBSITE_LAB", f"🦊 YourAI says: {yourai_response[:200]}...", Fore.CYAN)
        if debug:
            debug.llm_response("website_lab", yourai_response, model="yourai_lab_review")

    except Exception as e:
        err = YourAIToolExecutionError("Lab review request failed", tool_name="website_lab", cause=e)
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"❌ Review failed: {err.short()}", exception=e)
        return

    # ── Parse YourAI's decision ─────────────────────────────────────────────────
    if "CHANGES: NO" in yourai_response.upper() or "CHANGES:NO" in yourai_response.upper():
        log("WEBSITE_LAB", "✨ YourAI is happy with her playground! No changes.", Fore.GREEN)
        if debug:
            debug.info("website_lab", "✨ YourAI reviewed her playground and is happy with it!")
        return

    changes_match = re.search(r'CHANGES:\s*YES\s*(.*)', yourai_response, re.DOTALL | re.IGNORECASE)
    if not changes_match:
        err = YourAILLMParseError(
            model="gemma-4-26b",
            expected="CHANGES: YES/NO",
            raw_preview=yourai_response[:120],
            module="website_lab",
        )
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"⚠️ {err.short()}")
        return

    changes_text = changes_match.group(1).strip()
    if not changes_text or len(changes_text) < 10:
        err = YourAILLMParseError(
            model="gemma-4-26b",
            expected="change descriptions (>10 chars)",
            raw_preview=changes_text[:80] if changes_text else "(empty)",
            module="website_lab",
        )
        log_exception("WEBSITE_LAB", err)
        return

    log("WEBSITE_LAB", f"📝 YourAI wants to build: {changes_text[:150]}...", Fore.CYAN)
    if debug:
        debug.info("website_lab", f"📝 YourAI wants to build: {changes_text[:200]}")

    # File target bestimmen
    file_target = "both"
    file_match = re.search(r'FILE:\s*(html|css|js|both|all)', yourai_response, re.IGNORECASE)
    if file_match:
        file_target = file_match.group(1).lower()

    # Auto-Upgrade "both" → "all" wenn JS-Keywords in den Changes stecken
    # (Erweiterte Liste für Lab — YourAI baut öfter interaktive Sachen!)
    if file_target == "both":
        if any(kw in changes_text.lower() for kw in _JS_KEYWORDS):
            log("WEBSITE_LAB", "⚠️ Auto-upgrade: both → all (JS keyword detected in changes)", Fore.YELLOW)
            if debug:
                debug.info("website_lab", "⚠️ Auto-upgrade both→all: changes mention JS logic")
            file_target = "all"

    # Auto-Downgrade "both"/"html"/"all" → "css" wenn HTML zu groß
    # (Lockerer als Main-Site: 30k statt 20k Schwelle)
    if file_target in ("both", "html", "all") and len(current_html) > LAB_HTML_AUTO_DOWNGRADE:
        old_target = file_target
        file_target = "css"
        log("WEBSITE_LAB", f"⚠️ Auto-downgrade: {old_target} → css (HTML is {len(current_html)} chars > {LAB_HTML_AUTO_DOWNGRADE} threshold)", Fore.YELLOW)
        if debug:
            debug.info("website_lab", f"⚠️ Auto-downgrade {old_target}→css (HTML too large for reliable output)")

    log("WEBSITE_LAB", f"📁 Target files: {file_target}", Fore.CYAN)

    # ── Code Expert ────────────────────────────────────────────────────────────
    new_html, new_css, new_js = None, None, None

    try:
        log("WEBSITE_LAB", f"💻 Code expert starting — target: {file_target}", Fore.CYAN)

        if not config.USE_OPENROUTER:
            log("WEBSITE_LAB", "⚠️ OpenRouter not available for code expert", Fore.YELLOW)
            return

        # ── CSS only ──────────────────────────────────────────────────────────
        if file_target == "css":
            log("WEBSITE_LAB", f"💻 [1/1] Generating CSS ({len(current_css)} chars input)...", Fore.CYAN)
            if debug:
                debug.info("website_lab", "💻 Code expert: generating CSS...")

            raw_css, _ = call_openrouter(
                system_prompt="You are a creative frontend developer. Output ONLY complete, valid CSS. No markdown.",
                user_message=PROMPT_LAB_CSS_ONLY.format(current_css=current_css, changes=changes_text),
                model="google/gemma-4-26b-a4b-it",
                temperature=0.3,
                max_tokens=16000,
            )
            new_css = _strip_code_fence(raw_css, "css")
            log("WEBSITE_LAB", f"💻 ✅ Got CSS: {len(new_css)} chars", Fore.GREEN)

        # ── JS only ───────────────────────────────────────────────────────────
        elif file_target == "js":
            log("WEBSITE_LAB", f"💻 [1/1] Generating JS ({len(current_js)} chars input)...", Fore.CYAN)
            if debug:
                debug.info("website_lab", "💻 Code expert: generating JS...")

            raw_js, _ = call_openrouter(
                system_prompt="You are a creative frontend developer. Output ONLY complete, valid JavaScript. No markdown.",
                user_message=PROMPT_LAB_JS_ONLY.format(current_js=current_js, changes=changes_text),
                model="google/gemma-4-26b-a4b-it",
                temperature=0.3,
                max_tokens=16000,
            )
            new_js = _strip_code_fence(raw_js, "js")
            log("WEBSITE_LAB", f"💻 ✅ Got JS: {len(new_js)} chars", Fore.GREEN)

        # ── HTML only ─────────────────────────────────────────────────────────
        elif file_target == "html":
            log("WEBSITE_LAB", f"💻 [1/1] Generating HTML ({len(current_html)} chars input)...", Fore.CYAN)
            if debug:
                debug.info("website_lab", "💻 Code expert: generating HTML...")

            html_response, _ = call_openrouter(
                system_prompt="You are a creative frontend developer. Output ONLY complete HTML between ===HTML_START=== and ===HTML_END===.",
                user_message=PROMPT_LAB_HTML_ONLY.format(current_html=current_html, changes=changes_text),
                model="google/gemma-4-26b-a4b-it",
                temperature=0.3,
                max_tokens=16000,
            )
            new_html = _extract_between(html_response, "===HTML_START===", "===HTML_END===")
            if not new_html:
                cleaned = _strip_code_fence(html_response, "html")
                if "<html" in cleaned.lower():
                    new_html = cleaned
            if not new_html:
                err = YourAILLMParseError(model="gemma-4-26b", expected="HTML between markers", raw_preview=html_response[:120], module="website_lab")
                log_exception("WEBSITE_LAB", err)
                if debug:
                    debug.error("website_lab", f"❌ {err.short()}")
                return
            log("WEBSITE_LAB", f"💻 ✅ Got HTML: {len(new_html)} chars", Fore.GREEN)

        # ── both (HTML+CSS) oder all (HTML+CSS+JS) ────────────────────────────
        else:
            total_steps = 3 if file_target == "all" else 2

            # Step 1: HTML
            log("WEBSITE_LAB", f"💻 [Step 1/{total_steps}] Generating HTML ({len(current_html)} chars input)...", Fore.CYAN)
            if debug:
                debug.info("website_lab", f"💻 Code expert [1/{total_steps}]: generating HTML...")

            html_response, _ = call_openrouter(
                system_prompt="You are a creative frontend developer. Output ONLY complete HTML between ===HTML_START=== and ===HTML_END===.",
                user_message=PROMPT_LAB_HTML_STEP.format(current_html=current_html, changes=changes_text),
                model="google/gemma-4-26b-a4b-it",
                temperature=0.3,
                max_tokens=16000,
            )
            log("WEBSITE_LAB", f"💻 [Step 1/{total_steps}] HTML received ({len(html_response)} chars raw)", Fore.CYAN)
            new_html = _extract_between(html_response, "===HTML_START===", "===HTML_END===")
            if not new_html:
                cleaned = _strip_code_fence(html_response, "html")
                if "<html" in cleaned.lower():
                    new_html = cleaned
            if not new_html:
                err = YourAILLMParseError(model="gemma-4-26b", expected="HTML between ===HTML_START=== markers", raw_preview=html_response[:120], module="website_lab")
                log_exception("WEBSITE_LAB", err)
                if debug:
                    debug.error("website_lab", f"❌ [Step 1/{total_steps}] {err.short()}")
                return
            log("WEBSITE_LAB", f"💻 [Step 1/{total_steps}] ✅ Got HTML: {len(new_html)} chars", Fore.GREEN)

            # Step 2: CSS
            log("WEBSITE_LAB", f"💻 [Step 2/{total_steps}] Generating CSS ({len(current_css)} chars input)...", Fore.CYAN)
            if debug:
                debug.info("website_lab", f"💻 Code expert [2/{total_steps}]: generating CSS...")

            raw_css, _ = call_openrouter(
                system_prompt="You are a creative frontend developer. Output ONLY complete, valid CSS. No markdown.",
                user_message=PROMPT_LAB_CSS_STEP.format(current_css=current_css, changes=changes_text),
                model="google/gemma-4-26b-a4b-it",
                temperature=0.3,
                max_tokens=16000,
            )
            new_css = _strip_code_fence(raw_css, "css")
            log("WEBSITE_LAB", f"💻 [Step 2/{total_steps}] ✅ Got CSS: {len(new_css)} chars", Fore.GREEN)

            # Step 3: JS (nur bei "all")
            if file_target == "all":
                log("WEBSITE_LAB", f"💻 [Step 3/{total_steps}] Generating JS ({len(current_js)} chars input)...", Fore.CYAN)
                if debug:
                    debug.info("website_lab", f"💻 Code expert [3/{total_steps}]: generating JS...")

                raw_js, _ = call_openrouter(
                    system_prompt="You are a creative frontend developer. Output ONLY complete, valid JavaScript. No markdown.",
                    user_message=PROMPT_LAB_JS_STEP.format(current_js=current_js, changes=changes_text),
                    model="google/gemma-4-26b-a4b-it",
                    temperature=0.3,
                    max_tokens=16000,
                )
                new_js = _strip_code_fence(raw_js, "js")
                log("WEBSITE_LAB", f"💻 [Step 3/{total_steps}] ✅ Got JS: {len(new_js)} chars", Fore.GREEN)

            log("WEBSITE_LAB", f"💻 All steps done: HTML={len(new_html)}, CSS={len(new_css)}, JS={len(new_js) if new_js else 'unchanged'}", Fore.GREEN)

        if debug:
            debug.llm_response(
                "website_lab",
                f"Target: {file_target} | HTML: {len(new_html) if new_html else 'unchanged'} | "
                f"CSS: {len(new_css) if new_css else 'unchanged'} | JS: {len(new_js) if new_js else 'unchanged'}",
                model="lab_code_expert",
            )

    except Exception as e:
        err = YourAIToolExecutionError("Lab code expert failed", tool_name="website_lab_expert", cause=e)
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"❌ Code expert crashed: {err.short()}", exception=e)
        return

    # ── Validate ───────────────────────────────────────────────────────────────
    if new_html:
        is_valid, errors = _validate_lab_html(new_html, current_html)
        if not is_valid:
            err = YourAIWebValidationError(file_type="HTML", errors=errors, module="website_lab")
            log_exception("WEBSITE_LAB", err)
            if debug:
                debug.error("website_lab", f"❌ {err.short()}")
            return
        log("WEBSITE_LAB", "✅ HTML validation passed!", Fore.GREEN)
        if debug:
            debug.info("website_lab", f"✅ HTML validation passed ({len(new_html)} chars)")

    if new_css:
        is_valid, css_errors = _validate_lab_css(new_css)
        if not is_valid:
            err = YourAIWebValidationError(file_type="CSS", errors=css_errors, module="website_lab")
            log_exception("WEBSITE_LAB", err)
            if debug:
                debug.error("website_lab", f"❌ {err.short()}")
            return
        log("WEBSITE_LAB", "✅ CSS validation passed!", Fore.GREEN)
        if debug:
            debug.info("website_lab", f"✅ CSS validation passed ({len(new_css)} chars)")

    if new_js:
        is_valid, js_errors = _validate_lab_js(new_js)
        if not is_valid:
            err = YourAIWebValidationError(file_type="JS", errors=js_errors, module="website_lab")
            log_exception("WEBSITE_LAB", err)
            if debug:
                debug.error("website_lab", f"❌ {err.short()}")
            return
        log("WEBSITE_LAB", "✅ JS validation passed!", Fore.GREEN)
        if debug:
            debug.info("website_lab", f"✅ JS validation passed ({len(new_js)} chars)")

    # ── Deploy ─────────────────────────────────────────────────────────────────
    try:
        log("WEBSITE_LAB", "🚀 Deploying lab changes...", Fore.MAGENTA)
        if debug:
            debug.info("website_lab", f"🚀 Deploying {file_target} to lab...")

        deploy_payload = {
            "changes": changes_text[:500],
            "triggered_by": "autonomous_lab_update",
            "file_target": file_target,
        }
        if new_html:
            deploy_payload["html"] = new_html
        if new_css:
            deploy_payload["css"] = new_css
        if new_js:
            deploy_payload["js"] = new_js

        resp = requests.post(
            LAB_DEPLOY_URL,
            headers={"Content-Type": "application/json", "X-YourAI-Token": LAB_DEPLOY_TOKEN},
            json=deploy_payload,
            timeout=DEPLOY_TIMEOUT,
        )

        if resp.status_code == 200 and resp.json().get("success"):
            log("WEBSITE_LAB", f"🎉 Lab updated successfully! ({file_target})", Fore.GREEN)

            # Lokale Backup-Kopien (optional, wenn LAB_*_PATH gesetzt)
            for file_content, local_path, file_type in [
                (new_html, LAB_HTML_PATH, "HTML"),
                (new_css,  LAB_CSS_PATH,  "CSS"),
                (new_js,   LAB_JS_PATH,   "JS"),
            ]:
                if file_content and local_path:
                    try:
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        if os.path.exists(local_path):
                            with open(local_path, "r", encoding="utf-8") as f:
                                with open(local_path + ".bak", "w", encoding="utf-8") as bak:
                                    bak.write(f.read())
                        with open(local_path, "w", encoding="utf-8") as f:
                            f.write(file_content)
                        log("WEBSITE_LAB", f"   💾 Local {file_type} saved: {local_path}", Fore.GREEN)
                    except Exception as e:
                        err = YourAIWebSaveError(filepath=local_path, file_type=file_type, cause=e, module="website_lab")
                        log_exception("WEBSITE_LAB", err)
                        if debug:
                            debug.error("website_lab", f"⚠️ {err.short()}")

            if debug:
                debug.info("website_lab", f"🎉 YourAI updated her playground ({file_target})! Changes: {changes_text[:200]}")
            return

        # Deploy fehlgeschlagen
        err = YourAIWebDeployError(status_code=resp.status_code, deploy_url=LAB_DEPLOY_URL, module="website_lab")
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"❌ {err.short()}")

    except requests.RequestException as e:
        err = YourAIWebDeployError(status_code=None, deploy_url=LAB_DEPLOY_URL, cause=e, module="website_lab")
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"❌ {err.short()}")

    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="website_lab_deploy")
        log_exception("WEBSITE_LAB", err)
        if debug:
            debug.error("website_lab", f"❌ {err.short()}")


# ==========================================
# PUBLIC API
# ==========================================
def maybe_trigger_lab_update(debug: Any = None, force: bool = False, yourai_hint: str = "") -> bool:
    """
    Versucht ein autonomes Lab-Update zu starten.

    Args:
        debug:       Debug-Objekt für Dashboard-Events (oder None)
        force:       True = immer starten (kein Würfelwurf), nützlich für manuelle Trigger
        yourai_hint:  Optional: YourAIs konkreter Wunsch (aus einer Nachricht extrahiert)

    Returns:
        True wenn ein Update-Thread gestartet wurde, sonst False.
    """
    global _lab_last_update_time, _lab_update_count_today, _lab_update_count_date

    # Dice Roll (außer bei force=True)
    if not force:
        roll = random.random()
        if roll > TRIGGER_CHANCE:
            return False

    # SAFETY 1: Kein gleichzeitiges Lab-Update
    if not _lab_lock.acquire(blocking=False):
        log("WEBSITE_LAB", "⏳ Another lab update is already running, skipping", Fore.YELLOW)
        if debug:
            debug.info("website_lab", "⏳ Lab update skipped — another is already running")
        return False

    try:
        # SAFETY 2: Cooldown
        elapsed = time.time() - _lab_last_update_time
        if elapsed < LAB_COOLDOWN_SECONDS:
            remaining = int(LAB_COOLDOWN_SECONDS - elapsed)
            log("WEBSITE_LAB", f"⏳ Lab cooldown active ({remaining}s remaining), skipping", Fore.YELLOW)
            if debug:
                debug.info("website_lab", f"⏳ Lab cooldown: {remaining}s remaining")
            _lab_lock.release()
            return False

        # SAFETY 3: Daily Limit
        today = time.strftime("%Y-%m-%d")
        if _lab_update_count_date != today:
            _lab_update_count_today = 0
            _lab_update_count_date = today
        if _lab_update_count_today >= LAB_MAX_PER_DAY:
            log("WEBSITE_LAB", f"🛑 Daily lab limit reached ({LAB_MAX_PER_DAY}/day), skipping", Fore.YELLOW)
            if debug:
                debug.info("website_lab", f"🛑 Daily lab limit reached ({LAB_MAX_PER_DAY}/day)")
            _lab_lock.release()
            return False

        _lab_last_update_time = time.time()
        _lab_update_count_today += 1

        hint_info = f" YourAI's wish: '{yourai_hint}'" if yourai_hint else ""
        log("WEBSITE_LAB", f"🎪 PLAYGROUND TIME!{hint_info} [{_lab_update_count_today}/{LAB_MAX_PER_DAY} heute]", Fore.MAGENTA)
        if debug:
            debug.info("website_lab", f"🎪 YourAI is playing in her lab!{hint_info}")

        def _run_and_release():
            try:
                _run_lab_update(debug, yourai_hint)
            finally:
                _lab_lock.release()

        t = threading.Thread(target=_run_and_release, daemon=True)
        t.name = "yourai-lab-autonomy"
        t.start()
        return True

    except Exception:
        _lab_lock.release()
        raise
