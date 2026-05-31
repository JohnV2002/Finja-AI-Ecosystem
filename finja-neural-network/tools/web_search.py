"""
YourAI AI - Web Search (Docker Crawler Client)
===============================================
HTTP client for the DuckDuckGo/Tor web crawler Docker container.

Endpoints:
    POST http://YOUR_WEB_CRAWLER:8080/search
    Body: {"query": "...", "count": 5}
    Auth: Bearer Token

Usage:
    from tools.web_search import web_search
    results = web_search("Fuchsarten in Europa")
"""

import logging
import time
import requests
from typing import Dict, Any, Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError
from config import WEB_CRAWLER_URL, WEB_CRAWLER_TOKEN, WEB_CRAWLER_TIMEOUT, WEB_CRAWLER_MAX_RESULTS

logger = logging.getLogger("yourai.tools.web_search")


def web_search(query: str, count: Optional[int] = None, debug: Any = None) -> Dict[str, Any]:
    """
    Search the web via the Docker crawler.

    Args:
        query (str): The search term.
        count (Optional[int]): Number of desired results (default: WEB_CRAWLER_MAX_RESULTS).
        debug (Any): Dashboard debug client.

    Returns:
        Dict[str, Any]: {"success": bool, "results": [...], "message": str, "query": str}.
    """
    if not query or not query.strip():
        return {"success": False, "results": [], "message": "Empty search query", "query": ""}

    query = query.strip()
    count = count or WEB_CRAWLER_MAX_RESULTS

    logger.info("Web search: '%s' (count=%d)", query, count)
    log("WEB", f"🌐 Searching: {query}", Fore.CYAN)

    if not WEB_CRAWLER_TOKEN:
        logger.warning("No BEARER_WEBCRAWLER token set!")
        log("WEB", "⚠️ No crawler token configured!", Fore.YELLOW)
        return {"success": False, "results": [], "message": "Web crawler token not configured", "query": query}

    try:
        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {WEB_CRAWLER_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {"query": query, "count": count}

        response = requests.post(
            WEB_CRAWLER_URL,
            json=payload,
            headers=headers,
            timeout=WEB_CRAWLER_TIMEOUT,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 401:
            logger.error("Web crawler auth failed (401)")
            log("WEB", "❌ Crawler auth failed (wrong token?)", Fore.RED)
            return {"success": False, "results": [], "message": "Crawler authentication failed", "query": query}

        response.raise_for_status()
        raw_results = response.json()

        # Format results
        results = []
        for item in raw_results:
            results.append({
                "title": item.get("title") or "(No title)",
                "link": item.get("link", ""),
                "snippet": item.get("snippet") or "",
            })

        # RERANKER: sort results by relevance to the query (when available)
        try:
            from config import USE_RERANKER
            if USE_RERANKER and len(results) > 1:
                from reranker import rerank_documents
                _docs = [f"{r['title']}. {r['snippet']}" for r in results]
                _ranked = rerank_documents(query, _docs, top_n=len(results))
                if _ranked:
                    results = [results[r["index"]] for r in _ranked]
        except Exception:
            pass  # Graceful fallback — the original ordering is kept

        # Build human-readable text for YourAI
        result_lines = []
        for i, r in enumerate(results, 1):
            line = f"{i}. **{r['title']}**"
            if r["snippet"]:
                line += f"\n   {r['snippet']}"
            if r["link"]:
                line += f"\n   URL: {r['link']}"
            result_lines.append(line)

        message = f"🌐 {len(results)} results for '{query}' ({duration_ms}ms):\n" + "\n".join(result_lines)

        logger.info("Web search done: %d results in %dms", len(results), duration_ms)
        log("WEB", f"✅ {len(results)} results ({duration_ms}ms)", Fore.GREEN)

        return {
            "success": True,
            "results": results,
            "message": message,
            "query": query,
            "duration_ms": duration_ms,
        }

    except requests.exceptions.Timeout as e:
        err = YourAIToolExecutionError(f"Web crawler timeout ({WEB_CRAWLER_TIMEOUT}s)", tool_name="web_search", cause=e)
        log_exception("WEB", err)
        return {"success": False, "results": [], "message": f"Web crawler timeout ({WEB_CRAWLER_TIMEOUT}s)", "query": query}

    except requests.exceptions.ConnectionError as e:
        err = YourAIToolExecutionError("Crawler not reachable - is the Docker container down?", tool_name="web_search", cause=e)
        log_exception("WEB", err)
        return {"success": False, "results": [], "message": "Web crawler not reachable (Docker container down?)", "query": query}

    except Exception as e:
        err = YourAIToolExecutionError("Web search failed", tool_name="web_search", cause=e)
        log_exception("WEB", err)
        return {"success": False, "results": [], "message": f"Web search error: {e}", "query": query}


def format_results_for_prompt(search_result: Dict[str, Any]) -> str:
    """
    Format search results compactly for YourAI's prompt context.

    Args:
        search_result (Dict[str, Any]): The result dict returned by web_search.

    Returns:
        str: A compact, prompt-friendly summary of the results.
    """
    if not search_result.get("success") or not search_result.get("results"):
        return f"Web search for '{search_result.get('query', '?')}' returned no results."

    lines = [f"Web search results for '{search_result['query']}':"]
    for i, r in enumerate(search_result["results"], 1):
        lines.append(f"{i}. {r['title']}: {r['snippet']}")

    return "\n".join(lines)
