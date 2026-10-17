# ======================================================================
#          Flare (Finja Agentic Code) – Orchestrator Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-agentic-code / orchestrator
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.11.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   Builds the orchestrator API (FastAPI). Includes the Docker CLI so it
#   can spawn short-lived worker containers via the mounted Docker socket.
#
# ======================================================================

FROM python:3.14-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli \
    && rm -rf /var/lib/apt/lists/*

COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator/app ./app
COPY core ./core

EXPOSE 8077
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8077"]
