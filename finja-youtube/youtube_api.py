# youtube_api.py
# Hybrid Proxy: Chrome + Playwright + FastAPI

"""
======================================================================
         Finja YouTube Shorts – Container API
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-youtube
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
  Headless API container for YouTube Shorts interaction.
  Connects to a headless Chromium browser via CDP, injects cookies
  for authenticated YouTube access, and exposes a REST API for:

  • Scrolling through Shorts (next video + screenshot + metadata)
  • Liking the current video
  • Health/status checks
  • VPN IP verification (traffic routed through Gluetun)

  All intelligence stays in the Brain (Neural Network).
  This container is intentionally "dumb" — it only executes actions.

----------------------------------------------------------------------
 New in v1.2.0:
----------------------------------------------------------------------
  • Structured FINJA errors (module finja-youtube): unreadable cookie file
    FINJA-109 (before: the API crashed at startup), Chrome unreachable
    FINJA-538, unexpected request failure FINJA-539, probe FINJA-540
  • Analytics Contract sender (off unless ANALYTICS_ENABLED)
  • Owner-only GET /diagnostics/probe?token=… (YOUTUBE_PROBE_TOKEN)

----------------------------------------------------------------------
 Changelog v1.1.0:
----------------------------------------------------------------------
  • Adopted into Production ("Finja - Browser test" folder)
    as part of the module version/header unification (2026-07-19) --
    no functional changes in this file specifically

----------------------------------------------------------------------
 Changelog v1.0.0:
----------------------------------------------------------------------
  • Initial release
  • Headless Chrome via Playwright CDP
  • Cookie injection from JSON export
  • /scroll, /like, /health, /status, /ip endpoints
  • VPN-routed traffic via Gluetun sidecar

======================================================================
"""

import os
import json
import base64
import asyncio
import logging
import secrets
import time
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright, Browser, Error as PlaywrightError, Page

from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import (
    AnalyticsDeliveryError,
    AppError,
    YouTubeApiUnexpectedError,
    YouTubeChromeUnreachableError,
    YouTubeCookiesInvalidError,
    YouTubeDiagnosticsProbeError,
)
from shorts_stats import like_share

# ---- Config ----
CHROME_PORT = int(os.environ.get("CHROME_PORT", 9222))
API_PORT = int(os.environ.get("YOUTUBE_API_PORT", 8060))
COOKIES_FILE = os.environ.get("COOKIES_FILE", "/app/cookies.json")
YOUTUBE_TARGET_URL = os.environ.get("YOUTUBE_TARGET_URL", "https://m.youtube.com/shorts")

LOGGER = logging.getLogger("finja_youtube")
PROJECT_ROOT = Path(__file__).resolve().parent


def _report_analytics_problem(problem: dict) -> None:
    error = AnalyticsDeliveryError(str(problem.get("message") or "analytics delivery failed"),
                                   reason=problem.get("reason"), retry=problem.get("retry"))
    LOGGER.warning("%s %s context=%s", error.code, error, error.context)


_analytics_config, _analytics_problem = AnalyticsConfig.from_environment(PROJECT_ROOT, version="1.2.0")
analytics = AnalyticsSender(_analytics_config, root=PROJECT_ROOT, on_failure=_report_analytics_problem)


def report_failure(error: AppError) -> None:
    """One structured log line and, when analytics is on, one error.occurrence event."""
    LOGGER.error("%s %s context=%s", error.code, error, error.context)
    analytics.record_exception(error)


_browser: Browser | None = None
_page: Page | None = None
_playwright = None

SAME_SITE_MAP = {"unspecified": "None", "no_restriction": "None", "lax": "Lax", "strict": "Strict"}


def _load_cookies(filepath: str) -> list[dict]:
    """Browser-Export JSON → Playwright cookie format."""
    path = Path(filepath)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("cookie export is not a list")
    except (OSError, ValueError) as exc:  # a broken export is for a person to fix; start without login
        try:
            raise YouTubeCookiesInvalidError(
                "YouTube cookies are not configured correctly: the cookie file could not be read",
                module="finja-youtube", problem=type(exc).__name__) from None
        except YouTubeCookiesInvalidError as error:
            report_failure(error)
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
            pw["expires"] = exp
        cookies.append(pw)
    return cookies


# ---- Lifespan: Connect to Chrome on startup ----
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
                unreachable = YouTubeChromeUnreachableError(
                    "Chrome did not answer over CDP after 10 attempts", module="finja-youtube", cause=exc,
                    port=CHROME_PORT)
                report_failure(unreachable)
                analytics.flush_once()  # the API is about to stop: send now
                analytics.stop()
                raise unreachable from exc
            await asyncio.sleep(1)

    context = _browser.contexts[0]
    pages = context.pages
    _page = pages[0] if pages else await context.new_page()

    # Inject cookies (if available)
    cookies = _load_cookies(COOKIES_FILE)
    if cookies:
        await context.add_cookies(cookies)
        print(f"[API] {len(cookies)} YouTube cookies loaded!")
        await _page.goto(YOUTUBE_TARGET_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
    else:
        print("[API] No cookies.json found — YouTube without login.")

    print(f"[API] Connected! Current URL: {_page.url}")
    yield

    # Shutdown
    print("[API] Shutdown — disconnecting browser...")
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    analytics.stop()


app = FastAPI(title="Finja YouTube Shorts", lifespan=lifespan)


@app.exception_handler(AppError)
async def structured_error(_request: Request, exc: AppError) -> JSONResponse:
    report_failure(exc)
    return JSONResponse(status_code=500, content={"error": {"code": exc.code, "message": str(exc)}})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Anything an endpoint did not expect is reported once with its cause, then answered with 500."""
    error = YouTubeApiUnexpectedError(f"{request.method} {request.url.path} failed unexpectedly",
                                      module="finja-youtube", cause=exc, endpoint=request.url.path)
    report_failure(error)
    return JSONResponse(status_code=500, content={"error": {"code": error.code, "message": str(error)}})


@app.get("/diagnostics/probe")
async def diagnostics_probe(token: str = ""):
    """Owner-only: the like share before any Short was seen (the onboarding pilot's real bug)."""
    expected = os.environ.get("YOUTUBE_PROBE_TOKEN", "")
    if not expected or not secrets.compare_digest(token, expected):
        raise HTTPException(404, "Not found")
    try:
        value = like_share(0, 0)
    except ZeroDivisionError as exc:
        raise YouTubeDiagnosticsProbeError("Diagnostics probe hit a real bug", module="finja-youtube",
                                           probe="like_share") from exc
    return {"probe": "like_share", "value": value}


# ---- Health ----
@app.get("/health")
async def health():
    browser_ok = _browser is not None and _browser.is_connected()
    return {
        "status": "ok" if browser_ok else "degraded",
        "browser_connected": browser_ok,
        "current_url": _page.url if _page else None,
    }


# ---- VPN IP Check (external, routed through VPN tunnel) ----
@app.get("/ip")
async def get_vpn_ip():
    """Check public IP — routed through the Gluetun VPN tunnel."""
    async with httpx.AsyncClient(timeout=10) as client:
        for url in [
            "https://api.ipify.org?format=json",
            "https://ifconfig.me/all.json",
        ]:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                return {
                    "vpn_ip": data.get("ip", data.get("ip_addr")),
                    "source": url.split("/")[2],
                }
            except Exception:
                continue
    return {"vpn_ip": None, "error": "No external IP service reachable"}


# ---- Status ----
@app.get("/status")
async def status():
    if not _page:
        raise HTTPException(503, "Browser not connected")
    return {
        "url": _page.url,
        "title": await _page.title(),
    }


# ---- Scroll: Next video + Screenshot + Metadata ----
@app.post("/scroll")
async def scroll():
    """
    1. ArrowDown (next Short)
    2. Wait 2-3 sec for video to load
    3. Return screenshot + title + channel + URL
    """
    if not _page:
        raise HTTPException(503, "Browser not connected")

    # Scroll to next video
    await _page.keyboard.press("ArrowDown")

    # Wait for new video to load (YouTube needs a moment)
    await asyncio.sleep(3)

    # Scrape metadata via JavaScript (more robust than CSS selectors)
    try:
        meta = await _page.evaluate("""() => {
            let title = '';
            let channel = '';

            // Title: try various selectors
            const titleSels = [
                'yt-formatted-string.ytShortsVideoTitleViewModelShortsVideoTitle',
                '.reel-video-in-sequence[is-active] .metadata-title',
                'h2.title yt-formatted-string',
                '#video-title',
                'span.ytShortsVideoTitleViewModelShortsVideoTitle',
            ];
            for (const sel of titleSels) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim()) {
                    title = el.textContent.trim();
                    break;
                }
            }

            // Channel: link with /@username pattern
            const channelSels = [
                'a[href*="/@"]',
                '#channel-name a',
                '.ytReelChannelBarViewModelChannelName a',
            ];
            for (const sel of channelSels) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim()) {
                    channel = el.textContent.trim();
                    break;
                }
            }

            // Fallback: extract channel handle from URL
            if (!channel) {
                const links = document.querySelectorAll('a[href*="/@"]');
                for (const a of links) {
                    const match = a.href.match(/@([^/]+)/);
                    if (match) { channel = '@' + match[1]; break; }
                }
            }

            return { title: title || '', channel: channel || '' };
        }""")
        title = meta.get("title") or "Unknown"
        channel = meta.get("channel") or "Unknown"
    except Exception as e:
        print(f"[API] Metadata scrape error: {e}")
        title = "Scrape error"
        channel = "Scrape error"

    # Screenshot
    screenshot_bytes = await _page.screenshot(type="jpeg", quality=50)
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    return {
        "url": _page.url,
        "title": title,
        "channel": channel,
        "screenshot_b64": screenshot_b64,
    }


# ---- Like: Like the current video ----
@app.post("/like")
async def like():
    """Click the like button on the current video."""
    if not _page:
        raise HTTPException(503, "Browser not connected")

    # Mobile YouTube Shorts like selectors (fallback chain)
    for sel in [
        'button[aria-label*="Like"], button[aria-label*="like"]',
        'button[aria-label*="Mag ich"], button[aria-label*="mag ich"]',
        "#like-button button",
        "ytd-reel-video-renderer[is-active] #like-button button",
    ]:
        try:
            like_btn = _page.locator(sel).first
            if await like_btn.is_visible(timeout=1000):
                await like_btn.click()
                await asyncio.sleep(1)
                return {"liked": True, "url": _page.url}
        except Exception:
            continue
    return {"liked": False, "reason": "Like button not found (all selectors failed)"}


# ---- Run ----
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")
