"""
Image Generation Rate Limiter
==============================
Tracks per-user image generation usage with monthly reset.
Persists to docker_data/image_usage.json.

Usage:
    from tools.image_limits import can_generate, record_usage, get_usage

    ok, remaining, limit = can_generate("admin")
    if ok:
        # ... generate image ...
        record_usage("admin")
    else:
        # tell user they're out of quota
"""

import json
import os
import threading
from datetime import datetime
from display import log, log_exception, Fore
from exceptions import YourAISystemError
from config import IMAGE_LIMITS_FILE, IMAGE_LIMITS_DEFAULT

_lock = threading.Lock()


def _current_month() -> str:
    """Returns current month key like '2026-04'."""
    return datetime.now().strftime("%Y-%m")


def _load() -> dict:
    """Load usage data from disk."""
    try:
        if os.path.exists(IMAGE_LIMITS_FILE):
            with open(IMAGE_LIMITS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        err = YourAISystemError("Fehler beim Laden von image_usage.json", cause=e)
        log_exception("IMG-LIMIT", err)
    return {}


def _save(data: dict):
    """Save usage data to disk."""
    try:
        with open(IMAGE_LIMITS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        err = YourAISystemError("Fehler beim Speichern von image_usage.json", cause=e)
        log_exception("IMG-LIMIT", err)


def _get_limit(user_id: str, role: str = "") -> int:
    """Get monthly image limit for a user. Returns -1 for unlimited."""
    data = _load()
    user_data = data.get(user_id, {})

    # Per-user override takes priority
    if "custom_limit" in user_data:
        return user_data["custom_limit"]

    # Role-based default
    return IMAGE_LIMITS_DEFAULT.get(role, IMAGE_LIMITS_DEFAULT.get("default", 10))


def get_usage(user_id: str, role: str = "") -> dict:
    """
    Get usage info for a user.
    Returns: { "used": int, "limit": int, "remaining": int, "month": str, "unlimited": bool }
    """
    month = _current_month()
    limit = _get_limit(user_id, role)
    unlimited = limit == -1

    with _lock:
        data = _load()
        user_data = data.get(user_id, {})

        # Auto-reset if month changed
        if user_data.get("month") != month:
            used = 0
        else:
            used = user_data.get("used", 0)

    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used) if not unlimited else 999,
        "month": month,
        "unlimited": unlimited,
    }


def can_generate(user_id: str, role: str = "") -> tuple:
    """
    Check if user can generate an image.
    Returns: (allowed: bool, remaining: int, limit: int)
    """
    info = get_usage(user_id, role)
    if info["unlimited"]:
        return True, 999, -1
    allowed = info["used"] < info["limit"]
    return allowed, info["remaining"], info["limit"]


def record_usage(user_id: str):
    """Record one image generation for a user."""
    month = _current_month()
    with _lock:
        data = _load()

        if user_id not in data:
            data[user_id] = {}

        user_data = data[user_id]

        # Reset if new month
        if user_data.get("month") != month:
            user_data["month"] = month
            user_data["used"] = 0

        user_data["used"] = user_data.get("used", 0) + 1
        data[user_id] = user_data
        _save(data)

    used = user_data["used"]
    log("IMG-LIMIT", f"Recorded usage for {user_id}: {used} this month", Fore.CYAN)


def set_custom_limit(user_id: str, limit: int):
    """Set a custom monthly limit for a user. Use -1 for unlimited."""
    with _lock:
        data = _load()
        if user_id not in data:
            data[user_id] = {"month": _current_month(), "used": 0}
        data[user_id]["custom_limit"] = limit
        _save(data)
    log("IMG-LIMIT", f"Custom limit for {user_id}: {limit}", Fore.CYAN)
