# =====================================================================
#  Project: Finja Cloud Memory - Dockerfile: v4.1.3 (Fix)
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
#   + ✅ FIXED: Now copies both site-packages AND binaries (uvicorn, etc.)
# =====================================================================

# Stage 1: Build Stage
FROM python:3.12-alpine AS builder

WORKDIR /app

# Install system dependencies needed for pip (optional but recommended)
RUN apk add --no-cache gcc linux-headers musl-dev  

# Upgrade pip und installiere alle Dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Stage
FROM python:3.12-alpine

WORKDIR /app

# Erstelle einen dedizierten User (Security Best Practice)
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# 💡 WICHTIG: Kopiere BEIDE – die Python-Pakete UND die Binaries!
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Kopiere den App-Code (nachdem die Tools vorhanden sind)
COPY memory-server.py .

# Wechsle zum neuen User
USER appuser

EXPOSE 8000

# Starte die App – jetzt funktioniert uvicorn!
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]