# =====================================================================
#  Project: Adaptive Memory v4.1 
#  Author:  JohnV2002 (J. Apps / Sodakiller1)
#  Inspired by: gramanoid (diligent_chooser)
#  License: Apache License 2.0
#  Copyright (c) 2025 J. Apps
# =====================================================================

FROM python:3.11-slim
WORKDIR /app

# Installiere python-dotenv für .env Unterstützung
RUN pip install fastapi uvicorn pydantic python-dotenv

# Kopiere beide Dateien
COPY memory-server.py .
COPY .env .

EXPOSE 8000
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]

# This Dockerfile sets up a FastAPI application for the memory service.
# It uses Python 3.11 on a slim base image, installs necessary dependencies