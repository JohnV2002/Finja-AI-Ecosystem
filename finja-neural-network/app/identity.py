"""
YourAI App Identity Helpers
==========================
Utility helpers for mapping input platforms (Web, App, Discord, or device keys)
and access keys to canonical internal account IDs (user_id).

Main Responsibilities:
- Resolve a user access key/session profile tolerant to casing issues.
- Return the resolved canonical account ID (user_id).

Side Effects:
- Logs session resolution failures to debug console using YourAISessionError.
"""

import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from session import session_manager as _sm
from display import log_exception
from exceptions import YourAISessionError


def resolve_profile(user_key: str) -> Optional[Any]:
    """
    Finds the session profile corresponding to a user key, tolerant of case mismatches.

    Args:
        user_key (str): The user key to resolve.

    Returns:
        Optional[Any]: The user session profile object, or None if not found or on error.
    """
    if not user_key:
        return None
    try:
        profile = _sm.users.get(user_key)
        if profile:
            return profile

        lowered = user_key.lower()
        for key, candidate in _sm.users.items():
            if key.lower() == lowered:
                return candidate
    except Exception as e:
        err = YourAISessionError(
            "Could not resolve app session profile",
            user_key=user_key,
            cause=e,
            module="app_identity",
        )
        log_exception("APP_IDENTITY", err)
    return None


def resolve_user_id(key_info: dict) -> str:
    """
    Extracts the canonical user ID from access key metadata, falling back to the user key itself.

    Args:
        key_info (dict): The dictionary containing validated access key details.

    Returns:
        str: The canonical user ID (e.g. "admin").
    """
    user_key = str((key_info or {}).get("user_key") or "")
    profile = resolve_profile(user_key)
    if profile:
        return profile.user_id
    return user_key
