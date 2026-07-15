FROM python:3.11-slim

WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends patch \
    && rm -rf /var/lib/apt/lists/*

COPY worker.py .

CMD ["python", "/worker/worker.py"]
