"""
YourAI Error Inbox Helpers
=========================
Stores, deduplicates, and formats recent runtime errors.

Main Responsibilities:
- Build normalized error records.
- Persist and trim the error inbox.
- Expose unseen error summaries for notifications.

Side Effects:
- Reads and writes the local error inbox JSON file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime
from typing import Any


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "docker_data")
ERROR_INBOX_FILE = os.path.join(_DATA_DIR, "error_inbox.json")
_MAX_RECORDS = 300
_LOCK = threading.Lock()


def _now() -> str:
    """Handle now helper behavior."""
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: object, limit: int = 500) -> str:
    """Handle clean helper behavior."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _load() -> dict[str, Any]:
    """Handle load helper behavior."""
    if not os.path.exists(ERROR_INBOX_FILE):
        return {"version": 1, "errors": []}
    try:
        with open(ERROR_INBOX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": 1, "errors": []}
    if isinstance(data, list):
        return {"version": 1, "errors": data}
    if not isinstance(data, dict):
        return {"version": 1, "errors": []}
    data.setdefault("version", 1)
    if not isinstance(data.get("errors"), list):
        data["errors"] = []
    return data


def _save(data: dict[str, Any]) -> None:
    """Handle save helper behavior."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    data["updated_at"] = _now()
    tmp_file = ERROR_INBOX_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, ERROR_INBOX_FILE)


def _error_parts(category: str, error: Exception, context: str | None = None) -> dict[str, str]:
    """Handle error parts helper behavior."""
    cause = getattr(error, "cause", None)
    code = _clean(getattr(error, "code", "") or "")
    module = _clean(getattr(error, "module", "") or category.lower(), 80)
    error_type = type(error).__name__
    cause_text = ""
    cause_type = ""
    if cause:
        cause_type = type(cause).__name__
        cause_text = _clean(f"{cause_type}: {cause}", 300)

    if hasattr(error, "short"):
        try:
            short = _clean(error.short(), 350)
        except Exception:
            short = _clean(str(error), 350)
    else:
        short = _clean(str(error), 350)

    return {
        "category": _clean(category.upper(), 60),
        "code": code,
        "module": module,
        "type": error_type,
        "message": short or error_type,
        "cause": cause_text,
        "cause_type": cause_type,
        "context": _clean(context or "", 300),
    }


def _fingerprint(parts: dict[str, str]) -> str:
    """Handle fingerprint helper behavior."""
    raw = "|".join(
        [
            parts.get("category", ""),
            parts.get("code", ""),
            parts.get("module", ""),
            parts.get("type", ""),
            parts.get("cause_type", ""),
            parts.get("message", "")[:240],
        ]
    ).lower()
    raw = re.sub(r"0x[0-9a-f]+", "0xADDR", raw)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _make_record(category: str, error: Exception, context: str | None, source: str) -> dict[str, Any]:
    """Handle make record helper behavior."""
    parts = _error_parts(category, error, context)
    fp = _fingerprint(parts)
    now = _now()
    return {
        "id": fp,
        "fingerprint": fp,
        "first_seen": now,
        "last_seen": now,
        "count": 1,
        "is_seen": False,
        "isSeen": False,
        "seen_at": None,
        "seen_reason": None,
        "notified_at": None,
        "notified_via": None,
        "source": source,
        **parts,
    }


def _find_index(errors: list[dict[str, Any]], error_id: str) -> int:
    """Handle find index helper behavior."""
    for idx, item in enumerate(errors):
        if item.get("id") == error_id or item.get("fingerprint") == error_id:
            return idx
    return -1


def _trim(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Handle trim helper behavior."""
    if len(errors) <= _MAX_RECORDS:
        return errors
    return sorted(errors, key=lambda item: item.get("last_seen") or "")[-_MAX_RECORDS:]


def record_error(
    category: str,
    error: Exception,
    context: str | None = None,
    source: str = "log_exception",
) -> dict[str, Any]:
    """Record or update an error without marking it seen."""
    record = _make_record(category, error, context, source)
    with _LOCK:
        data = _load()
        errors = data["errors"]
        idx = _find_index(errors, record["id"])
        is_new = idx < 0
        if is_new:
            errors.append(record)
            stored = record
        else:
            stored = errors[idx]
            stored["last_seen"] = _now()
            stored["count"] = int(stored.get("count") or 1) + 1
            stored["source"] = source
            for key in ("message", "cause", "context", "code", "module", "type", "category"):
                if record.get(key):
                    stored[key] = record[key]
            stored["is_seen"] = bool(stored.get("is_seen") or stored.get("isSeen"))
            stored["isSeen"] = stored["is_seen"]
        data["errors"] = _trim(errors)
        _save(data)

    return {
        "record": dict(stored),
        "is_new": is_new,
        "should_alert": not bool(stored.get("is_seen") or stored.get("isSeen") or stored.get("notified_at")),
    }


def get_error_for_alert(
    category: str,
    error: Exception,
    context: str | None = None,
    source: str = "alert",
) -> dict[str, Any] | None:
    """Return an unseen record for alerting without increasing its count twice."""
    probe = _make_record(category, error, context, source)
    with _LOCK:
        data = _load()
        errors = data["errors"]
        idx = _find_index(errors, probe["id"])
        if idx < 0:
            errors.append(probe)
            data["errors"] = _trim(errors)
            _save(data)
            record = probe
        else:
            record = errors[idx]
        if record.get("is_seen") or record.get("isSeen") or record.get("notified_at"):
            return None
        return dict(record)


def mark_error_seen(
    error_id: str,
    seen_reason: str = "yourai_prompt",
    notified_via: str | None = None,
) -> bool:
    """Handle mark error seen helper behavior."""
    with _LOCK:
        data = _load()
        errors = data["errors"]
        idx = _find_index(errors, error_id)
        if idx < 0:
            return False
        record = errors[idx]
        now = _now()
        record["is_seen"] = True
        record["isSeen"] = True
        record["seen_at"] = record.get("seen_at") or now
        record["seen_reason"] = seen_reason
        if notified_via:
            record["notified_at"] = record.get("notified_at") or now
            record["notified_via"] = notified_via
        _save(data)
        return True


def pop_unseen_errors(
    max_items: int = 5,
    mark_seen: bool = True,
    seen_reason: str = "yourai_prompt",
) -> list[dict[str, Any]]:
    """Handle pop unseen errors helper behavior."""
    with _LOCK:
        data = _load()
        errors = data["errors"]
        unseen = [
            item for item in errors
            if not (item.get("is_seen") or item.get("isSeen") or item.get("notified_at"))
        ]
        unseen = sorted(unseen, key=lambda item: item.get("first_seen") or "")[:max_items]
        if mark_seen and unseen:
            now = _now()
            unseen_ids = {item.get("id") for item in unseen}
            for item in errors:
                if item.get("id") in unseen_ids:
                    item["is_seen"] = True
                    item["isSeen"] = True
                    item["seen_at"] = item.get("seen_at") or now
                    item["seen_reason"] = seen_reason
            _save(data)
        return [dict(item) for item in unseen]


def format_error_records(records: list[dict[str, Any]], max_message: int = 220) -> str:
    """Handle format error records helper behavior."""
    lines: list[str] = []
    for item in records:
        code = item.get("code") or item.get("id") or "ERROR"
        category = item.get("category") or "SYSTEM"
        module = item.get("module") or "unknown"
        count = int(item.get("count") or 1)
        message = _clean(item.get("message") or item.get("cause") or "Unknown error", max_message)
        suffix = f" (x{count})" if count > 1 else ""
        lines.append(f"- [{code}] {category}/{module}{suffix}: {message}")
    return "\n".join(lines)
