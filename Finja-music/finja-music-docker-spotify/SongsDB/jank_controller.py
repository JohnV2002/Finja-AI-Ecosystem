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
import pyautogui  # Unsere magische "STOP"-Taste! :3
from http.server import HTTPServer, BaseHTTPRequestHandler

# Wir holen uns den exakten Pfad, wo dieses Skript gerade liegt!
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, ".enrich_progress.json")
OUT_PATH = os.path.join(SCRIPT_DIR, "fertige_bpm_keys.json")

# Hier speichern wir unsere erbeuteten Daten
gesammelte_daten = {}
aktueller_song_id = None

# NEU: Das ist unser magisches Walkie-Talkie! Damit wartet das Skript auf die Daten.
daten_erhalten = threading.Event()

class ScraperHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Empfängt die Daten von unserer Spicetify-Extension"""
        global aktueller_song_id

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        daten = json.loads(post_data.decode('utf-8'))

        print(f"  [+] Daten erbeutet: BPM={daten['bpm']} | Key={daten['key']}")

        # Wir speichern die Daten unter der ID, die wir angefragt haben.
        # So funktioniert unsere Resume-Funktion perfekt!
        if aktueller_song_id:
             gesammelte_daten[aktueller_song_id] = {
                 "bpm": daten['bpm'],
                 "key": daten['key'],
                 "scraped_id": daten['id'] # Nur zur Sicherheit
             }

        # NEU: Wir funken an den Haupt-Thread: "Wir haben die Daten, du kannst weitermachen!"
        daten_erhalten.set()

        # Antwort an Spicetify, dass alles gut angekommen ist
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')  # NOSONAR
        self.end_headers()

    def do_OPTIONS(self):
        """Erlaubt Spicetify, überhaupt mit uns zu reden (CORS)"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')  # NOSONAR
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass # Versteckt nervige Logs

def starte_server():
    # Wir benutzen HTTP auf 127.0.0.1, da dies nur lokal erreichbar ist. 
    # Ein Wechsel auf HTTPS (SSL) wäre für diesen Anwendungsfall unnötig komplex.
    server = HTTPServer(('127.0.0.1', 8080), ScraperHandler)
    print("[*] Jank Mommy's Mutterschiff lauscht auf Port 8080... :3\n")
    server.serve_forever()

def spiele_song_in_spotify(spotify_id):
    """Zwingt die Desktop-App, den Song zu spielen"""
    uri = f"spotify:track:{spotify_id}"
    os.system(f"start {uri}")

def starte_den_wahnsinn():
    global aktueller_song_id

    # 1. Lade unsere Ziel-Liste
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except FileNotFoundError:
        print(f"[-] Oh nein! Ich suche genau hier: {JSON_PATH}")
        return

    songs = daten.get("enriched", {})
    print(f"[*] {len(songs)} Songs in der Ziel-Liste gefunden!")

    # 2. Lade bisherigen Fortschritt (RESUME FUNKTION)
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, "r", encoding="utf-8") as f:
                bisherige_daten = json.load(f)
                gesammelte_daten.update(bisherige_daten)
            print(f"[*] {len(gesammelte_daten)} fertige Songs geladen! Mache da weiter, wo wir aufgehört haben... :3")
        except Exception as e:
            print(f"[-] Konnte alten Fortschritt nicht laden: {e}")

    # Server im Hintergrund starten
    threading.Thread(target=starte_server, daemon=True).start()
    time.sleep(2)

    for name, s_id in songs.items():
        # Check: Haben wir den Song schon? Dann überspringen wir ihn sofort!
        if s_id in gesammelte_daten:
            continue

        aktueller_song_id = s_id
        daten_erhalten.clear() # Wir stellen das Walkie-Talkie wieder auf "Warten"

        print(f"\n[*] Zwinge Spotify zu: {name}")
        spiele_song_in_spotify(s_id)

        # Wir lassen das Lied 6 Sekunden laufen.
        time.sleep(6)

        # Musik Stoppen (Triggert das UI)
        print("  [*] Drücke virtuell STOP, damit das Spicetify UI nachlädt... :3")
        pyautogui.press('playpause')

        # NEU: Wir warten auf das Signal vom Server (Maximal 15 Sekunden)
        erfolg = daten_erhalten.wait(timeout=15.0)

        if erfolg:
            print("  [+] Perfekt, weiter zum nächsten!")
        else:
            print("  [-] Timeout (15s)! Keine Daten gekommen. Wir speichern ihn leer und machen weiter.")
            # Wir speichern ihn trotzdem (ohne Daten), damit er beim nächsten Mal nicht wieder hängt
            gesammelte_daten[aktueller_song_id] = {"bpm": "0", "key": "Unknown", "error": "timeout"}

        # Speichern nach jedem Song
        with open(OUT_PATH, "w", encoding="utf-8") as out:
            json.dump(gesammelte_daten, out, indent=4)

if __name__ == "__main__":
    print("=== Operation: F*** you, Spotify API ===")
    starte_den_wahnsinn()
    print("\n[+] Wir haben sie alle! :3")
