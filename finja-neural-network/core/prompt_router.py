"""
YourAI AI — Semantic Prompt Router
====================================
Classifies user messages to inject only RELEVANT tool sections into the
system prompt, cutting unnecessary tokens (e.g. HA device list during
small talk).

Architecture:
  - Route utterances are embedded via OpenRouter at startup (cached to disk)
  - Each route = one centroid vector (average of all utterances)
  - classify() embeds the user message → finds closest route
  - Confidence < THRESHOLD → returns None → full prompt (safe fallback)

Routes:
  "spotify"       → SECTION_SPOTIFY
  "homeassistant" → SECTION_HOME_ASSISTANT
  "web"           → SECTION_WEB_SEARCH
  "paperless"     → SECTION_PAPERLESS
  "file"          → SECTION_FILE_BRAIN
  "image"         → SECTION_IMAGE_GEN
  None            → all sections (smalltalk / mixed / unclear)
"""

import asyncio
import concurrent.futures
import hashlib
import json
import os
import threading

import aiohttp
import numpy as np

from display import log, log_exception, Fore
from exceptions import YourAINetworkError, YourAIEmbedError, YourAIUnexpectedError
from config import OPENROUTER_API_KEY, HIPPOCAMPUS_EMBEDDING_OPENROUTER

# ─── Threshold ───────────────────────────────────────────────────────────────
# Minimum cosine similarity to accept a route.
# Too low  → false positives (wrong section excluded)
# Too high → too many None / full-prompt fallbacks
THRESHOLD = 0.62

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "prompt_router_cache.json")
EMBED_URL  = "https://openrouter.ai/api/v1/embeddings"

# ─── Route definitions ────────────────────────────────────────────────────────
# 12-15 utterances per route, German + English mix.
# These are EXAMPLES of messages that need that tool section.
_ROUTE_UTTERANCES: dict[str, list[str]] = {
    "spotify": [
        "spiel mal Musik", "mach Musik an", "Musik bitte",
        "pause", "nächstes Lied bitte", "skip das",
        "shuffle die Playlist", "Lautstärke lauter",
        "leiser bitte", "was läuft gerade",
        "stopp die Musik", "play something", "resume the music",
        "yourai shuffle", "queue anzeigen", "welche Playlist",
        "play this song on Spotify", "can you play a song",
        "play the track", "put on some music",
        "could you play", "spiel das Lied", "spiel den Song",
        "play on Spotify", "spiel auf Spotify",
    ],
    "homeassistant": [
        "mach das Licht an", "Licht aus bitte", "Rolläden runter",
        "Temperatur im Wohnzimmer", "Heizung an", "Staubsauger starten",
        "welche Geräte sind an", "Lampe dimmen",
        "Szene aktivieren", "turn on the lights",
        "what's the room temperature", "Licht im Schlafzimmer",
        "Steckdose ausschalten", "smart home", "welche Lampen brennen",
    ],
    "web": [
        "such mal nach", "google das für mich", "aktuelle Nachrichten",
        "was kostet das gerade", "schau mal nach im Internet",
        "suche nach", "was ist passiert mit",
        "aktuelle Infos über", "web search",
        "look that up", "recherchiere das",
        "find me information about", "what's the latest on",
        "google that", "such mir das raus",
    ],
    "paperless": [
        "such in meinen Dokumenten", "hast du die Rechnung von",
        "finde den Brief", "Stromrechnung",
        "Telekom Rechnung", "such nach dem Vertrag",
        "mein Dokumentenarchiv", "find the invoice",
        "meine Dokumente durchsuchen", "paperless archiv",
        "welche Rechnungen habe ich von",
    ],
    "file": [
        "lies mir das vor", "was steht in Kapitel",
        "lese das Dokument", "File Brain",
        "read the file", "Buchinhalt anzeigen",
        "lese Kapitel", "was steht in der Datei",
        "öffne das Dokument", "zeig mir den Textinhalt",
    ],
    "image": [
        "generier ein Bild", "male mir", "erstell ein Bild von",
        "zeig mir wie das aussieht", "draw me",
        "generate an image", "Bild erstellen",
        "visualisiere das", "create artwork",
        "illustriere", "create a picture of", "generate art",
        "mach ein Bild davon",
    ],
}

# ─── State ───────────────────────────────────────────────────────────────────
_route_centroids: dict[str, list[float]] = {}
_initialized = False
_init_lock = threading.Lock()  # threading.Lock — safe across multiple asyncio.run() threads


# ─── Math helpers ─────────────────────────────────────────────────────────────
def _cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


# ─── Embedding ────────────────────────────────────────────────────────────────
async def _embed_batch(texts: list[str], session: aiohttp.ClientSession) -> list[list[float]]:
    """
    Batch embedding call via OpenRouter — all texts in ONE request.
    OpenRouter mirrors OpenAI's API: input accepts a list of strings.
    Returns list of embeddings in the same order as texts.
    """
    payload = {"model": HIPPOCAMPUS_EMBEDDING_OPENROUTER, "input": texts}
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with session.post(
            EMBED_URL, headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=60)  # batch needs more time
        ) as resp:
            if resp.status != 200:
                raise YourAIEmbedError(
                    f"OpenRouter embedding HTTP {resp.status}",
                    model=HIPPOCAMPUS_EMBEDDING_OPENROUTER,
                    module="prompt_router"
                )
            data = await resp.json()
            try:
                # API returns items sorted by index
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]
            except (KeyError, IndexError, TypeError) as e:
                raise YourAIEmbedError(
                    f"Unexpected batch embedding response format",
                    model=HIPPOCAMPUS_EMBEDDING_OPENROUTER,
                    cause=e,
                    module="prompt_router"
                )
    except (aiohttp.ClientConnectionError, aiohttp.ServerConnectionError) as e:
        raise YourAINetworkError(host="openrouter.ai", cause=e, module="prompt_router")
    except (YourAIEmbedError, YourAINetworkError):
        raise
    except Exception as e:
        raise YourAIUnexpectedError(cause=e, module="prompt_router")


async def _embed_single(text: str, session: aiohttp.ClientSession) -> list[float]:
    """Single embedding for classify() — reuses batch with one item."""
    results = await _embed_batch([text], session)
    return results[0]


# ─── Build centroids ─────────────────────────────────────────────────────────
async def _build_centroids() -> dict[str, list[float]]:
    """
    Embed ALL utterances in ONE batch call, then compute centroid per route.
    78 utterances × 1 call instead of 78 × 1 call = ~1-2s instead of ~25s.
    """
    total = sum(len(v) for v in _ROUTE_UTTERANCES.values())
    log("ROUTER", f"📐 Batch-embedding {total} utterances ({len(_ROUTE_UTTERANCES)} routes) in one call...", Fore.YELLOW)

    # Flatten all utterances, remember which route each belongs to
    all_texts: list[str] = []
    route_slices: dict[str, tuple[int, int]] = {}  # route → (start, end) in all_texts
    for route_name, utterances in _ROUTE_UTTERANCES.items():
        start = len(all_texts)
        all_texts.extend(utterances)
        route_slices[route_name] = (start, len(all_texts))

    async with aiohttp.ClientSession() as session:
        all_embeddings = await _embed_batch(all_texts, session)

    # Compute centroid per route from the flat embedding list
    centroids = {}
    for route_name, (start, end) in route_slices.items():
        route_embs = all_embeddings[start:end]
        centroid = np.mean(route_embs, axis=0).tolist()
        centroids[route_name] = centroid
        log("ROUTER", f"  ✓ {route_name} ({end - start} utterances)", Fore.CYAN)

    return centroids


# ─── Cache ────────────────────────────────────────────────────────────────────
def _cache_key() -> str:
    """MD5 of all utterances — rebuild cache if routes change."""
    all_text = json.dumps(_ROUTE_UTTERANCES, sort_keys=True)
    return hashlib.md5(all_text.encode()).hexdigest()


def _load_cache() -> dict[str, list[float]] | None:
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH) as f:
            cached = json.load(f)
        if cached.get("_key") != _cache_key():
            log("ROUTER", "🔄 Route utterances changed → rebuilding cache", Fore.YELLOW)
            return None
        return {k: v for k, v in cached.items() if not k.startswith("_")}
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="prompt_router_cache")
        log_exception("ROUTER", err)
        return None


def _save_cache(centroids: dict[str, list[float]]):
    try:
        data = dict(centroids)
        data["_key"] = _cache_key()
        with open(CACHE_PATH, "w") as f:
            json.dump(data, f)
        log("ROUTER", f"💾 Route embeddings cached to {os.path.basename(CACHE_PATH)}", Fore.GREEN)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="prompt_router_cache_save")
        log_exception("ROUTER", err)


# ─── Init ─────────────────────────────────────────────────────────────────────
async def _ensure_initialized():
    global _route_centroids, _initialized
    if _initialized:
        return
    # threading.Lock — each asyncio.run() in classify_sync() has its own event loop,
    # so asyncio.Lock() would hang across threads. threading.Lock() is loop-agnostic.
    with _init_lock:
        if _initialized:
            return
        cached = _load_cache()
        if cached:
            _route_centroids = cached
            log("ROUTER", f"🗂️ Route embeddings loaded from cache ({len(_route_centroids)} routes)", Fore.GREEN)
        else:
            log("ROUTER", "🔨 Building route embeddings (first run)...", Fore.YELLOW)
            _route_centroids = await _build_centroids()  # raises on failure
            _save_cache(_route_centroids)
            log("ROUTER", f"✅ Route embeddings ready ({len(_route_centroids)} routes)", Fore.GREEN)
        _initialized = True


# ─── Public API ───────────────────────────────────────────────────────────────
async def classify(message: str) -> str | None:
    """
    Classify a user message into a prompt section route.

    Returns:
        route name (str) — confident match → inject only that section
        None             — low confidence or any error → full prompt (safe fallback)

    Never raises — all errors are caught, logged, and return None.
    """
    if not OPENROUTER_API_KEY or not message.strip():
        return None

    try:
        await _ensure_initialized()
    except (YourAINetworkError, YourAIEmbedError) as e:
        log_exception("ROUTER", e)
        log("ROUTER", "⚠️ Router init failed → full prompt", Fore.YELLOW)
        return None
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="prompt_router_init")
        log_exception("ROUTER", err)
        return None

    if not _route_centroids:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            msg_emb = await _embed_single(message, session)
    except (YourAINetworkError, YourAIEmbedError) as e:
        log_exception("ROUTER", e)
        log("ROUTER", "⚠️ Message embed failed → full prompt", Fore.YELLOW)
        return None
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="prompt_router_embed")
        log_exception("ROUTER", err)
        return None

    scores: dict[str, float] = {}
    for route_name, centroid in _route_centroids.items():
        scores[route_name] = _cosine_sim(msg_emb, centroid)

    best_route = max(scores, key=lambda k: scores[k])
    best_score = scores[best_route]

    # Debug: show top 2
    top2 = sorted(scores.items(), key=lambda x: -x[1])[:2]
    runner_up = f"{top2[1][0]} ({top2[1][1]:.3f})" if len(top2) > 1 else "—"
    log("ROUTER", f"🧭 Best: {best_route} ({best_score:.3f}) | runner-up: {runner_up}", Fore.CYAN)

    if best_score >= THRESHOLD:
        return best_route

    log("ROUTER", f"🧭 Below threshold ({best_score:.3f} < {THRESHOLD}) → full prompt", Fore.CYAN)
    return None


# ─── Sync wrapper ─────────────────────────────────────────────────────────────
# yourai_node and all LangGraph nodes are synchronous — asyncio.run() in a
# dedicated thread is the safest way to call async code from sync context
# without disturbing the existing event loop (e.g. uvicorn/FastAPI).
_thread_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="prompt_router"
)


def classify_sync(message: str) -> str | None:
    """
    Synchronous wrapper around classify().
    Safe to call from non-async code (runs in a dedicated thread).
    Never raises — returns None on any error.
    """
    try:
        future = _thread_pool.submit(asyncio.run, classify(message))
        return future.result(timeout=25)
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="prompt_router_sync")
        log_exception("ROUTER", err)
        return None
