"""Shared dashboard data models."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """Enumeration of dashboard debug event types."""

    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    NODE_START = "node_start"
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    LLM_CALL = "llm_call"
    LLM_THINKING = "llm_thinking"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"
    MEMORY_SEARCH = "memory_search"
    MEMORY_FOUND = "memory_found"
    MEMORY_SAVE = "memory_save"
    SYSTEM_INFO = "system_info"
    SYSTEM_ERROR = "system_error"
    USER_SWITCH = "user_switch"
    SYSTEM_PROMPT = "system_prompt"
    USER_MESSAGE = "user_message"
    PROMISE_EVENT = "promise_event"
    PROMISE_CONFIRMATION = "promise_confirmation"
    IMAGE_READY = "image_ready"


@dataclass
class DebugEvent:
    """A single debug/telemetry event emitted to the dashboard."""

    event_type: EventType
    node_name: str
    timestamp: str
    title: str
    content: Optional[str] = None
    thinking: Optional[str] = None
    raw_output: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    ttft_ms: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    output_tokens_per_sec: Optional[float] = None
    estimated_cost_usd: Optional[float] = None
    cost_source: Optional[str] = None
    input_cost_usd_per_m: Optional[float] = None
    output_cost_usd_per_m: Optional[float] = None
    content_chars: Optional[int] = None
    audio_duration_sec: Optional[float] = None
    metric_name: Optional[str] = None
    result_count: Optional[int] = None
    candidate_count: Optional[int] = None
    cache_hit: Optional[bool] = None
    input_data: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    error_module: Optional[str] = None
    error_type: Optional[str] = None
    error_id: Optional[str] = None
    is_seen: Optional[bool] = None
    repeat_count: Optional[int] = None
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    stack_trace: Optional[str] = None
    tracking_id: Optional[str] = None
    source: Optional[str] = None
    for_user: Optional[str] = None
    image_url: Optional[str] = None
    expert_domain: Optional[str] = None
    expert_model: Optional[str] = None
    expert_pass: Optional[str] = None
    fallback_reason: Optional[str] = None
    promise_data: Optional[dict] = None
    status: str = "info"


@dataclass
class ConnectionInfo:
    """Per-WebSocket connection metadata locked to an access key."""

    websocket: Any
    role: str
    user_key: str
    can_altpersona: bool = False
