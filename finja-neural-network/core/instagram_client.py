"""
YourAI Instagram Reels Client
============================
HTTP client for the yourai-instagram Docker browsing container.

Main Responsibilities:
- Check container health and send browsing or interaction requests.
- Forward screenshots and captions to YourAI's vision and decision logic.
- Provide a small typed wrapper around the container API.

Side Effects:
- Performs HTTP requests to the Instagram container.
- May trigger browsing, scrolling, screenshot, like, or comment actions inside the container.
"""

import os
import time
import random
from typing import Optional, Dict, Any, Tuple

import httpx

from display import log, Fore

INSTAGRAM_API_URL = os.environ.get("INSTAGRAM_API_URL", "http://yourai-instagram:8061")
_TIMEOUT = 30.0

# Session-Parameter
MAX_REELS_PER_SESSION = 10
WATCH_TIME_MIN = 8
WATCH_TIME_MAX = 16

# Vision Model for Screenshot-Analyse
VISION_MODEL = os.environ.get("INSTAGRAM_VISION_MODEL", "google/gemini-3.1-flash-lite")

VISION_SYSTEM_PROMPT = """Du bist YourAI — eine 16-jaehrige KI.
Du scrollst gerade durch Instagram Reels und entscheidest ob ein Reel gut ist.

Analyse das Screenshot. Ist das Reel INTERESSANT for dich/deinen Creator?

INTERESSANT = Suesse Tiere, Katzen, Hunde, Food (Burger, Pizza, Kochen),
Art/Zeichnen Timelapses, Fitness, Fashion, Aesthetic Edits,
Memes, Comedy, Autos/Trucks, Anime, satisfying Videos, Musik,
coole Transitions, Travel, DIY.

NICHT INTERESSANT = Clickbait, Drama, Politik, Werbung, langweilig,
repetitive Trends die keinen Inhalt haben, Cringe.

Antworte NUR mit diesem Format:
JA kurzer Kommentar warum (max 1 Satz, teen-style)
oder
NEIN

Beispiele:
JA omg der hund traegt einen kleinen hut ich sterbe xd
JA alter die pasta sieht so gut aus
NEIN
JA die transition ist so smooth wtf"""

VISION_USER_PROMPT = """Instagram Reel Screenshot:
Kanal: {channel}

Ist das gut?"""


def _get(path: str) -> Optional[Dict[str, Any]]:
    """
    Executes the _get helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    try:
        with httpx.Client(base_url=INSTAGRAM_API_URL, timeout=_TIMEOUT) as c:
            r = c.get(path)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log("IG_CLIENT", f"GET {path} failed: {e}", Fore.RED)
        return None


def _post(path: str) -> Optional[Dict[str, Any]]:
    """
    Executes the _post helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    try:
        with httpx.Client(base_url=INSTAGRAM_API_URL, timeout=_TIMEOUT) as c:
            r = c.post(path)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log("IG_CLIENT", f"POST {path} failed: {e}", Fore.RED)
        return None


def is_healthy() -> bool:
    """
    Executes the is_healthy helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    data = _get("/health")
    return data is not None and data.get("status") == "ok"


def wakeup() -> bool:
    """Weckt Instagram auf: about:blank -> instagram.com/reels/."""
    data = _post("/wakeup")
    if data and data.get("status") in ("awake", "already_awake"):
        log("IG_CLIENT", f"Wakeup OK: {data.get('url', '?')}", Fore.CYAN)
        return True
    log("IG_CLIENT", "Wakeup failed!", Fore.RED)
    return False


def sleep_browser() -> bool:
    """Schlafen legen: instagram.com -> about:blank. Instagram sieht uns offline."""
    data = _post("/sleep")
    if data and data.get("status") in ("sleeping", "already_sleeping"):
        log("IG_CLIENT", "Sleep OK: about:blank", Fore.CYAN)
        return True
    log("IG_CLIENT", "Sleep failed!", Fore.RED)
    return False


def scroll() -> Optional[Dict[str, Any]]:
    """Scrollt zum naechsten Reel. Returns {url, channel, screenshot_b64}."""
    return _post("/scroll")


def like() -> Optional[Dict[str, Any]]:
    """Liked das aktuelle Reel. Returns {liked: bool}."""
    return _post("/like")


def analyze_screenshot(screenshot_b64: str, channel: str) -> Tuple[bool, str]:
    """
    Vision-LLM analysiert Screenshot.
    Returns (is_hit: bool, comment: str).
    """
    from config import call_openrouter

    user_content = [
        {
            "type": "text",
            "text": VISION_USER_PROMPT.format(channel=channel),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"},
        },
    ]

    try:
        response, used_model, _ = call_openrouter(
            system_prompt=VISION_SYSTEM_PROMPT,
            user_message=user_content,
            model=VISION_MODEL,
            temperature=0.7,
            max_tokens=80,
        )

        if not response:
            return False, ""

        text = response.strip()
        if text.upper().startswith("JA"):
            comment = text[2:].strip().lstrip("!:—- ")
            log("IG_CLIENT", f"Vision: HIT! {comment[:60]}", Fore.GREEN)
            return True, comment or "nice find :3"
        else:
            log("IG_CLIENT", f"Vision: skip ({used_model})", Fore.LIGHTBLACK_EX)
            return False, ""

    except Exception as e:
        log("IG_CLIENT", f"Vision-Analyse failed: {e}", Fore.RED)
        return False, ""


def run_browsing_session(stop_event=None) -> Optional[Dict[str, Any]]:
    """
    Eine komplette Browsing-Session durchfuehren.

    Flow: Wakeup -> Scroll -> Analyse -> Like -> Sleep
    Instagram sieht uns nur waehrend der aktiven Session als 'online'.

    Scrollt durch bis zu MAX_REELS_PER_SESSION Reels.
    Bei Hit: liked + returns Reel-Info mit Kommentar.
    Bei kein Hit: returns None.
    IMMER: Sleep am Ende (about:blank).

    Args:
        stop_event: threading.Event — wenn gesetzt, Session abbrechen.
    """
    if not is_healthy():
        log("IG_CLIENT", "Instagram Container nicht erreichbar — skip Session", Fore.YELLOW)
        return None

    # ── Aufwachen: about:blank -> instagram.com/reels/ ──
    if not wakeup():
        log("IG_CLIENT", "Wakeup failed — skip Session", Fore.RED)
        return None

    log("IG_CLIENT", f"Browsing session started (max {MAX_REELS_PER_SESSION} Reels)", Fore.MAGENTA)

    try:
        for i in range(MAX_REELS_PER_SESSION):
            if stop_event and stop_event.is_set():
                log("IG_CLIENT", "Session abgebrochen (stop_event)", Fore.YELLOW)
                return None

            # Menschliche Wartezeit
            watch_time = random.randint(WATCH_TIME_MIN, WATCH_TIME_MAX)
            log("IG_CLIENT", f"Reel {i+1}/{MAX_REELS_PER_SESSION} — schaue {watch_time}s...", Fore.LIGHTBLACK_EX)

            if stop_event:
                if stop_event.wait(watch_time):
                    return None
            else:
                time.sleep(watch_time)

            # Scroll zum naechsten Reel + Screenshot
            data = scroll()
            if not data or "screenshot_b64" not in data:
                log("IG_CLIENT", "Scroll failed — skip", Fore.YELLOW)
                continue

            # Vision-LLM Analyse (kein Titel — Vision sieht alles im Screenshot)
            is_hit, comment = analyze_screenshot(
                screenshot_b64=data["screenshot_b64"],
                channel=data.get("channel", "Unbekannt"),
            )

            if is_hit:
                # Like!
                like_result = like()
                liked = like_result.get("liked", False) if like_result else False

                log("IG_CLIENT", f"HIT nach {i+1} Reels! Liked={liked}", Fore.GREEN)

                return {
                    "url": data.get("url", ""),
                    "channel": data.get("channel", "Unbekannt"),
                    "comment": comment,
                    "liked": liked,
                    "reels_watched": i + 1,
                }

        log("IG_CLIENT", f"Session beendet — kein Hit nach {MAX_REELS_PER_SESSION} Reels", Fore.YELLOW)
        return None

    finally:
        # ── IMMER einschlafen — egal ob Hit, kein Hit, oder Error ──
        log("IG_CLIENT", "Session vorbei — schlafen legen...", Fore.CYAN)
        sleep_browser()
