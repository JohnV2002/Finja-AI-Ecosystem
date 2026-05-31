"""
YourAI App Linking Helpers
=========================
Handles pairing mobile devices to existing user accounts via one-time codes,
sharing the same underlying pairing system as the Discord link flow.

Main Responsibilities:
- Generate one-time pairing codes associated with specific user keys.
- Claim pairing codes, map mobile device IDs to user accounts, and write new API keys to disk.

Side Effects:
- Modifies access_keys.json via auth utilities.
- Logs unexpected pairing errors to the debug console using YourAIUnexpectedError.
"""

import os
import secrets
import sys

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError
from app.auth import load_access_keys, save_access_keys
from app.identity import resolve_profile
from helpers.platform_links import generate_link_code, consume_link_code, link_mobile_id


def generate_app_link(user_key: str) -> dict:
    """
    Generates a one-time mobile device linking code associated with a user key.

    Args:
        user_key (str): The user key to associate with the linking code.

    Returns:
        dict: A dictionary containing the generated code, user key, expiration, and hints.
    """
    code = generate_link_code(user_key, ttl_seconds=600)
    return {
        "code": code,
        "user_key": user_key,
        "expires_in": 600,
        "hint": f"Enter this code in the app: {code}",
    }


def claim_app_link(code: str, device_id: str) -> dict:
    """
    Claims a one-time linking code, maps the device ID to the user key, 
    and generates a dedicated API access key for the mobile device.

    Args:
        code (str): The one-time linking code (e.g. "YOURAI-XXXXXX").
        device_id (str): The unique identifier of the mobile device.

    Raises:
        HTTPException: 404 if the code is invalid or expired, 
                       500 if the new access key cannot be saved.

    Returns:
        dict: A status dictionary containing the success flag, the new access key, 
              the user key, and the user's display name.
    """
    user_key = consume_link_code(code)
    if not user_key:
        raise HTTPException(status_code=404, detail="Code invalid or expired")

    link_mobile_id(user_key, device_id)

    app_access_key = f"app-{secrets.token_urlsafe(48)}"
    keys = load_access_keys()
    keys[app_access_key] = {
        "role": "chat",
        "user_key": user_key,
        "can_altpersona": False,
        "description": f"Mobile App ({device_id[:8]}...)",
    }
    try:
        save_access_keys(keys)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_link_claim", user_key=user_key)
        log_exception("APP_LINKING", err)
        raise HTTPException(status_code=500, detail="Could not save access key")

    display_name = user_key
    try:
        profile = resolve_profile(user_key)
        if profile:
            display_name = profile.display_name
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_link_display_name", user_key=user_key)
        log_exception("APP_LINKING", err)

    log("APP_LINKING", f"Mobile linked: {device_id[:12]}... -> {user_key}", Fore.GREEN)
    return {
        "ok": True,
        "access_key": app_access_key,
        "user_key": user_key,
        "display_name": display_name,
    }
