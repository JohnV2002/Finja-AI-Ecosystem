# =====================================================================
#  Project: Finja Cloud Musik API Docker - Dockerfile
#  Module: finja-music-docker-spotify
#  Author: J. Apps (JohnV2002 / Sodakiller1)
#  Version: 1.1.0
#  Description: Dockerfile for the Music API service.
#
#  ✨ New in 1.1.0:
#    • Fixed SonarQube issue docker:S7019 (Shell form to Exec form)
#    • Translated comments to English
#    • Updated copyright to 2026
#
# ---------------------------------------------------------------------
#  Copyright (c) 2026 J. Apps
#  Licensed under the MIT License.
# =====================================================================

# Stage 1: Builder
# Compile and install dependencies here.
FROM python:3.11-alpine AS builder

WORKDIR /app

# Install build tools
RUN apk add --no-cache gcc linux-headers musl-dev

# Copy requirements.txt
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---

# Stage 2: Final
# This is the actual image used at the end.
FROM python:3.11-alpine

WORKDIR /app

# Create directories, user, and set permissions
RUN addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    mkdir -p Nowplaying Memory SongsDB cache && \
    chown -R appuser:appgroup /app Nowplaying Memory SongsDB cache

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy executable files (like uvicorn) - Set to read-only (SonarQube Security)
COPY --from=builder --chmod=555 /usr/local/bin /usr/local/bin

# Copy read-only application files as root-owned (SonarQube S6504 + S7020)
# appuser can still read/execute via chmod=555, but cannot modify application code
COPY --chown=root:root --chmod=555 app.py .
COPY --chown=root:root --chmod=555 config_min.json .
COPY --chown=root:root --chmod=555 requirements.txt .

# Copy writable data directories as appuser-owned (app needs write access at runtime)
COPY --chown=appuser:appgroup --chmod=555 Memory ./Memory
COPY --chown=appuser:appgroup --chmod=555 SongsDB ./SongsDB

# Ensure data directories are writable at runtime for the appuser (required for app data storage)
RUN chown -R appuser:appgroup Nowplaying Memory SongsDB cache && \
    chmod -R 750 Nowplaying Memory SongsDB cache

# Switch to non-privileged user
USER appuser

# Expose the port
EXPOSE 8022

# Standard start command (Exec form to satisfy SonarQube S7019)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8022"]