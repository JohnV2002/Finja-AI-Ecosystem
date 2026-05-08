"""
YourAI AI - Paperless-NGX Integration
======================================
API-Client für Paperless-NGX Dokumentenmanagement.
Admin-Only: Nur Creator darf Dokumente durchsuchen.

Endpoints:
    GET  /api/documents/?query=...     → Volltextsuche
    GET  /api/documents/{id}/          → Metadaten
    GET  /api/documents/{id}/preview/  → Vorschau-Bild
    GET  /api/tags/                    → Alle Tags
    GET  /api/correspondents/          → Alle Korrespondenten
    GET  /api/document_types/          → Alle Dokumenttypen

Usage:
    from tools.paperless import paperless_search, paperless_doc_info, paperless_list_tags
"""

import logging
import time
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError
from config import PAPERLESS_URL, PAPERLESS_TOKEN, PAPERLESS_TIMEOUT, PAPERLESS_MAX_RESULTS

logger = logging.getLogger("yourai.tools.paperless")

# ==========================================
# API HELPERS
# ==========================================

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Token {PAPERLESS_TOKEN}",
        "Accept": "application/json",
    }


def _api_get(endpoint: str, params: Optional[Dict] = None) -> Dict:
    """GET Request an Paperless API."""
    url = f"{PAPERLESS_URL}/api/{endpoint}"
    response = requests.get(url, headers=_headers(), params=params, timeout=PAPERLESS_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _format_date(iso_str: Optional[str]) -> str:
    """ISO Datum → lesbares Format."""
    if not iso_str:
        return "unbekannt"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso_str[:10] if iso_str else "unbekannt"


# ==========================================
# CACHES für Tag/Korrespondent/Typ-Namen
# ==========================================
# Paperless gibt nur IDs zurück, wir cachen die Namen

_tag_cache: Dict[int, str] = {}
_correspondent_cache: Dict[int, str] = {}
_doctype_cache: Dict[int, str] = {}


def _ensure_caches() -> None:
    """Lädt Tag/Korrespondent/Typ-Namen wenn Cache leer."""
    global _tag_cache, _correspondent_cache, _doctype_cache

    if not _tag_cache:
        try:
            data = _api_get("tags/", {"page_size": 200})
            _tag_cache = {t["id"]: t["name"] for t in data.get("results", [])}
        except Exception:
            pass

    if not _correspondent_cache:
        try:
            data = _api_get("correspondents/", {"page_size": 200})
            _correspondent_cache = {c["id"]: c["name"] for c in data.get("results", [])}
        except Exception:
            pass

    if not _doctype_cache:
        try:
            data = _api_get("document_types/", {"page_size": 200})
            _doctype_cache = {d["id"]: d["name"] for d in data.get("results", [])}
        except Exception:
            pass


def _resolve_tags(tag_ids: List[int]) -> List[str]:
    """Tag-IDs → Namen."""
    _ensure_caches()
    return [_tag_cache.get(tid, f"Tag#{tid}") for tid in tag_ids]


def _resolve_correspondent(cid: Optional[int]) -> str:
    """Korrespondent-ID → Name."""
    if cid is None:
        return "unbekannt"
    _ensure_caches()
    return _correspondent_cache.get(cid, f"Korrespondent#{cid}")


def _resolve_doctype(did: Optional[int]) -> str:
    """Dokumenttyp-ID → Name."""
    if did is None:
        return "unbekannt"
    _ensure_caches()
    return _doctype_cache.get(did, f"Typ#{did}")


# ==========================================
# MAIN FUNCTIONS
# ==========================================

def paperless_search(query: str, count: Optional[int] = None, debug: Any = None) -> Dict[str, Any]:
    """
    Volltextsuche in Paperless-NGX.

    Args:
        query: Suchbegriff
        count: Max Ergebnisse (default: PAPERLESS_MAX_RESULTS)
        debug: Dashboard debug client

    Returns:
        {"success": bool, "results": [...], "message": str}
    """
    if not query or not query.strip():
        return {"success": False, "results": [], "message": "Empty search query"}

    query = query.strip()
    count = count or PAPERLESS_MAX_RESULTS

    logger.info("Paperless search: '%s' (max %d)", query, count)
    log("PAPERLESS", f"📄 Searching: {query}", Fore.CYAN)

    if not PAPERLESS_TOKEN:
        log("PAPERLESS", "⚠️ No Paperless token configured!", Fore.YELLOW)
        return {"success": False, "results": [], "message": "Paperless token not configured"}

    try:
        start_time = time.time()

        data = _api_get("documents/", {
            "query": query,
            "page_size": count,
            "ordering": "-created",
        })

        duration_ms = int((time.time() - start_time) * 1000)
        raw_results = data.get("results", [])

        results = []
        for doc in raw_results:
            tags = _resolve_tags(doc.get("tags", []))
            correspondent = _resolve_correspondent(doc.get("correspondent"))
            doctype = _resolve_doctype(doc.get("document_type"))
            created = _format_date(doc.get("created"))

            results.append({
                "id": doc["id"],
                "title": doc.get("title", "(Kein Titel)"),
                "correspondent": correspondent,
                "document_type": doctype,
                "tags": tags,
                "created": created,
                "added": _format_date(doc.get("added")),
                "content_preview": (doc.get("content") or "")[:300].strip(),
            })

        # Lesbaren Text bauen
        result_lines = []
        for i, r in enumerate(results, 1):
            tags_str = ", ".join(r["tags"]) if r["tags"] else "keine"
            line = f"{i}. **{r['title']}** (ID: {r['id']})"
            line += f"\n   Von: {r['correspondent']} | Typ: {r['document_type']} | Datum: {r['created']}"
            line += f"\n   Tags: {tags_str}"
            if r["content_preview"]:
                preview = r["content_preview"].replace("\n", " ")[:150]
                line += f"\n   Vorschau: {preview}..."
            result_lines.append(line)

        total = data.get("count", len(results))
        message = f"📄 {len(results)} von {total} Dokumenten für '{query}' ({duration_ms}ms):\n" + "\n".join(result_lines)

        logger.info("Paperless search done: %d results in %dms", len(results), duration_ms)
        log("PAPERLESS", f"✅ {len(results)}/{total} results ({duration_ms}ms)", Fore.GREEN)

        return {
            "success": True,
            "results": results,
            "total": total,
            "message": message,
            "query": query,
            "duration_ms": duration_ms,
        }

    except requests.exceptions.Timeout:
        log("PAPERLESS", f"❌ Timeout ({PAPERLESS_TIMEOUT}s)", Fore.RED)
        return {"success": False, "results": [], "message": f"Paperless timeout ({PAPERLESS_TIMEOUT}s)"}

    except requests.exceptions.ConnectionError:
        log("PAPERLESS", "❌ Not reachable", Fore.RED)
        return {"success": False, "results": [], "message": "Paperless not reachable"}

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        log("PAPERLESS", f"❌ HTTP {status}", Fore.RED)
        return {"success": False, "results": [], "message": f"Paperless HTTP error: {status}"}

    except Exception as e:
        err = YourAIToolExecutionError("Fehler bei der Paperless Suche", tool_name="paperless_search", cause=e)
        log_exception("PAPERLESS", err)
        return {"success": False, "results": [], "message": f"Paperless error: {e}"}


def paperless_doc_content(doc_id: int, debug: Any = None) -> Dict[str, Any]:
    """
    Liest den Volltext eines Dokuments.

    Args:
        doc_id: Paperless Document ID

    Returns:
        {"success": bool, "title": str, "content": str, "message": str}
    """
    logger.info("Paperless read doc: #%d", doc_id)
    log("PAPERLESS", f"📖 Reading document #{doc_id}", Fore.CYAN)

    if not PAPERLESS_TOKEN:
        return {"success": False, "message": "Paperless token not configured"}

    try:
        start_time = time.time()
        data = _api_get(f"documents/{doc_id}/")
        duration_ms = int((time.time() - start_time) * 1000)

        title = data.get("title", f"Dokument #{doc_id}")
        content = data.get("content", "")
        tags = _resolve_tags(data.get("tags", []))
        correspondent = _resolve_correspondent(data.get("correspondent"))
        doctype = _resolve_doctype(data.get("document_type"))
        created = _format_date(data.get("created"))

        # Content kürzen wenn zu lang (max 8000 chars für Prompt)
        truncated = False
        if len(content) > 8000:
            content = content[:8000]
            truncated = True

        meta = f"Titel: {title}\nVon: {correspondent} | Typ: {doctype} | Datum: {created}\nTags: {', '.join(tags) if tags else 'keine'}"
        message = f"📄 {title} (#{doc_id}, {len(content)} Zeichen, {duration_ms}ms)"
        if truncated:
            message += " [gekürzt]"

        log("PAPERLESS", f"✅ {message}", Fore.GREEN)

        return {
            "success": True,
            "id": doc_id,
            "title": title,
            "correspondent": correspondent,
            "document_type": doctype,
            "tags": tags,
            "created": created,
            "content": content,
            "meta": meta,
            "truncated": truncated,
            "message": message,
        }

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status == 404:
            return {"success": False, "message": f"Dokument #{doc_id} nicht gefunden"}
        return {"success": False, "message": f"Paperless HTTP error: {status}"}

    except Exception as e:
        err = YourAIToolExecutionError(f"Fehler beim Lesen von Dokument #{doc_id}", tool_name="paperless_doc_content", cause=e)
        log_exception("PAPERLESS", err)
        return {"success": False, "message": f"Error reading doc #{doc_id}: {e}"}


def paperless_list_tags(debug: Any = None) -> Dict[str, Any]:
    """Listet alle Tags."""
    try:
        _ensure_caches()
        tags = sorted(_tag_cache.values())
        message = f"🏷️ {len(tags)} Tags: {', '.join(tags)}" if tags else "🏷️ Keine Tags vorhanden"
        return {"success": True, "tags": tags, "message": message}
    except Exception as e:
        err = YourAIToolExecutionError("Fehler beim Abrufen der Tag-Liste", tool_name="paperless_list_tags", cause=e)
        log_exception("PAPERLESS", err)
        return {"success": False, "message": f"Error: {e}"}


def paperless_list_correspondents(debug: Any = None) -> Dict[str, Any]:
    """Listet alle Korrespondenten."""
    try:
        _ensure_caches()
        corrs = sorted(_correspondent_cache.values())
        message = f"👤 {len(corrs)} Korrespondenten: {', '.join(corrs)}" if corrs else "👤 Keine Korrespondenten"
        return {"success": True, "correspondents": corrs, "message": message}
    except Exception as e:
        err = YourAIToolExecutionError("Fehler beim Abrufen der Korrespondenten", tool_name="paperless_list_correspondents", cause=e)
        log_exception("PAPERLESS", err)
        return {"success": False, "message": f"Error: {e}"}


def paperless_list_doctypes(debug: Any = None) -> Dict[str, Any]:
    """Listet alle Dokumenttypen."""
    try:
        _ensure_caches()
        types = sorted(_doctype_cache.values())
        message = f"📋 {len(types)} Dokumenttypen: {', '.join(types)}" if types else "📋 Keine Dokumenttypen"
        return {"success": True, "document_types": types, "message": message}
    except Exception as e:
        err = YourAIToolExecutionError("Fehler beim Abrufen der Dokumenttypen", tool_name="paperless_list_doctypes", cause=e)
        log_exception("PAPERLESS", err)
        return {"success": False, "message": f"Error: {e}"}


def format_search_for_prompt(search_result: Dict[str, Any]) -> str:
    """Formatiert Suchergebnisse kompakt für YourAIs Prompt-Kontext."""
    if not search_result.get("success") or not search_result.get("results"):
        return f"Paperless search for '{search_result.get('query', '?')}': no documents found."

    lines = [f"Paperless documents matching '{search_result['query']}' ({search_result.get('total', '?')} total):"]
    for r in search_result["results"]:
        tags_str = ", ".join(r["tags"]) if r["tags"] else "keine"
        lines.append(f"- #{r['id']} \"{r['title']}\" (Von: {r['correspondent']}, Typ: {r['document_type']}, Datum: {r['created']}, Tags: {tags_str})")

    return "\n".join(lines)


def format_doc_for_prompt(doc_result: Dict[str, Any]) -> str:
    """Formatiert Dokumentinhalt für YourAIs Prompt-Kontext."""
    if not doc_result.get("success"):
        return doc_result.get("message", "Document read failed.")

    lines = [
        doc_result.get("meta", ""),
        "---",
        doc_result.get("content", "(Kein Inhalt)"),
    ]
    if doc_result.get("truncated"):
        lines.append("\n[... Dokument wurde gekürzt, frag nach spezifischen Teilen ...]")

    return "\n".join(lines)
