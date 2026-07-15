# ======================================================================
#          Finja Canvas – Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-canvas
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.0.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ======================================================================

FROM python:3.12-slim

# Do not run as root
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin painter

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_client.py config.py gen_canv.py index.html new_motif.py painter.py \
     plan_drawing.py render.py reset_canvas.py server.py shape_template.py entrypoint.sh ./

# Fresh initial state is created IN the image (don't copy the dev states from the
# machine, see .dockerignore) - canvas.csv/color.csv/gallery/ are usually
# overwritten/persisted via volume, see docker-compose.yml.
RUN python gen_canv.py \
    && touch color.csv \
    && mkdir -p gallery \
    && chmod +x entrypoint.sh \
    && chown -R painter:painter /app

USER painter

ENV PAINT_INTERVAL_SECONDS=20 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000', timeout=3)" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
