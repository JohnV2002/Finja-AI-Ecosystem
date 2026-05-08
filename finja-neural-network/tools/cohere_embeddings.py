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
        embeddings = _embed_v2(texts_to_embed, input_type=input_type, model=model, timeout=timeout)
        if embeddings is None:
            embeddings = _embed_v1(texts_to_embed, input_type=input_type, model=model, timeout=timeout)

        if embeddings is None:
            return None

        missing_keys = [key for key, vec in zip(cache_keys, cached) if vec is None]
        for key, vec in zip(missing_keys, embeddings):
            _EMBED_CACHE[key] = vec

        ordered = [_EMBED_CACHE[key] for key in cache_keys]

        ms = int((time.time() - t0) * 1000)
        log("EMBED", f"Cohere embedded {len(texts_to_embed)} new texts ({ms}ms) [{model}]", Fore.GREEN)
        logger.info("Embedded %d new texts in %dms with %s", len(texts_to_embed), ms, model)
        return ordered
    except requests.exceptions.Timeout:
        log("EMBED", "Cohere embedding timeout", Fore.YELLOW)
        return None
    except requests.exceptions.ConnectionError:
        log("EMBED", "Cohere embedding API nicht erreichbar", Fore.RED)
        return None
    except Exception as exc:
        err = YourAIToolExecutionError("Cohere embedding failed", tool_name="cohere_embeddings", cause=exc)
        log_exception("EMBED", err)
        return None


def _embed_v2(texts: Sequence[str], *, input_type: str, model: str, timeout: int) -> Optional[List[List[float]]]:
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
        return None
    if resp.status_code == 401:
        log("EMBED", "Cohere auth failed - check COHERE_API_KEY in .env", Fore.RED)
        return None
    resp.raise_for_status()
    return _parse_embeddings(resp.json())


def _embed_v1(texts: Sequence[str], *, input_type: str, model: str, timeout: int) -> Optional[List[List[float]]]:
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
    if resp.status_code == 401:
        log("EMBED", "Cohere auth failed - check COHERE_API_KEY in .env", Fore.RED)
        return None
    if resp.status_code == 404:
        log("EMBED", f"Cohere embed model '{model}' not found", Fore.RED)
        return None
    resp.raise_for_status()
    return _parse_embeddings(resp.json())


def _parse_embeddings(data: dict) -> Optional[List[List[float]]]:
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
