"""
YourAI App Mood Helpers
======================
Utility function to retrieve and format YourAI's current emotional state and mood 
descriptor for mobile application rendering.

Main Responsibilities:
- Retrieve mood metadata (mood name, matching emoji, and description) for a specific user.
- Provide a safe fallback mood payload in case of errors.

Side Effects:
- Imports persona_manager dynamically from helpers.personas.
- Logs unexpected mood loading errors to the debug console using YourAIUnexpectedError.
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception
from exceptions import YourAIUnexpectedError
from helpers.personas import persona_manager

DEFAULT_MOOD_PAYLOAD = {
    "mood": "default",
    "emoji": "paw",
    "description": "Normal",
    "time": "",
    "time_of_day": "",
}


def get_mood_payload(user_id: Optional[str] = None) -> dict:
    """
    Returns YourAI's current mood payload for the mobile app UI.

    Args:
        user_id (Optional[str]): The canonical user ID used to retrieve persona-specific mood state.

    Returns:
        dict: The mood payload returned by the persona manager, or a safe fallback payload on error.
    """
    try:
        return persona_manager.get_mood_for_dashboard(user_id=user_id)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_mood")
        log_exception("APP_MOOD", err)
        return dict(DEFAULT_MOOD_PAYLOAD)
