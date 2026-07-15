"""
======================================================================
         Finja Omni Test – Active Capture
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / capture_active
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
  Active window capture (simulates what the VPet will do later).
  Uses pygetwindow (from Finja's eyes.py v1) to grab ONLY the FOCUSED 
  window instead of fullscreen -> less UI noise, faster. Saves the image
  UNSCALED (full resolution for OCR!) plus the window title as metadata.

  Installation:  pip install mss pygetwindow

  Usage:  python capture_active.py [label] [count]
     e.g. python capture_active.py realworld2 50
======================================================================
"""

import os
import sys
import json
import time
from mss import MSS
from mss.tools import to_png

try:
    import pygetwindow as gw
except ImportError:
    raise SystemExit("Please install:  pip install pygetwindow")

LABEL      = sys.argv[1] if len(sys.argv) > 1 else "active"
MAX_FRAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 50
TICK_RATE  = 5   # seconds between shots (time to switch programs)

# --- Chrome/Browser crop: cut off top bar (tabs+bookmarks+address).
# Kills the eternal "Apps Pillow Stardew ROMS..." noise + privacy bonus.
# Adjust pixels to your DPI/zoom if necessary (with/without bookmark bar).
BROWSER_TITLE_HINTS = ["google chrome", "mozilla firefox", "microsoft edge",
                       "brave", "opera", "chromium", "vivaldi"]
BROWSER_TOP_CROP = 130   # px to cut from top for browsers

# --- Content classification via title (NOT via screen size!).
# This ensures the IDE is NEVER falsely recognized as video.
VIDEO_TITLE_HINTS = ["youtube", "aniworld", "crunchyroll", "netflix", "twitch",
                     "wakanim", "vimeo", "- vlc", "mpv", "dailymotion", "disney+"]
IDE_TITLE_HINTS   = ["visual studio", "antigravity ide", "pycharm", "intellij",
                     "vs code", "vscode", "- code -", "sublime", "neovim"]


def classify(title):
    """Derive content type from window title: video / ide / other."""
    t = (title or "").lower()
    if any(h in t for h in VIDEO_TITLE_HINTS):
        return "video"
    if any(h in t for h in IDE_TITLE_HINTS):
        return "ide"
    return "other"


def is_browser(title):
    t = (title or "").lower()
    return any(h in t for h in BROWSER_TITLE_HINTS)

OUTPUT_DIR = os.path.join("captures", LABEL)
META_PATH  = os.path.join(OUTPUT_DIR, "meta.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 60)
print(f"  ACTIVE WINDOW CAPTURE -> '{OUTPUT_DIR}'")
print(f"  {MAX_FRAMES} frames, every {TICK_RATE}s, FULL resolution")
print("=" * 60)
print(f"\nGet '{LABEL}' ready... Starting in:")
for i in range(5, 0, -1):
    print(f"{i}...")
    time.sleep(1)
print("\nHERE WE GO! [CTRL + C] to abort early.")
print("-" * 60)


def active_region():
    """Returns (region, title) of the focused window.

    region = None -> Fullscreen fallback (no/invalid window).
    """
    try:
        win = gw.getActiveWindow()
    except Exception:
        win = None
    if not win or not getattr(win, "title", "").strip():
        return None, "(no active window)"
    # Invalid/minimized windows (negative or 0 size) -> fullscreen
    if win.width <= 0 or win.height <= 0:
        return None, win.title
    region = {
        "top": int(win.top), "left": int(win.left),
        "width": int(win.width), "height": int(win.height),
    }
    return region, win.title


meta = {}
if os.path.exists(META_PATH):
    with open(META_PATH, encoding="utf-8") as f:
        meta = json.load(f)

try:
    with MSS() as sct:
        full = sct.monitors[1]
        frame_count = len(meta)   # continue if something is already there
        captured = 0
        while captured < MAX_FRAMES:
            region, title = active_region()
            grab = region if region else full

            # Clamp: Window can partially be outside the monitor
            if region:
                grab = {
                    "top": max(region["top"], full["top"]),
                    "left": max(region["left"], full["left"]),
                    "width": min(region["width"], full["width"]),
                    "height": min(region["height"], full["height"]),
                }
                if grab["width"] <= 0 or grab["height"] <= 0:
                    grab = full
            else:
                grab = dict(full)

            content = classify(title)

            # Fullscreen detection BEFORE crop: does the window cover the whole
            # monitor (incl. taskbar)? 1920x1080 = fullscreen, 1920x1038 = max.
            fullscreen = (grab["height"] >= full["height"] - 5 and
                          grab["width"] >= full["width"] - 5)
            # The cute trigger: Video playing, but NOT fullscreen -> Finja annoys :3
            wants_fullscreen = (content == "video" and not fullscreen)

            # Browser? -> cut off top bar (tabs/bookmarks/address)
            cropped = False
            if is_browser(title) and grab["height"] > BROWSER_TOP_CROP + 50:
                grab = {
                    "top": grab["top"] + BROWSER_TOP_CROP,
                    "left": grab["left"],
                    "width": grab["width"],
                    "height": grab["height"] - BROWSER_TOP_CROP,
                }
                cropped = True

            ts = time.strftime("%H%M%S")
            fname = f"frame_{ts}_{frame_count}.png"
            fpath = os.path.join(OUTPUT_DIR, fname)

            try:
                img = sct.grab(grab)
                to_png(img.rgb, img.size, output=fpath)   # NO scaling
            except Exception as e:
                print(f"[!] Grab failed: {e}")
                time.sleep(TICK_RATE)
                continue

            meta[fname] = {
                "title": title, "region": grab,
                "content": content, "browser_cropped": cropped,
                "fullscreen": fullscreen,
                "wants_fullscreen": wants_fullscreen,
            }
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            short = (title[:42] + "…") if len(title) > 42 else title
            crop_tag = " [crop]" if cropped else ""
            # Make the trigger moment visible
            nag = "  💢 MAKE IT BIG!!" if wants_fullscreen else ""
            fs = "FS" if fullscreen else "  "
            print(f"[{captured + 1:>3}/{MAX_FRAMES}] {content:5} {fs} {fname}{crop_tag}  |  {short}{nag}")

            frame_count += 1
            captured += 1
            if captured < MAX_FRAMES:
                time.sleep(TICK_RATE)

    print("\n" + "=" * 60)
    print(f"Done! {captured} frames in {OUTPUT_DIR}")
    print(f"Metadata (window title): {META_PATH}")
    print(f"Now: python rapid_ocr_de.py {OUTPUT_DIR}")
    print("=" * 60)

except KeyboardInterrupt:
    print(f"\nAborted after {captured} frames. Found in {OUTPUT_DIR}")
