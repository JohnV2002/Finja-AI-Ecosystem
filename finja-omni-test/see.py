"""
======================================================================
         Finja Omni Test – Vision Module
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / see
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
  Layer 2 — Vision. Finja SEES the scene (not just reading subtitles).
  Clever frame splitting (Idea from John):
    video + fullscreen -> VLM only gets the TOP part (the scene WITHOUT 
                          subtitles), OCR reads the bottom strip. Both 
                          on the same frame.
    else               -> whole (small) image + downscale.

  Triggered sparingly (~every 30s / on scene change), NOT per frame.

  Backends:
    - local:      Ollama Vision (offline, privacy, but slow on CPU)
    - openrouter: Cloud VLM (fast/better, but image leaves the PC)

      python see.py captures/realworld3/frame_202212_14.png
      python see.py <frame> --both        # compare local AND openrouter
======================================================================
"""

import os
import sys
import io
import json
import time
import base64

import requests
from PIL import Image
from dotenv import load_dotenv

load_dotenv()   # Load .env before config is read

# --- CONFIG ---
OLLAMA_URL      = "http://localhost:11434/api/generate"
LOCAL_MODEL     = os.environ.get("LOCAL_VLM", "minicpm-v4.6:latest")
OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"
# Key ONLY from the Env variable (never hardcode -> otherwise it leaks in Git/Logs!)
OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_VLM", "qwen/qwen3-vl-8b-instruct")

DOWNSCALE_MAX = 1024     # longest edge for the VLM (saves tokens + time)
SCENE_TOP     = 0.55     # for fullscreen video: top portion = scene (rest = subs)

VISION_PROMPT = (
    "You are the eyes of a desktop companion. In ONE short sentence, describe "
    "what is happening on the screen right now (the scene, app, or activity). "
    "Do NOT transcribe any text or subtitles — only describe what you see."
)


def prep_image(image, content=None, fullscreen=False):
    """Prepares the image for the VLM: for fullscreen video only the scene (top),
    otherwise whole image. Always downscale. Returns base64-PNG.
    image: File path OR PIL Image (for the live loop)."""
    img = image if isinstance(image, Image.Image) else Image.open(image)
    img = img.convert("RGB")
    if content == "video" and fullscreen:
        w, h = img.size
        img = img.crop((0, 0, w, int(h * SCENE_TOP)))   # Scene without subtitles
    img.thumbnail((DOWNSCALE_MAX, DOWNSCALE_MAX))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def see_local(b64, prompt=VISION_PROMPT, model=LOCAL_MODEL, timeout=300):
    payload = {
        "model": model, "prompt": prompt, "images": [b64],
        "stream": False, "options": {"temperature": 0.2, "num_predict": 120},
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", "").strip()


def see_openrouter(b64, prompt=VISION_PROMPT, model=OPENROUTER_MODEL, timeout=360):
    if not OPENROUTER_KEY:
        raise RuntimeError("No OPENROUTER_API_KEY set (env variable).")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "temperature": 0.2, "max_tokens": 120,
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}",
               "Content-Type": "application/json"}
    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _load_meta_info(image_path):
    """Fetches content/fullscreen from the meta.json next to the frame (if there)."""
    folder = os.path.dirname(image_path)
    mp = os.path.join(folder, "meta.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            info = json.load(f).get(os.path.basename(image_path), {})
        return info.get("content"), bool(info.get("fullscreen"))
    return None, False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python see.py <frame.png> [--both|--openrouter]")
    image_path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "--local"

    content, fullscreen = _load_meta_info(image_path)
    b64 = prep_image(image_path, content, fullscreen)
    split = " (scene only, subs cut off)" if content == "video" and fullscreen else ""
    print("=" * 64)
    print(f"  SEEING: {os.path.basename(image_path)}  [content={content}, fs={fullscreen}]{split}")
    print("=" * 64)

    if mode in ("--local", "--both"):
        try:
            t0 = time.perf_counter()
            out = see_local(b64)
            print(f"\n  [LOCAL {LOCAL_MODEL}]  ({time.perf_counter()-t0:.1f}s)\n  {out}")
        except Exception as e:
            print(f"\n  [LOCAL] Error: {e}")

    if mode in ("--openrouter", "--both"):
        try:
            t0 = time.perf_counter()
            out = see_openrouter(b64)
            print(f"\n  [OPENROUTER {OPENROUTER_MODEL}]  ({time.perf_counter()-t0:.1f}s)\n  {out}")
        except Exception as e:
            print(f"\n  [OPENROUTER] Error: {e}")
    print()
