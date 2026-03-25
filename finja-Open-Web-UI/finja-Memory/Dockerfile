# ======================================================================
#          Finja Cloud Memory - Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module: finja-cloud-memory
#   Author: J. Apps (JohnV2002 / Sodakiller1)
#   Inspired by: gramanoid (diligent_chooser)
#   Version: 4.4.2
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the Apache License 2.0
#
# ----------------------------------------------------------------------
#
#   ✨ New in 4.4.2:
#     • Added backups folder to the container
#
#   ✨ New in 4.4.1:
#     • Layer optimization: merged multiple RUN commands into a single
#       layer for better build efficiency and smaller image size
#
#   ✨ New in 4.4.0:
#     • Switched from python:slim to python:alpine for minimal base
#     • Multi-stage build to keep the final image clean and small
#     • Non-root user for enhanced security (unprivileged container)
#     • Optimized layer caching by copying requirements.txt first
#     • Fixed: now copies both site-packages AND binaries (uvicorn, etc.)
#     • Fixed: added chown to solve permission issues inside container
#
# ======================================================================

# --- Stage 1: Build Stage ---
FROM python:3.12-alpine AS builder
WORKDIR /app
RUN apk add --no-cache gcc linux-headers musl-dev
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Final Stage ---
FROM python:3.12-alpine
WORKDIR /app

# Create directories, user, and set permissions in ONE step (layer optimized)
RUN mkdir -p user_memories user_audio tts_cache backups && \
    addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    chown -R appuser:appgroup /app user_memories user_audio tts_cache backups

# Copy installed packages from build stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder --chmod=555 /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appgroup --chmod=555 memory-server.py .

# Switch to non-root user
USER appuser

EXPOSE 8000
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]