"""
======================================================================
         Finja Instagram Reels – Browser Launcher
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram / browser-launcher
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Launches a local Chrome/Chromium instance in Desktop Mode
  (NO mobile emulation!) with CDP remote debugging enabled for the API.

  • Auto-detects OS (Windows / Linux)
  • Finds Chrome/Chromium installation automatically
  • Opens about:blank in full desktop resolution
  • Enables CDP on the specified port (default: 9222)

  NOTE: Desktop Mode is required because ArrowDown navigation
  in the Reels feed is most stable in the desktop layout.

----------------------------------------------------------------------
 New in v1.1.0:
----------------------------------------------------------------------
  • Adopted into Production ("Finja - Instagram test" folder) as part
    of the module version/header unification (2026-07-19) -- no
    functional changes in this file specifically

======================================================================
"""

import os
import subprocess
import time
import urllib.request
import urllib.error
import platform

# ---- Config ----
CHROME_PORT = int(os.environ.get("CHROME_PORT", 9222))
INSTAGRAM_TARGET_URL = os.environ.get("INSTAGRAM_TARGET_URL", "about:blank")


def start_instagram_browser(target_url=INSTAGRAM_TARGET_URL, port=CHROME_PORT):
    system = platform.system()
    print(f"[BROWSER] OS: {system}")

    # Persistent Chrome Profile (Cookies are retained)
    if system == "Windows":
        home = os.environ.get("USERPROFILE", "C:")
        profile_dir = os.path.join(home, "AppData", "Local", "finja_instagram_profil")
    else:
        home = os.path.expanduser("~")
        profile_dir = os.path.join(home, ".finja_instagram_profil")

    os.makedirs(profile_dir, exist_ok=True)
    print(f"[BROWSER] Profile: {profile_dir}")

    # Find Chrome executable
    if system == "Windows":
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]

    chrome_exe = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_exe = path
            break

    if not chrome_exe:
        print("[BROWSER] Chrome not found! FINJA-999")
        return None

    # Desktop Mode: Fullscreen, NO mobile user agent
    args = [
        chrome_exe,
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        target_url,
    ]

    if system == "Linux":
        args.extend(["--no-sandbox", "--disable-dev-shm-usage"])

    print(f"[BROWSER] Starting Chrome on port {port}...")
    proc = subprocess.Popen(args)

    # Wait for CDP to be ready
    for i in range(40):
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            if r.getcode() == 200:
                print(f"[BROWSER] Chrome ready! CDP active on port {port}")
                print(f"[BROWSER] Now start: python instagram_api.py")
                return proc
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(0.5)

    print("[BROWSER] Chrome is not responding! FINJA-130")
    proc.terminate()
    return None


if __name__ == "__main__":
    start_instagram_browser()
