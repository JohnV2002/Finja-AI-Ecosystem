"""
Cohere embedding helpers for semantic diary recall.

The diary path uses embeddings only as a first-stage candidate finder. The
existing Cohere reranker still decides which entries are worth prompt space.
"""

from __future__ import annotations

import logging
import math
import time
from typing import List, Optional, Sequence

import requests

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from config import COHERE_API_KEY, COHERE_EMBED_MODEL
from display import Fore, log, log_exception
from exceptions import YourAIEmbedError, YourAIToolExecutionError


logger = logging.getLogger("yourai.tools.cohere_embeddings")

_COHERE_EMBED_V2_URL = "https://api.cohere.com/v2/embed"
_COHERE_EMBED_V1_URL = "https://api.cohere.ai/v1/embed"
_EMBED_CACHE: dict[tuple[str, str, str], List[float]] = {}
_COHERE_BATCH_SIZE = 96  # Cohere hard limit per request


def embed_texts(
    texts: Sequence[str],
    *,
    input_type: str,
    model: Optional[str] = None,
    timeout: int = 15,
) -> Optional[List[List[float]]]:
    """Return float embeddings for texts, or None when Cohere is unavailable."""
    if not COHERE_API_KEY:
        return None

    clean_texts = [text.strip() for text in texts if text and text.strip()]
    if not clean_texts:
        return None

    model = model or COHERE_EMBED_MODEL
    cache_keys = [(model, input_type, text) for text in clean_texts]
    cached = [_EMBED_CACHE.get(key) for key in cache_keys]
    if all(vec is not None for vec in cached):
        return [vec for vec in cached if vec is not None]

    texts_to_embed = [
        text for text, vec in zip(clean_texts, cached)
        if vec is None
    ]
    t0 = time.time()

    try:
        # Cohere rejects >96 texts per request — batch if needed
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts_to_embed), _COHERE_BATCH_SIZE):
            batch = texts_to_embed[i : i + _COHERE_BATCH_SIZE]
            batch_vecs = _embed_v2(batch, input_type=input_type, model=model, timeout=timeout)
            if batch_vecs is None:
                batch_vecs = _embed_v1(batch, input_type=input_type, model=model, timeout=timeout)
            if batch_vecs is None:
                return None
            all_embeddings.extend(batch_vecs)

        missing_keys = [key for key, vec in zip(cache_keys, cached) if vec is None]
        for key, vec in zip(missing_keys, all_embeddings):
            _EMBED_CACHE[key] = vec

        ordered = [_EMBED_CACHE[key] for key in cache_keys]

        ms = int((time.time() - t0) * 1000)
        log("EMBED", f"Cohere embedded {len(texts_to_embed)} new texts ({ms}ms) [{model}]", Fore.GREEN)
        logger.info("Embedded %d new texts in %dms with %s", len(texts_to_embed), ms, model)
        try:
            import dashboard_analytics
            dashboard_analytics.record_event({
                "event_type": "system_info",
                "metric_name": "cohere_embedding",
                "node_name": "cohere_embeddings",
                "model": model,
                "source": "cohere",
                "duration_ms": ms,
                "candidate_count": len(texts_to_embed),
                "result_count": len(all_embeddings),
                "content_chars": sum(len(text) for text in texts_to_embed),
                "cost_source": "unknown_cohere_embedding_price",
                "status": "success",
            })
        except Exception:
            # Analytics is best-effort telemetry; never let it break embedding.
            pass
        return ordered
    except requests.exceptions.Timeout:
        log("EMBED", "Cohere embedding timeout", Fore.YELLOW)
        return None
    except requests.exceptions.ConnectionError:
        log("EMBED", "Cohere embedding API unreachable", Fore.RED)
        return None
    except Exception as exc:
        err = YourAIToolExecutionError("Cohere embedding failed", tool_name="cohere_embeddings", cause=exc)
        log_exception("EMBED", err)
        return None


def _embed_v2(texts: Sequence[str], *, input_type: str, model: str, timeout: int) -> Optional[List[List[float]]]:
    """Embed texts via the Cohere v2 endpoint.

    Args:
        texts (Sequence[str]): Texts to embed (already within the batch limit).
        input_type (str): Cohere input type (e.g. "search_document").
        model (str): The Cohere embedding model id.
        timeout (int): Request timeout in seconds.

    Returns:
        Optional[List[List[float]]]: Float embeddings, or None when v2 is not
        applicable (HTTP 400/401/404/422) so the caller can fall back to v1.

    Raises:
        requests.HTTPError: For unexpected non-2xx responses.
    """
    resp = requests.post(
        _COHERE_EMBED_V2_URL,
        json={
            "model": model,
            "texts": list(texts),
            "input_type": input_type,
            "embedding_types": ["float"],
        },
        headers={
            "Authorization": f"Bearer {COHERE_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    if resp.status_code in {400, 404, 422}:
        logger.debug("Cohere v2 rejected (HTTP %d): %s", resp.status_code, resp.text[:200])
        return None
    if resp.status_code == 401:
        log("EMBED", "Cohere auth failed - check COHERE_API_KEY in .env", Fore.RED)
        return None
    resp.raise_for_status()
    return _parse_embeddings(resp.json())


def _embed_v1(texts: Sequence[str], *, input_type: str, model: str, timeout: int) -> Optional[List[List[float]]]:
    """Embed texts via the legacy Cohere v1 endpoint (fallback for v2).

    Args:
        texts (Sequence[str]): Texts to embed (already within the batch limit).
        input_type (str): Cohere input type (e.g. "search_document").
        model (str): The Cohere embedding model id.
        timeout (int): Request timeout in seconds.

    Returns:
        Optional[List[List[float]]]: Float embeddings, or None on a handled
        client error (HTTP 400/401/404).

    Raises:
        requests.HTTPError: For unexpected non-2xx responses.
    """
    resp = requests.post(
        _COHERE_EMBED_V1_URL,
        json={
            "model": model,
            "texts": list(texts),
            "input_type": input_type,
        },
        headers={
            "Authorization": f"Bearer {COHERE_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    if resp.status_code == 400:
        log("EMBED", f"Cohere v1 bad request (400): {resp.text[:200]}", Fore.RED)
        return None
    if resp.status_code == 401:
        log("EMBED", "Cohere auth failed - check COHERE_API_KEY in .env", Fore.RED)
        return None
    if resp.status_code == 404:
        log("EMBED", f"Cohere embed model '{model}' not found", Fore.RED)
        return None
    resp.raise_for_status()
    return _parse_embeddings(resp.json())


def _parse_embeddings(data: dict) -> Optional[List[List[float]]]:
    """Extract the float embedding matrix from a Cohere response payload.

    Args:
        data (dict): The parsed JSON body from a Cohere embed call.

    Returns:
        Optional[List[List[float]]]: The list of embedding vectors.

    Raises:
        YourAIEmbedError: When the payload contains no embeddings or has an
            unexpected shape.
    """
    embeddings = data.get("embeddings")
    if isinstance(embeddings, dict):
        embeddings = embeddings.get("float")

    if not isinstance(embeddings, list) or not embeddings:
        raise YourAIEmbedError("Cohere returned no embeddings", model=COHERE_EMBED_MODEL)

    if not all(isinstance(vec, list) for vec in embeddings):
        raise YourAIEmbedError("Unexpected Cohere embedding shape", model=COHERE_EMBED_MODEL)

    return embeddings


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for two dense vectors."""
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
