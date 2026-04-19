# ─────────────────────────────────────────
# CVIS v9 — Multi-stage Dockerfile (FINAL)
# ─────────────────────────────────────────

# ── Stage 1: builder ──────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ──────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="CVIS v9 AIOps Backend"
LABEL org.opencontainers.image.version="9.0.0"

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1001 cvis

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Set working directory
WORKDIR /app

RUN mkdir -p /app/data && chown -R cvis:cvis /app/data

COPY --chown=cvis:cvis backend/ ./backend/

# 🔥 Copy FULL backend (includes gunicorn_conf.py, main.py, etc.)
COPY --chown=cvis:cvis backend/ ./backend/

# Ensure Python can resolve modules
ENV PYTHONPATH=/app

# Create writable directories
RUN mkdir -p model_versions logs && chown -R cvis:cvis /app

# Switch to non-root user
USER cvis

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Expose API port
EXPOSE 8000

# 🔥 FINAL ENTRYPOINT (correct path)
CMD ["gunicorn", "-c", "backend/gunicorn_conf.py", "backend.main:app"]
