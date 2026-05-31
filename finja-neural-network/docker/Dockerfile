# ==========================================
# Finja AI - Docker Image (CPU Edition)
# ==========================================
# Builds the CPU-only Docker image for the Finja AI runtime.
#
# Main Responsibilities:
# - Install system packages required for audio and HTTP tooling.
# - Install Python dependencies with pinned CPU-only PyTorch packages.
# - Copy the project into /app and prepare the entrypoint.
#
# Side Effects:
# - Downloads operating system and Python packages during image builds.
# - Removes cached package metadata and Python cache folders from the image.
# - Exposes the dashboard service on port 8051.
#
# Build:  docker build -t finja-ai -f docker/Dockerfile .
# Run:    docker compose -f docker/docker-compose.yml up -d
# ==========================================

FROM python:3.11-slim

# System dependencies for audio libraries such as coqui-tts and soundfile.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install requirements first for Docker layer caching.
COPY requirements.txt .

# Install CPU-only PyTorch first from its own index to avoid the large PyPI build.
# Pin the version so new upstream releases cannot unexpectedly stall builds.
RUN pip install --no-cache-dir --timeout 120 \
    "torch==2.5.1+cpu" "torchaudio==2.5.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

# Install the remaining dependencies; torch and torchaudio are already installed above.
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

# Copy the project.
COPY . .

# Keep __pycache__ and .venv out of the image.
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

# Normalize Windows CRLF to Linux LF for the entrypoint and .env.
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix && rm -rf /var/lib/apt/lists/* \
    && dos2unix /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

# Dashboard port.
EXPOSE 8051

# Healthcheck: the dashboard already responds on /events.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8051/events || exit 1

# Entrypoint copies state files and then starts the dashboard.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
