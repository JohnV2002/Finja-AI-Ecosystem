"""
======================================================================
         Finja Omni Test – Cost Calculator
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-omni-test / kosten
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
  Cost calculator/warning for Finja's LLM calls (OpenRouter prices LIVE).
  Answers: "Model X, every N seconds, H hours/day -> what does that cost per month?"
  Later in the VPet as a warning: "Attention, the selected model costs ~X EUR/month.
  Are you sure you want to continue?"

      python kosten.py                 # Comparison table, 25s, 8h/day
      python kosten.py 20 6            # every 20s, 6h/day
======================================================================
"""

import sys
import requests

# Assumptions per comment call. IN_TOKENS can be set via 3rd arg (Finja's true
# system prompt with persona+memory is much larger than our test ~700!)
IN_TOKENS      = int(sys.argv[3]) if len(sys.argv) > 3 else 700
OUT_NORMAL     = 120    # short answer without reasoning
OUT_REASONING  = 550    # Reasoning models (gemini-flash etc.) burn output
EUR_PER_USD    = 0.92

# Candidates + whether they have reasoning tax (more output tokens).
# (qwen *-flash are blocked on ZDR/Guardrail accounts -> here are the ones that run)
CANDIDATES = [
    ("google/gemini-3.5-flash",            True),
    ("nvidia/nemotron-3-ultra-550b-a55b",  False),
    ("nvidia/nemotron-3-super-120b-a12b",  False),   # cheaper Nemotron tier
    ("anthropic/claude-haiku-4.5",         False),
    ("qwen/qwen3-next-80b-a3b-instruct",   False),
    ("google/gemma-4-31b-it",              False),
]


def fetch_prices():
    data = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json()["data"]
    out = {}
    for m in data:
        p = m.get("pricing", {})
        try:
            out[m["id"].lstrip("~")] = (float(p["prompt"]) * 1e6, float(p["completion"]) * 1e6)
        except (KeyError, ValueError, TypeError):
            pass
    return out


def monthly(pin, pout, reasoning, interval_s, hours_day, days=30):
    out_tok = OUT_REASONING if reasoning else OUT_NORMAL
    per_call = IN_TOKENS / 1e6 * pin + out_tok / 1e6 * pout
    calls_h = 3600 / interval_s
    per_day = calls_h * per_call * hours_day
    return per_call, per_day, per_day * days


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    hours    = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    prices = fetch_prices()
    print("=" * 74)
    print(f"  LLM-COST  |  every {interval}s  |  {hours}h/day  |  "
          f"~{IN_TOKENS} in / Output per model")
    print("=" * 74)
    print(f"  {'Model':32} {'$/Call':>8} {'$/Day':>7} {'$/Month':>8} {'EUR/Month':>9}")
    print("  " + "-" * 70)

    rows = []
    for model, reasoning in CANDIDATES:
        pr = prices.get(model)
        if not pr:
            continue
        per_call, per_day, per_month = monthly(*pr, reasoning, interval, hours)
        rows.append((model, reasoning, per_call, per_day, per_month))

    for model, reasoning, pc, pd, pm in rows:
        tag = " (Reasoning!)" if reasoning else ""
        warn = "  ⚠️" if pm > 50 else ""
        print(f"  {model:32} {pc:8.4f} {pd:7.2f} {pm:8.2f} {pm*EUR_PER_USD:8.2f}€{warn}{tag}")

    print("  " + "-" * 70)
    print("  ⚠️ = over 50$/month. Reasoning models: output tokens explode.")
    if rows:
        cheap = min(rows, key=lambda r: r[4])
        print(f"\n  Cheapest: {cheap[0]}  ->  ~{cheap[4]*EUR_PER_USD:.2f}€/Month "
              f"at {hours}h/day every {interval}s")
