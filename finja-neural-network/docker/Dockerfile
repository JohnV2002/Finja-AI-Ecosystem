# ==========================================
# Finja AI - Docker Image (CPU Edition)
# ==========================================
# Build:  docker build -t finja-ai -f docker/Dockerfile .
# Run:    docker compose -f docker/docker-compose.yml up -d
# ==========================================

FROM python:3.11-slim

# System-Dependencies fuer Audio libs (coqui-tts, soundfile, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements zuerst (Docker layer caching)
COPY requirements.txt .

# PyTorch CPU-only zuerst (eigener Index, sonst lädt pip die riesige PyPI-Version)
# Version gepinnt — ungepinnt lädt pip immer die neueste (kann bei neuen Releases hängen)
RUN pip install --no-cache-dir --timeout 120 \
    "torch==2.5.1+cpu" "torchaudio==2.5.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

# Restliche Dependencies (torch/torchaudio sind bereits oben installiert)
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

# Projekt kopieren
COPY . .

# __pycache__ und .venv gehoeren nicht ins Image
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

# Windows CRLF → Linux LF (entrypoint + .env)
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix && rm -rf /var/lib/apt/lists/* \
    && dos2unix /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

# Port fuer Dashboard
EXPOSE 8051

# Healthcheck: Dashboard antwortet auf /events (existiert bereits)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8051/events || exit 1

# Entrypoint: kopiert State-Files, dann startet Dashboard
ENTRYPOINT ["/app/docker/entrypoint.sh"]
