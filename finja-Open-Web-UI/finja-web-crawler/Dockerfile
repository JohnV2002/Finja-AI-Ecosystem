# ======================================================================
#          Finja Web Crawler - Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module: finja-web-crawler
#   Author: J. Apps (JohnV2002 / Sodakiller1)
#   Version: 2.1.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   ✨ Security & Performance Upgrade:
#     • Multi-stage build to keep the final image clean and small
#     • Non-root user for enhanced security (unprivileged container)
#     • Optimized layer caching by copying requirements.txt first
#
# ======================================================================

# --- Stage 1: Build Stage ---
# Same Python tag as runtime — Dependabot may bump both; no hard-coded 3.XX paths.
FROM python:3.14-alpine AS builder
WORKDIR /app

# Install build dependencies for compiling Python packages if needed
RUN apk add --no-cache gcc linux-headers musl-dev

# Copy and install Python requirements into a neutral prefix (3.12 / 3.13 / 3.14 safe)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Final Stage ---
FROM python:3.14-alpine
WORKDIR /app

# Create non-root user and set permissions in ONE step (layer optimized)
RUN addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    chown -R appuser:appgroup /app

# site-packages + uvicorn (etc.) without hard-coded python3.12 paths
COPY --from=builder /install /usr/local

# Copy application code
COPY main.py .

# Switch to non-root user for security
USER appuser

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
