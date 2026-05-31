"""
YourAI App - Shared Authentication & Maintenance Utilities
=========================================================
FastAPI-compatible authentication utilities and maintenance mode handling,
shared between the dashboard server and mobile API.

Main Responsibilities:
- Validate API/access keys and extract role/permission levels.
- Perform role-based access checks (admin, debug, chat).
- Load/save access keys on disk.
- Detect and enforce global maintenance mode.

Side Effects:
- Blocks requests with a HTTP 503 JSON response when maintenance mode is active (non-admins).
- Raises HTTP 401/403 errors if access validation fails.
"""

import json
import os
import sys
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

import config as _cfg
from display import log_exception
from exceptions import YourAIConfigError

_ROOT_DIR             = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ACCESS_KEYS_FILE     = os.path.join(_ROOT_DIR, "access_keys.json")
_RUNTIME_CONFIG_FILE  = os.path.join(_ROOT_DIR, "runtime_config.json")

_MAINTENANCE_JSON = {"maintenance": True, "message": "YourAI will be right back."}


# =========================================================================
# Key Loading
# =========================================================================

def load_access_keys() -> Dict[str, Any]:
    """
    Loads the access keys configuration dictionary from disk.

    Returns:
        Dict[str, Any]: The loaded access keys, mapping keys to user metadata.
    """
    if os.path.exists(_ACCESS_KEYS_FILE):
        try:
            with open(_ACCESS_KEYS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            err = YourAIConfigError(
                "Could not load access keys",
                key=_ACCESS_KEYS_FILE,
                cause=e,
                module="app_auth",
            )
            log_exception("APP_AUTH", err)
    return {}


def save_access_keys(keys: Dict[str, Any]) -> None:
    """
    Writes the access keys configuration dictionary atomically to disk.

    Args:
        keys (Dict[str, Any]): The access keys dictionary to serialize and save.
    """
    with open(_ACCESS_KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2, ensure_ascii=False)


def get_key_info(key: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Retrieves metadata for a specific access key.

    Args:
        key (Optional[str]): The access key string to look up.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing role, user_key, and can_altpersona permission, 
                                 or None if the key is invalid.
    """
    if not key:
        return None
    keys = load_access_keys()
    entry = keys.get(key)
    if not entry or "role" not in entry:
        return None
    return {
        "role":      entry["role"],
        "user_key":  entry.get("user_key", "admin"),
        "can_altpersona":  entry.get("can_altpersona", False),
    }


def get_role_for_key(key: Optional[str]) -> Optional[str]:
    """
    Retrieves the role associated with a specific access key.

    Args:
        key (Optional[str]): The access key string to look up.

    Returns:
        Optional[str]: The associated role string (e.g. "admin", "chat"), or None if invalid.
    """
    info = get_key_info(key)
    return info["role"] if info else None


def verify_access(key: Optional[str], required_role: str = "chat") -> str:
    """
    Raises HTTPException 401/403 if the access key is invalid or lacks the required role level.

    Args:
        key (Optional[str]): The access key to validate.
        required_role (str, optional): The minimum role required. Defaults to "chat".

    Raises:
        HTTPException: 401 if unauthorized, 403 if forbidden.

    Returns:
        str: The authorized user's role on success.
    """
    role = get_role_for_key(key)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Access Key (?key=...)"
        )
    # Hierarchy: admin > debug > chat
    if role == "admin":
        return role
    if required_role == "debug" and role == "debug":
        return role
    if required_role == "chat" and role in ("chat", "debug"):
        return role
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient permissions for role '{role}'"
    )


# =========================================================================
# Maintenance Mode
# =========================================================================

def is_maintenance_mode() -> bool:
    """
    Determines if the global maintenance mode is currently active.

    Checks runtime overrides from the configuration file first, falling back 
    to the defaults defined in the config.

    Returns:
        bool: True if maintenance mode is active, False otherwise.
    """
    try:
        if os.path.exists(_RUNTIME_CONFIG_FILE):
            with open(_RUNTIME_CONFIG_FILE, "r") as f:
                overrides = json.load(f)
            return bool(overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False)))
        return bool(getattr(_cfg, "USE_MAINTENANCE", False))
    except Exception as e:
        err = YourAIConfigError(
            "Could not read maintenance mode",
            key=_RUNTIME_CONFIG_FILE,
            cause=e,
            module="app_auth",
        )
        log_exception("APP_AUTH", err)
        return False


def maintenance_block(key_info: Optional[Dict[str, Any]]) -> Optional[JSONResponse]:
    """
    Generates an HTTP 503 service unavailable response if maintenance mode is active
    and the user lacks administrative privileges.

    Args:
        key_info (Optional[Dict[str, Any]]): The user metadata associated with the access key.

    Returns:
        Optional[JSONResponse]: A 503 JSONResponse blocking the request, or None if the request can proceed.
    """
    if is_maintenance_mode() and (not key_info or key_info.get("role") != "admin"):
        return JSONResponse(status_code=503, content=_MAINTENANCE_JSON)
    return None
