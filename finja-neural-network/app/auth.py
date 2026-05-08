"""
YourAI App — Shared Auth & Maintenance Utilities
=================================================
Used by both dashboard_server.py and app/app_api.py.
Single source of truth for key validation and maintenance mode.
"""

import json
import os
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

_ROOT_DIR             = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ACCESS_KEYS_FILE     = os.path.join(_ROOT_DIR, "access_keys.json")
_RUNTIME_CONFIG_FILE  = os.path.join(_ROOT_DIR, "runtime_config.json")

_MAINTENANCE_JSON = {"maintenance": True, "message": "YourAI ist gleich zurück 🦊"}


# ─── Key loading ─────────────────────────────────────────────────────────────

def load_access_keys() -> Dict[str, Any]:
    if os.path.exists(_ACCESS_KEYS_FILE):
        try:
            with open(_ACCESS_KEYS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_key_info(key: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns {'role': ..., 'user_key': ..., 'can_altpersona': ...} or None if invalid."""
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
    info = get_key_info(key)
    return info["role"] if info else None


def verify_access(key: Optional[str], required_role: str = "chat"):
    """Raises HTTPException 401/403 if key is invalid or lacks required role."""
    role = get_role_for_key(key)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder fehlender Access Key (?key=...)"
        )
    # Hierarchy: admin > debug > chat
    if role == "admin":
        return True
    if required_role == "debug" and role == "debug":
        return True
    if required_role == "chat" and role in ("chat", "debug"):
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Nicht genügend Berechtigungen für Rolle '{role}'"
    )


# ─── Maintenance mode ─────────────────────────────────────────────────────────

def is_maintenance_mode() -> bool:
    """Returns True if USE_MAINTENANCE is active (runtime override or config default)."""
    try:
        import config as _cfg
        if os.path.exists(_RUNTIME_CONFIG_FILE):
            with open(_RUNTIME_CONFIG_FILE, "r") as f:
                overrides = json.load(f)
            return bool(overrides.get("USE_MAINTENANCE", getattr(_cfg, "USE_MAINTENANCE", False)))
        return bool(getattr(_cfg, "USE_MAINTENANCE", False))
    except Exception:
        return False


def maintenance_block(key_info: Optional[Dict[str, Any]]) -> Optional[JSONResponse]:
    """
    Returns a 503 JSONResponse if maintenance is active and the user is not admin.
    Returns None if the request may proceed normally.

    Usage:
        block = maintenance_block(key_info)
        if block:
            return block
    """
    if is_maintenance_mode() and (not key_info or key_info.get("role") != "admin"):
        return JSONResponse(status_code=503, content=_MAINTENANCE_JSON)
    return None
