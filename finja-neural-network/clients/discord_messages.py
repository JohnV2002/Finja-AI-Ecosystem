"""
YourAI AI - Discord Message Formatting
=====================================
Utility helpers for processing incoming and formatting outgoing Discord messages.

Main Responsibilities:
- Translate Discord custom emojis to readable strings.
- Map text emojis to server custom emoji formats.
- Split long outgoing messages to fit Discord's 2000 character limit.

Side Effects:
- None.
"""

import _paths  # noqa: F401

from config import DISCORD_CUSTOM_EMOJIS
from helpers.text_parser import replace_discord_colon_emojis, resolve_discord_custom_emojis


def resolve_custom_emojis(text: str) -> str:
    """
    Translates Discord custom emoji markup in raw text into human-readable text labels.

    Args:
        text (str): The raw input text.

    Returns:
        str: The emoji-resolved text.
    """
    return resolve_discord_custom_emojis(text, DISCORD_CUSTOM_EMOJIS)


def resolve_outgoing_emojis(text: str, server_emojis: dict) -> str:
    """
    Translates shortcode :emoji_name: patterns into cached Discord emoji formats.

    Args:
        text (str): Outgoing message text.
        server_emojis (dict): Cache map of name -> "<a:name:id>" markup.

    Returns:
        str: The formatted message.
    """
    if not server_emojis:
        return text
    return replace_discord_colon_emojis(text, server_emojis)


def split_message(text: str, max_len: int = 1900) -> list:
    """
    Splits a long message string into chunks adhering to Discord's character limit.

    Args:
        text (str): Outgoing message text.
        max_len (int, optional): Maximum length per chunk. Defaults to 1900.

    Returns:
        list: A list of message chunks.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        split_at = text.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = text.rfind(" ", 0, max_len)
        if split_at <= 0:
            split_at = max_len

        chunk = text[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        text = text[split_at:].lstrip()

    return chunks

