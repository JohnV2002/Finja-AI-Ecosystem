"""
======================================================================
         Finja Canvas – Painter Logic
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / painter
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.2.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Main painting loop that places pixels according to the generated plan
  and template.

 Changes (1.2.0):
  An unexpected failure is reported as FINJA-515 (log + Analytics Collector)
  before the painter stops as before; a missing key is FINJA-104.

 Changes (1.1.0):
  Now paints pixel templates generated from Recraft Vector SVG motifs.
======================================================================
"""

import csv
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from ai_client import API_KEY
from plan_drawing import plan_drawing
from render import render_full_canvas, render_motif_snapshot
from shape_template import CanvasFullError, load_or_build_template, template_pixel_pool
from analytics_sender import AnalyticsConfig, AnalyticsSender
from core.exceptions import AnalyticsDeliveryError, CanvasNotConfiguredError, CanvasPainterError

LOGGER = logging.getLogger("finja_canvas")
PROJECT_ROOT = Path(__file__).resolve().parent


def _report_analytics_problem(problem):
    error = AnalyticsDeliveryError(str(problem.get("message") or "analytics delivery failed"),
                                   reason=problem.get("reason"), retry=problem.get("retry"))
    LOGGER.warning("%s %s context=%s", error.code, error, error.context)


_analytics_config, _analytics_problem = AnalyticsConfig.from_environment(PROJECT_ROOT, version="1.2.0")
analytics = AnalyticsSender(_analytics_config, root=PROJECT_ROOT, on_failure=_report_analytics_problem)

sys.stdout.reconfigure(encoding='utf-8')


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_name(text):
    return re.sub(r"[^\w]+", "_", text).strip("_")[:40] or "motif"


# Real operating interval (no longer the 3s from testing) - adjustable via ENV, 
# e.g. in the Docker setup, without touching the code.
INTERVAL_SECONDS = int(os.getenv("PAINT_INTERVAL_SECONDS", "20"))
PLAN_FILE = "what_to_draw.json"


def load_plan():
    """Loads what_to_draw.json, or lets the AI create a new plan once."""
    if os.path.exists(PLAN_FILE):
        with open(PLAN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("No what_to_draw.json found, letting the AI create a plan...")
    return plan_drawing()


def paint_one_pixel(plan, template):
    """Paints exactly one free pixel within the shape - with the color that was already
    determined during the shape design (no more AI call per pixel).
    Return: True (painted), False (this motif is finished, canvas still has space
    for a next one), None (canvas completely full, nowhere space left)."""
    with open('canvas.csv', 'r') as f:
        reader = list(csv.reader(f))

    header = reader[0]
    available_pixels = reader[1:]

    if not available_pixels:
        print("No more pixels left! The artwork is finished! :3")
        path = render_full_canvas(f"{_timestamp()}_FULL.png")
        print(f"📸 Final canvas saved: {path}")
        return None

    pool = template_pixel_pool(template, available_pixels)
    if not pool:
        print("🎨 Shape is completely colored! The artwork is finished! :3")
        cells_xy = [[c[0], c[1]] for c in template["cells"]]
        name = _safe_name(plan.get("was", "motif"))
        path = render_motif_snapshot(cells_xy, f"{_timestamp()}_{name}.png")
        print(f"📸 Motif snapshot saved: {path}")
        return False

    x, y, color = random.choice(pool)
    chosen_pixel = [x, y]

    with open('color.csv', 'a', newline='') as f:
        csv.writer(f).writerow([x, y, color])

    available_pixels.remove(chosen_pixel)
    with open('canvas.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(available_pixels)

    print(f"🖌️ Painted pixel {x},{y} in {color}! :3")
    return True


def report_failure(error):
    """One structured line in the log and, when analytics is on, one error.occurrence event."""
    LOGGER.error("%s %s context=%s", error.code, error, error.context)
    if analytics.record_exception(error) is not None:
        analytics.flush_once()  # the painter is a short-lived process: send now, not later


def run():
    if not API_KEY:
        raise CanvasNotConfiguredError("Finja Canvas is not configured: OPENROUTER_API_KEY is missing",
                                       setting="OPENROUTER_API_KEY")

    plan = load_plan()
    if plan is None:
        print("⚠️ No plan available (all models down?), aborting.")
        raise SystemExit(1)

    try:
        template = load_or_build_template(plan)
    except CanvasFullError as e:
        print(f"🚫 {e}")
        path = render_full_canvas(f"{_timestamp()}_FULL.png")
        print(f"📸 Final canvas saved: {path}")
        raise SystemExit(2)  # Canvas completely full - Exit-Code 2 = "stop, do not try again"

    if template is None:
        print("⚠️ No template available, aborting.")
        raise SystemExit(1)

    print(
        f"Starting AI Pixel Painter Loop (every {INTERVAL_SECONDS}s) "
        f"- Motif: {plan.get('kategorie')} / {plan.get('was')} :3"
    )
    while True:
        result = paint_one_pixel(plan, template)
        if result is None:
            raise SystemExit(2)  # Canvas completely full
        if result is False:
            break  # Motif finished, but still space - Exit-Code 0, entrypoint starts next motif
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        run()
    except (SystemExit, KeyboardInterrupt):
        raise
    except CanvasNotConfiguredError as missing:  # logged with its code: "OPENROUTER_API_KEY is missing"
        report_failure(missing)
        raise SystemExit(1) from missing
    except Exception as exc:  # report a real failure with its code, then stop as before (entrypoint exits)
        report_failure(CanvasPainterError("A painting step failed unexpectedly", cause=exc))
        raise SystemExit(1) from exc
