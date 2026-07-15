"""
======================================================================
         Finja Omni Test – Capture Processor
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / verarbeite
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
  Processes a capture folder -> Routing -> SQLite.
  This is the core that will later run in the VPet: decide per frame 
  based on the content type (from meta.json) if & how OCR runs, skip 
  duplicates, write result to the DB.

  Routing:
    video  -> OCR (bottom strip = subtitles), save text
    ide    -> NO OCR (too slow/noisy) -> title only; content later via Layer 2
    other  -> NO OCR -> title only (Discord/Browser); possibly later Layer 2

      python verarbeite.py captures/realworld3
======================================================================
"""

import os
import sys
import glob
import json
import time

import db
from ocr import read_text

# Which content types get expensive OCR? (Rest: save title only)
OCR_CONTENT = {"video"}
# Subtitle zone: bottom X of the image (only useful for fullscreen video)
SUB_BAND = 0.45

INPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "captures/realworld3"
META_PATH = os.path.join(INPUT_DIR, "meta.json")

if not os.path.exists(META_PATH):
    raise SystemExit(f"No meta.json in '{INPUT_DIR}' – run capture_active.py first.")

with open(META_PATH, encoding="utf-8") as f:
    meta = json.load(f)


def app_from_title(title):
    """App = last ' - ' segment in title (e.g. 'Google Chrome', 'Antigravity IDE')."""
    if not title:
        return "?"
    parts = [p.strip() for p in title.split(" - ")]
    return parts[-1] if len(parts) > 1 else title.strip()


conn = db.get_conn()

print("=" * 64)
print(f"  PROCESSING {INPUT_DIR}  ->  {db.DB_PATH}")
print("=" * 64)

frames = sorted(glob.glob(os.path.join(INPUT_DIR, "*.png")))
stored = skipped_dup = ocred = title_only = 0

for path in frames:
    fname = os.path.basename(path)
    info = meta.get(fname, {})
    content = info.get("content", "other")
    title = info.get("title", "")
    fullscreen = 1 if info.get("fullscreen") else 0
    wants_fs = 1 if info.get("wants_fullscreen") else 0

    # --- Routing: only 'video' gets OCR ---
    text = ""
    if content in OCR_CONTENT:
        # Fullscreen video -> subtitle strip only; otherwise whole (small) image
        band = SUB_BAND if fullscreen else None
        t0 = time.perf_counter()
        text = read_text(path, band=band)
        dt = time.perf_counter() - t0
        ocred += 1
        tag = f"OCR {dt:4.1f}s"
    else:
        title_only += 1
        tag = "title-only"

    ph = db.phash(path)
    if db.is_duplicate(conn, ph, text):
        skipped_dup += 1
        print(f"  [dup ] {content:5} {fname}")
        continue

    db.insert(conn, {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "content": content,
        "app": app_from_title(title),
        "window_title": title,
        "text": text,
        "phash": ph,
        "fullscreen": fullscreen,
        "wants_fullscreen": wants_fs,
    })
    stored += 1
    preview = (text[:60] + "…") if len(text) > 60 else text
    print(f"  [save] {content:5} {tag:11} {fname}  {preview}")

total, by_content = db.stats(conn)
print("=" * 64)
print(f"  Processed: {len(frames)}  |  saved: {stored}  |  "
      f"duplicates skipped: {skipped_dup}")
print(f"  OCR run: {ocred}  |  title only: {title_only}")
print(f"  DB total: {total}  ->  {by_content}")
print("=" * 64)

# --- Demo: Full-text search ---
print("\n  Demo Search:")
for q in ["youtube", "anime", "Bibliothek", "Discord"]:
    hits = db.search(conn, q, limit=3)
    print(f"\n  >>> '{q}'  ({len(hits)} hits)")
    for ts, content, wt, text in hits:
        snippet = (text or wt)[:70]
        print(f"      [{content}] {snippet}")

conn.close()
print("\n  Tip: custom search -> python -c \"import db;c=db.get_conn();"
      "print(db.search(c,'YOUR_WORD'))\"")
