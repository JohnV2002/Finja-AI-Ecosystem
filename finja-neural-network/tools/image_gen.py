"""
YourAI AI - Image Generation Tool
==================================
Calls OpenRouter's image generation API.

Supported models (all capped at 1024x1024 for cost control):
- sourceful/riverflow-v2-fast           $0.02/img  — fastest, marketing/font support
- sourceful/riverflow-v2-standard-preview $0.035/img — balanced quality
- sourceful/riverflow-v2-max-preview    $0.075/img — best quality
- black-forest-labs/flux.2-pro          ~$0.03/MP  — Flux quality

Usage:
    from tools.image_gen import generate_image
    result = generate_image("a fox in the forest, digital art")
    if result["success"]:
        print(result["url"])
"""

import requests
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError

try:
    from config import OPENROUTER_API_KEY, IMAGE_MODEL, IMAGE_SIZE
except ImportError:
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    IMAGE_MODEL = "sourceful/riverflow-v2-fast"
    IMAGE_SIZE = "1024x1024"

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SECONDS = 90  # Image gen can take a while


def generate_image(prompt: str, model: str = None, size: str = None) -> dict:
    """
    Generate an image via OpenRouter.

    Args:
        prompt: Text description of the image
        model:  OpenRouter model ID (default: IMAGE_MODEL from config)
        size:   Image size string e.g. "1024x1024" (default: IMAGE_SIZE)

    Returns:
        {
            "success": bool,
            "url": str,        # image URL (if success)
            "b64": str,        # base64 data (if returned instead of URL)
            "error": str,      # error message (if failed)
            "prompt": str,     # original prompt
            "model": str,      # model used
            "elapsed_s": float # generation time
        }
    """
    model = model or IMAGE_MODEL
    size  = size  or IMAGE_SIZE
    prompt = prompt.strip()

    if not prompt:
        return {"success": False, "error": "Empty prompt", "prompt": prompt, "model": model}

    if not OPENROUTER_API_KEY:
        return {"success": False, "error": "OPENROUTER_API_KEY not set", "prompt": prompt, "model": model}

    log("IMAGE", f"🎨 Generating: '{prompt[:60]}...' [{model}]", Fore.MAGENTA)
    t0 = time.time()

    try:
        # OpenRouter routes image models through the standard chat completions endpoint.
        # The image URL is returned in choices[0].message.content
        resp = requests.post(
            OPENROUTER_CHAT_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://yourai.ai",
                "X-Title": "YourAI AI",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=TIMEOUT_SECONDS,
        )
        elapsed = round(time.time() - t0, 1)

        if resp.status_code != 200:
            err = f"HTTP {resp.status_code}"
            raw_body = ""
            try:
                raw_body = resp.text[:500]
                err_data = resp.json()
                err = err_data.get("error", {}).get("message", err) or err
            except Exception:
                # Best-effort error enrichment; keep the HTTP-status message on failure.
                pass
            log("IMAGE", f"❌ Failed [{model}]: {err}", Fore.RED)
            log("IMAGE", f"   Response body: {raw_body}", Fore.RED)
            return {"success": False, "error": f"{err}", "prompt": prompt, "model": model, "elapsed_s": elapsed}

        data = resp.json()

        import json as _json
        import re as _re

        url = ""
        try:
            msg = data["choices"][0]["message"]

            # 1. OpenRouter image models: message.images = [{"type": "...", "url": "..."}]
            images = msg.get("images") or []
            for img in images:
                if isinstance(img, dict):
                    log("IMAGE", f"🔍 Image obj: type={img.get('type','?')} keys={list(img.keys())}", Fore.CYAN)
                    # Try all known field names across providers
                    url = (
                        img.get("url") or
                        img.get("b64_json") or
                        img.get("data") or
                        (img.get("image_url") or {}).get("url") or
                        (img.get("source") or {}).get("data") or
                        ""
                    )
                    if url:
                        # Wrap raw base64 in a data URI so downstream can use it
                        if not url.startswith("http") and not url.startswith("data:"):
                            media_type = (
                                img.get("media_type") or
                                (img.get("source") or {}).get("media_type") or
                                "image/png"
                            )
                            url = f"data:{media_type};base64,{url}"
                        break

            # 2. Standard: message.content as string
            if not url:
                content = msg.get("content") or ""
                if isinstance(content, str) and content.strip():
                    if content.strip().startswith("http"):
                        url = content.strip().split()[0]
                    elif content.strip().startswith("data:image"):
                        url = content.strip()
                    else:
                        m = _re.search(r'https?://\S+', content)
                        if m:
                            url = m.group(0).rstrip(')')
                        else:
                            md = _re.search(r'!\[.*?\]\((https?://\S+)\)', content)
                            if md:
                                url = md.group(1)

            # 3. message.content as list (OpenAI vision format)
            if not url:
                content = msg.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "image_url":
                                url = item.get("image_url", {}).get("url", "")
                            elif item.get("type") == "image":
                                url = item.get("url", "") or item.get("source", {}).get("url", "")
                        if url:
                            break

        except (KeyError, IndexError, TypeError):
            # Response shape varies per provider; fall through to the next strategy.
            pass

        # 4. OpenAI images format fallback: data[0].url
        if not url:
            try:
                url = data["data"][0].get("url", "") or data["data"][0].get("b64_json", "")
            except (KeyError, IndexError, TypeError):
                # No OpenAI-style data array either; handled by the empty-url check below.
                pass

        if not url:
            raw = _json.dumps(data)[:400]
            log("IMAGE", f"❌ No image URL found. Raw: {raw}", Fore.RED)
            return {"success": False, "error": f"No image URL in response", "prompt": prompt, "model": model, "elapsed_s": elapsed}

        log("IMAGE", f"✅ Done in {elapsed}s [{model}]", Fore.GREEN)
        return {
            "success": True,
            "url": url,
            "prompt": prompt,
            "model": model,
            "elapsed_s": elapsed,
        }

    except requests.Timeout as e:
        elapsed = round(time.time() - t0, 1)
        err = YourAIToolExecutionError(f"Timeout after {elapsed}s", tool_name="image_gen", cause=e)
        log_exception("IMAGE", err)
        return {"success": False, "error": f"Timeout after {elapsed}s", "prompt": prompt, "model": model, "elapsed_s": elapsed}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        err = YourAIToolExecutionError("OpenRouter Image API Error", tool_name="image_gen", cause=e)
        log_exception("IMAGE", err)
        return {"success": False, "error": str(e), "prompt": prompt, "model": model, "elapsed_s": elapsed}
