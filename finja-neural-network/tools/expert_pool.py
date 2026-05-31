"""
Dynamic expert model pool.

The pool is monthly generated data, but runtime selection stays simple:
domain -> candidate models -> feedback removes bad models -> openrouter/auto.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from config import (
    EXPERT_FALLBACK_CHAINS,
    EXPERT_OPENROUTER_OVERRIDES,
    EXPERT_POOL_FILE,
    EXPERT_POOL_LOCK_FILE,
    EXPERT_POOL_PRICE_CAP_USD_PER_M,
    EXPERT_POOL_TOP_N,
    LLM_STATS_API_KEY,
    LLM_STATS_BASE_URL,
    OPENROUTER_API_KEY,
)
from display import Fore, log, log_exception
from exceptions import YourAIUnexpectedError


# Maps our domain names → llm-stats.com API category param (GET /stats/v1/rankings?category=X)
# Real categories from the API: biology, chemistry, coding, general, healthcare, math, physics, reasoning, science
DOMAIN_CATEGORY_MAP = {
    "bio":           "biology",
    "med":           "healthcare",
    "physics":       "physics",
    "chemie":        "chemistry",
    "math":          "math",
    "code":          "coding",
    "writing":       "writing",
    "social_media":  "writing",
    "homelab":       "coding",
    "gaming":        "general",
    "anime":         "general",
    "fox_philosophy": "reasoning",
}

# Keep old name as alias for _fallback_pool / display purposes
DOMAIN_BENCHMARK_HINTS = {k: [v] for k, v in DOMAIN_CATEGORY_MAP.items()}

MANAGED_DOMAINS = tuple(DOMAIN_BENCHMARK_HINTS.keys())


def _canonical_json(data: dict) -> str:
    """Serialize a dict to canonical, sorted, compact JSON (for stable hashing)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _md5(data: dict) -> str:
    """Return the MD5 hex digest of a dict's canonical JSON form."""
    return hashlib.md5(_canonical_json(data).encode("utf-8")).hexdigest()


def _write_pool(pool: dict) -> None:
    """Write the expert pool to disk and refresh its lock (hash) file."""
    os.makedirs(os.path.dirname(EXPERT_POOL_FILE) or ".", exist_ok=True)
    with open(EXPERT_POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)
    with open(EXPERT_POOL_LOCK_FILE, "w", encoding="utf-8") as f:
        f.write(_md5(pool))


def _load_pool_unchecked() -> Optional[dict]:
    """Load the raw pool JSON from disk without lock validation (None if absent)."""
    if not os.path.exists(EXPERT_POOL_FILE):
        return None
    with open(EXPERT_POOL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _lock_matches(pool: dict) -> bool:
    """Return True if the on-disk lock file matches the pool's current hash."""
    if not os.path.exists(EXPERT_POOL_LOCK_FILE):
        return False
    try:
        with open(EXPERT_POOL_LOCK_FILE, "r", encoding="utf-8") as f:
            expected = f.read().strip()
        return expected == _md5(pool)
    except Exception:
        # Unreadable lock file is treated as a mismatch (safe default).
        return False


def _fallback_pool(reason: str = "static_config") -> dict:
    """Build a static fallback pool from the configured fallback chains.

    Args:
        reason (str): Source label recorded on the generated pool/models.

    Returns:
        dict: A fully-formed pool dict for all managed domains.
    """
    domains = {}
    for domain in MANAGED_DOMAINS:
        chain = list(EXPERT_FALLBACK_CHAINS.get(domain, []))
        primary = EXPERT_OPENROUTER_OVERRIDES.get(domain)
        if primary and primary not in chain:
            chain.insert(0, primary)
        if "openrouter/auto" not in chain:
            chain.append("openrouter/auto")
        domains[domain] = {
            "benchmark": reason,
            "price_cap_usd_per_m": EXPERT_POOL_PRICE_CAP_USD_PER_M,
            "models": [
                {
                    "id": model,
                    "rank": idx + 1,
                    "score": None,
                    "effective_cost_usd_per_m": None,
                    "source": reason,
                }
                for idx, model in enumerate(chain)
            ],
        }

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": reason,
        "lock_algorithm": "md5(canonical-json)",
        "domains": domains,
    }


def load_pool(create_if_missing: bool = True) -> dict:
    """Load and validate the expert pool, falling back to static config."""
    try:
        pool = _load_pool_unchecked()
        if pool and _lock_matches(pool):
            return pool

        reason = "missing" if pool is None else "lock_mismatch"
        fallback = _fallback_pool(reason)
        if create_if_missing:
            _write_pool(fallback)
            log("EXPERT_POOL", f"Generated fallback pool ({reason})", Fore.YELLOW)
        return fallback
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="expert_pool_load")
        log_exception("EXPERT_POOL", err)
        return _fallback_pool("load_error")


def get_domain_models(domain: str) -> List[dict]:
    """Return the ranked model list for a domain (static config if pool lacks it)."""
    pool = load_pool()
    models = list(pool.get("domains", {}).get(domain, {}).get("models", []))
    if models:
        return models

    # A persisted pool can be older than the running code after a new expert
    # domain is added. In that case, do not fall through to openrouter/auto;
    # use the static config chain until the next pool refresh writes the domain.
    if domain in MANAGED_DOMAINS:
        return list(_fallback_pool("domain_missing_in_pool").get("domains", {}).get(domain, {}).get("models", []))
    return []


def get_model_chain(domain: str, exclude_models: Optional[List[str]] = None) -> List[str]:
    """Return active model chain for a domain after feedback exclusions."""
    exclude = set(exclude_models or [])
    chain = []

    for item in get_domain_models(domain):
        model = item.get("id")
        if not model:
            continue
        if model in exclude and model != "openrouter/auto":
            continue
        if model not in chain:
            chain.append(model)

    if "openrouter/auto" not in chain:
        chain.append("openrouter/auto")
    return chain


def get_primary_model(domain: str) -> Optional[str]:
    """Return the top-ranked model id for a domain (or None if empty)."""
    chain = get_model_chain(domain)
    return chain[0] if chain else None


def get_pool_status() -> dict:
    """Return a dashboard-friendly status snapshot of the expert pool."""
    pool = load_pool()
    status = {
        "file": EXPERT_POOL_FILE,
        "lock_file": EXPERT_POOL_LOCK_FILE,
        "lock_ok": _lock_matches(pool),
        "generated_at": pool.get("generated_at"),
        "source": pool.get("source"),
        "price_cap_usd_per_m": EXPERT_POOL_PRICE_CAP_USD_PER_M,
        "top_n": EXPERT_POOL_TOP_N,
        "domains": {},
    }
    for domain, info in pool.get("domains", {}).items():
        status["domains"][domain] = {
            "benchmark": info.get("benchmark"),
            "models": info.get("models", []),
        }
    return status


def _fetch_openrouter_prices() -> Dict[str, float]:
    """
    Fetch model pricing from OpenRouter API.
    Returns {model_id: usd_per_million_input_tokens}.
    Silently returns {} on any error.
    """
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        prices: Dict[str, float] = {}
        for m in resp.json().get("data", []):
            mid = m.get("id", "")
            prompt_price = _as_float((m.get("pricing") or {}).get("prompt"))
            if mid and prompt_price is not None:
                # OpenRouter pricing.prompt = USD per token → * 1e6 = USD/M
                prices[mid] = round(prompt_price * 1_000_000, 6)
        log("EXPERT_POOL", f"OpenRouter prices fetched: {len(prices)} models", Fore.CYAN)
        return prices
    except Exception as e:
        log("EXPERT_POOL", f"OpenRouter price fetch failed: {e}", Fore.YELLOW)
        return {}


def _enrich_with_openrouter_prices(domains: Dict[str, dict], or_prices: Dict[str, float]) -> None:
    """Fill in missing effective_cost_usd_per_m for static/fallback models using OpenRouter data."""
    if not or_prices:
        return
    for domain_info in domains.values():
        for model in domain_info.get("models", []):
            if model.get("effective_cost_usd_per_m") is None:
                price = or_prices.get(model["id"])
                if price is not None:
                    model["effective_cost_usd_per_m"] = price


def refresh_from_llm_stats() -> dict:
    """
    Best-effort monthly refresh hook.

    Queries GET /stats/v1/rankings?category=<X> once per domain (using DOMAIN_CATEGORY_MAP),
    builds org/model_id identifiers (OpenRouter format), filters by price cap, and writes the pool.

    Price unit from API: raw value / 1_000_000 = USD per million tokens.
    """
    if not LLM_STATS_API_KEY:
        pool = _fallback_pool("static_config_no_llm_stats_key")
        _write_pool(pool)
        return {"ok": False, "reason": "missing LLM_STATS_API_KEY", "pool": get_pool_status()}

    try:
        headers = {"Authorization": f"Bearer {LLM_STATS_API_KEY}"}
        base = LLM_STATS_BASE_URL.rstrip("/")
        url = f"{base}/stats/v1/rankings"

        domains: Dict[str, dict] = {}
        any_live = False

        for domain in MANAGED_DOMAINS:
            category = DOMAIN_CATEGORY_MAP.get(domain, "general")
            try:
                resp = requests.get(url, headers=headers, params={"category": category}, timeout=15)
                if resp.status_code != 200:
                    log("EXPERT_POOL", f"  {domain} ({category}): HTTP {resp.status_code} — using fallback", Fore.YELLOW)
                    domains[domain] = _fallback_pool("static_config")["domains"][domain]
                    continue

                rows = resp.json().get("models", [])
                picked = _pick_models_for_domain(domain, rows)
                domains[domain] = {
                    "benchmark": category,
                    "price_cap_usd_per_m": EXPERT_POOL_PRICE_CAP_USD_PER_M,
                    "models": picked,
                }
                n_live = sum(1 for m in picked if m.get("source") == "llm-stats")
                log("EXPERT_POOL", f"  {domain} ({category}): {n_live} live models from API", Fore.CYAN)
                if n_live > 0:
                    any_live = True

            except Exception as domain_err:
                log("EXPERT_POOL", f"  {domain}: error — {domain_err} — using fallback", Fore.YELLOW)
                domains[domain] = _fallback_pool("static_config")["domains"][domain]

        # Enrich static/fallback models with OpenRouter pricing
        or_prices = _fetch_openrouter_prices()
        _enrich_with_openrouter_prices(domains, or_prices)

        pool = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "llm-stats" if any_live else "llm_stats_no_usable_rankings",
            "lock_algorithm": "md5(canonical-json)",
            "domains": domains,
        }
        _write_pool(pool)

        if not any_live:
            return {"ok": False, "reason": "no usable rankings from API (all fallback)", "pool": get_pool_status()}
        return {"ok": True, "pool": get_pool_status()}

    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="expert_pool_refresh")
        log_exception("EXPERT_POOL", err)
        pool = _fallback_pool("llm_stats_error")
        _write_pool(pool)
        return {"ok": False, "reason": str(e), "pool": get_pool_status()}


def refresh_if_month_changed() -> dict:
    """Refresh once per month; safe to call at dashboard startup."""
    pool = load_pool()
    generated = str(pool.get("generated_at") or "")
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if generated.startswith(current_month):
        return {"ok": True, "skipped": True, "reason": "current month already generated", "pool": get_pool_status()}
    return refresh_from_llm_stats()


def _pick_models_for_domain(domain: str, rows: List[dict]) -> List[dict]:
    """
    Convert raw llm-stats rankings rows into a model list for one domain.

    API model_id format: "<model_id>" (e.g. "kimi-k2.6")
    API organization format: "<org>" (e.g. "moonshotai")
    OpenRouter format: "<org>/<model_id>"
    Price: raw value / 1_000_000 = USD per million tokens
    """
    picked: List[dict] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        # Build OpenRouter-style ID: org/model_id
        org = str(row.get("organization") or "").strip()
        mid = str(row.get("model_id") or "").strip()
        if not org or not mid:
            continue
        model_id = f"{org}/{mid}"

        # Price filter: API price unit is raw / 1e6 = USD/M tokens
        # Skip models with None price — they're usually not yet available on OpenRouter
        raw_price = _as_float(row.get("min_input_price"))
        if raw_price is None:
            continue
        usd_per_m = raw_price / 1_000_000
        if usd_per_m > EXPERT_POOL_PRICE_CAP_USD_PER_M:
            continue

        picked.append({
            "id": model_id,
            "rank": len(picked) + 1,
            "score": _as_float(row.get("score")),
            "effective_cost_usd_per_m": round(usd_per_m, 6) if usd_per_m is not None else None,
            "source": "llm-stats",
        })
        if len(picked) >= EXPERT_POOL_TOP_N:
            break

    # Pad with static fallback models if not enough live results
    fallback_chain = _fallback_pool("static_config")["domains"].get(domain, {}).get("models", [])
    live_ids = {m["id"] for m in picked}
    for item in fallback_chain:
        if len(picked) >= EXPERT_POOL_TOP_N + 2:
            break
        if item["id"] not in live_ids:
            picked.append(item)
            live_ids.add(item["id"])

    # Always end with safety fallback
    if "openrouter/auto" not in live_ids:
        picked.append({
            "id": "openrouter/auto",
            "rank": len(picked) + 1,
            "score": None,
            "effective_cost_usd_per_m": None,
            "source": "safety_fallback",
        })

    return picked


def _as_float(value: Any) -> Optional[float]:
    """Coerce a value to float, returning None for empty/invalid input."""
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _effective_cost(input_cost: Optional[float], output_cost: Optional[float]) -> Optional[float]:
    """Blend input/output costs (75/25 weighting) into one effective USD/M figure."""
    if input_cost is None and output_cost is None:
        return None
    if input_cost is None:
        return output_cost
    if output_cost is None:
        return input_cost
    return round(input_cost * 0.75 + output_cost * 0.25, 6)
