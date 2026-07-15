"""
======================================================================
         Finja Canvas – Canvas Generator
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / gen_canv
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
  Generates the initial empty canvas coordinate CSV file.
======================================================================
"""

import csv
from config import GRID_SIZE

with open('canvas.csv', 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['X', 'Y']) # Header

    # Generate all coordinates from 0,0 to GRID_SIZE-1,GRID_SIZE-1
    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE):
            writer.writerow([x, y])
            
print(f"canvas.csv with {GRID_SIZE * GRID_SIZE} pixels was successfully created! :3")