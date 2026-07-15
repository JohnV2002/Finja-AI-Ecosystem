"""
======================================================================
         Finja Omni Test – Live Pipeline
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / live
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
  Finja LIVE — parallel screen observation (Layer 1 + 2).
  Three threads, so slow Vision NEVER blocks fast OCR:

    [Producer]  every TICK s: active window -> Dedup (phash)
          |-- ocr_q --> [OCR-Worker]  video->OCR(Subs), ide/other->Title  (fast)
          '-- latest -> [Vision-Worker]  per content type at own pace (slow, background)
                          both -> SQLite (one connection + lock)

  CTRL+C exits cleanly.   ->   python live.py
======================================================================
"""

import time
import queue
import threading

import mss

import capture
import db
import ocr
import see

# --- CONFIG ---
TICK           = 3     # snappier (with preloaded models no problem)
PHASH_DUP      = 4
VISION_ENABLED = True
VISION_EVERY   = {"video": 30, "ide": 60, "other": 60}   # seconds per type
VISION_BACKEND = "local"     # "local" (Ollama) or "openrouter" (Cloud)
SUB_BAND       = 0.45

ocr_q   = queue.Queue(maxsize=8)
latest  = {"grab": None}                 # newest frame for the Vision thread
latest_lock = threading.Lock()
db_lock = threading.Lock()               # serializes DB writers
stop = threading.Event()


def do_vision(b64):
    if VISION_BACKEND == "openrouter":
        return see.see_openrouter(b64)
    return see.see_local(b64)


def warmup():
    """Load models ONCE at startup so everything runs warm from Frame 1
    (no stall during operation). Takes ~half a minute, then snappy."""
    import io, base64
    from PIL import Image
    dummy = Image.new("RGB", (64, 64))

    print("  Loading OCR model (latin5fast)...", flush=True)
    try:
        ocr.read_text(dummy)
        print("    ✓ OCR ready")
    except Exception as e:
        print(f"    ! OCR Warmup: {e}")

    if VISION_ENABLED and VISION_BACKEND == "local":
        print("  Loading Vision model (minicpm, ~25s)...", flush=True)
        try:
            buf = io.BytesIO(); dummy.save(buf, format="PNG")
            do_vision(base64.b64encode(buf.getvalue()).decode())
            print("    ✓ Vision ready")
        except Exception as e:
            print(f"    ! Vision Warmup: {e}")


def save(conn, grab, text, vision):
    """Saves with the CAPTURE timestamp of the frame (not 'now').
    -> Vision results end up in the timeline where the screenshot
    was taken. Lag becomes harmless (rewind principle like OMI)."""
    with db_lock:
        db.insert(conn, {
            "ts": grab["captured_at"],
            "content": grab["content"], "app": grab["app"],
            "window_title": grab["title"], "text": text, "vision": vision,
            "phash": grab["phash"],
            "fullscreen": 1 if grab["fullscreen"] else 0,
            "wants_fullscreen": 1 if grab["wants_fullscreen"] else 0,
        })


def producer():
    last_phash = None
    with mss.MSS() as sct:
        while not stop.is_set():
            try:
                grab = capture.grab_active(sct)
            except Exception as e:
                print(f"[producer] {e}"); stop.wait(TICK); continue

            ph = db.phash(grab["image"])
            if last_phash and db.hamming(ph, last_phash) <= PHASH_DUP:
                stop.wait(TICK); continue
            last_phash = ph
            grab["phash"] = ph
            grab["captured_at"] = time.strftime("%Y-%m-%d %H:%M:%S")  # Capture time!

            with latest_lock:
                latest["grab"] = grab          # for Vision thread
            try:
                ocr_q.put_nowait(grab)
            except queue.Full:                 # stay current: pop oldest
                try: ocr_q.get_nowait()
                except queue.Empty: pass
                try: ocr_q.put_nowait(grab)
                except queue.Full: pass
            stop.wait(TICK)


def ocr_worker():
    conn = db.get_conn(check_same_thread=False)
    while not (stop.is_set() and ocr_q.empty()):
        try:
            grab = ocr_q.get(timeout=1)
        except queue.Empty:
            continue
        content, fs = grab["content"], grab["fullscreen"]
        text = ""
        if content == "video":
            try:
                text = ocr.read_text(grab["image"], band=SUB_BAND if fs else None)
            except Exception as e:
                text = f"[ocr err: {e}]"
        save(conn, grab, text, "")
        nag = " 💢" if grab["wants_fullscreen"] else ""
        out = f"  [{time.strftime('%H:%M:%S')}] {content:5}{nag} {grab['app'][:20]:20}"
        if text:
            out += f"  📖 {text[:50]}"
        print(out)
        ocr_q.task_done()
    conn.close()


def vision_worker():
    conn = db.get_conn(check_same_thread=False)
    last = {"video": 0.0, "ide": 0.0, "other": 0.0}
    while not stop.is_set():
        with latest_lock:
            grab = latest["grab"]
        if VISION_ENABLED and grab:
            content = grab["content"]
            interval = VISION_EVERY.get(content)
            now = time.time()
            if interval and now - last.get(content, 0) >= interval:
                try:
                    b64 = see.prep_image(grab["image"], content, grab["fullscreen"])
                    desc = do_vision(b64)
                except Exception as e:
                    desc = f"[vision err: {e}]"
                last[content] = now
                save(conn, grab, "", desc)   # ts = capture time of the frame
                cap = grab["captured_at"].split(" ")[-1]
                print(f"        👁  [{content} @{cap}] {desc[:85]}")
        stop.wait(2)   # check frequently, but timer decides on calls
    conn.close()


if __name__ == "__main__":
    vmode = (f"{VISION_BACKEND} (video/{VISION_EVERY['video']}s, "
             f"ide+other/{VISION_EVERY['ide']}s)" if VISION_ENABLED else "off")
    print("=" * 64)
    print("  FINJA LIVE  —  Screen observation running")
    print(f"  Tick: {TICK}s | Vision: {vmode} | DB: {db.DB_PATH}")
    print("=" * 64)

    warmup()   # preload models -> warm from frame 1
    print("=" * 64)
    print("  GO! Observation running. CTRL+C to exit.")
    print("=" * 64)

    threads = [
        threading.Thread(target=producer, name="producer", daemon=True),
        threading.Thread(target=ocr_worker, name="ocr", daemon=True),
        threading.Thread(target=vision_worker, name="vision", daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  Exiting... (waiting for running frames)")
        stop.set()
        for t in threads:
            t.join(timeout=10)
        total, by = db.stats(db.get_conn())
        print(f"  Done. DB entries total: {total}  {by}")
