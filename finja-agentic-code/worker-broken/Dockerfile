# ======================================================================
#     Flare (Finja Agentic Code) – Broken Demo Worker Dockerfile
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-agentic-code / worker-broken
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.11.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   Builds the DELIBERATELY BROKEN worker sandbox (finja-agent-worker-broken:dev),
#   the Phase A test track. It is a drop-in replacement for
#   finja-agent-worker:dev: same env contract, same /jobs mount, same
#   result files -- but each phase can be told to misbehave on purpose.
#
#   This image is test infrastructure and must never be the WORKER_IMAGE
#   of a production stack. The default plan is empty, so an unconfigured
#   container behaves like the real worker instead of failing silently.
#
#   The build context is the module root, because the honest code path is
#   delegated to the real worker instead of being copied and left to drift:
#
#     docker build -f worker-broken/Dockerfile -t finja-agent-worker-broken:dev .
#
# ======================================================================

FROM python:3.14-slim

LABEL org.opencontainers.image.title="Flare broken demo worker"
LABEL org.opencontainers.image.description="Fault-injection worker sandbox for Flare's Phase A test track. Not for production."
LABEL org.opencontainers.image.version="1.11.0"
LABEL de.jappshome.flare.test-infrastructure="true"

WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends patch \
    && rm -rf /var/lib/apt/lists/*

# The real worker provides the honest "ok" path; the wrapper injects faults.
# l1_diagnosis.py comes along because worker.py imports it -- without it the
# broken image fails at import and every scenario fails for the wrong reason.
COPY worker/l1_diagnosis.py .
COPY worker/worker.py .
COPY worker-broken/worker_broken.py .

ENV FLARE_FAULT_PLAN=""

CMD ["python", "/worker/worker_broken.py"]
