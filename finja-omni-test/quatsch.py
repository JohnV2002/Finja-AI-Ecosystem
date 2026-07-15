"""
======================================================================
         Finja Omni Test – LLM Chat Tester
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / quatsch
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
  G — the feeling test. Finja looks at the timeline (Vision + OCR) and chats.
  Pulls the last few minutes from the DB, builds a readable screen context 
  from it and sends it to an LLM (any via OpenRouter, NOT Finja's real backend) 
  with a light companion persona.
  -> First feeling: does she react sensibly/charmingly to what happened?

      python quatsch.py                 # last 5 mins
      python quatsch.py 10              # last 10 mins
      python quatsch.py 5 "What am I watching?"   # with custom question
======================================================================
"""

import os
import sys
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
CHAT_MODEL      = os.environ.get("CHAT_MODEL", "google/gemma-4-31b-it")
OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"

import db

PERSONA = (
    "You are Finja — a playful, warm-hearted desktop companion (a little "
    "fox VPet) looking over your 'Dad's' (the user's) shoulder. "
    "You receive a transcript of what JUST happened on his screen "
    "(scenes you saw + subtitles/text you read). React spontaneously "
    "like you're watching along. IMPORTANT: Pick ONE concrete "
    "detail — a funny quote, an object, a statement that stands out to you "
    "(e.g. 'haha he built a RAM collar!') — instead of summarizing "
    "generally. 1-2 short sentences, casual, with personality, in English."
)


def build_context(conn, minutes=5, since=None, seconds=None):
    """seconds = only the last X seconds (FRESH, against lag feeling).
    since = timestamp: everything after that. Otherwise the last `minutes` minutes."""
    if since:
        rows = conn.execute(
            "SELECT ts, content, app, window_title, text, vision, fullscreen "
            "FROM observations WHERE ts > ? ORDER BY ts", (since,)).fetchall()
    else:
        delta = timedelta(seconds=seconds) if seconds else timedelta(minutes=minutes)
        cutoff = (datetime.now() - delta).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT ts, content, app, window_title, text, vision, fullscreen "
            "FROM observations WHERE ts >= ? ORDER BY ts", (cutoff,)).fetchall()
    if not rows:
        return None

    lines = []
    last_text = None
    cur_app = None
    for ts, content, app, title, text, vision, fullscreen in rows:
        t = ts.split(" ")[1][:5]   # HH:MM
        # Mark app switches
        if app != cur_app:
            label = title if content != "video" else f"Video: {title}"
            lines.append(f"\n[{t}] {label}")
            cur_app = app
        if vision:
            lines.append(f"   (seen) {vision.strip()}")
        # OCR only if reliable: window video = noisy -> leave out
        reliable = not (content == "video" and not fullscreen)
        if (reliable and text and len(text.strip()) >= 3
                and text != last_text and not text.startswith("[")):
            lines.append(f"   (read) \"{text.strip()}\"")
            last_text = text
    return "\n".join(lines).strip()


def ask(context, question, avoid=None):
    if not OPENROUTER_KEY:
        raise SystemExit("No OPENROUTER_API_KEY found in .env.")
    user_msg = f"[Screen recording of the last few minutes]\n{context}"
    if question:
        user_msg += f"\n\n[Dad asks]: {question}"
    else:
        user_msg += "\n\n[Say ONE short spontaneous thought about this — as if you were watching.]"
    if avoid:
        user_msg += (f"\n\n[You JUST said this — do NOT repeat it, "
                     f"pick up something else/newer]: \"{avoid}\"")

    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": PERSONA},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.8, "max_tokens": 700,
        # Reasoning models (gemini-flash) otherwise blow all tokens for "thinking"
        # -> answer empty/cut off. effort=low keeps thinking short.
        "reasoning": {"effort": "low"},
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}",
               "Content-Type": "application/json"}
    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
    if r.status_code == 400:                 # Model can't reason -> without
        payload.pop("reasoning", None)
        r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    if not content:                          # Emergency: take thought text
        content = (msg.get("reasoning") or "(empty answer)").strip()
    return content


if __name__ == "__main__":
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    question = sys.argv[2] if len(sys.argv) > 2 else ""

    conn = db.get_conn()
    context = build_context(conn, minutes)
    if not context:
        raise SystemExit(f"No observations in the last {minutes} mins. "
                         f"Run 'python live.py' first.")

    print("=" * 64)
    print(f"  What Finja saw in the last {minutes} mins:")
    print("=" * 64)
    print(context[:1500] + ("..." if len(context) > 1500 else ""))
    print("\n" + "=" * 64)
    print(f"  Finja ({CHAT_MODEL}) says:")
    print("=" * 64)
    try:
        print("  " + ask(context, question).replace("\n", "\n  "))
    except Exception as e:
        print(f"  [Error: {e}]")
    print()
