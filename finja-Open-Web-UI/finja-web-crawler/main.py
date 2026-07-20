# main.py
# Hybrid Proxy: TOR + DuckDuckGo + Crawler-Fallback

"""
======================================================================
                     Web Crawler API – Main
======================================================================

  Project: Web Crawler API
  Version: 2.1.0
  Author:  J. Apps (Sodakiller1)
  License: MIT License (c) 2026 J. Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Fast, hybrid web crawler with Tor support
  • Primary search via DuckDuckGo (ddgs)
  • Automatic fallback to Google HTML scraping when results are low
  • Runs via Tor (socks5h://tor:9050) for enhanced privacy
  • REST API provided with FastAPI
  • Secure authentication via Bearer Token
  • Parsing via BeautifulSoup (Title, Link, Snippet)
  • CLI Logging with status messages
  • Configurable timeout & retry delay for Google fallback
  • Docker & Compose ready for containerized deployment
  • Clean JSON responses for easy integration into other systems

----------------------------------------------------------------------
 New in v2.1.0:
 ---------------------------------------------------------------------
  • Part of the distributed-crawl release: this search API now sits
    alongside the crawl-spawner / crawl-worker / research-orchestrator
    services (see docker-compose.yml and the README architecture section)
  • Added /stats telemetry endpoint (counters, durations, cache, last error)
  • Result de-duplication and ranking (_dedupe_and_rank)
  • Query sanitization and URL normalization/unwrapping hardening
  • Module version unified to 2.1.0 across all files

----------------------------------------------------------------------
 To-Dos:
 ---------------------------------------------------------------------
 
  • Implement rate limiting
  • Improve error handling and security (More checks, advanced Auth)
  • Optimize Google HTML scraping (or move away from Google entirely!)
  • Implement other search engines as fallback
  
======================================================================
"""


import uvicorn
from fastapi import FastAPI, Header, Body, HTTPException
from pydantic import BaseModel, Field
import requests
from bs4 import BeautifulSoup, Tag
from ddgs import DDGS
import collections
import logging
import threading
import time
import secrets
from dotenv import load_dotenv
import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from typing import Annotated

load_dotenv()

# Logging setup — LOG_LEVEL env enables DEBUG verbosity for `docker logs`.
SERVICE_NAME = "finja-search-proxy"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("finja.search_proxy")

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

# Tor SOCKS Proxy for DDGS
TOR_PROXY = 'socks5h://tor:9050'

# User-Agents for the Crawler
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]

MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "20"))
TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "mc_cid", "mc_eid", "igshid",
}

app = FastAPI()

# Optional: API Key for authentication. It is highly recommended to change and use this in the .env!
EXPECTED_BEARER_TOKEN = os.getenv("BEARER_TOKEN")

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    count: int = Field(..., ge=1, le=MAX_SEARCH_RESULTS)

class SearchResult(BaseModel):
    link: str
    title: str | None = None
    snippet: str | None = None
    rank: int | None = None
    source: str | None = None
    domain: str | None = None


def _clean_text(value: str | None) -> str | None:
    """Normalize whitespace in result text fields."""
    if value is None:
        return None
    cleaned = " ".join(value.replace("\n", " ").replace("\r", " ").split())
    return cleaned or None


def _sanitize_query(query: str) -> str:
    """Return a safe single-line search query."""
    return " ".join(query.replace("\n", " ").replace("\r", " ").split()).strip()


def _unwrap_google_url(url: str) -> str:
    """Extract the real target from Google redirect URLs."""
    if not url.startswith("/url?q="):
        return url
    parsed = parse_qs(urlparse(url).query)
    return parsed.get("q", [""])[0] or url


def _normalize_url(url: str) -> str:
    """Normalize URL for result output and dedupe."""
    url = _unwrap_google_url(url.strip())
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    query_items = [
        (key, value)
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        if key.lower() not in TRACKING_QUERY_PARAMS
        for value in values
    ]
    query = urlencode(query_items, doseq=True)
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        "",
        query,
        "",
    ))


def _domain(url: str) -> str | None:
    """Return the normalized domain for a URL."""
    parsed = urlparse(url)
    return parsed.netloc.lower() or None


def _dedupe_and_rank(results: list[SearchResult], count: int) -> list[SearchResult]:
    """Drop invalid/duplicate URLs and assign ranks."""
    deduped: list[SearchResult] = []
    seen: set[str] = set()
    for item in results:
        normalized = _normalize_url(item.link)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        item.link = normalized
        item.title = _clean_text(item.title)
        item.snippet = _clean_text(item.snippet)
        item.domain = _domain(normalized)
        deduped.append(item)
        if len(deduped) >= count:
            break
    for idx, item in enumerate(deduped, 1):
        item.rank = idx
    return deduped

@app.post("/search", responses={401: {"description": "Unauthorized"}})
async def external_search(
    search_request: Annotated[SearchRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
):
    if EXPECTED_BEARER_TOKEN:
        expected_auth_header = f"Bearer {EXPECTED_BEARER_TOKEN}"
        if authorization != expected_auth_header:
            raise HTTPException(status_code=401, detail="Unauthorized")

    query = _sanitize_query(search_request.query)
    count = min(search_request.count, MAX_SEARCH_RESULTS)
    safe_query = query[:200]

    _m_incr("search_total")
    start = time.time()
    logger.info("Search started: %s (max %d results)", safe_query, count)
    logger.debug("Search request detail: query=%r count=%d", safe_query, count)

    results = _dedupe_and_rank(ddg_search(query, count), count)

    used_fallback = False
    if len(results) < count:
        used_fallback = True
        _m_incr("search_fallback_used")
        logger.info("DuckDuckGo returned too few results (%d/%d) -> activating Google fallback crawler", len(results), count)
        crawler_results = google_crawler(query, count - len(results))
        results = _dedupe_and_rank(results + crawler_results, count)

    if not results:
        _m_incr("search_empty")
        logger.warning("No results found, returning fallback cat link")
        results.append(SearchResult(
            link="https://en.wikipedia.org/wiki/Tabby_cat",
            title="🐾 Tabby Cat Fallback",
            snippet="I couldn't find anything... But here is a cat. Sometimes they help more than Google. 😊"
        ))

    duration_ms = int((time.time() - start) * 1000)
    _m_incr("search_ok")
    _m_observe("search", duration_ms)
    logger.info("Search returned %d result(s) in %dms (fallback=%s)", len(results), duration_ms, used_fallback)
    return results

def ddg_search(query: str, count: int) -> list[SearchResult]:
    try:
        logger.info(f"Starting DuckDuckGo search with proxy: {TOR_PROXY}")
        with DDGS(proxy=TOR_PROXY) as ddgs:
            search_results = ddgs.text(query, safesearch="moderate", max_results=count)
        return [SearchResult(
            link=result["href"],
            title=result.get("title"),
            snippet=result.get("body"),
            source="duckduckgo",
        ) for result in search_results]
    except Exception as e:
        _m_incr("ddg_error")
        _m_error(f"ddg: {e}")
        logger.error(f"Error during DuckDuckGo search: {e}")
        return []

def _parse_google_html(html_text: str, count: int) -> list[SearchResult]:
    """Helper method to parse Google HTML and reduce cognitive complexity."""
    soup = BeautifulSoup(html_text, 'html.parser')
    result_elements = soup.select('div.g')
    results = []

    for element in result_elements[:count]:
        link_tag = element.find('a', href=True)
        title_tag = element.find('h3')
        snippet_tag = element.find('span', {'class': 'aCOpRe'})

        if not (link_tag and title_tag and isinstance(link_tag, Tag)):
            continue

        href = link_tag.get('href')
        if not isinstance(href, str):
            continue

        href = _unwrap_google_url(href)
            
        if not (href and isinstance(href, str) and href.startswith('http')):
            continue

        results.append(SearchResult(
            link=href,
            title=title_tag.get_text(strip=True),
            snippet=snippet_tag.get_text(strip=True) if snippet_tag else None,
            source="google_fallback",
        ))
    return results

def google_crawler(query: str, count: int) -> list[SearchResult]:
    query = _sanitize_query(query)
    safe_query = query[:200]
    logger.info("Starting Google Fallback Crawler for query: %s", safe_query)
    headers = {
        "User-Agent": secrets.choice(USER_AGENTS)
    }
    try:
        proxies = {
            "http": TOR_PROXY,
            "https": TOR_PROXY
        }

        response = requests.get(
            "https://www.google.com/search",
            params={"q": query},
            proxies=proxies,
            headers=headers,
            timeout=10
        )
        logger.info(f"Google Crawler HTTP Status: {response.status_code}")

        # REQUIRED SLEEP TO PREVENT GOOGLE IP BANS ⬇⬇⬇
        time.sleep(3)

        if response.status_code != 200:
            logger.error(f"Crawler HTTP Error: {response.status_code}")
            return []

        results = _parse_google_html(response.text, count)
        logger.info(f"Crawler found {len(results)} results")
        return results

    except Exception as e:
        _m_incr("google_fallback_error")
        _m_error(f"google: {e}")
        logger.error(f"Error in crawler: {e}")
        return []


@app.get("/health")
async def health() -> dict:
    """Health/status endpoint with a small telemetry summary."""
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "uptime_s": int(time.time() - _STARTED_AT),
        "searches": _COUNTERS.get("search_total", 0),
    }


@app.get("/stats")
async def stats() -> dict:
    """Self-contained telemetry snapshot (counters + avg durations + last error)."""
    return _m_snapshot()


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "80"))
    logger.info(f"Starting DuckDuckGo Tor Proxy on {host}:{port}...")
    uvicorn.run("main:app", host=host, port=port)
