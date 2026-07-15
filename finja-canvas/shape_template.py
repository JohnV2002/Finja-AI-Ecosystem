"""
======================================================================
         Finja Canvas – Shape Template Generator
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / shape_template
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
  Generates shape templates for the AI painter, supporting both 
  geometric primitives and ASCII-style rasterized motifs. Handles 
  placement collision detection and canvas full state.
======================================================================
"""

import csv
import json
import os
import random
import re
import sys

from PIL import Image, ImageDraw

from ai_client import ask_ai, API_KEY
from config import LOGICAL_SIZE, cell_to_pixels

sys.stdout.reconfigure(encoding='utf-8')

TEMPLATE_FILE = "shape_template.json"
PLACEMENT_ATTEMPTS = 200
MAX_ACCEPTABLE_OVERLAP = 0.5  # from here on it's "no space found"
MAX_SHAPES = 30

# The AI does NOT draw in the full 64x64 coordinate space, but in a smaller,
# randomly chosen area per motif - this creates the r/place collage effect
# (multiple motifs next to each other) instead of a single motif filling almost
# the entire canvas. No subsequent scaling needed, so no quality loss - the AI
# is given a more compact space to design in right from the start.
MOTIF_SIZE_MIN = 16
MOTIF_SIZE_MAX = 28

# Two alternating drawing styles: "primitives" (clean geometric shapes with color,
# usually more smooth/blocky) and "ascii" (raster drawing character by character,
# but more organic/irregular - creates more stylistic variety on the canvas.
STYLES = ["primitives", "ascii"]

MAX_CONSECUTIVE_DUPLICATE_LINES = 10  # ASCII: from here it's considered a repetition collapse
MAX_FILL_RATIO = 0.6  # ASCII: more than 60% "X" is no longer a plausible silhouette


class CanvasFullError(Exception):
    """No free space left for a new motif - Canvas is (almost) completely occupied."""
    pass


def occupied_pixels():
    """All already painted pixels from color.csv, as {(x, y), ...}."""
    occupied = set()
    if os.path.exists("color.csv"):
        with open("color.csv", "r", newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 2:
                    occupied.add((int(row[0]), int(row[1])))
    return occupied


def find_free_placement(cells, occupied, attempts=PLACEMENT_ATTEMPTS):
    """Moves the cells (with their color) as a rigid block to a random
    position until one is found that overlaps as little as possible with already
    painted art. cells are [x, y, color] triples. Returns (shifted_cells, overlap_ratio)."""
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    min_x, min_y = min(xs), min(ys)
    w, h = max(xs) - min_x + 1, max(ys) - min_y + 1

    if w > LOGICAL_SIZE or h > LOGICAL_SIZE:
        return cells, 1.0

    best_cells, best_ratio = None, None
    for _ in range(attempts):
        ox = random.randint(0, LOGICAL_SIZE - w)
        oy = random.randint(0, LOGICAL_SIZE - h)
        shifted = [[x - min_x + ox, y - min_y + oy, color] for x, y, color in cells]

        real_pixels = [p for cx, cy, _ in shifted for p in cell_to_pixels(cx, cy)]
        overlap = sum(1 for p in real_pixels if p in occupied)
        ratio = overlap / len(real_pixels) if real_pixels else 1.0

        if ratio == 0:
            return shifted, 0.0
        if best_ratio is None or ratio < best_ratio:
            best_ratio, best_cells = ratio, shifted

    return best_cells, best_ratio


# ---------- Style A: geometric primitives (clean, but "perfect"/blocky) ----------

def build_primitives_prompt(kategorie, was, motif_size):
    return (
        f"Describe '{was}' ({kategorie}) on a compact {motif_size}x{motif_size} pixel grid "
        "as a combination of simple geometric shapes with color. Reply ONLY with JSON in this "
        "format, no other text:\n"
        '{"shapes": [\n'
        '  {"type":"circle","cx":12,"cy":12,"r":8,"color":"#RRGGBB"},\n'
        '  {"type":"rect","x":4,"y":15,"w":10,"h":6,"color":"#RRGGBB"},\n'
        '  {"type":"polygon","points":[[x1,y1],[x2,y2],[x3,y3]],"color":"#RRGGBB"},\n'
        '  {"type":"line","points":[[x1,y1],[x2,y2]],"width":2,"color":"#RRGGBB"}\n'
        "]}\n"
        f"Use 3 to {MAX_SHAPES} shapes, coordinates 0-{motif_size-1} (the motif should fill the entire "
        f"{motif_size}x{motif_size} grid well), allowed types: circle, rect, polygon, line."
    )


def parse_primitives(content):
    """Extracts the 'shapes' list from the JSON response, robust against Markdown fences."""
    content = re.sub(r"```\w*", "", content)
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    shapes = data.get("shapes") if isinstance(data, dict) else None
    return shapes if isinstance(shapes, list) else []


def _valid_color(c):
    return isinstance(c, str) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", c or ""))


def rasterize_primitives(shapes, motif_size):
    """Renders the shapes onto a motif_size grid (black background) and returns
    all visible pixels as [x, y, color] triples."""
    img = Image.new("RGB", (motif_size, motif_size), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    for s in shapes[:MAX_SHAPES]:
        if not isinstance(s, dict):
            continue
        color = s.get("color")
        color = color if _valid_color(color) else "#FFFFFF"
        t = s.get("type")
        try:
            if t == "circle":
                cx, cy, r = float(s["cx"]), float(s["cy"]), float(s["r"])
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
            elif t == "rect":
                x, y, w, h = float(s["x"]), float(s["y"]), float(s["w"]), float(s["h"])
                draw.rectangle([x, y, x + w, y + h], fill=color)
            elif t == "polygon":
                pts = [(float(px), float(py)) for px, py in s["points"]]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=color)
            elif t == "line":
                pts = [(float(px), float(py)) for px, py in s["points"]]
                width = max(1, int(s.get("width", 1)))
                if len(pts) >= 2:
                    draw.line(pts, fill=color, width=width)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue

    px = img.load()
    cells = []
    for y in range(motif_size):
        for x in range(motif_size):
            if px[x, y] != (0, 0, 0):
                r, g, b = px[x, y]
                cells.append([x, y, f"#{r:02X}{g:02X}{b:02X}"])
    return cells


# ---------- Style B: ASCII grid (more organic/irregular) ----------

def build_ascii_prompt(kategorie, was, motif_size):
    return (
        f"Draw the silhouette of '{was}' ({kategorie}) as ASCII art on a compact "
        f"{motif_size}x{motif_size} grid. ONLY use the characters '.' (empty/background) and 'X' "
        f"(part of the shape). Reply ONLY with exactly {motif_size} lines of {motif_size} characters, otherwise "
        "absolutely nothing - no markdown, no explanation, no code block markers."
    )


def parse_ascii_grid(content, motif_size):
    """Robust against Markdown fences and explanation text around it - only keeps lines
    that really look like a grid line (mostly '.'/'X'). Small free models sometimes
    slip into a repetition loop (the same X-line x-times in a row) - this is detected
    and the template is cut off there. Empty (background) lines can repeat arbitrarily often,
    this is normal (e.g. sky above a motif), only X-line repetition is a collapse."""
    content = re.sub(r"```\w*", "", content)
    grid_lines = []
    prev_line, repeat_count = None, 0
    for raw in content.strip().splitlines():
        ln = raw.strip()
        if not ln:
            continue
        shape_chars = sum(1 for c in ln if c in ".Xx")
        if shape_chars / len(ln) < 0.8:
            continue
        ln = ln.upper()

        if "X" in ln:
            if ln == prev_line:
                repeat_count += 1
                if repeat_count >= MAX_CONSECUTIVE_DUPLICATE_LINES:
                    break
            else:
                prev_line, repeat_count = ln, 1
        else:
            prev_line, repeat_count = None, 0

        grid_lines.append(ln)

    cells = []
    for cy, line in enumerate(grid_lines[:motif_size]):
        for cx, ch in enumerate(line[:motif_size]):
            if ch == "X":
                cells.append([cx, cy])

    fill_ratio = len(cells) / (motif_size * motif_size)
    if fill_ratio > MAX_FILL_RATIO:
        return []  # too full to be a plausible silhouette -> treat as failed

    return cells


def rasterize_ascii(bool_cells, farben):
    """Assigns each 'X' cell a random color from the palette - exactly the
    speckled, organic look that earlier ASCII motifs (e.g. the moon) had."""
    palette = farben or ["#FFFFFF"]
    return [[x, y, random.choice(palette)] for x, y in bool_cells]


# ---------- Common flow ----------

def build_shape_template(plan):
    kategorie = plan.get("kategorie", "?")
    was = plan.get("was", "?")
    farben = plan.get("farben") or []
    motif_size = random.randint(MOTIF_SIZE_MIN, MOTIF_SIZE_MAX)
    style = random.choice(STYLES)

    if style == "primitives":
        content, model = ask_ai(
            build_primitives_prompt(kategorie, was, motif_size), max_tokens=2200, wall_clock_timeout=40
        )
        if content is None:
            print("⚠️ All models are currently unavailable, no template created.")
            return None
        shapes = parse_primitives(content)
        if not shapes:
            print(f"⚠️ Could not read shapes from the response: {content[:150]!r}")
            return None
        raw_cells = rasterize_primitives(shapes, motif_size)
        if not raw_cells:
            print("⚠️ Shapes did not result in any visible pixels.")
            return None
    else:
        content, model = ask_ai(
            build_ascii_prompt(kategorie, was, motif_size), max_tokens=1500, wall_clock_timeout=35
        )
        if content is None:
            print("⚠️ All models are currently unavailable, no template created.")
            return None
        bool_cells = parse_ascii_grid(content, motif_size)
        if not bool_cells:
            print(f"⚠️ Could not read shape from the response: {content[:150]!r}")
            return None
        raw_cells = rasterize_ascii(bool_cells, farben)

    occupied = occupied_pixels()
    if occupied:
        cells, overlap_ratio = find_free_placement(raw_cells, occupied)
        if overlap_ratio > MAX_ACCEPTABLE_OVERLAP:
            raise CanvasFullError(
                f"No free space found for a new motif "
                f"(best position overlaps by {overlap_ratio:.0%} with existing art)."
            )
        if overlap_ratio > 0:
            print(f"⚠️ New motif overlaps {overlap_ratio:.0%} with existing art, placing at best position anyway.")
    else:
        cells = raw_cells  # virgin canvas, no shift needed

    data = {"logical_size": LOGICAL_SIZE, "cells": cells}
    with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

    print(f"🎨 {model} drew '{was}' in {style} style with {len(cells)} pixels -> {TEMPLATE_FILE}")
    return data


def load_or_build_template(plan):
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("No shape_template.json found, letting the AI create one...")
    return build_shape_template(plan)


def template_pixel_pool(template, available_pixels):
    """All still free real pixels within the shape, with their color already
    determined during shape design - no more AI call needed to choose a color."""
    available_set = {(row[0], row[1]) for row in available_pixels}
    pool = []
    for cx, cy, color in template["cells"]:
        for x, y in cell_to_pixels(cx, cy):
            coord = (str(x), str(y))
            if coord in available_set:
                pool.append((coord[0], coord[1], color))
    return pool


if __name__ == "__main__":
    if not API_KEY:
        print("⚠️ No OPENROUTER_API_KEY found in .env! Please enter it and restart.")
        raise SystemExit(1)

    with open("what_to_draw.json", "r", encoding="utf-8") as f:
        plan = json.load(f)

    build_shape_template(plan)
