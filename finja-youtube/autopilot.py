"""
======================================================================
         Finja YouTube Shorts – Autopilot (Prototype)
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-youtube / autopilot
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
  Prototype autopilot that watches YouTube Shorts in a loop:
  1. Watches each video for a random 10-18 seconds
  2. Takes a screenshot and scrapes metadata (title + channel)
  3. Asks the Brain (LLM) whether the video is a "hit"
  4. If yes: likes the video and sends a Discord DM
  5. Scrolls to the next Short and repeats

  NOTE: The LLM call and Discord webhook are stubbed out.
  Replace the placeholder functions with real API calls.

======================================================================
"""

import os
import time
import random
import base64
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

# ---- Config ----
CHROME_PORT = int(os.environ.get("CHROME_PORT", 9222))
FINJA_BRAIN_URL = os.environ.get("FINJA_BRAIN_URL", "http://localhost:8051")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


# ==========================================
# Placeholder section (replace with real APIs)
# ==========================================

def ask_brain(title, channel, screenshot_base64):
    """
    PLACEHOLDER: Send screenshot + metadata to Finja's Brain (LLM).

    Replace this with your actual API call, e.g.:
        response = requests.post(FINJA_BRAIN_URL, json={
            "title": title,
            "channel": channel,
            "image_b64": screenshot_base64,
        })
        return response.json().get("liked", False)
    """
    print(f"[Brain] Analyzing video: '{title}' by '{channel}'...")

    # For the prototype, we just flip a coin:
    return random.choice([True, False])


def send_to_discord(video_url):
    """
    PLACEHOLDER: Send the video URL to a Discord channel via webhook.

    Replace this with your actual webhook call, e.g.:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": f"Check this out: {video_url}"})
    """
    print(f"[Discord] Sent video link: {video_url}")


# ==========================================
# Autopilot loop
# ==========================================

def autopilot(port=CHROME_PORT):
    print("Autopilot starting up... Ready to scroll! :3")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            page = context.pages[0]

            print("Connected! Autopilot is now in control.")

            while True:
                # 1. Watch the video for a human-like duration
                watch_time = random.randint(10, 18)
                print(f"\nWatching video for {watch_time} seconds...")
                time.sleep(watch_time)

                # 2. Scrape metadata (title & channel)
                try:
                    title_el = page.locator("h2.title yt-formatted-string").first
                    title = title_el.inner_text() if title_el.is_visible() else "Unknown title"

                    channel_el = page.locator("#channel-name .yt-simple-endpoint").first
                    channel = channel_el.inner_text() if channel_el.is_visible() else "Unknown channel"
                except Exception:
                    title, channel = "Scrape error", "Scrape error"

                # 3. Take a screenshot (base64 for the LLM)
                print("Taking screenshot...")
                screenshot_bytes = page.screenshot(type="jpeg", quality=50)
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

                # 4. Ask the Brain
                is_a_hit = ask_brain(title, channel, screenshot_base64)

                if is_a_hit:
                    print("Brain says YES! This is a hit!")

                    # 5. Like the video
                    try:
                        like_button = page.locator("ytd-reel-video-renderer[is-active] #like-button button").first
                        if like_button.is_visible():
                            like_button.click()
                            print("Video liked! The algorithm is learning...")
                            time.sleep(1)
                    except Exception as e:
                        print(f"Could not find like button: {e}")

                    # 6. Send to Discord
                    send_to_discord(page.url)

                else:
                    print("Brain says no. Skipping this one.")

                # 7. Scroll to the next video
                print("Swiping to next Short...")
                page.keyboard.press("ArrowDown")

                # Short pause between swipes
                time.sleep(2)

        except Exception as error:
            print("Connection lost or critical crash! FINJA-203!")
            print(f"Details: {error}")


if __name__ == "__main__":
    autopilot()