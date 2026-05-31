"""
YourAI User Profile Helpers
==========================
Stores lightweight user profiles and learned user facts.

Main Responsibilities:
- Load and persist user profile records.
- Create default profiles for new users.
- Append learned details to profiles.

Side Effects:
- Reads and writes users_db.json.
- Writes user learning logs.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError

from config import USERS_DB_FILE, ADMIN_USERNAME

USERS_FILE = USERS_DB_FILE

# Default values for new users.
DEFAULT_USER = {
    "name": "Viewer",
    "role": "Viewer", # Viewer, VIP, Mod, Admin
    "first_seen": 0,
    "last_seen": 0,
    "msg_count": 0,
    "facts": [] # Z.B. "Mag Minecraft"
}

class UserManager:
    """Represent UserManager behavior for helper workflows."""
    def __init__(self):
        """Handle init helper behavior."""
        self.users = self._load()

    def _load(self):
        """Handle load helper behavior."""
        if not os.path.exists(USERS_FILE): return {}
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="users_load")
            log_exception("USERS", err)
            return {}

    def _save(self):
        """Save users atomically so crashes do not corrupt the file."""
        tmp_path = f"{USERS_FILE}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, USERS_FILE)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="users_save")
            log_exception("USERS", err)
            try:
                os.remove(tmp_path)
            except OSError as cleanup_error:
                cleanup_err = YourAIUnexpectedError(cause=cleanup_error, module="users_tmp_cleanup")
                log_exception("USERS", cleanup_err)

    def get_profile(self, username):
        """Handle get profile helper behavior."""
        username = username.lower().strip()
        
        # Admin Override (Dich erkennen wir immer)
        if username == ADMIN_USERNAME:
            return {
                "name": "Admin (YOUR_STREAMER_NAME)",
                "role": "CREATOR & BOSS",
                "facts": ["Hat mich gebaut", "Der beste Streamer"],
                "msg_count": 9999
            }

        # Neuer User? Anlegen!
        if username not in self.users:
            self.users[username] = DEFAULT_USER.copy()
            self.users[username]["name"] = username
            self.users[username]["first_seen"] = time.time()
            log("USERS", f"🆕 Neuer User registriert: {username}", Fore.GREEN)
        
        # Update Stats
        self.users[username]["last_seen"] = time.time()
        self.users[username]["msg_count"] += 1
        
        # Save immediately; not optimal for every call, but simple and explicit here.
        self._save()
        
        return self.users[username]

    def add_fact(self, username, fact):
        """Wenn YourAI was lernt (z.B. 'Nico mag Trucks'), speichern wir das."""
        username = username.lower()
        if username in self.users:
            if fact not in self.users[username]["facts"]:
                self.users[username]["facts"].append(fact)
                self._save()
                log("USERS", f"🧠 New detail learned about {username} learned: {fact}", Fore.CYAN)

# Globale Instanz
directory = UserManager()
