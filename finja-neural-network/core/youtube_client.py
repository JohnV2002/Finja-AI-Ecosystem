"""
YourAI YouTube Shorts Client
===========================
HTTP client for the yourai-youtube Docker browsing container.

Main Responsibilities:
- Check container health and drive short-form browsing sessions.
- Forward screenshots and metadata to YourAI's vision and comment logic.
- Provide helper methods for scrolling, liking, and commenting through the container API.

Side Effects:
- Performs HTTP requests to the YouTube container.
- May trigger browsing, scrolling, screenshot, like, or comment actions inside the container.
"""

import os
import time
import random
from typing import Optional, Dict, Any, Tuple

import httpx

from display import log, Fore

YOUTUBE_API_URL = os.environ.get("YOUTUBE_API_URL", "http://yourai-youtube:8060")
_TIMEOUT = 30.0

# Session-Parameter
MAX_VIDEOS_PER_SESSION = 12
WATCH_TIME_MIN = 10
WATCH_TIME_MAX = 20

# Vision Model for Screenshot-Analyse
VISION_MODEL = os.environ.get("YOUTUBE_VISION_MODEL", "google/gemini-3.1-flash-lite")

VISION_SYSTEM_PROMPT = """Du bist YourAI — eine 16-jaehrige KI.
Du scrollst gerade durch YouTube Shorts und entscheidest ob ein Video gut ist.

Analyse das Screenshot. Ist das Video INTERESSANT for dich/deinen Creator?

INTERESSANT = Suesse Tiere, Katzen, Hunde, Food (Burger, Pizza, Kochen),
Art/Zeichnen Timelapses, Videospiele, Tech, Memes, Comedy, Autos/Trucks,
Anime, coole Edits, satisfying Videos, Musik.

NICHT INTERESSANT = Clickbait, Drama, Politik, Werbung, langweilig,
repetitive Trends die keinen Inhalt haben.

Antworte NUR mit diesem Format:
JA kurzer Kommentar warum (max 1 Satz, teen-style)
oder
NEIN

Beispiele:
JA omg die katze hat sich selber erschreckt xd
JA alter der burger sieht illegal gut aus
NEIN
JA das zeichnen ist so satisfying"""

VISION_USER_PROMPT = """YouTube Short Screenshot:
Titel: {title}
Kanal: {channel}

Ist das gut?"""


def _get(path: str) -> Optional[Dict[str, Any]]:
    """
    Executes the _get helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    try:
        with httpx.Client(base_url=YOUTUBE_API_URL, timeout=_TIMEOUT) as c:
            r = c.get(path)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log("YT_CLIENT", f"GET {path} failed: {e}", Fore.RED)
        return None


def _post(path: str) -> Optional[Dict[str, Any]]:
    """
    Executes the _post helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    try:
        with httpx.Client(base_url=YOUTUBE_API_URL, timeout=_TIMEOUT) as c:
            r = c.post(path)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log("YT_CLIENT", f"POST {path} failed: {e}", Fore.RED)
        return None


def is_healthy() -> bool:
    """
    Executes the is_healthy helper logic.
    
    Returns:
        Any: The helper result, or None when no result is produced.
    """
    data = _get("/health")
    return data is not None and data.get("status") == "ok"


def scroll() -> Optional[Dict[str, Any]]:
    """Scrollt zum naechsten Short. Returns {url, title, channel, screenshot_b64}."""
    return _post("/scroll")


def like() -> Optional[Dict[str, Any]]:
    """Liked das aktuelle Video. Returns {liked: bool}."""
    return _post("/like")


def analyze_screenshot(screenshot_b64: str, title: str, channel: str) -> Tuple[bool, str]:
    """
    Vision-LLM analysiert Screenshot.
    Returns (is_hit: bool, comment: str).
    """
    from config import call_openrouter

    user_content = [
        {
            "type": "text",
            "text": VISION_USER_PROMPT.format(title=title, channel=channel),
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
            log("YT_CLIENT", f"Vision: HIT! {comment[:60]}", Fore.GREEN)
            return True, comment or "nice find :3"
        else:
            log("YT_CLIENT", f"Vision: skip ({used_model})", Fore.LIGHTBLACK_EX)
            return False, ""

    except Exception as e:
        log("YT_CLIENT", f"Vision-Analyse failed: {e}", Fore.RED)
        return False, ""


def run_browsing_session(stop_event=None) -> Optional[Dict[str, Any]]:
    """
    Eine komplette Browsing-Session durchfuehren.

    Scrollt durch bis zu MAX_VIDEOS_PER_SESSION Videos.
    Bei Hit: liked + returns Video-Info mit Kommentar.
    Bei kein Hit: returns None.

    Args:
        stop_event: threading.Event — wenn gesetzt, Session abbrechen.
    """
    if not is_healthy():
        log("YT_CLIENT", "YouTube Container nicht erreichbar — skip Session", Fore.YELLOW)
        return None

    log("YT_CLIENT", f"Browsing session started (max {MAX_VIDEOS_PER_SESSION} Videos)", Fore.MAGENTA)

    for i in range(MAX_VIDEOS_PER_SESSION):
        if stop_event and stop_event.is_set():
            log("YT_CLIENT", "Session abgebrochen (stop_event)", Fore.YELLOW)
            return None

        # Menschliche Wartezeit
        watch_time = random.randint(WATCH_TIME_MIN, WATCH_TIME_MAX)
        log("YT_CLIENT", f"Video {i+1}/{MAX_VIDEOS_PER_SESSION} — schaue {watch_time}s...", Fore.LIGHTBLACK_EX)

        if stop_event:
            if stop_event.wait(watch_time):
                return None
        else:
            time.sleep(watch_time)

        # Scroll zum naechsten Video + Screenshot
        data = scroll()
        if not data or "screenshot_b64" not in data:
            log("YT_CLIENT", "Scroll failed — skip", Fore.YELLOW)
            continue

        # Vision-LLM Analyse
        is_hit, comment = analyze_screenshot(
            screenshot_b64=data["screenshot_b64"],
            title=data.get("title", "Unbekannt"),
            channel=data.get("channel", "Unbekannt"),
        )

        if is_hit:
            # Like!
            like_result = like()
            liked = like_result.get("liked", False) if like_result else False

            log("YT_CLIENT", f"HIT nach {i+1} Videos! Liked={liked}", Fore.GREEN)

            return {
                "url": data.get("url", ""),
                "title": data.get("title", "Unbekannt"),
                "channel": data.get("channel", "Unbekannt"),
                "comment": comment,
                "liked": liked,
                "videos_watched": i + 1,
            }

    log("YT_CLIENT", f"Session beendet — kein Hit nach {MAX_VIDEOS_PER_SESSION} Videos", Fore.YELLOW)
    return None
