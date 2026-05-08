import base64
import time
import requests
import os
import sys
import json

# Desktop screenshot libs — lazy import (crash in Docker without display)
# Only needed by see(), capture_active_window(), encode_image()
# NOT needed by see_url() which uses OpenRouter API directly
_HAS_DESKTOP = False
try:
    import mss
    import mss.tools
    import pygetwindow as gw
    from PIL import Image
    _HAS_DESKTOP = True
except (ImportError, NotImplementedError):
    mss = None
    gw = None
    Image = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIVisionError, YourAIUnexpectedError, YourAINetworkError, YourAISystemError

# Importiere jetzt alles zentral aus deiner schönen Config!
from config import (
    LLM_HOST_MAIN, VISION_MODEL, VISION_IMG_PATH, VISION_MAX_SIZE,
    VISION_USE_OPENROUTER, OPENROUTER_API_KEY
)

if _HAS_DESKTOP:
    log("VISION", "👁️ Desktop Vision verfügbar (mss + pygetwindow)", Fore.GREEN)
else:
    log("VISION", "👁️ Headless Mode — nur URL-Vision (OpenRouter) verfügbar", Fore.YELLOW)

# ==========================================
# ⚙️ KONFIGURATION
# ==========================================

# Lokaler Fallback
OLLAMA_VISION_URL = f"{LLM_HOST_MAIN}/api/chat"

# OpenRouter
OPENROUTER_VISION_URL = "https://openrouter.ai/api/v1/chat/completions"


# ==========================================
# 👁️ THE EYES
# ==========================================

def get_active_window_list():
    """SCAN 1: Der Radar."""
    if not _HAS_DESKTOP:
        return "Desktop vision not available (headless/Docker mode)."
    try:
        windows = gw.getAllTitles()
        clean_list = [w for w in windows if w.strip() and w != "Program Manager"]
        status_text = "Open Apps:\n" + "\n".join([f"- {w}" for w in clean_list])
        return status_text
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="eyes_window_list")
        log_exception("VISION", err)
        return "Could not list windows."

def capture_active_window():
    """SCAN 2: Der Fokus."""
    if not _HAS_DESKTOP:
        log("VISION", "⚠️ Desktop capture not available (headless/Docker mode)", Fore.YELLOW)
        return None
    try:
        active_window = gw.getActiveWindow()
        region = None

        if not active_window:
            log("VISION", "⚠️ Kein aktives Fenster gefunden. Mache Fullscreen.", Fore.YELLOW)
        else:
            log("VISION", f"📸 Fokus auf: {active_window.title}", Fore.CYAN)
            if active_window.width > 0 and active_window.height > 0:
                region = {
                    "top": int(active_window.top),
                    "left": int(active_window.left),
                    "width": int(active_window.width),
                    "height": int(active_window.height)
                }

        with mss.mss() as sct:
            if region:
                screenshot = sct.grab(region)
            else:
                screenshot = sct.grab(sct.monitors[1])

            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # Hier nutzen wir jetzt die globale Config!
            img.thumbnail(VISION_MAX_SIZE)

            img.save(VISION_IMG_PATH)
            return VISION_IMG_PATH

    except Exception as e:
        err = YourAIVisionError("Screenshot fehlgeschlagen", cause=e)
        log_exception("VISION", err)
        return None

def encode_image(image_path):
    """Wandelt Bild in Base64 für den Server um."""
    if not os.path.exists(image_path): return None
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except OSError as e:
        err = YourAISystemError(message=f"Fehler beim Lesen des Bildes: {image_path}", cause=e, module="eyes_encode")
        log_exception("VISION", err)
        return None
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="eyes_encode")
        log_exception("VISION", err)
        return None


def _see_openrouter(base64_img: str, prompt: str) -> str:
    """Vision via OpenRouter API (ZDR supported)."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_img}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 3000,  # Thinking-Models brauchen ~200-300 tokens für Reasoning, dann erst Content!
    }

    log("VISION", f"☁️ Sende an OpenRouter ({VISION_MODEL})...", Fore.MAGENTA)
    start = time.time()
    try:
        response = requests.post(OPENROUTER_VISION_URL, headers=headers, json=payload, timeout=30)
    except requests.exceptions.RequestException as e:
        raise YourAINetworkError(host="openrouter.ai", cause=e, module="eyes_openrouter")
    duration = time.time() - start

    if response.status_code == 200:
        result = response.json()
        raw_full = json.dumps(result)  # Voller String — nie abschneiden bei Errors!
        choices = result.get("choices")
        if not choices or not choices[0].get("message"):
            log("VISION", f"⚠️ Unerwartete Response-Struktur (FULL):\n{raw_full}", Fore.RED)
            raise YourAIVisionError(
                f"OpenRouter returned unexpected format\n"
                f"Model: {VISION_MODEL}\n"
                f"Full response: {raw_full}"
            )
        desc = choices[0]["message"]["content"]
        if not desc:
            choice_full = json.dumps(choices[0])
            log("VISION", f"⚠️ Leerer Vision-Content! Full choice[0]:\n{choice_full}", Fore.RED)
            log("VISION", f"⚠️ Full response:\n{raw_full}", Fore.RED)
            raise YourAIVisionError(
                f"OpenRouter returned empty vision content\n"
                f"Model: {VISION_MODEL}\n"
                f"choice[0]: {choice_full}\n"
                f"Full response: {raw_full}"
            )
        log("VISION", f"☁️ OpenRouter Vision ({duration:.1f}s): {desc[:100]}...", Fore.GREEN)
        return desc
    else:
        full_error = response.text
        log("VISION", f"⚠️ OpenRouter HTTP {response.status_code} (FULL):\n{full_error}", Fore.RED)
        raise YourAIVisionError(
            f"OpenRouter Vision HTTP {response.status_code}\n"
            f"Model: {VISION_MODEL}\n"
            f"Full error: {full_error}"
        )


def _see_ollama(base64_img: str, prompt: str) -> str:
    """Vision via lokales Ollama (Fallback)."""
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64_img]
            }
        ],
        "stream": False
    }

    log("VISION", f"🖥️ Sende an lokales Ollama ({VISION_MODEL})...", Fore.MAGENTA)
    start = time.time()
    try:
        response = requests.post(OLLAMA_VISION_URL, json=payload, timeout=None)
    except requests.exceptions.RequestException as e:
        raise YourAINetworkError(host=LLM_HOST_MAIN, cause=e, module="eyes_ollama")
    duration = time.time() - start

    if response.status_code == 200:
        result = response.json()
        desc = result['message']['content']
        log("VISION", f"🖥️ Lokal Vision ({duration:.1f}s): {desc[:100]}...", Fore.GREEN)
        return desc
    else:
        raise YourAIVisionError(f"Server Error {response.status_code}: {response.text}")


def see(prompt="Describe what is in this window briefly."):
    """Die Hauptfunktion: Gucken, Senden, Verstehen."""

    log("VISION", "👀 YourAI schaut auf den Screen...", Fore.BLUE)
    image_path = capture_active_window()

    if not image_path:
        raise YourAIVisionError("Screenshot capture fehlgeschlagen")

    base64_img = encode_image(image_path)
    if not base64_img:
        raise YourAIVisionError("Bild-Encoding fehlgeschlagen")

    # Tier 1: OpenRouter (wenn aktiviert)
    if VISION_USE_OPENROUTER and OPENROUTER_API_KEY:
        try:
            return _see_openrouter(base64_img, prompt)
        except Exception as e:
            err = YourAIVisionError("OpenRouter Vision failed", cause=e)
            log_exception("VISION", err)
            log("VISION", "☁️ OpenRouter Vision Failed! → Trying local...", Fore.RED)

    # Tier 2: Lokales Ollama (Fallback)
    try:
        return _see_ollama(base64_img, prompt)
    except Exception as e:
        err = YourAIVisionError("Alle Vision-Tier fehlgeschlagen (OpenRouter + Ollama)", cause=e)
        log_exception("VISION", err)
        raise err


def see_url(image_url: str, prompt="Describe what is in this image briefly."):
    """Vision für URL-basierte Bilder (z.B. Discord Attachments)."""

    log("VISION", f"🖼️ Analysiere Bild-URL: {image_url[:80]}...", Fore.BLUE)

    if not VISION_USE_OPENROUTER or not OPENROUTER_API_KEY:
        raise YourAIVisionError("URL-Vision offline (OpenRouter nicht konfiguriert)")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                ]
            }
        ],
        "max_tokens": 3000,  # Thinking-Models brauchen ~200-300 tokens für Reasoning, dann erst Content!
    }

    log("VISION", f"☁️ Sende URL an OpenRouter ({VISION_MODEL})...", Fore.MAGENTA)
    start = time.time()
    try:
        response = requests.post(OPENROUTER_VISION_URL, headers=headers, json=payload, timeout=30)
    except requests.exceptions.RequestException as e:
        err = YourAINetworkError(host="openrouter.ai (url)", cause=e, module="eyes_url_vision")
        log_exception("VISION", err)
        raise err
    duration = time.time() - start

    if response.status_code == 200:
        result = response.json()
        raw_full = json.dumps(result)  # Voller String — nie abschneiden bei Errors!
        choices = result.get("choices")
        if not choices or not choices[0].get("message"):
            log("VISION", f"⚠️ URL Vision unerwartete Response-Struktur (FULL):\n{raw_full}", Fore.RED)
            raise YourAIVisionError(
                f"OpenRouter returned unexpected format (URL vision)\n"
                f"Model: {VISION_MODEL}\n"
                f"URL: {image_url[:120]}\n"
                f"Full response: {raw_full}"
            )
        desc = choices[0]["message"]["content"]
        if not desc:
            choice_full = json.dumps(choices[0])
            log("VISION", f"⚠️ URL Vision leerer Content! Full choice[0]:\n{choice_full}", Fore.RED)
            log("VISION", f"⚠️ Full response:\n{raw_full}", Fore.RED)
            raise YourAIVisionError(
                f"OpenRouter returned empty vision content (URL vision)\n"
                f"Model: {VISION_MODEL}\n"
                f"URL: {image_url[:120]}\n"
                f"choice[0]: {choice_full}\n"
                f"Full response: {raw_full}"
            )
        log("VISION", f"🖼️ URL Vision ({duration:.1f}s): {desc[:100]}...", Fore.GREEN)
        return desc
    else:
        full_error = response.text
        log("VISION", f"⚠️ URL Vision HTTP {response.status_code} (FULL):\n{full_error}", Fore.RED)
        raise YourAIVisionError(
            f"OpenRouter Vision HTTP {response.status_code} (URL vision)\n"
            f"Model: {VISION_MODEL}\n"
            f"URL: {image_url[:120]}\n"
            f"Full error: {full_error}"
        )


if __name__ == "__main__":
    log("VISION", "Test Vision...", Fore.CYAN)
    see("What is this?")
