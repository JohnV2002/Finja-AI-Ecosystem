"""
======================================================================
         Finja Canvas – Rendering Utility
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / render
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
  Renders snapshots of the canvas or individual motifs as PNG images.
======================================================================
"""

import csv
import os

from PIL import Image

from config import GRID_SIZE

GALLERY_DIR = "gallery"
CELL_PX = 10  # same scaling as the canvas in index.html
BG_COLOR = (0, 0, 0)


def _read_colors():
    """Reads color.csv -> dict {(x,y): '#RRGGBB'}."""
    colors = {}
    if not os.path.exists("color.csv"):
        return colors
    with open("color.csv", "r", newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 3:
                colors[(int(row[0]), int(row[1]))] = row[2]
    return colors


def _save(img, filename):
    os.makedirs(GALLERY_DIR, exist_ok=True)
    path = os.path.join(GALLERY_DIR, filename)
    img.save(path)
    return path


def render_full_canvas(filename):
    """Renders the complete canvas (all pixels painted so far) as PNG."""
    colors = _read_colors()
    img = Image.new("RGB", (GRID_SIZE * CELL_PX, GRID_SIZE * CELL_PX), BG_COLOR)
    pixels = img.load()

    for (x, y), hexcolor in colors.items():
        rgb = tuple(int(hexcolor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        for dx in range(CELL_PX):
            for dy in range(CELL_PX):
                pixels[x * CELL_PX + dx, y * CELL_PX + dy] = rgb

    return _save(img, filename)


def render_motif_snapshot(cells, filename, margin=1):
    """Renders only the section (bounding box + margin) around the logical
    cells of a single motif, with the actually painted colors."""
    colors = _read_colors()
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    x0, x1 = max(0, min(xs) - margin), min(GRID_SIZE - 1, max(xs) + margin)
    y0, y1 = max(0, min(ys) - margin), min(GRID_SIZE - 1, max(ys) + margin)
    w, h = x1 - x0 + 1, y1 - y0 + 1

    img = Image.new("RGB", (w * CELL_PX, h * CELL_PX), BG_COLOR)
    pixels = img.load()

    for (x, y), hexcolor in colors.items():
        if x0 <= x <= x1 and y0 <= y <= y1:
            rgb = tuple(int(hexcolor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            for dx in range(CELL_PX):
                for dy in range(CELL_PX):
                    pixels[(x - x0) * CELL_PX + dx, (y - y0) * CELL_PX + dy] = rgb

    return _save(img, filename)
