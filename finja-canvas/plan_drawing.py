"""
======================================================================
         Finja Canvas – Motif Planner
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / plan_drawing
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
  Asks the AI to choose a new motif and color palette.
======================================================================
"""

import json
import random
import re
import sys

from ai_client import ask_ai, API_KEY
from config import GRID_SIZE, TOTAL_PIXELS

sys.stdout.reconfigure(encoding='utf-8')

# Categories chosen on 2026-07-14 via benchmark (no "Animal" - never looked good).
CATEGORIES = [
    "Food", "Plant", "Nature", "Building", "Vehicle",
    "Furniture", "Weather", "Tool", "Clothing", "Drink",
]


def build_prompt(kategorie):
    return (
        f"You have a {GRID_SIZE}x{GRID_SIZE} pixel canvas with {TOTAL_PIXELS} pixels, which is being "
        f"painted by an AI. The category is already set: {kategorie}. Choose a specific motif from "
        "this category, as well as a matching color palette (3 to 8 hex color codes).\n"
        "Respond ONLY with a JSON object in exactly this format, without any other text around it:\n"
        '{"was": "Apple", "farben": ["#F5F5F5", "#FF6B6B", "#2E8B57"]}'
    )


def plan_drawing():
    # Category is randomly chosen by code, not left to the AI - in practice the AI
    # almost always chose "Nature", no matter how the list looked in the prompt.
    kategorie = random.choice(CATEGORIES)

    content, model = ask_ai(build_prompt(kategorie))
    if content is None:
        print("⚠️ All models are currently unavailable, no plan created.")
        return None

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        print(f"⚠️ No JSON response detected: {content!r}")
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON broken ({e}): {content!r}")
        return None

    data["kategorie"] = kategorie

    with open("what_to_draw.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"🎲 Category (randomly rolled): {kategorie}")
    print(f"🎨 {model} decided: {data.get('was')}")
    print(f"   Colors: {data.get('farben')}")
    return data


if __name__ == "__main__":
    if not API_KEY:
        print("⚠️ No OPENROUTER_API_KEY found in .env! Please enter it and restart.")
        raise SystemExit(1)

    plan_drawing()
