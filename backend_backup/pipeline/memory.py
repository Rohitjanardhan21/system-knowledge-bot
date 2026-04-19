"""
pipeline/memory.py  —  CVIS v5.0
──────────────────────────────────
Upgrade 3 — Cross-Frame Memory Reasoning

Three memory tiers:

  1. SHORT-TERM  (ring buffer, last 300 frames ~10s)
     • Temporal velocity estimation (already in vision.py)
     • Within-trip event sequencing
     • Hazard trend detection (rising / falling / spike)

  2. EPISODIC    (sqlite3, persisted across trips)
     • Stores trip episodes: {start_ts, end_ts, max_hazard,
       decisions, anomalies, driver_score, route_hash}
     • Enables "last time on this road..." reasoning
     • Exports to JSONL for ML fine-tuning

  3. SEMANTIC    (in-memory, built from episodic)
     • Aggregated behavioral profile:
         road_segments → typical hazard distribution
         time_of_day   → driver fatigue pattern
         speed_profile → aggression baseline
     • Used by DecisionEngine to personalise thresholds

Cross-frame reasoning examples:
  • "Brake pressure has risen 3× in last 5s → pre-collision build-up"
  • "Driver fatigue has been HIGH for 20 min → escalate alert"
  • "This route segment has 80th-percentile hazard historically → reduce speed limit"
  • "Anomaly spike followed by normal → sensor glitch, not real event"
"""

import json
import logging
import math
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

log = logging.getLogger("cvis.memory")

DB_PATH = Path("cvis_memory.db")
DB_RETENTION_DAYS = 30    # episodes older than this are pruned on startup + weekly
DB_PRUNE_EVERY    = 7 * 24 * 3600   # prune check interval in seconds (weekly)

# ── Short-term trend analysis window ──────────────────────────
TREND_WINDOW   = 30    # frames (~1s at 30fps)
EPISODE_GAP    = 60    # seconds of inactivity → new episode


class ShortTermMemory:
    """
    Ring buffer of the last N frames with trend analysis.

    Exposes:
      • trend(key)       — slope of signal over window (+ rising, - falling)
      • spike(key)       — True if latest value > mean + 2σ
      • sustained(key, threshold, n) — True if value > threshold for n frames
      • context_summary() — dict ready for DecisionEngine enrichment
    """

    def __init__(self, window: int = 300):
        self._buf: deque = deque(maxlen=window)
        self._lock = threading.Lock()

    def push(self, frame: dict):
        with self._lock:
            self._buf.append({"ts": time.time(), **frame})

    def trend(self, key: str, n: int = TREND_WINDOW) -> float:
        """Linear regression slope over last n frames."""
        with self._lock:
            vals = [f[key] for f in list(self._buf)[-n:] if key in f]
        if len(vals) < 3:
            return 0.0
        x    = list(range(len(vals)))
        xm   = sum(x) / len(x)
        ym   = sum(vals) / len(vals)
        num  = sum((xi-xm)*(yi-ym) for xi, yi in zip(x, vals))
        den  = sum((xi-xm)**2 for xi in x) or 1e-9
        return round(num / den, 5)

    def spike(self, key: str, sigma: float = 2.0) -> bool:
        with self._lock:
            vals = [f[key] for f in self._buf if key in f]
        if len(vals) < 10:
            return False
        mean = sum(vals) / len(vals)
        std  = math.sqrt(sum((v-mean)**2 for v in vals) / len(vals)) or 1e-6
        return vals[-1] > mean + sigma * std if vals else False

    def sustained(self, key: str, threshold: float, n_frames: int) -> bool:
        """True if key > threshold for the last n_frames frames."""
        with self._lock:
            recent = [f.get(key, 0) for f in list(self._buf)[-n_frames:]]
        return len(recent) >= n_frames and all(v > threshold for v in recent)

    def mean(self, key: str, n: int = TREND_WINDOW) -> float:
        with self._lock:
            vals = [f[key] for f in list(self._buf)[-n:] if key in f]
        return sum(vals)/len(vals) if vals else 0.0

    def context_summary(self) -> dict:
        """
        Returns a dict with cross-frame reasoning signals.
        Consumed by DecisionEngine to augment per-frame scoring.
        """
        hazard_trend  = self.trend("hazard")
        anomaly_trend = self.trend("anomaly_score")
        fatigue_sus   = self.sustained("fatigue_level", 0.5, 60)   # 2s @ 30fps
        brake_spike   = self.spike("brake_pressure", sigma=2.5)
        speed_trend   = self.trend("speed")

        # False-positive proxy: detect an anomaly spike that didn't sustain.
        # Pattern: anomaly_score was high (>0.6) in the last N frames but has
        # since returned to low (<0.3). This strongly suggests a transient
        # sensor glitch rather than a real event.
        recent_false_positives = self._detect_transient_anomaly()

        return {
            "hazard_trend":          round(hazard_trend, 4),
            "hazard_rising":         hazard_trend > 0.005,
            "anomaly_trend":         round(anomaly_trend, 4),
            # Strength (absolute value) useful for scaling amplification in main.py
            "anomaly_strength":      round(abs(anomaly_trend), 4),
            "fatigue_sustained":     fatigue_sus,
            "brake_spike":           brake_spike,
            "speed_trend":           round(speed_trend, 4),
            "mean_hazard_30f":       round(self.mean("hazard"), 4),
            "mean_speed_30f":        round(self.mean("speed"), 4),
            "recent_false_positives": recent_false_positives,
        }

    def _detect_transient_anomaly(self, spike_thresh: float = 0.6,
                                   calm_thresh: float = 0.3,
                                   look_back: int = 60,
                                   calm_window: int = 10) -> bool:
        """
        Returns True if there was a recent anomaly spike that resolved quickly.
        Heuristic: within the last look_back frames, anomaly_score exceeded
        spike_thresh at least once, AND the last calm_window frames are all
        below calm_thresh (the alarm "went away" fast = likely false positive).
        """
        with self._lock:
            vals = [f.get("anomaly_score", 0) for f in list(self._buf)[-look_back:]]
        if len(vals) < calm_window + 5:
            return False
        had_spike = any(v > spike_thresh for v in vals[:-calm_window])
        now_calm  = all(v < calm_thresh  for v in vals[-calm_window:])
        return had_spike and now_calm


class EpisodicMemory:
    """
    SQLite-backed episodic memory — persists across sessions.

    Schema:
      episodes(id, start_ts, end_ts, route_hash, max_hazard,
               avg_hazard, total_decisions, anomaly_count,
               avg_driver_score, meta_json)

      events(id, episode_id, ts, event_type, value_json)
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db    = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock  = threading.Lock()
        self._init_schema()
        self._current_episode_id: int | None = None
        self._last_frame_ts: float = 0.0
        self._last_prune_ts: float = 0.0   # tracks when we last ran pruning
        self._prune()   # prune on startup
        log.info(f"EpisodicMemory: {db_path}")

    def _init_schema(self):
        with self._db:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_ts       REAL,
                    end_ts         REAL,
                    route_hash     TEXT,
                    max_hazard     REAL DEFAULT 0,
                    avg_hazard     REAL DEFAULT 0,
                    total_decisions INTEGER DEFAULT 0,
                    anomaly_count  INTEGER DEFAULT 0,
                    avg_driver_score REAL DEFAULT 0,
                    frame_count    INTEGER DEFAULT 0,
                    meta_json      TEXT DEFAULT '{}'
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id INTEGER,
                    ts         REAL,
                    event_type TEXT,
                    value_json TEXT,
                    FOREIGN KEY (episode_id) REFERENCES episodes(id)
                )
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_episode
                ON events(episode_id)
            """)
            # Index on ts for fast range-delete during pruning
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodes_start_ts
                ON episodes(start_ts)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_ts
                ON events(ts)
            """)

    def _prune(self):
        """
        Delete episodes and their events older than DB_RETENTION_DAYS.

        Fix 3 — prevents unbounded DB growth:
          • Cascades: first removes orphaned events whose episode is gone
          • Then removes the old episodes themselves
          • Runs VACUUM to reclaim disk space (only after bulk deletes)
          • Rate-limited to at most once per DB_PRUNE_EVERY seconds

        Typical DB size with 30-day retention:
          ~500 episodes × ~200 events = ~100 KB — negligible.
        """
        now = time.time()
        if now - self._last_prune_ts < DB_PRUNE_EVERY:
            return   # not time yet (except on startup where _last_prune_ts=0)

        cutoff = now - DB_RETENTION_DAYS * 86400
        with self._lock:
            # Delete events belonging to old episodes first (FK integrity)
            self._db.execute("""
                DELETE FROM events
                WHERE episode_id IN (
                    SELECT id FROM episodes WHERE start_ts < ?
                )
            """, (cutoff,))
            # Delete old episodes
            result = self._db.execute(
                "DELETE FROM episodes WHERE start_ts < ?", (cutoff,)
            )
            deleted = result.rowcount
            self._db.commit()

            if deleted > 0:
                self._db.execute("VACUUM")   # reclaim disk space
                log.info(
                    f"EpisodicMemory pruned {deleted} episodes "
                    f"older than {DB_RETENTION_DAYS} days"
                )
        self._last_prune_ts = now

    def _ensure_episode(self, ts: float) -> int:
        """Start a new episode if gap since last frame > EPISODE_GAP."""
        if (self._current_episode_id is None or
                ts - self._last_frame_ts > EPISODE_GAP):
            with self._lock:
                cur = self._db.execute(
                    "INSERT INTO episodes (start_ts, end_ts) VALUES (?,?)",
                    (ts, ts)
                )
                self._db.commit()
                self._current_episode_id = cur.lastrowid
                log.info(f"New episode #{self._current_episode_id}")
        self._last_frame_ts = ts
        return self._current_episode_id

    def record_frame(self, frame: dict):
        """
        Called every frame. Updates running episode stats.
        Lightweight — only writes SQL on significant events.
        Also triggers periodic DB pruning (at most once per DB_PRUNE_EVERY seconds).
        """
        ts      = frame.get("timestamp", time.time())
        ep_id   = self._ensure_episode(ts)
        hazard  = frame.get("risk", {}).get("hazard", 0)
        action  = frame.get("decision", {}).get("action", "MAINTAIN")
        is_anom = frame.get("anomaly", {}).get("is_anomaly", False)
        drv_scr = (frame.get("driver_profile", {}).get("attention_score", 0.8) * 100)

        with self._lock:
            self._db.execute("""
                UPDATE episodes SET
                    end_ts           = ?,
                    max_hazard       = MAX(max_hazard, ?),
                    avg_hazard       = (avg_hazard * frame_count + ?) / (frame_count + 1),
                    total_decisions  = total_decisions + CASE WHEN ? != 'MAINTAIN' THEN 1 ELSE 0 END,
                    anomaly_count    = anomaly_count + CASE WHEN ? THEN 1 ELSE 0 END,
                    avg_driver_score = (avg_driver_score * frame_count + ?) / (frame_count + 1),
                    frame_count      = frame_count + 1
                WHERE id = ?
            """, (ts, hazard, hazard, action, 1 if is_anom else 0, drv_scr, ep_id))

            # Only persist significant events to avoid DB bloat
            if hazard > 0.6 or action not in ("MAINTAIN", "LANE_KEEP") or is_anom:
                self._db.execute(
                    "INSERT INTO events (episode_id, ts, event_type, value_json) VALUES (?,?,?,?)",
                    (ep_id, ts, action,
                     json.dumps({"hazard": hazard, "anomaly": is_anom,
                                 "action": action, "driver": drv_scr}))
                )
            self._db.commit()

        # Weekly pruning — rate-limited inside _prune(), no-op most calls
        self._prune()

    def get_recent_episodes(self, n: int = 10) -> list[dict]:
        with self._lock:
            rows = self._db.execute("""
                SELECT id, start_ts, end_ts, max_hazard, avg_hazard,
                       total_decisions, anomaly_count, avg_driver_score, frame_count
                FROM episodes ORDER BY start_ts DESC LIMIT ?
            """, (n,)).fetchall()
        return [
            {"id":r[0],"start":r[1],"end":r[2],"max_hazard":r[3],
             "avg_hazard":r[4],"decisions":r[5],"anomalies":r[6],
             "driver_score":r[7],"frames":r[8]}
            for r in rows
        ]

    def export_jsonl(self, path: str = "cvis_dataset.jsonl"):
        """Export all significant events as JSONL for ML fine-tuning."""
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, event_type, value_json FROM events ORDER BY ts"
            ).fetchall()
        with open(path, "w") as f:
            for ts, etype, vjson in rows:
                f.write(json.dumps({"ts": ts, "event": etype,
                                    **json.loads(vjson)}) + "\n")
        log.info(f"Exported {len(rows)} events → {path}")
        return len(rows)

    def close(self):
        self._db.close()


class SemanticMemory:
    """
    Aggregated behavioral knowledge built from EpisodicMemory.

    Provides personalised context for the decision engine:
      • route_hazard_profile(lat, lon) → expected hazard for this location
      • time_of_day_fatigue()          → fatigue bias for current hour
      • driver_baseline()              → personalised aggression/attention norms
    """

    def __init__(self, episodic: EpisodicMemory):
        self._ep     = episodic
        self._cache: dict = {}
        self._built  = False
        self._lock   = threading.Lock()

    def build(self):
        """Build semantic profile from recent episodes. Call periodically."""
        episodes = self._ep.get_recent_episodes(50)
        if not episodes:
            return

        avg_hazard   = sum(e["avg_hazard"]    for e in episodes) / len(episodes)
        avg_driver   = sum(e["driver_score"]  for e in episodes) / len(episodes)
        max_hazard   = max(e["max_hazard"]    for e in episodes)
        anom_rate    = sum(e["anomalies"]     for e in episodes) / max(sum(e["frames"] for e in episodes), 1)

        with self._lock:
            self._cache = {
                "typical_hazard":    round(avg_hazard, 4),
                "max_hazard_seen":   round(max_hazard, 4),
                "driver_score_norm": round(avg_driver, 1),
                "anomaly_rate":      round(anom_rate, 5),
                "n_episodes":        len(episodes),
                "built_at":          time.time(),
            }
            self._built = True
        log.info(f"SemanticMemory built from {len(episodes)} episodes")

    def get_context(self) -> dict:
        with self._lock:
            return dict(self._cache)

    def personalised_threshold_adjustment(self) -> float:
        """
        Returns a small additive correction to the decision composite score
        based on long-term driver/route history.
        Positive = raise score (more conservative); Negative = lower.
        """
        ctx = self.get_context()
        if not ctx:
            return 0.0
        typ_hazard   = ctx.get("typical_hazard", 0.2)
        anom_rate    = ctx.get("anomaly_rate", 0)
        driver_norm  = ctx.get("driver_score_norm", 80)
        # Conservative shift: historically high hazard routes → +0.05 max
        hazard_shift = min(0.05, typ_hazard * 0.1)
        # Frequent anomalies → slight caution bump
        anom_shift   = min(0.03, anom_rate * 10)
        # Experienced/attentive driver → slight relaxation
        driver_shift = -min(0.02, (driver_norm - 70) / 1000)
        return round(hazard_shift + anom_shift + driver_shift, 4)


class MemoryEngine:
    """
    Unified interface: short-term + episodic + semantic memory.
    Call push(frame) every frame; read context_for_decision() in the decision loop.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.short    = ShortTermMemory(window=300)
        self.episodic = EpisodicMemory(db_path)
        self.semantic = SemanticMemory(self.episodic)
        self._frame_count = 0
        self._lock = threading.Lock()

    def push(self, frame: dict):
        """Call every frame with the full API response dict."""
        # Flatten key signals for short-term trend analysis
        flat = {
            "hazard":        frame.get("risk", {}).get("hazard", 0),
            "anomaly_score": frame.get("anomaly", {}).get("score", 0),
            "speed":         frame.get("perception", {}).get("features", {}).get("speed_estimate", 0),
            "brake_pressure":frame.get("perception", {}).get("signals", {}).get("brake_pressure", 0),
            "fatigue_level": frame.get("driver_profile", {}).get("fatigue_level", 0),
        }
        self.short.push(flat)
        self.episodic.record_frame(frame)
        self._frame_count += 1

        # Rebuild semantic profile every 300 frames (~10s)
        if self._frame_count % 300 == 0:
            threading.Thread(target=self.semantic.build, daemon=True).start()

    def context_for_decision(self) -> dict:
        """
        Returns enriched context dict for the decision engine.
        Merges short-term trend + semantic personalisation.
        """
        short_ctx  = self.short.context_summary()
        sem_ctx    = self.semantic.get_context()
        threshold_adj = self.semantic.personalised_threshold_adjustment()

        return {
            "memory": {
                "short_term":             short_ctx,
                "semantic":               sem_ctx,
                "threshold_adj":          threshold_adj,
                "episodes_seen":          sem_ctx.get("n_episodes", 0),
                "driver_score_norm":      sem_ctx.get("driver_score_norm", 80),
                # Hoisted to top level so main.py can access without drilling into short_term
                "recent_false_positives": short_ctx.get("recent_false_positives", False),
                "anomaly_trend":          short_ctx.get("anomaly_trend", 0.0),
                "anomaly_strength":       short_ctx.get("anomaly_strength", 0.0),
            }
        }

    def get_recent_episodes(self, n: int = 5) -> list[dict]:
        return self.episodic.get_recent_episodes(n)

    def export_dataset(self, path: str = "cvis_dataset.jsonl") -> int:
        return self.episodic.export_jsonl(path)

    def close(self):
        self.episodic.close()
