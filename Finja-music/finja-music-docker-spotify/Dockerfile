# =====================================================================
#  Project: Finja Cloud Musik API Docker - Dockerfile: v1.0.0
#  Author:  JohnV2002 (J. Apps / Sodakiller1)
#  License: MIT License (c) 2025 J. Apps
# =====================================================================

# Stage 1: Builder
# Hier werden die Abhängigkeiten kompiliert und installiert.
FROM python:3.11-alpine AS builder

WORKDIR /app

# Installiere Build-Tools
RUN apk add --no-cache gcc linux-headers musl-dev

# Kopiere die requirements.txt
COPY requirements.txt .

# Installiere die Python-Abhängigkeiten
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---

# Stage 2: Final
# Das ist das eigentliche Image, das am Ende verwendet wird.
FROM python:3.11-alpine

WORKDIR /app

# Erstelle Verzeichnisse, User und setze Rechte
RUN addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    mkdir -p Nowplaying Memory SongsDB cache && \
    chown -R appuser:appgroup /app Nowplaying Memory SongsDB cache

# Kopiere die installierten Pakete aus der Builder-Stage.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# HIER IST DIE NEUE ZEILE: Kopiere die ausführbaren Dateien (wie uvicorn)
COPY --from=builder /usr/local/bin /usr/local/bin

# Kopiere den gesamten Anwendungscode
COPY --chown=appuser:appgroup . .

# Wechsle zum unprivilegierten Benutzer
USER appuser

# Gib den Port an
EXPOSE 8000

# Standard-Startbefehl
CMD uvicorn app:app --host 0.0.0.0 --port 8000