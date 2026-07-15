"""
======================================================================
         Flare (Finja Agentic Code) – Test Job
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / test
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

======================================================================
"""
import json
import time
import urllib.request

payload = {
    "task": "Fix the syntax bug in demo.py. Keep the add function returning a + b.",
    "files": [{"path": "demo.py", "content": "def add(a, b):\n    return a +\n"}],
}

request = urllib.request.Request(
    "http://localhost:8077/jobs",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=10) as response:
    created = json.loads(response.read().decode("utf-8"))

print(json.dumps(created, indent=2))
time.sleep(20)

status_url = "http://localhost:8077/jobs/" + created["job_id"]
with urllib.request.urlopen(status_url, timeout=10) as response:
    status = json.loads(response.read().decode("utf-8"))

print(json.dumps(status, indent=2)[:3000])
