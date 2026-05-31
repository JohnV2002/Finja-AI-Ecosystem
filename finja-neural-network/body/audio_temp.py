"""
Body Audio Temp Helpers
=======================
Shared utility helpers for managing temporary audio files used by recording and output modules.

Main Responsibilities:
- Purge expired or transient speech audio WAV files.

Side Effects:
- Deletes files from the disk/filesystem.
"""

import os

from display import log_exception
from exceptions import YourAISystemError

BODY_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_SPEECH_PATH = os.path.join(BODY_DIR, "temp_speech.wav")


def remove_temp_audio(path: str, category: str = "AUDIO") -> None:
    """
    Safely removes a temporary audio file from the filesystem.

    Args:
        path (str): The absolute path to the temporary audio file.
        category (str, optional): Logging category for error tracking. Defaults to "AUDIO".

    Returns:
        None.
    """
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        err = YourAISystemError(
            message="Temporary audio cleanup failed",
            path=path,
            cause=e,
            module="body_audio_temp",
        )
        log_exception(category, err)
