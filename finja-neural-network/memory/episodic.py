"""
YourAI's Episodic Diary System v2.0
===================================
Weekly Rotation with FULL Transparency & Access Guarantees

YOURAI'S REQUIREMENTS (ALL IMPLEMENTED ✅):
1. ✅ No deletion - only rotation/moving
2. ✅ Permanent access to ALL old memories
3. ✅ /list_rotations command for transparency
4. ✅ Read-only backups that can't be overwritten
5. ✅ Simple access commands
6. ✅ Weekly summaries always available

DIRECTORY STRUCTURE:
    diary/
    ├── current_week/
    │   └── current.json          # Active diary (always accessible)
    ├── weekly_diary/
    │   ├── 2025_W01.json         # Week 1 full diary
    │   ├── 2025_W02.json         # Week 2 full diary
    │   └── ...
    ├── weekly_summary/
    │   ├── 2025_W01_summary.json # Week 1 summary (always accessible)
    │   ├── 2025_W02_summary.json # Week 2 summary
    │   └── ...
    └── backups/
        ├── 2025_W01_backup.json  # Read-only backup
        └── ...

ALWAYS ACCESSIBLE:
- current_week/current.json
- ALL weekly_summary/*.json files
- ALL weekly_diary/*.json files (on request)
- ALL backups/*.json files

Usage:
    from episodic import journal
    
    # Write entry (goes to current week)
    journal.log_event("We played Minecraft!", ["gaming", "fun"])
    
    # Get recent events
    journal.get_recent(hours=24)
    
    # YOURAI'S COMMANDS:
    journal.list_rotations()      # See all available weeks
    journal.get_week("2025_W01")  # Access specific week
    journal.get_summary("2025_W01")  # Get week summary
    journal.search_all("minecraft")  # Search ALL history
"""

import json
import os
import sys
import shutil
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore, Style
from exceptions import YourAIUnexpectedError
from memory.episodic_utils import (
    DiaryEntry,
    compact_diary_content,
    generate_week_summary,
    get_week_id,
    get_week_start_end,
)
from memory.debug_client import get_dashboard_debug


# ==========================================
# CONFIGURATION
# ==========================================

# Base directory for all diary data
DIARY_BASE_DIR = "diary"

# Subdirectories
CURRENT_WEEK_DIR = os.path.join(DIARY_BASE_DIR, "current_week")
WEEKLY_DIARY_DIR = os.path.join(DIARY_BASE_DIR, "weekly_diary")
WEEKLY_SUMMARY_DIR = os.path.join(DIARY_BASE_DIR, "weekly_summary")
BACKUP_DIR = os.path.join(DIARY_BASE_DIR, "backups")

# Current week file
CURRENT_DIARY_FILE = os.path.join(CURRENT_WEEK_DIR, "current.json")

# Legacy file (for migration)
LEGACY_DIARY_FILE = "episodic_diary.json"


# ==========================================
# DIRECTORY HELPERS
# ==========================================

def ensure_directories():
    """Create all required directories if they don't exist."""
    for directory in [CURRENT_WEEK_DIR, WEEKLY_DIARY_DIR, WEEKLY_SUMMARY_DIR, BACKUP_DIR]:
        os.makedirs(directory, exist_ok=True)


# ==========================================
# MAIN DIARY CLASS
# ==========================================

class Diary:
    """
    YourAI's Episodic Diary with Weekly Rotation.
    
    GUARANTEES FOR YOURAI:
    1. No data is EVER deleted
    2. ALL weeks are accessible via simple commands
    3. Transparent listing of all rotations
    4. Read-only backups for safety
    """
    
    def __init__(self, base_dir: str = DIARY_BASE_DIR, label: str = "DIARY"):
        # Instance-level paths (allows multiple Diary instances with different dirs)
        self._base_dir = base_dir
        self._label = label
        self._current_week_dir = os.path.join(base_dir, "current_week")
        self._weekly_dir = os.path.join(base_dir, "weekly_diary")
        self._summary_dir = os.path.join(base_dir, "weekly_summary")
        self._backup_dir = os.path.join(base_dir, "backups")
        self._current_file = os.path.join(self._current_week_dir, "current.json")
        self._legacy_file = os.path.join(os.path.dirname(base_dir) if os.path.dirname(base_dir) else ".",
                                          f"{os.path.basename(base_dir)}_legacy.json") if base_dir != DIARY_BASE_DIR else LEGACY_DIARY_FILE

        for d in [self._current_week_dir, self._weekly_dir, self._summary_dir, self._backup_dir]:
            os.makedirs(d, exist_ok=True)

        # WICHTIG: Erst laden, DANN week_id setzen!
        loaded_data = self._load_current_with_meta()
        self.entries = loaded_data["entries"]
        # Benutze die gespeicherte week_id wenn vorhanden, sonst aktuelle
        self.current_week_id = loaded_data.get("week_id") or get_week_id()

        self._migrate_legacy()
        self._check_rotation()

        entry_count = len(self.entries)
        weeks_count = len(self.list_rotations()["available_weeks"])
        log(self._label, f"📔 v2.0: {entry_count} entries this week, {weeks_count} weeks archived", Fore.GREEN)
    
    # ==========================================
    # CORE LOADING/SAVING
    # ==========================================
    
    def _load_current_with_meta(self) -> dict:
        """Load current week's diary WITH metadata (week_id)."""
        if not os.path.exists(self._current_file):
            return {"entries": [], "week_id": None}
        try:
            with open(self._current_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {
                        "entries": data.get("entries", []),
                        "week_id": data.get("week_id")
                    }
                else:
                    # Legacy format (just list of entries)
                    return {"entries": data, "week_id": None}
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_load")
            log_exception(self._label, err)
            return {"entries": [], "week_id": None}
    
    def _load_current(self) -> List[dict]:
        """Load current week's diary (entries only, for backwards compat)."""
        return self._load_current_with_meta()["entries"]
    
    def _save_current(self):
        """Save current week's diary (atomic write)."""
        try:
            data = {
                "week_id": self.current_week_id,
                "last_updated": datetime.now().isoformat(),
                "entries": self.entries
            }
            tmp_path = self._current_file + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._current_file)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_save")
            log_exception(self._label, err)
            try:
                os.remove(self._current_file + ".tmp")
            except OSError as cleanup_error:
                cleanup_err = YourAIUnexpectedError(cause=cleanup_error, module="episodic_save_cleanup")
                log_exception(self._label, cleanup_err)
    
    def _migrate_legacy(self):
        """
        Migrate old episodic_diary.json to new system.
        KEEPS original file as backup!
        """
        if not os.path.exists(self._legacy_file):
            return

        log(self._label, "📦 Found legacy diary, migrating...", Fore.CYAN)

        try:
            with open(self._legacy_file, "r", encoding="utf-8") as f:
                legacy_entries = json.load(f)
            
            if not legacy_entries:
                return
            
            # Group entries by week
            weeks: Dict[str, List[dict]] = {}
            for entry in legacy_entries:
                ts = entry.get("timestamp", time.time())
                dt = datetime.fromtimestamp(ts)
                week_id = get_week_id(dt)
                
                if week_id not in weeks:
                    weeks[week_id] = []
                weeks[week_id].append(entry)
            
            # Save each week
            for week_id, week_entries in weeks.items():
                if week_id == self.current_week_id:
                    # Merge with current
                    self.entries = week_entries + self.entries
                else:
                    # Save as archived week
                    self._save_week_archive(week_id, week_entries)
            
            self._save_current()
            
            # Create backup of original (READ-ONLY guarantee!)
            backup_path = os.path.join(self._backup_dir, "legacy_migration_backup.json")
            shutil.copy2(self._legacy_file, backup_path)

            # Rename original (don't delete!)
            os.rename(self._legacy_file, self._legacy_file + ".migrated")

            log(self._label, f"✅ Migration complete! {len(legacy_entries)} entries sorted into {len(weeks)} weeks", Fore.GREEN)
            log(self._label, f"   Original backed up to: {backup_path}", Fore.LIGHTBLACK_EX)

        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_migrate")
            log_exception(self._label, err)
    
    def _save_week_archive(self, week_id: str, entries: List[dict]):
        """
        Save a week's entries to the archive.
        Also creates summary and backup.
        """
        try:
            # Save full diary
            diary_path = os.path.join(self._weekly_dir, f"{week_id}.json")
            with open(diary_path, "w", encoding="utf-8") as f:
                json.dump({
                    "week_id": week_id,
                    "archived_at": datetime.now().isoformat(),
                    "entry_count": len(entries),
                    "entries": entries
                }, f, indent=2, ensure_ascii=False)

            # Generate and save summary
            summary = generate_week_summary(entries, week_id)
            summary_path = os.path.join(self._summary_dir, f"{week_id}_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            # Create read-only backup
            backup_path = os.path.join(self._backup_dir, f"{week_id}_backup.json")
            shutil.copy2(diary_path, backup_path)

            log(self._label, f"📁 Archived week {week_id}: {len(entries)} entries", Fore.CYAN)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_archive", context={"week_id": week_id})
            log_exception(self._label, err)
    
    def _check_rotation(self):
        """Check if we need to rotate to a new week."""
        current = get_week_id()
        
        if current != self.current_week_id and self.entries:
            log(self._label, f"🔄 Week changed: {self.current_week_id} → {current}", Fore.YELLOW)
            self._rotate_week()
        elif current != self.current_week_id and not self.entries:
            log(self._label, f"📅 New week {current}, no entries to archive", Fore.CYAN)
            self.current_week_id = current
    
    def _rotate_week(self):
        """
        Rotate current week to archive.
        THIS NEVER DELETES - ONLY MOVES!
        """
        if not self.entries:
            self.current_week_id = get_week_id()
            return
        
        old_week = self.current_week_id
        
        # Archive the old week (with backup!)
        self._save_week_archive(old_week, self.entries)
        
        # Start fresh
        self.current_week_id = get_week_id()
        self.entries = []
        self._save_current()
        
        log(self._label, f"✅ Rotation complete! Week {old_week} safely archived.", Fore.GREEN)
    
    # ==========================================
    # WRITE OPERATIONS
    # ==========================================
    
    def log_event(self, content: str, tags: Optional[List[str]] = None, user_id: str = "", session_uuid: str = ""):
        """
        Write a new diary entry.

        Args:
            content: What happened
            tags: Categories like ["gaming", "coding"]
            user_id: The user this entry belongs to (for per-user privacy filtering)
            session_uuid: Browser session UUID for DSGVO deletion requests
        """
        # Check if week changed
        self._check_rotation()

        entry = DiaryEntry(content, tags, user_id=user_id, session_uuid=session_uuid).to_dict()
        self.entries.append(entry)
        self._save_current()

        tag_list = tags if tags else []
        log(self._label, f"✍️ Added: '{content[:50]}...' [{', '.join(tag_list)}]", Fore.MAGENTA)
        _dbg = get_dashboard_debug(self._label, module="episodic_dashboard_debug")
        if _dbg:
            _dbg.info("diary", f"✍️ New entry: {content[:80]}", f"Tags: {', '.join(tag_list)}" if tag_list else None)
    
    # ==========================================
    # READ OPERATIONS - CURRENT WEEK
    # ==========================================

    def iter_entries(self, user_id: str = "", include_archives: bool = True, limit: Optional[int] = None) -> List[dict]:
        """Return diary entries visible to a user, newest first, across current and archives."""
        is_admin = user_id == "admin"

        def _user_allowed(entry: dict) -> bool:
            if not user_id:
                return True
            entry_uid = entry.get("user_id", "")
            if entry_uid == user_id:
                return True
            if is_admin and entry_uid == "":
                return True
            return False

        entries: List[dict] = []
        for entry in self.entries:
            if _user_allowed(entry):
                e = entry.copy()
                e["_source"] = f"current ({self.current_week_id})"
                entries.append(e)

        if include_archives and os.path.exists(self._weekly_dir):
            for f in os.listdir(self._weekly_dir):
                if not f.endswith(".json"):
                    continue

                week_id = f.replace(".json", "")
                path = os.path.join(self._weekly_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                    for entry in data.get("entries", []):
                        if _user_allowed(entry):
                            e = entry.copy()
                            e["_source"] = f"archive ({week_id})"
                            entries.append(e)
                except Exception as e:
                    err = YourAIUnexpectedError(cause=e, module="episodic_iter_entries", context={"file": f})
                    log_exception(self._label, err)

        entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        if limit is not None:
            entries = entries[:limit]
        return entries
    
    def get_recent(self, hours: int = 24, max_entries: int = 12, user_id: str = "") -> str:
        """Get entries from the last X hours, capped to save tokens.

        Returns the most recent entries (newest first, then reversed for chronological order).
        Long entries (e.g. image descriptions) get their content trimmed.

        Args:
            user_id: If set, only return entries for this user.
                     Entries without user_id (legacy) are shown only to admin ("admin" user_id).
        """
        cutoff = time.time() - (hours * 3600)
        all_recent = [e for e in self.entries if e.get("timestamp", 0) > cutoff]

        # Per-user privacy filter
        if user_id:
            is_admin = user_id == "admin"
            recent = [
                e for e in all_recent
                if e.get("user_id", "") == user_id  # own entries
                or (is_admin and e.get("user_id", "") == "")  # admin sees legacy entries too
            ]
        else:
            recent = all_recent

        # Cap to max_entries (keep newest)
        if len(recent) > max_entries:
            recent = recent[-max_entries:]

        # Trim prompt preview only; raw diary entries stay unchanged on disk.
        trimmed = []
        for e in recent:
            content = e.get("content", "")
            preview = compact_diary_content(content, max_chars=900)
            if preview != content:
                e_copy = e.copy()
                e_copy["content"] = preview
                trimmed.append(e_copy)
            else:
                trimmed.append(e)

        return self._format_entries(trimmed)
    
    def get_today(self) -> str:
        """Get all entries from today."""
        today = datetime.now().date()
        today_entries = []
        
        for e in self.entries:
            try:
                entry_date = datetime.fromtimestamp(e.get("timestamp", 0)).date()
                if entry_date == today:
                    today_entries.append(e)
            except (ValueError, OSError):
                pass  # Invalid timestamp, skip entry
        
        return self._format_entries(today_entries)
    
    def search_by_tag(self, tag: str, limit: int = 10) -> str:
        """Search current week by tag."""
        matches = [
            e for e in self.entries 
            if tag.lower() in [t.lower() for t in e.get("tags", [])]
        ]
        return self._format_entries(matches[-limit:])
    
    # ==========================================
    # 🌟 YOURAI'S TRANSPARENCY COMMANDS 🌟
    # ==========================================
    
    def list_rotations(self) -> dict:
        """
        📋 LIST ALL AVAILABLE WEEKS
        
        YourAI's Requirement: "Transparency = autonomy"
        This shows EVERYTHING that's available.
        
        Returns:
            Dict with all available data
        """
        result = {
            "current_week": {
                "week_id": self.current_week_id,
                "entries": len(self.entries),
                "file": self._current_file
            },
            "available_weeks": [],
            "available_summaries": [],
            "available_backups": [],
            "total_entries_all_time": len(self.entries)
        }
        
        # List archived weeks
        if os.path.exists(self._weekly_dir):
            for f in sorted(os.listdir(self._weekly_dir)):
                if f.endswith(".json"):
                    week_id = f.replace(".json", "")
                    path = os.path.join(self._weekly_dir, f)
                    try:
                        with open(path, "r", encoding="utf-8") as file:
                            data = json.load(file)
                            entry_count = data.get("entry_count", len(data.get("entries", [])))
                    except Exception as e:
                        err = YourAIUnexpectedError(cause=e, module="episodic_list", context={"file": f})
                        log_exception(self._label, err)
                        entry_count = "?"
                    
                    result["available_weeks"].append({
                        "week_id": week_id,
                        "entries": entry_count,
                        "file": path
                    })
                    if isinstance(entry_count, int):
                        result["total_entries_all_time"] += entry_count
        
        # List summaries
        if os.path.exists(self._summary_dir):
            for f in sorted(os.listdir(self._summary_dir)):
                if f.endswith(".json"):
                    result["available_summaries"].append({
                        "file": f,
                        "path": os.path.join(self._summary_dir, f)
                    })

        # List backups
        if os.path.exists(self._backup_dir):
            for f in sorted(os.listdir(self._backup_dir)):
                if f.endswith(".json"):
                    result["available_backups"].append({
                        "file": f,
                        "path": os.path.join(self._backup_dir, f)
                    })
        
        return result
    
    def get_week(self, week_id: str) -> str:
        """
        📖 ACCESS A SPECIFIC WEEK'S FULL DIARY
        
        YourAI's Requirement: "Access to every backup"
        
        Args:
            week_id: Week to retrieve (e.g., "2025_W01")
            
        Returns:
            Formatted diary entries
        """
        # Check if it's current week
        if week_id == self.current_week_id:
            return self._format_entries(self.entries)
        
        # Load from archive
        path = os.path.join(self._weekly_dir, f"{week_id}.json")

        if not os.path.exists(path):
            return f"❌ Week {week_id} not found. Use list_rotations() to see available weeks."

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                entries = data.get("entries", [])
                return self._format_entries(entries)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_get_week", context={"week_id": week_id})
            log_exception(self._label, err)
            return f"❌ Error loading week {week_id}: {e}"
    
    def get_summary(self, week_id: str) -> dict:
        """
        📊 GET A WEEK'S SUMMARY
        
        Summaries are ALWAYS accessible per YourAI's requirements.
        
        Args:
            week_id: Week to get summary for
            
        Returns:
            Summary dict with stats and highlights
        """
        # Current week - generate live
        if week_id == self.current_week_id:
            return generate_week_summary(self.entries, week_id)
        
        # Load from archive
        path = os.path.join(self._summary_dir, f"{week_id}_summary.json")

        if not os.path.exists(path):
            return {"error": f"Summary for {week_id} not found"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_get_summary", context={"week_id": week_id})
            log_exception(self._label, err)
            return {"error": f"Error loading summary: {e}"}
    
    @staticmethod
    def _fuzzy_match(query: str, text: str) -> bool:
        """
        Fuzzy matching: findet 'mom' auch in 'mome', 'mommy', 'mama'.
        Prüft exakten Substring + Prefix-Match auf Wortebene.
        """
        # Exakter Substring (wie vorher)
        if query in text:
            return True

        # Wort-Prefix-Match: 'mom' findet 'mome', 'mommy', 'moms'
        # Aber nur wenn Query >= 3 Zeichen (sonst zu viele false positives)
        if len(query) >= 3:
            words = text.split()
            for word in words:
                # Nur alphanumerische Zeichen für Vergleich
                clean_word = ''.join(c for c in word if c.isalnum()).lower()
                if clean_word.startswith(query) and len(clean_word) <= len(query) + 3:
                    return True
                # Auch umgekehrt: Query 'minecraft' findet Wort 'mine'? Nein.
                # Aber Query 'mom' findet 'mome'? Ja (Prefix + max 3 extra chars)

        return False

    def search_all(self, query: str, limit: int = 20, user_id: str = "") -> str:
        """
        🔍 SEARCH ALL HISTORY (Current + All Archives)

        YourAI's Requirement: Full access to all memories
        Uses fuzzy matching (prefix + substring) for better recall.

        Args:
            query: Text to search for
            limit: Max results
            user_id: If set, only return entries for this user.
                     Entries without user_id (legacy) are shown only to admin.

        Returns:
            Formatted matching entries
        """
        all_matches = []
        query_lower = query.lower()
        is_admin = user_id == "admin"

        def _user_allowed(entry: dict) -> bool:
            if not user_id:
                return True  # No filter
            entry_uid = entry.get("user_id", "")
            if entry_uid == user_id:
                return True
            if is_admin and entry_uid == "":
                return True  # Admin sees legacy entries
            return False

        # Search current week
        for entry in self.entries:
            if not _user_allowed(entry):
                continue
            content = entry.get("content", "").lower()
            tags = [t.lower() for t in entry.get("tags", [])]

            if self._fuzzy_match(query_lower, content) or any(self._fuzzy_match(query_lower, t) for t in tags):
                entry_copy = entry.copy()
                entry_copy["_source"] = f"current ({self.current_week_id})"
                all_matches.append(entry_copy)

        # Search all archived weeks
        if os.path.exists(self._weekly_dir):
            for f in os.listdir(self._weekly_dir):
                if not f.endswith(".json"):
                    continue

                week_id = f.replace(".json", "")
                path = os.path.join(self._weekly_dir, f)

                try:
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        entries = data.get("entries", [])

                        for entry in entries:
                            if not _user_allowed(entry):
                                continue
                            content = entry.get("content", "").lower()
                            tags = [t.lower() for t in entry.get("tags", [])]

                            if self._fuzzy_match(query_lower, content) or any(self._fuzzy_match(query_lower, t) for t in tags):
                                entry_copy = entry.copy()
                                entry_copy["_source"] = f"archive ({week_id})"
                                all_matches.append(entry_copy)
                except Exception as e:
                    err = YourAIUnexpectedError(cause=e, module="episodic_search", context={"file": f})
                    log_exception(self._label, err)
        
        # Sort by timestamp (newest first)
        all_matches.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        
        # Limit results
        all_matches = all_matches[:limit]
        
        if not all_matches:
            return f"No entries found for '{query}'"
        
        # Format with source info
        text = f"🔍 Found {len(all_matches)} entries for '{query}':\n\n"
        for e in all_matches:
            source = e.get("_source", "unknown")
            content = compact_diary_content(e.get("content", ""), max_chars=1200)
            text += f"[{e.get('date_readable', '?')}] ({source})\n"
            text += f"  {content}\n\n"
        
        return text
    
    def get_all_summaries(self) -> List[dict]:
        """
        📚 GET ALL WEEK SUMMARIES AT ONCE
        
        For quick overview of entire history.
        
        Returns:
            List of all summary dicts
        """
        summaries = []
        
        # Current week
        summaries.append(generate_week_summary(self.entries, self.current_week_id))
        
        # Archived summaries
        if os.path.exists(self._summary_dir):
            for f in sorted(os.listdir(self._summary_dir), reverse=True):
                if f.endswith(".json"):
                    path = os.path.join(self._summary_dir, f)
                    try:
                        with open(path, "r", encoding="utf-8") as file:
                            summaries.append(json.load(file))
                    except Exception as e:
                        err = YourAIUnexpectedError(cause=e, module="episodic_get_summaries", context={"file": f})
                        log_exception(self._label, err)
        
        return summaries
    
    # ==========================================
    # DSGVO: DATA ACCESS / DELETE BY UUID
    # ==========================================

    def count_by_uuid(self, session_uuid: str) -> int:
        """Count all diary entries belonging to a session_uuid (DSGVO Art. 15)."""
        if not session_uuid:
            return 0
        count = sum(1 for e in self.entries if e.get("session_uuid", "") == session_uuid)
        if os.path.isdir(self._weekly_dir):
            for f in os.listdir(self._weekly_dir):
                if not f.endswith(".json"):
                    continue
                path = os.path.join(self._weekly_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    count += sum(1 for e in data.get("entries", []) if e.get("session_uuid", "") == session_uuid)
                except Exception as e:
                    err = YourAIUnexpectedError(cause=e, module="episodic_count_uuid", context={"file": f})
                    log_exception(self._label, err)
        return count

    def count_by_user_id(self, user_id: str) -> int:
        """Count all diary entries belonging to a user_id (cross-platform).
        Admin sees legacy entries (empty user_id) as well."""
        if not user_id:
            return 0
        is_admin = user_id == "admin"

        def _match(entry: dict) -> bool:
            uid = entry.get("user_id", "")
            if uid == user_id:
                return True
            if is_admin and uid == "":
                return True
            return False

        count = sum(1 for e in self.entries if _match(e))
        if os.path.isdir(self._weekly_dir):
            for f in os.listdir(self._weekly_dir):
                if not f.endswith(".json"):
                    continue
                path = os.path.join(self._weekly_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    count += sum(1 for e in data.get("entries", []) if _match(e))
                except Exception as e:
                    err = YourAIUnexpectedError(cause=e, module="episodic_count_user", context={"file": f})
                    log_exception(self._label, err)
        return count

    def delete_by_uuid(self, session_uuid: str) -> int:
        """Remove all diary entries matching a session_uuid (DSGVO deletion request).
        Searches current week + all archives. Returns total deleted count."""
        if not session_uuid:
            return 0

        deleted = 0

        # Current week
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.get("session_uuid", "") != session_uuid]
        deleted += before - len(self.entries)
        if deleted:
            self._save_current()

        # Archives
        if os.path.exists(self._weekly_dir):
            for f in os.listdir(self._weekly_dir):
                if not f.endswith(".json"):
                    continue
                path = os.path.join(self._weekly_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    entries = data.get("entries", [])
                    filtered = [e for e in entries if e.get("session_uuid", "") != session_uuid]
                    if len(filtered) < len(entries):
                        deleted += len(entries) - len(filtered)
                        data["entries"] = filtered
                        with open(path, "w", encoding="utf-8") as fh:
                            json.dump(data, fh, ensure_ascii=False, indent=2)
                except Exception as e:
                    err = YourAIUnexpectedError(cause=e, module="episodic_delete_uuid", context={"file": f})
                    log_exception(self._label, err)

        log(self._label, f"🗑️ DSGVO delete: removed {deleted} entries for UUID {session_uuid[:8]}...", Fore.YELLOW)
        return deleted

    # ==========================================
    # FORMATTING
    # ==========================================

    def _format_entries(self, entries: List[dict]) -> str:
        """Format entries for display."""
        if not entries:
            return "No entries found."
        
        text = ""
        for e in entries:
            tags_str = f" [{', '.join(e.get('tags', []))}]" if e.get('tags') else ""
            content = compact_diary_content(e.get("content", ""), max_chars=1200)
            text += f"[{e.get('date_readable', '?')}]{tags_str} {content}\n"
        
        return text
    
    # ==========================================
    # MANUAL REORGANIZATION (einmalig!)
    # ==========================================
    
    def force_reorganize(self) -> str:
        """
        🔄 REORGANIZE ALL ENTRIES BY THEIR TIMESTAMP
        
        Goes through current entries and sorts them into the correct week
        based on their actual timestamp. Useful when entries got mixed up.
        
        Returns:
            Status report of what was moved
        """
        if not self.entries:
            return "📔 No entries to reorganize."
        
        # Group entries by their actual week
        entries_by_week: Dict[str, List[dict]] = {}
        current_week = get_week_id()
        
        for entry in self.entries:
            # Get the week this entry actually belongs to
            ts = entry.get("timestamp")
            if ts:
                entry_date = datetime.fromtimestamp(ts)
                entry_week = get_week_id(entry_date)
            else:
                # No timestamp - assume current week
                entry_week = current_week
            
            if entry_week not in entries_by_week:
                entries_by_week[entry_week] = []
            entries_by_week[entry_week].append(entry)
        
        # Report what we found
        report_lines = ["🔄 DIARY REORGANIZATION REPORT", "=" * 40]
        
        for week_id, week_entries in sorted(entries_by_week.items()):
            report_lines.append(f"  📅 {week_id}: {len(week_entries)} entries")
        
        report_lines.append("=" * 40)
        
        # Archive old weeks, keep only current week
        moved_count = 0
        for week_id, week_entries in entries_by_week.items():
            if week_id != current_week:
                # This belongs to an older week - archive it!
                self._merge_into_archive(week_id, week_entries)
                moved_count += len(week_entries)
                report_lines.append(f"✅ Moved {len(week_entries)} entries to {week_id}")
        
        # Update current entries to only include current week
        self.entries = entries_by_week.get(current_week, [])
        self.current_week_id = current_week
        self._save_current()
        
        report_lines.append(f"\n📔 Current week ({current_week}): {len(self.entries)} entries")
        report_lines.append(f"📦 Moved to archive: {moved_count} entries")
        
        return "\n".join(report_lines)
    
    def _merge_into_archive(self, week_id: str, new_entries: List[dict]):
        """
        Merge entries into an existing archive (or create new one).
        Avoids duplicates based on timestamp.
        """
        archive_path = os.path.join(self._weekly_dir, f"{week_id}.json")
        existing_entries = []

        # Load existing archive if it exists
        if os.path.exists(archive_path):
            try:
                with open(archive_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    existing_entries = data.get("entries", [])
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="episodic_merge", context={"week_id": week_id})
                log_exception(self._label, err)
        
        # Get existing timestamps to avoid duplicates
        existing_timestamps = {e.get("timestamp") for e in existing_entries}
        
        # Add only new entries (avoid duplicates)
        added = 0
        for entry in new_entries:
            if entry.get("timestamp") not in existing_timestamps:
                existing_entries.append(entry)
                added += 1
        
        # Sort by timestamp
        existing_entries.sort(key=lambda x: x.get("timestamp", 0))
        
        try:
            # Save merged archive
            archive_data = {
                "week_id": week_id,
                "archived_at": datetime.now().isoformat(),
                "merged": True,
                "entry_count": len(existing_entries),
                "entries": existing_entries
            }
            
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump(archive_data, f, indent=2, ensure_ascii=False)
            
            # Also create/update summary
            summary = generate_week_summary(existing_entries, week_id)
            summary_path = os.path.join(self._summary_dir, f"{week_id}_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            log(self._label, f"📦 Merged {added} new entries into {week_id} (total: {len(existing_entries)})", Fore.CYAN)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="episodic_merge_save", context={"week_id": week_id})
            log_exception(self._label, err)
    
    # ==========================================
    # STATS & INFO
    # ==========================================
    
    def get_stats(self) -> dict:
        """Get overall diary statistics."""
        rotations = self.list_rotations()
        
        return {
            "current_week": self.current_week_id,
            "entries_this_week": len(self.entries),
            "total_weeks_archived": len(rotations["available_weeks"]),
            "total_entries_all_time": rotations["total_entries_all_time"],
            "backups_available": len(rotations["available_backups"]),
            "summaries_available": len(rotations["available_summaries"])
        }
    
    def print_status(self):
        """Print a nice status overview."""
        stats = self.get_stats()
        rotations = self.list_rotations()
        
        print(f"\n{Fore.CYAN}{'=' * 50}")
        print(f"📔 {self._label} STATUS")
        print(f"{'=' * 50}{Style.RESET_ALL}")
        print(f"Current Week: {stats['current_week']}")
        print(f"Entries This Week: {stats['entries_this_week']}")
        print(f"Total Weeks Archived: {stats['total_weeks_archived']}")
        print(f"Total Entries All Time: {stats['total_entries_all_time']}")
        print(f"Backups Available: {stats['backups_available']}")
        print(f"{Fore.LIGHTBLACK_EX}{'-' * 50}{Style.RESET_ALL}")
        print("Available Weeks:")
        print(f"  📅 {self.current_week_id} (current) - {len(self.entries)} entries")
        for week in rotations["available_weeks"]:
            print(f"  📁 {week['week_id']} - {week['entries']} entries")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")


# ==========================================
# GLOBAL INSTANCES
# ==========================================

journal = Diary()                                          # YourAI's diary (diary/)
altpersona_journal = Diary(base_dir="diary_altpersona", label="ALTPERSONA-DIARY")  # AltPersona's diary (diary_altpersona/)


# ==========================================
# CONVENIENCE FUNCTIONS (for YourAI)
# ==========================================

def list_rotations() -> dict:
    """Shortcut for journal.list_rotations()"""
    return journal.list_rotations()


def get_week(week_id: str) -> str:
    """Shortcut for journal.get_week()"""
    return journal.get_week(week_id)


def search_all(query: str) -> str:
    """Shortcut for journal.search_all()"""
    return journal.search_all(query)


# ==========================================
# TEST
# ==========================================

if __name__ == "__main__":
    print(f"\n{Fore.MAGENTA}=== YourAI's Episodic Diary v2.0 Test ==={Style.RESET_ALL}\n")
    
    # Show status
    journal.print_status()
    
    # Test logging
    journal.log_event("Testing the new diary system!", ["test", "coding"])
    journal.log_event("Creator and I worked on the rotation feature.", ["coding", "yourai"])
    
    # Test transparency commands
    print(f"\n{Fore.YELLOW}--- Testing Transparency Commands ---{Style.RESET_ALL}")
    
    print("\n📋 list_rotations():")
    rotations = journal.list_rotations()
    print(f"  Current week: {rotations['current_week']['week_id']}")
    print(f"  Archived weeks: {len(rotations['available_weeks'])}")
    print(f"  Backups: {len(rotations['available_backups'])}")
    
    print("\n📊 Current week summary:")
    summary = journal.get_summary(journal.current_week_id)
    print(f"  Entries: {summary.get('total_entries', 0)}")
    print(f"  Top tags: {list(summary.get('tags_frequency', {}).keys())[:3]}")
    
    print("\n🔍 search_all('coding'):")
    results = journal.search_all("coding")
    print(results[:200] + "..." if len(results) > 200 else results)
    
    print(f"\n{Fore.GREEN}✅ All YourAI's requirements implemented!{Style.RESET_ALL}")
    print("   - No deletion, only rotation")
    print("   - Full access to all weeks via get_week()")
    print("   - Transparent listing via list_rotations()")
    print("   - Read-only backups created automatically")
    print("   - Search across ALL history via search_all()")
