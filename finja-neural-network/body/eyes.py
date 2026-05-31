"""
Body Eyes - Visual Perception
=============================
Handles taking screenshots of the active desktop window (or full screen) and transcribing / analyzing 
the visual content using local Ollama Vision or cloud-based OpenRouter models.

Main Responsibilities:
- Query active desktop windows.
- Capture screenshot of active window or full monitor.
- Base64 encode and format images for visual model endpoints.
- Call local Ollama or cloud OpenRouter visual APIs.

Side Effects:
- Takes system-level desktop screenshots.
- Writes transient captured image to VISION_IMG_PATH.
- Screenshot Capture not working on Docker.
"""

import base64
import os
import sys
from typing import Optional

# Desktop screenshot libs: lazy import, because Docker/headless can crash here.
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
from exceptions import YourAIVisionError, YourAIUnexpectedError, YourAISystemError
from config import (
    LLM_HOST_MAIN,
    VISION_MODEL,
    VISION_IMG_PATH,
    VISION_MAX_SIZE,
    VISION_USE_OPENROUTER,
    OPENROUTER_API_KEY,
)
from body.vision_clients import call_ollama_vision, call_openrouter_vision

if _HAS_DESKTOP:
    log("VISION", "Desktop Vision available (mss + pygetwindow)", Fore.GREEN)
else:
    log("VISION", "Headless mode - URL vision only (OpenRouter)", Fore.YELLOW)


def get_active_window_list() -> str:
    """
    Retrieves a formatted list of all visible desktop application window titles.

    Returns:
        str: A multi-line string listing window titles, or an error/status message.
    """
    if not _HAS_DESKTOP:
        return "Desktop vision not available (headless/Docker mode)."
    try:
        windows = gw.getAllTitles()
        clean_list = [w for w in windows if w.strip() and w != "Program Manager"]
        return "Open Apps:\n" + "\n".join([f"- {w}" for w in clean_list])
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="eyes_window_list")
        log_exception("VISION", err)
        return "Could not list windows."


def capture_active_window() -> Optional[str]:
    """
    Captures the currently focused window or full monitor.

    Saves the captured screenshot at the path specified by the configuration.

    Returns:
        Optional[str]: The path to the saved screenshot file, or None if capturing failed.
    """
    if not _HAS_DESKTOP:
        log("VISION", "Desktop capture not available (headless/Docker mode)", Fore.YELLOW)
        return None

    try:
        active_window = gw.getActiveWindow()
        region = None

        if not active_window:
            log("VISION", "No active window found. Capturing fullscreen.", Fore.YELLOW)
        else:
            log("VISION", f"Focused window: {active_window.title}", Fore.CYAN)
            if active_window.width > 0 and active_window.height > 0:
                region = {
                    "top": int(active_window.top),
                    "left": int(active_window.left),
                    "width": int(active_window.width),
                    "height": int(active_window.height),
                }

        with mss.mss() as sct:
            screenshot = sct.grab(region) if region else sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.thumbnail(VISION_MAX_SIZE)
            img.save(VISION_IMG_PATH)
            return VISION_IMG_PATH
    except Exception as e:
        err = YourAIVisionError("Screenshot failed", cause=e, module="eyes_capture")
        log_exception("VISION", err)
        return None


def encode_image(image_path: str) -> Optional[str]:
    """
    Encodes a local image file as a base64 string.

    Args:
        image_path (str): Path to the image file.

    Returns:
        Optional[str]: The base64 encoded string, or None if the file is missing or unreadable.
    """
    if not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except OSError as e:
        err = YourAISystemError(
            message=f"Could not read image: {image_path}",
            cause=e,
            module="eyes_encode",
        )
        log_exception("VISION", err)
        return None
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="eyes_encode")
        log_exception("VISION", err)
        return None


def _see_openrouter(base64_img: str, prompt: str) -> str:
    """
    Calls the OpenRouter vision model to describe the base64 image.

    Args:
        base64_img (str): The base64 encoded image string (excluding prefix).
        prompt (str): Prompt instructing the model what to look for.

    Returns:
        str: The text response from OpenRouter.
    """
    return call_openrouter_vision(
        OPENROUTER_API_KEY,
        VISION_MODEL,
        prompt,
        f"data:image/png;base64,{base64_img}",
        label="screenshot",
    )


def _see_ollama(base64_img: str, prompt: str) -> str:
    """
    Calls the local Ollama vision model to describe the base64 image.

    Args:
        base64_img (str): The base64 encoded image string (excluding prefix).
        prompt (str): Prompt instructing the model what to look for.

    Returns:
        str: The text response from Ollama.
    """
    return call_ollama_vision(LLM_HOST_MAIN, VISION_MODEL, prompt, base64_img)


def see(prompt: str = "Describe what is in this window briefly.") -> str:
    """
    Captures the focused desktop screen, encodes it, and describes it using vision models.

    Tries cloud vision via OpenRouter first (if configured), falling back to local 
    Ollama vision if that fails.

    Args:
        prompt (str, optional): The prompt instructions for the vision model.

    Raises:
        YourAIVisionError: If screenshot capturing, encoding, or both vision tiers fail.

    Returns:
        str: The visual description text.
    """
    log("VISION", "YourAI is looking at the screen...", Fore.BLUE)
    image_path = capture_active_window()
    if not image_path:
        raise YourAIVisionError("Screenshot capture failed")

    base64_img = encode_image(image_path)
    if not base64_img:
        raise YourAIVisionError("Image encoding failed")

    if VISION_USE_OPENROUTER and OPENROUTER_API_KEY:
        try:
            return _see_openrouter(base64_img, prompt)
        except Exception as e:
            err = YourAIVisionError("OpenRouter Vision failed", cause=e, module="eyes_see")
            log_exception("VISION", err)
            log("VISION", "OpenRouter Vision failed - trying local fallback.", Fore.RED)

    try:
        return _see_ollama(base64_img, prompt)
    except Exception as e:
        err = YourAIVisionError("All vision tiers failed (OpenRouter + Ollama)", cause=e, module="eyes_see")
        log_exception("VISION", err)
        raise err


def see_url(image_url: str, prompt: str = "Describe what is in this image briefly.") -> str:
    """
    Sends a remote image URL to the OpenRouter vision model for analysis.

    Args:
        image_url (str): The public URL of the image to analyze.
        prompt (str, optional): The prompt instructions for the model.

    Raises:
        YourAIVisionError: If OpenRouter is not configured or the analysis request fails.

    Returns:
        str: The visual description text.
    """
    log("VISION", f"Analyzing image URL: {image_url[:80]}...", Fore.BLUE)

    if not VISION_USE_OPENROUTER or not OPENROUTER_API_KEY:
        raise YourAIVisionError("URL vision offline: OpenRouter is not configured")

    try:
        return call_openrouter_vision(
            OPENROUTER_API_KEY,
            VISION_MODEL,
            prompt,
            image_url,
            label="url",
        )
    except Exception as e:
        err = YourAIVisionError("URL vision failed", cause=e, module="eyes_url_vision")
        log_exception("VISION", err)
        raise err


if __name__ == "__main__":
    log("VISION", "Test Vision...", Fore.CYAN)
    see("What is this?")
