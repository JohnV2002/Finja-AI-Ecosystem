"""
YourAI AI - Cohere Reranker
===========================
Relevance reranking via the Cohere API (direct, no OpenRouter).
Improves diary search and web-search results.

Cost:    ~$0.0025 / search
Model:   rerank-multilingual-v3.0 (DE + EN)
Privacy: Training explicitly set to OFF in the Cohere dashboard.

Usage:
    from tools.reranker import rerank_documents
    ranked = rerank_documents("Was ist Minecraft?", ["doc1", "doc2", ...], top_n=3)
    if ranked:
        best_docs = [r["text"] for r in ranked]
"""

import logging
import time
import requests
from typing import Any, Dict, List, Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError
from config import COHERE_API_KEY, COHERE_RERANK_MODEL

logger = logging.getLogger("yourai.tools.reranker")

_COHERE_URL = "https://api.cohere.com/v2/rerank"


def rerank_documents(
    query: str,
    documents: List[str],
    top_n: int = 5,
    model: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Rerank documents by relevance via the Cohere API.

    Args:
        query (str): The search query to rank documents against.
        documents (List[str]): The list of text documents to rerank.
        top_n (int): Number of top results to return.
        model (Optional[str]): Model override (default: COHERE_RERANK_MODEL).

    Returns:
        Optional[List[Dict[str, Any]]]: List of
        {"index": int, "text": str, "relevance_score": float} sorted by
        relevance (highest first), or None on error (caller then keeps the
        original order).
    """
    if not COHERE_API_KEY:
        return None

    if not documents or not query or not query.strip():
        return None

    # Filter out empty docs, remember original indices for correct mapping back
    valid = [(i, doc) for i, doc in enumerate(documents) if doc and doc.strip()]
    if not valid:
        return None

    doc_texts = [doc for _, doc in valid]
    orig_idx  = [i   for i, _ in valid]
    model     = model or COHERE_RERANK_MODEL
    top_n     = min(top_n, len(doc_texts))

    try:
        t0 = time.time()

        resp = requests.post(
            _COHERE_URL,
            json={
                "model":            model,
                "query":            query,
                "documents":        doc_texts,
                "top_n":            top_n,
                "return_documents": False,
            },
            headers={
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=10,
        )

        ms = int((time.time() - t0) * 1000)

        if resp.status_code == 401:
            log("RERANK", "❌ Cohere auth failed — check COHERE_API_KEY in .env", Fore.RED)
            return None

        if resp.status_code == 404:
            log("RERANK", f"❌ Model '{model}' not found — check COHERE_RERANK_MODEL", Fore.RED)
            return None

        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            i = orig_idx[item["index"]]
            results.append({
                "index":           i,
                "text":            documents[i],
                "relevance_score": item.get("relevance_score", 0.0),
            })

        scores = ", ".join(f"{r['relevance_score']:.3f}" for r in results)
        log("RERANK", f"✅ {len(doc_texts)} → top {len(results)} ({ms}ms) [{scores}]", Fore.GREEN)
        logger.info("Reranked %d → top %d in %dms", len(doc_texts), len(results), ms)

        try:
            import dashboard_analytics
            dashboard_analytics.record_event({
                "event_type": "system_info",
                "metric_name": "cohere_rerank",
                "node_name": "cohere_rerank",
                "model": model,
                "source": "cohere",
                "duration_ms": ms,
                "candidate_count": len(doc_texts),
                "result_count": len(results),
                "content_chars": len(query or "") + sum(len(doc) for doc in doc_texts),
                "estimated_cost_usd": 0.0025,
                "cost_source": "static_config_per_search",
                "status": "success",
            })
        except Exception:
            # Analytics is best-effort telemetry; never let it break reranking.
            pass

        return results

    except requests.exceptions.Timeout:
        log("RERANK", "⏰ Timeout (10s)", Fore.YELLOW)
        return None
    except requests.exceptions.ConnectionError:
        log("RERANK", "❌ Cohere API unreachable", Fore.RED)
        return None
    except Exception as e:
        err = YourAIToolExecutionError("Reranking failed", tool_name="reranker", cause=e)
        log_exception("RERANK", err)
        return None
