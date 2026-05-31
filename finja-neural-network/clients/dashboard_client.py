"""
YourAI AI - Dashboard Client
===========================
Client for sending metrics, logging nodes, and fetching web input from the web dashboard.

Main Responsibilities:
- Lazy/Robust connection event dispatching to the dashboard API.
- Query active user web input queries from the dashboard server.
- Provide helper instrumentation methods for node lifetime logging (start/end).
- Broadcast image generation, memory searches, and system metrics to the dashboard.

Side Effects:
- Performs external HTTP requests to DASHBOARD_URL.
"""

import os
import sys
import time
import traceback
from datetime import datetime
from functools import wraps
from typing import Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError
from dashboard_images import prepare_dashboard_image_url
from helpers.text_parser import extract_dashboard_thinking

from config import DASHBOARD_URL


class DashboardClient:
    """
    Dashboard telemetry client for pipeline events, web input, and frontend status updates.
    """
    def __init__(self, base_url: str = DASHBOARD_URL):
        """
        Initializes instance state and cached connection metadata.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self.base_url = base_url
        self.enabled = True
        self._start_times = {}
        self._connected = False
        self._was_connected_ever = False
        self._last_web_user_key = "admin"      # Track last web user
        self._last_web_image_urls: list = []   # Track image_urls from last web input
        self._last_web_text_attachments: list = []  # Track text/file attachments from last web input
        self._last_web_session_uuid: str = ""  # Track session UUID for GDPR/DSGVO diary logging
        self._active_source: str = ""
        self._active_for_user: str = ""
    
    def _send(self, event: dict):
        """
        Sends a dashboard event payload while tracking connection state.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        if not self.enabled:
            return
        event["timestamp"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            requests.post(f"{self.base_url}/event", json=event, timeout=0.5)
            if not self._connected:
                if self._was_connected_ever:
                    log("DASHBOARD", "Connection to Dashboard restored.", Fore.GREEN)
                self._connected = True
                self._was_connected_ever = True
        except requests.RequestException:
            if self._connected:
                log("DASHBOARD", "Connection to Dashboard lost. Operating silently.", Fore.YELLOW)
                self._connected = False
        except Exception as e:
            if self._connected:
                err = YourAIUnexpectedError(cause=e, module="dashboard_client_send")
                log_exception("DASHBOARD", err)
                self._connected = False
    
    def get_web_input(self) -> Optional[str]:
        """
        Check if there's input from the web dashboard.
        Returns the text if available, None otherwise.
        Call this in your main loop!
        """
        if not self.enabled:
            return None
        try:
            resp = requests.get(f"{self.base_url}/get_input", timeout=0.3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("has_input"):
                    # NEU: Track user_key + image_urls from dashboard
                    self._last_web_user_key = data.get("user_key", "admin")
                    self._last_web_image_urls = data.get("image_urls") or []
                    self._last_web_text_attachments = data.get("text_attachments") or []
                    self._last_web_session_uuid = data.get("session_uuid", "")
                    return data.get("text", "")
        except requests.RequestException:
            pass  # Ignore network errors here to avoid spam (handled in _send)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="dashboard_client_input")
            log_exception("DASHBOARD", err)
        return None
    
    def get_last_web_user_key(self) -> str:
        """Returns the user_key from the last web input."""
        return self._last_web_user_key

    def get_last_web_image_urls(self) -> list:
        """Returns the image_urls from the last web input (empty list if none)."""
        return self._last_web_image_urls or []

    def get_last_web_text_attachments(self) -> list:
        """Returns text/file attachments from the last web input."""
        return self._last_web_text_attachments or []

    def get_last_web_session_uuid(self) -> str:
        """Returns the session_uuid from the last web input (empty string if none)."""
        return self._last_web_session_uuid or ""
    
    def _extract_thinking(self, raw_output: str) -> tuple[str, str]:
        """
        Splits model thinking traces from visible dashboard content.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        return extract_dashboard_thinking(raw_output)
    
    # ==========================================
    # HIGH-LEVEL API
    # ==========================================
    
    def node_start(self, node_name: str, model: Optional[str] = None, input_data: Optional[str] = None):
        """
        Records and emits the start of a pipeline node execution.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self._start_times[node_name] = time.time()
        self._send({
            "event_type": "node_start",
            "node_name": node_name,
            "title": f"{node_name.upper()} started",
            "model": model,
            "input_data": input_data,
            "status": "info"
        })
    
    def node_end(self, node_name: str, duration_ms: Optional[int] = None):
        """
        Emits the completion event for a pipeline node execution.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        if duration_ms is None and node_name in self._start_times:
            duration_ms = int((time.time() - self._start_times[node_name]) * 1000)
        
        self._send({
            "event_type": "node_end",
            "node_name": node_name,
            "title": f"{node_name.upper()} finished",
            "duration_ms": duration_ms,
            "status": "success"
        })
    
    def llm_call(self, node_name: str, model: str, prompt: str):
        """
        Emits a dashboard event before an LLM request is sent.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self._send({
            "event_type": "llm_call",
            "node_name": node_name,
            "title": f"Calling {model}",
            "model": model,
            "input_data": prompt[:2000] + "..." if len(prompt) > 2000 else prompt,
            "status": "info"
        })
    
    def llm_response(
        self, 
        node_name: str, 
        raw_output: str, 
        model: Optional[str] = None,
        duration_ms: Optional[int] = None,
        ttft_ms: Optional[int] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        output_tokens_per_sec: Optional[float] = None,
        source: Optional[str] = None,
        for_user: Optional[str] = None,
        auto_extract_thinking: bool = True
    ):
        """
        Emits a dashboard event for an LLM response and optional token metrics.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        thinking = ""
        content = raw_output
        
        if auto_extract_thinking:
            thinking, content = self._extract_thinking(raw_output)
        
        payload = {
            "event_type": "llm_response",
            "node_name": node_name,
            "title": f"Response from {model or node_name}",
            "model": model,
            "content": content,
            "thinking": thinking if thinking else None,
            # ALWAYS send raw_output so it is displayed in the Dashboard!
            "raw_output": raw_output,
            "duration_ms": duration_ms,
            "ttft_ms": ttft_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "output_tokens_per_sec": output_tokens_per_sec,
            "status": "success"
        }
        source = source or self._active_source
        for_user = for_user or self._active_for_user
        if source:
            payload["source"] = source
        if for_user:
            payload["for_user"] = for_user
        self._send(payload)
    
    def thinking(self, node_name: str, thought: str, model: Optional[str] = None):
        """
        Emits a dashboard event containing intermediate model reasoning text.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self._send({
            "event_type": "llm_thinking",
            "node_name": node_name,
            "title": f"{node_name} thinking...",
            "model": model,
            "thinking": thought,
            "status": "info"
        })
    
    def system_prompt_dump(self, node_name: str, system_prompt: str):
        """Send the full system prompt to the dashboard for debugging."""
        self._send({
            "event_type": "system_prompt",
            "node_name": node_name,
            "title": f"System System Prompt for {node_name}",
            "content": system_prompt,
            "raw_output": system_prompt,  # So it shows in "Raw Output" tab
            "status": "info"
        })
    
    def user_message_dump(self, node_name: str, user_message: str):
        """Send the full user message to the dashboard for debugging."""
        self._send({
            "event_type": "user_message",
            "node_name": node_name,
            "title": f"Message User Message for {node_name}",
            "content": user_message,
            "raw_output": user_message,
            "status": "info"
        })
    
    def error(
        self, 
        node_name: str, 
        message: str, 
        exception: Optional[Exception] = None,
        input_data: Optional[str] = None,
        error_code: Optional[str] = None,
        error_module: Optional[str] = None,
        error_type: Optional[str] = None,
        error_id: Optional[str] = None,
        is_seen: Optional[bool] = None,
        repeat_count: Optional[int] = None,
        first_seen_at: Optional[str] = None,
        last_seen_at: Optional[str] = None,
    ):
        """
        Emits a normalized dashboard error event with optional YourAIError metadata.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        stack = None
        if exception:
            stack = traceback.format_exc()

        error_code = error_code or getattr(exception, "code", None)
        error_module = error_module or getattr(exception, "module", None) or node_name
        error_type = error_type or (type(exception).__name__ if exception else None)

        self._send({
            "event_type": "node_error",
            "node_name": node_name,
            "title": f"ERROR in {node_name}",
            "error": message,
            "error_code": error_code,
            "error_module": error_module,
            "error_type": error_type,
            "error_id": error_id,
            "is_seen": is_seen,
            "repeat_count": repeat_count,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "stack_trace": stack,
            "input_data": input_data,
            "status": "error"
        })
    
    def memory_search(self, query: str, results: list, model: str = None):
        """
        Emits dashboard details for a memory search query and its results.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        payload = {
            "event_type": "memory_search",
            "node_name": "memory",
            "title": f"Memory search: {len(results)} results",
            "input_data": f"Query: {query}",
            "content": "\n".join(f"- {r}" for r in results) if results else "No memories found",
            "status": "success" if results else "warning"
        }
        if model:
            payload["model"] = model
        self._send(payload)
    
    def memory_save(self, facts: list):
        """
        Emits dashboard details for newly saved memory facts.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self._send({
            "event_type": "memory_save",
            "node_name": "memory",
            "title": f"Saving {len(facts)} new facts",
            "content": "\n".join(f"- {f}" for f in facts),
            "status": "success"
        })
    
    def promise_event(self, action: str, promise_name: str, details: Optional[str] = None, reason: Optional[str] = None):
        """Send promise events to dashboard (made/broken/fulfilled)."""
        icons = {"made": "Promise", "broken": "Broken", "fulfilled": "Fulfilled", "detected": "Detected"}
        icon = icons.get(action, "System")
        status_map = {"made": "info", "broken": "warning", "fulfilled": "success", "detected": "info"}

        content_parts = [f"Promise: {promise_name}", f"Action: {action}"]
        if reason:
            content_parts.append(f"Reason: {reason}")
        if details:
            content_parts.append(f"Details: {details}")

        self._send({
            "event_type": "promise_event",
            "node_name": "system",
            "title": f"{icon} Promise {action}: {promise_name}",
            "content": "\n".join(content_parts),
            "status": status_map.get(action, "info")
        })

    def promise_confirmation(self, signal, for_user: str = ""):
        """Send promise confirmation request to frontend - user decides yes/no."""
        action_labels = {"MADE": "erkannt", "BROKEN": "gebrochen"}
        label = action_labels.get(signal.action, signal.action)
        self._send({
            "event_type": "promise_confirmation",
            "node_name": "system",
            "title": f"Promise Promise {label}: {signal.promise_name}",
            "content": signal.reasoning or signal.original_message[:100],
            "for_user": for_user,
            "status": "warning",
            "promise_data": signal.to_dict(),
        })

    def info(self, node_name: str, message: str, details: Optional[str] = None):
        """
        Emits a generic informational dashboard event.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self._send({
            "event_type": "system_info",
            "node_name": node_name,
            "title": message,
            "content": details,
            "status": "info"
        })

    def metric(
        self,
        metric_name: str,
        node_name: str,
        title: str,
        **kwargs
    ):
        """
        Sends telemetry/performance metrics to the dashboard server.

        Args:
            metric_name (str): The unique name representing this metric event.
            node_name (str): The execution node where the metric originated.
            title (str): Readable status/action title.
            **kwargs: Optional keyword parameters:
                duration_ms (int, optional): Execution duration in milliseconds.
                result_count (int, optional): Count of results.
                candidate_count (int, optional): Count of candidates.
                cache_hit (bool, optional): Whether cache hit occurred.
                source (str, optional): Metric context source.
                for_user (str, optional): Target user ID.
                expert_domain (str, optional): Domain area.
                expert_model (str, optional): LLM model used.
                expert_pass (str, optional): Expert pass strategy.
                fallback_reason (str, optional): Fallback trigger context.
                prompt_tokens (int, optional): Prompt token count.
                completion_tokens (int, optional): Completion token count.
                total_tokens (int, optional): Total token count.
                output_tokens_per_sec (float, optional): Token speed metric.
                estimated_cost_usd (float, optional): Estimated cost in USD.
                cost_source (str, optional): Cost source details.
                input_cost_usd_per_m (float, optional): Input rate per million tokens.
                output_cost_usd_per_m (float, optional): Output rate per million tokens.
                content_chars (int, optional): Character count of response content.
                audio_duration_sec (float, optional): Audio length in seconds.
                details (str, optional): Extra textual details.
                status (str, optional): Metric status level ("success", "info", "warning").
        """
        status = kwargs.get("status", "success")
        payload = {
            "event_type": "system_info",
            "node_name": node_name,
            "title": title,
            "content": kwargs.get("details"),
            "duration_ms": kwargs.get("duration_ms"),
            "metric_name": metric_name,
            "result_count": kwargs.get("result_count"),
            "candidate_count": kwargs.get("candidate_count"),
            "cache_hit": kwargs.get("cache_hit"),
            "prompt_tokens": kwargs.get("prompt_tokens"),
            "completion_tokens": kwargs.get("completion_tokens"),
            "total_tokens": kwargs.get("total_tokens"),
            "output_tokens_per_sec": kwargs.get("output_tokens_per_sec"),
            "estimated_cost_usd": kwargs.get("estimated_cost_usd"),
            "cost_source": kwargs.get("cost_source"),
            "input_cost_usd_per_m": kwargs.get("input_cost_usd_per_m"),
            "output_cost_usd_per_m": kwargs.get("output_cost_usd_per_m"),
            "content_chars": kwargs.get("content_chars"),
            "audio_duration_sec": kwargs.get("audio_duration_sec"),
            "status": status,
        }
        for field in ["source", "for_user", "expert_domain", "expert_model", "expert_pass", "fallback_reason"]:
            val = kwargs.get(field)
            if val is not None:
                payload[field] = val
        self._send(payload)

    def queue_status(self, message: str, details: Optional[str] = None,
                     source: str = None, for_user: str = None,
                     status: str = "info", phase: str = "processing"):
        """
        Emits queue processing status for the dashboard timeline.

        Returns:
            Any: The operation result, or None when no result is produced.
        """
        payload = {
            "event_type": "system_info",
            "node_name": "queue_status",
            "title": message,
            "content": details,
            "status": status,
            "phase": phase,
        }
        if source:
            payload["source"] = source
        if for_user:
            payload["for_user"] = for_user
        self._send(payload)
    
    def image_ready(self, image_url: str, prompt: str = "", model: str = "", elapsed_s: float = 0.0, for_user: str = ""):
        """Fires an image_ready event so the frontend can display the generated image."""
        # base64 data URIs can be several MB; save to disk and send an HTTP path instead
        image_url = prepare_dashboard_image_url(image_url)

        details = f"Prompt: {prompt[:200]}"
        if model:
            details += f"\nModel: {model}"
        if elapsed_s:
            details += f"\nTime: {elapsed_s}s"
        self._send({
            "event_type": "image_ready",
            "node_name": "image_gen",
            "title": "Image Image generated!",
            "content": details,
            "image_url": image_url,
            "for_user": for_user,
            "status": "success",
        })

    def pipeline_start(self, user: str, question: str, source: str, for_user: str = ""):
        """
        Emits a dashboard event when a user request enters the pipeline.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self._active_source = source or ""
        self._active_for_user = for_user or ""
        self._send({
            "event_type": "pipeline_start",
            "node_name": "system",
            "title": f"New request from {user}",
            "content": question,
            "input_data": f"Source: {source}",
            "source": source or None,
            "for_user": for_user or None,
            "status": "info"
        })
    
    def pipeline_end(self, response: str, total_ms: int, tracking_id: str = None,
                     source: str = None, for_user: str = None, model: str = None,
                     expert_domain: str = None, expert_model: str = None):
        """
        Emits a dashboard event when a pipeline response is completed.

        Returns:
            Any: The operation result, or None when no result is produced.
        """
        payload = {
            "event_type": "pipeline_end",
            "node_name": "system",
            "title": "Pipeline complete",
            "content": response,
            "duration_ms": total_ms,
            "status": "success"
        }
        if tracking_id:
            payload["tracking_id"] = tracking_id
        if source:
            payload["source"] = source
        if for_user:
            payload["for_user"] = for_user
        if model:
            payload["model"] = model
        if expert_domain:
            payload["expert_domain"] = expert_domain
        if expert_model:
            payload["expert_model"] = expert_model
        self._send(payload)
        self._active_source = ""
        self._active_for_user = ""


# Global instance
debug = DashboardClient()


if __name__ == "__main__":
    print("Testing dashboard client v2...")
    print("Checking for web input (run dashboard_server.py first)...")
    
    for i in range(10):
        web_input = debug.get_web_input()
        if web_input:
            print(f"Got web input: {web_input}")
        else:
            print(".", end="", flush=True)
        time.sleep(1)
    
    print("\nDone!")
