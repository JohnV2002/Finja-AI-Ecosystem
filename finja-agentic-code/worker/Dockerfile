# ======================================================================
#          Flare (Finja Agentic Code) – Worker Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-agentic-code / worker
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.0.1
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   Builds the short-lived worker sandbox image (finja-agent-worker:dev).
#   Spawned on demand by the orchestrator, one per job, with --network none
#   and no access to Finja's data, memory, or secrets.
#
# ======================================================================

FROM python:3.11-slim

WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends patch \
    && rm -rf /var/lib/apt/lists/*

COPY worker.py .

CMD ["python", "/worker/worker.py"]
