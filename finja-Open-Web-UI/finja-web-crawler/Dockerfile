# ======================================================================
#          Finja Web Crawler - Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module: finja-web-crawler
#   Author: J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.0.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the Apache License 2.0
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
FROM python:3.12-alpine AS builder
WORKDIR /app

# Install build dependencies for compiling Python packages if needed
RUN apk add --no-cache gcc linux-headers musl-dev

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Final Stage ---
FROM python:3.12-alpine
WORKDIR /app

# Create non-root user and set permissions in ONE step (layer optimized)
RUN addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    chown -R appuser:appgroup /app

# Copy installed packages and binaries from build stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY main.py .

# Switch to non-root user for security
USER appuser

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
