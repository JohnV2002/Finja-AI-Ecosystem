"""
YourAI Glorpo HTML tool.

Provides Glorpo HTML rules and optional HTML/CSS conversion for direct user
requests. Website autonomy imports the root ``glorpo_html`` module directly;
this tool is for conversational tool routing.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from exceptions import YourAIToolExecutionError
from glorpo_html import (
    YOURAI_RULES,
    TAG,
    glorpify_css,
    glorpify_document,
    glorpify_html,
)


def _extract_fenced_code(text: str, language: str) -> str:
    """Return the first fenced code block for a language (empty if none).

    Args:
        text (str): The text that may contain a fenced code block.
        language (str): The fence language tag to look for (e.g. "html").

    Returns:
        str: The trimmed code block contents, or "" when not found.
    """
    match = re.search(rf"```{language}\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _tag_cheatsheet() -> str:
    """Return a human-readable HTML -> Glorpo tag mapping cheatsheet.

    Returns:
        str: One ``<html> -> <glorpo>`` mapping per line, sorted by HTML tag.
    """
    pairs = [f"<{html}> -> <{glorpo}>" for html, glorpo in sorted(TAG.items())]
    return "\n".join(pairs)


def glorpo_html_assistant(context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """Return Glorpo HTML help, or convert fenced HTML/CSS from the user message."""
    question = str(context.get("question") or "")

    try:
        html = _extract_fenced_code(question, "html")
        css = _extract_fenced_code(question, "css")

        if html:
            converted = glorpify_document(html) if "<html" in html.lower() else glorpify_html(html)
            return {
                "success": True,
                "result": converted,
                "type": "glorpo_html",
            }

        if css:
            return {
                "success": True,
                "result": glorpify_css(css),
                "type": "glorpo_css",
            }

        return {
            "success": True,
            "result": (
                "Glorpo HTML rules for YourAI:\n\n"
                f"{YOURAI_RULES}\n\n"
                "Tag cheatsheet:\n"
                f"{_tag_cheatsheet()}"
            ),
            "type": "glorpo_rules",
        }

    except Exception as e:
        raise YourAIToolExecutionError(
            "Glorpo HTML tool failed",
            tool_name="glorpo_html",
            cause=e,
        ) from e
