"""
======================================================================
         Finja Canvas – Reset Utility
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / reset_canvas
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
  Resets the canvas and colors to empty, and deletes AI planning files.
======================================================================
"""

import csv
import os
import sys

from config import GRID_SIZE

sys.stdout.reconfigure(encoding='utf-8')

# These files are bound to ONE artwork - during a reset they must be removed,
# otherwise painter.py stubbornly continues painting the old motif/template 
# on the next start (even still the same fox 2 years later :3).
FILES_TO_CLEAR = ["what_to_draw.json", "shape_template.json"]


def reset_canvas():
    with open('canvas.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['X', 'Y'])
        for x in range(GRID_SIZE):
            for y in range(GRID_SIZE):
                writer.writerow([x, y])

    open('color.csv', 'w').close()

    removed = []
    for path in FILES_TO_CLEAR:
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)

    print(f"Canvas reset ({GRID_SIZE}x{GRID_SIZE} pixels, empty).")
    if removed:
        print(f"Deleted: {', '.join(removed)} - next painter.py start will create a fresh plan + template.")
    print("Done :3")


if __name__ == "__main__":
    reset_canvas()
