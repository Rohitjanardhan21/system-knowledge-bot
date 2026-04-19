"""
CVIS v9 — db.py
Lightweight SQLite persistence via aiosqlite.
Stores: alert history, intervention log, event log, metric snapshots.
Falls back silently to in-memory if aiosqlite is not installed.
"""

import json, logging, os, time
from typing import Optional

log = logging.getLogger("cvis.db")

DB_PATH = os.environ.get("DB_PATH", "/app/data/cvis.db")

try:
    import aiosqlite
    SQLITE_OK = True
except ImportError:
    SQLITE_OK = False
    log.warning("aiosqlite not installed — history will not survive restarts (pip install aiosqlite)")

# ── Schema ────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT    PRIMARY KEY,
    rule_id     TEXT    NOT NULL,
    severity    TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    metrics     TEXT,               -- JSON blob
    fired_at    REAL    NOT NULL,
    resolved_at REAL,
    sent_to     TEXT                -- JSON list
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
"""

# ─────────────────────────────────────────────────────────
#  Connection pool (one persistent connection per process)
# ─────────────────────────────────────────────────────────
_conn: Optional[object] = None

async def get_db():
    global _conn
    if not SQLITE_OK:
        return None
    if _conn is None:
        _conn = await aiosqlite.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = aiosqlite.Row
        await _conn.executescript(_SCHEMA)
        await _conn.execute("PRAGMA journal_mode=WAL")   # concurrent reads + writes
        await _conn.execute("PRAGMA synchronous=NORMAL") # fast enough, safe enough
        await _conn.commit()
        log.info("SQLite opened: %s", DB_PATH)
    return _conn

async def close_db():
    global _conn
    if _conn:
        await _conn.close()
        _conn = None

# ─────────────────────────────────────────────────────────
#  ALERTS
# ─────────────────────────────────────────────────────────
async def save_alert(alert) -> bool:
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute(
            "INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?,?)",
            (
                alert.alert_id,
                alert.rule_id,
                alert.severity,
                alert.message,
                json.dumps(alert.metrics),
                alert.fired_at,
                alert.resolved_at,
                json.dumps(alert.sent_to),
            )
        )
        await db.commit()
        return True
    except Exception as e:
        log.error("save_alert: %s", e)
        return False

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
            d["metrics"]  = json.loads(d["metrics"] or "{}")
            d["sent_to"]  = json.loads(d["sent_to"] or "[]")
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
        # Prune: keep only last 1000 events to prevent unbounded growth
        await db.execute(
            "DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY ts DESC LIMIT 1000)"
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
#  METRIC SNAPSHOTS  (sampled every 10s to keep DB small)
# ─────────────────────────────────────────────────────────
_last_snapshot_ts = 0.0

async def maybe_save_snapshot(metrics: dict, interval_s: int = 10) -> bool:
    global _last_snapshot_ts
    now = time.time()
    if now - _last_snapshot_ts < interval_s:
        return False
    _last_snapshot_ts = now
    db = await get_db()
    if not db:
        return False
    try:
        await db.execute(
            "INSERT INTO metric_snapshots (cpu,mem,disk,net,anomaly,health,ensemble,ts) VALUES (?,?,?,?,?,?,?,?)",
            (
                metrics.get("cpu_percent", 0),
                metrics.get("memory", 0),
                metrics.get("disk_percent", 0),
                metrics.get("network_percent", 0),
                metrics.get("anomaly_score", 0),
                metrics.get("health_score", 100),
                metrics.get("anomaly_score", 0),   # ensemble = anomaly_score from backend
                now,
            )
        )
        await db.commit()
        # Prune: keep 24 hours of 10s samples = 8640 rows max
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
#  DB info endpoint payload
# ─────────────────────────────────────────────────────────
async def db_info() -> dict:
    db = await get_db()
    if not db:
        return {"available": False, "reason": "aiosqlite not installed"}
    try:
        async with db.execute("SELECT COUNT(*) as n FROM alerts")      as c: alerts = (await c.fetchone())["n"]
        async with db.execute("SELECT COUNT(*) as n FROM interventions") as c: ivs   = (await c.fetchone())["n"]
        async with db.execute("SELECT COUNT(*) as n FROM events")       as c: evts  = (await c.fetchone())["n"]
        async with db.execute("SELECT COUNT(*) as n FROM metric_snapshots") as c: snaps = (await c.fetchone())["n"]
        size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "available":    True,
            "path":         DB_PATH,
            "size_bytes":   size_bytes,
            "alerts":       alerts,
            "interventions": ivs,
            "events":       evts,
            "snapshots":    snaps,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}
