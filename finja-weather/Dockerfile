# ======================================================================
#          Finja Weather API – Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-weather
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
#     Builds the stateless weather microservice container.
#     Supports Open-Meteo (default) and Google Weather API.
#     No user data, no consent storage.
#
# ======================================================================

FROM python:3.12-slim

WORKDIR /app

# Install Python requirements (layer-cached).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY weather_api.py providers.py .

EXPOSE 80
CMD ["uvicorn", "weather_api:app", "--host", "0.0.0.0", "--port", "80"]
