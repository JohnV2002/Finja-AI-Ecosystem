"""
======================================================================
         Finja Weather API – Smoke Test
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / test_weather
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
  Smoke test for the Finja Weather API.

  Usage:
      python test_weather.py [base_url] [bearer_token]
  Defaults: http://localhost:8095 and BEARER_TOKEN from the environment/.env.
======================================================================
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8095").rstrip("/")
TOKEN = sys.argv[2] if len(sys.argv) > 2 else os.getenv("BEARER_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

# Leipzig, DE as a sample coordinate.
LAT, LON = 51.3397, 12.3731


def main() -> None:
    """Run health, current and forecast smoke checks."""
    print("health  :", requests.get(f"{BASE}/health", timeout=8).json())

    cur = requests.post(f"{BASE}/current", json={"latitude": LAT, "longitude": LON}, headers=HEADERS, timeout=12)
    print("current :", cur.status_code, cur.json())

    fc = requests.post(f"{BASE}/forecast", json={"latitude": LAT, "longitude": LON, "days": 3}, headers=HEADERS, timeout=12)
    print("forecast:", fc.status_code, "days =", len(fc.json().get("days", [])))

    print("stats   :", requests.get(f"{BASE}/stats", timeout=8).json())


if __name__ == "__main__":
    main()
