"""
======================================================================
         Finja YouTube Shorts – Browser Launcher
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-youtube / browser-launcher
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
  Launches a local Chrome/Chromium instance in mobile emulation mode
  with CDP remote debugging enabled. Used for local development and
  testing — the Docker container uses its own headless Chrome instead.

  • Auto-detects OS (Windows / Linux)
  • Finds Chrome/Chromium installation automatically
  • Opens YouTube Shorts in mobile viewport (412x915)
  • Enables CDP on the specified port (default: 9222)

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
YOUTUBE_TARGET_URL = os.environ.get("YOUTUBE_TARGET_URL", "https://www.youtube.com/shorts")
MOBILE_UA = os.environ.get("MOBILE_UA", "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")


def start_mobile_browser(target_url=YOUTUBE_TARGET_URL, port=CHROME_PORT):
    # Detect operating system
    operating_system = platform.system()
    print(f"[Launcher] Detected OS: {operating_system}")

    # 1. Create a temporary profile directory
    if operating_system == "Windows":
        user_path = os.environ.get('USERPROFILE', 'C:')
        temp_dir = os.path.join(user_path, 'AppData', 'Local', 'Temp', f'finja_mobile_profile_{port}')
    else:
        # On Linux / Docker use the standard temp directory
        temp_dir = f"/tmp/finja_mobile_profile_{port}"

    os.makedirs(temp_dir, exist_ok=True)

    # 2. Find the browser executable
    if operating_system == "Windows":
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
    else:
        # Typical locations on Linux / Docker
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser"
        ]

    chrome_exe = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_exe = path
            break

    if not chrome_exe:
        print("[Launcher] ERROR: Chrome/Chromium not found! FINJA-999")
        return None

    print(f"[Launcher] Starting mobile browser on port {port}...")

    # Mobile user agent (Samsung S22 Ultra)
    mobile_ua = MOBILE_UA

    # Chrome launch arguments
    args = [
        chrome_exe,
        f"--user-data-dir={temp_dir}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-agent={mobile_ua}",
        "--window-size=412,915",
        "--hide-scrollbars",
    ]

    # 3. Extra flags for Linux / Docker
    if operating_system == "Linux":
        args.extend([
            "--no-sandbox",             # Required inside Docker
            "--disable-dev-shm-usage"   # Prevents shared-memory crashes in Docker
        ])

        # NOTE: If running in a headless Docker environment (no GUI),
        # uncomment the following line:
        # args.append("--headless=new")

    args.append(target_url)

    # Launch browser
    browser_process = subprocess.Popen(args)

    # Wait for CDP to become available
    print("[Launcher] Waiting for CDP port to open...")
    cdp_ready = False

    for _ in range(40):
        try:
            response = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            if response.getcode() == 200:
                cdp_ready = True
                break
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(0.5)

    if cdp_ready:
        print("[Launcher] Browser is ready! CDP port is open. :3")
        return browser_process
    else:
        print("[Launcher] ERROR: CDP port did not open in time. FINJA-130")
        browser_process.terminate()
        return None


if __name__ == "__main__":
    start_mobile_browser()