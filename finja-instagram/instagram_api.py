# instagram_api.py
# Hybrid Proxy: Chrome + Playwright + FastAPI

"""
======================================================================
         Finja Instagram Reels – Container API
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.2.0

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

----------------------------------------------------------------------
 New in v1.2.0:
----------------------------------------------------------------------
  • Structured FINJA errors (module finja-instagram): unreadable cookie
    file FINJA-105, Chrome unreachable FINJA-517, unexpected request
    failure FINJA-518, diagnostics probe FINJA-519
  • Analytics Contract sender (off unless ANALYTICS_ENABLED): lifecycle,
    CPU, RAM and errors to the Analytics Collector, which hands repeated
    errors to Flare
  • Owner-only GET /diagnostics/probe?token=… (INSTAGRAM_PROBE_TOKEN)

----------------------------------------------------------------------
 Changelog v1.1.0:
----------------------------------------------------------------------
  • Merged Production + GitHub tracks (2026-07-19)
  • Kept Production's domain-prefixed cookie filename default
    (www.instagram.com_cookies.json) instead of GitHub's generic
    cookies.json -- real Production files use this name, so adopting
    GitHub's default verbatim would have silently broken cookie loading

======================================================================
"""

import os
import json
import base64
import asyncio
import logging
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright, Browser, Error as PlaywrightError, Page

from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import (
    AnalyticsDeliveryError,
    AppError,
    InstagramApiUnexpectedError,
    InstagramChromeUnreachableError,
    InstagramCookiesInvalidError,
    InstagramDiagnosticsProbeError,
)
from reel_stats import like_rate

# ---- Config ----
CHROME_PORT = int(os.environ.get("CHROME_PORT", 9222))
API_PORT = int(os.environ.get("INSTAGRAM_API_PORT", 8061))

_SCRIPT_DIR = str(Path(__file__).parent)
COOKIES_JSON = os.environ.get("COOKIES_JSON", os.path.join(_SCRIPT_DIR, "www.instagram.com_cookies.json"))
COOKIES_TXT = os.environ.get("COOKIES_TXT", os.path.join(_SCRIPT_DIR, "www.instagram.com_cookies.txt"))
INSTAGRAM_TARGET_URL = os.environ.get("INSTAGRAM_TARGET_URL", "https://www.instagram.com/reels/")

LOGGER = logging.getLogger("finja_instagram")
PROJECT_ROOT = Path(__file__).resolve().parent


def _report_analytics_problem(problem: dict) -> None:
    error = AnalyticsDeliveryError(str(problem.get("message") or "analytics delivery failed"),
                                   reason=problem.get("reason"), retry=problem.get("retry"))
    LOGGER.warning("%s %s context=%s", error.code, error, error.context)


_analytics_config, _analytics_problem = AnalyticsConfig.from_environment(PROJECT_ROOT, version="1.2.0")
analytics = AnalyticsSender(_analytics_config, root=PROJECT_ROOT, on_failure=_report_analytics_problem)


def report_failure(error: AppError) -> None:
    """One structured line in the log and, when analytics is on, one error.occurrence event."""
    LOGGER.error("%s %s context=%s", error.code, error, error.context)
    analytics.record_exception(error)


def _cookie_file_problem(fmt: str, exc: Exception) -> None:
    """A broken cookie file is for a person to fix (re-export it), not for a code repair."""
    try:
        raise InstagramCookiesInvalidError(
            "Instagram cookies are not configured correctly: the cookie file could not be read",
            format=fmt, problem=type(exc).__name__) from None
    except InstagramCookiesInvalidError as error:
        report_failure(error)


_browser: Browser | None = None
_page: Page | None = None
_playwright = None

SAME_SITE_MAP = {
    "unspecified": "None",
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
}


def _is_instagram_url(url: str | None) -> bool:
    """True only when the URL host is instagram.com (or a subdomain).

    CodeQL flags ``\"instagram.com\" in url`` as incomplete substring
    sanitization (evil.com/?q=instagram.com would match). Use the parsed
    hostname instead.
    """
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "instagram.com" or host.endswith(".instagram.com")


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
    except (OSError, ValueError) as exc:
        _cookie_file_problem("json", exc)
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
    except (OSError, ValueError) as exc:
        _cookie_file_problem("txt", exc)
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
    if _analytics_problem:
        _report_analytics_problem({"message": "analytics stays off", "reason": _analytics_problem})
    analytics.start()
    print("[API] Connecting to Chrome via CDP...")

    pw = await async_playwright().start()
    _playwright = pw

    for attempt in range(10):
        try:
            _browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_PORT}")
            break
        except (PlaywrightError, OSError) as exc:
            if attempt == 9:
                unreachable = InstagramChromeUnreachableError(
                    "Chrome did not answer over CDP after 10 attempts", cause=exc, port=CHROME_PORT)
                report_failure(unreachable)
                analytics.flush_once()  # the API is about to stop: send now
                analytics.stop()
                raise unreachable from exc
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
    analytics.stop()


app = FastAPI(title="Finja Instagram Reels", lifespan=lifespan)


@app.exception_handler(AppError)
async def structured_error(_request: Request, exc: AppError) -> JSONResponse:
    report_failure(exc)
    return JSONResponse(status_code=500, content={"error": {"code": exc.code, "message": str(exc)}})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Anything an endpoint did not expect is reported once with its cause, then answered with 500."""
    error = InstagramApiUnexpectedError(f"{request.method} {request.url.path} failed unexpectedly", cause=exc,
                                        endpoint=request.url.path)
    report_failure(error)
    return JSONResponse(status_code=500, content={"error": {"code": error.code, "message": str(error)}})


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
        "awake": _is_instagram_url(_page.url),
    }


@app.get("/diagnostics/probe")
async def diagnostics_probe(token: str = ""):
    """Owner-only: runs the Reel statistics before any Reel was seen (the onboarding pilot's real bug)."""
    expected = os.environ.get("INSTAGRAM_PROBE_TOKEN", "")
    if not expected or not secrets.compare_digest(token, expected):
        raise HTTPException(404, "Not found")
    try:
        value = like_rate(0, 0)
    except ZeroDivisionError as exc:
        raise InstagramDiagnosticsProbeError("Diagnostics probe hit a real bug", probe="like_rate") from exc
    return {"probe": "like_rate", "value": value}


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
    if _is_instagram_url(_page.url):
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
    if not _is_instagram_url(_page.url):
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")
