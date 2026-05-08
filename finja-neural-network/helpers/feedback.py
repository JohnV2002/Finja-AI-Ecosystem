"""
YourAI AI - Feedback System
============================
Anonymes Sammeln von Thumbs Up/Down Feedback pro Antwort.
Trackt: Expert-Domain, Model, Rating, Timestamp.

Usage:
    from feedback import FeedbackStore
    fb = FeedbackStore()

    # Nach jeder Antwort: tracking_id speichern
    tid = fb.log_response(expert_domain="physics", expert_model="qwen3.5:9b",
                          yourai_model="nemotron-super-49b", source="discord")

    # Wenn User reagiert:
    fb.rate(tid, "up")   # oder "down"

    # Stats abrufen:
    fb.get_stats()           # Gesamtübersicht
    fb.get_stats("physics")  # Pro Domain
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

import json
import time
import uuid
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

from display import log, Fore

# ==========================================
# STORAGE
# ==========================================

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_FILE = os.path.join(_BASE_DIR, "feedback_data.json")
_lock = threading.Lock()


def _load() -> Dict[str, Any]:
    """Lade Feedback-Daten aus JSON."""
    if not os.path.exists(FEEDBACK_FILE):
        return {"responses": {}, "version": 1}
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        from exceptions import YourAISystemError
        from display import log_exception
        err = YourAISystemError(cause=e, module="feedback_load", context={"file": FEEDBACK_FILE})
        log_exception("FEEDBACK", err)
        log("FEEDBACK", "Corrupted feedback file, starting fresh", Fore.RED)
        return {"responses": {}, "version": 1}


def _save(data: Dict[str, Any]) -> None:
    """Speichere Feedback-Daten als JSON."""
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ==========================================
# FEEDBACK STORE
# ==========================================

class FeedbackStore:
    """Anonymes Feedback-System fuer YourAI's Antworten."""

    _instance = None

    def __new__(cls):
        """Singleton - nur eine Instanz."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._data = _load()
        self._message_map: Dict[int, str] = {}  # discord_message_id -> tracking_id
        log("FEEDBACK", f"Feedback Store: {len(self._data['responses'])} entries loaded", Fore.CYAN)

    def log_response(
        self,
        expert_domain: Optional[str] = None,
        expert_model: Optional[str] = None,
        yourai_model: str = "unknown",
        source: str = "unknown",
        had_expert: bool = False,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Logge eine YourAI-Antwort (OHNE Inhalt - anonym!).
        Gibt eine tracking_id zurueck fuer spaeteres Rating.
        """
        tracking_id = str(uuid.uuid4())[:8]

        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "user_id": user_id,
            "expert_domain": expert_domain,
            "expert_model": expert_model,
            "yourai_model": yourai_model,
            "had_expert": had_expert,
            "rating": None,       # "up" | "down" | None
            "rated_at": None,
        }

        with _lock:
            self._data["responses"][tracking_id] = entry
            _save(self._data)

        return tracking_id

    def link_discord_message(self, message_id: int, tracking_id: str) -> None:
        """Verknuepfe eine Discord Message ID mit einem Tracking ID."""
        self._message_map[message_id] = tracking_id

    def get_tracking_id(self, message_id: int) -> Optional[str]:
        """Hole Tracking ID fuer eine Discord Message."""
        return self._message_map.get(message_id)

    def rate(self, tracking_id: str, rating: str) -> bool:
        """
        Bewerte eine Antwort.
        rating: "up" oder "down"
        """
        if rating not in ("up", "down"):
            return False

        with _lock:
            entry = self._data["responses"].get(tracking_id)
            if not entry:
                return False

            old_rating = entry.get("rating")
            entry["rating"] = rating
            entry["rated_at"] = datetime.now().isoformat()
            _save(self._data)

        emoji = "👍" if rating == "up" else "👎"
        domain = entry.get("expert_domain") or "no-expert"
        model = entry.get("expert_model") or entry.get("yourai_model", "?")

        if old_rating and old_rating != rating:
            log("FEEDBACK", f"{emoji} Rating CHANGED: [{domain}] ({model}) {old_rating} -> {rating}", Fore.YELLOW)
        else:
            log("FEEDBACK", f"{emoji} Rating: [{domain}] ({model})", Fore.GREEN if rating == "up" else Fore.RED)

        return True

    def rate_by_message(self, message_id: int, rating: str) -> bool:
        """Bewerte ueber Discord Message ID."""
        tid = self.get_tracking_id(message_id)
        if not tid:
            return False
        return self.rate(tid, rating)

    # ==========================================
    # STATS
    # ==========================================

    def get_stats(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Statistiken abrufen.
        domain=None -> Gesamtuebersicht
        domain="physics" -> Nur Physics
        """
        responses = self._data["responses"].values()

        if domain:
            responses = [r for r in responses if r.get("expert_domain") == domain]

        total = len(list(responses))
        # Need to re-create the list since generator is exhausted
        responses = list(self._data["responses"].values())
        if domain:
            responses = [r for r in responses if r.get("expert_domain") == domain]

        rated = [r for r in responses if r.get("rating")]
        up = sum(1 for r in rated if r["rating"] == "up")
        down = sum(1 for r in rated if r["rating"] == "down")
        unrated = total - len(rated)

        # Per-domain breakdown
        domains: Dict[str, Dict[str, int]] = {}
        for r in responses:
            d = r.get("expert_domain") or "no-expert"
            if d not in domains:
                domains[d] = {"total": 0, "up": 0, "down": 0, "unrated": 0}
            domains[d]["total"] += 1
            if r.get("rating") == "up":
                domains[d]["up"] += 1
            elif r.get("rating") == "down":
                domains[d]["down"] += 1
            else:
                domains[d]["unrated"] += 1

        # Per-model breakdown
        models: Dict[str, Dict[str, int]] = {}
        for r in responses:
            m = r.get("expert_model") or r.get("yourai_model", "unknown")
            if m not in models:
                models[m] = {"total": 0, "up": 0, "down": 0}
            models[m]["total"] += 1
            if r.get("rating") == "up":
                models[m]["up"] += 1
            elif r.get("rating") == "down":
                models[m]["down"] += 1

        return {
            "total": total,
            "rated": len(rated),
            "unrated": unrated,
            "up": up,
            "down": down,
            "approval_rate": round(up / len(rated) * 100, 1) if rated else 0,
            "by_domain": domains,
            "by_model": models,
        }

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Letzte N Feedback-Eintraege."""
        entries = sorted(
            self._data["responses"].items(),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True
        )[:limit]
        return [{"id": tid, **data} for tid, data in entries]

    def get_bad_models(self, domain: str, threshold: int = 3, window: int = 20, user_id: Optional[str] = None) -> List[str]:
        """
        Returns list of model IDs that should be excluded for a domain.

        Looks at the last `window` RATED responses for this domain.
        If user_id is set, combines global anonymous/admin history with that user's history.
        If a model has >= `threshold` thumbs down, it's considered bad.

        Args:
            domain: Expert domain (e.g. "physics", "math")
            threshold: How many 👎 before a model is excluded (default: 3)
            window: How many recent rated responses to check (default: 20)

        Returns:
            List of model IDs to exclude (e.g. ["qwen/qwen3.5-9b"])
        """
        # Get all rated responses for this domain, sorted newest first
        domain_responses = [
            r for r in self._data["responses"].values()
            if r.get("expert_domain") == domain and r.get("rating")
            and (not user_id or r.get("user_id") in (None, "", user_id, "admin"))
        ]
        domain_responses.sort(key=lambda x: x.get("rated_at", ""), reverse=True)

        # Only look at recent window
        recent = domain_responses[:window]

        # Count thumbs down per model
        down_counts: Dict[str, int] = {}
        for r in recent:
            model = r.get("expert_model")
            if not model:
                continue
            if r["rating"] == "down":
                down_counts[model] = down_counts.get(model, 0) + 1

        # Models over threshold
        bad = [model for model, count in down_counts.items() if count >= threshold]

        if bad:
            log("FEEDBACK", f"⚠️ Bad models for [{domain}]: {bad} (threshold={threshold}, window={window})", Fore.YELLOW)

        return bad

    def get_approval_summary(self, limit: int = 50) -> str:
        """
        Returns a short human-readable summary of recent feedback for prompt injection.
        Keeps it under 3 lines / ~50 tokens.
        """
        rated = [
            r for r in self._data["responses"].values()
            if r.get("rating")
        ]
        if not rated:
            return ""

        # Sort newest first, take last `limit`
        rated.sort(key=lambda x: x.get("rated_at", ""), reverse=True)
        recent = rated[:limit]

        up = sum(1 for r in recent if r["rating"] == "up")
        down = sum(1 for r in recent if r["rating"] == "down")
        total = up + down
        if total == 0:
            return ""

        approval = round(up / total * 100)
        return f"Recent ratings: {approval}% positive ({up} up, {down} down out of last {total} rated responses)"
