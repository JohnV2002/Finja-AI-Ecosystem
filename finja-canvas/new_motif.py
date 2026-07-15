"""
======================================================================
         Finja Canvas – New Motif Trigger
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / new_motif
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
  Deletes the current AI plan to force a new motif on the next cycle,
  leaving the already painted canvas intact.
======================================================================
"""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Unlike reset_canvas.py: canvas.csv/color.csv are left untouched. Only the plan +
# template are deleted, so painter.py plans a NEW motif on the next start next to
# the previous one (see find_free_placement in shape_template.py).
FILES_TO_CLEAR = ["what_to_draw.json", "shape_template.json"]


def new_motif():
    removed = []
    for path in FILES_TO_CLEAR:
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)

    if removed:
        print(f"Deleted: {', '.join(removed)}")
        print("Canvas remains intact - painter.py will plan a new motif next time.")
    else:
        print("No old plan/template found - painter.py will plan anew on next start anyway.")


if __name__ == "__main__":
    new_motif()
