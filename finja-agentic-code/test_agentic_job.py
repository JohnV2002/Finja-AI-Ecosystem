"""
======================================================================
         Flare (Finja Agentic Code) – Manual Test Job
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / test
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Optional live API smoke test; inert during pytest collection.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""

import json
import os
import time
import urllib.request


def main() -> None:
    base_url = os.getenv("FLARE_BASE_URL", "http://localhost:8077").rstrip("/")
    token = os.getenv("ORCHESTRATOR_AUTH_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "task": "Fix the syntax bug in demo.py. Keep the add function returning a + b.",
        "repository": "finja-agentic-code",
        "files": [{"path": "demo.py", "content": "def add(a, b):\n    return a +\n"}],
    }

    request = urllib.request.Request(
        f"{base_url}/jobs",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        created = json.loads(response.read().decode("utf-8"))

    print(json.dumps(created, indent=2))

    status_url = f"{base_url}/jobs/{created['job_id']}"
    status = created
    for _ in range(60):
        with urllib.request.urlopen(urllib.request.Request(status_url, headers=headers), timeout=10) as response:
            status = json.loads(response.read().decode("utf-8"))
        if status["status"] in {"awaiting_approval", "failed", "rolled_back"}:
            break
        time.sleep(1)

    print(json.dumps(status, indent=2)[:3000])

    if status["status"] == "awaiting_approval":
        approval = urllib.request.Request(
            status_url + "/approve",
            data=json.dumps({"revision": status["revision"]}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(approval, timeout=10) as response:
            status = json.loads(response.read().decode("utf-8"))

        for _ in range(60):
            with urllib.request.urlopen(urllib.request.Request(status_url, headers=headers), timeout=10) as response:
                status = json.loads(response.read().decode("utf-8"))
            if status["status"] in {"completed", "failed", "rolled_back"}:
                break
            time.sleep(1)

    print(json.dumps(status, indent=2)[:3000])


if __name__ == "__main__":
    main()
