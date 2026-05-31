"""
YourAI App Profile Payload
=========================
Builds the consolidated profile, mood, usage statistics, style indicators, streak,
and linked platforms info payload for the mobile app's `/api/app/me` endpoint.

Main Responsibilities:
- Fetch and merge token usage information.
- Aggregate writing style analysis statistics across linked platforms.
- Query image generation usage limits and current balance.
- Check user interaction streak days.
- List linked platform IDs (Discord, Mobile devices).

Side Effects:
- Dynamically loads and updates session tokens via the session manager.
- Merges historical style profile analysis across user aliases.
- Logs unexpected payload assembly issues using YourAISessionError and YourAIUnexpectedError.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

import config as _cfg
from session import session_manager as _sm
from display import log_exception
from exceptions import YourAISessionError, YourAIUnexpectedError
from helpers.personas import persona_manager
from helpers.platform_links import get_discord_ids, get_mobile_ids, get_linked_platforms
from helpers.style_analyzer import get_style_summary, merge_style_profile
from tools.image_limits import get_usage as get_image_usage
from app.chat_log import get_streak_payload
from app.identity import resolve_profile, resolve_user_id


def _profile_info(user_key: str, fallback_user_id: str) -> dict:
    """
    Resolves profile metadata (display name, role, description) for a user key,
    falling back to a generic guest representation if resolving fails.

    Args:
        user_key (str): The identifier key of the user.
        fallback_user_id (str): The ID to use as a fallback.

    Returns:
        dict: A profile info dictionary with user_id, display_name, role, and description.
    """
    info = {
        "user_id": fallback_user_id,
        "display_name": user_key,
        "role": "guest",
        "description": "",
    }
    try:
        profile = resolve_profile(user_key)
        if profile:
            info.update(
                {
                    "user_id": profile.user_id,
                    "display_name": profile.display_name,
                    "role": profile.role,
                    "description": profile.description,
                }
            )
    except Exception as e:
        err = YourAISessionError(
            "Could not build app profile info",
            user_key=user_key,
            cause=e,
            module="app_profile",
        )
        log_exception("APP_PROFILE", err)
    return info


def _mood_data(user_id: str = "admin") -> dict:
    """
    Retrieves current mood metadata (mood name, emoji, description, color) for a user ID.

    Args:
        user_id (str, optional): The canonical user_id. Defaults to "admin".

    Returns:
        dict: The user's mood metadata dictionary.
    """
    fallback = {"mood": "default", "emoji": "paw", "description": "Normal", "color": "#FF9800"}
    try:
        return persona_manager.get_mood_for_dashboard(user_id=user_id)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_profile_mood")
        log_exception("APP_PROFILE", err)
        return fallback


def _token_usage(user_id: str, user_key: str, session_uuid: str) -> dict:
    """
    Determines current token usage, limit, and status for the user session,
    handling session token merging and touching active sessions.

    Args:
        user_id (str): The canonical user ID.
        user_key (str): The user access key identifier.
        session_uuid (str): The temporary mobile device session UUID.

    Returns:
        dict: Token usage metadata including used, limit, remaining, percent, and level.
    """
    fallback = {"used": 0, "limit": 80000, "percent": 0, "level": "ok"}
    try:
        try:
            _sm._load()
        except Exception as e:
            err = YourAISessionError("Could not reload sessions", cause=e, module="app_profile")
            log_exception("APP_PROFILE", err)

        token_session_id = user_id or user_key
        if session_uuid and token_session_id:
            try:
                _sm.merge_tokens(session_uuid, token_session_id)
            except Exception as e:
                err = YourAISessionError(
                    "Could not merge token buckets",
                    user_id=token_session_id,
                    session_uuid=session_uuid,
                    cause=e,
                    module="app_profile",
                )
                log_exception("APP_PROFILE", err)
        try:
            _sm.touch_token_session(token_session_id)
        except Exception as e:
            err = YourAISessionError(
                "Could not touch token session",
                user_id=token_session_id,
                cause=e,
                module="app_profile",
            )
            log_exception("APP_PROFILE", err)

        used = int(_sm.get_tokens(token_session_id) or 0)
        limit = getattr(_cfg, "TOKEN_SOFT_LIMIT", 80000)

        pct = min(100, round((used / limit) * 100, 1)) if limit else 0
        if pct >= 90:
            level = "danger"
        elif pct >= 65:
            level = "warning"
        else:
            level = "ok"

        return {
            "session_id": token_session_id,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "percent": pct,
            "level": level,
        }
    except Exception as e:
        err = YourAISessionError("Could not load app token usage", user_id=user_id, cause=e, module="app_profile")
        log_exception("APP_PROFILE", err)
        return fallback


def _build_candidates(user_key: str, user_id: str, session_uuid: str) -> list:
    """
    Compiles a deduplicated list of source identifier candidates (Discord IDs,
    mobile IDs, session UUID, and user ID) to scan for style analysis.

    Args:
        user_key (str): The user access key identifier.
        user_id (str): The canonical user ID.
        session_uuid (str): The temporary mobile device session UUID.

    Returns:
        list: A list of candidate profile sources.
    """
    candidates = []
    seen = set()

    def add(sid: str, label: str, kind: str) -> None:
        if sid and sid not in seen:
            seen.add(sid)
            candidates.append({"id": sid, "label": label, "kind": kind})

    for did in get_discord_ids(user_key):
        add(f"dm_{did}", "Discord DM", "discord_dm")
    for mid in get_mobile_ids(user_key):
        add(f"app_{mid}", "Mobile App", "mobile_app")
    add(session_uuid, "Session", "session")
    add(user_id, "User", "user")
    return candidates


def _merge_candidates(candidates: list, user_id: str) -> None:
    """
    Merges platform specific writing styles into the canonical user ID profile
    for all compiled candidate sources.

    Args:
        candidates (list): The list of candidate dictionaries containing platform sources.
        user_id (str): The canonical user ID.
    """
    if not user_id:
        return
    for candidate in candidates:
        if candidate["id"] == user_id:
            continue
        try:
            merge_style_profile(candidate["id"], user_id)
        except Exception as e:
            err = YourAIUnexpectedError(
                cause=e,
                module="app_profile_style_merge",
                source_id=candidate["id"],
                user_id=user_id,
            )
            log_exception("APP_PROFILE", err)


def _rank_style_summary(summary: dict) -> tuple:
    """
    Generates a sorting key rank for a style summary based on availability
    and total message count.

    Args:
        summary (dict): The style summary dictionary to evaluate.

    Returns:
        tuple: A sorting rank tuple of (is_available, message_count).
    """
    is_available = 1 if summary.get("available") else 0
    msg_count = int(summary.get("msg_count") or 0)
    return (is_available, msg_count)


def _style_usage(user_key: str, user_id: str, session_uuid: str) -> dict:
    """
    Aggregates and merges style analysis statistics for a user across all linked platforms.

    Args:
        user_key (str): The user access key identifier.
        user_id (str): The canonical user ID.
        session_uuid (str): The temporary mobile device session UUID.

    Returns:
        dict: The aggregated style usage summary and its component sources.
    """
    try:
        candidates = _build_candidates(user_key, user_id, session_uuid)
        _merge_candidates(candidates, user_id)

        sources = []
        for candidate in candidates:
            summary = get_style_summary(candidate["id"])
            summary["source_label"] = candidate["label"]
            sources.append(summary)

        if user_id:
            style_usage = get_style_summary(user_id)
        elif sources:
            style_usage = dict(max(sources, key=_rank_style_summary))
        else:
            style_usage = {"available": False}

        style_usage["source_label"] = "User"
        style_usage["sources"] = sources
        return style_usage
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_profile_style")
        log_exception("APP_PROFILE", err)
        return {"available": False, "error": str(e)}


def _image_usage(user_id: str, role: str) -> dict:
    """
    Fetches image generation usage limits and remaining balance for a user role.

    Args:
        user_id (str): The canonical user ID.
        role (str): The user permission role level.

    Returns:
        dict: The image usage metadata (limit, used, remaining, unlimited).
    """
    fallback = {"used": 0, "limit": 0, "remaining": 0, "unlimited": False}
    try:
        return get_image_usage(user_id, role)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_profile_image_usage", user_id=user_id)
        log_exception("APP_PROFILE", err)
        return fallback


def _streak_data(user_id: str) -> dict:
    """
    Calculates the consecutive active interaction streak for a user account.

    Args:
        user_id (str): The canonical user ID.

    Returns:
        dict: The user's interaction streak payload containing streak days and total days.
    """
    try:
        return get_streak_payload(user_id)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_profile_streak", user_id=user_id)
        log_exception("APP_PROFILE", err)
        return {"streak": 0, "total_days": 0}


def _platforms(user_key: str) -> dict:
    """
    Retrieves all linked platform IDs (Discord, Mobile) for a user key.

    Args:
        user_key (str): The user access key identifier.

    Returns:
        dict: Lists of linked discord_ids and mobile_ids.
    """
    try:
        return get_linked_platforms(user_key)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="app_profile_platforms", user_key=user_key)
        log_exception("APP_PROFILE", err)
        return {"discord_ids": [], "mobile_ids": []}


def build_app_me_payload(key_info: dict, session_uuid: str) -> dict:
    """
    Builds the complete consolidated profile payload for the mobile /api/app/me endpoint.

    Args:
        key_info (dict): The dictionary containing validated key permissions and metadata.
        session_uuid (str): The temporary device session UUID.

    Returns:
        dict: The nested mobile API profile response payload.
    """
    user_key = key_info["user_key"]
    user_id = resolve_user_id(key_info)
    profile = _profile_info(user_key, user_id)
    user_id = profile["user_id"]

    return {
        "user_key": user_key,
        "user_id": user_id,
        "display_name": profile["display_name"],
        "role": profile["role"],
        "description": profile["description"],
        "mood": _mood_data(user_id),
        "token_usage": _token_usage(user_id, user_key, session_uuid),
        "style_usage": _style_usage(user_key, user_id, session_uuid),
        "image_usage": _image_usage(user_id, profile["role"]),
        "streak": _streak_data(user_id),
        "platforms": _platforms(user_key),
    }
