"""
YourAI Platform Link Helpers
===========================
Links external platform identifiers to YourAI user keys.

Main Responsibilities:
- Store Discord-to-user mappings.
- Manage one-time platform link codes.
- Expose safety checks for DM permissions.

Side Effects:
- Reads and writes platform link JSON files.
"""
import json
import os
import secrets
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception
from exceptions import YourAIUnexpectedError

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR     = os.path.join(_BASE, "docker_data")
_LINKS_FILE   = os.path.join(_DATA_DIR, "platform_links.json")
_PENDING_FILE = os.path.join(_DATA_DIR, "pending_discord_links.json")

_lock = threading.Lock()


# ── Core CRUD ──────────────────────────────────────────────────────

def _load() -> dict:
    """Handle load helper behavior."""
    try:
        if os.path.exists(_LINKS_FILE):
            with open(_LINKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="platform_links_load")
        log_exception("PLATFORM", err)
    return {}


def _save(data: dict) -> None:
    """Handle save helper behavior."""
    with open(_LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Lookup ─────────────────────────────────────────────────────────

def resolve_discord_id(discord_id: str) -> str | None:
    """Return user_key when discord_id is linked, otherwise None."""
    with _lock:
        data = _load()
    for user_key, info in data.items():
        if discord_id in info.get("discord_ids", []):
            return user_key
    return None


def is_dm_allowed(discord_id: str) -> bool:
    """True wenn dieser Discord-User proaktive DMs von YourAI empfangen darf."""
    with _lock:
        data = _load()
    for info in data.values():
        if discord_id in info.get("discord_ids", []):
            return bool(info.get("dm_allowed", False))
    return False


# ── Mutate ─────────────────────────────────────────────────────────

def get_discord_ids(user_key: str) -> list[str]:
    """Return all Discord IDs linked to a dashboard user_key."""
    if not user_key:
        return []
    with _lock:
        data = _load()
    info = data.get(user_key) or {}
    return [str(discord_id) for discord_id in info.get("discord_ids", []) if discord_id]


def link_discord_id(user_key: str, discord_id: str, dm_allowed: bool = False) -> None:
    """Add discord_id to user_key idempotently."""
    with _lock:
        data = _load()
        entry = data.setdefault(user_key, {"discord_ids": [], "dm_allowed": False})
        if discord_id not in entry["discord_ids"]:
            entry["discord_ids"].append(discord_id)
        if dm_allowed:
            entry["dm_allowed"] = True
        _save(data)


def unlink_discord_id(discord_id: str) -> str | None:
    """Remove discord_id from all entries and return user_key or None."""
    with _lock:
        data = _load()
        for user_key, info in data.items():
            if discord_id in info.get("discord_ids", []):
                info["discord_ids"].remove(discord_id)
                _save(data)
                return user_key
    return None


def all_dm_allowed_ids() -> list[str]:
    """All Discord IDs with dm_allowed=true for send_dm safety checks."""
    with _lock:
        data = _load()
    result = []
    for info in data.values():
        if info.get("dm_allowed"):
            result.extend(info.get("discord_ids", []))
    return result


# ── Mobile Device Linking ──────────────────────────────────────────

def get_mobile_ids(user_key: str) -> list[str]:
    """Return all mobile device IDs linked to a user_key."""
    if not user_key:
        return []
    with _lock:
        data = _load()
    info = data.get(user_key) or {}
    return [str(did) for did in info.get("mobile_ids", []) if did]


def link_mobile_id(user_key: str, device_id: str) -> None:
    """Link a mobile device_id to a user_key (idempotent)."""
    with _lock:
        data = _load()
        entry = data.setdefault(user_key, {"discord_ids": [], "dm_allowed": False})
        mobile_ids = entry.setdefault("mobile_ids", [])
        if device_id not in mobile_ids:
            mobile_ids.append(device_id)
        _save(data)


def resolve_mobile_id(device_id: str) -> str | None:
    """Returns user_key if device_id is linked, else None."""
    with _lock:
        data = _load()
    for user_key, info in data.items():
        if device_id in info.get("mobile_ids", []):
            return user_key
    return None


def unlink_mobile_id(device_id: str) -> str | None:
    """Remove device_id from all entries. Returns user_key, or None."""
    with _lock:
        data = _load()
        for user_key, info in data.items():
            if device_id in info.get("mobile_ids", []):
                info["mobile_ids"].remove(device_id)
                _save(data)
                return user_key
    return None


def get_linked_platforms(user_key: str) -> dict:
    """Summary of all linked platforms for a user_key."""
    with _lock:
        data = _load()
    info = data.get(user_key) or {}
    return {
        "discord_ids": info.get("discord_ids", []),
        "mobile_ids": info.get("mobile_ids", []),
        "dm_allowed": info.get("dm_allowed", False),
    }


# One-time codes for /link.

def generate_link_code(user_key: str, ttl_seconds: int = 600) -> str:
    """
    Generate a one-time code such as YOURAI-A3BX9K for Discord linking.
    Expires after ttl_seconds; default is 10 minutes.
    """
    code = "YOURAI-" + secrets.token_urlsafe(6).upper()[:6]
    os.makedirs(os.path.dirname(_PENDING_FILE), exist_ok=True)
    with _lock:
        pending = _load_pending()
        # Remove old codes for the same user.
        pending = {k: v for k, v in pending.items() if v.get("user_key") != user_key}
        pending[code] = {
            "user_key": user_key,
            "expires": time.time() + ttl_seconds,
        }
        _save_pending(pending)
    return code


def consume_link_code(code: str) -> str | None:
    """
    Validiert und verbraucht einen Einmal-Code.
    Return user_key when valid, otherwise None.
    """
    code = code.upper().strip()
    with _lock:
        pending = _load_pending()
        entry = pending.get(code)
        if not entry:
            return None
        if time.time() > entry["expires"]:
            del pending[code]
            _save_pending(pending)
            return None
        user_key = entry["user_key"]
        del pending[code]
        _save_pending(pending)
    return user_key


def _load_pending() -> dict:
    """Handle load pending helper behavior."""
    try:
        if os.path.exists(_PENDING_FILE):
            with open(_PENDING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="platform_links_pending_load")
        log_exception("PLATFORM", err)
    return {}


def _save_pending(data: dict) -> None:
    """Handle save pending helper behavior."""
    with open(_PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
