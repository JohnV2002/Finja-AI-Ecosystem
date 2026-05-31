"""
YourAI Vision Provider Clients
=============================
Handles raw HTTP payloads, authorization headers, and response parsing for cloud-based OpenRouter 
and local Ollama vision services.

Main Responsibilities:
- Formulate OpenRouter and Ollama vision API HTTP request payloads.
- Parse responses, extracting descriptions and handling provider specific errors.
- Support fallback mechanisms and timeout settings.

Side Effects:
- Performs external HTTP network requests (OpenRouter and Ollama).
"""

import json
import time

import requests

from display import log, Fore
from exceptions import YourAINetworkError, YourAIVisionError

OPENROUTER_VISION_URL = "https://openrouter.ai/api/v1/chat/completions"


def _openrouter_headers(api_key: str) -> dict:
    """
    Builds authorization and content type headers for OpenRouter API requests.

    Args:
        api_key (str): The OpenRouter API key.

    Returns:
        dict: The header dictionary.
    """
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _openrouter_payload(model: str, prompt: str, image_url: str) -> dict:
    """
    Builds the payload structure required by the OpenRouter vision completions API.

    Args:
        model (str): Name of the visual model.
        prompt (str): Text prompt describing the requested analysis.
        image_url (str): Public URL or data URI of the image.

    Returns:
        dict: The payload dictionary.
    """
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        "max_tokens": 3000,
    }


def _parse_openrouter_response(result: dict, model: str, label: str, source_preview: str = "") -> str:
    """
    Extracts the visual description text from an OpenRouter completions response.

    Args:
        result (dict): The parsed JSON response dictionary from OpenRouter.
        model (str): The model name used.
        label (str): Classification label (e.g. "screenshot", "url").
        source_preview (str, optional): A text preview snippet of the source image reference.

    Raises:
        YourAIVisionError: If the response is in an unexpected format or is empty.

    Returns:
        str: The visual description text content.
    """
    raw_full = json.dumps(result)
    choices = result.get("choices")
    if not choices or not choices[0].get("message"):
        raise YourAIVisionError(
            f"OpenRouter returned unexpected format ({label})\n"
            f"Model: {model}\n"
            f"Source: {source_preview}\n"
            f"Full response: {raw_full}"
        )

    desc = choices[0]["message"].get("content")
    if not desc:
        choice_full = json.dumps(choices[0])
        raise YourAIVisionError(
            f"OpenRouter returned empty vision content ({label})\n"
            f"Model: {model}\n"
            f"Source: {source_preview}\n"
            f"choice[0]: {choice_full}\n"
            f"Full response: {raw_full}"
        )
    return desc


def call_openrouter_vision(api_key: str, model: str, prompt: str, image_url: str, label: str = "image") -> str:
    """
    Executes a visual analysis HTTP request against the OpenRouter completions API.

    Args:
        api_key (str): The OpenRouter API key.
        model (str): Name of the visual model.
        prompt (str): Prompt instructing the model what to analyze.
        image_url (str): The public URL or base64 data URI of the image.
        label (str, optional): Logging label/context identifier. Defaults to "image".

    Raises:
        YourAINetworkError: If a connection error occurs.
        YourAIVisionError: If the server returns a non-200 HTTP status or invalid JSON response.

    Returns:
        str: The visual description text content.
    """
    log("VISION", f"OpenRouter Vision request ({model}, {label})...", Fore.MAGENTA)
    start = time.time()
    try:
        response = requests.post(
            OPENROUTER_VISION_URL,
            headers=_openrouter_headers(api_key),
            json=_openrouter_payload(model, prompt, image_url),
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise YourAINetworkError(host="openrouter.ai", cause=e, module=f"eyes_openrouter_{label}")

    duration = time.time() - start
    if response.status_code != 200:
        raise YourAIVisionError(
            f"OpenRouter Vision HTTP {response.status_code} ({label})\n"
            f"Model: {model}\n"
            f"Source: {image_url[:120]}\n"
            f"Full error: {response.text}"
        )

    desc = _parse_openrouter_response(response.json(), model, label, image_url[:120])
    log("VISION", f"OpenRouter Vision ({duration:.1f}s): {desc[:100]}...", Fore.GREEN)
    return desc


def call_ollama_vision(host: str, model: str, prompt: str, base64_img: str) -> str:
    """
    Executes a visual analysis HTTP request against the local Ollama vision API.

    Args:
        host (str): Local Ollama endpoint host.
        model (str): Name of the visual model.
        prompt (str): Prompt instructing the model what to analyze.
        base64_img (str): The base64 encoded image content.

    Raises:
        YourAINetworkError: If a connection error occurs.
        YourAIVisionError: If the server returns a non-200 HTTP status or empty content.

    Returns:
        str: The visual description text content.
    """
    url = f"{host}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64_img],
            }
        ],
        "stream": False,
    }

    log("VISION", f"Local Ollama Vision request ({model})...", Fore.MAGENTA)
    start = time.time()
    try:
        response = requests.post(url, json=payload, timeout=None)
    except requests.exceptions.RequestException as e:
        raise YourAINetworkError(host=host, cause=e, module="eyes_ollama")

    duration = time.time() - start
    if response.status_code != 200:
        raise YourAIVisionError(f"Ollama Vision HTTP {response.status_code}: {response.text}")

    result = response.json()
    desc = result.get("message", {}).get("content")
    if not desc:
        raise YourAIVisionError(
            f"Ollama returned empty vision content\n"
            f"Model: {model}\n"
            f"Full response: {json.dumps(result)}"
        )
    log("VISION", f"Local Ollama Vision ({duration:.1f}s): {desc[:100]}...", Fore.GREEN)
    return desc
