

"""
CVIS v9 — db.py
Lightweight SQLite persistence via aiosqlite.
Stores: alert history, intervention log, event log, metric snapshots.
Falls back silently to in-memory if aiosqlite is not installed.
"""

import json, logging, os, sys, time
from typing import Optional

log = logging.getLogger("cvis.db")

# ── DB Path — Windows-aware ───────────────────────────────
# On Linux/Docker the default is /app/data/cvis.db.
# On Windows that path doesn't exist, so fall back to a
# path relative to this file's location.
if sys.platform == "win32":
    _DEFAULT_DB = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "data", "cvis.db"
    )
else:
    _DEFAULT_DB = "/app/data/cvis.db"

DB_PATH = os.environ.get("DB_PATH", _DEFAULT_DB)

# Ensure the data directory exists before trying to open the DB
try:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
except Exception:
    pass

try:
    import aiosqlite
    SQLITE_OK = True
except ImportError:
    SQLITE_OK = False
    log.warning("aiosqlite not installed — history will not survive restarts (pip install aiosqlite)")

# ── Schema ────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id                TEXT    PRIMARY KEY,
    rule_id           TEXT    NOT NULL,
    severity          TEXT    NOT NULL,
    message           TEXT    NOT NULL,
    metrics           TEXT,
    fired_at          REAL    NOT NULL,
    resolved_at       REAL,
    sent_to           TEXT,
    lifecycle_version INTEGER NOT NULL DEFAULT 1,
    device_id         TEXT,
    device_name       TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_fired_at ON alerts(fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity  ON alerts(severity);

CREATE TABLE IF NOT EXISTS interventions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    anomaly     REAL,
    ctx_key     TEXT,
    ts          REAL    NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);
CREATE INDEX IF NOT EXISTS idx_interventions_ts ON interventions(ts DESC);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    severity    TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    ts          REAL    NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu         REAL,
    mem         REAL,
    disk        REAL,
    net         REAL,
    anomaly     REAL,
    health      REAL,
    ensemble    REAL,
    ts          REAL    NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON metric_snapshots(ts DESC);
CREATE TABLE IF NOT EXISTS incidents (
    incident_id      TEXT PRIMARY KEY,
    device_id        TEXT,
    failure_type     TEXT NOT NULL,
    severity         TEXT,
    status           TEXT NOT NULL DEFAULT 'open',

    started_at       REAL,
    detected_at      REAL,
    predicted_at     REAL,
    occurred_at      REAL,
    resolved_at      REAL,

    root_cause       TEXT,
    evidence         TEXT,
    metadata         TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_device_ts
ON incidents(device_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_type_ts
ON incidents(failure_type, occurred_at DESC);


CREATE TABLE IF NOT EXISTS predictions (
    prediction_id       TEXT PRIMARY KEY,
    device_id           TEXT,

    failure_type        TEXT NOT NULL,
    created_at          REAL NOT NULL,
    expected_at         REAL,

    confidence          REAL,
    risk_score          REAL,
    lead_time_seconds   REAL,

    status              TEXT NOT NULL DEFAULT 'active',

    evidence            TEXT,
    model_version       TEXT
);

CREATE INDEX IF NOT EXISTS idx_predictions_device_ts
ON predictions(device_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_status
ON predictions(status);


CREATE TABLE IF NOT EXISTS prediction_outcomes (
    prediction_id       TEXT PRIMARY KEY,
    incident_id         TEXT,

    outcome             TEXT NOT NULL,
    lead_time_seconds   REAL,

    false_positive      INTEGER NOT NULL DEFAULT 0,
    false_negative      INTEGER NOT NULL DEFAULT 0,
    prevented           INTEGER NOT NULL DEFAULT 0,

    validated_at        REAL,

    FOREIGN KEY(prediction_id)
        REFERENCES predictions(prediction_id),

    FOREIGN KEY(incident_id)
        REFERENCES incidents(incident_id)
);

CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_incident
ON prediction_outcomes(incident_id);
"""

# ─────────────────────────────────────────────────────────
#  Connection pool
# ─────────────────────────────────────────────────────────
_conn: Optional[object] = None

async def get_db():
    global _conn
    if not SQLITE_OK:
        return None
    if _conn is None:
        try:
            # Ensure directory exists right before connecting
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            _conn = await aiosqlite.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = aiosqlite.Row
            await _conn.executescript(_SCHEMA)
                       # Backward-compatible schema migration.
            # Existing alerts keep lifecycle_version=1.
            async with _conn.execute("PRAGMA table_info(alerts)") as cur:
                columns = {row["name"] for row in await cur.fetchall()}

            if "lifecycle_version" not in columns:
                await _conn.execute(
                    """
                    ALTER TABLE alerts
                    ADD COLUMN lifecycle_version INTEGER NOT NULL DEFAULT 1
                    """
                )
                await _conn.commit()
                log.info("Added alerts.lifecycle_version column")

            # Add device identity columns to existing databases.
            if "device_id" not in columns:
                await _conn.execute(
                    "ALTER TABLE alerts ADD COLUMN device_id TEXT"
                )
                log.info("Added alerts.device_id column")

            if "device_name" not in columns:
                await _conn.execute(
                    "ALTER TABLE alerts ADD COLUMN device_name TEXT"
                )
                log.info("Added alerts.device_name column")

            await _conn.commit()

            await _conn.execute("PRAGMA journal_mode=WAL")
            await _conn.execute("PRAGMA synchronous=NORMAL")
            await _conn.commit()
            log.info("SQLite opened: %s", DB_PATH)
        except Exception as e:
            log.warning("SQLite unavailable (%s) — running without persistence", e)
            _conn = None
            return None
    return _conn

async def close_db():
    global _conn
    if _conn:
        try:
            await _conn.close()
        except Exception:
            pass
        _conn = None

# ─────────────────────────────────────────────────────────
#  ALERTS
# ─────────────────────────────────────────────────────────

async def _migrate_alert_device_columns(db):
    """Add remote-device identity columns to existing alert databases."""
    try:
        async with db.execute("PRAGMA table_info(alerts)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}

        if "device_id" not in columns:
            await db.execute("ALTER TABLE alerts ADD COLUMN device_id TEXT")

        if "device_name" not in columns:
            await db.execute("ALTER TABLE alerts ADD COLUMN device_name TEXT")

        await db.commit()
    except Exception as e:
        log.error("Alert device-column migration failed: %s", e)
        raise

async def save_alert(alert) -> bool:
    """Persist a newly created lifecycle-v2 alert."""
    db = await get_db()
    if not db:
        return False

    try:
        await db.execute(
            """
            INSERT OR REPLACE INTO alerts
            (
                id,
                rule_id,
                severity,
                message,
                metrics,
                fired_at,
                resolved_at,
                sent_to,
                lifecycle_version,
                device_id,
                device_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.alert_id,
                alert.rule_id,
                alert.severity,
                alert.message,
                json.dumps(alert.metrics),
                alert.fired_at,
                alert.resolved_at,
                json.dumps(alert.sent_to),
                2,
                getattr(alert, "device_id", None),
                getattr(alert, "device_name", None),
            ),
        )

        await db.commit()

        await db.execute(
            """
            DELETE FROM alerts
            WHERE id NOT IN (
                SELECT id
                FROM alerts
                ORDER BY fired_at DESC
                LIMIT 1000
            )
            """
        )

        await db.commit()
        return True

    except Exception as e:
        log.error("save_alert: %s", e)
        return False




async def resolve_alert(alert_id: str, resolved_at: float) -> bool:
    """Mark an active alert as resolved in SQLite."""
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute(
            """
            UPDATE alerts
            SET resolved_at = ?
            WHERE id = ?
              AND resolved_at IS NULL
            """,
            (resolved_at, alert_id),
        )
        await db.commit()
        return True
    except Exception as e:
        log.error("resolve_alert: %s", e)
        return False


async def load_active_alerts() -> list[dict]:
    """
    Load unresolved lifecycle-v2 alerts.

    Lifecycle-v1 alerts are historical records from before
    active-incident tracking was introduced.
    """
    db = await get_db()
    if not db:
        return []

    try:
        async with db.execute(
            """
            SELECT *
            FROM alerts
            WHERE resolved_at IS NULL
              AND lifecycle_version = 2
            ORDER BY fired_at DESC
            """
        ) as cur:
            rows = await cur.fetchall()

        out = []

        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d["metrics"] or "{}")
            d["sent_to"] = json.loads(d["sent_to"] or "[]")
            out.append(d)

        return out

    except Exception as e:
        log.error("load_active_alerts: %s", e)
        return []


async def load_alerts(limit: int = 200, severity: str = None) -> list[dict]:
    db = await get_db()
    if not db:
        return []
    try:
        q = "SELECT * FROM alerts"
        params = []
        if severity:
            q += " WHERE severity = ?"
            params.append(severity)
        q += f" ORDER BY fired_at DESC LIMIT {int(limit)}"
        async with db.execute(q, params) as cur:
            rows = await cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d["metrics"] or "{}")
            d["sent_to"] = json.loads(d["sent_to"] or "[]")
            out.append(d)
        return out
    except Exception as e:
        log.error("load_alerts: %s", e)
        return []

async def count_alerts_by_severity() -> dict:
    db = await get_db()
    if not db:
        return {}
    try:
        async with db.execute(
            "SELECT severity, COUNT(*) as n FROM alerts GROUP BY severity"
        ) as cur:
            return {r["severity"]: r["n"] for r in await cur.fetchall()}
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────
#  INTERVENTIONS
# ─────────────────────────────────────────────────────────
async def save_intervention(type_: str, text: str, anomaly: float = 0, ctx_key: str = "") -> bool:
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute(
            "INSERT INTO interventions (type, text, anomaly, ctx_key, ts) VALUES (?,?,?,?,?)",
            (type_, text, anomaly, ctx_key, time.time())
        )
        await db.commit()
        return True
    except Exception as e:
        log.error("save_intervention: %s", e)
        return False

async def load_interventions(limit: int = 50) -> list[dict]:
    db = await get_db()
    if not db:
        return []
    try:
        async with db.execute(
            "SELECT * FROM interventions ORDER BY ts DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
    except Exception:
        return []

# ─────────────────────────────────────────────────────────
#  EVENTS
# ─────────────────────────────────────────────────────────
async def save_event(severity: str, message: str) -> bool:
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute(
            "INSERT INTO events (severity, message, ts) VALUES (?,?,?)",
            (severity, message, time.time())
        )
        await db.commit()
        await db.execute(
            "DELETE FROM events WHERE id NOT IN "
            "(SELECT id FROM events ORDER BY ts DESC LIMIT 1000)"
        )
        await db.commit()
        return True
    except Exception as e:
        log.error("save_event: %s", e)
        return False

async def load_events(limit: int = 60) -> list[dict]:
    db = await get_db()
    if not db:
        return []
    try:
        async with db.execute(
            "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
    except Exception:
        return []

# ─────────────────────────────────────────────────────────
#  METRIC SNAPSHOTS
# ─────────────────────────────────────────────────────────
_last_snapshot_ts = 0.0
_startup_ts = __import__("time").time()
STARTUP_GRACE_S = 300

async def maybe_save_snapshot(metrics: dict, interval_s: int = 10) -> bool:
    global _last_snapshot_ts
    now = time.time()
    if now - _startup_ts < STARTUP_GRACE_S:
        return False
    if now - _last_snapshot_ts < interval_s:
        return False
    _last_snapshot_ts = now
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute(
            "INSERT INTO metric_snapshots (cpu,mem,disk,net,anomaly,health,ensemble,ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                metrics.get("cpu_percent",    0),
                metrics.get("memory",         0),
                metrics.get("disk_percent",   0),
                metrics.get("network_percent",0),
                metrics.get("anomaly_score",  0),
                metrics.get("health_score",   100),
                metrics.get("anomaly_score",  0),
                now,
            )
        )
        await db.commit()
        await db.execute(
            "DELETE FROM metric_snapshots WHERE ts < ?", (now - 86400,)
        )
        await db.commit()
        return True
    except Exception as e:
        log.error("save_snapshot: %s", e)
        return False

async def load_snapshots(hours: float = 1.0) -> list[dict]:
    db = await get_db()
    if not db:
        return []
    try:
        since = time.time() - hours * 3600
        async with db.execute(
            "SELECT * FROM metric_snapshots WHERE ts > ? ORDER BY ts ASC", (since,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
    except Exception:
        return []

# ─────────────────────────────────────────────────────────
#  INCIDENT / PREDICTION GROUND TRUTH
# ─────────────────────────────────────────────────────────

async def save_incident(incident: dict) -> bool:
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute("""
            INSERT OR REPLACE INTO incidents (
                incident_id, device_id, failure_type, severity, status,
                started_at, detected_at, predicted_at, occurred_at,
                resolved_at, root_cause, evidence, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            incident.get("incident_id"),
            incident.get("device_id"),
            incident.get("failure_type"),
            incident.get("severity"),
            incident.get("status", "open"),
            incident.get("started_at"),
            incident.get("detected_at"),
            incident.get("predicted_at"),
            incident.get("occurred_at"),
            incident.get("resolved_at"),
            json.dumps(incident.get("root_cause")) if isinstance(incident.get("root_cause"), (dict, list)) else incident.get("root_cause"),
            json.dumps(incident.get("evidence")) if isinstance(incident.get("evidence"), (dict, list)) else incident.get("evidence"),
            json.dumps(incident.get("metadata")) if isinstance(incident.get("metadata"), (dict, list)) else incident.get("metadata"),
        ))
        await db.commit()
        return True
    except Exception as e:
        log.error("save_incident: %s", e)
        return False


async def save_prediction(prediction: dict) -> bool:
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute("""
            INSERT OR REPLACE INTO predictions (
                prediction_id, device_id, failure_type, created_at,
                expected_at, confidence, risk_score, lead_time_seconds,
                status, evidence, model_version, acknowledged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prediction.get("prediction_id"),
            prediction.get("device_id"),
            prediction.get("failure_type"),
            prediction.get("created_at", time.time()),
            prediction.get("expected_at"),
            prediction.get("confidence"),
            prediction.get("risk_score"),
            prediction.get("lead_time_seconds"),
            prediction.get("status", "active"),
            json.dumps(prediction.get("evidence")) if isinstance(prediction.get("evidence"), (dict, list)) else prediction.get("evidence"),
            prediction.get("model_version"),
            int(bool(prediction.get("acknowledged", False))),
        ))
        await db.commit()
        return True
    except Exception as e:
        log.error("save_prediction: %s", e)
        return False


async def save_prediction_outcome(outcome: dict) -> bool:
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute("""
            INSERT OR REPLACE INTO prediction_outcomes (
                prediction_id, incident_id, outcome, lead_time_seconds,
                false_positive, false_negative, prevented, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            outcome.get("prediction_id"),
            outcome.get("incident_id"),
            outcome.get("outcome"),
            outcome.get("lead_time_seconds"),
            int(bool(outcome.get("false_positive", False))),
            int(bool(outcome.get("false_negative", False))),
            int(bool(outcome.get("prevented", False))),
            outcome.get("validated_at", time.time()),
        ))
        await db.commit()
        return True
    except Exception as e:
        log.error("save_prediction_outcome: %s", e)
        return False


async def load_active_predictions() -> list[dict]:
    db = await get_db()
    if not db:
        return []
    try:
        async with db.execute("""
            SELECT * FROM predictions
            WHERE status = 'active'
            ORDER BY created_at DESC
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        log.error("load_active_predictions: %s", e)
        return []


async def load_incidents(limit: int = 100) -> list[dict]:
    db = await get_db()
    if not db:
        return []
    try:
        async with db.execute("""
            SELECT * FROM incidents
            ORDER BY occurred_at DESC
            LIMIT ?
        """, (limit,)) as cur:
            return [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        log.error("load_incidents: %s", e)
        return []

# ─────────────────────────────────────────────────────────
#  DB info — never raises, always returns a dict
# ─────────────────────────────────────────────────────────
async def db_info() -> dict:
    if not SQLITE_OK:
        return {"available": False, "reason": "aiosqlite not installed", "alerts": 0}
    try:
        db = await get_db()
        if not db:
            return {"available": False, "reason": f"Could not open {DB_PATH}", "alerts": 0}
        async with db.execute("SELECT COUNT(*) as n FROM alerts") as c:
            alerts = (await c.fetchone())["n"]
        async with db.execute(
            "SELECT COUNT(*) as n FROM alerts WHERE resolved_at IS NULL AND lifecycle_version = 2"
        ) as c:
            active_alerts = (await c.fetchone())["n"]
        async with db.execute("SELECT COUNT(*) as n FROM interventions") as c:
            ivs = (await c.fetchone())["n"]
        async with db.execute("SELECT COUNT(*) as n FROM events")           as c: evts  = (await c.fetchone())["n"]
        async with db.execute("SELECT COUNT(*) as n FROM metric_snapshots") as c: snaps = (await c.fetchone())["n"]
        size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "available":     True,
            "path":          DB_PATH,
            "size_bytes":    size_bytes,
            "alerts":        alerts,
            "active_alerts":  active_alerts,
            "interventions": ivs,
            "events":        evts,
            "snapshots":     snaps,
        }
    except Exception as e:
        return {"available": False, "reason": str(e), "alerts": 0}
