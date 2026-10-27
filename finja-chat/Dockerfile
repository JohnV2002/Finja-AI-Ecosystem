# Project: Finja Chat System
# Module: container / Dockerfile
# Author: J. Apps (JohnV2002 / Sodakiller1)
# Version: 2.5.0
# Description: One non-root image for the overlay pages, the song-request server and the VPet bridge.
# New in v2.5.0: First container image (base image is a required digest-pinned build argument).
# Copyright (c) 2026 J. Apps - Licensed under the MIT License.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FINJA_CHAT_HOST=0.0.0.0 \
    SPOTIFY_TOKEN_CACHE=/app/private/.cache

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system chat \
    && adduser --system --ingroup chat chat \
    && mkdir -p /app/private /srv/static \
    && chown chat:chat /app/private

COPY core ./core
COPY analytics_sender.py analytics_contract.json chat_stats.py spotify_request_server_env.py command_bridge.py ./
COPY index_merged.html bot_merged.html commands.html twitch_auth.js quickstart.svg /srv/static/

USER chat
EXPOSE 8088 8091 8099
VOLUME ["/app/private"]
CMD ["python", "spotify_request_server_env.py"]
