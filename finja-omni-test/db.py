"""
======================================================================
         Finja Omni Test – Database Layer
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / db
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
  SQLite storage for Finja's screen observations (Layer 1).
  Local, offline, searchable (FTS5) — like OMI/OMNI, but cleaner:
  Timestamp, app, window title, content type, perceptual hash for dedup.
======================================================================
"""

import sqlite3
from PIL import Image

DB_PATH = "finja_screen.db"


def get_conn(path=DB_PATH, check_same_thread=True):
    # check_same_thread=False for the live loop (multiple threads, one conn).
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.execute("PRAGMA busy_timeout=5000")   # wait instead of immediately "locked"
    conn.execute("PRAGMA journal_mode=WAL")    # readers do not block writers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS observations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts               TEXT,
            content          TEXT,   -- video / ide / other
            app              TEXT,
            window_title     TEXT,
            text             TEXT,
            vision           TEXT,   -- VLM scene description (Layer 2)
            phash            TEXT,
            fullscreen       INTEGER,
            wants_fullscreen INTEGER
        )""")
    # Migration: add vision column if DB is older
    cols = [r[1] for r in conn.execute("PRAGMA table_info(observations)")]
    if "vision" not in cols:
        conn.execute("ALTER TABLE observations ADD COLUMN vision TEXT")
    # Full-text search over text + title, synchronous via trigger
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS obs_fts USING fts5(
            text, window_title, content,
            content='observations', content_rowid='id')""")
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
          INSERT INTO obs_fts(rowid, text, window_title, content)
          VALUES (new.id, new.text, new.window_title, new.content);
        END;""")
    # Index on ts -> time window queries remain fast regardless of DB size
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations(ts)")
    conn.commit()
    return conn


def prune(conn, keep_days=30, vacuum=False):
    """Deletes observations older than keep_days (old screen logs = useless).
    Keeps the DB lean AND relevant. vacuum=True frees disk space."""
    import datetime
    cutoff = (datetime.datetime.now()
              - datetime.timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("DELETE FROM observations WHERE ts < ?", (cutoff,))
    # Clean up FTS (external-content -> not auto-deleted via trigger)
    conn.execute("INSERT INTO obs_fts(obs_fts) VALUES('rebuild')")
    conn.commit()
    if vacuum:
        conn.execute("VACUUM")
    return cur.rowcount


# ---------- Perceptual Hash (aHash 8x8) for Dedup ----------
def phash(image_or_path):
    """64-bit Average Hash as a hex string. Takes path OR PIL Image
    (The latter for dedup BEFORE saving in the live loop)."""
    img = image_or_path if isinstance(image_or_path, Image.Image) else Image.open(image_or_path)
    img = img.convert("L").resize((8, 8))
    px = list(img.getdata())
    avg = sum(px) / len(px)
    bits = 0
    for p in px:
        bits = (bits << 1) | (1 if p > avg else 0)
    return f"{bits:016x}"


def hamming(a, b):
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def is_duplicate(conn, new_phash, new_text, phash_thresh=4):
    """Dup if: Image almost identical (phash) OR same text as last entry.

    For static screens (IDE/reading) the phash works, for subtitles
    the text comparison works (video moves, but sub stays -> don't save twice).
    """
    row = conn.execute(
        "SELECT phash, text FROM observations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return False
    last_phash, last_text = row
    if hamming(new_phash, last_phash) <= phash_thresh:
        return True
    if new_text and new_text == last_text:
        return True
    return False


def insert(conn, row):
    row = {"vision": "", **row}   # vision optional (Layer 2 not always there)
    conn.execute("""
        INSERT INTO observations
        (ts, content, app, window_title, text, vision, phash,
         fullscreen, wants_fullscreen)
        VALUES (:ts, :content, :app, :window_title, :text, :vision, :phash,
                :fullscreen, :wants_fullscreen)""", row)
    conn.commit()


def _fts_prefix(query):
    """Turns 'Library anime' -> '"Library"* OR "anime"*' for
    prefix search."""
    import re
    words = re.findall(r"\w+", query, flags=re.UNICODE)
    if not words:
        return query
    return " OR ".join(f'"{w}"*' for w in words)


def search(conn, query, limit=20, prefix=True):
    """Full-text search -> List of (ts, content, window_title, text).

    prefix=True: Prefix/partial word search.
    """
    match = _fts_prefix(query) if prefix else query
    rows = conn.execute("""
        SELECT o.ts, o.content, o.window_title, o.text
        FROM obs_fts f JOIN observations o ON o.id = f.rowid
        WHERE obs_fts MATCH ?
        ORDER BY o.id DESC LIMIT ?""", (match, limit)).fetchall()
    return rows


def stats(conn):
    total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    by_content = conn.execute(
        "SELECT content, COUNT(*) FROM observations GROUP BY content").fetchall()
    return total, dict(by_content)
