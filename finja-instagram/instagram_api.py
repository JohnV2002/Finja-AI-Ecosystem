# instagram_api.py
# Hybrid Proxy: Chrome + Playwright + FastAPI

"""
======================================================================
         Finja Instagram Reels – Container API
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Headless API container for Instagram Reels interaction.
  Connects to a headless Chromium browser via CDP, injects cookies
  for authenticated Instagram access, and exposes a REST API for:

  • Scrolling through Reels (next video + screenshot + metadata)
  • Liking the current video
  • Health/status checks
  • Wakeup (navigates to Reels) / Sleep (navigates to about:blank)

  NOTE: Uses Desktop Mode (Full HD) instead of Mobile Mode because
  ArrowDown navigation is more stable on the desktop layout for Reels.

======================================================================
"""

import os
import json
import base64
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright, Browser, Page

# ---- Config ----
CHROME_PORT = int(os.environ.get("CHROME_PORT", 9222))
API_PORT = int(os.environ.get("INSTAGRAM_API_PORT", 8061))

_SCRIPT_DIR = str(Path(__file__).parent)
COOKIES_JSON = os.environ.get("COOKIES_JSON", os.path.join(_SCRIPT_DIR, "cookies.json"))
COOKIES_TXT = os.environ.get("COOKIES_TXT", os.path.join(_SCRIPT_DIR, "www.instagram.com_cookies.txt"))
INSTAGRAM_TARGET_URL = os.environ.get("INSTAGRAM_TARGET_URL", "https://www.instagram.com/reels/")

_browser: Browser | None = None
_page: Page | None = None
_playwright = None

SAME_SITE_MAP = {
    "unspecified": "None",
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
}


# ==========================================
# Cookie Loader: JSON + TXT (Netscape)
# ==========================================

def _load_cookies_json(filepath: str) -> list[dict]:
    """Browser Extension JSON Export -> Playwright cookie format."""
    path = Path(filepath)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[COOKIES] JSON parse error: {e}")
        return []

    cookies = []
    for c in raw:
        if "partitionKey" in c:
            continue
        pw = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": SAME_SITE_MAP.get(c.get("sameSite", ""), "None"),
        }
        exp = c.get("expirationDate")
        if exp and exp > 0:
            pw["expires"] = int(exp)
        cookies.append(pw)
    return cookies


def _load_cookies_txt(filepath: str) -> list[dict]:
    """Netscape HTTP Cookie File (curl/wget format) -> Playwright cookie format."""
    path = Path(filepath)
    if not path.exists():
        return []
    cookies = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, path_val, secure, expires, name, value = parts[:7]
            pw = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_val,
                "secure": secure.upper() == "TRUE",
                "httpOnly": False,
                "sameSite": "None",
            }
            exp = int(expires)
            if exp > 0:
                pw["expires"] = exp
            cookies.append(pw)
    except Exception as e:
        print(f"[COOKIES] TXT parse error: {e}")
    return cookies


def _load_cookies() -> list[dict]:
    """Tries JSON first, then falls back to TXT."""
    cookies = _load_cookies_json(COOKIES_JSON)
    if cookies:
        print(f"[COOKIES] Loaded {len(cookies)} cookies from JSON")
        return cookies

    cookies = _load_cookies_txt(COOKIES_TXT)
    if cookies:
        print(f"[COOKIES] Loaded {len(cookies)} cookies from TXT (Netscape)")
        return cookies

    print("[COOKIES] No cookie file found! Instagram will require login.")
    return []


# ==========================================
# Lifespan: Connect to Chrome + Inject Cookies
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _browser, _page, _playwright
    print("[API] Connecting to Chrome via CDP...")

    pw = await async_playwright().start()
    _playwright = pw

    for attempt in range(10):
        try:
            _browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_PORT}")
            break
        except Exception as e:
            if attempt == 9:
                print(f"[API] ERROR: Chrome unreachable! {e}")
                raise
            await asyncio.sleep(1)

    context = _browser.contexts[0]
    pages = context.pages
    _page = pages[0] if pages else await context.new_page()

    # Inject cookies (but DO NOT navigate — /wakeup handles that)
    cookies = _load_cookies()
    if cookies:
        await context.add_cookies(cookies)
        print(f"[API] Cookies injected! Staying on about:blank until /wakeup is called.")
    else:
        print("[API] No cookies — Instagram without login.")

    print(f"[API] Ready! Sleeping on: {_page.url}")
    yield

    print("[API] Shutdown...")
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()


app = FastAPI(title="Finja Instagram Reels", lifespan=lifespan)


# ==========================================
# Popup Killer
# ==========================================

async def _dismiss_popups():
    """Dismiss Instagram Login nags, Cookie banners, and 'Get App' dialogs."""
    dismiss_selectors = [
        # Login popup
        "button:has-text('Nicht jetzt')",
        "button:has-text('Not Now')",
        "button:has-text('Not now')",
        # Cookie consent
        "button:has-text('Alle ablehnen')",
        "button:has-text('Decline optional cookies')",
        "button:has-text('Decline')",
        # App banner
        "button:has-text('Jetzt nicht')",
        "button:has-text('Cancel')",
    ]
    for sel in dismiss_selectors:
        try:
            btn = _page.locator(sel).first
            if await btn.is_visible(timeout=800):
                await btn.click()
                print(f"[API] Dismissed popup: {sel}")
                await asyncio.sleep(1)
        except Exception:
            pass


# ==========================================
# Endpoints
# ==========================================

@app.get("/health")
async def health():
    browser_ok = _browser is not None and _browser.is_connected()
    return {
        "status": "ok" if browser_ok else "degraded",
        "browser_connected": browser_ok,
        "current_url": _page.url if _page else None,
    }


@app.get("/status")
async def status():
    if not _page:
        raise HTTPException(503, "Browser not connected")
    return {
        "url": _page.url,
        "title": await _page.title(),
        "awake": "instagram.com" in (_page.url or ""),
    }


# ---- Wakeup: Open Instagram ----
@app.post("/wakeup")
async def wakeup():
    """
    Wakeup: about:blank -> instagram.com/reels/
    Cookies are already injected, we just need to navigate.
    Instagram only sees us as 'online' from this point forward.
    """
    if not _page:
        raise HTTPException(503, "Browser not connected")

    # Already awake?
    if "instagram.com" in _page.url:
        return {"status": "already_awake", "url": _page.url}

    print("[API] Wakeup! Navigating to Instagram Reels...")
    await _page.goto(INSTAGRAM_TARGET_URL, wait_until="domcontentloaded")
    await asyncio.sleep(4)

    # Dismiss login popups and cookie banners
    await _dismiss_popups()

    # Set focus for ArrowDown navigation
    await _page.mouse.click(500, 400)
    await asyncio.sleep(0.5)

    print(f"[API] Awake! URL: {_page.url}")
    return {"status": "awake", "url": _page.url}


# ---- Sleep: Return to about:blank ----
@app.post("/sleep")
async def sleep_endpoint():
    """
    Sleep: instagram.com -> about:blank
    Instagram sees us as 'offline' from this point forward.
    Prevents 24/7 presence on Reels.
    """
    if not _page:
        raise HTTPException(503, "Browser not connected")

    # Already sleeping?
    if "instagram.com" not in (_page.url or ""):
        return {"status": "already_sleeping", "url": _page.url}

    print("[API] Sleep! Returning to about:blank...")
    await _page.goto("about:blank", wait_until="domcontentloaded")
    await asyncio.sleep(0.5)

    print("[API] Sleeping. URL: about:blank")
    return {"status": "sleeping", "url": _page.url}


# ---- Scroll: Next Reel + Screenshot + Metadata ----
@app.post("/scroll")
async def scroll_next():
    """
    Buffer-Buster Scroll:
    1. Press ArrowDown
    2. Check if URL changed (indicates a new Reel)
    3. Retry up to 3x if Instagram buffers
    4. Return screenshot + metadata
    """
    if not _page:
        raise HTTPException(503, "Browser not connected")

    # Dismiss popups if any appeared
    await _dismiss_popups()

    url_before = _page.url
    await _page.keyboard.press("ArrowDown")

    # Instagram takes ~3s to switch URL + Video
    await asyncio.sleep(3)

    url_after = _page.url
    scrolled = url_before != url_after
    if not scrolled:
        print("[API] URL did not change — Reel might not have switched")

    # Scrape channel — ONLY the BOTTOMMOST visible one (= current Reel)
    try:
        channel = await _page.evaluate("""() => {
            const vh = window.innerHeight;
            const links = document.querySelectorAll(
                'a[aria-label^="Reels von"], a[aria-label^="Reels by"]'
            );
            let best = null;
            let maxY = -9999;
            for (const a of links) {
                const r = a.getBoundingClientRect();
                if (r.top >= -50 && r.top <= vh && r.width > 0 && r.top > maxY) {
                    maxY = r.top;
                    best = a;
                }
            }
            if (best) {
                const span = best.querySelector('span');
                if (span) return span.textContent.trim();
                const label = best.getAttribute('aria-label') || '';
                const m = label.match(/Reels (?:von|by) (.+)/);
                if (m) return m[1];
            }
            return '';
        }""") or "Unknown"
    except Exception as e:
        print(f"[API] Channel scrape error: {e}")
        channel = "Unknown"

    # Screenshot
    screenshot_bytes = await _page.screenshot(type="jpeg", quality=50)
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    return {
        "url": _page.url,
        "channel": channel,
        "screenshot_b64": screenshot_b64,
        "scrolled": scrolled,
    }


# ---- Like: Like the current Reel ----
@app.post("/like")
async def like_reel():
    """Click the like button (heart) of the current Reel."""
    if not _page:
        raise HTTPException(503, "Browser not connected")

    # Find like button via JS within the visible viewport
    # (prevents clicking the button from the previous Reel)
    result = await _page.evaluate("""() => {
        const labels = ['Gefällt mir', 'Like'];
        for (const label of labels) {
            const svgs = document.querySelectorAll(`svg[aria-label="${label}"]`);
            for (const svg of svgs) {
                const rect = svg.getBoundingClientRect();
                // Only target the like button in the visible area
                if (rect.top >= 0 && rect.top <= window.innerHeight && rect.width > 0) {
                    const btn = svg.closest('button, div[role="button"], span[role="button"]');
                    if (btn) {
                        btn.click();
                        return { liked: true, method: 'button' };
                    }
                }
            }
        }
        return { liked: false };
    }""")

    if result.get("liked"):
        await asyncio.sleep(1)
        return {"liked": True, "url": _page.url, "method": result.get("method")}

    return {"liked": False, "reason": "Like button not found in viewport"}


# ==========================================
# Run
# ==========================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")
