# ── Stage 1: Build frontend ─────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/system-ui

COPY system-ui/package.json system-ui/package-lock.json ./
RUN npm ci

COPY system-ui/ ./
RUN npm run build

# ── Stage 2: Build Python dependencies ─────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 3: Runtime ────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="CVIS v9 AIOps Backend"
LABEL org.opencontainers.image.version="9.0.0"

RUN apt-get update && apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash --uid 1001 cvis

COPY --from=builder /install /usr/local

RUN python -m pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY --chown=cvis:cvis backend/ ./backend/
COPY --chown=cvis:cvis frontend/ ./frontend/
COPY --from=frontend-builder --chown=cvis:cvis /build/system-ui/dist/ ./frontend/

COPY --chown=cvis:cvis cvis_temp.py ./cvis_temp.py
COPY --chown=cvis:cvis agent/ ./agent/
COPY --chown=cvis:cvis preflight/ ./preflight/
COPY --chown=cvis:cvis timeline/ ./timeline/
COPY --chown=cvis:cvis judgment/ ./judgment/

ENV PYTHONPATH=/app

RUN mkdir -p /app/data /app/model_versions /app/logs && \
    chown -R cvis:cvis /app

USER cvis

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
