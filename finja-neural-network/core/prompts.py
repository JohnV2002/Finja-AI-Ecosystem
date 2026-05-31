"""
Legacy Prompt Module
====================
Inactive compatibility note for the previous flat prompt module.

Main Responsibilities:
- Document that Python now resolves prompt imports through the core/prompts package.
- Point maintainers to the split prompt modules used by the active brain pipeline.

Side Effects:
- None.
"""

# NOTE: This file is no longer active.
# Python prefers the prompts/ package (core/prompts/__init__.py) over this file.
# Prompts are now split into:
#   core/prompts/core.py      - Core prompts (Granite, Router, YourAI, Promise, Coherence)
#   core/prompts/sections.py  - Discord and tool sections
#   core/prompts/altpersona.py      - AltPersona prompts
#   core/prompts/experts.py   - Expert prompts, EXPERT_PROMPTS, and get_expert_prompt
#   core/prompts/__init__.py  - Re-exported names for unchanged brain.py imports
