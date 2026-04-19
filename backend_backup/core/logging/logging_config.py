"""
CVIS v9 — logging_config.py
Structured JSON logging with:
  • RotatingFileHandler  (10 MB × 5 files)
  • StreamHandler        (stdout for Docker / Loki)
  • Optional Loki HTTP handler
  • Correlation-ID middleware (trace requests across workers)
  • uvicorn/gunicorn access log unified into root logger
"""

import json, logging, logging.handlers, os, time, uuid
from typing import Callable

# ── Log level from env ────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_DIR   = os.environ.get("LOG_DIR",   "logs")
LOKI_URL  = os.environ.get("LOKI_URL",  "")   # e.g. http://loki:3100/loki/api/v1/push

os.makedirs(LOG_DIR, exist_ok=True)

# ── JSON formatter ────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """
    Emits one JSON object per line — consumed by Loki / ELK / CloudWatch.
    Fields: time, level, logger, message, [exc_info], [correlation_id], [**extra]
    """
    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "time":    self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%03dZ"),
            "level":   record.levelname,
            "logger":  record.name,
            "pid":     record.process,
            "message": record.getMessage(),
        }
        # Correlation ID injected by middleware
        if hasattr(record, "correlation_id"):
            doc["correlation_id"] = record.correlation_id
        # Exception info
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        # Any extra fields attached by callers
        for key in ("worker", "route", "status", "duration_ms", "rule_id",
                    "version_id", "alert_id", "scope"):
            if hasattr(record, key):
                doc[key] = getattr(record, key)
        return json.dumps(doc, default=str)


# ── Loki handler (optional, best-effort) ─────────────────
class LokiHandler(logging.Handler):
    """
    Fire-and-forget HTTP POST to Grafana Loki.
    Batches up to 50 log lines or 5 seconds, whichever comes first.
    Falls back silently if Loki is unreachable.
    """
    def __init__(self, url: str, labels: dict = None):
        super().__init__()
        self.url    = url.rstrip("/")
        self.labels = labels or {"app": "cvis", "env": os.environ.get("ENV", "prod")}
        self._batch: list = []
        self._last_flush = time.monotonic()
        # Lazy import to avoid hard dependency
        try:
            import httpx
            self._http = httpx.Client(timeout=5)
            self._ok   = True
        except ImportError:
            self._ok = False

    def emit(self, record: logging.LogRecord):
        if not self._ok:
            return
        try:
            msg = self.format(record)
            ts  = str(int(record.created * 1e9))   # nanoseconds
            self._batch.append([ts, msg])
            now = time.monotonic()
            if len(self._batch) >= 50 or (now - self._last_flush) >= 5:
                self._flush()
        except Exception:
            self.handleError(record)

    def _flush(self):
        if not self._batch:
            return
        streams = [{"stream": self.labels, "values": self._batch.copy()}]
        payload = {"streams": streams}
        self._batch.clear()
        self._last_flush = time.monotonic()
        try:
            self._http.post(f"{self.url}/loki/api/v1/push", json=payload)
        except Exception:
            pass   # Loki unavailable — no crash


# ── Setup function ────────────────────────────────────────
def setup_logging():
    """
    Call once at app startup.
    Sets up the root logger + CVIS-specific loggers.
    """
    json_fmt = JsonFormatter()

    # 1. Rotating file (10 MB × 5)
    file_handler = logging.handlers.RotatingFileHandler(
        filename    = os.path.join(LOG_DIR, "cvis.log"),
        maxBytes    = 10 * 1024 * 1024,   # 10 MB
        backupCount = 5,
        encoding    = "utf-8",
    )
    file_handler.setFormatter(json_fmt)

    # Separate file for access logs (request traces)
    access_handler = logging.handlers.RotatingFileHandler(
        filename    = os.path.join(LOG_DIR, "access.log"),
        maxBytes    = 20 * 1024 * 1024,
        backupCount = 3,
        encoding    = "utf-8",
    )
    access_handler.setFormatter(json_fmt)

    # 2. Stdout (Docker → Loki / CloudWatch)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(json_fmt)

    # 3. Optional Loki
    handlers = [file_handler, stream_handler]
    if LOKI_URL:
        loki = LokiHandler(LOKI_URL)
        loki.setFormatter(json_fmt)
        handlers.append(loki)

    # 4. Root logger
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    for h in handlers:
        root.addHandler(h)

    # 5. Access logger (uvicorn/gunicorn requests)
    access_log = logging.getLogger("cvis.access")
    access_log.addHandler(access_handler)
    access_log.propagate = False

    # 6. Quiet noisy libs
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("cvis").info(
        "Logging initialised",
        extra={"level": LOG_LEVEL, "loki": bool(LOKI_URL)},
    )


# ── FastAPI middleware: Correlation-ID injection ──────────
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Attaches a UUID correlation ID to every request.
    Reads X-Request-ID from inbound headers (set by nginx/LB), else generates one.
    Injects it into log records via a LogRecord factory and returns it in responses.
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
        request.state.correlation_id = cid

        # Inject into all log records for this request
        old_factory = logging.getLogRecordFactory()
        def _factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.correlation_id = cid
            return record
        logging.setLogRecordFactory(_factory)

        try:
            response = await call_next(request)
        finally:
            logging.setLogRecordFactory(old_factory)

        response.headers["X-Request-ID"] = cid
        return response


# ── Access logging middleware ─────────────────────────────
class AccessLogMiddleware(BaseHTTPMiddleware):
    _access_log = logging.getLogger("cvis.access")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        self._access_log.info(
            "%s %s %d",
            request.method, request.url.path, response.status_code,
            extra={
                "route":       request.url.path,
                "method":      request.method,
                "status":      response.status_code,
                "duration_ms": duration_ms,
                "ip":          request.client.host if request.client else "unknown",
            },
        )
        return response
