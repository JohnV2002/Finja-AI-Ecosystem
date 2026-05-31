"""
YourAI AI - Discord Private Channel Map
======================================
Handles loading and persisting of the discord_user_id -> private channel metadata mapping.

Main Responsibilities:
- Load mapping database from discord_channels.json.
- Persist mapping updates back to discord_channels.json.

Side Effects:
- Reads and writes to DISCORD_CHANNELS_FILE on the disk.
"""

import json
import os

import _paths  # noqa: F401

from config import DISCORD_CHANNELS_FILE
from display import Fore, log, log_exception
from exceptions import YourAIUnexpectedError


def load_private_channels() -> dict:
    """
    Loads the Discord user to private channel mapping from disk.

    Returns:
        dict: A mapping of discord_user_id -> {channel_id, username, created}.
    """
    if not os.path.exists(DISCORD_CHANNELS_FILE):
        return {}

    try:
        with open(DISCORD_CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="discord_private_channels_load")
        log_exception("DISCORD", err)
        log("DISCORD", f"Failed to read discord_channels.json: {e}", Fore.YELLOW)
        return {}


def save_private_channels(channels: dict):
    """
    Saves the Discord user to private channel mapping back to disk.

    Args:
        channels (dict): The mapping dictionary to persist.
    """
    try:
        with open(DISCORD_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels, f, indent=2, ensure_ascii=False)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="discord_private_channels_save")
        log_exception("DISCORD", err)
        log("DISCORD", f"Failed to save discord_channels.json: {e}", Fore.YELLOW)

