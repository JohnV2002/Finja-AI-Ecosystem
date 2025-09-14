
# =====================================================================
#  Project: Web Crawler API
#  Author:  JohnV2002 (J. Apps / Sodakiller1)
#  License: MIT License
#  Copyright (c) 2025 J. Apps
# =====================================================================

FROM python:3.11-alpine

# Arbeitsverzeichnis
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Haupt-Script kopieren
COPY main.py .

# App starten
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
