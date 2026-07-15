"""
======================================================================
         Finja Omni Test – Ground Truth Labeler
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / labeln
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
  GUI tool to quickly label test frames for OCR evaluation.
  Creates ground_truth.json (T = Text present, L = Empty).
======================================================================
"""

import os
import glob
import json
import tkinter as tk
from tkinter import font as tkfont

# Pillow for image display
try:
    from PIL import Image, ImageTk
except ImportError:
    raise SystemExit("Please install first:  pip install pillow")

INPUT_DIR     = "test_frames"
GROUND_TRUTH  = "ground_truth.json"   # saves here

image_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.png")))
if not image_files:
    raise SystemExit(f"No images in '{INPUT_DIR}'!")

# Load already labeled ones (so you can pause & continue)
if os.path.exists(GROUND_TRUTH):
    with open(GROUND_TRUTH, encoding="utf-8") as f:
        labels = json.load(f)
else:
    labels = {}

# Max width for display (frames are 1920 wide -> scale down)
MAX_W = 1280


class Labeler:
    def __init__(self, root):
        self.root = root
        self.root.title("Finja Frame Labeler  |  T=Text  L=Empty  <-=Back  Q=Quit")
        self.root.configure(bg="#1e1e1e")

        self.idx = self._first_unlabeled()

        self.info = tk.Label(root, bg="#1e1e1e", fg="#dcdcdc",
                             font=tkfont.Font(size=14, weight="bold"))
        self.info.pack(pady=6)

        self.canvas = tk.Label(root, bg="#000000")
        self.canvas.pack()

        self.help = tk.Label(
            root, bg="#1e1e1e", fg="#888888",
            text="[T] = has Text    [L] = EMPTY (no text)    "
                 "[<-] back    [Q] save & quit",
            font=tkfont.Font(size=11))
        self.help.pack(pady=6)

        root.bind("t", lambda e: self.label("text"))
        root.bind("l", lambda e: self.label("leer"))
        root.bind("<Left>", lambda e: self.back())
        root.bind("q", lambda e: self.quit())
        root.bind("<Escape>", lambda e: self.quit())

        self.show()

    def _first_unlabeled(self):
        for i, path in enumerate(image_files):
            if os.path.basename(path) not in labels:
                return i
        return len(image_files)  # all done

    def show(self):
        if self.idx >= len(image_files):
            self.finish()
            return

        path = image_files[self.idx]
        name = os.path.basename(path)

        img = Image.open(path)
        if img.width > MAX_W:
            ratio = MAX_W / img.width
            img = img.resize((MAX_W, int(img.height * ratio)))
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.config(image=self.photo)

        done = len(labels)
        prev = labels.get(name)
        prev_txt = f"  (current: {prev})" if prev else ""
        self.info.config(
            text=f"Image {self.idx + 1}/{len(image_files)}   |   "
                 f"labeled: {done}   |   {name}{prev_txt}")

    def label(self, value):
        name = os.path.basename(image_files[self.idx])
        labels[name] = value
        self.save()
        self.idx += 1
        self.show()

    def back(self):
        if self.idx > 0:
            self.idx -= 1
            self.show()

    def save(self):
        with open(GROUND_TRUTH, "w", encoding="utf-8") as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)

    def finish(self):
        n_text = sum(1 for v in labels.values() if v == "text")
        n_leer = sum(1 for v in labels.values() if v == "leer")
        self.canvas.config(image="")
        self.info.config(
            text=f"DONE!  Text: {n_text}   Empty: {n_leer}   "
                 f"Total: {len(labels)}")
        self.help.config(text="Saved to ground_truth.json  –  [Q] to close")

    def quit(self):
        self.save()
        n_text = sum(1 for v in labels.values() if v == "text")
        n_leer = sum(1 for v in labels.values() if v == "leer")
        print(f"Saved: {len(labels)} labeled  (Text: {n_text}, Empty: {n_leer})")
        print(f"-> {GROUND_TRUTH}")
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Labeler(root)
    root.mainloop()
