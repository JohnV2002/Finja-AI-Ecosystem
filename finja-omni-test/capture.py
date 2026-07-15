"""
======================================================================
         Finja Omni Test – Screen Capture
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / capture
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
  Reusable active window capture (module for live.py).
  Returns the focused window as a PIL Image + metadata (title, content 
  type, fullscreen, Chrome crop) per call. No loop -> importable.
======================================================================
"""

from PIL import Image
import pygetwindow as gw

BROWSER_TITLE_HINTS = ["google chrome", "mozilla firefox", "microsoft edge",
                       "brave", "opera", "chromium", "vivaldi"]
BROWSER_TOP_CROP = 130

VIDEO_TITLE_HINTS = ["youtube", "aniworld", "crunchyroll", "netflix", "twitch",
                     "wakanim", "vimeo", "- vlc", "mpv", "dailymotion", "disney+"]
IDE_TITLE_HINTS   = ["visual studio", "antigravity ide", "pycharm", "intellij",
                     "vs code", "vscode", "- code -", "sublime", "neovim"]


def classify(title):
    t = (title or "").lower()
    if any(h in t for h in VIDEO_TITLE_HINTS):
        return "video"
    if any(h in t for h in IDE_TITLE_HINTS):
        return "ide"
    return "other"


def is_browser(title):
    t = (title or "").lower()
    return any(h in t for h in BROWSER_TITLE_HINTS)


def app_from_title(title):
    if not title:
        return "?"
    parts = [p.strip() for p in title.split(" - ")]
    return parts[-1] if len(parts) > 1 else title.strip()


def grab_active(sct):
    """Grabs the active window. Returns dict:
       image (PIL), title, app, content, fullscreen, wants_fullscreen.
    """
    full = sct.monitors[1]
    try:
        win = gw.getActiveWindow()
    except Exception:
        win = None
    title = (getattr(win, "title", "") or "").strip()

    if win and win.width > 0 and win.height > 0:
        region = {
            "top": max(int(win.top), full["top"]),
            "left": max(int(win.left), full["left"]),
            "width": min(int(win.width), full["width"]),
            "height": min(int(win.height), full["height"]),
        }
        if region["width"] <= 0 or region["height"] <= 0:
            region = dict(full)
    else:
        region = dict(full)

    content = classify(title)
    # Determine fullscreen BEFORE the crop
    fullscreen = (region["height"] >= full["height"] - 5 and
                  region["width"] >= full["width"] - 5)
    wants_fullscreen = (content == "video" and not fullscreen)

    # Browser top crop (remove tabs/bookmarks)
    if is_browser(title) and region["height"] > BROWSER_TOP_CROP + 50:
        region = {
            "top": region["top"] + BROWSER_TOP_CROP, "left": region["left"],
            "width": region["width"], "height": region["height"] - BROWSER_TOP_CROP,
        }

    shot = sct.grab(region)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    return {
        "image": img, "title": title, "app": app_from_title(title),
        "content": content, "fullscreen": fullscreen,
        "wants_fullscreen": wants_fullscreen,
    }
