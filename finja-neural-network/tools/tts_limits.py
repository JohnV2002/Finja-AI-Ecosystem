"""
Premium TTS Rate Limiter
=========================
Tracks per-user ElevenLabs (Tier 3) usage with monthly reset.
Mirrors the image_limits.py pattern.

Usage:
    from tools.tts_limits import can_use_premium, record_usage, get_usage

    ok, remaining, limit = can_use_premium("Mom", "family")
    if ok:
        record_usage("Mom")
    else:
        # tell user they're out of free quota
"""

import json
import os
import threading
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAISystemError
from config import TTS_LIMITS_FILE, TTS_PREMIUM_LIMITS

_lock = threading.Lock()


def _current_month() -> str:
    """Return the current month key like '2026-05'."""
    return datetime.now().strftime("%Y-%m")


def _load() -> dict:
    """Load the TTS usage data from disk (empty dict on missing/corrupt file)."""
    try:
        if os.path.exists(TTS_LIMITS_FILE):
            with open(TTS_LIMITS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_exception("TTS-LIMIT", YourAISystemError("Failed to load tts_usage.json", cause=e))
    return {}


def _save(data: dict):
    """Persist the TTS usage data to disk (best-effort, logs on failure)."""
    try:
        os.makedirs(os.path.dirname(TTS_LIMITS_FILE), exist_ok=True)
        with open(TTS_LIMITS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_exception("TTS-LIMIT", YourAISystemError("Failed to save tts_usage.json", cause=e))


def _get_limit(user_id: str, role: str = "") -> int:
    """Get monthly premium TTS limit. -1 = unlimited."""
    data = _load()
    user_data = data.get(user_id, {})
    if "custom_limit" in user_data:
        return user_data["custom_limit"]
    return TTS_PREMIUM_LIMITS.get(role, TTS_PREMIUM_LIMITS.get("default", 3))


def get_usage(user_id: str, role: str = "") -> dict:
    """
    Returns: { used, limit, remaining, month, unlimited }
    """
    month = _current_month()
    limit = _get_limit(user_id, role)
    unlimited = limit == -1

    with _lock:
        data = _load()
        user_data = data.get(user_id, {})
        used = 0 if user_data.get("month") != month else user_data.get("used", 0)

    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used) if not unlimited else 999,
        "month": month,
        "unlimited": unlimited,
    }


def can_use_premium(user_id: str, role: str = "") -> tuple:
    """Returns (allowed: bool, remaining: int, limit: int)"""
    info = get_usage(user_id, role)
    if info["unlimited"]:
        return True, 999, -1
    allowed = info["used"] < info["limit"]
    return allowed, info["remaining"], info["limit"]


def record_usage(user_id: str):
    """Record one ElevenLabs (Tier 3) premium TTS generation."""
    month = _current_month()
    with _lock:
        data = _load()
        if user_id not in data:
            data[user_id] = {}
        user_data = data[user_id]
        if user_data.get("month") != month:
            user_data["month"] = month
            user_data["used"] = 0
        user_data["used"] = user_data.get("used", 0) + 1
        data[user_id] = user_data
        _save(data)
    log("TTS-LIMIT", f"ElevenLabs TTS used: {user_id} → {user_data['used']} this month", Fore.CYAN)


# ─── Chatterbox (Tier 2) counter ─────────────────────────────────────────────

def record_yourai_usage(user_id: str):
    """Record one Chatterbox (Tier 2) TTS generation. No limit — just tracking."""
    month = _current_month()
    with _lock:
        data = _load()
        if user_id not in data:
            data[user_id] = {}
        yourai = data[user_id].get("yourai", {})
        if yourai.get("month") != month:
            yourai = {"month": month, "used": 0}
        yourai["used"] = yourai.get("used", 0) + 1
        data[user_id]["yourai"] = yourai
        _save(data)
    log("TTS-LIMIT", f"Chatterbox TTS used: {user_id} → {yourai['used']} this month", Fore.CYAN)


def get_yourai_usage(user_id: str) -> dict:
    """Returns Chatterbox TTS usage: { used, month }"""
    month = _current_month()
    with _lock:
        data = _load()
        yourai = data.get(user_id, {}).get("yourai", {})
        used = 0 if yourai.get("month") != month else yourai.get("used", 0)
    return {"used": used, "month": month}
