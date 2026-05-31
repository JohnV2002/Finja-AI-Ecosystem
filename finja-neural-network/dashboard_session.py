"""Session and token helpers for the YourAI dashboard."""

from datetime import datetime
from typing import Any, Dict, Optional

from display import Fore, log, log_exception
from exceptions import YourAIUnexpectedError


class DummySessionManager:
    """Fallback when helpers/session.py is unavailable."""

    def get_current_user(self, source: str = "console") -> str:
        """Return the default admin display name."""
        return "Admin (Admin)"

    def get_current_user_id(self, source: str = "console") -> str:
        """Return the default admin user id."""
        return "admin"

    def get_tokens(self, session_id: str) -> int:
        """Return 0 — token tracking is unavailable in the fallback."""
        return 0

    def switch_user(self, user_key: str, source: str = "console") -> str:
        """Reject user switching — the session manager is unavailable."""
        return "Session manager not available"

    def get_mode(self, source: str = "console") -> str:
        """Return the default mode ('yourai')."""
        return "yourai"

    def set_mode(self, mode: str, source: str = "console") -> str:
        """Reject mode switching — the session manager is unavailable."""
        return "Session manager not available"

    def is_altpersona_mode(self, source: str = "console") -> bool:
        """Return False — AltPersona mode is never active in the fallback."""
        return False

    @property
    def users(self) -> dict:
        """Return a single hard-coded admin user."""
        return {"admin": type("obj", (object,), {"display_name": "Admin (Admin)", "role": "admin"})()}


session_manager: Any = DummySessionManager()
PREDEFINED_USERS: Dict[str, Any] = {}
SESSION_AVAILABLE = False

try:
    from session import PREDEFINED_USERS as _pu
    from session import session_manager as _sm

    session_manager = _sm
    PREDEFINED_USERS = _pu
    SESSION_AVAILABLE = True
    log("DASHBOARD", "[OK] Session manager loaded!", Fore.GREEN)
except ImportError:
    log("DASHBOARD", "[!] Session manager not found - user switching disabled", Fore.YELLOW)


TOKEN_SOFT_LIMIT = 80000
TOKEN_DASHBOARD_ACTIVE_SECONDS = 30 * 60


def resolve_session_profile(user_key: str):
    """Find a session profile by user_key; tries exact and case-insensitive key match."""
    if not SESSION_AVAILABLE:
        return None
    profile = session_manager.users.get(user_key)
    if profile:
        return profile
    for key, candidate in session_manager.users.items():
        if key.lower() == user_key.lower():
            return candidate
    return None


def token_level(used: int, limit: int = TOKEN_SOFT_LIMIT) -> str:
    """Classify token usage as 'ok', 'warning', or 'danger' by percentage."""
    if limit <= 0:
        return "ok"
    pct = (used / limit) * 100
    if pct >= 90:
        return "danger"
    if pct >= 65:
        return "warning"
    return "ok"


def token_age_seconds(last_seen: Optional[str]) -> Optional[int]:
    """Return seconds since the last_seen ISO timestamp (None if unparseable)."""
    if not last_seen:
        return None
    try:
        normalized = last_seen.replace("Z", "+00:00")
        seen = datetime.fromisoformat(normalized)
        if seen.tzinfo is not None:
            seen = seen.replace(tzinfo=None)
        return max(0, int((datetime.utcnow() - seen).total_seconds()))
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="dashboard_token_age")
        log_exception("DASHBOARD", err)
        return None


def token_usage_payload(session_id: str) -> dict:
    """Build the dashboard token-usage payload (used/limit/percent/level/active)."""
    used = 0
    last_seen = None
    if SESSION_AVAILABLE and session_id:
        try:
            used = int(session_manager.get_tokens(session_id) or 0)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="dashboard_token_get")
            log_exception("DASHBOARD", err)
            used = 0
        try:
            last_seen = session_manager.get_token_last_seen(session_id)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="dashboard_token_last_seen")
            log_exception("DASHBOARD", err)
            last_seen = None
    age_seconds = token_age_seconds(last_seen)
    is_active = age_seconds is not None and age_seconds <= TOKEN_DASHBOARD_ACTIVE_SECONDS
    remaining = max(0, TOKEN_SOFT_LIMIT - used)
    pct = min(100, round((used / TOKEN_SOFT_LIMIT) * 100, 1)) if TOKEN_SOFT_LIMIT else 0
    return {
        "session_id": session_id,
        "used": used,
        "limit": TOKEN_SOFT_LIMIT,
        "remaining": remaining,
        "percent": pct,
        "level": token_level(used),
        "last_seen": last_seen,
        "age_seconds": age_seconds,
        "active": is_active,
    }


def reload_sessions_from_disk() -> None:
    """Dashboard and brain run in separate processes; refresh persisted session state."""
    if not SESSION_AVAILABLE:
        return
    try:
        session_manager._load()
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="dashboard_session_reload")
        log_exception("DASHBOARD", err)
        log("DASHBOARD", f"[!] Session reload failed: {e}", Fore.YELLOW)
