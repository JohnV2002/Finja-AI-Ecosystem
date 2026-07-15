"""
======================================================================
         Finja Omni Test – Speech Bubble
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / bubble
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
  Finja Speech Bubble — floating overlay with Finja's thoughts on the screen.
  Reads the timeline (Vision + OCR) that `live.py` writes to the DB, 
  asks the LLM every few seconds "what are you thinking right now?", 
  and shows the answer in a floating bubble (always-on-top, above 
  fullscreen video).

  Temporary stand-in for what the VPet will do later.

      1. Terminal A:  python live.py     (observes + writes DB)
      2. Terminal B:  python bubble.py   (shows Finja's thoughts)

  Quit: ESC or right-click the bubble. Move: drag.
======================================================================
"""
import time
import threading
import tkinter as tk
from tkinter import font as tkfont

import db
import quatsch

# Event-driven: reacts to app switch (snappy), otherwise "ambient" now and then.
POLL_SEC    = 4         # how often to check for changes (cheap, only DB query)
AMBIENT_SEC = 35        # if nothing changes (e.g. Anime): a thought every Xs
RECENT_SEC  = 22        # Context = only the last Xs -> always FRESH (no lag!)
WIDTH       = 360       # Bubble width (px)
LOG_FILE    = "finja_thoughts.txt"   # all thoughts for copying/sharing


def log(tag, text):
    """Prints Finja's thoughts to console + file (for reading along/sharing)."""
    line = f"[{time.strftime('%H:%M:%S')}] {tag}: {text}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# Colors (dark, friendly bubble)
BG     = "#1e1f2b"
ACCENT = "#ff9ec4"      # Finja Pink
TEXT   = "#f0f0f5"
MUTED  = "#8a8ba0"


class Bubble:
    def __init__(self, root):
        self.root = root
        root.attributes("-alpha", 0.95)         # slightly transparent
        root.configure(bg=ACCENT)               # serves as a thin border

        # Position: bottom right
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = sw - WIDTH - 30
        y = sh - 260
        root.geometry(f"{WIDTH}x220+{x}+{y}")

        # Pink border: 2px accent all around
        frame = tk.Frame(root, bg=BG, padx=16, pady=12)
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Borderless + always on top + bring to front (robust on Windows)
        root.overrideredirect(True)
        root.update_idletasks()
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(50, lambda: root.focus_force())

        head = tk.Label(frame, text="🦊  Finja", bg=BG, fg=ACCENT,
                        font=tkfont.Font(size=13, weight="bold"))
        head.pack(anchor="w")

        self.body = tk.Label(
            frame, text="is looking around ...", bg=BG, fg=TEXT,
            font=tkfont.Font(size=11), wraplength=WIDTH - 36,
            justify="left", anchor="nw")
        self.body.pack(anchor="w", pady=(6, 0), fill="both", expand=True)

        self.status = tk.Label(frame, text="", bg=BG, fg=MUTED,
                               font=tkfont.Font(size=8))
        self.status.pack(anchor="e", side="bottom")

        # Interaction: drag to move, ESC/right-click to close
        for w in (frame, head, self.body):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._on_move)
        root.bind("<Escape>", lambda e: root.destroy())
        root.bind("<Button-3>", lambda e: root.destroy())

        self._busy = False
        self.last_ts = None            # timestamp of last seen frame
        self.last_comment = None       # what Finja said last (against repetition)
        self.last_app = None           # which app was active during last comment
        self.last_comment_time = 0.0   # when last commented (for ambient)
        self.tick()

    # --- Move window ---
    def _start_move(self, e):
        self._dx, self._dy = e.x, e.y

    def _on_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    # --- Event-driven cycle ---
    def tick(self):
        self.root.after(POLL_SEC * 1000, self.tick)   # check repeatedly
        if self._busy:
            return
        reason, app = self._trigger()
        if reason:
            self._busy = True
            self.status.config(text="thinking ...")
            threading.Thread(target=self._generate, args=(reason, app),
                             daemon=True).start()

    def _trigger(self):
        """Should Finja say something now? 'switch' = app changed (snappy),
        'ambient' = same app, but nothing said for a long time. Otherwise None."""
        try:
            conn = db.get_conn(check_same_thread=False)
            row = conn.execute("SELECT app FROM observations "
                               "ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
        except Exception:
            return None, None
        if not row:
            return None, None
        app = row[0]
        if app != self.last_app:
            return "switch", app
        if time.time() - self.last_comment_time >= AMBIENT_SEC:
            return "ambient", app
        return None, None

    def _generate(self, reason, app):
        txt = None
        try:
            conn = db.get_conn(check_same_thread=False)
            # Context = only the last seconds -> Finja comments on what is happening
            # RIGHT NOW, not what happened 50s ago (no more lag feeling).
            ctx = quatsch.build_context(conn, seconds=RECENT_SEC)
            conn.close()

            if not ctx or len(ctx.strip()) < 8:
                self.root.after(0, lambda: self.status.config(text="watching ..."))
                self._busy = False
                self.last_app = app
                return

            question = ""
            if reason == "switch":
                question = (f"(Dad just switched to '{app}' — react BRIEFLY "
                            f"to what he is doing/opening right now.)")
            log("CONTEXT", f"[{reason}] {len(ctx)} chars -> ...{ctx[-130:].strip()}")
            txt = quatsch.ask(ctx, question, avoid=self.last_comment)
            self.last_comment = txt
            self.last_app = app
            self.last_comment_time = time.time()
        except Exception as e:
            txt = f"(Error: {e})"
        log("FINJA", txt)
        self.root.after(0, lambda: self._show(txt))

    def _show(self, txt):
        self.body.config(text=txt)
        self.status.config(text="")
        self._busy = False


if __name__ == "__main__":
    print("Finja bubble started — bottom right of the screen.")
    print("  (move: drag | close: ESC or right-click)")
    print("  Tip: run 'live.py' in parallel so she has fresh data.")
    root = tk.Tk()
    root.title("Finja")
    Bubble(root)
    root.mainloop()
