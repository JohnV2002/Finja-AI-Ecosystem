"""Optional dashboard debug access for memory modules."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log_exception
from exceptions import YourAIUnexpectedError

_debug_checked = False
_debug_client = None


def get_dashboard_debug(label: str = "MEMORY", module: str = "memory_dashboard_debug"):
    """Return dashboard debug client if available, logging import failures once."""
    global _debug_checked, _debug_client

    if _debug_checked:
        return _debug_client

    try:
        from clients.dashboard_client import debug

        _debug_client = debug
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module=module)
        log_exception(label, err)
        _debug_client = None

    _debug_checked = True
    return _debug_client
