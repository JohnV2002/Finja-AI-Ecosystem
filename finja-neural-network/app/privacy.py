"""
YourAI App Privacy Helpers
=========================
GDPR/DSGVO data portability (Art. 15) and erasure (Art. 17) compliance helpers
for mobile endpoints.

Main Responsibilities:
- Erasure (Art. 17): Delete user diary entries by session UUID and memory facts by user_id.
- Portability (Art. 15): Count and retrieve stored diary entries and memory facts.

Side Effects:
- Performs HTTP API calls to the external memory server/service.
- Logs server connectivity issues to debug console using YourAIMemoryServerError.
"""

import os
import sys

import httpx
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIMemoryError, YourAIMemoryServerError, YourAIUnexpectedError
from config import MEMORY_API_BASE, MEMORY_API_KEY
from memory.episodic import Diary, journal


async def delete_user_data(session_uuid: str, user_id: str) -> dict:
    """
    Complies with GDPR/DSGVO Article 17 (Right to Erasure).
    Deletes all diary entries matching the session UUID and all memory facts 
    stored on the memory server for the canonical user ID.

    Args:
        session_uuid (str): The session identifier to purge diary entries for.
        user_id (str): The canonical user ID to purge memories for.

    Raises:
        HTTPException: 500 if an error occurs while deleting local diary files.

    Returns:
        dict: A confirmation dictionary with the count of deleted items and status.
    """
    deleted = 0
    memory_deleted = False

    try:
        diary = Diary()
        deleted = diary.delete_by_uuid(session_uuid)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_privacy_delete_diary")
        log_exception("APP_PRIVACY", err)
        raise HTTPException(status_code=500, detail="Error deleting data")

    if user_id:
        try:
            if MEMORY_API_BASE and MEMORY_API_KEY:
                url = f"{MEMORY_API_BASE}/delete_user_memories"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        url,
                        headers={"X-API-Key": MEMORY_API_KEY, "Content-Type": "application/json"},
                        json={"user_id": user_id},
                    )
                    memory_deleted = response.status_code == 200
                    if not memory_deleted:
                        err = YourAIMemoryServerError(
                            url=url,
                            status=response.status_code,
                            user_id=user_id,
                            module="app_privacy",
                        )
                        log_exception("APP_PRIVACY", err)
        except Exception as e:
            err = YourAIMemoryServerError(
                user_id=user_id,
                cause=e,
                module="app_privacy",
            )
            log_exception("APP_PRIVACY", err)

    log(
        "APP_PRIVACY",
        f"GDPR/DSGVO Art.17: {deleted} diary entries, memories={'yes' if memory_deleted else 'no'} | user={user_id}",
        Fore.CYAN,
    )
    return {
        "ok": True,
        "deleted": deleted,
        "memory_deleted": memory_deleted,
        "message": f"{deleted} entries deleted",
    }


async def get_user_data_summary(user_key: str, user_id: str) -> dict:
    """
    Complies with GDPR/DSGVO Article 15 (Right to Access).
    Retrieves the total count of diary entries and the list of memory facts
    for the user.

    Args:
        user_key (str): The user access key identifier.
        user_id (str): The canonical user ID.

    Returns:
        dict: A summary dictionary containing the diary_count, list of memory_facts, 
              and memory_error flag if the remote server call failed.
    """
    result: dict = {
        "diary_count": 0,
        "memory_facts": [],
        "memory_error": False,
    }

    if user_id:
        try:
            result["diary_count"] = journal.count_by_user_id(user_id)
        except Exception as e:
            err = YourAIMemoryError(
                "Could not count diary entries",
                user_id=user_id,
                cause=e,
                module="app_privacy",
            )
            log_exception("APP_PRIVACY", err)

    try:
        if MEMORY_API_BASE and MEMORY_API_KEY:
            url = f"{MEMORY_API_BASE}/get_memories"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    url,
                    headers={"X-API-Key": MEMORY_API_KEY},
                    params={"user_id": user_id, "limit": 200},
                )
                if response.status_code == 200:
                    facts = response.json()
                    result["memory_facts"] = [m.get("text", "") for m in facts if m.get("text")]
                else:
                    result["memory_error"] = True
                    err = YourAIMemoryServerError(
                        url=url,
                        status=response.status_code,
                        user_id=user_id,
                        module="app_privacy",
                    )
                    log_exception("APP_PRIVACY", err)
    except Exception as e:
        result["memory_error"] = True
        err = YourAIMemoryServerError(user_id=user_id, cause=e, module="app_privacy")
        log_exception("APP_PRIVACY", err)

    log(
        "APP_PRIVACY",
        f"Art.15 data view: {user_key} ({user_id}) - diary={result['diary_count']}, facts={len(result['memory_facts'])}",
        Fore.CYAN,
    )
    return result
