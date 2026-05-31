"""
YourAI App Push Helpers
======================
Manages registration and persistent storage of Firebase Cloud Messaging (FCM) 
device tokens mapped to canonical internal user accounts.

Main Responsibilities:
- Load FCM token mappings from storage.
- Register/update an FCM token mapping for a user and write to disk.

Side Effects:
- Reads/writes to docker_data/fcm_tokens.json.
- Logs file system errors to the debug console using YourAIUnexpectedError.
"""

import json
import os
import sys

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FCM_TOKENS_FILE = os.path.join(_ROOT_DIR, "docker_data", "fcm_tokens.json")


def _load_tokens() -> dict:
    """
    Loads Firebase Cloud Messaging (FCM) tokens from the storage file on disk.

    Returns:
        dict: A dictionary mapping user IDs to their registered FCM tokens.
    """
    if not os.path.exists(FCM_TOKENS_FILE):
        return {}
    try:
        with open(FCM_TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_push_load")
        log_exception("APP_PUSH", err)
        return {}


def register_fcm_token(user_id: str, token: str) -> dict:
    """
    Registers or updates a Firebase Cloud Messaging (FCM) token for a specific user ID.

    Args:
        user_id (str): The canonical user ID.
        token (str): The FCM registration token.

    Raises:
        HTTPException: 500 if saving the updated token mapping fails.

    Returns:
        dict: A dictionary showing success status.
    """
    tokens = _load_tokens()
    tokens[user_id] = token
    try:
        os.makedirs(os.path.dirname(FCM_TOKENS_FILE), exist_ok=True)
        with open(FCM_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_push_save", user_id=user_id)
        log_exception("APP_PUSH", err)
        raise HTTPException(status_code=500, detail="Error saving token")

    log("APP_PUSH", f"FCM token registered for {user_id}", Fore.CYAN)
    return {"ok": True}
