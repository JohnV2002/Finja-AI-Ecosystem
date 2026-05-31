"""
YourAI App Chat Log Helpers
==========================
Read-only utility functions to parse and retrieve mobile chat logs, message history,
and user interaction streak calculations from persistent JSONL log files.

Main Responsibilities:
- Read and stream user-specific entries from the application chat log (app_chat_log.jsonl).
- Format and package message history for mobile consumption.
- Calculate consecutive days streak and total activity statistics.

Side Effects:
- Reads directly from file on disk (docker_data/app_chat_log.jsonl).
- Logs parsing issues to debug console using YourAIMemoryError.
"""

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception
from exceptions import YourAIMemoryError

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_LOG_FILE = os.path.join(_ROOT_DIR, "docker_data", "app_chat_log.jsonl")


def iter_user_entries(user_id: str) -> list[dict]:
    """
    Reads the app chat log and retrieves parsed entries matching the user ID.

    Args:
        user_id (str): The canonical user ID to filter entries by.

    Returns:
        list[dict]: A list of log entry dictionaries.
    """
    entries: list[dict] = []
    if not os.path.exists(CHAT_LOG_FILE):
        return entries

    try:
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    err = YourAIMemoryError(
                        "Could not parse app chat log line",
                        user_id=user_id,
                        cause=e,
                        module="app_chat_log",
                    )
                    log_exception("APP_CHAT_LOG", err)
                    continue
                if entry.get("user_id") == user_id:
                    entries.append(entry)
    except Exception as e:
        err = YourAIMemoryError("Could not read app chat log", user_id=user_id, cause=e, module="app_chat_log")
        log_exception("APP_CHAT_LOG", err)
    return entries


def get_chat_history_payload(user_id: str, limit: int = 50) -> dict:
    """
    Builds the chat history payload containing the most recent message pairs.

    Args:
        user_id (str): The canonical user ID.
        limit (int, optional): The maximum number of message pairs to return. Defaults to 50.

    Returns:
        dict: The chat history payload mapping messages to list of role/text pairs.
    """
    entries = iter_user_entries(user_id)[-limit:]
    messages = []
    for entry in entries:
        messages.append(
            {
                "role": "user",
                "text": entry["user_msg"],
                "ts": entry["ts"],
                "tracking_id": "",
            }
        )
        messages.append(
            {
                "role": "yourai",
                "text": entry["yourai_msg"],
                "ts": entry["ts"],
                "tracking_id": entry.get("tracking_id", ""),
            }
        )
    return {"messages": messages, "total": len(entries)}


def get_streak_payload(user_id: str) -> dict:
    """
    Calculates the consecutive active day interaction streak for a user ID.

    Args:
        user_id (str): The canonical user ID.

    Returns:
        dict: The streak payload containing streak count, last active date, and total active days.
    """
    active_dates = {
        entry.get("ts", "")[:10]
        for entry in iter_user_entries(user_id)
        if entry.get("ts")
    }

    today = date.today()
    streak = 0
    check = today
    if str(today) not in active_dates:
        check = today - timedelta(days=1)
    while str(check) in active_dates:
        streak += 1
        check -= timedelta(days=1)

    return {
        "streak": streak,
        "last_active": max(active_dates) if active_dates else None,
        "total_days": len(active_dates),
    }
