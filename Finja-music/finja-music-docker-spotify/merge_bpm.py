#!/usr/bin/env python3
"""
======================================================================
          BPM/Key Merge Tool - Knowledge Base Enrichment
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-music-docker-spotify
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.1.0
  Description: Merges scraped BPM/Key data from fertige_bpm_keys.json
               into songs_kb.json. Uses spotify_id to match songs.
               Creates automatic backups before modifying the KB.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""
import json
from pathlib import Path

DB_DIR = Path(__file__).parent / "SongsDB"
SONGS_FILE = DB_DIR / "songs_kb.json"
BPM_FILE = DB_DIR / "fertige_bpm_keys.json"

def _load_data():
    """Load BPM data and songs KB from disk."""
    with open(BPM_FILE, encoding="utf-8") as f:
        bpm_data = json.load(f)
    print(f"[LOAD] {len(bpm_data)} BPM entries loaded")

    with open(SONGS_FILE, encoding="utf-8") as f:
        songs = json.load(f)
    print(f"[LOAD] {len(songs)} songs loaded")
    return bpm_data, songs


def _create_backup(songs):
    """Create a backup of songs_kb.json before modifying."""
    backup_path = DB_DIR / "backups" / "songs_kb_pre_merge.json"
    backup_path.parent.mkdir(exist_ok=True)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)
    print(f"[BACKUP] {backup_path}")


def _merge_song(song, bpm_data):
    """Try to merge BPM/Key into a single song. Returns skip reason or None on success."""
    spotify_id = song.get("spotify_id")
    if not spotify_id:
        return "no_id"
    if spotify_id not in bpm_data:
        return "no_match"

    entry = bpm_data[spotify_id]
    bpm_val = entry.get("bpm", "0")
    key_val = entry.get("key", "Unknown")

    if bpm_val == "0" and key_val == "Unknown":
        return "unknown"
    if song.get("bpm") and song.get("key"):
        return "already"

    try:
        song["bpm"] = int(bpm_val) if bpm_val != "0" else 0
    except (ValueError, TypeError):
        song["bpm"] = 0
    song["key"] = key_val if key_val != "Unknown" else ""
    return None


def main():
    print("=" * 60)
    print("  Merge BPM/Key Data into songs_kb.json")
    print("=" * 60)

    bpm_data, songs = _load_data()
    _create_backup(songs)

    # Merge
    counts = {"merged": 0, "no_id": 0, "no_match": 0, "already": 0, "unknown": 0}
    for song in songs:
        reason = _merge_song(song, bpm_data)
        if reason:
            counts[reason] += 1
        else:
            counts["merged"] += 1

    print("\n[RESULTS]")
    print(f"  Merged:           {counts['merged']}")
    print(f"  Already had BPM:  {counts['already']}")
    print(f"  No spotify_id:    {counts['no_id']}")
    print(f"  No BPM match:     {counts['no_match']}")
    print(f"  Unknown/zero BPM: {counts['unknown']}")

    # Save
    with open(SONGS_FILE, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)
    print("\n[SAVE] songs_kb.json updated!")

    # Stats
    has_bpm = sum(1 for s in songs if s.get("bpm"))
    total = len(songs)
    print(f"[STATS] {has_bpm}/{total} songs have BPM ({100*has_bpm/total:.1f}%)")

if __name__ == "__main__":
    main()
