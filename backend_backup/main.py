"""
CVIS v9 Backend — FastAPI
PyTorch LSTM + β-VAE + sklearn IF + Versioning + Alerts + Auth + Redis

Run (dev):  python backend_v9.py
Run (prod): gunicorn -c gunicorn_conf.py backend_v9:app
"""
import asyncio, threading, time, os
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Internal modules ──────────────────────────────────────
from logging_config import setup_logging, CorrelationIDMiddleware, AccessLogMiddleware
from auth         import require_scope, create_api_key, revoke_api_key, issue_token_pair, refresh_access_token
from redis_store  import (alert_check_and_set, cache_metrics, get_cached_metrics,
                           redis_info, publish_event, incr_counter)
from ml_engine    import get_engine
from model_registry import get_registry
from alert_engine   import get_alert_engine, AlertRule
from db           import (save_alert, load_alerts, load_events, maybe_save_snapshot,
                           load_snapshots, db_info, close_db)
from sse          import broadcast, stream_endpoint, client_count

import logging
setup_logging()
log = logging.getLogger("cvis.main")

# Event loop reference — set in lifespan, used by collector thread for SSE broadcast
_event_loop: asyncio.AbstractEventLoop = None

async def _push_and_persist(metrics: dict, scores):
    """Coroutine called from the collector thread via run_coroutine_threadsafe."""
    # 1. Broadcast to all SSE clients
    await broadcast("metrics", {
        "cpu":    metrics.get("cpu_percent", 0),
        "mem":    metrics.get("memory", 0),
        "disk":   metrics.get("disk_percent", 0),
        "net":    metrics.get("network_percent", 0),
        "health": metrics.get("health_score", 100),
        "anomaly": scores.ensemble_score,
    })
    await broadcast("ml", {
        "if_score":       scores.if_score,
        "vae_score":      scores.vae_score,
        "lstm_score":     scores.lstm_score,
        "ensemble_score": scores.ensemble_score,
        "steps_lstm":     scores.steps_lstm,
        "steps_vae":      scores.steps_vae,
        "lstm_trend":     scores.lstm_trend,
        "lstm_loss":      scores.lstm_loss,
        "vae_recon_loss": scores.vae_recon_loss,
        "feat_errors":    scores.feat_errors,
        "latent_mu":      scores.latent_mu,
        "model_fitted":   scores.model_fitted,
    })
    # 2. Persist snapshot to SQLite (sampled every 10s)
    await maybe_save_snapshot(metrics)


# ── Optional psutil ───────────────────────────────────────
try:
    import psutil
    PS_OK = True
except ImportError:
    PS_OK = False
    log.warning("psutil not found — synthetic metrics active")

# ── Shared state ──────────────────────────────────────────
from collections import deque
feature_buffer: deque = deque(maxlen=600)
_last_metrics: dict = {}
_lock = threading.Lock()

# ─────────────────────────────────────────────────────────
#  Background collector
# ─────────────────────────────────────────────────────────
def _collect():
    engine   = get_engine()
    registry = get_registry()
    last_save = time.time()
    AUTOSAVE_INTERVAL = int(os.environ.get("AUTOSAVE_INTERVAL_S", "300"))

    while True:
        try:
            feat, raw = _build_feature_vector()
            with _lock:
                feature_buffer.append(feat)
                _last_metrics.update(raw)

            engine.ingest(feat)
            scores = engine.score(feat)

            update = {
                "anomaly_score":  scores.ensemble_score,
                "if_score":       scores.if_score,
                "vae_score":      scores.vae_score,
                "lstm_score":     scores.lstm_score,
                "vae_recon_loss": scores.vae_recon_loss,
                "vae_kl_loss":    scores.vae_kl_loss,
                "lstm_loss":      scores.lstm_loss,
                "latent_mu":      scores.latent_mu,
                "latent_logvar":  scores.latent_logvar,
                "feat_errors":    scores.feat_errors,
                "lstm_trend":     scores.lstm_trend,
                "model_fitted":   scores.model_fitted,
                "steps_lstm":     scores.steps_lstm,
                "steps_vae":      scores.steps_vae,
                "lstm_loss_hist": scores.lstm_loss_hist[-30:],
                "vae_loss_hist":  scores.vae_loss_hist[-30:],
                "backend":        scores.backend,
            }
            with _lock:
                _last_metrics.update(update)

            # Push to SSE clients and persist snapshot
            merged = {**_last_metrics}
            asyncio.run_coroutine_threadsafe(
                _push_and_persist(merged, scores), _event_loop
            )

            # Auto-save model version
            if time.time() - last_save > AUTOSAVE_INTERVAL and scores.steps_lstm > 50:
                registry.save_version(
                    "ensemble", engine.state_dict(),
                    dict(ensemble_score=scores.ensemble_score,
                         steps_lstm=scores.steps_lstm, steps_vae=scores.steps_vae,
                         lstm_loss=scores.lstm_loss, vae_recon_loss=scores.vae_recon_loss),
                    description="auto-save",
                )
                last_save = time.time()

        except Exception as e:
            log.error("Collector error: %s", e, exc_info=True)
        time.sleep(float(os.environ.get("POLL_INTERVAL_S", "1")))


def _build_feature_vector():
    import math
    if not PS_OK:
        t = time.time()
        cpu  = 30 + 20 * abs(math.sin(t / 60))
        mem  = 45 + 10 * abs(math.sin(t / 90 + 1))
        disk = 25 +  5 * abs(math.sin(t / 120 + 2))
        net  = 30 + 15 * abs(math.sin(t / 45 + 3))
    else:
        cpu  = psutil.cpu_percent(interval=0.05)
        mem  = psutil.virtual_memory().percent
        try:
            d    = psutil.disk_io_counters()
            disk = min(100, (d.read_bytes + d.write_bytes) / 1e8 * 5)
        except Exception:
            disk = 0.0
        try:
            n   = psutil.net_io_counters()
            net = min(100, (n.bytes_sent + n.bytes_recv) / 1e8 * 10)
        except Exception:
            net = 0.0

    health = max(0, 100 - max(0, cpu-70)*0.35 - max(0, mem-60)*0.25)
    raw = {
        "cpu_percent":      round(float(cpu),    2),
        "memory":           round(float(mem),    2),
        "disk_percent":     round(float(disk),   2),
        "network_percent":  round(float(net),    2),
        "health_score":     round(float(health), 2),
        "collected_at":     time.time(),
    }
    feat = np.array([cpu/100, mem/100, disk/100, net/100, 0.0], dtype=np.float32)
    return feat, raw


# ─────────────────────────────────────────────────────────
#  Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    os.makedirs("logs", exist_ok=True)
    os.makedirs("model_versions", exist_ok=True)

    # Collector thread
    t = threading.Thread(target=_collect, daemon=True, name="cvis-collector")
    t.start()

    # Alert evaluation loop (every 5s) — saves alerts to SQLite + broadcasts SSE
    async def _alert_loop():
        ae = get_alert_engine()
        original_dispatch = ae._dispatch

        async def _db_and_sse_dispatch(alert):
            await save_alert(alert)
            await broadcast("alert", {
                "alert_id": alert.alert_id,
                "severity": alert.severity,
                "message":  alert.message,
                "fired_at": alert.fired_at,
            })
            await original_dispatch(alert)

        ae._dispatch = _db_and_sse_dispatch

        while True:
            if _last_metrics:
                m = dict(_last_metrics)
                for rule in ae.rules.values():
                    if rule.enabled:
                        ae._cooldowns.pop(rule.rule_id, None)
                ae._dispatch = _db_and_sse_dispatch
                async def _redis_dispatch(alert):
                    fired = await alert_check_and_set(
                        alert.rule_id,
                        ae.rules[alert.rule_id].cooldown_s if alert.rule_id in ae.rules else 60
                    )
                    if fired:
                        await _db_and_sse_dispatch(alert)
                        await publish_event(alert.severity, alert.message)
                        await incr_counter("total_alerts_fired")
                ae._dispatch = _redis_dispatch
                await ae.evaluate(m)
                await cache_metrics(m, ttl=3)
            await asyncio.sleep(5)

    asyncio.create_task(_alert_loop())
    log.info("CVIS v9 started — SSE /stream ready, SQLite at %s",
             os.environ.get("DB_PATH", "cvis.db"))
    yield
    await close_db()
    log.info("CVIS v9 shutdown — DB closed")


# ─────────────────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title="CVIS v9 AIOps Backend",
    version="9.0.0",
    description="PyTorch LSTM + β-VAE + sklearn IF · Versioning · Alerts · Auth · Redis",
    lifespan=lifespan,
    # Disable docs in production if needed
    docs_url="/docs" if os.environ.get("ENV") != "prod" else None,
    redoc_url=None,
)


# ── CORS ─────────────────────────────────────────────────
# In production, set ALLOWED_ORIGIN=https://yourdomain.com
# in your .env file.  Leave unset for local development only.
_ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
if _ALLOWED_ORIGIN != "*":
    _origins = [o.strip() for o in _ALLOWED_ORIGIN.split(",")]
else:
    _origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
    allow_credentials=_ALLOWED_ORIGIN != "*",   # credentials only with explicit origin
)

app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(AccessLogMiddleware)

# ── SSE stream (public — same trust level as /health) ─────
@app.get("/stream", tags=["System"], include_in_schema=False)
async def sse_stream(request: Request):
    """Real-time push stream. Connect once; receive metrics, ml, alert events."""
    return await stream_endpoint(request)


# ── Auth endpoints ────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class ApiKeyRequest(BaseModel):
    name:  str
    scope: str = "read"

class RefreshRequest(BaseModel):
    refresh_token: str

# In production replace with a real user store / LDAP / SSO
_USERS = {
    os.environ.get("CVIS_ADMIN_USER", "admin"):
    os.environ.get("CVIS_ADMIN_PASS", "changeme"),
}

@app.post("/auth/login", tags=["Auth"])
async def login(req: LoginRequest):
    if _USERS.get(req.username) != req.password:
        raise HTTPException(401, "Invalid credentials")
    pair = issue_token_pair(req.username, scope="admin")
    return {"access_token": pair.access_token, "refresh_token": pair.refresh_token,
            "token_type": "bearer", "expires_in": pair.expires_in}

@app.post("/auth/refresh", tags=["Auth"])
async def refresh(req: RefreshRequest):
    pair = await refresh_access_token(req.refresh_token)
    return {"access_token": pair.access_token, "refresh_token": pair.refresh_token,
            "token_type": "bearer", "expires_in": pair.expires_in}

@app.post("/auth/api-keys", tags=["Auth"])
async def create_key(req: ApiKeyRequest, principal=Depends(require_scope("admin"))):
    key = await create_api_key(req.name, req.scope)
    return {"key": key, "name": req.name, "scope": req.scope,
            "note": "Store this key securely — it will not be shown again"}

@app.delete("/auth/api-keys/{key_hash}", tags=["Auth"])
async def delete_key(key_hash: str, principal=Depends(require_scope("admin"))):
    await revoke_api_key(key_hash)
    return {"revoked": key_hash}


# ── OS endpoints (scope: read) ────────────────────────────
@app.get("/os/status", tags=["OS"])
async def os_status(principal=Depends(require_scope("read"))):
    cached = await get_cached_metrics()
    return cached or {**_last_metrics, "ps_available": PS_OK}

@app.get("/os/processes", tags=["OS"])
async def os_processes(principal=Depends(require_scope("read"))):
    if not PS_OK:
        return {"by_cpu": [], "by_mem": []}
    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent","status"]):
        try:
            if p.info["status"] == "zombie": continue
            procs.append({"pid": p.info["pid"], "name": (p.info["name"] or "unknown")[:24],
                          "cpu": round(p.info["cpu_percent"] or 0.0, 2),
                          "mem": round(p.info["memory_percent"] or 0.0, 2), "real": True})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {"by_cpu": sorted(procs, key=lambda x: x["cpu"], reverse=True)[:10],
            "by_mem": sorted(procs, key=lambda x: x["mem"], reverse=True)[:10]}


# ── ML endpoints ──────────────────────────────────────────
class FeatRequest(BaseModel):
    features: list[float] = Field(..., min_length=5, max_length=5)

@app.post("/ml/scores", tags=["ML"])
async def ml_scores(req: FeatRequest, principal=Depends(require_scope("read"))):
    feat = np.array(req.features, dtype=np.float32)
    m = get_engine().score(feat)
    return {
        "if_score":       float(m.if_score),
        "vae_score":      float(m.vae_score),
        "lstm_score":     float(m.lstm_score),
        "ensemble_score": float(m.ensemble_score),
        "model_fitted":   m.model_fitted,
        "backend":        m.backend,
    }

@app.get("/ml/status", tags=["ML"])
async def ml_status(principal=Depends(require_scope("read"))):
    m = get_engine().metrics
    return {
        "backend":        m.backend,
        "model_fitted":   m.model_fitted,
        "steps_lstm":     int(m.steps_lstm),
        "steps_vae":      int(m.steps_vae),
        "lstm_loss":      float(m.lstm_loss),
        "lstm_loss_hist": [float(v) for v in m.lstm_loss_hist[-30:]],
        "vae_loss_hist":  [float(v) for v in m.vae_loss_hist[-30:]],
        "vae_recon_loss": float(m.vae_recon_loss),
        "vae_kl_loss":    float(m.vae_kl_loss),
        "lstm_trend":     m.lstm_trend,
        "latent_mu":      [float(v) for v in m.latent_mu],
        "latent_logvar":  [float(v) for v in m.latent_logvar],
        "feat_errors":    [float(v) for v in m.feat_errors],
        "if_score":       float(m.if_score),
        "vae_score":      float(m.vae_score),
        "lstm_score":     float(m.lstm_score),
        "ensemble_score": float(m.ensemble_score),
        "buffer_size":    len(feature_buffer),
    }


# ── Model versioning (scope: admin) ──────────────────────
class SaveVersionRequest(BaseModel):
    model_name:  str = "ensemble"
    description: str = ""
    tag:         str = ""

@app.post("/models/save", tags=["Versioning"])
async def save_version(req: SaveVersionRequest, principal=Depends(require_scope("admin"))):
    engine = get_engine(); m = engine.metrics
    entry  = get_registry().save_version(
        req.model_name, engine.state_dict(),
        dict(ensemble_score=m.ensemble_score, steps_lstm=m.steps_lstm,
             steps_vae=m.steps_vae, lstm_loss=m.lstm_loss),
        req.description or f"Manual save · steps={m.steps_lstm+m.steps_vae}", req.tag)
    return {"version_id": entry.version_id, "saved": True}

@app.get("/models/versions", tags=["Versioning"])
async def list_versions(model_name: Optional[str] = None, principal=Depends(require_scope("read"))):
    return get_registry().list_versions(model_name)

@app.post("/models/activate/{model_name}/{version_id}", tags=["Versioning"])
async def activate_version(model_name: str, version_id: str, principal=Depends(require_scope("admin"))):
    state = get_registry().activate(model_name, version_id)
    if not state: raise HTTPException(404, "Version not found")
    get_engine().load_state_dict(state)
    return {"activated": version_id}

@app.post("/models/rollback/{model_name}", tags=["Versioning"])
async def rollback(model_name: str, principal=Depends(require_scope("admin"))):
    result = get_registry().rollback(model_name)
    if not result: raise HTTPException(404, "No previous version")
    vid, state = result; get_engine().load_state_dict(state)
    return {"rolled_back_to": vid}

@app.post("/models/rollback_best/{model_name}", tags=["Versioning"])
async def rollback_best(model_name: str, principal=Depends(require_scope("admin"))):
    result = get_registry().rollback_to_best(model_name)
    if not result: raise HTTPException(404, "No best version recorded")
    vid, state = result; get_engine().load_state_dict(state)
    return {"rolled_back_to_best": vid}

@app.delete("/models/{model_name}/{version_id}", tags=["Versioning"])
async def delete_version(model_name: str, version_id: str, principal=Depends(require_scope("admin"))):
    if not get_registry().delete_version(model_name, version_id):
        raise HTTPException(404, "Version not found or is active")
    return {"deleted": version_id}

@app.get("/models/stats", tags=["Versioning"])
async def version_stats(principal=Depends(require_scope("read"))):
    return get_registry().stats()


# ── Alert endpoints (write/admin) ─────────────────────────
class WebhookRequest(BaseModel):
    url: str; name: str; secret: str = ""

class EmailRequest(BaseModel):
    host: str; port: int = 587; username: str = ""; password: str = ""
    from_addr: str; to_addrs: list[str]; use_tls: bool = True

class RuleRequest(BaseModel):
    name: str; metric: str; operator: str; threshold: float
    severity: str = "WARNING"; cooldown_s: int = 60
    message_tpl: str = "{metric} is {value:.2f} (threshold: {threshold})"

@app.post("/alerts/webhooks", tags=["Alerts"])
async def add_webhook(req: WebhookRequest, principal=Depends(require_scope("write"))):
    wh = get_alert_engine().add_webhook(req.url, req.name, req.secret)
    return {"id": wh.id, "name": wh.name}

@app.delete("/alerts/webhooks/{wh_id}", tags=["Alerts"])
async def remove_webhook(wh_id: str, principal=Depends(require_scope("admin"))):
    if not get_alert_engine().remove_webhook(wh_id): raise HTTPException(404, "Not found")
    return {"deleted": wh_id}

@app.post("/alerts/webhooks/{wh_id}/test", tags=["Alerts"])
async def test_webhook(wh_id: str, principal=Depends(require_scope("write"))):
    return {"success": await get_alert_engine().test_webhook(wh_id)}

@app.put("/alerts/email", tags=["Alerts"])
async def configure_email(req: EmailRequest, principal=Depends(require_scope("admin"))):
    cfg = get_alert_engine().configure_email(**req.dict(), enabled=True)
    return {"configured": True, "to": cfg.to_addrs}

@app.get("/alerts/history", tags=["Alerts"])
async def alert_history(limit: int = 50, severity: Optional[str] = None,
                        principal=Depends(require_scope("read"))):
    # Try SQLite first; fall back to in-memory deque
    db_rows = await load_alerts(limit=limit, severity=severity)
    if db_rows:
        return db_rows
    return get_alert_engine().get_history(limit, severity)

@app.get("/alerts/stats", tags=["Alerts"])
async def alert_stats(principal=Depends(require_scope("read"))):
    total = 0
    from redis_store import get_client
    c = await get_client()
    if c:
        try: total = int(await c.get("cvis:total_alerts_fired") or 0)
        except Exception: pass
    stats = get_alert_engine().get_stats()
    stats["redis_total"] = total
    return stats

@app.get("/alerts/rules", tags=["Alerts"])
async def list_rules(principal=Depends(require_scope("read"))):
    return [vars(r) for r in get_alert_engine().rules.values()]

@app.post("/alerts/rules", tags=["Alerts"])
async def add_rule(req: RuleRequest, principal=Depends(require_scope("admin"))):
    import uuid as _u
    rule = AlertRule(rule_id=_u.uuid4().hex[:8], **req.dict())
    get_alert_engine().add_rule(rule); return vars(rule)

@app.delete("/alerts/rules/{rule_id}", tags=["Alerts"])
async def delete_rule(rule_id: str, principal=Depends(require_scope("admin"))):
    if not get_alert_engine().delete_rule(rule_id): raise HTTPException(404, "Not found")
    return {"deleted": rule_id}

@app.patch("/alerts/rules/{rule_id}", tags=["Alerts"])
async def patch_rule(rule_id: str, enabled: Optional[bool] = None,
                     threshold: Optional[float] = None, principal=Depends(require_scope("admin"))):
    kw: dict[str, object] = {}
    if enabled   is not None: kw["enabled"]   = enabled
    if threshold is not None: kw["threshold"] = threshold
    rule = get_alert_engine().update_rule(rule_id, **kw)
    if not rule: raise HTTPException(404, "Not found")
    return vars(rule)


# ── Prometheus /metrics (public — scraped by Prometheus/Grafana) ──
from fastapi.responses import PlainTextResponse

@app.get("/metrics", tags=["System"], response_class=PlainTextResponse,
         include_in_schema=False)
async def prometheus_metrics():
    """
    Prometheus text format.
    Scrape config:  - job_name: cvis
                      static_configs:
                        - targets: ['backend:8000']
    """
    m   = _last_metrics
    eng = get_engine().metrics
    ae  = get_alert_engine().get_stats()
    reg = get_registry().stats()

    def g(name: str, value, help_: str, type_: str = "gauge") -> str:
        v = round(float(value), 6) if value is not None else 0
        return (f"# HELP {name} {help_}\n"
                f"# TYPE {name} {type_}\n"
                f"{name} {v}\n")

    lines = [
        "# CVIS v9 metrics\n",
        g("cvis_cpu_percent",           m.get("cpu_percent", 0),     "Host CPU %"),
        g("cvis_memory_percent",         m.get("memory", 0),          "Host memory %"),
        g("cvis_disk_percent",           m.get("disk_percent", 0),    "Disk I/O %"),
        g("cvis_health_score",           m.get("health_score", 100),  "System health 0–100"),
        g("cvis_anomaly_score",          m.get("anomaly_score", 0),   "Ensemble anomaly score 0–1"),
        g("cvis_ml_if_score",            eng.if_score,                 "Isolation Forest anomaly score"),
        g("cvis_ml_vae_score",           eng.vae_score,                "β-VAE anomaly score"),
        g("cvis_ml_lstm_score",          eng.lstm_score,               "LSTM prediction error score"),
        g("cvis_ml_ensemble_score",      eng.ensemble_score,           "Ensemble score (IF×0.4+VAE×0.35+LSTM×0.25)"),
        g("cvis_ml_lstm_loss",           eng.lstm_loss,                "LSTM MSE training loss"),
        g("cvis_ml_vae_recon_loss",      eng.vae_recon_loss,          "VAE reconstruction loss"),
        g("cvis_ml_vae_kl_loss",         eng.vae_kl_loss,             "VAE KL divergence"),
        g("cvis_ml_steps_lstm",          eng.steps_lstm,               "LSTM training steps", "counter"),
        g("cvis_ml_steps_vae",           eng.steps_vae,                "VAE training steps",  "counter"),
        g("cvis_ml_model_fitted",        int(eng.model_fitted),        "1 if IF model is fitted"),
        g("cvis_ml_feature_buffer_size", len(feature_buffer),          "Feature replay buffer size"),
        g("cvis_alerts_critical_total",  ae.get("critical", 0),        "Critical alerts fired", "counter"),
        g("cvis_alerts_warning_total",   ae.get("warning",  0),        "Warning alerts fired",  "counter"),
        g("cvis_alerts_info_total",      ae.get("info",     0),        "Info alerts fired",     "counter"),
        g("cvis_alerts_rules_active",    ae.get("rules_active", 0),    "Alert rules currently enabled"),
        g("cvis_model_versions_total",
          sum(v.get("total_versions", 0) for v in reg.values()),        "Total saved model versions"),
    ]
    return "".join(lines)


# ── Health (public — no auth) ─────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    e = get_engine()
    return {
        "status":         "ok",
        "model_fitted":   e.metrics.model_fitted,
        "buffer":         len(feature_buffer),
        "steps_lstm":     e.metrics.steps_lstm,
        "steps_vae":      e.metrics.steps_vae,
        "ps":             PS_OK,
        "redis":          await redis_info(),
        "db":             await db_info(),
        "sse_clients":    client_count(),
        "versions":       get_registry().stats(),
        "alert_stats":    get_alert_engine().get_stats(),
    }

@app.get("/db/snapshots", tags=["System"])
async def get_snapshots(hours: float = 1.0, principal=Depends(require_scope("read"))):
    """Historical metric snapshots from SQLite (up to 24h)."""
    return await load_snapshots(hours=min(hours, 24.0))

@app.get("/db/events", tags=["System"])
async def get_events(limit: int = 60, principal=Depends(require_scope("read"))):
    """Persisted event log from SQLite."""
    rows = await load_events(limit=limit)
    return rows or []


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  CVIS v9.0 · dev server (single worker)")
    print("  For production: gunicorn -c gunicorn_conf.py backend_v9:app")
    print(f"  psutil : {'✓' if PS_OK else '✗'}")
    print("  Docs   : http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run("backend_v9:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", 8000)),
                reload=False, log_level="warning", access_log=False)
