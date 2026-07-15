"""
======================================================================
         Finja Instagram Reels – Autopilot (Prototype)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-instagram / autopilot
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
  Prototype autopilot that watches Instagram Reels in a loop:
  1. Injects cookies into the active Playwright context.
  2. Watches each Reel for a random 10-18 seconds.
  3. Takes a screenshot and scrapes metadata (title + channel).
  4. Asks the Brain (LLM) whether the Reel is a "hit".
  5. If yes: likes the video and sends a Discord DM.
  6. Swipes to the next Reel using the "Buffer-Buster" method.

  NOTE: The LLM call and Discord webhook are stubbed out.
  Configure the API URLs via .env or replace the functions entirely.

======================================================================
"""

import time
import random
import json
import os
import base64
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

# ---- Config ----
CHROME_PORT = int(os.environ.get("CHROME_PORT", 9222))
FINJA_BRAIN_URL = os.environ.get("FINJA_BRAIN_URL", "http://localhost:8051")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


# ==========================================
# J. APPS COOKIE SMUGGLER
# ==========================================

def load_instagram_cookies(context, filepath="cookies.json"):
    if not os.path.exists(filepath):
        print(f"⚠️ Cookie file '{filepath}' not found in directory! FINJA-130!")
        return False
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_cookies = json.load(f)
            
        print(f"🍪 Found {len(raw_cookies)} cookies. Preparing them for Playwright...")
        
        clean_cookies = []
        for c in raw_cookies:
            # Playwright is picky and expects exact standard fields
            clean_cookie = {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": c.get("domain"),
                "path": c.get("path", "/"),
            }
            # Handle optional fields carefully
            if "expires" in c: clean_cookie["expires"] = int(c["expires"]) if c["expires"] is not None else -1
            if "httpOnly" in c: clean_cookie["httpOnly"] = bool(c["httpOnly"])
            if "secure" in c: clean_cookie["secure"] = bool(c["secure"])
            
            # Catch SameSite issues
            if "sameSite" in c and c["sameSite"] in ["Strict", "Lax", "None"]:
                clean_cookie["sameSite"] = c["sameSite"]
                
            # Discard invalid expiration dates to prevent crashes
            if clean_cookie.get("expires") == -1:
                clean_cookie.pop("expires", None)
                
            clean_cookies.append(clean_cookie)
            
        # Inject into the browser context
        context.add_cookies(clean_cookies)
        print("🎉 All cookies successfully injected into Instagram! You should be logged in now. :3")
        return True
        
    except Exception as e:
        print(f"Oops, crumbled the cookies while loading: {e} (FINJA-203)")
        return False


# ==========================================
# J. APPS PLACEHOLDERS (FINJA'S BRAIN)
# ==========================================

def ask_brain(title, channel, screenshot_base64):
    """
    PLACEHOLDER: Send screenshot + metadata to Finja's Brain (LLM).
    Update this to use FINJA_BRAIN_URL.
    """
    print(f"[Brain] Analyzing Reel by: '{channel}' with text: '{title}'...")
    return random.choice([True, False])


def send_to_discord(video_url):
    """
    PLACEHOLDER: Send the video URL to a Discord channel via webhook.
    Update this to use DISCORD_WEBHOOK_URL.
    """
    print(f"[Discord] 🚀 Message secretly sent: {video_url}")


# ==========================================
# BUFFER-BUSTER FOR ARROW DOWN
# ==========================================

def buffer_buster_jump(page):
    """Presses ArrowDown and retries if Instagram is buffering/stuck."""
    old_url = page.url
    print("\nPressing ArrowDown... 🔽")
    page.keyboard.press("ArrowDown")
    
    time.sleep(1.2)
    
    retries = 0
    while page.url == old_url and retries < 3:
        retries += 1
        print(f"⚠️ Loading buffer blocked! Finja presses down again ({retries})... :3")
        page.keyboard.press("ArrowDown")
        time.sleep(1.5)
        
    if page.url != old_url:
        print("🎉 Barrier broken! Next Reel active.")
    else:
        print("Mhm, Instagram is stuck. FINJA-130 (No fire found)!")


# ==========================================
# THE ACTUAL AUTOPILOT
# ==========================================

def autopilot(port=CHROME_PORT):
    print("Instagram Autopilot starting up... Ready for cookie injection! :3")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            page = context.pages[0]
            
            # 1. Inject cookies directly into the opened window
            load_instagram_cookies(context)
            
            # Reload page so Instagram recognizes the cookies
            print("Reloading page to activate login...")
            page.reload()
            time.sleep(3)
            
            page.bring_to_front()
            print("Grabbing keyboard focus with a click in the center...")
            page.mouse.click(500, 500)
            time.sleep(1)
            
            while True:
                watch_time = random.randint(10, 18)
                print(f"\nWatching Reel for {watch_time} seconds...")
                time.sleep(watch_time)
                
                # Scrape metadata
                try:
                    channel_el = page.locator("span[style*='font-weight: 600']").first
                    channel = channel_el.inner_text() if channel_el.is_visible() else "Unknown Creator"
                    
                    title_el = page.locator("span._ap3a, span").first
                    title = title_el.inner_text()[:60] if title_el.is_visible() else "No description"
                except Exception:
                    title, channel = "Scrape error", "Scrape error"
                
                # Screenshot for Finja
                print("Taking a stealthy snapshot...")
                screenshot_bytes = page.screenshot(type="jpeg", quality=50)
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                is_a_hit = ask_brain(title, channel, screenshot_base64)
                
                if is_a_hit:
                    print("🎉 FINJA SAYS YES!")
                    try:
                        like_svg = page.locator("svg[aria-label='Gefällt mir'], svg[aria-label='Like']").first
                        if like_svg.is_visible():
                            like_svg.locator("xpath=..").click()
                            print("❤️ Reel liked!")
                            time.sleep(1)
                    except Exception as e:
                        print(f"Could not hit the heart: {e}")
                    
                    send_to_discord(page.url)
                else:
                    print("Finja looks away. Moving on.")
                
                # Move to next Reel using the Buffer-Buster
                buffer_buster_jump(page)
                
        except Exception as error:
            print(f"Massive workshop crash! FINJA-203! Details: {error}")

if __name__ == "__main__":
    autopilot()