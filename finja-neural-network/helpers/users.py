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

# Standard-Werte für neue User
DEFAULT_USER = {
    "name": "Viewer",
    "role": "Viewer", # Viewer, VIP, Mod, Admin
    "first_seen": 0,
    "last_seen": 0,
    "msg_count": 0,
    "facts": [] # Z.B. "Mag Minecraft"
}

class UserManager:
    def __init__(self):
        self.users = self._load()

    def _load(self):
        if not os.path.exists(USERS_FILE): return {}
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="users_load")
            log_exception("USERS", err)
            return {}

    def _save(self):
        """Speichert die User atomic, damit die Datei bei Abstürzen nicht korrumpiert!"""
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
            except OSError:
                pass

    def get_profile(self, username):
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
        
        # Speichern (nicht bei jedem Aufruf optimal, aber hier einfachheitshalber ja)
        self._save()
        
        return self.users[username]

    def add_fact(self, username, fact):
        """Wenn YourAI was lernt (z.B. 'Nico mag Trucks'), speichern wir das."""
        username = username.lower()
        if username in self.users:
            if fact not in self.users[username]["facts"]:
                self.users[username]["facts"].append(fact)
                self._save()
                log("USERS", f"🧠 Neues Detail über {username} gelernt: {fact}", Fore.CYAN)

# Globale Instanz
directory = UserManager()