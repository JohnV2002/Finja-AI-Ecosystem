"""
Dashboard Client for AltPersona Brain v2
===================================
Now with Web Input support!

Usage:
    from dashboard_client import debug

    # Check for web input in your main loop:
    web_input = debug.get_web_input()
    if web_input:
        process_input(web_input, "Admin (Web)", "web", history)
"""

import requests
import time
import re
import sys, os
import traceback
from datetime import datetime
from typing import Optional
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError

from config import DASHBOARD_URL

# ==========================================
# DEBUG CLIENT
# ==========================================

class DashboardClient:
    def __init__(self, base_url: str = DASHBOARD_URL):
        self.base_url = base_url
        self.enabled = True
        self._start_times = {}
        self._connected = False
        self._was_connected_ever = False
        self._last_web_user_key = "admin"      # Track last web user
        self._last_web_image_urls: list = []   # Track image_urls from last web input
        self._last_web_session_uuid: str = ""  # Track session UUID for DSGVO diary logging
    
    def _send(self, event: dict):
        if not self.enabled:
            return
        event["timestamp"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            requests.post(f"{self.base_url}/event", json=event, timeout=0.5)
            if not self._connected:
                if self._was_connected_ever:
                    log("DASHBOARD", "🔌 Connection to Dashboard restored!", Fore.GREEN)
                self._connected = True
                self._was_connected_ever = True
        except requests.RequestException:
            if self._connected:
                log("DASHBOARD", "⚠️ Connection to Dashboard lost. Operating silently...", Fore.YELLOW)
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

    def get_last_web_session_uuid(self) -> str:
        """Returns the session_uuid from the last web input (empty string if none)."""
        return self._last_web_session_uuid or ""
    
    def _extract_thinking(self, raw_output: str) -> tuple[str, str]:
        if not raw_output:
            return "", ""
        
        thinking_parts = []
        clean = raw_output
        
        patterns = [
            r'<(think|thinking|thought|thoughts|scratchpad|reasoning|analysis|internal|reflection)>(.*?)</\1>',
            r'<i>(.*?)</i>',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, raw_output, re.DOTALL | re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    thinking_parts.append(match[-1].strip())
                else:
                    if len(match.split()) > 10:
                        thinking_parts.append(match.strip())
        
        for pattern in patterns:
            clean = re.sub(pattern, '', clean, flags=re.DOTALL | re.IGNORECASE)
        
        clean = clean.strip()
        thinking = "\n---\n".join(thinking_parts) if thinking_parts else ""
        
        return thinking, clean
    
    # ==========================================
    # HIGH-LEVEL API
    # ==========================================
    
    def node_start(self, node_name: str, model: Optional[str] = None, input_data: Optional[str] = None):
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
        auto_extract_thinking: bool = True
    ):
        thinking = ""
        content = raw_output
        
        if auto_extract_thinking:
            thinking, content = self._extract_thinking(raw_output)
        
        self._send({
            "event_type": "llm_response",
            "node_name": node_name,
            "title": f"Response from {model or node_name}",
            "model": model,
            "content": content,
            "thinking": thinking if thinking else None,
            # IMMER raw_output senden damit es im Dashboard angezeigt wird!
            "raw_output": raw_output,
            "duration_ms": duration_ms,
            "status": "success"
        })
    
    def thinking(self, node_name: str, thought: str, model: Optional[str] = None):
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
            "title": f"📋 System Prompt for {node_name}",
            "content": system_prompt,
            "raw_output": system_prompt,  # So it shows in "Raw Output" tab
            "status": "info"
        })
    
    def user_message_dump(self, node_name: str, user_message: str):
        """Send the full user message to the dashboard for debugging."""
        self._send({
            "event_type": "user_message",
            "node_name": node_name,
            "title": f"💬 User Message for {node_name}",
            "content": user_message,
            "raw_output": user_message,
            "status": "info"
        })
    
    def error(
        self, 
        node_name: str, 
        message: str, 
        exception: Optional[Exception] = None,
        input_data: Optional[str] = None
    ):
        stack = None
        if exception:
            stack = traceback.format_exc()
        
        self._send({
            "event_type": "node_error",
            "node_name": node_name,
            "title": f"ERROR in {node_name}",
            "error": message,
            "stack_trace": stack,
            "input_data": input_data,
            "status": "error"
        })
    
    def memory_search(self, query: str, results: list, model: str = None):
        payload = {
            "event_type": "memory_search",
            "node_name": "memory",
            "title": f"Memory search: {len(results)} results",
            "input_data": f"Query: {query}",
            "content": "\n".join(f"• {r}" for r in results) if results else "No memories found",
            "status": "success" if results else "warning"
        }
        if model:
            payload["model"] = model
        self._send(payload)
    
    def memory_save(self, facts: list):
        self._send({
            "event_type": "memory_save",
            "node_name": "memory",
            "title": f"Saving {len(facts)} new facts",
            "content": "\n".join(f"• {f}" for f in facts),
            "status": "success"
        })
    
    def promise_event(self, action: str, promise_name: str, details: Optional[str] = None, reason: Optional[str] = None):
        """Send promise events to dashboard (made/broken/fulfilled)."""
        icons = {"made": "🤝", "broken": "💔", "fulfilled": "🎉", "detected": "🔍"}
        icon = icons.get(action, "📋")
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

    def info(self, node_name: str, message: str, details: Optional[str] = None):
        self._send({
            "event_type": "system_info",
            "node_name": node_name,
            "title": message,
            "content": details,
            "status": "info"
        })
    
    def image_ready(self, image_url: str, prompt: str = "", model: str = "", elapsed_s: float = 0.0, for_user: str = ""):
        """Fires an image_ready event so the frontend can display the generated image."""
        # base64 data URIs can be several MB — save to disk and send an HTTP path instead
        if image_url.startswith("data:"):
            try:
                import base64 as _b64
                import time as _time
                _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                _gen_dir = os.path.join(_project_root, "frontend", "generated")
                os.makedirs(_gen_dir, exist_ok=True)
                _, encoded = image_url.split(",", 1)
                img_bytes = _b64.b64decode(encoded)
                filename = f"yourai_art_{int(_time.time())}.png"
                with open(os.path.join(_gen_dir, filename), "wb") as _f:
                    _f.write(img_bytes)
                image_url = f"/generated/{filename}"
                log("DASHBOARD", f"🎨 Bild gespeichert → {image_url}", Fore.CYAN)
            except Exception as _e:
                log("DASHBOARD", f"⚠️ Bild-Speichern fehlgeschlagen: {_e}", Fore.YELLOW)

        details = f"Prompt: {prompt[:200]}"
        if model:
            details += f"\nModel: {model}"
        if elapsed_s:
            details += f"\nTime: {elapsed_s}s"
        self._send({
            "event_type": "image_ready",
            "node_name": "image_gen",
            "title": "🎨 Image generated!",
            "content": details,
            "image_url": image_url,
            "for_user": for_user,
            "status": "success",
        })

    def pipeline_start(self, user: str, question: str, source: str, for_user: str = ""):
        self._send({
            "event_type": "pipeline_start",
            "node_name": "system",
            "title": f"New request from {user}",
            "content": question,
            "input_data": f"Source: {source}",
            "for_user": for_user or None,
            "status": "info"
        })
    
    def pipeline_end(self, response: str, total_ms: int, tracking_id: str = None,
                     source: str = None, for_user: str = None, model: str = None,
                     expert_domain: str = None, expert_model: str = None):
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