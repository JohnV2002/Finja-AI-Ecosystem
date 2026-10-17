"""
======================================================================
      Flare (Finja Agentic Code) – Container Health Probe
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / orchestrator
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Exit code for Docker's HEALTHCHECK. Healthy only if the
               API answers and its quest supervisor is alive.

  New in v1.11.0:
    - First version. Before this the container had no health check, so a
      dead supervisor or a wedged API still showed as "running".

----------------------------------------------------------------------

  Docker marks a container unhealthy but does not restart it. Something
  outside (orchestration, a watchdog, a person) has to act on that.
  Standard library only, so the probe cannot fail on a missing package.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8077/health"
TIMEOUT_SECONDS = 5


def evaluate(health: object) -> tuple[bool, str]:
    """Judge a parsed /health document. Returns (healthy, reason)."""
    if not isinstance(health, dict):
        return False, "health document is not an object"
    if health.get("ok") is not True:
        return False, "orchestrator reports it is not ok"
    block = health.get("supervisor")
    if not isinstance(block, dict):
        return False, "health document has no supervisor block"
    if block.get("enabled") and block.get("stalled"):
        return False, "supervisor is stalled"
    return True, "ok"


def main() -> int:
    url = os.getenv("HEALTHCHECK_URL", DEFAULT_URL)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # nosec B310 - fixed local URL
            document = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError) as exc:
        sys.stderr.write(f"unhealthy: /health unreachable or unreadable ({type(exc).__name__})\n")
        return 1
    healthy, reason = evaluate(document)
    if not healthy:
        sys.stderr.write(f"unhealthy: {reason}\n")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
