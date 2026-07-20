"""
======================================================================
              Finja Web Crawler – Crawl Worker API
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-web-crawler / crawl-worker
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
  Description:
----------------------------------------------------------------------
  Sandboxed baby service for reading untrusted web pages.

  Main Responsibilities:
  - Fetch one concrete HTTP/HTTPS URL.
  - Reject private/local network targets before every request/redirect.
  - Extract sanitized text without executing JavaScript or shell commands.

  Side Effects:
  - Performs outbound HTTP requests, optionally through Tor/proxy.
  - Keeps no persistent state.
"""

from __future__ import annotations

import collections
import ipaddress
import logging
import os
import socket
import threading
import time
from typing import Annotated
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl


SERVICE_NAME = "finja-crawl-worker"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("finja.crawl_worker")

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


app = FastAPI(title="Finja Crawl Worker", version="0.1.0")

FETCH_PROXY = os.getenv("FETCH_PROXY", "socks5h://tor:9050").strip()
FETCH_TIMEOUT_SEC = float(os.getenv("CRAWL_TIMEOUT_SEC", "12"))
MAX_RESPONSE_BYTES = int(os.getenv("CRAWL_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024)))
MAX_REDIRECTS = int(os.getenv("CRAWL_MAX_REDIRECTS", "3"))
MAX_CONCURRENT_CRAWLS = int(os.getenv("CRAWL_MAX_CONCURRENT", "1"))

USER_AGENT = os.getenv(
    "CRAWL_USER_AGENT",
    "FinjaResearchBot/0.1 (+https://jappshome.de/finja; research crawler)",
)

_crawl_slots = threading.BoundedSemaphore(max(1, MAX_CONCURRENT_CRAWLS))


class CrawlRequest(BaseModel):
    """Request to read one URL."""

    url: HttpUrl
    max_chars: int = Field(default=12000, ge=500, le=50000)


class CrawlResponse(BaseModel):
    """Sanitized crawl result."""

    url: str
    title: str | None = None
    text: str
    excerpt: str
    content_type: str | None = None
    content_bytes: int
    duration_ms: int
    source_quality: str = "crawled"


def _is_blocked_ip(raw_ip: str) -> bool:
    """Return True for loopback/private/link-local/etc. targets."""
    try:
        ip = ipaddress.ip_address(raw_ip)
    except ValueError:
        return True
    return any((
        ip.is_loopback,
        ip.is_private,
        ip.is_link_local,
        ip.is_multicast,
        ip.is_reserved,
        ip.is_unspecified,
    ))


def _validate_public_url(url: str) -> None:
    """Reject unsupported schemes and private/local network destinations."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL hostname is missing")

    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"Hostname could not be resolved: {exc}") from exc

    for address in addresses:
        ip = address[4][0]
        if _is_blocked_ip(ip):
            raise HTTPException(status_code=403, detail="Private/local network targets are blocked")


def _fetch_url(url: str) -> tuple[str, bytes, str | None]:
    """Fetch a URL with checked redirects and a byte cap."""
    proxies = {"http": FETCH_PROXY, "https": FETCH_PROXY} if FETCH_PROXY else None
    current_url = url
    headers = {"User-Agent": USER_AGENT}

    for _ in range(MAX_REDIRECTS + 1):
        _validate_public_url(current_url)
        response = requests.get(
            current_url,
            headers=headers,
            proxies=proxies,
            timeout=FETCH_TIMEOUT_SEC,
            allow_redirects=False,
            stream=True,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            if not location:
                raise HTTPException(status_code=502, detail="Redirect without Location header")
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        allowed = ("text/html", "text/plain", "application/xhtml+xml", "")
        if not any(content_type.lower().startswith(item) for item in allowed):
            raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise HTTPException(status_code=413, detail="Response is too large")
            chunks.append(chunk)
        return response.url, b"".join(chunks), content_type or None

    raise HTTPException(status_code=508, detail="Too many redirects")


def _extract_text(html_bytes: bytes, max_chars: int) -> tuple[str | None, str]:
    """Extract main readable text from HTML/plain text bytes."""
    decoded = html_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(decoded, "html.parser")

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    for tag in soup([
        "script", "style", "noscript", "template", "iframe", "svg",
        "form", "input", "button", "select", "textarea",
    ]):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text("\n", strip=True)
    lines = []
    seen = set()
    for line in text.splitlines():
        cleaned = " ".join(line.split())
        if len(cleaned) < 2 or cleaned in seen:
            continue
        seen.add(cleaned)
        lines.append(cleaned)

    compact = "\n".join(lines)
    if len(compact) > max_chars:
        compact = compact[: max_chars - 80].rstrip() + "\n\n[crawl text truncated by worker]"
    return title, compact


@app.get("/health")
async def health() -> dict:
    """Health/status endpoint."""
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "uptime_s": int(time.time() - _STARTED_AT),
        "proxy_configured": bool(FETCH_PROXY),
        "max_concurrent": MAX_CONCURRENT_CRAWLS,
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "crawl_total": _COUNTERS.get("crawl_total", 0),
    }


@app.get("/stats")
async def stats() -> dict:
    """Self-contained telemetry snapshot (counters + avg durations + last error)."""
    return _m_snapshot()


@app.post("/crawl", response_model=CrawlResponse)
def crawl_endpoint(crawl_request: Annotated[CrawlRequest, Body(...)]) -> CrawlResponse:
    """Read and sanitize one concrete URL."""
    _m_incr("crawl_total")
    acquired = _crawl_slots.acquire(blocking=False)
    if not acquired:
        _m_incr("crawl_busy")
        logger.warning("Crawl rejected: worker busy (max_concurrent=%s)", MAX_CONCURRENT_CRAWLS)
        raise HTTPException(status_code=429, detail="Crawl worker is busy")

    logger.debug("Crawl request: url=%s max_chars=%s", str(crawl_request.url), crawl_request.max_chars)
    start = time.time()
    try:
        final_url, content, content_type = _fetch_url(str(crawl_request.url))
        title, text = _extract_text(content, crawl_request.max_chars)
        if not text.strip():
            raise HTTPException(status_code=422, detail="No readable text extracted")
        duration_ms = int((time.time() - start) * 1000)
        _m_incr("crawl_ok")
        _m_observe("crawl", duration_ms)
        logger.info("Crawled %s (%s bytes, %sms)", final_url, len(content), duration_ms)
        return CrawlResponse(
            url=final_url,
            title=title,
            text=text,
            excerpt=text[:1000],
            content_type=content_type,
            content_bytes=len(content),
            duration_ms=duration_ms,
        )
    except HTTPException as exc:
        # Expected rejections (SSRF block 403, too large 413, unsupported 415, empty 422).
        _m_incr("crawl_rejected")
        _m_error(f"rejected {exc.status_code}: {exc.detail}")
        logger.warning("Crawl rejected (%s): %s", exc.status_code, exc.detail)
        raise
    except requests.RequestException as exc:
        _m_incr("crawl_fail")
        _m_error(f"fetch: {exc}")
        logger.warning("Crawl fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}") from exc
    finally:
        _crawl_slots.release()
