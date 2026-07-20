"""
======================================================================
              Finja Web Crawler – Crawl Spawner API
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-web-crawler / crawl-spawner
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.1.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

----------------------------------------------------------------------
  Description:
----------------------------------------------------------------------
  Small privileged bridge that owns Docker access and spawns one
  short-lived crawl worker container per crawl request. The research
  orchestrator talks to this like it talked to the old static
  crawl-worker: POST /crawl -> CrawlResponse.

  Only this service mounts the Docker socket. Spawned workers get no
  socket, run read-only, and keep the same network/CPU/RAM/PID limits
  as the old baby worker.
======================================================================
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
import uuid
from typing import Annotated, Any

import docker
import requests
from docker.errors import APIError, DockerException, NotFound
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

SERVICE_NAME = "finja-crawl-spawner"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("finja.crawl_spawner")

WORKER_IMAGE = os.getenv("CRAWL_WORKER_IMAGE", "finja-crawl-spawner:local")
WORKER_NETWORK = os.getenv("CRAWL_SPAWN_NETWORK", "finja-web-crawler-net")
WORKER_START_TIMEOUT_SEC = float(os.getenv("CRAWL_SPAWN_START_TIMEOUT_SEC", "8"))
WORKER_TOTAL_TIMEOUT_SEC = float(os.getenv("CRAWL_SPAWN_TOTAL_TIMEOUT_SEC", "24"))
MAX_PARALLEL_SPAWNS = max(1, int(os.getenv("CRAWL_SPAWN_MAX_PARALLEL", "4")))
FETCH_PROXY = os.getenv("FETCH_PROXY", "socks5h://tor:9050")
CRAWL_TIMEOUT_SEC = os.getenv("CRAWL_TIMEOUT_SEC", "12")
CRAWL_MAX_RESPONSE_BYTES = os.getenv("CRAWL_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024))
CRAWL_MAX_REDIRECTS = os.getenv("CRAWL_MAX_REDIRECTS", "3")

_METRICS_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = collections.defaultdict(int)
_DUR_SUM: dict[str, float] = collections.defaultdict(float)
_DUR_CNT: dict[str, int] = collections.defaultdict(int)
_STARTED_AT = time.time()
_LAST_ERROR: dict[str, object] = {"msg": None, "at": None}
_spawn_slots = threading.BoundedSemaphore(MAX_PARALLEL_SPAWNS)
_docker_client = docker.from_env()

app = FastAPI(title="Finja Crawl Spawner", version="0.1.0")


class CrawlRequest(BaseModel):
    """Request to read one URL."""

    url: HttpUrl
    max_chars: int = Field(default=12000, ge=500, le=50000)


class CrawlResponse(BaseModel):
    """Sanitized crawl result, mirrored from crawl_worker.py."""

    url: str
    title: str | None = None
    text: str
    excerpt: str
    content_type: str | None = None
    content_bytes: int | None = None
    duration_ms: int
    source_quality: str = "crawled"


def _m_incr(key: str, n: int = 1) -> None:
    with _METRICS_LOCK:
        _COUNTERS[key] += n


def _m_observe(key: str, ms: float) -> None:
    with _METRICS_LOCK:
        _DUR_SUM[key] += ms
        _DUR_CNT[key] += 1


def _m_error(msg: object) -> None:
    with _METRICS_LOCK:
        _LAST_ERROR["msg"] = str(msg)[:300]
        _LAST_ERROR["at"] = int(time.time())


def _m_snapshot() -> dict[str, Any]:
    with _METRICS_LOCK:
        avg = {k: round(_DUR_SUM[k] / _DUR_CNT[k]) for k in _DUR_CNT if _DUR_CNT[k]}
        return {
            "service": SERVICE_NAME,
            "uptime_s": int(time.time() - _STARTED_AT),
            "counters": dict(_COUNTERS),
            "avg_duration_ms": avg,
            "last_error": dict(_LAST_ERROR),
            "worker_image": WORKER_IMAGE,
            "worker_network": WORKER_NETWORK,
            "max_parallel_spawns": MAX_PARALLEL_SPAWNS,
        }


def _worker_env() -> dict[str, str]:
    return {
        "LOG_LEVEL": LOG_LEVEL,
        "FETCH_PROXY": FETCH_PROXY,
        "CRAWL_TIMEOUT_SEC": CRAWL_TIMEOUT_SEC,
        "CRAWL_MAX_RESPONSE_BYTES": CRAWL_MAX_RESPONSE_BYTES,
        "CRAWL_MAX_REDIRECTS": CRAWL_MAX_REDIRECTS,
        "CRAWL_MAX_CONCURRENT": "1",
    }


def _start_worker(name: str):
    """Create one locked-down HTTP crawl worker container."""
    return _docker_client.containers.run(
        WORKER_IMAGE,
        command=["uvicorn", "crawl_worker:app", "--host", "0.0.0.0", "--port", "80"],
        detach=True,
        name=name,
        network=WORKER_NETWORK,
        environment=_worker_env(),
        read_only=True,
        tmpfs={"/tmp": "size=64m,noexec,nosuid,nodev"},
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        pids_limit=128,
        mem_limit="256m",
        nano_cpus=500_000_000,
        user="appuser",
        labels={
            "finja.service": SERVICE_NAME,
            "finja.worker": "crawl",
        },
    )


def _wait_for_worker(base_url: str) -> None:
    deadline = time.time() + WORKER_START_TIMEOUT_SEC
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=0.75)
            if response.ok:
                return
            last_error = RuntimeError(f"health status {response.status_code}")
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"spawned crawl worker did not become healthy: {last_error}")


def _cleanup_worker(container) -> None:
    try:
        container.stop(timeout=1)
    except (APIError, NotFound):
        pass
    except DockerException as exc:
        logger.warning("Could not stop spawned worker: %s", exc)
    try:
        container.remove(force=True)
    except NotFound:
        pass
    except DockerException as exc:
        logger.warning("Could not remove spawned worker: %s", exc)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health/status endpoint."""
    try:
        _docker_client.ping()
        docker_ok = True
    except DockerException as exc:
        docker_ok = False
        _m_error(f"docker ping: {exc}")
    return {"ok": docker_ok, **_m_snapshot()}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    """Telemetry endpoint."""
    return _m_snapshot()


@app.post("/crawl", response_model=CrawlResponse)
def crawl_endpoint(crawl_request: Annotated[CrawlRequest, Body(...)]) -> CrawlResponse:
    """Spawn one baby crawl worker, delegate one URL read, then kill it."""
    _m_incr("crawl_total")
    if not _spawn_slots.acquire(blocking=False):
        _m_incr("crawl_busy")
        raise HTTPException(status_code=429, detail="Crawl spawner is busy")

    name = f"finja-crawl-job-{uuid.uuid4().hex[:12]}"
    container = None
    start = time.time()
    try:
        container = _start_worker(name)
        base_url = f"http://{name}"
        _wait_for_worker(base_url)
        response = requests.post(
            f"{base_url}/crawl",
            json={"url": str(crawl_request.url), "max_chars": crawl_request.max_chars},
            timeout=WORKER_TOTAL_TIMEOUT_SEC,
        )
        if response.status_code >= 400:
            _m_incr("crawl_rejected" if response.status_code < 500 else "crawl_fail")
            _m_error(f"worker {response.status_code}: {response.text[:240]}")
            raise HTTPException(status_code=response.status_code, detail=response.text[:500])

        raw = response.json()
        duration_ms = int((time.time() - start) * 1000)
        _m_incr("crawl_ok")
        _m_observe("crawl", duration_ms)
        logger.info("Spawned crawl done: %s in %sms", raw.get("url") or crawl_request.url, duration_ms)
        return CrawlResponse(
            url=str(raw.get("url") or crawl_request.url),
            title=raw.get("title"),
            text=str(raw.get("text") or ""),
            excerpt=str(raw.get("excerpt") or str(raw.get("text") or "")[:1000]),
            content_type=raw.get("content_type"),
            content_bytes=raw.get("content_bytes"),
            duration_ms=int(raw.get("duration_ms") or duration_ms),
            source_quality=str(raw.get("source_quality") or "crawled"),
        )
    except HTTPException:
        raise
    except (DockerException, requests.RequestException, RuntimeError) as exc:
        _m_incr("crawl_fail")
        _m_error(exc)
        logger.warning("Spawned crawl failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Spawned crawl failed: {exc}") from exc
    finally:
        if container is not None:
            _cleanup_worker(container)
        _spawn_slots.release()
