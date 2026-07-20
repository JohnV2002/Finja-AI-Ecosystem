"""
======================================================================
           Finja Web Crawler – Research Orchestrator API
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-web-crawler / research-orchestrator
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
  Description:
----------------------------------------------------------------------
  Mother service for Finja's research pipeline.

  Main Responsibilities:
  - Expose separate search, crawl, and research endpoints.
  - Keep API authentication, orchestration, ranking, and budgeting in one place.
  - Delegate untrusted page reads to a sandboxed crawl-worker service.

  Side Effects:
  - Calls the existing search-proxy service.
  - Optionally calls a crawl-worker service when configured.
  - Does not store persistent research data.
======================================================================
"""

from __future__ import annotations

import collections
import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated, Any
from urllib.parse import urlparse, urlunparse

import requests
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl


load_dotenv()

SERVICE_NAME = "finja-research-orchestrator"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("finja.research_orchestrator")

# ── Telemetry (self-contained, in-process counters exposed via /stats) ─────────
_METRICS_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = collections.defaultdict(int)
_DUR_SUM: dict[str, float] = collections.defaultdict(float)
_DUR_CNT: dict[str, int] = collections.defaultdict(int)
_STARTED_AT = time.time()
_LAST_ERROR: dict[str, object] = {"msg": None, "at": None}


def _m_incr(key: str, n: int = 1) -> None:
    """Increment a named counter."""
    with _METRICS_LOCK:
        _COUNTERS[key] += n


def _m_observe(key: str, ms: float) -> None:
    """Record a duration sample (ms) for averaging."""
    with _METRICS_LOCK:
        _DUR_SUM[key] += ms
        _DUR_CNT[key] += 1


def _m_error(msg: object) -> None:
    """Remember the most recent error for /stats."""
    with _METRICS_LOCK:
        _LAST_ERROR["msg"] = str(msg)[:300]
        _LAST_ERROR["at"] = int(time.time())


def _m_snapshot() -> dict:
    """Return a JSON-safe telemetry snapshot."""
    with _METRICS_LOCK:
        avg = {k: round(_DUR_SUM[k] / _DUR_CNT[k]) for k in _DUR_CNT if _DUR_CNT[k]}
        return {
            "service": SERVICE_NAME,
            "uptime_s": int(time.time() - _STARTED_AT),
            "counters": dict(_COUNTERS),
            "avg_duration_ms": avg,
            "last_error": dict(_LAST_ERROR),
        }


app = FastAPI(title="Finja Research Orchestrator", version="0.1.0")

EXPECTED_BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SEARCH_API_URL = os.getenv("SEARCH_API_URL", "http://search-proxy/search")
CRAWL_WORKER_URL = os.getenv("CRAWL_WORKER_URL", "").rstrip("/")
CRAWL_WORKER_URLS = [
    url.strip().rstrip("/")
    for url in os.getenv("CRAWL_WORKER_URLS", "").split(",")
    if url.strip()
]
REQUEST_TIMEOUT_SEC = float(os.getenv("RESEARCH_REQUEST_TIMEOUT_SEC", "20"))
MAX_SEARCH_RESULTS = int(os.getenv("RESEARCH_MAX_SEARCH_RESULTS", "8"))
MAX_RESEARCH_SOURCES = int(os.getenv("RESEARCH_MAX_SOURCES", "3"))
MAX_PARALLEL_CRAWLS = max(1, int(os.getenv("RESEARCH_MAX_PARALLEL_CRAWLS", "4")))
MAX_CONTEXT_CHARS = int(os.getenv("RESEARCH_MAX_CONTEXT_CHARS", "12000"))
_crawl_slots = threading.BoundedSemaphore(MAX_PARALLEL_CRAWLS)
_crawl_worker_lock = threading.Lock()
_crawl_worker_cursor = 0


class SearchRequest(BaseModel):
    """Search query request."""

    query: str = Field(..., min_length=1, max_length=500)
    count: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    """Normalized search result."""

    link: str
    title: str | None = None
    snippet: str | None = None
    rank: int | None = None
    source: str | None = None
    domain: str | None = None
    source_quality: str = "snippet"


class SearchResponse(BaseModel):
    """Search response with metadata."""

    query: str
    count: int
    duration_ms: int
    source: str
    results: list[SearchResult]


class CrawlRequest(BaseModel):
    """Crawl one concrete URL through a sandbox worker."""

    url: HttpUrl
    max_chars: int = Field(default=MAX_CONTEXT_CHARS, ge=500, le=50000)


class CrawlResponse(BaseModel):
    """Sanitized page-read response from the crawl worker."""

    url: str
    title: str | None = None
    text: str
    excerpt: str
    duration_ms: int | None = None
    source_quality: str = "crawled"


class ResearchRequest(BaseModel):
    """Deepsearch-light request."""

    query: str = Field(..., min_length=1, max_length=500)
    count: int = Field(default=5, ge=1, le=20)
    crawl_top_n: int = Field(default=MAX_RESEARCH_SOURCES, ge=0, le=8)
    max_context_chars: int = Field(default=MAX_CONTEXT_CHARS, ge=1000, le=50000)


class ResearchSource(BaseModel):
    """One source used in the research context."""

    url: str
    title: str | None = None
    snippet: str | None = None
    excerpt: str | None = None
    source_quality: str


class ResearchResponse(BaseModel):
    """Research response for Finja/expert context injection."""

    query: str
    duration_ms: int
    crawl_enabled: bool
    sources: list[ResearchSource]
    research_context: str
    notes: list[str] = Field(default_factory=list)


def _require_auth(authorization: str | None) -> None:
    """Validate bearer-token authentication when configured."""
    if not EXPECTED_BEARER_TOKEN:
        return
    expected_auth_header = f"Bearer {EXPECTED_BEARER_TOKEN}"
    if authorization != expected_auth_header:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _safe_log_text(text: str) -> str:
    """Return a log-safe single-line preview."""
    return text.replace("\n", " ").replace("\r", " ").strip()[:200]


def _normalize_url(url: str) -> str:
    """Normalize URL enough for duplicate removal without changing meaning."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    """Remove duplicate URLs while preserving order."""
    deduped: list[SearchResult] = []
    seen: set[str] = set()
    for item in results:
        key = _normalize_url(item.link)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    for idx, item in enumerate(deduped, 1):
        item.rank = idx
    return deduped


def _post_json(url: str, payload: dict[str, Any], authorization: str | None) -> Any:
    """POST JSON to a child service and return parsed JSON."""
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    return response.json()


def _crawl_worker_configured() -> bool:
    """Return whether at least one crawl worker target is configured."""
    return bool(CRAWL_WORKER_URLS or CRAWL_WORKER_URL)


def _url_with_host(base_url: str, host: str, port: int | None) -> str:
    """Return base_url with hostname replaced by a resolved worker IP."""
    parsed = urlparse(base_url)
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port else host
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", "")).rstrip("/")


def _resolve_crawl_worker_urls() -> list[str]:
    """Resolve scaled crawl-worker containers into concrete base URLs."""
    configured = CRAWL_WORKER_URLS or ([CRAWL_WORKER_URL] if CRAWL_WORKER_URL else [])
    if CRAWL_WORKER_URLS or not configured:
        return configured

    base_url = configured[0]
    parsed = urlparse(base_url)
    if not parsed.hostname:
        return configured

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        logger.warning("Could not resolve crawl worker DNS '%s': %s", parsed.hostname, exc)
        return configured

    resolved: list[str] = []
    seen: set[str] = set()
    for info in infos:
        host = info[4][0]
        url = _url_with_host(base_url, host, parsed.port)
        if url not in seen:
            resolved.append(url)
            seen.add(url)
    return resolved or configured


def _next_crawl_worker_urls() -> list[str]:
    """Return worker URLs in round-robin order for retry/failover."""
    global _crawl_worker_cursor
    urls = _resolve_crawl_worker_urls()
    if not urls:
        return []
    with _crawl_worker_lock:
        start = _crawl_worker_cursor % len(urls)
        _crawl_worker_cursor += 1
    return urls[start:] + urls[:start]


def _search(search_request: SearchRequest, authorization: str | None) -> SearchResponse:
    """Call search-proxy and normalize its output."""
    count = min(search_request.count, MAX_SEARCH_RESULTS)
    safe_query = _safe_log_text(search_request.query)
    _m_incr("search_total")
    logger.info("Research search started: %s (count=%s)", safe_query, count)

    start = time.time()
    try:
        raw_results = _post_json(
            SEARCH_API_URL,
            {"query": search_request.query, "count": count},
            authorization,
        )
    except Exception as exc:
        _m_incr("search_fail")
        _m_error(f"search: {exc}")
        logger.warning("Research search failed: %s", exc)
        raise
    duration_ms = int((time.time() - start) * 1000)

    normalized = [
        SearchResult(
            link=str(item.get("link", "")),
            title=item.get("title"),
            snippet=item.get("snippet"),
            rank=item.get("rank"),
            source=item.get("source"),
            domain=item.get("domain"),
            source_quality=item.get("source_quality") or "snippet",
        )
        for item in raw_results
        if item.get("link")
    ]
    results = _dedupe_results(normalized)
    _m_incr("search_ok")
    _m_observe("search", duration_ms)
    logger.info("Research search returned %s result(s) in %sms", len(results), duration_ms)
    return SearchResponse(
        query=search_request.query,
        count=count,
        duration_ms=duration_ms,
        source="search-proxy",
        results=results,
    )


def _crawl(crawl_request: CrawlRequest, authorization: str | None) -> CrawlResponse:
    """Delegate a URL read to the sandboxed crawl worker."""
    _m_incr("crawl_total")
    worker_urls = _next_crawl_worker_urls()
    if not worker_urls:
        raise HTTPException(
            status_code=503,
            detail="Crawl worker is not configured yet. Build the sandbox worker first.",
        )

    if not _crawl_slots.acquire(blocking=False):
        _m_incr("crawl_busy")
        logger.warning("Crawl rejected: all %s crawl slot(s) busy", MAX_PARALLEL_CRAWLS)
        raise HTTPException(status_code=503, detail="All crawl worker slots are busy")

    logger.debug("Crawl dispatch: url=%s workers=%d", _safe_log_text(str(crawl_request.url)), len(worker_urls))
    start = time.time()
    last_error: Exception | None = None
    raw: dict[str, Any] | None = None
    try:
        for worker_url in worker_urls:
            try:
                raw = _post_json(
                    f"{worker_url}/crawl",
                    {"url": str(crawl_request.url), "max_chars": crawl_request.max_chars},
                    authorization,
                )
                break
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status == 429 or status >= 500:
                    last_error = exc
                    logger.warning("Crawl worker failed (%s): %s", worker_url, exc)
                    continue
                raise
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Crawl worker failed (%s): %s", worker_url, exc)
        if raw is None:
            _m_incr("crawl_fail")
            _m_error(f"crawl: {last_error}")
            raise last_error or RuntimeError("No crawl worker response")
    finally:
        _crawl_slots.release()

    duration_ms = int((time.time() - start) * 1000)
    _m_incr("crawl_ok")
    _m_observe("crawl", duration_ms)
    logger.info("Crawled %s in %sms", _safe_log_text(str(raw.get("url") or crawl_request.url)), duration_ms)
    text = str(raw.get("text", ""))[: crawl_request.max_chars]
    return CrawlResponse(
        url=str(raw.get("url") or crawl_request.url),
        title=raw.get("title"),
        text=text,
        excerpt=str(raw.get("excerpt") or text[:1000]),
        duration_ms=raw.get("duration_ms") or duration_ms,
        source_quality=str(raw.get("source_quality") or "crawled"),
    )


def _source_from_search_result(result: SearchResult) -> ResearchSource:
    """Build a research source from a search-only result."""
    return ResearchSource(
        url=result.link,
        title=result.title,
        snippet=result.snippet,
        source_quality="snippet_only",
    )


def _source_from_crawl_result(result: SearchResult, crawled: CrawlResponse) -> ResearchSource:
    """Build a research source from crawled page text plus search metadata."""
    return ResearchSource(
        url=crawled.url,
        title=crawled.title or result.title,
        snippet=result.snippet,
        excerpt=crawled.excerpt,
        source_quality=crawled.source_quality,
    )


def _crawl_search_result(
    result: SearchResult,
    max_chars: int,
    authorization: str | None,
) -> ResearchSource:
    """Crawl one search result and return it as a research source."""
    crawled = _crawl(
        CrawlRequest(url=result.link, max_chars=max_chars),
        authorization,
    )
    return _source_from_crawl_result(result, crawled)


def _build_research_context(query: str, sources: list[ResearchSource], max_chars: int) -> str:
    """Build a compact context block for Finja/expert prompts."""
    lines = [
        f"Research results for: {query}",
        "Source quality legend: crawled = page text read; snippet_only = search snippet only.",
    ]
    for idx, source in enumerate(sources, 1):
        lines.append(f"\n[{idx}] {source.title or '(No title)'}")
        lines.append(f"URL: {source.url}")
        lines.append(f"Quality: {source.source_quality}")
        if source.excerpt:
            lines.append(f"Excerpt: {source.excerpt}")
        elif source.snippet:
            lines.append(f"Snippet: {source.snippet}")

    context = "\n".join(lines)
    if len(context) <= max_chars:
        return context
    return context[: max_chars - 80].rstrip() + "\n\n[research context truncated by orchestrator]"


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health/status endpoint."""
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "uptime_s": int(time.time() - _STARTED_AT),
        "search_api_url": SEARCH_API_URL,
        "crawl_worker_configured": _crawl_worker_configured(),
        "crawl_worker_count": len(_resolve_crawl_worker_urls()),
        "max_parallel_crawls": MAX_PARALLEL_CRAWLS,
        "research_total": _COUNTERS.get("research_total", 0),
        "crawl_total": _COUNTERS.get("crawl_total", 0),
    }


@app.post("/search", response_model=SearchResponse, responses={401: {"description": "Unauthorized"}})
async def search_endpoint(
    search_request: Annotated[SearchRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> SearchResponse:
    """Search-only endpoint: fast candidate discovery."""
    _require_auth(authorization)
    return _search(search_request, authorization)


@app.post("/crawl", response_model=CrawlResponse, responses={401: {"description": "Unauthorized"}})
async def crawl_endpoint(
    crawl_request: Annotated[CrawlRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> CrawlResponse:
    """Crawl one concrete URL through the future sandbox worker."""
    _require_auth(authorization)
    return _crawl(crawl_request, authorization)


@app.post("/research", response_model=ResearchResponse, responses={401: {"description": "Unauthorized"}})
async def research_endpoint(
    research_request: Annotated[ResearchRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> ResearchResponse:
    """Deepsearch-light endpoint: search, optional crawl, compact research context."""
    _require_auth(authorization)
    _m_incr("research_total")
    logger.info("Research started: %s (count=%s, crawl_top_n=%s)",
                _safe_log_text(research_request.query), research_request.count, research_request.crawl_top_n)
    start = time.time()
    search_response = _search(
        SearchRequest(query=research_request.query, count=research_request.count),
        authorization,
    )

    search_results = search_response.results[: research_request.count]
    sources: list[ResearchSource] = []
    notes: list[str] = []
    crawl_limit = research_request.crawl_top_n if _crawl_worker_configured() else 0
    if research_request.crawl_top_n and not _crawl_worker_configured():
        notes.append("crawl_worker_not_configured; using search snippets only")

    crawled_sources: dict[int, ResearchSource] = {}
    if crawl_limit:
        crawl_candidates = search_results[:crawl_limit]
        workers = min(MAX_PARALLEL_CRAWLS, len(crawl_candidates))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    _crawl_search_result,
                    result,
                    research_request.max_context_chars,
                    authorization,
                ): idx
                for idx, result in enumerate(crawl_candidates)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                result = crawl_candidates[idx]
                try:
                    crawled_sources[idx] = future.result()
                except Exception as exc:
                    notes.append(f"crawl_failed:{result.link}:{exc}")

    for idx, result in enumerate(search_results):
        sources.append(crawled_sources.get(idx) or _source_from_search_result(result))

    context = _build_research_context(
        research_request.query,
        sources,
        research_request.max_context_chars,
    )
    duration_ms = int((time.time() - start) * 1000)
    _m_incr("research_ok")
    _m_observe("research", duration_ms)
    crawled_count = sum(1 for s in sources if s.source_quality not in ("snippet_only", "snippet"))
    logger.info("Research done: %s source(s), %s crawled, %s note(s) in %sms",
                len(sources), crawled_count, len(notes), duration_ms)
    return ResearchResponse(
        query=research_request.query,
        duration_ms=duration_ms,
        crawl_enabled=_crawl_worker_configured(),
        sources=sources,
        research_context=context,
        notes=notes,
    )


@app.get("/stats")
async def stats() -> dict:
    """Self-contained telemetry snapshot (counters + avg durations + last error)."""
    return _m_snapshot()
