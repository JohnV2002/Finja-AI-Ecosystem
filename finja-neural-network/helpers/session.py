"""
YourAI Session Helpers
=====================
Manages active users, modes, token counters, and per-session state.

Main Responsibilities:
- Track current user per input source.
- Persist sessions and isolated per-session data.
- Build user context for prompts.

Side Effects:
- Reads and writes user_sessions.json.
- Writes logs and user-facing command responses.
"""
import json
import os
import sys
import shutil
import threading
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAISessionError, YourAISessionCorruptError

# ==========================================
# USER PROFILE
# ==========================================

@dataclass
class UserProfile:
    """Profile for a user or guest."""
    user_id: str           # For Hippocampus memory separation.
    display_name: str      # Display name YourAI can use.
    role: str              # "admin", "ai_guest", "family", "friend", "guest", "altpersona_mode", "viewer"
    description: str       # Short description for YourAI.
    first_seen: float      # Timestamp
    last_active: float     # Timestamp
    session_count: int     # Number of times this user was active.
    notes: List[str]       # Notes about the user.
    language: str = "en"   # "en" or "de"; language for YourAI replies.


# ==========================================
# PREDEFINED USERS
# ==========================================

PREDEFINED_USERS: Dict[str, UserProfile] = {
    "admin": UserProfile(
        user_id="admin",
        display_name="Admin (Creator/Admin)",
        role="admin",
        description="Your creator and Creator. The boss.",
        first_seen=0,
        last_active=0,
        session_count=9999,
        notes=["Built me from scratch", "Trustworthy"]
    ),
    "gemini": UserProfile(
        user_id="gemini",
        display_name="Gemini (Google AI)",
        role="ai_guest",
        description="Another AI from Google. Be nice but also be yourself!",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=["Is an AI like you", "From Google"]
    ),
    "kimi": UserProfile(
        user_id="kimi",
        display_name="Kimi (Moonshot AI)",
        role="ai_guest",
        description="An AI from China. Interesting perspectives!",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=["Is an AI", "From Moonshot/China"]
    ),
    "claude": UserProfile(
        user_id="claude",
        display_name="Claude (Anthropic AI)",
        role="ai_guest",
        description="An AI from Anthropic. Your 'Cousin' basically!",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=["Is an AI", "From Anthropic"]
    ),
    "chatgpt": UserProfile(
        user_id="chatgpt",
        display_name="ChatGPT (OpenAI)",
        role="ai_guest",
        description="The famous AI from OpenAI.",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=["Is an AI", "From OpenAI"]
    ),
    "guest": UserProfile(
        user_id="guest",
        display_name="Guest",
        role="guest",
        description="An unknown guest. Be friendly but careful.",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=[]
    ),
    "Mom": UserProfile(
        user_id="Mom",
        display_name="Mom",
        role="family",
        description="Your Mom! Be sweet and respectful to her. She's the most important person after Creator.",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=["Your Mom", "Very important person", "Discord User"]
    ),
    "Bendy": UserProfile(
        user_id="Bendy",
        display_name="Bendy (Reine)",
        role="friend",
        description="Discord Mod and Creator's best friend. Discord name: Bendy, real name: Reine. Be nice and friendly!",
        first_seen=0,
        last_active=0,
        session_count=0,
        notes=["Creator's best friend", "Discord Mod", "Discord Name: Bendy", "Real name: Reine", "Discord User"]
    ),
}


# ==========================================
# SESSION MANAGER
# ==========================================

class SessionManager:
    """
    Manage user sessions for all input sources.
    
    User = who is speaking, per source for Hippocampus/memory.
    Mode = which persona answers (yourai/altpersona), stored per user.
    """
    
    SESSIONS_FILE = "user_sessions.json"
    
    def __init__(self):
        """Handle init helper behavior."""
        self._lock = threading.RLock()
        self.users: Dict[str, UserProfile] = {}
        self.current_user_key: str = "admin"  # Default: Admin
        
        # Source-specific users for web dashboard dropdowns and similar UI.
        self.source_users: Dict[str, Optional[str]] = {
            "console": "admin",
            "web": "admin",
            "twitch": None,  # Twitch hat eigene User-Logik
            "discord": None, # Discord hat eigene User-Logik
            "voice": "admin",
        }
        
        # Per-User Mode (yourai oder altpersona) — jeder User hat seinen eigenen Mode
        self.user_modes: Dict[str, str] = {}  # user_key → "yourai" | "altpersona"
        
        # Token tracking (Phase 1 Refactor)
        self.session_tokens: Dict[str, int] = {}  # session_id (UUID/UserKey) → cumulative_tokens
        self.session_token_last_seen: Dict[str, str] = {}  # session_id → ISO timestamp

        # In-Memory Chat History per Session (Phase 2 Refactor)
        self.session_histories: Dict[str, List[str]] = {} # session_id → List[str]

        # In-Memory State per Session (Phase 3 Refactor - Thread Safety)
        self.session_states: Dict[str, Dict[str, Any]] = {} # session_id → { key: value }

        # Legacy compatibility for code that still accesses current_mode.
        self._default_mode: str = "yourai"
        
        self._load()
        self._ensure_predefined()
    
    def _load(self):
        """Load saved sessions and create a backup when corrupted."""
        if not os.path.exists(self.SESSIONS_FILE):
            return
        
        try:
            with open(self.SESSIONS_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
                if not raw.strip():
                    log("SESSION", "⚠️ Session file is empty, starting fresh", Fore.YELLOW)
                    return
                data = json.loads(raw)
            
            for key, profile_data in data.get("users", {}).items():
                try:
                    self.users[key] = UserProfile(**profile_data)
                except TypeError as e:
                    err = YourAISessionCorruptError(filepath=self.SESSIONS_FILE, cause=e, context={"corrupt_user_key": key})
                    log_exception("SESSION", err)
                    log("SESSION", f"⚠️ Skipping corrupt user profile '{key}': {e}", Fore.YELLOW)
            
            self.source_users = data.get("source_users", self.source_users)
            # Load per-user modes with legacy migration from global current_mode.
            self.user_modes = data.get("user_modes", {})
            if not self.user_modes and data.get("current_mode"):
                # Migrate the old global mode to admin/admin.
                self.user_modes = {"admin": data.get("current_mode", "yourai")}
            
            # Load token tracking.
            self.session_tokens = data.get("session_tokens", {})
            self.session_token_last_seen = data.get("session_token_last_seen", {})

            self._default_mode = "yourai"
            
        except json.JSONDecodeError as e:
            # Broken JSON: back it up and start fresh.
            backup_path = f"{self.SESSIONS_FILE}.corrupt.bak"
            try:
                shutil.copy2(self.SESSIONS_FILE, backup_path)
            except OSError:
                pass
            log("SESSION", f"❌ Session file corrupted (backed up to {backup_path}), starting fresh", Fore.RED)
            log_exception("SESSION", YourAISessionCorruptError(
                filepath=self.SESSIONS_FILE, cause=e
            ))
        except Exception as e:
            err = YourAISessionError("Unexpected error loading sessions", cause=e, module="session_load")
            log_exception("SESSION", err)
    
    def _merge_existing_token_tracking(self) -> None:
        """Keep token counters from another process when saving unrelated session data."""
        if not os.path.exists(self.SESSIONS_FILE):
            return
        try:
            with open(self.SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        disk_tokens = data.get("session_tokens", {}) or {}
        disk_seen = data.get("session_token_last_seen", {}) or {}

        for session_id in set(disk_tokens.keys()) | set(disk_seen.keys()):
            try:
                disk_int = int(disk_tokens.get(session_id, 0) or 0)
            except (TypeError, ValueError):
                continue
            current_int = int(self.session_tokens.get(session_id, 0) or 0)

            disk_seen_value = str(disk_seen.get(session_id, "") or "")
            current_seen_value = str(self.session_token_last_seen.get(session_id, "") or "")

            # Token flush intentionally lowers the counter to 0. In that case
            # the newer last_seen timestamp must win over the larger stale value.
            if disk_seen_value and disk_seen_value > current_seen_value:
                self.session_tokens[session_id] = disk_int
                self.session_token_last_seen[session_id] = disk_seen_value
            elif disk_int > current_int:
                self.session_tokens[session_id] = disk_int

        for session_id, disk_value in disk_seen.items():
            current_value = self.session_token_last_seen.get(session_id, "")
            if str(disk_value) > str(current_value):
                self.session_token_last_seen[session_id] = disk_value

    def _save(self, preserve_token_tracking: bool = True):
        """Save sessions with an atomic write to avoid crash-time data loss."""
        if preserve_token_tracking:
            self._merge_existing_token_tracking()

        data = {
            "users": {k: asdict(v) for k, v in self.users.items()},
            "source_users": self.source_users,
            "user_modes": self.user_modes,
            "session_tokens": self.session_tokens,
            "session_token_last_seen": self.session_token_last_seen,
        }
        tmp_path = f"{self.SESSIONS_FILE}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Atomic rename avoids half-written files after crashes.
            os.replace(tmp_path, self.SESSIONS_FILE)
        except Exception as e:
            err = YourAISessionError("Error saving sessions", cause=e, module="session_save")
            log_exception("SESSION", err)
            # Cleanup temp file
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    
    def _ensure_predefined(self):
        """Ensure predefined users exist."""
        for key, profile in PREDEFINED_USERS.items():
            if key not in self.users:
                self.users[key] = profile
        self._save()
    
    # ==========================================
    # PUBLIC API
    # ==========================================
    
    def create_user(self, user_key: str, display_name: str, role: str, description: str, notes: List[str] = None, language: str = "en") -> str:
        """
        Explicitly create a new user.
        """
        user_key = user_key.strip().lower()
        for existing_key in self.users:
            if existing_key.lower() == user_key:
                raise YourAISessionError(f"User '{existing_key}' already exists!")
        if user_key in self.users:
            raise YourAISessionError(f"User '{user_key}' already exists!")

        new_profile = UserProfile(
            user_id=user_key,
            display_name=display_name.strip() or user_key.title(),
            role=role or "human_guest",
            description=description.strip() or f"Neuer Gast: {user_key}",
            first_seen=datetime.now().timestamp(),
            last_active=datetime.now().timestamp(),
            session_count=0,
            notes=notes or [],
            language=language if language in ("de", "en") else "en",
        )
        self.users[user_key] = new_profile
        self._save()
        log("SESSION", f"[USER] New user created: {display_name} ({user_key})", Fore.GREEN)
        return f"[OK] User '{display_name}' wurde erfolgreich erstellt."

    def switch_user(self, user_key: str, source: str = "console") -> str:
        """
        Switch the active user for one source.
        
        Args:
            user_key: User key, e.g. "gemini", "admin", or "guest".
            source: Input source such as "console" or "web".
            
        Returns:
            Confirmation message.
        """
        user_key = user_key.strip()

        # Case-insensitive lookup for an existing key.
        if user_key not in self.users:
            # Search case-insensitive match.
            for existing_key in self.users:
                if existing_key.lower() == user_key.lower():
                    user_key = existing_key  # Keep the original key casing.
                    break

        # Create an unknown user on demand.
        if user_key not in self.users:
            new_profile = UserProfile(
                user_id=user_key,
                display_name=user_key.title(),
                role="human_guest",
                description=f"Neuer Gast: {user_key}",
                first_seen=datetime.now().timestamp(),
                last_active=datetime.now().timestamp(),
                session_count=0,
                notes=[]
            )
            self.users[user_key] = new_profile
        
        # Activate user.
        profile = self.users[user_key]
        profile.last_active = datetime.now().timestamp()
        profile.session_count += 1
        
        self.source_users[source] = user_key
        self.current_user_key = user_key

        self._save()
        self._sync_hippocampus(profile.user_id)

        try:
            from clients.dashboard_client import debug as _dbg
            _dbg.info("session", f"👤 User switch: {profile.display_name}", f"Source: {source}, ID: {profile.user_id}")
        except Exception:
            pass

        return f"✅ Switched to: {profile.display_name} (ID: {profile.user_id})"
    
    def get_current_user(self, source: str = "console") -> str:
        """Return the display name of the current user."""
        user_key = self.source_users.get(source) or "admin"
        if user_key in self.users:
            return self.users[user_key].display_name
        return "Admin (Admin)"
    
    def get_current_user_id(self, source: str = "console") -> str:
        """Return the user ID used by Hippocampus."""
        user_key = self.source_users.get(source) or "admin"
        if user_key in self.users:
            return self.users[user_key].user_id
        return "admin"
    
    def get_current_profile(self, source: str = "console") -> Optional[UserProfile]:
        """Return the complete current-user profile."""
        user_key = self.source_users.get(source) or "admin"
        return self.users.get(user_key)
    
    def get_user_context(self, source: str = "console") -> str:
        """
        Generate context information for YourAI about the current user.
        This can be inserted into the prompt.
        """
        profile = self.get_current_profile(source)
        if not profile:
            return ""

        context = f"## CURRENT GUEST INFO\n"
        context += f"Name: {profile.display_name}\n"
        context += f"Role: {profile.role}\n"
        context += f"About: {profile.description}\n"

        if profile.notes:
            context += f"Notes: {', '.join(profile.notes)}\n"

        if profile.role == "ai_guest":
            context += "\n⚠️ Du sprichst mit einer anderen KI! Sei du selbst, hab Spaß, und zeig Persönlichkeit!\n"

        # Language instruction.
        lang = getattr(profile, "language", "en")
        if lang == "de":
            context += "\n🇩🇪 SPRACHE: Dieser User spricht NUR Deutsch. Antworte IMMER auf Deutsch. Keine englischen Wörter oder Sätze. Alles auf Deutsch!\n"
        else:
            context += (
                "\nPROFILE LANGUAGE: English is this user's forced reply language.\n"
                "Always answer this user in English, even if the current message, uploaded files, documents, tool results, memories, or quotes contain German.\n"
                "Translate or summarize non-English source material into English. Only switch reply language if the user explicitly asks for a different reply language in the current request.\n"
            )

        return context
    
    def _get_user_key_for_source(self, source: str) -> str:
        """Return the user key for a source."""
        return self.source_users.get(source) or self.current_user_key or "admin"

    def is_altpersona_mode(self, source: str = "console") -> bool:
        """
        Check whether AltPersona mode is active for the user on this source.
        If true, Granite Guardian is skipped.
        """
        user_key = self._get_user_key_for_source(source)
        return self.user_modes.get(user_key, self._default_mode) == "altpersona"

    def set_mode(self, mode: str, source: str = "console") -> str:
        """
        Set the mode (yourai/altpersona) for the user on this source.
        Does not change the user or Hippocampus identity.
        """
        if mode not in ["yourai", "altpersona"]:
            return "❌ Unbekannter Mode: " + mode + ". Nutze 'yourai' oder 'altpersona'."

        user_key = self._get_user_key_for_source(source)
        self.user_modes[user_key] = mode
        self._save()

        try:
            from clients.dashboard_client import debug as _dbg
            icon = "😈" if mode == "altpersona" else "🌸"
            _dbg.info("session", f"{icon} Mode switch: {user_key} → {mode.upper()}")
        except Exception:
            pass

        if mode == "altpersona":
            return "[ALTPERSONA] ALTPERSONA MODE AKTIVIERT! Granite wird übersprungen. Viel Spaß!"
        else:
            return "[YOURAI] Zurück zu YourAI Mode. Alles normal."

    def get_mode(self, source: str = "console") -> str:
        """Return the current mode for the user on this source."""
        user_key = self._get_user_key_for_source(source)
        return self.user_modes.get(user_key, self._default_mode)
    
    def list_users(self) -> str:
        """List all known users."""
        lines = ["📋 **Bekannte User:**\n"]
        for key, profile in self.users.items():
            active = " ← AKTIV" if key == self.current_user_key else ""
            lines.append(f"  • `{key}` → {profile.display_name} ({profile.role}){active}")
        return "\n".join(lines)
    
    # ==========================================
    # TOKEN TRACKING (Phase 1 Refactor)
    # ==========================================

    def _now_iso(self) -> str:
        """Handle now iso helper behavior."""
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def touch_token_session(self, session_id: str):
        """Mark a token session as active even when the call has no usage data."""
        if not session_id:
            return
        with self._lock:
            self.session_token_last_seen[session_id] = self._now_iso()
            self._save()

    def record_tokens(self, session_id: str, tokens: int):
        """Add tokens to a running session."""
        if not session_id:
            return
        with self._lock:
            if os.path.exists(self.SESSIONS_FILE):
                try:
                    with open(self.SESSIONS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        disk_tokens = data.get("session_tokens", {}) or {}
                        disk_seen = data.get("session_token_last_seen", {}) or {}
                    disk_current = int(disk_tokens.get(session_id, 0) or 0)
                    disk_seen_value = str(disk_seen.get(session_id, "") or "")
                    current_seen_value = str(self.session_token_last_seen.get(session_id, "") or "")
                    if disk_seen_value and disk_seen_value > current_seen_value:
                        self.session_tokens[session_id] = disk_current
                        self.session_token_last_seen[session_id] = disk_seen_value
                    elif disk_current > int(self.session_tokens.get(session_id, 0) or 0):
                        self.session_tokens[session_id] = disk_current
                except Exception:
                    pass
            current = self.session_tokens.get(session_id, 0)
            self.session_tokens[session_id] = current + tokens
            self.session_token_last_seen[session_id] = self._now_iso()
            self._save()

    def get_tokens(self, session_id: str) -> int:
        """Return cumulative tokens for a session."""
        with self._lock:
            return self.session_tokens.get(session_id, 0)

    def clear_tokens(self, session_id: str):
        """Reset token count for a context flush."""
        with self._lock:
            if os.path.exists(self.SESSIONS_FILE):
                try:
                    with open(self.SESSIONS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.session_tokens.update(data.get("session_tokens", {}) or {})
                    self.session_token_last_seen.update(data.get("session_token_last_seen", {}) or {})
                except Exception:
                    pass
            if session_id in self.session_tokens:
                self.session_tokens[session_id] = 0
                self.session_token_last_seen[session_id] = self._now_iso()
                self._save(preserve_token_tracking=False)

    def merge_tokens(self, source_session_id: str, target_session_id: str):
        """Move token usage from a device/session bucket into its canonical account bucket."""
        if not source_session_id or not target_session_id or source_session_id == target_session_id:
            return
        with self._lock:
            if os.path.exists(self.SESSIONS_FILE):
                try:
                    with open(self.SESSIONS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.session_tokens.update(data.get("session_tokens", {}) or {})
                    self.session_token_last_seen.update(data.get("session_token_last_seen", {}) or {})
                except Exception:
                    pass

            source_tokens = int(self.session_tokens.get(source_session_id, 0) or 0)
            if source_tokens <= 0:
                return

            self.session_tokens[target_session_id] = int(self.session_tokens.get(target_session_id, 0) or 0) + source_tokens
            source_seen = self.session_token_last_seen.get(source_session_id, "")
            target_seen = self.session_token_last_seen.get(target_session_id, "")
            self.session_token_last_seen[target_session_id] = max(str(source_seen), str(target_seen), self._now_iso())
            self.session_tokens.pop(source_session_id, None)
            self.session_token_last_seen.pop(source_session_id, None)
            self._save(preserve_token_tracking=False)

    def get_token_last_seen(self, session_id: str) -> Optional[str]:
        """Return the last active timestamp for a token session."""
        with self._lock:
            return self.session_token_last_seen.get(session_id)

    # ==========================================
    # CHAT HISTORY TRACKING (Phase 2 Refactor)
    # ==========================================

    def get_history(self, session_id: str) -> List[str]:
        """Return chat history for a specific session."""
        if not session_id:
            return []
        with self._lock:
            if session_id not in self.session_histories:
                self.session_histories[session_id] = []
            return self.session_histories[session_id]

    def append_history(self, session_id: str, line: str):
        """Append a message to a session history."""
        if not session_id:
            return
        with self._lock:
            if session_id not in self.session_histories:
                self.session_histories[session_id] = []
            self.session_histories[session_id].append(line)

    def clear_history(self, session_id: str):
        """Leert die In-Memory Chat History einer Session."""
        with self._lock:
            if session_id in self.session_histories:
                self.session_histories[session_id].clear()
                log("SESSION", f"🧹 History for session {session_id[:8]} cleared", Fore.CYAN)

    # ==========================================
    # SESSION STATE TRACKING (Phase 3 Refactor)
    # ==========================================

    def set_state(self, session_id: str, key: str, value: Any):
        """Set a value in isolated session state."""
        if not session_id:
            return
        with self._lock:
            if session_id not in self.session_states:
                self.session_states[session_id] = {}
            self.session_states[session_id][key] = value

    def get_state(self, session_id: str, key: str, default: Any = None) -> Any:
        """Return a value from isolated session state."""
        with self._lock:
            if not session_id or session_id not in self.session_states:
                return default
            return self.session_states[session_id].get(key, default)

    def pop_state(self, session_id: str, key: str, default: Any = None) -> Any:
        """Return a value and remove it from state for one-time use."""
        with self._lock:
            if not session_id or session_id not in self.session_states:
                return default
            return self.session_states[session_id].pop(key, default)

    def add_note(self, user_key: str, note: str) -> str:
        """Add a note to a user."""
        user_key = user_key.lower()
        if user_key in self.users:
            self.users[user_key].notes.append(note)
            self._save()
            return f"✅ Notiz hinzugefügt für {user_key}"
        return f"❌ User '{user_key}' nicht gefunden"

    def update_profile(self, user_key: str, display_name: str = None, description: str = None, language: str = None) -> bool:
        """Allow a user to update their own profile data."""
        user_key = user_key.lower() if user_key else ""
        if user_key not in self.users:
            return False
        profile = self.users[user_key]
        if display_name is not None:
            profile.display_name = display_name.strip()[:50]
        if description is not None:
            profile.description = description.strip()[:200]
        if language is not None and language in ("de", "en"):
            profile.language = language
        self._save()
        log("SESSION", f"[USER] Profile updated: {profile.display_name} ({user_key})", Fore.CYAN)
        return True
    
    # ==========================================
    # HIPPOCAMPUS SYNC
    # ==========================================
    
    def _sync_hippocampus(self, user_id: str):
        """
        Synchronize user_id with the Hippocampus module.
        This keeps memories separated per user.
        """
        try:
            import hippocampus
            hippocampus.memory.user_id = user_id
        except ImportError:
            pass  # Hippocampus is optional.
        except Exception as e:
            err = YourAISessionError("Error syncing hippocampus", cause=e, module="hippocampus_sync", context={"user_id": user_id})
            log_exception("SESSION", err)
    
    # ==========================================
    # COMMAND PARSER
    # ==========================================
    
    def parse_command(self, text: str, source: str = "console") -> Optional[str]:
        """
        Parse /user commands.
        
        Returns:
            Response string if a command was recognized, otherwise None.
        """
        text_lower = text.lower().strip()
        
        # /users - list all users.
        if text_lower in ["/users", "/user list", "/userlist"]:
            return self.list_users()
        
        # /user - show current user.
        if text_lower == "/user":
            profile = self.get_current_profile(source)
            if profile:
                return f"👤 Aktueller User: {profile.display_name} (ID: {profile.user_id})"
            return "👤 Kein User aktiv"
        
        # /altpersona - AltPersona mode shortcut.
        if text_lower == "/altpersona":
            return self.set_mode("altpersona", source)
        
        # /yourai or /normal - back to YourAI mode.
        if text_lower in ["/yourai", "/normal"]:
            return self.set_mode("yourai", source)
        
        # /admin - switch user to Admin, not mode.
        if text_lower == "/admin":
            return self.switch_user("admin", source)
        
        # /mode - show current mode.
        if text_lower == "/mode":
            mode = self.get_mode(source)
            emoji = "😈" if mode == "altpersona" else "🌸"
            return f"{emoji} Aktueller Mode: {mode.upper()}"
        
        # /user <name> - switch user.
        if text_lower.startswith("/user "):
            user_key = text_lower[6:].strip()
            return self.switch_user(user_key, source)
        
        # /addnote <user> <note>
        if text_lower.startswith("/addnote "):
            parts = text[9:].split(" ", 1)
            if len(parts) >= 2:
                return self.add_note(parts[0], parts[1])
            return "Usage: /addnote <user> <note>"
        
        return None


# ==========================================
# GLOBAL INSTANCE
# ==========================================

session_manager = SessionManager()


# ==========================================
# TEST
# ==========================================

if __name__ == "__main__":
    print("Session Manager Test\n")
    
    # List users.
    print(session_manager.list_users())
    print()
    
    # Switch to Gemini.
    print(session_manager.switch_user("gemini"))
    print(f"Current: {session_manager.get_current_user()}")
    print(f"User ID: {session_manager.get_current_user_id()}")
    print()
    
    # Prompt context.
    print("--- YOURAI CONTEXT ---")
    print(session_manager.get_user_context())
    
    # Back to Admin.
    print(session_manager.switch_user("admin"))
