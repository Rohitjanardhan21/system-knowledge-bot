"""
pipeline/anomaly.py  —  CVIS v5.0  (final)
───────────────────────────────────────────
Layer 4 — ML Anomaly Detection

Scaling pipeline (Fix 1 — fully corrected):

  raw_signals
      │
      ▼  _engineer_features()
  15-D feature vector  (9 raw + 6 engineered)
      │
      ▼  _pre_normalize()
  domain-range clip → [0, 1]  per feature
  (prevents high-magnitude signals like RPM dominating
   IsolationForest random split selection over low-magnitude
   ones like acc_x before StandardScaler runs)
      │
      ▼  StandardScaler.transform()
  zero-mean, unit-variance per feature
  INVARIANT: _fitted=True  ↔  _model and _scaler are both non-None
      │
      ▼  IsolationForest.score_samples()
  negative avg path-length → normalised anomaly score [0, 1]

Online learning:
  • Warm-up: 50 samples before first fit
  • Rolling window: 2 000 samples
  • Auto-refit: every 200 new samples

Thread safety: all state mutations guarded by threading.Lock.
"""

import logging
import math
import threading
import time
from collections import deque
from typing import Any

import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False

log = logging.getLogger("cvis.anomaly")

N_WARMUP    = 50
WINDOW_SIZE = 2000
REFIT_EVERY = 200


class IsolationForestDetector:
    """Production-grade ML anomaly detector for vehicle telemetry."""

    FEATURE_NAMES = [
        "speed", "thermal", "vibration", "rpm", "brake",
        "acc_x", "acc_y", "gyro_yaw", "lane_offset",
        "speed_delta", "thermal_delta", "acc_magnitude",
        "lateral_energy", "jerk", "brake_speed_ratio",
    ]

    # Domain-knowledge min/max for pre-normalisation → [0,1]
    # Order must match FEATURE_NAMES exactly.
    FEATURE_RANGES = [
        (0,    140),   # speed         mph
        (50,   130),   # thermal       °C
        (0,    60),    # vibration     Hz
        (0,    6000),  # rpm
        (0,    100),   # brake         %
        (-3,    3),    # acc_x         g
        (-3,    3),    # acc_y         g
        (-2,    2),    # gyro_yaw      deg/s
        (-1,    1),    # lane_offset
        (-20,  20),    # speed_delta   mph/frame
        (-5,    5),    # thermal_delta degC/frame
        (0,     4),    # acc_magnitude g
        (0,     9),    # lateral_energy g²
        (-2,    2),    # jerk          g/frame
        (0,     3),    # brake_speed_ratio
    ]

    def __init__(self, contamination: float = 0.05, n_estimators: int = 200):
        self.contamination  = contamination
        self.n_estimators   = n_estimators
        self.sample_count   = 0
        self._lock          = threading.Lock()

        # INVARIANT: _fitted=True  <=>  _model and _scaler both non-None.
        # Never check _model alone; always gate on _fitted.
        self._model:  Any  = None
        self._scaler: Any  = None
        self._fitted        = False

        self._window:      deque = deque(maxlen=WINDOW_SIZE)
        self._warmup_buf:  list  = []
        self._since_last_fit     = 0

        self._stats:        dict = {}
        self._patterns:     list = []
        self._anomaly_log: deque = deque(maxlen=500)
        self._prev:         dict = {}
        self._thresholds:   dict = {}

        log.info(f"IsolationForest initialised: n={n_estimators}, c={contamination}")

    # ── Public API ────────────────────────────────────────────

    def score(self, raw_signals: dict) -> dict:
        with self._lock:
            raw_feat  = self._engineer_features(raw_signals)
            norm_feat = self._pre_normalize(raw_feat)      # Fix 1: normalise first

            self._update_stats(raw_signals)
            self._window.append(norm_feat)                 # window = pre-normalised
            if len(self._warmup_buf) < N_WARMUP:
                self._warmup_buf.append(norm_feat)
            self.sample_count    += 1
            self._since_last_fit += 1

            if self.sample_count == N_WARMUP and not self._fitted:
                self._refit()
            if self._fitted and self._since_last_fit >= REFIT_EVERY:
                self._refit()

            result = (self._if_score(norm_feat, raw_signals)
                      if self._fitted
                      else self._stat_score(raw_signals))

            if result["is_anomaly"]:
                self._log_anomaly(raw_signals, result)
                self._mine_pattern(raw_signals, result)

            self._update_thresholds(raw_signals)
            return result

    def get_learned_patterns(self) -> list:
        with self._lock:
            return list(self._patterns[-6:])

    def get_thresholds(self) -> dict:
        with self._lock:
            return {k: round(v, 3) for k, v in self._thresholds.items()}

    # ── Feature engineering ───────────────────────────────────

    def _engineer_features(self, s: dict) -> list[float]:
        speed     = float(s.get("speed",       0))
        thermal   = float(s.get("thermal",     70))
        vibration = float(s.get("vibration",   0))
        rpm       = float(s.get("rpm",         800))
        brake     = float(s.get("brake",       0))
        acc_x     = float(s.get("acc_x",       0))
        acc_y     = float(s.get("acc_y",       0))
        gyro_yaw  = float(s.get("gyro_yaw",    0))
        lane_off  = float(s.get("lane_offset", 0))

        prev_speed   = self._prev.get("speed",   speed)
        prev_thermal = self._prev.get("thermal", thermal)
        prev_acc_mag = self._prev.get("acc_mag", 1.0)

        speed_delta    = speed - prev_speed
        thermal_delta  = thermal - prev_thermal
        acc_mag        = math.sqrt(acc_x**2 + acc_y**2 + 0.98**2)
        lateral_energy = acc_x**2 + acc_y**2
        jerk           = acc_mag - prev_acc_mag
        brake_speed    = brake / (speed + 1e-6)

        self._prev.update({"speed": speed, "thermal": thermal, "acc_mag": acc_mag})

        return [
            speed, thermal, vibration, rpm, brake,
            acc_x, acc_y, gyro_yaw, lane_off,
            speed_delta, thermal_delta, acc_mag,
            lateral_energy, jerk, brake_speed,
        ]

    # ── Pre-normalisation ─────────────────────────────────────

    def _pre_normalize(self, features: list[float]) -> list[float]:
        """
        Clip each feature to its known domain range → [0, 1].

        Why this is needed even though StandardScaler runs afterwards:
          StandardScaler computes mean/std from the training window.
          If RPM (≈2000) and acc_x (≈0.15) coexist, RPM's absolute
          magnitude dominates the pre-scaled matrix. IsolationForest
          chooses split thresholds uniformly at random between feature
          min and max — so RPM gets far more splits than acc_x and
          effectively monopolises the anomaly detection.
          Pre-normalising to [0,1] gives every feature equal footing
          before StandardScaler then fine-tunes distributional spread.
        """
        out = []
        for v, (lo, hi) in zip(features, self.FEATURE_RANGES):
            span = hi - lo
            out.append(0.0 if span == 0
                        else float(max(0.0, min(1.0, (v - lo) / span))))
        return out

    # ── Model fit ─────────────────────────────────────────────

    def _refit(self):
        """
        Fit StandardScaler + IsolationForest on the rolling window.
        Window holds pre-normalised data (already in [0,1]) so
        StandardScaler handles only residual distributional differences.
        Atomic swap: _model and _scaler assigned together as final step
        so _fitted invariant is never partially satisfied.
        """
        if not _SKLEARN_OK:
            return
        data = list(self._window)
        if len(data) < 20:
            return

        X = np.array(data, dtype=np.float32)
        X = np.nan_to_num(X, nan=0.5, posinf=1.0, neginf=0.0)

        scaler   = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = IsolationForest(
            n_estimators  = self.n_estimators,
            contamination = self.contamination,
            max_samples   = min(256, len(data)),
            random_state  = 42,
            n_jobs        = -1,
        )
        model.fit(X_scaled)

        # Atomic swap — invariant maintained
        self._model         = model
        self._scaler        = scaler
        self._fitted        = True
        self._since_last_fit = 0
        log.info(f"IsolationForest refitted on {len(data)} samples")

    # ── IsolationForest scoring ───────────────────────────────

    def _if_score(self, norm_features: list[float], raw: dict) -> dict:
        """
        Score pre-normalised features.
        _fitted=True guarantees _scaler is non-None — transform() is safe.
        """
        X  = np.array([norm_features], dtype=np.float32)
        X  = np.nan_to_num(X, nan=0.5, posinf=1.0, neginf=0.0)
        Xs = self._scaler.transform(X)

        raw_score  = float(self._model.score_samples(Xs)[0])
        normalized = float(np.clip((-raw_score - 0.1) / 0.6, 0.0, 1.0))
        is_anom    = self._model.predict(Xs)[0] == -1
        severity   = ("CRITICAL" if normalized > 0.65
                      else "WARNING" if normalized > 0.35
                      else "NORMAL")

        return {
            "score":           round(normalized, 4),
            "is_anomaly":      bool(is_anom),
            "severity":        severity,
            "top_signals":     self._contribution_estimate(X[0], Xs[0], raw),
            "model_type":      "IsolationForest",
            "raw_if_score":    round(raw_score, 4),
            "trained_samples": self.sample_count,
        }

    def _contribution_estimate(
        self, feat: np.ndarray, feat_scaled: np.ndarray, raw: dict
    ) -> list[dict]:
        contribs = []
        for i, name in enumerate(self.FEATURE_NAMES):
            z = abs(float(feat_scaled[i]))
            contribs.append({
                "signal":       name,
                "value":        round(float(feat[i]), 3),
                "contribution": round(min(1.0, z / 4), 3),
                "z":            round(z, 2),
            })
        return sorted(contribs, key=lambda x: -x["contribution"])[:5]

    # ── Statistical fallback (warm-up) ────────────────────────

    def _stat_score(self, raw: dict) -> dict:
        zs = []
        for k, v in raw.items():
            if not isinstance(v, (int, float)):
                continue
            st = self._stats.get(k, {"mean": float(v), "var": 1.0, "n": 1})
            z  = abs((v - st["mean"]) / (math.sqrt(st["var"]) + 1e-6))
            zs.append({"signal": k, "value": round(float(v), 3),
                        "z": round(z, 2), "contribution": round(min(1.0, z / 5), 3)})
        max_z  = max((x["z"] for x in zs), default=0.0)
        score  = min(1.0, max_z / 5)
        warmup = min(100, int(self.sample_count / N_WARMUP * 100))
        return {
            "score":           round(score, 4),
            "is_anomaly":      score > 0.35,
            "severity":        ("CRITICAL" if score > 0.65 else
                                "WARNING"  if score > 0.35 else "NORMAL"),
            "top_signals":     sorted(zs, key=lambda x: -x["z"])[:5],
            "model_type":      f"Warmup ({warmup}%)",
            "raw_if_score":    None,
            "trained_samples": self.sample_count,
        }

    # ── Welford online stats ──────────────────────────────────

    def _update_stats(self, raw: dict):
        for k, v in raw.items():
            if not isinstance(v, (int, float)):
                continue
            v = float(v)
            if k not in self._stats:
                self._stats[k] = {"mean": v, "var": 1.0, "n": 1}
                continue
            st   = self._stats[k]
            n    = st["n"] + 1
            mean = st["mean"] + (v - st["mean"]) / n
            var  = st["var"]  + (v - st["mean"]) * (v - mean)
            self._stats[k] = {"mean": mean, "var": max(0.001, var / n), "n": n}

    # ── Pattern mining ────────────────────────────────────────

    def _log_anomaly(self, raw: dict, result: dict):
        self._anomaly_log.append({
            "ts": time.time(), "score": result["score"],
            "severity": result["severity"],
            "signals": {k: round(float(v), 2) for k, v in raw.items()
                        if isinstance(v, (int, float))},
        })

    def _mine_pattern(self, raw: dict, result: dict):
        top2 = tuple(x["signal"] for x in result["top_signals"][:2])
        if not top2:
            return
        for p in self._patterns:
            if p["signals"] == top2:
                p["freq"]   += 1
                p["learned"] = _fmt_age(p["first_seen"])
                return
        self._patterns.append({
            "pattern":    f"{top2[0]} + {top2[1]} co-anomaly",
            "signals":    top2,
            "freq":       1,
            "severity":   result["severity"],
            "first_seen": time.time(),
            "learned":    "just now",
        })
        if len(self._patterns) > 20:
            self._patterns = sorted(self._patterns, key=lambda x: -x["freq"])[:20]

    # ── Adaptive thresholds ───────────────────────────────────

    def _update_thresholds(self, raw: dict):
        for k, st in self._stats.items():
            if k in raw:
                self._thresholds[k] = st["mean"] + 2.5 * math.sqrt(st["var"])


def _fmt_age(ts: float) -> str:
    s = int(time.time() - ts)
    if s < 60:   return f"{s}s ago"
    if s < 3600: return f"{s // 60}m ago"
    return f"{s // 3600}h ago"
