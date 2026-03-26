#!/usr/bin/env python3
"""
======================================================================
          Jank Mommy's BPM Controller - Spotify Enrichment
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-music-docker-spotify / SongsDB
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Automated BPM/Key scraping controller that forces
               Spotify Desktop to play each song, waits for the
               Spicetify jank_scraper.js extension to capture
               BPM/Key data from the DJ UI, and saves results.

  How it works:
    1. Loads a list of songs to enrich from .enrich_progress.json
    2. Starts a local HTTP server on port 8080
    3. For each song: opens it in Spotify, pauses playback,
       waits for the Spicetify scraper to POST the BPM/Key data
    4. Saves progress after each song (resume-safe)

  Requirements:
    - Spicetify with jank_scraper.js installed
    - pyautogui (for simulating play/pause)
    - Spotify Desktop app running

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import json
import time
import os
import threading
import pyautogui  # Our magic "STOP" button! :3
from http.server import HTTPServer, BaseHTTPRequestHandler

# Get the exact path where this script is located!
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, ".enrich_progress.json")
OUT_PATH = os.path.join(SCRIPT_DIR, "fertige_bpm_keys.json")

# Store our captured data here
collected_data = {}
current_song_id = None

# NEW: Our magic Walkie-Talkie! Used to wait for data from the scraper.
data_received = threading.Event()

class ScraperHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Receives data from our Spicetify extension"""
        global current_song_id

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))

        print(f"  [+] Data captured: BPM={data['bpm']} | Key={data['key']}")

        # Save data under the requested ID. 
        # This ensures our resume feature works perfectly!
        if current_song_id:
             collected_data[current_song_id] = {
                 "bpm": data['bpm'],
                 "key": data['key'],
                 "scraped_id": data['id'] # Just for safety
             }

        # NEW: Signal to the main thread: "We got the data, you can move on!"
        data_received.set()

        # Respond to Spicetify that everything arrived safely
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')  # NOSONAR
        self.end_headers()

    def do_OPTIONS(self):
        """Allows Spicetify to talk to us (CORS)"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')  # NOSONAR
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass # Hides noisy logs

def start_server():
    # Use HTTP on 127.0.0.1 as it's only locally accessible.
    # Switching to HTTPS (SSL) would be unnecessarily complex for this use case.
    server = HTTPServer(('127.0.0.1', 8080), ScraperHandler)
    print("[*] Jank Mommy's Mothership listening on Port 8080... :3\n")
    server.serve_forever()

def play_song_in_spotify(spotify_id):
    """Forces the desktop app to play the song"""
    uri = f"spotify:track:{spotify_id}"
    os.system(f"start {uri}")

def start_the_madness():
    global current_song_id

    # 1. Load our target list
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[-] Oh no! I'm looking right here: {JSON_PATH}")
        return

    songs = data.get("enriched", {})
    print(f"[*] {len(songs)} songs found in target list!")

    # 2. Load progress (RESUME FEATURE)
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, "r", encoding="utf-8") as f:
                previous_data = json.load(f)
                collected_data.update(previous_data)
            print(f"[*] {len(collected_data)} finished songs loaded! Resuming where we left off... :3")
        except Exception as e:
            print(f"[-] Could not load previous progress: {e}")

    # Start server in background
    threading.Thread(target=start_server, daemon=True).start()
    time.sleep(2)

    for name, s_id in songs.items():
        # Check: Do we already have this song? If so, skip it!
        if s_id in collected_data:
            continue

        current_song_id = s_id
        data_received.clear() # Set walkie-talkie back to "Waiting"

        print(f"\n[*] Forcing Spotify to: {name}")
        play_song_in_spotify(s_id)

        # Let the song play for 6 seconds
        time.sleep(6)

        # Stop music (Triggers the UI)
        print("  [*] Virtual STOP to reload Spicetify UI... :3")
        pyautogui.press('playpause')

        # NEW: Wait for signal from server (Max 15 seconds)
        success = data_received.wait(timeout=15.0)

        if success:
            print("  [+] Perfect, next one!")
        else:
            print("  [-] Timeout (15s)! No data received. Saving empty entry and continuing.")
            # Save anyway (without data) so it doesn't get stuck next time
            collected_data[current_song_id] = {"bpm": "0", "key": "Unknown", "error": "timeout"}

        # Save after each song
        with open(OUT_PATH, "w", encoding="utf-8") as out:
            json.dump(collected_data, out, indent=4)

if __name__ == "__main__":
    print("=== Operation: F**** you, Spotify API ===")
    start_the_madness()
    print("\n[+] Captured them all! :3")