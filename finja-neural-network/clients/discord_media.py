"""
YourAI AI - Discord Media Extraction
===================================
Handles extracting media content (stickers, GIFs, image URLs, attached text files) from Discord messages.

Main Responsibilities:
- Parse Discord message attachments and embeds.
- Download and decode small text files for prompt inclusion context.
- Identify GIF keywords from Giphy/Tenor URLs.

Side Effects:
- Performs transient memory reads of small text file attachments.
"""

import _paths  # noqa: F401
from typing import Optional

from display import log_exception
from exceptions import YourAIUnexpectedError
from helpers.text_parser import extract_discord_gif_keywords


TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".js", ".ts", ".css", ".html",
    ".yml", ".yaml", ".toml", ".cfg", ".ini", ".log", ".csv",
}
MAX_TEXT_FILE_SIZE = 5 * 1024 * 1024


def _log_unexpected(module: str, error: Exception):
    """
    Wraps an unexpected exception in a YourAI error and logs it.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    err = YourAIUnexpectedError(cause=error, module=module)
    log_exception("DISCORD", err)


def _extract_stickers_context(stickers, server_stickers: dict) -> list[str]:
    """
    Builds text context for stickers attached to a Discord message.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    parts = []
    if not stickers:
        return parts
    for sticker in stickers:
        desc = server_stickers.get(sticker.name) if server_stickers else None
        if desc:
            parts.append(f"(Sticker: {sticker.name} - {desc})")
        else:
            parts.append(f"(Sticker: {sticker.name})")
    return parts


def _extract_embeds_context(embeds) -> list[str]:
    """
    Builds text context for GIF embeds attached to a Discord message.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    parts = []
    if not embeds:
        return parts
    for embed in embeds:
        url = embed.url or (embed.thumbnail.url if embed.thumbnail else "")
        if not url:
            continue
        keywords = extract_discord_gif_keywords(url)
        if keywords:
            parts.append(f"(GIF: {keywords})")
            continue
        if embed.type == "gifv" or ".gif" in url.lower():
            parts.append("(GIF sent)")
    return parts


async def _read_attachment_text(att, filename: str) -> tuple[Optional[dict], str]:
    """
    Reads a small text attachment from Discord into prompt context.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    if att.size and att.size > MAX_TEXT_FILE_SIZE:
        return None, f"(File: {filename} - too large: {att.size // 1000}KB)"
    try:
        file_bytes = await att.read()
        if file_bytes:
            file_text = file_bytes.decode("utf-8", errors="replace")
            return {"name": filename, "data": file_text}, f"(Attached text file: {filename})"
        return None, f"(File: {filename} - could not be read)"
    except Exception as e:
        _log_unexpected("discord_attachment_read", e)
        return None, f"(File: {filename} - error: {e})"


async def _extract_attachments_context(attachments) -> tuple[list[str], list[str], list[dict]]:
    """
    Extracts images, videos, and text files from Discord attachments.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    parts = []
    image_urls = []
    text_attachments = []
    if not attachments:
        return parts, image_urls, text_attachments

    for att in attachments:
        ct = att.content_type or ""
        filename = att.filename or ""
        ext = filename[filename.rfind("."):].lower() if "." in filename else ""

        if ct.startswith("image/"):
            image_urls.append(att.url)
            parts.append(f"(Image: {filename})")
        elif ct.startswith("video/"):
            parts.append(f"(Video: {filename})")
        elif ext in TEXT_EXTENSIONS or ct.startswith("text/"):
            text_att, part_text = await _read_attachment_text(att, filename)
            if text_att:
                text_attachments.append(text_att)
            parts.append(part_text)
    return parts, image_urls, text_attachments


async def extract_media_context(message, server_stickers: dict) -> tuple[str, list, list]:
    """
    Extracts stickers, GIFs, image URLs, and text-file content from an incoming Discord message.

    Args:
        message (discord.Message): The Discord message object to parse.
        server_stickers (dict): Cached stickers mapping from the guild.

    Returns:
        tuple[str, list, list]: A tuple containing:
                                - str: A string context describing the attachments.
                                - list: A list of image URLs.
                                - list: A list of dicts for text attachments (name, data).
    """
    parts = []
    parts.extend(_extract_stickers_context(message.stickers, server_stickers))
    parts.extend(_extract_embeds_context(message.embeds))

    attachment_parts, image_urls, text_attachments = await _extract_attachments_context(message.attachments)
    parts.extend(attachment_parts)
    return " ".join(parts), image_urls, text_attachments

