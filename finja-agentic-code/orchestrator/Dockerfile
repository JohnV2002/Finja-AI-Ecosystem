# ======================================================================
#          Flare (Finja Agentic Code) – Orchestrator Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-agentic-code / orchestrator
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
#   Builds the orchestrator API (FastAPI). Includes the Docker CLI so it
#   can spawn short-lived worker containers via the mounted Docker socket.
#
# ======================================================================

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8077
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8077"]
