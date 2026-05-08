"""
YourAI AI - Session Manager
===========================
Verwaltet den aktuellen "Gast" für Console, Web, etc.
Synchronisiert user_name (für YourAI) mit user_id (für Hippocampus).

Usage:
    from session import session_manager
    
    # User wechseln (Console Command)
    session_manager.switch_user("Gemini")
    
    # Aktuellen User holen
    name = session_manager.get_current_user()
    
    # In process_input nutzen
    process_input(text, session_manager.get_current_user(), "console", history)

Commands für YourAI:
    /user gemini     - Wechselt zu Gemini
    /user kimi       - Wechselt zu Kimi  
    /user admin       - Zurück zu Admin (Admin)
    /user            - Zeigt aktuellen User
    /users           - Listet alle bekannten User
"""

import json
import os
import sys
import shutil
from typing import Dict, Optional, List
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
    """Profil eines Users/Gastes."""
    user_id: str           # Für Hippocampus (memory separation)
    display_name: str      # Für YourAI zum Ansprechen
    role: str              # "admin", "ai_guest", "family", "friend", "guest", "altpersona_mode", "viewer"
    description: str       # Kurzbeschreibung für YourAI
    first_seen: float      # Timestamp
    last_active: float     # Timestamp
    session_count: int     # Wie oft war dieser User aktiv
    notes: List[str]       # Notizen über den User


# ==========================================
# VORDEFINIERTE USER
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
    Verwaltet User-Sessions für alle Input-Quellen.
    
    User = Wer spricht (für Hippocampus/Memory) - PRO SOURCE
    Mode = Welche Persona antwortet (yourai/altpersona) - GLOBAL für alle Sources
    """
    
    SESSIONS_FILE = "user_sessions.json"
    
    def __init__(self):
        self.users: Dict[str, UserProfile] = {}
        self.current_user_key: str = "admin"  # Default: Admin
        
        # Source-spezifische User (für Web Dashboard Dropdown etc.)
        self.source_users: Dict[str, Optional[str]] = {
            "console": "admin",
            "web": "admin",
            "twitch": None,  # Twitch hat eigene User-Logik
            "discord": None, # Discord hat eigene User-Logik
            "voice": "admin",
        }
        
        # Per-User Mode (yourai oder altpersona) — jeder User hat seinen eigenen Mode
        self.user_modes: Dict[str, str] = {}  # user_key → "yourai" | "altpersona"
        # Legacy compat: current_mode als Property für Code der noch darauf zugreift
        self._default_mode: str = "yourai"
        
        self._load()
        self._ensure_predefined()
    
    def _load(self):
        """Lädt gespeicherte Sessions. Erstellt Backup bei Corruption."""
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
            # Per-User Modes laden (mit Legacy-Migration von globalem current_mode)
            self.user_modes = data.get("user_modes", {})
            if not self.user_modes and data.get("current_mode"):
                # Legacy: alter globaler Mode → migriere als Mode für admin (admin)
                self.user_modes = {"admin": data.get("current_mode", "yourai")}
            self._default_mode = "yourai"
            
        except json.JSONDecodeError as e:
            # JSON ist kaputt — Backup machen und neu starten
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
    
    def _save(self):
        """Speichert Sessions (atomic write → kein Datenverlust bei Crash)."""
        data = {
            "users": {k: asdict(v) for k, v in self.users.items()},
            "source_users": self.source_users,
            "user_modes": self.user_modes,
        }
        tmp_path = f"{self.SESSIONS_FILE}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Atomic rename (kein halb-geschriebenes File bei Crash)
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
        """Stellt sicher dass vordefinierte User existieren."""
        for key, profile in PREDEFINED_USERS.items():
            if key not in self.users:
                self.users[key] = profile
        self._save()
    
    # ==========================================
    # PUBLIC API
    # ==========================================
    
    def create_user(self, user_key: str, display_name: str, role: str, description: str, notes: List[str] = None) -> str:
        """
        Legt einen neuen User explizit an.
        """
        user_key = user_key.strip().lower()
        if user_key in self.users:
            raise YourAISessionError(f"User '{user_key}' existiert bereits!")
        
        new_profile = UserProfile(
            user_id=user_key,
            display_name=display_name.strip() or user_key.title(),
            role=role or "human_guest",
            description=description.strip() or f"Neuer Gast: {user_key}",
            first_seen=datetime.now().timestamp(),
            last_active=datetime.now().timestamp(),
            session_count=0,
            notes=notes or []
        )
        self.users[user_key] = new_profile
        self._save()
        log("SESSION", f"[USER] Neuer User angelegt: {display_name} ({user_key})", Fore.GREEN)
        return f"[OK] User '{display_name}' wurde erfolgreich erstellt."

    def switch_user(self, user_key: str, source: str = "console") -> str:
        """
        Wechselt den aktiven User für eine Source.
        
        Args:
            user_key: User-Key (z.B. "gemini", "admin", "guest")
            source: Input-Quelle ("console", "web", etc.)
            
        Returns:
            Bestätigungs-Nachricht
        """
        user_key = user_key.strip()

        # Case-insensitive lookup: Finde existierenden Key
        if user_key not in self.users:
            # Suche case-insensitive match
            for existing_key in self.users:
                if existing_key.lower() == user_key.lower():
                    user_key = existing_key  # Verwende den Original-Key
                    break

        # Neuen User anlegen falls nicht bekannt
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
        
        # User aktivieren
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
        """Holt den Display-Namen des aktuellen Users."""
        user_key = self.source_users.get(source) or "admin"
        if user_key in self.users:
            return self.users[user_key].display_name
        return "Admin (Admin)"
    
    def get_current_user_id(self, source: str = "console") -> str:
        """Holt die User-ID für Hippocampus."""
        user_key = self.source_users.get(source) or "admin"
        if user_key in self.users:
            return self.users[user_key].user_id
        return "admin"
    
    def get_current_profile(self, source: str = "console") -> Optional[UserProfile]:
        """Holt das komplette Profil des aktuellen Users."""
        user_key = self.source_users.get(source) or "admin"
        return self.users.get(user_key)
    
    def get_user_context(self, source: str = "console") -> str:
        """
        Generiert Kontext-Info für YourAI über den aktuellen User.
        Kann in den Prompt eingefügt werden.
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
        
        return context
    
    def _get_user_key_for_source(self, source: str) -> str:
        """Holt den User-Key für eine Source."""
        return self.source_users.get(source) or self.current_user_key or "admin"

    def is_altpersona_mode(self, source: str = "console") -> bool:
        """
        Checkt ob AltPersona-Mode aktiv ist für den User der gerade auf dieser Source ist.
        Wenn True, wird Granite Guardian übersprungen!
        """
        user_key = self._get_user_key_for_source(source)
        return self.user_modes.get(user_key, self._default_mode) == "altpersona"

    def set_mode(self, mode: str, source: str = "console") -> str:
        """
        Setzt den Mode (yourai/altpersona) für den User auf dieser Source.
        Ändert NICHT den User/Hippocampus!
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
        """Gibt den aktuellen Mode zurück für den User auf dieser Source."""
        user_key = self._get_user_key_for_source(source)
        return self.user_modes.get(user_key, self._default_mode)
    
    def list_users(self) -> str:
        """Listet alle bekannten User."""
        lines = ["📋 **Bekannte User:**\n"]
        for key, profile in self.users.items():
            active = " ← AKTIV" if key == self.current_user_key else ""
            lines.append(f"  • `{key}` → {profile.display_name} ({profile.role}){active}")
        return "\n".join(lines)
    
    def add_note(self, user_key: str, note: str) -> str:
        """Fügt eine Notiz zu einem User hinzu."""
        user_key = user_key.lower()
        if user_key in self.users:
            self.users[user_key].notes.append(note)
            self._save()
            return f"✅ Notiz hinzugefügt für {user_key}"
        return f"❌ User '{user_key}' nicht gefunden"
    
    # ==========================================
    # HIPPOCAMPUS SYNC
    # ==========================================
    
    def _sync_hippocampus(self, user_id: str):
        """
        Synchronisiert die user_id mit dem Hippocampus-Modul.
        So werden Memories pro User getrennt!
        """
        try:
            import hippocampus
            hippocampus.memory.user_id = user_id
        except ImportError:
            pass  # Hippocampus optional
        except Exception as e:
            err = YourAISessionError("Error syncing hippocampus", cause=e, module="hippocampus_sync", context={"user_id": user_id})
            log_exception("SESSION", err)
    
    # ==========================================
    # COMMAND PARSER
    # ==========================================
    
    def parse_command(self, text: str, source: str = "console") -> Optional[str]:
        """
        Parst /user Commands.
        
        Returns:
            Response-String wenn Command erkannt, sonst None
        """
        text_lower = text.lower().strip()
        
        # /users - Liste alle
        if text_lower in ["/users", "/user list", "/userlist"]:
            return self.list_users()
        
        # /user - Zeige aktuellen
        if text_lower == "/user":
            profile = self.get_current_profile(source)
            if profile:
                return f"👤 Aktueller User: {profile.display_name} (ID: {profile.user_id})"
            return "👤 Kein User aktiv"
        
        # /altpersona - Shortcut für AltPersona Mode 😈
        if text_lower == "/altpersona":
            return self.set_mode("altpersona", source)
        
        # /yourai oder /normal - Zurück zu YourAI Mode
        if text_lower in ["/yourai", "/normal"]:
            return self.set_mode("yourai", source)
        
        # /admin - Wechsle User zu Admin (nicht Mode!)
        if text_lower == "/admin":
            return self.switch_user("admin", source)
        
        # /mode - Zeige aktuellen Mode
        if text_lower == "/mode":
            mode = self.get_mode(source)
            emoji = "😈" if mode == "altpersona" else "🌸"
            return f"{emoji} Aktueller Mode: {mode.upper()}"
        
        # /user <name> - Wechseln
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
    
    # Liste User
    print(session_manager.list_users())
    print()
    
    # Wechsel zu Gemini
    print(session_manager.switch_user("gemini"))
    print(f"Current: {session_manager.get_current_user()}")
    print(f"User ID: {session_manager.get_current_user_id()}")
    print()
    
    # Kontext für Prompt
    print("--- YOURAI CONTEXT ---")
    print(session_manager.get_user_context())
    
    # Zurück zu Admin
    print(session_manager.switch_user("admin"))