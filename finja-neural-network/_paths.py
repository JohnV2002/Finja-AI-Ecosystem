"""
YourAI AI - Path Setup
======================
Adds all subdirectories to the Python path so existing imports
(e.g. `from config import X`) keep working.

Must be imported FIRST in every entry point:
    import _paths  # noqa: F401
"""

import sys
import os

_BASE = os.path.dirname(os.path.abspath(__file__))

_SUBDIRS = ["core", "helpers", "body", "memory", "clients", "tools"]

for subdir in _SUBDIRS:
    path = os.path.join(_BASE, subdir)
    if path not in sys.path:
        sys.path.insert(0, path)

# Also ensure the root is present (for cross-imports between subdirs)
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
