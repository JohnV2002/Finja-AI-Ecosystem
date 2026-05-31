"""
YourAI App Version Helpers
=========================
Public endpoint utility to retrieve the current minimum required application 
version and verify its integrity against an MD5 lock file.

Main Responsibilities:
- Read version descriptor from app_version.txt.
- Verify version integrity against app_version.lock MD5 signature.
- Output safe fallback version in case files are missing or unreadable.

Side Effects:
- Reads app_version.txt and app_version.lock from disk.
- Logs checksum validation errors or file access failures using YourAIUnexpectedError.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_VERSION_TXT = os.path.join(_ROOT_DIR, "app_version.txt")
APP_VERSION_LOCK = os.path.join(_ROOT_DIR, "app_version.lock")


def get_app_version_payload() -> dict:
    """
    Retrieves the minimum required mobile app version and its integrity status.

    Reads the required version from app_version.txt and compares its MD5 hash 
    against app_version.lock to detect tampering or manual misconfigurations.

    Returns:
        dict: A payload mapping version, stored hash, and valid status boolean.
    """
    try:
        with open(APP_VERSION_TXT, "r", encoding="utf-8") as f:
            version = f.read().strip()
        with open(APP_VERSION_LOCK, "r", encoding="utf-8") as f:
            stored_hash = f.read().strip()

        computed = hashlib.md5(version.encode()).hexdigest()
        valid = computed == stored_hash
        if not valid:
            log(
                "APP_VERSION",
                f"app_version lock mismatch! version={version} stored={stored_hash} computed={computed}",
                Fore.RED,
            )
        return {"version": version, "hash": stored_hash, "valid": valid}
    except FileNotFoundError:
        return {"version": "0.0.0", "hash": "", "valid": False}
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_version")
        log_exception("APP_VERSION", err)
        return {"version": "0.0.0", "hash": "", "valid": False}
