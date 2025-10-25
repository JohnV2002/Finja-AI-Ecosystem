# =====================================================================
#  Project: Finja Cloud Memory - Dockerfile: v4.1.7 (Optimization)
#  Author:  JohnV2002 (J. Apps / Sodakiller1)
#  Inspired by: gramanoid (diligent_chooser)
#  License: Apache License 2.0
#  Copyright (c) 2025 J. Apps
#
# =====================================================================
# Updated in v4.1.7:
# =====================================================================
#   + Added backups Folder to the docker.
#
# Updated in v4.1.6:
# =====================================================================
#   + LAYER OPTIMIZATION: Merged multiple RUN commands into a single layer
#     to improve build efficiency and reduce final image size.
#
# Updated in v4.1.5:
# =====================================================================
#   + Switched from python:slim to python:alpine for minimal base.
#   + Implemented a multi-stage build to keep the final image clean and small.
#   + Added a non-root user for enhanced security (container runs unprivileged).
#   + Optimized layer caching by copying requirements.txt first.
#   + FIXED: Now copies both site-packages AND binaries (uvicorn, etc.).
#   + FIXED: Added chown to solve user permission issues inside the container.
# =====================================================================

# Stage 1: Build Stage
FROM python:3.12-alpine AS builder
WORKDIR /app
RUN apk add --no-cache gcc linux-headers musl-dev
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Stage
FROM python:3.12-alpine
WORKDIR /app

# Erstelle Verzeichnisse, User und setze Rechte in EINEM Schritt (optimiert für Docker Layers)
RUN mkdir -p user_memories user_audio tts_cache backups && \
    addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    chown -R appuser:appgroup /app user_memories user_audio tts_cache

# Kopiere alles von der Build-Stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Kopiere den App-Code
COPY memory-server.py .

# Wechsle zum neuen User
USER appuser

EXPOSE 8000
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]