# ======================================================================
#          Finja YouTube Shorts – Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-youtube
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.0.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   Description:
#     Builds a container with headless Chromium + Playwright + FastAPI.
#     Scrolls through YouTube Shorts, takes screenshots, and lets the
#     Brain (Neural Network) decide via Vision-LLM whether to like
#     and forward a video.
#
#   ✨ Features:
#     • Headless Chromium in mobile emulation mode
#     • Non-root user for enhanced security
#     • CRLF fix for Windows → Linux compatibility
#     • Healthcheck endpoint on port 8060
#
# ======================================================================

FROM python:3.11-slim

# ---- System Dependencies: Chromium + Libs ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libpango-1.0-0 \
    libcairo2 \
    curl \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# ---- Non-root User (Security) ----
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser -s /bin/bash appuser

WORKDIR /app

# ---- Python Dependencies (layer cache) ----
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

# ---- App Code ----
COPY . .

# ---- Cleanup ----
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true \
    && rm -f /app/tempCodeRunnerFile.py

# ---- CRLF Fix (Windows -> Linux) ----
RUN dos2unix /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# ---- Directories with correct permissions ----
RUN mkdir -p /data/chrome-profile /app/screenshots \
    && chown -R appuser:appuser /data /app /home/appuser

# ---- Switch to non-root ----
USER appuser

# ---- Internal API Port ----
EXPOSE 8060

# ---- Healthcheck ----
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8060/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
