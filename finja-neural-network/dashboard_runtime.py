"""Runtime config helpers for the YourAI dashboard."""

import json
import os

from display import log_exception
from exceptions import YourAIUnexpectedError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_CONFIG_FILE = os.path.join(BASE_DIR, "runtime_config.json")

EXPOSED_FLAGS = [
    "USE_STREAMING",
    "USE_VOICE",
    "USE_VISION",
    "USE_DISCORD",
    "USE_SPOTIFY",
    "USE_TOOLS",
    "USE_MEMORY",
    "USE_EPISODIC",
    "USE_THINKING",
    "USE_GRANITE",
    "USE_COHERENCE_CHECK",
    "USE_CONSOLE_LOG",
    "USE_WEB_SEARCH",
    "USE_PAPERLESS",
    "USE_HOME_ASSISTANT",
    "USE_IMAGE_GEN",
    "USE_PROMISE_CHECK",
    "USE_SUBCONSCIOUS",
    "USE_MAINTENANCE",
]


def load_runtime_overrides() -> dict:
    """Load runtime feature-flag overrides from disk (empty dict on error)."""
    if os.path.exists(RUNTIME_CONFIG_FILE):
        try:
            with open(RUNTIME_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="dashboard_runtime_load")
            log_exception("DASHBOARD", err)
    return {}


def save_runtime_override(key: str, value) -> None:
    """Set a single runtime override key and persist all overrides to disk."""
    overrides = load_runtime_overrides()
    overrides[key] = value
    with open(RUNTIME_CONFIG_FILE, "w") as f:
        json.dump(overrides, f, indent=2)
