"""
YourAI AI - Path Setup
======================
Fügt alle Unterordner zum Python-Path hinzu, damit bestehende
Imports (z.B. `from config import X`) weiterhin funktionieren.

Muss als ERSTES importiert werden in jedem Entry Point:
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

# Root auch sicherstellen (für cross-imports zwischen Subdirs)
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
