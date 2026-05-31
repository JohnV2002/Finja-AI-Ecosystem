"""
YourAI Dashboard Analytics
=========================
Stores compact dashboard metrics, rollups, cost estimates, and alert summaries.

Main Responsibilities:
- Record low-cardinality analytics from dashboard events.
- Build cost, latency, error, cache, and health summaries for the dashboard.
- Prune old metrics into daily rollups and maintain alert state.

Side Effects:
- Reads and writes files under docker_data/analytics.
- Reads error inbox and model pricing cache data.
- May fetch OpenRouter model pricing through configured helpers.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import math
import os
import re
from typing import Any, Callable, Iterable


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ANALYTICS_DIR = os.path.join(_BASE_DIR, "docker_data", "analytics")
METRICS_FILE = os.path.join(_ANALYTICS_DIR, "metrics.jsonl")
ERROR_INBOX_FILE = os.path.join(_BASE_DIR, "docker_data", "error_inbox.json")
ALERTS_FILE = os.path.join(_ANALYTICS_DIR, "alerts.json")
DAILY_ROLLUP_FILE = os.path.join(_ANALYTICS_DIR, "daily_rollups.json")
PRICE_CACHE_FILE = os.path.join(_ANALYTICS_DIR, "price_cache.json")

_MAX_FILE_BYTES = 8 * 1024 * 1024
_ROTATE_KEEP_LINES = 12000
_ALERT_COOLDOWN_MINUTES = 30
_RETENTION_DAYS = 30
_ROLLUP_AFTER_DAYS = 7

_ERROR_EVENTS = {"node_error", "llm_error", "system_error"}
_DURATION_EVENTS = {"pipeline_end", "node_end", "llm_response"}


# Static seeds are deliberately small and obvious. Live llm-stats / expert-pool
# values override these when available; unknown prices stay unknown in the UI.
_STATIC_MODEL_COSTS_USD_PER_M = {
    "google/gemma-4-26b-a4b-it": {"input": 0.06, "output": 0.06, "source": "static_config"},
    "moonshotai/kimi-k2.6": {"input": 0.95, "output": 0.95, "source": "static_config"},
    "google/gemini-3.1-pro-preview": {"input": 2.5, "output": 2.5, "source": "static_config"},
    "openai/gpt-5.4": {"input": 2.5, "output": 2.5, "source": "static_config"},
    "qwen/qwen3-8b": {"input": 0.05, "output": 0.05, "source": "static_config"},
    "qwen/qwen-2.5-72b-instruct": {"input": 0.36, "output": 0.40, "source": "static_config"},
}


def _utc_now() -> datetime:
    """Handle utc now."""
    return datetime.now(timezone.utc)


def _as_plain_dict(event: Any) -> dict[str, Any]:
    """Handle as plain dict."""
    if is_dataclass(event):
        data = asdict(event)
    elif isinstance(event, dict):
        data = dict(event)
    else:
        data = dict(getattr(event, "__dict__", {}) or {})

    event_type = data.get("event_type")
    if isinstance(event_type, Enum):
        data["event_type"] = event_type.value
    elif event_type is not None:
        data["event_type"] = str(event_type)
    return data


def _safe_int(value: Any) -> int | None:
    """Handle safe int."""
    try:
        if value is None or value == "":
            return None
        parsed = int(float(value))
        return parsed if parsed >= 0 else None
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    """Handle safe float."""
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
        return parsed if parsed >= 0 else None
    except Exception:
        return None


def _content_len(data: dict[str, Any]) -> int:
    """Handle content len."""
    lengths = []
    for key in ("content", "raw_output", "thinking", "input_data"):
        value = data.get(key)
        if isinstance(value, str):
            lengths.append(len(value))
    return max(lengths or [0])


def _error_hash(error: Any) -> str | None:
    """Handle error hash."""
    if not error:
        return None
    digest = hashlib.sha1(str(error).encode("utf-8", errors="ignore")).hexdigest()
    return digest[:12]


def _extract_error_code(data: dict[str, Any]) -> str:
    """Handle extract error code."""
    explicit = str(data.get("error_code") or "").strip()
    if explicit:
        return explicit
    for key in ("error", "title", "content"):
        text = str(data.get(key) or "")
        match = re.search(r"\[(YOURAI-\d+)\]", text)
        if match:
            return match.group(1)
    return ""


def _metric_kind(event_type: str, status: str) -> str | None:
    """Handle metric kind."""
    if event_type == "system_info":
        return None
    if event_type == "pipeline_end":
        return "request"
    if event_type == "node_end":
        return "node_latency"
    if event_type == "llm_response":
        return "llm_latency"
    if event_type in _ERROR_EVENTS or status == "error":
        return "error"
    return None


def _metric_from_event(event: Any) -> dict[str, Any] | None:
    """Handle metric from event."""
    data = _as_plain_dict(event)
    event_type = str(data.get("event_type") or "")
    status = str(data.get("status") or "info")
    metric_name = str(data.get("metric_name") or "")
    kind = metric_name or _metric_kind(event_type, status)
    if not kind:
        return None

    duration_ms = _safe_int(data.get("duration_ms"))
    if (event_type in _DURATION_EVENTS or metric_name) and duration_ms is None:
        return None

    now = _utc_now()
    node_name = str(data.get("node_name") or "unknown")
    model = data.get("model") or data.get("expert_model")
    error = data.get("error")
    return {
        "ts": now.isoformat(),
        "day": now.strftime("%Y-%m-%d"),
        "hour": now.strftime("%Y-%m-%dT%H:00:00Z"),
        "event_type": event_type,
        "kind": kind,
        "metric_name": metric_name,
        "node_name": node_name,
        "model": str(model) if model else "",
        "duration_ms": duration_ms,
        "ttft_ms": _safe_int(data.get("ttft_ms")),
        "prompt_tokens": _safe_int(data.get("prompt_tokens")),
        "completion_tokens": _safe_int(data.get("completion_tokens")),
        "total_tokens": _safe_int(data.get("total_tokens")),
        "output_tokens_per_sec": _safe_float(data.get("output_tokens_per_sec")),
        "estimated_cost_usd": _safe_float(data.get("estimated_cost_usd")),
        "cost_source": str(data.get("cost_source") or ""),
        "input_cost_usd_per_m": _safe_float(data.get("input_cost_usd_per_m")),
        "output_cost_usd_per_m": _safe_float(data.get("output_cost_usd_per_m")),
        "audio_duration_sec": _safe_float(data.get("audio_duration_sec")),
        "result_count": _safe_int(data.get("result_count")),
        "candidate_count": _safe_int(data.get("candidate_count")),
        "cache_hit": bool(data.get("cache_hit")) if data.get("cache_hit") is not None else None,
        "status": status,
        "source": str(data.get("source") or ""),
        "for_user": str(data.get("for_user") or ""),
        "tracking_id": str(data.get("tracking_id") or ""),
        "expert_domain": str(data.get("expert_domain") or ""),
        "expert_model": str(data.get("expert_model") or ""),
        "expert_pass": str(data.get("expert_pass") or ""),
        "fallback_reason": str(data.get("fallback_reason") or ""),
        "content_chars": _safe_int(data.get("content_chars")) if data.get("content_chars") is not None else _content_len(data),
        "error_hash": _error_hash(error),
        "error_code": _extract_error_code(data),
        "error_module": str(data.get("error_module") or data.get("module") or node_name or ""),
        "error_type": str(data.get("error_type") or ""),
        "error_id": str(data.get("error_id") or ""),
        "is_seen": bool(data.get("is_seen")) if data.get("is_seen") is not None else None,
        "repeat_count": _safe_int(data.get("repeat_count")),
        "first_seen_at": str(data.get("first_seen_at") or ""),
        "last_seen_at": str(data.get("last_seen_at") or ""),
    }


def _rotate_if_needed() -> None:
    """Handle rotate if needed."""
    try:
        if not os.path.exists(METRICS_FILE):
            return
        if os.path.getsize(METRICS_FILE) <= _MAX_FILE_BYTES:
            return
        with open(METRICS_FILE, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        keep = lines[-_ROTATE_KEEP_LINES:]
        with open(METRICS_FILE, "w", encoding="utf-8") as handle:
            handle.writelines(keep)
    except Exception:
        return


def _load_all_metric_lines() -> list[dict[str, Any]]:
    """Load all metric lines."""
    if not os.path.exists(METRICS_FILE):
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _write_metric_lines(rows: list[dict[str, Any]]) -> None:
    """Handle write metric lines."""
    os.makedirs(_ANALYTICS_DIR, exist_ok=True)
    tmp_file = METRICS_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp_file, METRICS_FILE)


def _load_rollups() -> dict[str, Any]:
    """Load rollups."""
    if not os.path.exists(DAILY_ROLLUP_FILE):
        return {"version": 1, "days": {}}
    try:
        with open(DAILY_ROLLUP_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"version": 1, "days": {}}
    if not isinstance(data, dict):
        return {"version": 1, "days": {}}
    data.setdefault("version", 1)
    if not isinstance(data.get("days"), dict):
        data["days"] = {}
    return data


def _save_rollups(data: dict[str, Any]) -> None:
    """Save rollups."""
    os.makedirs(_ANALYTICS_DIR, exist_ok=True)
    data["updated_at"] = _utc_now().isoformat()
    tmp_file = DAILY_ROLLUP_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DAILY_ROLLUP_FILE)


def _counter_dict(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    """Handle counter dict."""
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get(key) or "unknown")
        counts[name] = counts.get(name, 0) + 1
    return counts


def _price_record(input_cost: Any, output_cost: Any = None, source: str = "unknown") -> dict[str, Any] | None:
    """Handle price record."""
    in_cost = _safe_float(input_cost)
    out_cost = _safe_float(output_cost)
    if out_cost is None:
        out_cost = in_cost
    if in_cost is None and out_cost is None:
        return None
    return {
        "input_usd_per_m": in_cost,
        "output_usd_per_m": out_cost,
        "source": source,
    }


def _add_price(catalog: dict[str, dict[str, Any]], model: Any, price: dict[str, Any] | None, *, overwrite: bool = False) -> None:
    """Handle add price."""
    model_id = str(model or "").strip()
    if not model_id or not price:
        return
    existing = catalog.get(model_id)
    if existing and not overwrite:
        return
    catalog[model_id] = {
        "model": model_id,
        "input_usd_per_m": price.get("input_usd_per_m"),
        "output_usd_per_m": price.get("output_usd_per_m"),
        "source": price.get("source") or "unknown",
    }


def _configured_models_from_config_source() -> dict[str, set[str]]:
    """Handle configured models from config source."""
    roles: dict[str, set[str]] = {}
    config_path = os.path.join(_BASE_DIR, "core", "config.py")
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return roles

    constants: dict[str, str] = {}
    for match in re.finditer(r"^(OPENROUTER_MODEL[A-Z0-9_]*|MODEL_[A-Z0-9_]+|HIPPOCAMPUS_EMBEDDING_OPENROUTER)\s*=\s*\"([^\"]+)\"", text, re.M):
        constants[match.group(1)] = match.group(2)
    for match in re.finditer(r"^(OPENROUTER_MODEL[A-Z0-9_]*|MODEL_[A-Z0-9_]+|HIPPOCAMPUS_EMBEDDING_OPENROUTER)\s*=\s*([A-Z0-9_]+)", text, re.M):
        target = constants.get(match.group(2))
        if target:
            constants[match.group(1)] = target

    for name, model_id in constants.items():
        role = name.lower().replace("openrouter_model_", "").replace("model_", "")
        roles.setdefault(model_id, set()).add(role)
    return roles


def _load_price_cache() -> dict[str, Any]:
    """Load price cache."""
    if not os.path.exists(PRICE_CACHE_FILE):
        return {}
    try:
        with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_price_cache(data: dict[str, Any]) -> None:
    """Save price cache."""
    try:
        os.makedirs(_ANALYTICS_DIR, exist_ok=True)
        data["updated_at"] = _utc_now().isoformat()
        tmp_file = PRICE_CACHE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_file, PRICE_CACHE_FILE)
    except Exception:
        pass


def _openrouter_price_catalog(max_age_hours: int = 24) -> dict[str, dict[str, Any]]:
    """Handle openrouter price catalog."""
    cache = _load_price_cache()
    updated_at = _parse_ts(cache.get("updated_at"))
    if updated_at and updated_at > _utc_now() - timedelta(hours=max_age_hours):
        cached_prices = cache.get("openrouter") or {}
        if isinstance(cached_prices, dict):
            return cached_prices

    try:
        import requests
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=8)
        if resp.status_code != 200:
            return cache.get("openrouter") or {}
        prices: dict[str, dict[str, Any]] = {}
        for model in resp.json().get("data", []):
            model_id = str(model.get("id") or "").strip()
            pricing = model.get("pricing") or {}
            input_cost = _safe_float(pricing.get("prompt"))
            output_cost = _safe_float(pricing.get("completion"))
            record = _price_record(
                input_cost * 1_000_000 if input_cost is not None else None,
                output_cost * 1_000_000 if output_cost is not None else None,
                "openrouter_api",
            )
            if model_id and record:
                prices[model_id] = record
        if prices:
            cache["openrouter"] = prices
            _save_price_cache(cache)
        return prices or (cache.get("openrouter") or {})
    except Exception:
        cached_prices = cache.get("openrouter") or {}
        return cached_prices if isinstance(cached_prices, dict) else {}


def build_cost_catalog() -> dict[str, Any]:
    """Best-effort model price catalog used by analytics and config UI."""
    catalog: dict[str, dict[str, Any]] = {}
    configured_models: dict[str, set[str]] = {}

    for model_id, price in _STATIC_MODEL_COSTS_USD_PER_M.items():
        _add_price(
            catalog,
            model_id,
            _price_record(price.get("input"), price.get("output"), price.get("source") or "static_config"),
        )

    for model_id, price in _openrouter_price_catalog().items():
        _add_price(catalog, model_id, price, overwrite=True)

    try:
        from tools.expert_pool import load_pool
        pool = load_pool(create_if_missing=False)
        for domain, info in (pool.get("domains") or {}).items():
            for model in info.get("models") or []:
                model_id = str(model.get("id") or "").strip()
                configured_models.setdefault(model_id, set()).add(str(domain))
                cost = _safe_float(model.get("effective_cost_usd_per_m"))
                if cost is not None:
                    _add_price(
                        catalog,
                        model_id,
                        _price_record(cost, cost, str(model.get("source") or pool.get("source") or "expert_pool")),
                        overwrite=True,
                    )
    except Exception:
        pass

    try:
        import config as _cfg
        for model_id, roles in _configured_models_from_config_source().items():
            configured_models.setdefault(model_id, set()).update(roles)
        config_sources = {
            "yourai": getattr(_cfg, "MODEL_YOURAI_OPENROUTER", None),
            "router": getattr(_cfg, "OPENROUTER_MODEL_ROUTER", None),
            "subconscious": getattr(_cfg, "OPENROUTER_MODEL_SUBCONSCIOUS", None),
            "style": getattr(_cfg, "OPENROUTER_MODEL_STYLE", None),
            "promise": getattr(_cfg, "OPENROUTER_MODEL_PROMISE", None),
            "coherence": getattr(_cfg, "OPENROUTER_MODEL_COHERENCE", None),
            "memory_llm": getattr(_cfg, "OPENROUTER_MODEL_MEMORY", None),
            "hippocampus_embedding": getattr(_cfg, "HIPPOCAMPUS_EMBEDDING_OPENROUTER", None),
        }
        for role, model_id in config_sources.items():
            if model_id:
                configured_models.setdefault(str(model_id), set()).add(role)

        for domain, model_id in (getattr(_cfg, "EXPERT_OPENROUTER_OVERRIDES", {}) or {}).items():
            if model_id:
                configured_models.setdefault(str(model_id), set()).add(f"expert:{domain}")
        for domain, chain in (getattr(_cfg, "EXPERT_FALLBACK_CHAINS", {}) or {}).items():
            for model_id in chain or []:
                configured_models.setdefault(str(model_id), set()).add(f"fallback:{domain}")
    except Exception:
        for model_id, roles in _configured_models_from_config_source().items():
            configured_models.setdefault(model_id, set()).update(roles)

    unknown = []
    for model_id, roles in configured_models.items():
        if model_id and model_id not in catalog:
            unknown.append({"model": model_id, "roles": sorted(roles), "source": "config"})

    return {
        "models": sorted(catalog.values(), key=lambda item: item["model"]),
        "unknown_models": sorted(unknown, key=lambda item: item["model"]),
    }


def get_model_cost(model_id: str) -> dict[str, Any] | None:
    """Return model cost."""
    catalog = build_cost_catalog()
    for item in catalog.get("models", []):
        if item.get("model") == model_id:
            return item
    return None


def _estimate_llm_row_cost(row: dict[str, Any], price_by_model: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Handle estimate llm row cost."""
    model = str(row.get("model") or row.get("expert_model") or "").strip()
    prompt_tokens = _safe_int(row.get("prompt_tokens")) or 0
    completion_tokens = _safe_int(row.get("completion_tokens")) or 0
    total_tokens = _safe_int(row.get("total_tokens")) or (prompt_tokens + completion_tokens)
    price = price_by_model.get(model)
    if not model or not total_tokens or not price:
        return {
            "model": model or "unknown",
            "known": False,
            "tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": 0.0,
            "source": "unknown",
        }

    input_cost = _safe_float(price.get("input_usd_per_m"))
    output_cost = _safe_float(price.get("output_usd_per_m"))
    if input_cost is None and output_cost is None:
        known = False
        cost = 0.0
    elif prompt_tokens or completion_tokens:
        known = True
        cost = (prompt_tokens / 1_000_000) * (input_cost or output_cost or 0.0)
        cost += (completion_tokens / 1_000_000) * (output_cost or input_cost or 0.0)
    else:
        known = True
        effective = input_cost if input_cost is not None else output_cost or 0.0
        cost = (total_tokens / 1_000_000) * effective

    return {
        "model": model,
        "known": known,
        "tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(cost, 8),
        "source": str(price.get("source") or "unknown"),
        "input_usd_per_m": input_cost,
        "output_usd_per_m": output_cost,
    }


def _rows_with_inferred_request_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill missing llm source/user from surrounding pipeline events.

    Older LLM metrics did not carry source/for_user. Pipeline end does include
    the request duration, so rows inside that request window can be attributed
    without rewriting historical metrics.
    """
    requests: list[tuple[datetime, datetime, str, str]] = []
    for row in rows:
        if row.get("kind") != "request":
            continue
        end_ts = _parse_ts(row.get("ts"))
        duration_ms = _safe_int(row.get("duration_ms")) or 0
        if not end_ts or duration_ms <= 0:
            continue
        source = str(row.get("source") or "").strip()
        user = str(row.get("for_user") or "").strip()
        if not source and not user:
            continue
        start_ts = end_ts - timedelta(milliseconds=duration_ms + 2000)
        requests.append((start_ts, end_ts + timedelta(milliseconds=1000), source, user))

    if not requests:
        return rows

    requests.sort(key=lambda item: item[1])
    enriched: list[dict[str, Any]] = []
    for row in rows:
        is_cost_row = row.get("estimated_cost_usd") is not None or row.get("cost_source")
        if row.get("kind") != "llm_latency" and not is_cost_row:
            enriched.append(row)
            continue
        if row.get("for_user") and (row.get("source") or row.get("request_source")):
            enriched.append(row)
            continue
        ts = _parse_ts(row.get("ts"))
        if not ts:
            enriched.append(row)
            continue
        match = None
        for start_ts, end_ts, source, user in requests:
            if start_ts <= ts <= end_ts:
                match = (source, user)
                break
        if not match:
            enriched.append(row)
            continue
        patched = dict(row)
        if not patched.get("source") and match[0]:
            patched["source"] = match[0]
        if is_cost_row and match[0]:
            patched["request_source"] = match[0]
        if not patched.get("for_user") and match[1]:
            patched["for_user"] = match[1]
        enriched.append(patched)
    return enriched


def _cost_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Handle cost summary."""
    rows = _rows_with_inferred_request_context(rows)
    catalog = build_cost_catalog()
    price_by_model = {item["model"]: item for item in catalog.get("models", [])}
    llm_rows = [
        row for row in rows
        if row.get("kind") == "llm_latency" and (_safe_int(row.get("total_tokens")) or _safe_int(row.get("prompt_tokens")))
    ]

    by_model: dict[str, dict[str, Any]] = {}
    by_user: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    by_day: dict[str, dict[str, Any]] = {}
    unknown_by_model: dict[str, dict[str, Any]] = {}
    known_usd = 0.0
    known_tokens = 0
    unknown_tokens = 0

    for row in llm_rows:
        item = _estimate_llm_row_cost(row, price_by_model)
        target = by_model if item["known"] else unknown_by_model
        bucket = target.setdefault(item["model"], {
            "name": item["model"],
            "cost_usd": 0.0,
            "tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "source": item.get("source") or "unknown",
            "input_usd_per_m": item.get("input_usd_per_m"),
            "output_usd_per_m": item.get("output_usd_per_m"),
            "count": 0,
        })
        bucket["cost_usd"] += item["cost_usd"]
        bucket["tokens"] += item["tokens"]
        bucket["prompt_tokens"] += item["prompt_tokens"]
        bucket["completion_tokens"] += item["completion_tokens"]
        bucket["count"] += 1
        if item["known"]:
            known_usd += item["cost_usd"]
            known_tokens += item["tokens"]
            for key, buckets, fallback in (
                (str(row.get("for_user") or "unknown"), by_user, "unknown"),
                (str(row.get("request_source") or row.get("source") or "unknown"), by_source, "unknown"),
                (str(row.get("day") or "unknown"), by_day, "unknown"),
            ):
                bucket = buckets.setdefault(key or fallback, {
                    "name": key or fallback,
                    "cost_usd": 0.0,
                    "tokens": 0,
                    "count": 0,
                    "source": "rollup",
                })
                bucket["cost_usd"] += item["cost_usd"]
                bucket["tokens"] += item["tokens"]
                bucket["count"] += 1
        else:
            unknown_tokens += item["tokens"]

    service_rows = [row for row in rows if row.get("estimated_cost_usd") is not None or row.get("cost_source")]
    by_service: dict[str, dict[str, Any]] = {}
    unknown_services: dict[str, dict[str, Any]] = {}
    service_usd = 0.0
    for row in service_rows:
        name = str(row.get("model") or row.get("node_name") or row.get("kind") or "service")
        est = _safe_float(row.get("estimated_cost_usd"))
        target = by_service if est is not None else unknown_services
        bucket = target.setdefault(name, {
            "name": name,
            "cost_usd": 0.0,
            "count": 0,
            "source": str(row.get("cost_source") or row.get("source") or "unknown"),
            "content_chars": 0,
            "audio_duration_sec": 0.0,
        })
        bucket["count"] += 1
        bucket["content_chars"] += _safe_int(row.get("content_chars")) or 0
        bucket["audio_duration_sec"] += _safe_float(row.get("audio_duration_sec")) or 0.0
        if est is not None:
            bucket["cost_usd"] += est
            service_usd += est
            user_key = str(row.get("for_user") or "unknown")
            source_key = str(row.get("request_source") or row.get("source") or row.get("node_name") or "unknown")
            day_key = str(row.get("day") or "unknown")
            for key, buckets in ((user_key, by_user), (source_key, by_source), (day_key, by_day)):
                rolled = buckets.setdefault(key, {
                    "name": key,
                    "cost_usd": 0.0,
                    "tokens": 0,
                    "count": 0,
                    "source": "rollup",
                })
                rolled["cost_usd"] += est
                rolled["count"] += 1

    def _finish_cost_items(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """Handle finish cost items."""
        output = []
        for item in items.values():
            item = dict(item)
            item["cost_usd"] = round(float(item.get("cost_usd") or 0.0), 6)
            if "audio_duration_sec" in item:
                item["audio_duration_sec"] = round(float(item.get("audio_duration_sec") or 0.0), 2)
            output.append(item)
        output.sort(key=lambda x: (x.get("cost_usd") or 0.0, x.get("tokens") or 0), reverse=True)
        return output

    return {
        "total_usd": round(known_usd + service_usd, 6),
        "llm_usd": round(known_usd, 6),
        "service_usd": round(service_usd, 6),
        "known_tokens": known_tokens,
        "unknown_tokens": unknown_tokens,
        "tracked_llm_calls": len(llm_rows),
        "known_model_count": len(by_model),
        "unknown_model_count": len(unknown_by_model),
        "by_model": _finish_cost_items(by_model)[:12],
        "by_user": _finish_cost_items(by_user)[:12],
        "by_source": _finish_cost_items(by_source)[:12],
        "by_day": _finish_cost_items(by_day)[:14],
        "unknown_models": _finish_cost_items(unknown_by_model)[:12],
        "by_service": _finish_cost_items(by_service)[:12],
        "unknown_services": _finish_cost_items(unknown_services)[:12],
        "catalog": {
            "priced_models": len(catalog.get("models", [])),
            "configured_unknown_models": len(catalog.get("unknown_models", [])),
            "unknown_config_models": catalog.get("unknown_models", [])[:16],
        },
    }


def _daily_rollup(day: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Handle daily rollup."""
    requests = [row for row in rows if row.get("kind") == "request"]
    errors = [row for row in rows if row.get("kind") == "error"]
    llm = [row for row in rows if row.get("kind") == "llm_latency"]
    memory = [
        row for row in rows
        if row.get("kind") in ("memory_search", "memory_write")
        or (row.get("kind") == "node_latency" and "memory" in str(row.get("node_name") or ""))
    ]
    expert = [row for row in rows if row.get("kind") == "expert_total"]
    return {
        "day": day,
        "count": len(rows),
        "requests": len(requests),
        "errors": len(errors),
        "error_rate": round(len(errors) / max(1, len(requests)), 4) if requests else 0.0,
        "e2e_ms": _stats(_durations(requests, lambda _: True)),
        "llm_ms": _stats(_durations(llm, lambda _: True)),
        "memory_ms": _stats(_durations(memory, lambda _: True)),
        "expert_ms": _stats(_durations(expert, lambda _: True)),
        "error_codes": _counter_dict(errors, "error_code"),
        "sources": _counter_dict(requests, "source"),
        "models": _counter_dict(llm, "model"),
    }


def prune_metrics_retention(force: bool = False) -> dict[str, Any]:
    """Keep raw metrics for 30 days and roll up days older than 7 days."""
    try:
        rows = _load_all_metric_lines()
        if not rows:
            return {"kept": 0, "removed": 0, "rolled_days": 0}

        now = _utc_now()
        cutoff = now - timedelta(days=_RETENTION_DAYS)
        rollup_cutoff = now - timedelta(days=_ROLLUP_AFTER_DAYS)
        kept: list[dict[str, Any]] = []
        old_by_day: dict[str, list[dict[str, Any]]] = {}
        removed = 0

        for row in rows:
            ts = _parse_ts(row.get("ts"))
            if not ts:
                kept.append(row)
                continue
            if ts < cutoff:
                removed += 1
                continue
            if ts < rollup_cutoff:
                old_by_day.setdefault(str(row.get("day") or ts.strftime("%Y-%m-%d")), []).append(row)
            kept.append(row)

        rollups = _load_rollups()
        for day, day_rows in old_by_day.items():
            if force or day not in rollups["days"]:
                rollups["days"][day] = _daily_rollup(day, day_rows)
        if old_by_day:
            _save_rollups(rollups)

        if removed:
            _write_metric_lines(kept)
        return {"kept": len(kept), "removed": removed, "rolled_days": len(old_by_day)}
    except Exception:
        return {"kept": 0, "removed": 0, "rolled_days": 0, "error": True}


def clear_all_metrics() -> dict[str, Any]:
    """Delete all raw metrics, rollups, alerts, and error inbox. Returns summary."""
    removed = {}
    for name, path in [
        ("metrics", METRICS_FILE),
        ("alerts", ALERTS_FILE),
        ("rollups", DAILY_ROLLUP_FILE),
        ("error_inbox", ERROR_INBOX_FILE),
    ]:
        try:
            if os.path.exists(path):
                size = os.path.getsize(path)
                os.remove(path)
                removed[name] = size
        except OSError:
            removed[name] = "error"
    return {"cleared": removed}


def record_event(event: Any) -> None:
    """Append one condensed analytics metric. Never raises."""
    try:
        metric = _metric_from_event(event)
        if not metric:
            return
        os.makedirs(_ANALYTICS_DIR, exist_ok=True)
        with open(METRICS_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(metric, ensure_ascii=False, separators=(",", ":")) + "\n")
        _rotate_if_needed()
        prune_metrics_retention()
    except Exception:
        return


def _parse_ts(value: Any) -> datetime | None:
    """Handle parse ts."""
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def load_metrics(hours: int = 24) -> list[dict[str, Any]]:
    """Load metrics."""
    hours = max(1, min(int(hours or 24), 24 * 14))
    cutoff = _utc_now() - timedelta(hours=hours)
    if not os.path.exists(METRICS_FILE):
        return []

    rows: list[dict[str, Any]] = []
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = _parse_ts(row.get("ts"))
                if ts and ts >= cutoff:
                    rows.append(row)
    except Exception:
        return []
    return rows


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    user: str | None = None,
    source: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Handle filter rows."""
    user = str(user or "").strip()
    source = str(source or "").strip()
    model = str(model or "").strip()
    if not user and not source and not model:
        return rows

    def _matches(row: dict[str, Any]) -> bool:
        """Handle matches."""
        if user and str(row.get("for_user") or "") != user:
            return False
        if source and str(row.get("source") or "") != source:
            return False
        if model:
            row_model = str(row.get("model") or row.get("expert_model") or "")
            if row_model != model:
                return False
        return True

    return [row for row in rows if _matches(row)]


def _filter_options(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Handle filter options."""
    users = sorted({str(row.get("for_user") or "").strip() for row in rows if str(row.get("for_user") or "").strip()})
    sources = sorted({str(row.get("source") or "").strip() for row in rows if str(row.get("source") or "").strip()})
    models = sorted({
        str(row.get("model") or row.get("expert_model") or "").strip()
        for row in rows
        if str(row.get("model") or row.get("expert_model") or "").strip()
    })
    return {
        "users": users[:80],
        "sources": sources[:80],
        "models": models[:120],
    }


def _durations(rows: Iterable[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> list[int]:
    """Handle durations."""
    values: list[int] = []
    for row in rows:
        if not predicate(row):
            continue
        duration = _safe_int(row.get("duration_ms"))
        if duration is not None:
            values.append(duration)
    return values


def _percentile(values: list[int], pct: float) -> int | None:
    """Handle percentile."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[int(pos)]
    return int(round(ordered[low] + (ordered[high] - ordered[low]) * (pos - low)))


def _stats(values: list[int]) -> dict[str, Any]:
    """Handle stats."""
    if not values:
        return {"count": 0, "avg": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "avg": int(round(sum(values) / len(values))),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _float_stats(values: list[float]) -> dict[str, Any]:
    """Handle float stats."""
    if not values:
        return {"count": 0, "avg": None, "p50": None, "p95": None, "max": None}
    scaled = [int(round(v * 100)) for v in values]
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "p50": round((_percentile(scaled, 0.50) or 0) / 100, 2),
        "p95": round((_percentile(scaled, 0.95) or 0) / 100, 2),
        "max": round(max(values), 2),
    }


def _p95(rows: Iterable[dict[str, Any]], key: str = "duration_ms") -> int | None:
    """Handle p95."""
    values = [
        value for value in (_safe_int(row.get(key)) for row in rows)
        if value is not None
    ]
    return _stats(values)["p95"]


def _cache_stats(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Handle cache stats."""
    values = [row.get("cache_hit") for row in rows if row.get("cache_hit") is not None]
    total = len(values)
    hits = sum(1 for value in values if value is True)
    misses = total - hits
    return {
        "total": total,
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hits / total, 4) if total else None,
    }


def _load_error_inbox_records() -> list[dict[str, Any]]:
    """Load error inbox records."""
    try:
        if not os.path.exists(ERROR_INBOX_FILE):
            return []
        with open(ERROR_INBOX_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = data.get("errors") or []
    else:
        records = []
    return [item for item in records if isinstance(item, dict)]


def _error_inbox_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Handle error inbox stats."""
    total = len(records)
    unseen = [
        item for item in records
        if not (item.get("is_seen") or item.get("isSeen") or item.get("notified_at"))
    ]
    repeated = [item for item in records if (_safe_int(item.get("count")) or 0) > 1]
    return {
        "total": total,
        "unseen": len(unseen),
        "seen": total - len(unseen),
        "repeated": len(repeated),
    }


def _top_repeated_errors(records: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Handle top repeated errors."""
    items = []
    for item in records:
        count = _safe_int(item.get("count")) or 0
        if count <= 1:
            continue
        code = str(item.get("code") or item.get("id") or "ERROR")
        module = str(item.get("module") or "unknown")
        seen = bool(item.get("is_seen") or item.get("isSeen") or item.get("notified_at"))
        items.append({
            "name": f"{code} | {module}",
            "count": count,
            "seen": seen,
            "last_seen": str(item.get("last_seen") or ""),
        })
    items.sort(key=lambda item: (item["count"], item.get("last_seen") or ""), reverse=True)
    return items[:limit]


def _load_alert_store() -> dict[str, Any]:
    """Load alert store."""
    if not os.path.exists(ALERTS_FILE):
        return {"version": 1, "alerts": []}
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"version": 1, "alerts": []}
    if not isinstance(data, dict):
        return {"version": 1, "alerts": []}
    data.setdefault("version", 1)
    if not isinstance(data.get("alerts"), list):
        data["alerts"] = []
    return data


def _save_alert_store(data: dict[str, Any]) -> None:
    """Save alert store."""
    os.makedirs(_ANALYTICS_DIR, exist_ok=True)
    data["updated_at"] = _utc_now().isoformat()
    tmp_file = ALERTS_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_file, ALERTS_FILE)


def _alert_id(alert_type: str, title: str) -> str:
    """Handle alert id."""
    raw = f"{alert_type}|{title}".lower()
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _upsert_alert(alerts: list[dict[str, Any]], alert: dict[str, Any], now: datetime) -> None:
    """Handle upsert alert."""
    alert_id = _alert_id(alert["type"], alert["title"])
    now_s = now.isoformat()
    cooldown_after = now - timedelta(minutes=_ALERT_COOLDOWN_MINUTES)
    for item in alerts:
        if item.get("id") != alert_id:
            continue
        last_seen = _parse_ts(item.get("last_seen"))
        item["last_seen"] = now_s
        item["count"] = int(item.get("count") or 1) + 1
        item["message"] = alert["message"]
        item["details"] = alert.get("details", {})
        item["severity"] = alert.get("severity", item.get("severity", "warning"))
        if not last_seen or last_seen <= cooldown_after:
            item["is_seen"] = False
            item["isSeen"] = False
            item["seen_at"] = None
        return
    alerts.append({
        "id": alert_id,
        "type": alert["type"],
        "severity": alert.get("severity", "warning"),
        "title": alert["title"],
        "message": alert["message"],
        "details": alert.get("details", {}),
        "first_seen": now_s,
        "last_seen": now_s,
        "count": 1,
        "is_seen": False,
        "isSeen": False,
        "seen_at": None,
        "seen_reason": None,
    })


def evaluate_alerts(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Detect notable analytics conditions and persist one-shot alerts."""
    now = _utc_now()
    rows = rows if rows is not None else load_metrics(6)
    recent_cutoff = now - timedelta(minutes=15)
    baseline_cutoff = now - timedelta(hours=3)
    recent = [row for row in rows if (_parse_ts(row.get("ts")) or now) >= recent_cutoff]
    baseline = [
        row for row in rows
        if baseline_cutoff <= (_parse_ts(row.get("ts")) or now) < recent_cutoff
    ]

    candidates: list[dict[str, Any]] = []

    recent_errors = [row for row in recent if row.get("kind") == "error"]
    baseline_errors = [row for row in baseline if row.get("kind") == "error"]
    recent_error_rate = len(recent_errors) / 15
    baseline_error_rate = len(baseline_errors) / max(1, 180)
    if len(recent_errors) >= 3 and recent_error_rate >= max(0.05, baseline_error_rate * 2.5):
        candidates.append({
            "type": "error_spike",
            "severity": "critical" if len(recent_errors) >= 8 else "warning",
            "title": "Error spike",
            "message": f"{len(recent_errors)} errors in the last 15 minutes.",
            "details": {"recent_errors": len(recent_errors), "baseline_errors": len(baseline_errors)},
        })

    recent_memory = [
        row for row in recent
        if row.get("kind") in ("memory_search", "memory_write")
        or (row.get("kind") == "node_latency" and "memory" in str(row.get("node_name") or ""))
    ]
    baseline_memory = [
        row for row in baseline
        if row.get("kind") in ("memory_search", "memory_write")
        or (row.get("kind") == "node_latency" and "memory" in str(row.get("node_name") or ""))
    ]
    memory_p95 = _p95(recent_memory)
    memory_base_p95 = _p95(baseline_memory)
    if memory_p95 is not None and memory_p95 >= max(2500, int((memory_base_p95 or 0) * 2.2)):
        candidates.append({
            "type": "memory_slow",
            "severity": "warning",
            "title": "Memory latency high",
            "message": f"Memory p95 is at {_format_ms(memory_p95)}.",
            "details": {"p95_ms": memory_p95, "baseline_p95_ms": memory_base_p95},
        })

    recent_llm = [row for row in recent if row.get("kind") == "llm_latency"]
    baseline_llm = [row for row in baseline if row.get("kind") == "llm_latency"]
    llm_p95 = _p95(recent_llm)
    llm_base_p95 = _p95(baseline_llm)
    ttft_p95 = _p95(recent_llm, key="ttft_ms")
    if (
        (llm_p95 is not None and llm_p95 >= max(45000, int((llm_base_p95 or 0) * 2.0)))
        or (ttft_p95 is not None and ttft_p95 >= 12000)
    ):
        candidates.append({
            "type": "openrouter_slow",
            "severity": "warning",
            "title": "OpenRouter unusually slow",
            "message": f"LLM p95 {_format_ms(llm_p95)} / TTFT p95 {_format_ms(ttft_p95)}.",
            "details": {"llm_p95_ms": llm_p95, "baseline_p95_ms": llm_base_p95, "ttft_p95_ms": ttft_p95},
        })

    noisy_fallbacks = [
        row for row in recent
        if row.get("kind") == "expert_call"
        and row.get("fallback_reason")
        and row.get("fallback_reason") not in ("primary", "direct_answer", "single_pass")
    ]
    if len(noisy_fallbacks) >= 3:
        candidates.append({
            "type": "expert_fallback_spike",
            "severity": "warning",
            "title": "Expert fallback spike",
            "message": f"{len(noisy_fallbacks)} expert fallbacks in the last 15 minutes.",
            "details": {"fallbacks": len(noisy_fallbacks)},
        })

    data = _load_alert_store()
    alerts = data["alerts"]
    for alert in candidates:
        _upsert_alert(alerts, alert, now)
    alerts.sort(key=lambda item: item.get("last_seen") or "", reverse=True)
    data["alerts"] = alerts[:100]
    if candidates:
        _save_alert_store(data)

    active = [
        item for item in data["alerts"]
        if (_parse_ts(item.get("last_seen")) or now) >= now - timedelta(hours=2)
    ]
    unseen = [
        item for item in active
        if not (item.get("is_seen") or item.get("isSeen"))
    ]
    return {
        "active": active[:8],
        "unseen": unseen[:8],
        "active_count": len(active),
        "unseen_count": len(unseen),
        "evaluated": len(candidates),
    }


def pop_unseen_alerts(max_items: int = 5, mark_seen: bool = True, seen_reason: str = "yourai_prompt") -> list[dict[str, Any]]:
    """Handle pop unseen alerts."""
    data = _load_alert_store()
    alerts = data["alerts"]
    unseen = [item for item in alerts if not (item.get("is_seen") or item.get("isSeen"))]
    unseen = sorted(unseen, key=lambda item: item.get("first_seen") or "")[:max_items]
    if mark_seen and unseen:
        now_s = _utc_now().isoformat()
        ids = {item.get("id") for item in unseen}
        for item in alerts:
            if item.get("id") in ids:
                item["is_seen"] = True
                item["isSeen"] = True
                item["seen_at"] = item.get("seen_at") or now_s
                item["seen_reason"] = seen_reason
        _save_alert_store(data)
    return [dict(item) for item in unseen]


def format_alert_records(records: list[dict[str, Any]]) -> str:
    """Format alert records."""
    lines = []
    for item in records:
        severity = str(item.get("severity") or "warning").upper()
        title = str(item.get("title") or item.get("type") or "Alert")
        message = str(item.get("message") or "")
        count = int(item.get("count") or 1)
        suffix = f" (x{count})" if count > 1 else ""
        lines.append(f"- [{severity}] {title}{suffix}: {message}")
    return "\n".join(lines)


def _format_ms(value: Any) -> str:
    """Format ms."""
    parsed = _safe_int(value)
    if parsed is None:
        return "n/a"
    if parsed >= 1000:
        return f"{parsed / 1000:.1f}s"
    return f"{parsed}ms"


def _counter(rows: Iterable[dict[str, Any]], key: str, limit: int = 8) -> list[dict[str, Any]]:
    """Handle counter."""
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get(key) or "unknown")
        if name == "":
            name = "unknown"
        counts[name] = counts.get(name, 0) + 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _group_duration_stats(
    rows: Iterable[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    key_fn: Callable[[dict[str, Any]], str],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Handle group duration stats."""
    grouped: dict[str, list[int]] = {}
    for row in rows:
        if not predicate(row):
            continue
        duration = _safe_int(row.get("duration_ms"))
        if duration is None:
            continue
        key = key_fn(row).strip() or "unknown"
        grouped.setdefault(key, []).append(duration)

    items = []
    for key, values in grouped.items():
        stat = _stats(values)
        stat["name"] = key
        items.append(stat)
    items.sort(key=lambda item: (item.get("p95") or 0, item.get("avg") or 0), reverse=True)
    return items[:limit]


def build_summary(
    hours: int = 24,
    *,
    user: str | None = None,
    source: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build summary."""
    all_rows = load_metrics(hours)
    rows = _filter_rows(all_rows, user=user, source=source, model=model)
    retention = prune_metrics_retention()
    error_inbox_records = _load_error_inbox_records()
    alerts = evaluate_alerts(rows)
    requests = [r for r in rows if r.get("kind") == "request"]
    errors = [r for r in rows if r.get("kind") == "error"]
    node_rows = [r for r in rows if r.get("kind") == "node_latency"]
    llm_rows = [r for r in rows if r.get("kind") == "llm_latency"]
    diary_rows = [r for r in rows if r.get("kind") == "diary_rag"]
    memory_search_rows = [r for r in rows if r.get("kind") == "memory_search"]
    memory_write_rows = [r for r in rows if r.get("kind") == "memory_write"]
    tts_cache_rows = [r for r in rows if r.get("kind") == "tts_cache"]
    tts_cache_upload_rows = [r for r in rows if r.get("kind") == "tts_cache_upload"]
    expert_call_rows = [r for r in rows if r.get("kind") == "expert_call"]
    expert_total_rows = [r for r in rows if r.get("kind") == "expert_total"]
    e2e = _durations(requests, lambda _: True)
    llm_values = _durations(llm_rows, lambda _: True)
    ttft_values = [
        value for value in (_safe_int(row.get("ttft_ms")) for row in llm_rows)
        if value is not None
    ]
    tps_values = [
        value for value in (_safe_float(row.get("output_tokens_per_sec")) for row in llm_rows)
        if value is not None
    ]
    memory_values = _durations(node_rows, lambda r: "memory" in str(r.get("node_name") or ""))
    expert_values = _durations(expert_total_rows, lambda _: True) or _durations(node_rows, lambda r: "expert" in str(r.get("node_name") or ""))
    token_totals = {
        "prompt": sum(_safe_int(row.get("prompt_tokens")) or 0 for row in llm_rows),
        "completion": sum(_safe_int(row.get("completion_tokens")) or 0 for row in llm_rows),
        "total": sum(_safe_int(row.get("total_tokens")) or 0 for row in llm_rows),
    }
    diary_result_counts = [
        value for value in (_safe_int(row.get("result_count")) for row in diary_rows)
        if value is not None
    ]
    memory_result_counts = [
        value for value in (_safe_int(row.get("result_count")) for row in memory_search_rows)
        if value is not None
    ]
    costs = _cost_summary(rows)

    latest_ts = max((_parse_ts(r.get("ts")) for r in rows), default=None)
    latest_request_ts = max((_parse_ts(r.get("ts")) for r in requests), default=None)
    error_rate = (len(errors) / max(1, len(requests))) if requests else 0.0

    return {
        "window_hours": max(1, min(int(hours or 24), 24 * 14)),
        "generated_at": _utc_now().isoformat(),
        "filters": {
            "user": str(user or ""),
            "source": str(source or ""),
            "model": str(model or ""),
            "options": _filter_options(all_rows),
        },
        "metrics_file": METRICS_FILE,
        "retention": retention,
        "event_count": len(rows),
        "latest_event_at": latest_ts.isoformat() if latest_ts else None,
        "latest_request_at": latest_request_ts.isoformat() if latest_request_ts else None,
        "requests": len(requests),
        "errors": len(errors),
        "error_rate": round(error_rate, 4),
        "e2e_ms": _stats(e2e),
        "llm_ms": _stats(llm_values),
        "ttft_ms": _stats(ttft_values),
        "output_tokens_per_sec": _float_stats(tps_values),
        "tokens": token_totals,
        "costs": costs,
        "memory_ms": _stats(memory_values),
        "expert_ms": _stats(expert_values),
        "diary_rag_ms": _stats(_durations(diary_rows, lambda _: True)),
        "diary_rag_results": _stats(diary_result_counts),
        "memory_search_ms": _stats(_durations(memory_search_rows, lambda _: True)),
        "memory_search_results": _stats(memory_result_counts),
        "memory_cache": _cache_stats(memory_search_rows),
        "memory_write_ms": _stats(_durations(memory_write_rows, lambda _: True)),
        "tts_cache_ms": _stats(_durations(tts_cache_rows, lambda _: True)),
        "tts_cache": _cache_stats(tts_cache_rows),
        "tts_cache_upload_ms": _stats(_durations(tts_cache_upload_rows, lambda _: True)),
        "node_latency": _group_duration_stats(
            node_rows,
            lambda r: True,
            lambda r: str(r.get("node_name") or "unknown"),
            limit=12,
        ),
        "llm_latency": _group_duration_stats(
            llm_rows,
            lambda r: True,
            lambda r: f"{r.get('node_name') or 'unknown'} | {r.get('model') or 'unknown'}",
            limit=12,
        ),
        "models": _group_duration_stats(
            llm_rows,
            lambda r: bool(r.get("model")),
            lambda r: str(r.get("model") or "unknown"),
            limit=12,
        ),
        "expert_domains": _group_duration_stats(
            expert_total_rows or requests,
            lambda r: bool(r.get("expert_domain")),
            lambda r: str(r.get("expert_domain") or "unknown"),
            limit=12,
        ),
        "expert_models": _group_duration_stats(
            expert_call_rows,
            lambda r: bool(r.get("expert_model") or r.get("model")),
            lambda r: str(r.get("expert_model") or r.get("model") or "unknown"),
            limit=12,
        ),
        "expert_passes": _group_duration_stats(
            expert_call_rows,
            lambda r: bool(r.get("expert_pass")),
            lambda r: f"{r.get('expert_pass') or 'unknown'} | {r.get('expert_domain') or 'unknown'}",
            limit=12,
        ),
        "expert_fallbacks": _counter(
            [r for r in expert_call_rows + expert_total_rows if r.get("fallback_reason")],
            "fallback_reason",
            limit=8,
        ),
        "sources": _counter(requests, "source", limit=8),
        "users": _counter(requests, "for_user", limit=8),
        "error_nodes": _counter(errors, "node_name", limit=8),
        "error_codes": _counter(errors, "error_code", limit=8),
        "error_modules": _counter(errors, "error_module", limit=8),
        "error_types": _counter(errors, "error_type", limit=8),
        "error_inbox": _error_inbox_stats(error_inbox_records),
        "error_repeats": _top_repeated_errors(error_inbox_records, limit=8),
        "alerts": alerts,
    }


def _bucket_start(ts: datetime, bucket_minutes: int) -> datetime:
    """Handle bucket start."""
    minutes_today = ts.hour * 60 + ts.minute
    bucket_total = (minutes_today // bucket_minutes) * bucket_minutes
    hour = bucket_total // 60
    minute = bucket_total % 60
    return ts.replace(hour=hour, minute=minute, second=0, microsecond=0)


def build_timeseries(
    hours: int = 24,
    bucket_minutes: int = 60,
    *,
    user: str | None = None,
    source: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build timeseries."""
    hours = max(1, min(int(hours or 24), 24 * 14))
    bucket_minutes = max(5, min(int(bucket_minutes or 60), 240))
    rows = _filter_rows(load_metrics(hours), user=user, source=source, model=model)
    buckets: dict[str, dict[str, Any]] = {}
    price_by_model = {item["model"]: item for item in build_cost_catalog().get("models", [])}

    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if not ts:
            continue
        bucket_ts = _bucket_start(ts, bucket_minutes)
        key = bucket_ts.isoformat()
        bucket = buckets.setdefault(key, {
            "ts": key,
            "requests": 0,
            "errors": 0,
            "e2e_values": [],
            "node_values": [],
            "memory_values": [],
            "memory_search_values": [],
            "memory_cache_hits": 0,
            "memory_cache_total": 0,
            "expert_values": [],
            "expert_total_values": [],
            "diary_values": [],
            "tts_cache_hits": 0,
            "tts_cache_total": 0,
            "llm_values": [],
            "ttft_values": [],
            "tps_values": [],
            "cost_usd": 0.0,
            "unknown_cost_tokens": 0,
        })
        kind = row.get("kind")
        duration = _safe_int(row.get("duration_ms"))
        if kind == "request":
            bucket["requests"] += 1
            if duration is not None:
                bucket["e2e_values"].append(duration)
        elif kind == "error":
            bucket["errors"] += 1
        elif kind == "node_latency" and duration is not None:
            node = str(row.get("node_name") or "")
            bucket["node_values"].append(duration)
            if "memory" in node:
                bucket["memory_values"].append(duration)
            if "expert" in node:
                bucket["expert_values"].append(duration)
        elif kind == "expert_total" and duration is not None:
            bucket["expert_total_values"].append(duration)
            bucket["expert_values"].append(duration)
        elif kind == "diary_rag" and duration is not None:
            bucket["diary_values"].append(duration)
        elif kind == "memory_search" and duration is not None:
            bucket["memory_search_values"].append(duration)
            if row.get("cache_hit") is not None:
                bucket["memory_cache_total"] += 1
                if row.get("cache_hit") is True:
                    bucket["memory_cache_hits"] += 1
        elif kind == "tts_cache" and duration is not None:
            if row.get("cache_hit") is not None:
                bucket["tts_cache_total"] += 1
                if row.get("cache_hit") is True:
                    bucket["tts_cache_hits"] += 1
        elif kind == "llm_latency" and duration is not None:
            bucket["llm_values"].append(duration)
            ttft = _safe_int(row.get("ttft_ms"))
            tps = _safe_float(row.get("output_tokens_per_sec"))
            if ttft is not None:
                bucket["ttft_values"].append(ttft)
            if tps is not None:
                bucket["tps_values"].append(tps)
            if _safe_int(row.get("total_tokens")) or _safe_int(row.get("prompt_tokens")):
                cost_item = _estimate_llm_row_cost(row, price_by_model)
                if cost_item.get("known"):
                    bucket["cost_usd"] += _safe_float(cost_item.get("cost_usd")) or 0.0
                else:
                    bucket["unknown_cost_tokens"] += _safe_int(cost_item.get("tokens")) or 0
        if row.get("estimated_cost_usd") is not None:
            bucket["cost_usd"] += _safe_float(row.get("estimated_cost_usd")) or 0.0

    output = []
    for key in sorted(buckets):
        bucket = buckets[key]
        output.append({
            "ts": bucket["ts"],
            "requests": bucket["requests"],
            "errors": bucket["errors"],
            "e2e_p50": _stats(bucket["e2e_values"])["p50"],
            "e2e_p95": _stats(bucket["e2e_values"])["p95"],
            "node_p50": _stats(bucket["node_values"])["p50"],
            "memory_p50": _stats(bucket["memory_values"])["p50"],
            "memory_search_p50": _stats(bucket["memory_search_values"])["p50"],
            "memory_hit_rate": round(bucket["memory_cache_hits"] / bucket["memory_cache_total"], 4)
            if bucket["memory_cache_total"] else None,
            "expert_p50": _stats(bucket["expert_total_values"] or bucket["expert_values"])["p50"],
            "diary_p50": _stats(bucket["diary_values"])["p50"],
            "tts_hit_rate": round(bucket["tts_cache_hits"] / bucket["tts_cache_total"], 4)
            if bucket["tts_cache_total"] else None,
            "llm_p50": _stats(bucket["llm_values"])["p50"],
            "ttft_p50": _stats(bucket["ttft_values"])["p50"],
            "tps_avg": _float_stats(bucket["tps_values"])["avg"],
            "cost_usd": round(bucket["cost_usd"], 6),
            "unknown_cost_tokens": bucket["unknown_cost_tokens"],
        })

    return {
        "window_hours": hours,
        "bucket_minutes": bucket_minutes,
        "generated_at": _utc_now().isoformat(),
        "filters": {
            "user": str(user or ""),
            "source": str(source or ""),
            "model": str(model or ""),
        },
        "buckets": output,
    }
