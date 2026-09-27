"""
Synapse Backend — FastAPI
PyTorch LSTM + β-VAE + sklearn IF + Versioning + Alerts + Auth + Redis

Run (dev):  uvicorn backend.main:app --reload
Run (prod): gunicorn -c gunicorn_conf.py backend.main:app
"""
import sys, os as _os

BASE_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import asyncio, json as _json, threading, time, os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from collections import deque

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse as _FR, HTMLResponse as _HR,
    PlainTextResponse, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles as _SS
from pydantic import BaseModel, Field

from backend.core.logging.logging_config import (
    setup_logging, CorrelationIDMiddleware, AccessLogMiddleware,
)
from backend.core.auth.auth import (
    require_scope, create_api_key, revoke_api_key,
    issue_token_pair, refresh_access_token, get_redis,
)
from backend.core.storage.redis_store import (
    alert_check_and_set, cache_metrics, get_cached_metrics,
    redis_info, publish_event, incr_counter,
)
from backend.core.ml.ml_engine           import get_engine
from backend.core.ml.remote_inference     import RemoteInferenceManager
from backend.core.storage.model_registry import get_registry
from backend.core.alerts.alert_engine    import get_alert_engine, AlertRule
from backend.chat_routes import router as chat_router
from backend.core.storage.db import (
    save_alert, save_event, load_alerts, load_events, maybe_save_snapshot,
    load_snapshots, db_info, close_db, save_prediction_outcome,
)

import logging
setup_logging()
log = logging.getLogger("cvis.main")

try:
    from backend.core.cognitive.failure_dna       import get_dna_engine
    from backend.core.cognitive.forecaster         import get_forecaster
    from backend.core.cognitive.premortem          import get_premortem_engine
    from backend.core.actions.auto_remediation     import get_ar_engine
    from backend.core.cognitive.notifier           import get_notifier
    from backend.core.cognitive.black_box          import get_black_box
    from backend.core.cognitive.postmortem_builder import get_postmortem_builder
    COGNITIVE_OK = True
except Exception as _ce:
    log.warning("Cognitive layer unavailable: %s", _ce)
    COGNITIVE_OK = False

try:
    import psutil
    PS_OK = True
except ImportError:
    PS_OK = False
    log.warning("psutil not found — synthetic metrics active")

feature_buffer: deque = deque(maxlen=600)
_last_metrics: dict   = {}
_lock = threading.Lock()
_event_loop: asyncio.AbstractEventLoop = None
_collector_stop = threading.Event()
_collector_thread = None
_devices: dict = {}

async def _restore_registered_devices():
    """Restore registered device identities from Redis into the in-memory registry."""
    redis = await get_redis()
    if redis is None:
        log.warning("Device registry unavailable during startup")
        return

    restored = 0
    try:
        async for key in redis.scan_iter(match="device:registry:*"):
            data = await redis.hgetall(key)
            if not data:
                continue

            device_id = data.get("device_id")
            if not device_id:
                continue

            try:
                capabilities = _json.loads(
                    data.get("capabilities", "[]")
                )
            except (TypeError, ValueError):
                capabilities = []

            _devices[device_id] = {
                "device_id": device_id,
                "device_name": data.get("device_name", "unknown"),
                "os": data.get("os", "unknown"),
                "os_version": data.get("os_version", ""),
                "hostname": data.get("hostname", ""),
                "capabilities": capabilities,
                "registered_at": float(data.get("registered_at", 0)),
                "status": "registered",
                "last_seen": None,
                "metrics": {},
                "processes": [],
            }
            restored += 1

        log.info("Restored %d registered device(s) from Redis", restored)
    except Exception as exc:
        log.exception("Failed to restore registered devices: %s", exc)


# Remote telemetry freshness / replay protection.
TELEMETRY_MAX_AGE_S = 120.0
TELEMETRY_MAX_FUTURE_SKEW_S = 30.0
_last_telemetry_timestamp: dict[str, float] = {}

TELEMETRY_WATERMARK_TTL_S = int(TELEMETRY_MAX_AGE_S * 2 + TELEMETRY_MAX_FUTURE_SKEW_S)

async def _accept_telemetry_timestamp(device_id: str, timestamp: float) -> bool:
    """Atomically accept a strictly newer telemetry timestamp."""
    redis = await get_redis()

    if redis is not None:
        key = f"telemetry:last_timestamp:{device_id}"
        script = """
        local current = redis.call('GET', KEYS[1])
        if current and tonumber(ARGV[1]) <= tonumber(current) then
            return 0
        end
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
        return 1
        """
        accepted = await redis.eval(
            script,
            1,
            key,
            str(timestamp),
            str(TELEMETRY_WATERMARK_TTL_S),
        )
        return bool(accepted)

    # Local fallback when Redis is temporarily unavailable.
    previous = _last_telemetry_timestamp.get(device_id)
    if previous is not None and timestamp <= previous:
        return False

    _last_telemetry_timestamp[device_id] = timestamp
    return True

# Persist the latest remote-device telemetry in the node format consumed
# by the intelligence pipeline.
NODES_DIR = Path("system_facts/nodes")
NODES_DIR.mkdir(parents=True, exist_ok=True)


def _persist_device_node(payload):
    node_data = {
        "node": payload.device_id,
        "node_name": payload.device_name or payload.hostname or payload.device_id,
        "os": payload.os,
        "os_version": payload.os_version,
        "hostname": payload.hostname,
        "timestamp": payload.timestamp,
        "metrics": {
            **payload.metrics,
            "processes": payload.processes,
        },
    }

    node_file = NODES_DIR / f"{payload.device_id}.json"
    node_file.write_text(_json.dumps(node_data, indent=2))



# Remote-device inference uses the shared model weights but keeps
# sequence history and EMA state isolated per device.
_remote_inference: Optional[RemoteInferenceManager] = None

def get_remote_inference() -> RemoteInferenceManager:
    global _remote_inference
    if _remote_inference is None:
        _remote_inference = RemoteInferenceManager(get_engine())
    return _remote_inference

# Rolling state for container CPU accounting — a delta is taken between
# successive collector-loop samples instead of a fresh isolated snapshot
# each call, so the measurement window tracks the real polling cadence.
_cpu_usage_state: dict = {"usage_ns": None, "ts": None}

# Rolling observed stability state. This is derived from real collector
# telemetry; it is not a Digital Twin or counterfactual simulation score.
_stability_history = deque(maxlen=60)


def _calculate_observed_stability(metrics: dict) -> dict:
    """Calculate a transparent stability index from recent real telemetry.

    The index combines current resource pressure, anomaly pressure, and
    short-term volatility. It is intentionally bounded to [0, 1].
    """
    cpu = max(0.0, min(100.0, float(metrics.get("cpu_percent", 0.0))))
    memory = max(0.0, min(100.0, float(metrics.get("memory", 0.0))))
    disk = max(0.0, min(100.0, float(metrics.get("disk_percent", 0.0))))
    anomaly = max(0.0, min(1.0, float(metrics.get("anomaly_score", 0.0))))

    sample = {
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "anomaly": anomaly,
    }
    _stability_history.append(sample)

    # Resource pressure: only sustained pressure above normal operating
    # ranges contributes strongly to instability.
    cpu_pressure = max(0.0, (cpu - 70.0) / 30.0)
    memory_pressure = max(0.0, (memory - 70.0) / 30.0)
    disk_pressure = max(0.0, (disk - 85.0) / 15.0)

    resource_pressure = min(
        1.0,
        0.40 * cpu_pressure +
        0.35 * memory_pressure +
        0.25 * disk_pressure,
    )

    # Recent movement/volatility from actual collector samples.
    volatility = 0.0
    if len(_stability_history) >= 2:
        previous = list(_stability_history)[-2]
        volatility = min(
            1.0,
            (
                abs(cpu - previous["cpu"]) / 30.0 * 0.4 +
                abs(memory - previous["memory"]) / 30.0 * 0.3 +
                abs(disk - previous["disk"]) / 15.0 * 0.2 +
                abs(anomaly - previous["anomaly"]) * 0.1
            ),
        )

    anomaly_pressure = anomaly

    instability = min(
        1.0,
        0.55 * resource_pressure +
        0.30 * anomaly_pressure +
        0.15 * volatility,
    )

    stability = round(max(0.0, min(1.0, 1.0 - instability)), 3)

    return {
        "stability": stability,
        "stability_pressure": round(instability, 3),
        "stability_volatility": round(volatility, 3),
        "stability_samples": len(_stability_history),
    }


def explain_and_act(metrics: dict) -> dict:
    reasons, actions = [], []
    cpu     = metrics.get("cpu_percent",   0)
    mem     = metrics.get("memory",        0)
    disk    = metrics.get("disk_percent",  0)
    anomaly = metrics.get("anomaly_score", 0)
    health  = metrics.get("health_score",  100)

    if cpu > 85:
        reasons.append(f"CPU critical ({cpu:.1f}%)")
        actions.append("Check top CPU processes — consider horizontal scaling")
    elif cpu > 70:
        reasons.append(f"CPU elevated ({cpu:.1f}%)")
        actions.append("Profile top processes for CPU hotspots")
    if mem > 85:
        reasons.append(f"Memory critical ({mem:.1f}%)")
        actions.append("Restart memory-heavy services — check for heap leaks")
    elif mem > 75:
        reasons.append(f"Memory pressure ({mem:.1f}%)")
        actions.append("Monitor memory trend — watch for monotonic growth")
    if disk > 85:
        reasons.append(f"Disk space utilization high ({disk:.1f}%)")
        actions.append("Check disk usage, large files, and log rotation")
    if anomaly > 0.7:
        reasons.append(f"ML ensemble anomaly ({anomaly:.3f})")
        actions.append("Investigate anomaly source — cross-reference with process list")
    elif anomaly > 0.4:
        reasons.append(f"ML activity elevated ({anomaly:.3f})")
        actions.append("Monitor for escalation — check recent changes")
    if health < 60:
        reasons.append(f"Health degraded ({health:.1f}%)")
        actions.append("System needs immediate attention")

    severity = (
        "CRITICAL" if anomaly > 0.8 or cpu > 90 or mem > 90 or disk > 95 else
        "HIGH"     if anomaly > 0.6 or cpu > 80 or mem > 80 or disk > 85 else
        "MEDIUM"   if anomaly > 0.3 or cpu > 70 or mem > 70 else
        "LOW"
    )
    return {
        "reason":   " + ".join(reasons) if reasons else "System stable",
        "actions":  actions             if actions else ["No action needed"],
        "severity": severity,
    }


def _read_v2_usage_ns(stat_path: Path) -> int:
    """cgroup v2 cpu.stat reports usage_usec (microseconds) — convert to ns."""
    line = next(x for x in stat_path.read_text().splitlines() if x.startswith("usage_usec "))
    return int(line.split()[1]) * 1000


def _read_v1_usage_ns(usage_path: Path) -> int:
    """cgroup v1 cpuacct.usage already reports nanoseconds."""
    return int(usage_path.read_text().strip())


def _cgroup_cpu_quota():
    """
    Detect the container's CPU quota and return (quota_cpus, usage_reader),
    where usage_reader() returns cumulative CPU time in nanoseconds.
    Supports both cgroup v2 and cgroup v1 (classic + hybrid mounts).
    Returns None when the container has no quota set (unlimited) or the
    relevant cgroup files aren't present/readable — callers should fall
    back to host-wide accounting in that case.
    """
    # cgroup v2
    v2_max, v2_stat = Path("/sys/fs/cgroup/cpu.max"), Path("/sys/fs/cgroup/cpu.stat")
    if v2_max.exists() and v2_stat.exists():
        quota, period = v2_max.read_text().strip().split()
        if quota == "max":
            return None
        return int(quota) / int(period), (lambda: _read_v2_usage_ns(v2_stat))

    # cgroup v1 (classic "cpu" controller, or hybrid "cpu,cpuacct" mount)
    for base in ("/sys/fs/cgroup/cpu,cpuacct", "/sys/fs/cgroup/cpu"):
        quota_f  = Path(f"{base}/cpu.cfs_quota_us")
        period_f = Path(f"{base}/cpu.cfs_period_us")
        usage_f  = Path(f"{base}/cpuacct.usage")
        if quota_f.exists() and period_f.exists() and usage_f.exists():
            quota_us  = int(quota_f.read_text().strip())
            period_us = int(period_f.read_text().strip())
            if quota_us <= 0:
                return None  # -1 == unlimited
            return quota_us / period_us, (lambda: _read_v1_usage_ns(usage_f))

    return None


def _container_cpu_percent() -> float:
    """
    CPU % scoped to the container's cgroup CPU quota (e.g. a 4-CPU quota
    fully saturated == 100%), matching what alert thresholds expect.

    Usage is measured as a delta between this call and the *previous*
    collector-loop call, not a fresh isolated snapshot each time. A
    short synchronous sample (e.g. sleep 0.5s, diff, return) measures a
    window that's disconnected from the real polling cadence and from
    whatever interval Docker's own stats are averaged over — under a
    bursty load, a half-second snapshot can land in a lull and read a
    much lower rate than Docker reports for the same period, even
    though both are reading the same cgroup counter. Diffing against
    the last sample instead ties our window to the actual ~poll
    interval, which tracks Docker's own refresh cadence far more
    closely and removes the per-call blocking sleep entirely (after
    the first sample).

    Falls back to host-wide psutil accounting when no quota is set
    (unlimited container) or cgroup files can't be read.
    """
    try:
        quota = _cgroup_cpu_quota()
        if quota is None:
            return float(psutil.cpu_percent(interval=0.5)) if PS_OK else 0.0

        cpus, read_usage_ns = quota
        now_ns = read_usage_ns()
        now_ts = time.monotonic()

        with _lock:
            prev_ns = _cpu_usage_state["usage_ns"]
            prev_ts = _cpu_usage_state["ts"]
            _cpu_usage_state["usage_ns"] = now_ns
            _cpu_usage_state["ts"]       = now_ts

        if prev_ns is None or prev_ts is None:
            # First sample ever — no baseline to diff against yet. Take
            # one short blocking measurement so startup doesn't report a
            # stale 0% until the next collector tick.
            time.sleep(0.5)
            after_ns = read_usage_ns()
            elapsed  = max(0.1, time.monotonic() - now_ts)
            used_seconds = (after_ns - now_ns) / 1_000_000_000
            with _lock:
                _cpu_usage_state["usage_ns"] = after_ns
                _cpu_usage_state["ts"]       = time.monotonic()
        else:
            elapsed = max(0.1, now_ts - prev_ts)
            used_seconds = (now_ns - prev_ns) / 1_000_000_000

        return max(0.0, min(100.0, (used_seconds / (elapsed * cpus)) * 100.0))
    except Exception:
        return float(psutil.cpu_percent(interval=0.5)) if PS_OK else 0.0


def _build_feature_vector():
    import math
    if not PS_OK:
        t    = time.time()
        cpu  = 30 + 20 * abs(math.sin(t / 60))
        mem  = 45 + 10 * abs(math.sin(t / 90  + 1))
        disk = 25 +  5 * abs(math.sin(t / 120 + 2))
        net  = 30 + 15 * abs(math.sin(t / 45  + 3))
    else:
        cpu  = _container_cpu_percent()
        mem  = psutil.virtual_memory().percent
        try:
            disk = psutil.disk_usage("/").percent
        except Exception:
            disk = 0.0
        try:
            n   = psutil.net_io_counters()
            net = min(100, (n.bytes_sent + n.bytes_recv) / 1e8 * 10)
        except Exception:
            net = 0.0

    health = max(0, 100 - max(0, cpu - 70) * 0.35 - max(0, mem - 60) * 0.25)
    raw = {
        "cpu_percent":     round(float(cpu),    2),
        "memory":          round(float(mem),    2),
        "disk_percent":    round(float(disk),   2),
        "network_percent": round(float(net),    2),
        "health_score":    round(float(health), 2),
        "collected_at":    time.time(),
    }
    feat = np.array([cpu/100, mem/100, disk/100, net/100, 0.0], dtype=np.float32)
    return feat, raw


async def _push_and_persist(metrics: dict, scores):
    # Persist the normal telemetry snapshot first.
    await maybe_save_snapshot(metrics)

    # Generate and persist structured system events independently.
    # Event failures must never interrupt telemetry persistence.
    try:
        from backend.event_engine import generate_events

        events = generate_events(metrics)

        for event in events:
            severity = str(event.get("severity", "low")).lower()
            message = str(event.get("message") or event.get("title") or "System event")

            await save_event(
                severity=severity,
                message=message,
            )

    except Exception as exc:
        log.exception("Event pipeline failed: %s", exc)


def _collect():
    # ── Windows fix ──────────────────────────────────────
    # On Windows the asyncio event loop is not transferable
    # across threads. Without this, run_coroutine_threadsafe
    # raises "RuntimeError: Event loop is closed".
    if sys.platform == "win32":
        asyncio.set_event_loop(asyncio.new_event_loop())

    engine    = get_engine()
    registry  = get_registry()
    last_save = time.time()

    AUTOSAVE_INTERVAL = int(os.environ.get("AUTOSAVE_INTERVAL_S", "300"))

    while not _collector_stop.is_set():
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
            _exp = explain_and_act({**_last_metrics, **update})
            update["severity"] = _exp["severity"]
            update["reason"]   = _exp["reason"]
            update["actions"]  = _exp["actions"]

            # Derive observed stability from the same real collector sample.
            # This is an observed telemetry index, not a Digital Twin score.
            update.update(_calculate_observed_stability({
                **_last_metrics,
                **update,
            }))

            with _lock:
                _last_metrics.update(update)

            # Guard against closed loop (Windows shutdown race)
            if _event_loop and not _event_loop.is_closed():
                try:
                    merged = dict(_last_metrics)
                    asyncio.run_coroutine_threadsafe(
                        _push_and_persist(merged, scores), _event_loop
                    )
                except RuntimeError:
                    pass

            if COGNITIVE_OK:
                try:
                    m        = dict(_last_metrics)
                    dna      = get_dna_engine()
                    fcast    = get_forecaster()
                    bb       = get_black_box()
                    notifier = get_notifier()

                    dna.ingest(m)
                    fcast.ingest(m)
                    get_premortem_engine().ingest(m)
                    try:
                        from backend.core.cognitive.degradation import get_degradation_detector
                        get_degradation_detector().ingest(m)
                    except Exception:
                        pass
                    get_ar_engine().update_metrics(m)

                    procs     = m.get("processes", {})
                    proc_list = procs.get("by_cpu", []) if isinstance(procs, dict) else []
                    bb.record(m, proc_list, m.get("reason", ""), m.get("severity", "LOW"))

                    try:
                        ar         = get_ar_engine()
                        ar.set_notifier(get_notifier())
                        preds      = dna.get_active_predictions()
                        dna_sum    = dna.get_dna_summary()
                        pred_dicts = [
                            {
                                "id":           p.prediction_id,
                                "type":         p.failure_type,
                                "confidence":   p.confidence * 100,
                                "severity":     p.severity,
                                "message":      p.plain_message,
                                "acknowledged": p.acknowledged,
                                "resolved":     p.resolved,
                            }
                            for p in preds
                        ]
                        ar.evaluate(pred_dicts, dna_sum)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception("Auto-remediation evaluation failed: %s", e)

                    prediction = dna.predict(m)
                    if prediction and not prediction.acknowledged:
                        notifier.send_prediction(prediction)

                    health_data = dna.get_health_score(m)
                    if health_data["score"] < 400:
                        notifier.send_health_alert(health_data["score"], health_data["grade"])

                    if m.get("severity") in ("HIGH", "CRITICAL") and m.get("reason"):
                        notifier.send_anomaly_alert(m["reason"], m["severity"])

                    with _lock:
                        _last_metrics["health_credit_score"] = health_data["score"]
                        _last_metrics["health_grade"]        = health_data["grade"]
                        _last_metrics["active_prediction"]   = (
                            {
                                "id":         prediction.prediction_id,
                                "type":       prediction.failure_type,
                                "eta_min":    round(prediction.minutes_remaining, 1),
                                "message":    prediction.plain_message,
                                "action":     prediction.plain_action,
                                "severity":   prediction.severity,
                                "confidence": round(prediction.confidence * 100, 0),
                            }
                            if prediction else None
                        )
                except Exception as e:
                    import logging
                    logging.getLogger("cvis").exception(
                        "Cognitive processing failed: %s", e
                    )

            if time.time() - last_save > AUTOSAVE_INTERVAL and scores.steps_lstm > 50:
                registry.save_version(
                    "ensemble", engine.state_dict(),
                    dict(
                        ensemble_score=scores.ensemble_score,
                        steps_lstm=scores.steps_lstm,
                        steps_vae=scores.steps_vae,
                        lstm_loss=scores.lstm_loss,
                        vae_recon_loss=scores.vae_recon_loss,
                    ),
                    description="auto-save",
                )
                last_save = time.time()

        except Exception as e:
            log.error("Collector error: %s", e, exc_info=True)
        _collector_stop.wait(float(os.environ.get("POLL_INTERVAL_S", "1")))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop, _collector_thread
    _event_loop = asyncio.get_running_loop()
    await _restore_registered_devices()

    os.makedirs("logs",           exist_ok=True)
    os.makedirs("model_versions", exist_ok=True)

    # Restore the explicitly active ensemble checkpoint before live collection.
    try:
        registry = get_registry()
        active = registry.get_active_version("ensemble")
        if active:
            state = registry.load_version("ensemble", active["version_id"])
            if state:
                get_engine().load_state_dict(state)
                log.info(
                    "Restored active ensemble: %s (steps_lstm=%s, steps_vae=%s)",
                    active["version_id"],
                    state.get("metrics", {}).get("steps_lstm", 0),
                    state.get("metrics", {}).get("steps_vae", 0),
                )
            else:
                log.warning(
                    "Active ensemble checkpoint could not be loaded: %s",
                    active["version_id"],
                )
        else:
            log.info("No active ensemble checkpoint configured")
    except Exception as e:
        log.warning("Ensemble restore failed: %s", e, exc_info=True)

    # Restore active cognitive predictions from SQLite into Failure-DNA.
    # Failure-DNA has its own JSON persistence, but predictions created through
    # the prediction storage layer must also survive a backend restart.
    try:
        from backend.core.storage.db import load_active_predictions
        from backend.core.cognitive.failure_dna import ActivePrediction
        import json

        dna = get_dna_engine()
        persisted_predictions = await load_active_predictions()
        restored_count = 0

        for row in persisted_predictions:
            pred_id = row.get("prediction_id")

            if not pred_id:
                continue
            try:
                evidence = row.get("evidence") or {}
                if isinstance(evidence, str):
                    try:
                        evidence = json.loads(evidence)
                    except Exception:
                        evidence = {}

                failure_type = str(
                    row.get("failure_type") or "UNKNOWN"
                ).upper()

                pattern_id = evidence.get(
                    "pattern_id",
                    f"dna_{failure_type}"
                )

                now = time.time()
                expected_at = row.get("expected_at")
                lead_time = float(
                    row.get("lead_time_seconds") or 0
                )

                if expected_at is None:
                    expected_at = now + lead_time

                minutes_remaining = max(
                    0.0,
                    (float(expected_at) - now) / 60.0
                )

                confidence = float(
                    row.get("confidence") or 0.0
                )

                severity = dna._severity_from_eta(
                    minutes_remaining,
                    confidence
                )

                prediction = ActivePrediction(
                    prediction_id=pred_id,
                    failure_type=failure_type,
                    detected_at=float(
                        row.get("created_at") or now
                    ),
                    predicted_eta=float(expected_at),
                    confidence=confidence,
                    minutes_remaining=minutes_remaining,
                    plain_message=evidence.get(
                        "message",
                        f"{failure_type} failure predicted in about "
                        f"{int(minutes_remaining)} minutes"
                    ),
                    plain_action=dna._plain_action(
                        type(
                            "_Pattern",
                            (),
                            {"failure_type": failure_type}
                        )()
                    ),
                    severity=severity,
                    pattern_id=pattern_id,
                    acknowledged=bool(row.get("acknowledged", 0)),
                )

                dna._active_predictions[pred_id] = prediction
                restored_count += 1

            except Exception as pred_error:
                log.warning(
                    "Failed to restore cognitive prediction %s: %s",
                    pred_id,
                    pred_error
                )

        log.info(
            "Restored %d active cognitive prediction(s) from SQLite",
            restored_count
        )

    except Exception as e:
        log.warning(
            "Cognitive prediction restore failed: %s",
            e,
            exc_info=True
        )

    _collector_stop.clear()
    _collector_thread = threading.Thread(target=_collect, daemon=True, name="cvis-collector")
    _collector_thread.start()

    async def _alert_loop():
        ae = get_alert_engine()
        await ae.restore_active_alerts()

        # Preserve the real notification dispatcher before adding
        # Redis-based notification throttling.
        original_dispatch = ae._dispatch

        async def _redis_dispatch(alert):
            # Persist every new incident regardless of notification
            # cooldown. Cooldown controls notifications, not incidents.
            await save_alert(alert)

            fired = await alert_check_and_set(
                alert.rule_id,
                ae.rules[alert.rule_id].cooldown_s
                if alert.rule_id in ae.rules
                else 60,
                device_id=getattr(alert, "device_id", None),
            )

            if fired:
                await original_dispatch(alert)
                await publish_event(alert.severity, alert.message)
                await incr_counter("total_alerts_fired")

        ae._dispatch = _redis_dispatch

        while True:
            if _last_metrics:
                await ae.evaluate(dict(_last_metrics))
                await cache_metrics(dict(_last_metrics), ttl=3)

            await asyncio.sleep(5)

    asyncio.create_task(_alert_loop())
    log.info("Synapse started — SQLite at %s", os.environ.get("DB_PATH", "cvis.db"))
    yield
    _collector_stop.set()
    if _collector_thread is not None and _collector_thread.is_alive():
        await asyncio.to_thread(_collector_thread.join, 5.0)
        if _collector_thread.is_alive():
            log.warning("Collector thread did not stop within shutdown timeout")
    await close_db()
    log.info("Synapse shutdown — DB closed")


app = FastAPI(
    title="Synapse AI Backend",
    version="1.0.6",
    description="Synapse — PyTorch LSTM + beta-VAE + sklearn IF · Versioning · Alerts · Auth · Redis",
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV") != "prod" else None,
    redoc_url=None,
)

app.include_router(
    chat_router,
    dependencies=[Depends(require_scope("read"))],
)

_ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
_origins = (
    [o.strip() for o in _ALLOWED_ORIGIN.split(",")]
    if _ALLOWED_ORIGIN != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
    allow_credentials=_ALLOWED_ORIGIN != "*",
)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(AccessLogMiddleware)


@app.get("/stream", tags=["System"], include_in_schema=False)
async def sse_stream(request: Request):
    async def event_gen():
        while True:
            if await request.is_disconnected():
                break
            try:
                m     = dict(_last_metrics)
                eng   = get_engine()
                eng_m = eng.metrics if eng else None
                ex    = explain_and_act(m)
                payload = {
                    "cpu_percent":         m.get("cpu_percent",       0),
                    "memory":              m.get("memory",            0),
                    "disk_percent":        m.get("disk_percent",      0),
                    "network_percent":     m.get("network_percent",   0),
                    "health_score":        m.get("health_score",      100),
                    "anomaly_score":       m.get("anomaly_score",     0),
                    "ensemble_score":      float(eng_m.ensemble_score) if eng_m else 0.0,
                    "if_score":            float(eng_m.if_score)       if eng_m else 0.0,
                    "vae_score":           float(eng_m.vae_score)      if eng_m else 0.0,
                    "lstm_score":          float(eng_m.lstm_score)     if eng_m else 0.0,
                    "model_fitted":        eng_m.model_fitted          if eng_m else False,
                    "steps_lstm":          int(eng_m.steps_lstm)       if eng_m else 0,
                    "steps_vae":           int(eng_m.steps_vae)        if eng_m else 0,
                    "reason":              ex["reason"],
                    "actions":             ex["actions"],
                    "severity":            ex["severity"],
                    "timestamp":           time.time(),
                    "health_credit_score": m.get("health_credit_score"),
                    "health_grade":        m.get("health_grade"),
                    "active_prediction":   m.get("active_prediction"),
                }
                yield f"event: metrics\ndata: {_json.dumps(payload)}\n\n"
            except Exception:
                yield "data: {}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class LoginRequest(BaseModel):
    username: str
    password: str

class ApiKeyRequest(BaseModel):
    name:  str
    scope: str = "read"
    device_id: str | None = None

class RefreshRequest(BaseModel):
    refresh_token: str

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
async def create_key(req: ApiKeyRequest, principal: dict = Depends(require_scope("admin"))):
    key = await create_api_key(req.name, req.scope, req.device_id)
    return {"key": key, "name": req.name, "scope": req.scope, "device_id": req.device_id,
            "note": "Store this key securely — it will not be shown again"}

@app.delete("/auth/api-keys/{key_hash}", tags=["Auth"])
async def delete_key(key_hash: str):
    await revoke_api_key(key_hash)
    return {"deleted": key_hash}


@app.get("/os/status", tags=["OS"])
async def os_status(
    principal: dict = Depends(require_scope("read")),
):
    cached = await get_cached_metrics()
    return cached or {**_last_metrics, "ps_available": PS_OK}

@app.get("/os/processes", tags=["OS"])
async def os_processes():
    if not PS_OK:
        return {"by_cpu": [], "by_mem": []}
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            if p.info["status"] == "zombie":
                continue
            procs.append({
                "pid":  p.info["pid"],
                "name": (p.info["name"] or "unknown")[:24],
                "cpu":  round(p.info["cpu_percent"]    or 0.0, 2),
                "mem":  round(p.info["memory_percent"] or 0.0, 2),
                "real": True,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {
        "by_cpu": sorted(procs, key=lambda x: x["cpu"], reverse=True)[:10],
        "by_mem": sorted(procs, key=lambda x: x["mem"], reverse=True)[:10],
    }


class FeatRequest(BaseModel):
    features: list[float] = Field(..., min_length=5, max_length=5)

@app.post("/ml/scores", tags=["ML"])
async def ml_scores(
    req: FeatRequest,
    principal: dict = Depends(require_scope("write")),
):
    feat = np.array(req.features, dtype=np.float32)
    m    = get_engine().score(feat)
    return {
        "if_score":       float(m.if_score),
        "vae_score":      float(m.vae_score),
        "lstm_score":     float(m.lstm_score),
        "ensemble_score": float(m.ensemble_score),
        "model_fitted":   m.model_fitted,
        "backend":        m.backend,
    }

@app.get("/ml/status", tags=["ML"])
async def ml_status():
    eng = get_engine()
    m = eng.metrics

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


class SaveVersionRequest(BaseModel):
    model_name:  str = "ensemble"
    description: str = ""
    tag:         str = ""

@app.post("/models/save", tags=["Versioning"])
async def save_version(
    req: SaveVersionRequest,
    principal: dict = Depends(require_scope("write")),
):
    engine = get_engine()
    m      = engine.metrics
    entry  = get_registry().save_version(
        req.model_name, engine.state_dict(),
        dict(ensemble_score=m.ensemble_score, steps_lstm=m.steps_lstm,
             steps_vae=m.steps_vae, lstm_loss=m.lstm_loss),
        req.description or f"Manual save · steps={m.steps_lstm + m.steps_vae}",
        req.tag,
    )
    return {"version_id": entry.version_id, "saved": True}

@app.get("/models/versions", tags=["Versioning"])
async def list_versions(model_name: Optional[str] = None):
    return get_registry().list_versions(model_name)

@app.post("/models/activate/{model_name}/{version_id}", tags=["Versioning"])
async def activate_version(model_name: str, version_id: str):
    state = get_registry().activate(model_name, version_id)
    if not state:
        raise HTTPException(404, "Version not found")
    get_engine().load_state_dict(state)
    return {"activated": version_id}

@app.post("/models/rollback/{model_name}", tags=["Versioning"])
async def rollback(model_name: str):
    result = get_registry().rollback(model_name)
    if not result:
        raise HTTPException(404, "No previous version")
    vid, state = result
    get_engine().load_state_dict(state)
    return {"rolled_back_to": vid}

@app.post("/models/rollback_best/{model_name}", tags=["Versioning"])
async def rollback_best(model_name: str):
    result = get_registry().rollback_to_best(model_name)
    if not result:
        raise HTTPException(404, "No best version recorded")
    vid, state = result
    get_engine().load_state_dict(state)
    return {"rolled_back_to_best": vid}

@app.delete("/models/{model_name}/{version_id}", tags=["Versioning"])
async def delete_version(model_name: str, version_id: str):
    if not get_registry().delete_version(model_name, version_id):
        raise HTTPException(404, "Version not found or is active")
    return {"deleted": version_id}

@app.get("/models/stats", tags=["Versioning"])
async def version_stats():
    return get_registry().stats()


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
async def add_webhook(req: WebhookRequest):
    wh = get_alert_engine().add_webhook(req.url, req.name, req.secret)
    return {"id": wh.id, "name": wh.name}

@app.delete("/alerts/webhooks/{wh_id}", tags=["Alerts"])
async def remove_webhook(wh_id: str):
    if not get_alert_engine().remove_webhook(wh_id):
        raise HTTPException(404, "Not found")
    return {"deleted": wh_id}

@app.post("/alerts/webhooks/{wh_id}/test", tags=["Alerts"])
async def test_webhook(wh_id: str):
    return {"success": await get_alert_engine().test_webhook(wh_id)}

@app.put("/alerts/email", tags=["Alerts"])
async def configure_email(req: EmailRequest):
    cfg = get_alert_engine().configure_email(**req.dict(), enabled=True)
    return {"configured": True, "to": cfg.to_addrs}

@app.get("/alerts/history", tags=["Alerts"])
async def alert_history(limit: int = 50, severity: Optional[str] = None):
    import re
    if severity and not re.match(r'^[A-Z_]+$', severity):
        raise HTTPException(status_code=422, detail="Invalid severity value")
    db_rows = await load_alerts(limit=limit, severity=severity)
    return db_rows if db_rows else get_alert_engine().get_history(limit, severity)

@app.get("/alerts/stats", tags=["Alerts"])
async def alert_stats():
    total = 0
    from backend.core.storage.redis_store import get_client
    c = await get_client()
    if c:
        try:
            total = int(await c.get("cvis:total_alerts_fired") or 0)
        except Exception:
            pass
    stats = get_alert_engine().get_stats()
    stats["redis_total"] = total
    return stats

@app.get("/alerts/rules", tags=["Alerts"])
async def list_rules():
    return [vars(r) for r in get_alert_engine().rules.values()]

@app.post("/alerts/rules", tags=["Alerts"])
async def add_rule(req: RuleRequest):
    import uuid as _u
    rule = AlertRule(rule_id=_u.uuid4().hex[:8], **req.dict())
    get_alert_engine().add_rule(rule)
    return vars(rule)

@app.delete("/alerts/rules/{rule_id}", tags=["Alerts"])
async def delete_rule(rule_id: str):
    if not get_alert_engine().delete_rule(rule_id):
        raise HTTPException(404, "Not found")
    return {"deleted": rule_id}

@app.patch("/alerts/rules/{rule_id}", tags=["Alerts"])
async def patch_rule(
    rule_id:   str,
    enabled:   Optional[bool]  = None,
    threshold: Optional[float] = None,
):
    kw: dict = {}
    if enabled   is not None: kw["enabled"]   = enabled
    if threshold is not None: kw["threshold"] = threshold
    rule = get_alert_engine().update_rule(rule_id, **kw)
    if not rule:
        raise HTTPException(404, "Not found")
    return vars(rule)


@app.get("/metrics", tags=["System"], response_class=PlainTextResponse, include_in_schema=False)
async def prometheus_metrics():
    m   = _last_metrics
    eng = get_engine().metrics
    ae  = get_alert_engine().get_stats()
    reg = get_registry().stats()

    def g(name, value, help_, type_="gauge"):
        v = round(float(value), 6) if value is not None else 0
        return f"# HELP {name} {help_}\n# TYPE {name} {type_}\n{name} {v}\n"

    return "".join([
        "# CVIS v9 metrics\n",
        g("cvis_cpu_percent",            m.get("cpu_percent",  0),  "Container CPU utilization %"),
        g("cvis_memory_percent",         m.get("memory",       0),  "Host memory %"),
        g("cvis_disk_percent",           m.get("disk_percent", 0),  "Disk space utilization %"),
        g("cvis_health_score",           m.get("health_score", 100),"System health 0-100"),
        g("cvis_anomaly_score",          m.get("anomaly_score",0),  "Ensemble anomaly 0-1"),
        g("cvis_ml_if_score",            eng.if_score,               "Isolation Forest score"),
        g("cvis_ml_vae_score",           eng.vae_score,              "VAE anomaly score"),
        g("cvis_ml_lstm_score",          eng.lstm_score,             "LSTM error score"),
        g("cvis_ml_ensemble_score",      eng.ensemble_score,         "Ensemble score"),
        g("cvis_ml_lstm_loss",           eng.lstm_loss,              "LSTM MSE loss"),
        g("cvis_ml_vae_recon_loss",      eng.vae_recon_loss,        "VAE recon loss"),
        g("cvis_ml_vae_kl_loss",         eng.vae_kl_loss,           "VAE KL divergence"),
        g("cvis_ml_steps_lstm",          eng.steps_lstm,             "LSTM steps", "counter"),
        g("cvis_ml_steps_vae",           eng.steps_vae,              "VAE steps",  "counter"),
        g("cvis_ml_model_fitted",        int(eng.model_fitted),      "1 if IF fitted"),
        g("cvis_ml_feature_buffer_size", len(feature_buffer),        "Feature buffer size"),
        g("cvis_alerts_critical_total",  ae.get("critical", 0),      "Critical alerts", "counter"),
        g("cvis_alerts_warning_total",   ae.get("warning",  0),      "Warning alerts",  "counter"),
        g("cvis_alerts_info_total",      ae.get("info",     0),      "Info alerts",     "counter"),
        g("cvis_alerts_rules_active",    ae.get("rules_active", 0),  "Active rules"),
        g("cvis_model_versions_total",
          sum(v.get("total_versions", 0) for v in reg.values()),      "Saved model versions"),
    ])


@app.get("/health", tags=["System"])
async def health():
    e  = get_engine()
    ex = explain_and_act(_last_metrics)
    return {
        "status":       "ok",
        "model_fitted": e.metrics.model_fitted,
        "buffer":       len(feature_buffer),
        "steps_lstm":   e.metrics.steps_lstm,
        "steps_vae":    e.metrics.steps_vae,
        "ps":           PS_OK,
        "redis":        await redis_info(),
        "db":           await db_info(),
        "versions":     get_registry().stats(),
        "alert_stats":  get_alert_engine().get_stats(),
        "reason":       ex["reason"],
        "severity":     ex["severity"],
        "actions":      ex["actions"],
    }

@app.get("/health/full", tags=["System"])
async def health_full():
    base = await health()
    base["health_credit_score"] = _last_metrics.get("health_credit_score")
    base["health_grade"]        = _last_metrics.get("health_grade")
    base["active_prediction"]   = _last_metrics.get("active_prediction")
    return base

@app.get("/db/snapshots", tags=["System"])
async def get_snapshots(hours: float = 1.0):
    return await load_snapshots(hours=min(hours, 24.0))

@app.get("/db/events", tags=["System"])
async def get_events(limit: int = 60):
    return await load_events(limit=limit) or []


@app.get("/debug/cpu", tags=["System"])
async def debug_cpu(window_s: float = 2.0):
    """
    Synchronized CPU diagnostic. Takes ONE raw cgroup usage delta over
    `window_s` seconds (independent of the collector's rolling state)
    and reports it in both conventions at once:

      - quota_normalized_percent        (CVIS convention: 100% = full quota)
      - equivalent_docker_style_percent (docker stats convention: 100% = 1 core)

    Run this at the same time as `docker stats <container> --no-stream`
    (on the HOST, targeting the actual synapse-backend container — not
    `top`/`htop` run inside the container, which is not cgroup-aware and
    will show host-wide usage across every process on the box).
    equivalent_docker_style_percent should closely match Docker's own
    number if both are reading the same container's cgroup. If they
    don't match, Docker is looking at a different scope than this
    container's quota; if quota_normalized_percent doesn't match a
    manual read of the cgroup files, that's a real bug in CVIS.
    """
    quota = _cgroup_cpu_quota()
    if quota is None:
        return {
            "quota_detected": False,
            "note": (
                "No cgroup CPU quota found (unlimited container, or cgroup "
                "files unreadable) — CVIS is falling back to host-wide "
                "psutil accounting, not quota-normalized cgroup accounting."
            ),
            "psutil_host_cpu_percent": (
                float(psutil.cpu_percent(interval=window_s)) if PS_OK else None
            ),
        }

    cpus, read_usage_ns = quota
    before = read_usage_ns()
    t0 = time.monotonic()
    await asyncio.sleep(window_s)
    after = read_usage_ns()
    elapsed = max(0.1, time.monotonic() - t0)

    used_seconds = (after - before) / 1_000_000_000
    quota_pct   = max(0.0, min(100.0, (used_seconds / (elapsed * cpus)) * 100.0))
    docker_pct  = round(used_seconds / elapsed * 100, 2)

    return {
        "quota_detected":                True,
        "quota_cpus":                    cpus,
        "sample_window_s":               round(elapsed, 3),
        "cpu_time_consumed_s":           round(used_seconds, 3),
        "quota_normalized_percent":      round(quota_pct, 2),
        "equivalent_docker_style_percent": docker_pct,
        "note": (
            "Compare equivalent_docker_style_percent (not "
            "quota_normalized_percent) against `docker stats` output "
            "captured at the same time — they use the same 100%=1-core "
            "convention. quota_normalized_percent is what CVIS displays "
            "and alerts on (100% = full quota)."
        ),
    }


@app.get("/cognitive/health-score", tags=["Cognitive"])
async def cognitive_health_score():
    if not COGNITIVE_OK:
        return {"score": None, "error": "Cognitive layer not available"}
    return get_dna_engine().get_health_score(dict(_last_metrics))

@app.get("/cognitive/pipeline", tags=["Cognitive"])
async def cognitive_pipeline():
    try:
        from backend.intelligence_pipeline import run_intelligence_pipeline
        return run_intelligence_pipeline(
            allow_execution=False,
            live_metrics=dict(_last_metrics),
        )
    except Exception as e:
        return {
            "error": "Intelligence pipeline unavailable",
            "detail": str(e),
        }

@app.get("/cognitive/forecast", tags=["Cognitive"])
async def cognitive_forecast():
    if not COGNITIVE_OK:
        return {"error": "Cognitive layer not available"}
    return get_forecaster().get_plain_timeline(dict(_last_metrics))

@app.get("/cognitive/predictions", tags=["Cognitive"])
async def cognitive_predictions():
    if not COGNITIVE_OK:
        return []
    dna     = get_dna_engine()
    preds   = dna.get_active_predictions()
    metrics = dict(_last_metrics)
    return [
        {
            "id":               p.prediction_id,
            "type":             p.failure_type,
            "eta_minutes":      round(p.minutes_remaining, 1),
            "confidence":       round(p.confidence * 100, 0),
            "confidence_label": (
                "Very high" if p.confidence >= 0.90 else
                "High"      if p.confidence >= 0.75 else
                "Moderate"  if p.confidence >= 0.60 else "Low"
            ),
            "message":          p.plain_message,
            "action":           p.plain_action,
            "severity":         p.severity,
            "acknowledged":     p.acknowledged,
            "trustworthy": dna.is_prediction_trustworthy(p.pattern_id),
            "explanation":      dna.explain_prediction(p, metrics),
        }
        for p in preds
    ]

@app.get("/cognitive/debug/matcher", tags=["Cognitive"])
async def cognitive_debug_matcher():
    if not COGNITIVE_OK:
        return {"error": "Cognitive layer not available"}

    dna = get_dna_engine()
    buffer = list(dna._metric_buffer)

    result = {
        "buffer_length": len(buffer),
        "baseline_keys": list(dna._baseline_stats.keys()),
        "patterns": {},
    }

    for pid, pattern in dna._patterns.items():
        try:
            confidence, eta = dna._match_pattern(pattern, buffer)
            debug = {
                "pattern_id": pid,
                "seen_count": pattern.seen_count,
                "detection_accuracy": pattern.detection_accuracy,
                "pattern_confidence": pattern.confidence,
                "match_confidence": round(float(confidence), 4),
                "match_percent": round(float(confidence) * 100, 2),
                "eta_minutes": round(float(eta), 2),
                "passes_sample_gate": pattern.seen_count >= dna.MIN_SAMPLES,
                "passes_confidence_gate": confidence >= dna.MIN_CONFIDENCE,
            }

            # Detailed matcher diagnostics.
            try:
                recent = buffer[-min(30, len(buffer)):]
                current_z = [
                    dna._to_z_scores(snapshot).tolist()
                    for snapshot in recent
                ]

                signatures = [
                    list(sig)
                    for sig in pattern.signature_steps
                ]

                step_debug = []
                start_pos = 0

                for step_index, sig in enumerate(signatures):
                    if start_pos >= len(current_z):
                        break

                    candidates = current_z[start_pos:]

                    distances = [
                        float(
                            np.linalg.norm(
                                np.asarray(z, dtype=np.float32)
                                - np.asarray(sig, dtype=np.float32)
                            )
                        )
                        for z in candidates
                    ]

                    if not distances:
                        break

                    local_idx = int(np.argmin(distances))
                    distance = distances[local_idx]
                    similarity = 1.0 / (1.0 + distance)
                    actual_pos = start_pos + local_idx

                    step_debug.append({
                        "step": step_index + 1,
                        "signature": sig,
                        "matched_buffer_position": actual_pos,
                        "distance": round(distance, 4),
                        "similarity": round(similarity, 4),
                    })

                    start_pos = actual_pos + 1

                debug["latest_z_scores"] = (
                    current_z[-1] if current_z else []
                )
                debug["matched_steps"] = step_debug
                debug["steps_matched"] = len(step_debug)
                debug["steps_total"] = len(signatures)

            except Exception as debug_error:
                debug["diagnostic_error"] = repr(debug_error)

            result["patterns"][pattern.failure_type] = debug
        except Exception as e:
            result["patterns"][pattern.failure_type] = {
                "error": repr(e)
            }

    return result


@app.post("/cognitive/predictions/{pred_id}/acknowledge", tags=["Cognitive"])
async def acknowledge_prediction(pred_id: str):
    if not COGNITIVE_OK:
        raise HTTPException(
            status_code=503,
            detail="Cognitive layer unavailable",
        )

    from backend.core.storage.db import get_db

    dna = get_dna_engine()
    pred = dna._active_predictions.get(pred_id)

    if pred is None:
        raise HTTPException(
            status_code=404,
            detail="Prediction not found",
        )

    dna.acknowledge_prediction(pred_id, user_acted=True)

    db = await get_db()

    if not db:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )

    try:
        await db.execute(
            "UPDATE predictions SET acknowledged = 1 WHERE prediction_id = ?",
            (pred_id,),
        )
        await db.commit()
    except Exception as e:
        log.error(
            "Failed to persist acknowledgement for %s: %s",
            pred_id,
            e,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to persist acknowledgement",
        )

    return {
        "acknowledged": pred_id,
        "persisted": True,
    }

@app.post("/cognitive/predictions/{pred_id}/resolve", tags=["Cognitive"])
async def resolve_prediction(pred_id: str, was_correct: bool):
    if not COGNITIVE_OK:
        raise HTTPException(status_code=503, detail="Cognitive layer unavailable")

    from backend.core.storage.db import (
        get_db,
        load_active_predictions,
        save_prediction,
        save_prediction_outcome,
    )

    dna = get_dna_engine()
    pred = dna._active_predictions.get(pred_id)

    # First enforce durable immutability. This protects predictions that
    # survived a backend restart and are no longer in Failure-DNA memory.
    db = await get_db()
    if db:
        try:
            async with db.execute(
                """
                SELECT outcome, false_positive, false_negative, prevented
                FROM prediction_outcomes
                WHERE prediction_id = ?
                """,
                (pred_id,),
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                return {
                    "resolved": pred_id,
                    "was_correct": existing["outcome"] == "correct",
                    "found": True,
                    "already_resolved": True,
                    "persisted_only": pred is None,
                }
        except Exception as e:
            log.error("resolve_prediction outcome lookup failed: %s", e)

    # Predictions may survive a backend restart in SQLite without being
    # present in the in-memory Failure-DNA registry.
    if pred is None:
        persisted = await load_active_predictions()
        row = next(
            (r for r in persisted if r.get("prediction_id") == pred_id),
            None,
        )

        if row is None:
            return {
                "resolved": pred_id,
                "was_correct": was_correct,
                "found": False,
            }

        await save_prediction({
            "prediction_id": row.get("prediction_id"),
            "device_id": row.get("device_id"),
            "failure_type": row.get("failure_type"),
            "created_at": row.get("created_at"),
            "expected_at": row.get("expected_at"),
            "confidence": row.get("confidence"),
            "risk_score": row.get("risk_score"),
            "lead_time_seconds": row.get("lead_time_seconds"),
            "status": "resolved",
            "evidence": row.get("evidence"),
            "model_version": row.get("model_version"),
        })

        await save_prediction_outcome({
            "prediction_id": pred_id,
            "outcome": "correct" if was_correct else "incorrect",
            "lead_time_seconds": row.get("lead_time_seconds"),
            "false_positive": not was_correct,
            "false_negative": False,
            "prevented": False,
        })

        return {
            "resolved": pred_id,
            "was_correct": was_correct,
            "found": True,
            "persisted_only": True,
        }

    # In-memory prediction has already been resolved.
    if getattr(pred, "resolved", False):
        return {
            "resolved": pred_id,
            "was_correct": bool(pred.was_correct),
            "found": True,
            "already_resolved": True,
        }

    dna.resolve_prediction(pred_id, was_correct)

    await save_prediction({
        "prediction_id": pred_id,
        "device_id": getattr(pred, "device_id", None),
        "failure_type": (
            getattr(pred, "failure_type", None)
            or getattr(pred, "pattern_id", None)
            or "unknown"
        ),
        "created_at": getattr(pred, "created_at", None) or __import__("time").time(),
        "expected_at": None,
        "confidence": getattr(pred, "confidence", None),
        "risk_score": getattr(pred, "confidence", None),
        "lead_time_seconds": getattr(pred, "minutes_remaining", 0) * 60,
        "status": "resolved",
        "evidence": {
            "pattern_id": getattr(pred, "pattern_id", None),
            "message": getattr(pred, "plain_message", None),
        },
        "model_version": "failure_dna",
    })

    await save_prediction_outcome({
        "prediction_id": pred_id,
        "outcome": "correct" if was_correct else "incorrect",
        "lead_time_seconds": getattr(pred, "minutes_remaining", 0) * 60,
        "false_positive": not was_correct,
        "false_negative": False,
        "prevented": False,
    })

    return {
        "resolved": pred_id,
        "was_correct": was_correct,
        "found": True,
    }


@app.get("/cognitive/dna", tags=["Cognitive"])
async def cognitive_dna():
    if not COGNITIVE_OK:
        return {"patterns": 0}
    dna     = get_dna_engine()
    summary = dna.get_dna_summary()
    metrics = dict(_last_metrics)
    for pattern in summary.get("pattern_list", []):
        try:
            pattern["explanation"] = dna.explain(metrics, pattern["type"])
        except Exception:
            pattern["explanation"] = {}
    return summary

@app.get("/cognitive/premortem", tags=["Cognitive"])
async def cognitive_premortem():
    dna    = get_dna_engine().get_dna_summary()
    result = get_premortem_engine().run(dna_summary=dna)

    def threat_to_dict(t):
        return {
            "threat_id":      t.threat_id,
            "failure_type":   t.failure_type,
            "probability":    round(t.probability * 100, 1),
            "days_until":     round(t.days_until, 1) if t.days_until else None,
            "confidence":     t.confidence,
            "headline":       t.headline,
            "evidence":       t.evidence,
            "recommendation": t.recommendation,
            "data_points":    t.data_points,
            "trend_per_day":  round(t.trend_per_day, 3),
        }

    return {
        "generated_at":   result.generated_at,
        "horizon_days":   result.horizon_days,
        "safe":           result.safe,
        "summary":        result.plain_summary,
        "data_quality":   result.data_quality,
        "snapshot_count": result.snapshot_count,
        "threat_count":   len(result.threats),
        "threats":        [threat_to_dict(t) for t in result.threats],
        "top_threat":     threat_to_dict(result.top_threat) if result.top_threat else None,
    }

@app.get("/cognitive/remediation/status", tags=["Actions"])
async def remediation_status():
    return get_ar_engine().get_status()

@app.get("/cognitive/remediation/log", tags=["Actions"])
async def remediation_log(limit: int = 20):
    return get_ar_engine().get_audit_log(limit=limit)

@app.get("/cognitive/blackbox", tags=["Cognitive"])
async def cognitive_blackbox():
    if not COGNITIVE_OK:
        return {"recording": False}
    bb = get_black_box()
    return {"status": bb.get_status(), "recent_frames": bb.get_recent_frames(minutes=5)}

@app.post("/cognitive/incident", tags=["Cognitive"])
async def mark_incident(incident_type: str, description: str = ""):
    if not COGNITIVE_OK:
        return {"error": "Cognitive layer not available"}
    bb          = get_black_box()
    dna         = get_dna_engine()
    incident_id = bb.mark_incident(incident_type, description or incident_type)
    dna.record_failure(incident_type, description or incident_type)
    return {"incident_id": incident_id, "recorded": True}

@app.get("/cognitive/incidents", tags=["Cognitive"])
async def list_incidents():
    if not COGNITIVE_OK:
        return []
    return get_black_box().get_incidents()

@app.get("/cognitive/incidents/{incident_id}", tags=["Cognitive"])
async def get_incident(incident_id: str):
    if not COGNITIVE_OK:
        return {"error": "not available"}
    incident = get_black_box().get_incident(incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    postmortem = get_dna_engine().generate_postmortem(incident_id)
    return {**incident, "postmortem": postmortem}

@app.get("/cognitive/postmortem/{event_id}", tags=["Cognitive"])
async def get_postmortem(event_id: str):
    if not COGNITIVE_OK:
        return {"error": "not available"}
    bb       = get_black_box()
    incident = bb.get_incident(event_id)
    if incident:
        tl_data = bb.get_timeline_for_incident(event_id)
        return get_postmortem_builder().build(incident, tl_data.get("timeline", []))
    return get_dna_engine().generate_postmortem(event_id)

@app.get("/cognitive/notifications", tags=["Cognitive"])
async def notification_history():
    if not COGNITIVE_OK:
        return []
    return get_notifier().get_history()

@app.post("/cognitive/notifications/config", tags=["Cognitive"])
async def configure_notifications(enabled: bool = True, min_severity: str = "MEDIUM"):
    if COGNITIVE_OK:
        n = get_notifier()
        n.set_enabled(enabled)
        n.set_min_severity(min_severity)
    return {"enabled": enabled, "min_severity": min_severity}

@app.get("/cognitive/status", tags=["Cognitive"])
async def cognitive_status():
    if not COGNITIVE_OK:
        return {"available": False}
    m   = dict(_last_metrics)
    dna = get_dna_engine()
    bb  = get_black_box()
    return {
        "available":          True,
        "health_score":       dna.get_health_score(m),
        "dna":                dna.get_dna_summary(),
        "black_box":          bb.get_status(),
        "notifications":      get_notifier().get_status(),
        "active_predictions": len(dna.get_active_predictions()),
    }


class DeviceRegistrationPayload(BaseModel):
    device_id: str
    device_name: str
    os: str
    os_version: str = ""
    hostname: str = ""
    capabilities: list[str] = []


@app.post("/devices/register", tags=["Devices"])
async def register_device(
    payload: DeviceRegistrationPayload,
    principal: dict = Depends(require_scope("admin")),
):
    device_id = payload.device_id.strip()

    if not device_id:
        raise HTTPException(400, "device_id is required")

    if len(device_id) > 128:
        raise HTTPException(400, "device_id is too long")

    if not payload.device_name.strip():
        raise HTTPException(400, "device_name is required")

    if not payload.os.strip():
        raise HTTPException(400, "os is required")

    redis = await get_redis()

    if redis is None:
        raise HTTPException(
            503,
            "Device registration persistence unavailable",
        )

    registry_key = f"device:registry:{device_id}"

    try:
        if await redis.exists(registry_key):
            raise HTTPException(409, "Device is already registered")
    except HTTPException:
        raise
    except Exception as exc:
        log.exception(
            "Failed to check registration for device %s: %s",
            device_id,
            exc,
        )
        raise HTTPException(
            503,
            "Device registration persistence unavailable",
        )

    registration = {
        "device_id": device_id,
        "device_name": payload.device_name.strip(),
        "os": payload.os.strip(),
        "os_version": payload.os_version.strip(),
        "hostname": payload.hostname.strip(),
        "capabilities": list(dict.fromkeys(payload.capabilities)),
        "registered_at": time.time(),
        "status": "registered",
    }

    try:
        await redis.hset(
                registry_key,
                mapping={
                    "device_id": registration["device_id"],
                    "device_name": registration["device_name"],
                    "os": registration["os"],
                    "os_version": registration["os_version"],
                    "hostname": registration["hostname"],
                    "capabilities": _json.dumps(registration["capabilities"]),
                    "registered_at": str(registration["registered_at"]),
                    "status": registration["status"],
                },
        )
    except Exception as exc:
        log.exception(
            "Failed to persist registration for device %s: %s",
            device_id,
            exc,
        )
        raise HTTPException(
            503,
            "Device registration persistence unavailable",
        )

    # Device identity is supplied by the agent and becomes the binding
    # identity for its telemetry credential.
    from backend.core.auth.auth import create_api_key

    try:
        api_key = await create_api_key(
            name=f"device:{device_id}",
            scope="write",
            device_id=device_id,
        )
    except Exception as exc:
        # Do not leave a registry entry behind if credential issuance fails.
        try:
            await redis.delete(registry_key)
        except Exception:
            log.exception(
                "Failed to roll back registration for device %s",
                device_id,
            )
        raise HTTPException(
            503,
            "Device credential issuance failed",
        ) from exc

    _devices[device_id] = {
        **registration,
        "last_seen": None,
        "metrics": {},
        "processes": [],
    }

    return {
        "registered": True,
        "device_id": device_id,
        "credential": api_key,
        "credential_scope": "write",
        "credential_device_id": device_id,
    }


class DeviceCommandCreatePayload(BaseModel):
    command_type: str
    payload: dict = {}
    ttl_s: float = 300.0


class DeviceCommandTransitionPayload(BaseModel):
    status: str
    result: dict | None = None


@app.post("/devices/{device_id}/commands", tags=["Devices"])
async def create_device_command(
    device_id: str,
    payload: DeviceCommandCreatePayload,
    principal: dict = Depends(require_scope("admin")),
):
    """Create and durably enqueue an allowlisted command for a device."""
    if device_id not in _devices:
        raise HTTPException(404, "Device is not registered")

    redis = await get_redis()
    if redis is None:
        raise HTTPException(503, "Command persistence unavailable")

    from backend.core.devices.command_service import create_command

    requested_by = principal.get("sub") or principal.get("name") or "admin"

    try:
        return await create_command(
            redis,
            device_id=device_id,
            command_type=payload.command_type,
            requested_by=requested_by,
            payload=payload.payload,
            ttl_s=payload.ttl_s,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.exception(
            "Failed to create command for device %s: %s",
            device_id,
            exc,
        )
        raise HTTPException(503, "Command creation failed") from exc



@app.get("/devices/{device_id}/commands/pending", tags=["Devices"])
async def poll_device_commands(
    device_id: str,
    principal: dict = Depends(require_scope("write")),
):
    """Atomically claim and return the next pending command for the authenticated device."""
    credential_device_id = principal.get("device_id")

    if not credential_device_id:
        raise HTTPException(
            403,
            "Device-bound credential required for command polling",
        )

    if credential_device_id != device_id:
        raise HTTPException(
            403,
            "Credential is not authorized for this device",
        )

    redis = await get_redis()
    if redis is None:
        raise HTTPException(503, "Command persistence unavailable")

    from backend.core.devices.command_service import claim_next_command

    try:
        command = await claim_next_command(
            redis,
            device_id,
        )
    except Exception as exc:
        log.exception(
            "Failed to claim command for device %s: %s",
            device_id,
            exc,
        )
        raise HTTPException(503, "Command polling failed") from exc

    if command is None:
        return {"commands": []}

    return {"commands": [command]}


@app.get("/devices/{device_id}/commands/{command_id}", tags=["Devices"])
async def get_device_command(
    device_id: str,
    command_id: str,
    principal: dict = Depends(require_scope("read")),
):
    """Return command state, enforcing device binding for device credentials."""
    redis = await get_redis()
    if redis is None:
        raise HTTPException(503, "Command persistence unavailable")

    from backend.core.devices.command_service import get_command

    command = await get_command(redis, command_id)

    if command is None:
        raise HTTPException(404, "Command not found")

    if command["device_id"] != device_id:
        raise HTTPException(404, "Command not found")

    credential_device_id = principal.get("device_id")
    if credential_device_id and credential_device_id != device_id:
        raise HTTPException(
            403,
            "Credential is not authorized for this device",
        )

    return command


@app.post(
    "/devices/{device_id}/commands/{command_id}/transition",
    tags=["Devices"],
)
async def transition_device_command(
    device_id: str,
    command_id: str,
    payload: DeviceCommandTransitionPayload,
    principal: dict = Depends(require_scope("write")),
):
    """Advance a command through its guarded lifecycle."""
    credential_device_id = principal.get("device_id")

    if not credential_device_id:
        raise HTTPException(
            403,
            "Device-bound credential required for command transition",
        )

    if credential_device_id != device_id:
        raise HTTPException(
            403,
            "Credential is not authorized for this device",
        )

    redis = await get_redis()
    if redis is None:
        raise HTTPException(503, "Command persistence unavailable")

    from backend.core.devices.command_service import (
        get_command,
        transition_command,
    )

    command = await get_command(redis, command_id)

    if command is None or command["device_id"] != device_id:
        raise HTTPException(404, "Command not found")

    log.info(
        "COMMAND TRANSITION: device=%s command=%s status=%s result=%r",
        device_id,
        command_id,
        payload.status,
        payload.result,
    )

    try:
        transitioned = await transition_command(
            redis,
            command_id,
            payload.status,
            payload.result,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not transitioned:
        raise HTTPException(
            409,
            "Command transition is invalid for its current state",
        )

    return await get_command(redis, command_id)


class DeviceMetricsPayload(BaseModel):
    device_id:   str
    device_name: str
    os:          str
    os_version:  str  = ""
    hostname:    str  = ""
    timestamp:   float
    metrics:     dict
    processes:   list = []

class DeviceHeartbeatPayload(BaseModel):
    device_id: str
    timestamp: float


HEARTBEAT_MAX_AGE_S = 120.0
HEARTBEAT_MAX_FUTURE_SKEW_S = 30.0
HEARTBEAT_WATERMARK_TTL_S = int(
    HEARTBEAT_MAX_AGE_S * 2 + HEARTBEAT_MAX_FUTURE_SKEW_S
)
_last_heartbeat_timestamp: dict[str, float] = {}


async def _accept_heartbeat_timestamp(device_id: str, timestamp: float) -> bool:
    """Atomically accept a strictly newer heartbeat timestamp."""
    redis = await get_redis()

    if redis is not None:
        key = f"heartbeat:last_timestamp:{device_id}"
        script = """
        local current = redis.call('GET', KEYS[1])
        if current and tonumber(ARGV[1]) <= tonumber(current) then
            return 0
        end
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
        return 1
        """
        accepted = await redis.eval(
            script,
            1,
            key,
            str(timestamp),
            str(HEARTBEAT_WATERMARK_TTL_S),
        )
        return bool(accepted)

    # Local fallback when Redis is temporarily unavailable.
    previous = _last_heartbeat_timestamp.get(device_id)
    if previous is not None and timestamp <= previous:
        return False

    _last_heartbeat_timestamp[device_id] = timestamp
    return True


@app.post("/devices/{device_id}/heartbeat", tags=["Devices"])
async def receive_device_heartbeat(
    device_id: str,
    payload: DeviceHeartbeatPayload,
    principal: dict = Depends(require_scope("write")),
):
    credential_device_id = principal.get("device_id")

    if not credential_device_id:
        raise HTTPException(
            403,
            "Device-bound credential required for heartbeat",
        )

    if credential_device_id != device_id:
        raise HTTPException(
            403,
            "Credential is not authorized for this device",
        )

    if payload.device_id != device_id:
        raise HTTPException(
            400,
            "Payload device_id does not match URL device_id",
        )

    now = time.time()
    age = now - payload.timestamp

    if age > HEARTBEAT_MAX_AGE_S:
        raise HTTPException(409, "Heartbeat timestamp is stale")

    if age < -HEARTBEAT_MAX_FUTURE_SKEW_S:
        raise HTTPException(
            409,
            "Heartbeat timestamp is too far in the future",
        )

    if not await _accept_heartbeat_timestamp(
        device_id,
        payload.timestamp,
    ):
        raise HTTPException(
            409,
            "Heartbeat timestamp is out of order or replayed",
        )

    device = _devices.get(device_id)

    if device is None:
        raise HTTPException(404, "Device is not registered")

    device["last_seen"] = now
    device["status"] = "online"

    redis = await get_redis()

    if redis is not None:
        try:
            await redis.hset(
                f"device:registry:{device_id}",
                mapping={
                    "last_seen": str(now),
                },
            )
        except Exception:
            log.exception(
                "Failed to persist heartbeat for device %s",
                device_id,
            )

    return {
        "status": "online",
        "device_id": device_id,
        "timestamp": payload.timestamp,
        "last_seen": now,
    }


@app.post("/devices/{device_id}/metrics", tags=["Devices"])
async def receive_device_metrics(
    device_id: str,
    payload: DeviceMetricsPayload,
    principal: dict = Depends(require_scope("write")),
):
    credential_device_id = principal.get("device_id")
    if not credential_device_id:
        raise HTTPException(403, "Device-bound credential required for telemetry")
    if credential_device_id != device_id:
        raise HTTPException(403, "Credential is not authorized for this device")
    if payload.device_id != device_id:
        raise HTTPException(400, "Payload device_id does not match URL device_id")

    now = time.time()
    age = now - payload.timestamp

    if age > TELEMETRY_MAX_AGE_S:
        raise HTTPException(409, "Telemetry timestamp is stale")

    if age < -TELEMETRY_MAX_FUTURE_SKEW_S:
        raise HTTPException(409, "Telemetry timestamp is too far in the future")

    if not await _accept_telemetry_timestamp(device_id, payload.timestamp):
        raise HTTPException(409, "Telemetry timestamp is out of order or replayed")

    # Store the complete remote-device telemetry payload.
    device = {
        **payload.dict(),
        "last_seen": time.time(),
        "status": "online",
    }

    # Run inference against the shared active model while keeping
    # temporal/EMA state isolated to this device.
    try:
        ml = get_remote_inference().score(
            device_id,
            payload.metrics,
        )
        device["ml"] = ml

        # Evaluate this remote device independently from local backend alerts.
        alert_metrics = {
            **payload.metrics,
            "anomaly_score": ml.get("ensemble_score", 0.0),
        }
        await get_alert_engine().evaluate_device(
            device_id=device_id,
            device_name=payload.device_name,
            metrics=alert_metrics,
        )
    except Exception as exc:
        # Telemetry ingestion must remain available even if ML inference
        # encounters a bad payload/model state.
        log.exception(
            "Remote ML inference failed for device %s: %s",
            device_id,
            exc,
        )
        device["ml"] = {
            "available": False,
            "error": str(exc),
        }

    _devices[device_id] = device

    # Keep the persistent node snapshot synchronized with the live
    # /devices telemetry so the intelligence pipeline sees remote devices.
    try:
        _persist_device_node(payload)
    except Exception as exc:
        log.exception(
            "Failed to persist node snapshot for device %s: %s",
            device_id,
            exc,
        )

    return {
        "accepted": True,
        "device_id": device_id,
        "ml": device["ml"],
    }

@app.get("/devices", tags=["Devices"])
async def list_devices():
    now = time.time()
    return [
        {
            "device_id":   did,
            "device_name": d.get("device_name", "unknown"),
            "os":          d.get("os",           "unknown"),
            "hostname":    d.get("hostname",      ""),
            "status":      "online" if now - (d.get("last_seen") or 0) < 30 else "offline",
            "last_seen_s": (round(now - d["last_seen"], 1) if d.get("last_seen") is not None else None),
            "metrics":     d.get("metrics",   {}),
            "processes":   d.get("processes", []),
        }
        for did, d in _devices.items()
    ]

@app.get("/devices/{device_id}", tags=["Devices"])
async def get_device(device_id: str):
    if device_id not in _devices:
        raise HTTPException(404, "Device not found")
    dev = _devices[device_id]
    age = time.time() - dev.get("last_seen", 0)
    return {**dev, "status": "online" if age < 30 else "offline", "last_seen_s": round(age, 1)}


try:
    from backend.core.actions.action_executor import (
        execute_action as _execute_action,
        get_available_actions as _get_actions,
    )
    ACTIONS_OK = True
except Exception as _ae:
    log.warning("Action executor unavailable: %s", _ae)
    ACTIONS_OK = False

@app.get("/actions/available", tags=["Actions"])
async def list_available_actions(failure_type: Optional[str] = None):
    if not ACTIONS_OK:
        return []
    return _get_actions(failure_type)

@app.post("/actions/execute", tags=["Actions"], dependencies=[Depends(require_scope("write"))])
async def run_action(action_id: str):
    if not ACTIONS_OK:
        return {"success": False, "error": "Action executor not available"}
    result = await asyncio.get_event_loop().run_in_executor(None, _execute_action, action_id)
    return result


@app.get("/report/weekly", tags=["Reports"])
async def weekly_health_report():
    from datetime import datetime
    m     = dict(_last_metrics)
    score = m.get("health_credit_score") or 0
    if score == 0 and COGNITIVE_OK:
        try:
            score = get_dna_engine().get_health_score(m).get("score", 0)
        except Exception:
            pass

    severity = m.get("severity", "UNKNOWN")
    reason   = m.get("reason",   "")

    def _grade(s):
        if s >= 800: return "Excellent"
        if s >= 600: return "Good"
        if s >= 400: return "Fair"
        if s >= 200: return "Poor"
        return "Critical"

    bar = "X" * int(score / 50) + "." * (20 - int(score / 50))
    dna_section = ""
    if COGNITIVE_OK:
        try:
            s = get_dna_engine().get_dna_summary()
            dna_section = f"  Failure DNA:\n  - {s.get('patterns',0)} patterns\n  - {s.get('prevented',0)} prevented"
        except Exception:
            pass

    fc_section = ""
    if COGNITIVE_OK:
        try:
            fc = get_forecaster().forecast(m)
            if fc:
                fc_section = f"  Next 60 Min: {getattr(fc,'plain_summary',getattr(fc,'summary','Analyzing...'))}"
        except Exception:
            pass

    rec = (
        "Health low — check disk and processes." if score < 400 else
        "Health fair — monitor memory."          if score < 700 else
        "System healthy — no action needed."
    )
    week = datetime.now().strftime("%B %d, %Y")
    report = (
        f"{'='*56}\n  CVIS Weekly Report - {week}\n{'='*56}\n\n"
        f"  Health: {score}/1000 ({_grade(score)})\n  [{bar}]\n"
        f"  Status: {severity} - {reason}\n\n{dna_section}\n\n{fc_section}\n\n"
        f"  Recommendation: {rec}\n  Dashboard: http://localhost\n{'='*56}"
    )
    return {"report": report, "generated_at": time.time(), "format": "plain_text"}


# ── Settings endpoints ────────────────────────────────────────────────────────

from backend.core.settings import settings_manager as _sm

@app.get("/settings", tags=["Settings"])
async def get_settings():
    return _sm.get_all()

@app.post("/settings", tags=["Settings"])
async def save_settings(request: Request):
    body = await request.json()
    result = _sm.save(body)
    # Apply thresholds to live alert engine immediately
    try:
        _sm.apply_alert_thresholds(get_alert_engine())
    except Exception:
        pass
    return result

@app.post("/settings/reset", tags=["Settings"])
async def reset_settings():
    return _sm.reset()

@app.post("/settings/test-email", tags=["Settings"])
async def settings_test_email():
    try:
        from backend.core.reports.weekly_report import send_alert_email
        send_alert_email(
            severity="INFO",
            message="CVIS settings test — email delivery confirmed.",
            reason="Manual test from Settings panel",
            actions=["No action required"],
            metrics={
                "cpu_percent":  _last_metrics.get("cpu_percent",  0),
                "memory":       _last_metrics.get("memory",       0),
                "health_score": _last_metrics.get("health_score", 100),
            },
        )
        return {"success": True, "message": "Test email sent — check your inbox."}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/settings/send-report", tags=["Settings"])
async def settings_send_report():
    try:
        from backend.core.reports.weekly_report import send_weekly_report_email
        to = _sm.get("alert_email") or os.environ.get("ALERT_EMAIL", "")
        if not to:
            return {"success": False, "message": "No alert email configured."}
        send_weekly_report_email(to)
        return {"success": True, "message": f"Weekly report sent to {to}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Silent Degradation endpoint ───────────────────────────────────────────────

@app.get("/cognitive/degradation", tags=["Cognitive"])
async def cognitive_degradation():
    """
    Returns long-term chronic drift analysis.
    Requires ~7 days of data for meaningful results.
    """
    try:
        from backend.core.cognitive.degradation import get_degradation_detector
        return get_degradation_detector().get_report_dict()
    except Exception as e:
        return {
            "is_degrading": False,
            "summary": "Degradation detector initialising — check back after 7 days of data.",
            "has_data": False,
            "days_of_data": 0,
            "metrics": [],
            "error": str(e),
        }


# ── Stress Test endpoints ─────────────────────────────────────────────────────

@app.get("/stress/scenarios", tags=["Demo"])
async def list_stress_scenarios():
    """List available stress test scenarios for demo."""
    try:
        from backend.core.demo.stress_engine import get_scenarios
        return get_scenarios()
    except Exception as e:
        return []

@app.post("/stress/start/{scenario_id}", tags=["Demo"])
async def start_stress(scenario_id: str):
    """Start a stress scenario to trigger CVIS predictions."""
    try:
        from backend.core.demo.stress_engine import start_scenario
        return start_scenario(scenario_id)
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/stress/stop/{scenario_id}", tags=["Demo"])
async def stop_stress(scenario_id: str):
    """Stop a running stress scenario."""
    try:
        from backend.core.demo.stress_engine import stop_scenario
        return stop_scenario(scenario_id)
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/stress/stop", tags=["Demo"])
async def stop_all_stress():
    """Stop all running stress scenarios immediately."""
    try:
        from backend.core.demo.stress_engine import stop_all
        return stop_all()
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/stress/status", tags=["Demo"])
async def stress_status():
    """Get current stress test status."""
    try:
        from backend.core.demo.stress_engine import get_status
        return get_status()
    except Exception as e:
        return {"running": False, "active": [], "error": str(e)}


_FRONTEND_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "frontend",
)

if _os.path.isdir(_FRONTEND_DIR):
    @app.get("/", include_in_schema=False)
    async def serve_dashboard():
        p = _os.path.join(_FRONTEND_DIR, "index.html")
        return _FR(p) if _os.path.exists(p) else _HR("<h1>CVIS backend is running</h1>")

    @app.get("/onboarding", include_in_schema=False)
    async def serve_onboarding():
        p = _os.path.join(_FRONTEND_DIR, "onboarding.html")
        if _os.path.exists(p):
            return _FR(p)
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/")

    try:
        app.mount("/assets", _SS(_FRONTEND_DIR, html=False), name="frontend-assets")
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  CVIS v9.0 - dev server")
    print(f"  psutil: {'OK' if PS_OK else 'MISSING - synthetic metrics active'}")
    print("  Docs  : http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
        log_level="warning",
        access_log=False,
    )
