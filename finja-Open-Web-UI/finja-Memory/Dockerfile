# =====================================================================
#  Project: Adaptive Memory v4.1 - Dockerfile: v4.1.1 
#  Author:  JohnV2002 (J. Apps / Sodakiller1)
#  Inspired by: gramanoid (diligent_chooser)
#  License: Apache License 2.0
#  Copyright (c) 2025 J. Apps
#
#======================================================================
# Updated: 
#======================================================================
#   - went from python:3.11-slim -> Snyk = 22 Low Vulnerabilities 
#   + to python:3.12-slim-bookworm -> Snyk = 0 Vulnerabilities
#   + added no-cache dir to make it even slimmer
#   + added requirements.txt for better control of versions and bugs/Vulnerabilities
#   + optimized COPY order for Docker layer caching
# =====================================================================

FROM python:3.12-slim-bookworm
WORKDIR /app

# Install dependencies from requirements.txt
# First: upgrade pip tools (critical for security)
# Then: install app dependencies with no cache
COPY requirements.txt .
RUN pip install --upgrade --no-cache-dir pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Kopiere beide Dateien
COPY memory-server.py .
COPY .env .

EXPOSE 8000
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]

# This Dockerfile sets up a FastAPI application for the memory service.
# It uses Python 3.12 on a slim base image, installs necessary dependencies