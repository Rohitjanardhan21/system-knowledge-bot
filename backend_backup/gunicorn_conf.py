"""
CVIS v9 — gunicorn_conf.py
Production Gunicorn config for FastAPI (uvicorn workers).
Workers = min(CPU*2+1, 8) so we never over-provision on small instances.
"""

import multiprocessing
import os

# ── Workers ───────────────────────────────────────────────
# Env override takes precedence (for containers with constrained CPUs)
_env_workers = os.environ.get("GUNICORN_WORKERS", "")
if _env_workers.isdigit() and int(_env_workers) > 0:
    # Explicit override from env / docker-compose — always respected.
    workers = int(_env_workers)
else:
    cpu_count = multiprocessing.cpu_count()
    # Formula: min(CPU × 2, 4).
    # Rationale: uvicorn workers are async; doubling CPUs is plenty.
    # Cap at 4 to keep RAM usage predictable on small EC2/VPS instances.
    # On a 2-vCPU EC2 t3.small this gives workers=2.
    # Scale up via GUNICORN_WORKERS env var on larger instances.
    workers = min(cpu_count * 2, 4)

worker_class = "uvicorn.workers.UvicornWorker"   # async worker (ASGI)

# ── Binding ───────────────────────────────────────────────
bind    = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
backlog = 2048

# ── Timeouts ──────────────────────────────────────────────
timeout          = 60    # kill worker if no response in 60s (ML inference can be slow)
graceful_timeout = 30    # wait 30s for in-flight requests during reload
keepalive        = 5

# ── Process naming ────────────────────────────────────────
proc_name = "cvis-backend"

# ── Logging ───────────────────────────────────────────────
# Access log format: JSON (picked up by Loki / ELK)
access_log_format = (
    '{"time":"%(t)s","method":"%(m)s","path":"%(U)s",'
    '"status":"%(s)s","bytes":%(b)s,"rt":"%(L)ss",'
    '"referer":"%(f)s","ua":"%(a)s"}'
)
accesslog   = "-"    # stdout → Docker log driver
errorlog    = "-"
loglevel    = os.environ.get("LOG_LEVEL", "warning")

# ── Worker recycling (memory leak guard) ──────────────────
max_requests      = 1000   # restart worker after N requests
max_requests_jitter = 100   # add jitter so workers don't restart simultaneously

# ── Hooks ─────────────────────────────────────────────────
def on_starting(server):
    server.log.info("CVIS v9 starting — workers=%d", workers)

def post_fork(server, worker):
    server.log.debug("Worker %d spawned (pid %d)", worker.age, worker.pid)

def worker_exit(server, worker):
    server.log.warning("Worker %d exited (pid %d)", worker.age, worker.pid)

def on_exit(server):
    server.log.info("CVIS v9 shutdown complete")
