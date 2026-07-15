"""
======================================================================
         Finja Canvas – AI Client
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / ai_client
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Client for interacting with OpenRouter API. Includes fallback and 
  timeout logic for models.
======================================================================
"""

import concurrent.futures
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Selected on 2026-07-14 via category benchmark (10 categories x Primitives shape generation):
# gemma-4-26b and nemo-550b consistently provided the most recognizable shapes.
# nemo-9b, gemma-31b, llama-3.x, qwen3-next-80b were 0/0 or very unreliable and
# were discarded; nemo-30b looked ok in an earlier test, but was completely empty 
# in 8 out of 10 categories in the category benchmark - also out.
FREE_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
]

# Paid last-resort fallback, in case ALL free models are currently rate-limited.
# Costs real money, but at $0.01/$0.03 per 1M tokens practically nothing (Price checked
# live on 2026-07-14 against https://openrouter.ai/api/v1/models). Placed intentionally
# as a separate list AFTER FREE_MODELS, so it remains clear what is free and what is not.
PAID_FALLBACK_MODELS = [
    "inclusionai/ling-2.6-flash",
]

MODEL_CHAIN = FREE_MODELS + PAID_FALLBACK_MODELS

# Pure round-robin cursor: advances by 1 on EVERY call, regardless of whether the previous
# call was successful or not (no more sticky behavior). Thus, every call changes the provider
# by default (gemma -> nemotron -> gemma -> llama -> ...), instead of spamming the same
# provider until it fails. If a pick fails anyway, it stubbornly tries the chain (with wraparound)
# from there on as before.
_cursor = 0

# nvidia/nemotron-nano-9b-v2:free is a reasoning model (thinks in a separate "reasoning" field 
# before it answers) - this can take a very long time with a high max_tokens. Since the answer
# trickles in continuously (slowly) during this, requests' normal read timeout does NOT trigger 
# (it only reacts to silence, not to total duration) - a hanging call can otherwise block for
# minutes. Therefore, every request runs in a thread with a true wall-clock limit; if this is
# exceeded, we give up on the call and try the next model (the thread runs out in the background
# and is discarded).
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def _post(model, prompt, max_tokens, headers):
    # No "reasoning" parameter here: not every model supports it, some (e.g. openai/gpt-oss-20b)
    # reject the whole request with 400. The wall-clock timeout in ask_ai() is enough protection
    # against slow reasoning models.
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    return requests.post(API_URL, headers=headers, json=payload, timeout=30)


def ask_ai(prompt, max_tokens=800, wall_clock_timeout=20):
    """
    Sends the prompt to MODEL_CHAIN, starting at the next model in the round-robin
    (rotates further with wraparound on errors/timeouts). Returns (content, model_name),
    or (None, None) if all fail.
    """
    global _cursor

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    n = len(MODEL_CHAIN)
    start = _cursor
    _cursor = (_cursor + 1) % n

    for offset in range(n):
        idx = (start + offset) % n
        model = MODEL_CHAIN[idx]

        future = _executor.submit(_post, model, prompt, max_tokens, headers)
        try:
            response = future.result(timeout=wall_clock_timeout)
        except concurrent.futures.TimeoutError:
            print(f"⚠️ {model} answers too slowly (>{wall_clock_timeout}s), trying next model...")
            continue
        except requests.RequestException as e:
            print(f"⚠️ {model} failed ({e}), trying next model...")
            continue

        if response.status_code == 429:
            print(f"⚠️ {model} is rate-limited, trying next model...")
            continue
        try:
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content")
            if not content:
                print(f"⚠️ {model} returned empty content, trying next model...")
                continue
            return content.strip(), model
        except requests.RequestException as e:
            print(f"⚠️ {model} failed ({e}), trying next model...")
            continue
        except (KeyError, IndexError, ValueError) as e:
            print(f"⚠️ {model} sent an unexpected response ({e}), trying next model...")
            continue

    return None, None
