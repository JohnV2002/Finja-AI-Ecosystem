# =====================================================================
#  Project: Adaptive Memory v4.1 - Dockerfile: v4.1.2 
#  Author:  JohnV2002 (J. Apps / Sodakiller1)
#  Inspired by: gramanoid (diligent_chooser)
#  License: Apache License 2.0
#  Copyright (c) 2025 J. Apps
#
# =====================================================================
# Updated in v4.1.3:
# =====================================================================
#   + Switched from python:slim to python:alpine for minimal base and 3 CVEs.
#   + Implemented a multi-stage build to keep the final image clean and small.
#   + Added a non-root user for enhanced security (container runs unprivileged).
#   + Removed insecure COPY of .env file; configuration is now passed in at runtime.
#   + Optimized layer caching by copying requirements.txt first.
# =====================================================================

# Stage 1: Build Stage
# Hier installieren wir die Dependencies, um den Build-Cache optimal zu nutzen.
FROM python:3.12-alpine AS builder

WORKDIR /app

# Upgrade pip und installiere nur die Dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Stage
# Jetzt erstellen wir das finale, saubere Image ohne Build-Tools.
FROM python:3.12-alpine

WORKDIR /app

# Erstelle einen dedizierten User und eine Gruppe, um nicht als root zu laufen (Security Best Practice)
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Kopiere die installierten Pakete aus der Build-Stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Kopiere den App-Code
COPY memory-server.py .

# Wechsle zum neuen User
USER appuser

EXPOSE 8000

# Starte die App
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]