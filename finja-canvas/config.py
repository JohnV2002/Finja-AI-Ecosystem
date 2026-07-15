"""
======================================================================
         Finja Canvas – Configuration
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / config
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
  Shared configuration for the canvas grid sizes and logical scaling.
======================================================================
"""

# True canvas resolution (must match gen_canv.py / index.html)
GRID_SIZE = 64
TOTAL_PIXELS = GRID_SIZE * GRID_SIZE

# Fixed "AI vision" resolution: the AI ALWAYS thinks in a LOGICAL_SIZE x LOGICAL_SIZE
# grid, regardless of the true GRID_SIZE. This keeps prompts (template ASCII art,
# cell lists) constant, even if the real canvas is scaled up to 128x128, 256x256 etc.
# Each logical cell simply covers a larger block of pixels.
LOGICAL_SIZE = 64
BLOCK_SIZE = max(1, GRID_SIZE // LOGICAL_SIZE)


def cell_to_pixels(cx, cy):
    """Maps a logical cell (cx, cy) to its BLOCK_SIZE x BLOCK_SIZE pixel block."""
    x0, y0 = cx * BLOCK_SIZE, cy * BLOCK_SIZE
    return [(x, y) for x in range(x0, x0 + BLOCK_SIZE) for y in range(y0, y0 + BLOCK_SIZE)]
