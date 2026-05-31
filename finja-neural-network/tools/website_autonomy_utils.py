"""Small parsing helpers shared by website autonomy tools."""

import re
from typing import Optional


def count_emoji_and_unicode(text: str) -> int:
    """Count emoji and selected unicode symbols contained in a text.

    Args:
        text (str): The text to scan.

    Returns:
        int: The number of matched emoji/unicode symbol runs.
    """
    emoji_pattern = re.compile(
        r'[\U0001F300-\U0001F9FF'
        r'\U00002702-\U000027B0'
        r'\U0000FE00-\U0000FE0F'
        r'\u2014\u2022\u25B6\u2B21'
        r'\u00A9\u00AE'
        r'\u2192\u2190\u2191\u2193'
        r']+',
        re.UNICODE,
    )
    return len(emoji_pattern.findall(text))


def extract_between(text: str, start_marker: str, end_marker: str) -> Optional[str]:
    """Return the substring between two markers, or None if either is missing.

    Args:
        text (str): The text to search.
        start_marker (str): Marker that precedes the wanted substring.
        end_marker (str): Marker that follows the wanted substring.

    Returns:
        Optional[str]: The trimmed substring, or None when a marker is absent.
    """
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return None
    start_idx += len(start_marker)
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        return None
    return text[start_idx:end_idx].strip()


def strip_code_fence(text: str, lang: str = "") -> str:
    """Remove Markdown code fences."""
    pattern_open = rf'^```{re.escape(lang)}?\s*\n?' if lang else r'^```\w*\s*\n?'
    text = re.sub(pattern_open, '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()
