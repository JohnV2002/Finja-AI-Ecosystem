# =====================================================================
#  Project: OCR Tika-Docker
#  License: Apache License 2.0
# =====================================================================

# Dieses Projekt steht unter der Apache License 2.0
# Original: https://github.com/apache/tika-docker?tab=Apache-2.0-1-ov-file
# – veröffentlicht unter Apache 2.0.
# Siehe LICENSE-Datei oder https://www.apache.org/licenses/LICENSE-2.0

# Basis: offizielles Tika-Server-Image mit eingebautem Tesseract-Support
FROM logicalspark/docker-tikaserver:latest

# Root für Paketinstallation
USER root

# Deutsche + Englische Tesseract-Sprachdaten installieren
# (weitere Sprachen: tesseract-ocr-<lang>, z. B. tesseract-ocr-fra, -ita, -spa ...)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tesseract-ocr-deu \
      tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Tesseract-Datenpfad (typisch für Debian/Ubuntu)
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# Optional: Tika OCR Feintuning (nur Beispiele; je nach Bedarf aktivieren)
# ENV TIKA_OCR_TIMEOUT=120
# ENV TIKA_OCR_PAGE_SEGMENTATION_MODE=1
# ENV TIKA_OCR_MIN_FILE_SIZE_TO_OCR=0
# ENV TIKA_OCR_MAX_FILE_SIZE_TO_OCR=200000000

# Setze wieder den Nicht-Root User, wie beim Basisimage üblich
USER 10001
