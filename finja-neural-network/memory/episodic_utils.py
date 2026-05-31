"""Pure helpers for YourAI's episodic diary."""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def get_week_id(dt: Optional[datetime] = None) -> str:
    """Get week identifier in format YYYY_WXX."""
    if dt is None:
        dt = datetime.now()
    year = dt.year
    week = dt.isocalendar()[1]
    return f"{year}_W{week:02d}"


def get_week_start_end(week_id: str) -> tuple[datetime, datetime]:
    """Get start and end datetime for a week ID."""
    year, week_str = week_id.split("_W")
    year = int(year)
    week = int(week_str)

    jan1 = datetime(year, 1, 1)
    days_to_monday = (7 - jan1.weekday()) % 7
    first_monday = jan1 + timedelta(days=days_to_monday)

    if jan1.weekday() <= 3:
        first_monday = jan1 - timedelta(days=jan1.weekday())

    week_start = first_monday + timedelta(weeks=week - 1)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return week_start, week_end


def compact_diary_content(content: str, max_chars: int = 900) -> str:
    """Create a prompt-safe preview while preserving the raw stored diary entry."""
    if not content:
        return ""
    if len(content) <= max_chars:
        return content

    text = content.strip()
    code_fence_count = text.count("```")
    looks_like_code = code_fence_count >= 2 or any(marker in text for marker in (
        "Traceback (most recent call last)",
        "SyntaxError:",
        "TypeError:",
        "ReferenceError:",
        "def ",
        "class ",
        "function ",
        "import ",
        "const ",
    ))

    if "ORIGINAL USER QUESTION:" in text:
        question = text.split("ORIGINAL USER QUESTION:")[-1].strip()
        return _middle_cut("ORIGINAL USER QUESTION: " + question, max_chars=max_chars)

    prefix = "[Code/Log preview] " if looks_like_code else ""
    return prefix + _middle_cut(text, max_chars=max_chars - len(prefix))


def _middle_cut(text: str, max_chars: int = 900, head_ratio: float = 0.62) -> str:
    if len(text) <= max_chars:
        return text
    marker = f"\n[... gekuerzt: {len(text) - max_chars} Zeichen ...]\n"
    available = max(120, max_chars - len(marker))
    head_len = max(80, int(available * head_ratio))
    tail_len = max(60, available - head_len)
    return text[:head_len].rstrip() + marker + text[-tail_len:].lstrip()


class DiaryEntry:
    """Represents a single diary entry."""

    def __init__(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        timestamp: Optional[float] = None,
        date_readable: Optional[str] = None,
        user_id: str = "",
        session_uuid: str = "",
    ):
        self.timestamp: float = timestamp if timestamp is not None else time.time()
        self.date_readable: str = date_readable if date_readable is not None else datetime.now().strftime("%Y-%m-%d %H:%M")
        self.content = content
        self.tags: List[str] = tags if tags is not None else []
        self.user_id: str = user_id
        self.session_uuid: str = session_uuid

    def to_dict(self) -> dict:
        data = {
            "timestamp": self.timestamp,
            "date_readable": self.date_readable,
            "content": self.content,
            "tags": self.tags,
            "user_id": self.user_id,
        }
        if self.session_uuid:
            data["session_uuid"] = self.session_uuid
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "DiaryEntry":
        return cls(
            content=data.get("content", ""),
            tags=data.get("tags"),
            timestamp=data.get("timestamp"),
            date_readable=data.get("date_readable"),
            user_id=data.get("user_id", ""),
            session_uuid=data.get("session_uuid", ""),
        )


def generate_week_summary(entries: List[dict], week_id: str) -> dict:
    """Generate a summary of the week's entries."""
    if not entries:
        return {
            "week_id": week_id,
            "total_entries": 0,
            "tags_frequency": {},
            "first_entry": None,
            "last_entry": None,
            "highlights": [],
        }

    tag_counts: Dict[str, int] = {}
    for entry in entries:
        for tag in entry.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    sorted_entries = sorted(entries, key=lambda x: x.get("timestamp", 0))
    highlights = sorted(entries, key=lambda x: len(x.get("content", "")), reverse=True)[:5]

    return {
        "week_id": week_id,
        "generated_at": datetime.now().isoformat(),
        "total_entries": len(entries),
        "tags_frequency": dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)),
        "first_entry": sorted_entries[0].get("date_readable") if sorted_entries else None,
        "last_entry": sorted_entries[-1].get("date_readable") if sorted_entries else None,
        "date_range": {
            "start": sorted_entries[0].get("date_readable") if sorted_entries else None,
            "end": sorted_entries[-1].get("date_readable") if sorted_entries else None,
        },
        "highlights": [
            {
                "date": h.get("date_readable"),
                "preview": h.get("content", "")[:100] + "..." if len(h.get("content", "")) > 100 else h.get("content", ""),
                "tags": h.get("tags", []),
            }
            for h in highlights
        ],
    }
