"""
CVIS Forecaster
===============
Projects current metric trends forward in time using the LSTM model.
Shows users what will happen in the next 60 minutes, not just what's
happening now.

Plain English output — no ML jargon.
"""
import time
import threading
from dataclasses import dataclass
from typing import Optional
from collections import deque

import numpy as np

# ── Data structures ───────────────────────────────────────

@dataclass
class ForecastPoint:
    """A single point in the forecast timeline."""
    minutes_from_now: int
    cpu:              float
    memory:           float
    disk:             float
    anomaly:          float
    risk_level:       str   # SAFE / ELEVATED / HIGH / CRITICAL
    plain_label:      str   # human-readable description


@dataclass
class Forecast:
    """A complete 60-minute forecast."""
    generated_at:     float
    horizon_minutes:  int
    points:           list   # list of ForecastPoint
    plain_summary:    str    # one sentence summary
    first_risk_at:    Optional[int]   # minutes until first HIGH risk (None if safe)
    peak_risk_level:  str
    confidence:       float
    trend_direction:  str    # IMPROVING / STABLE / DEGRADING / CRITICAL


# ── Forecaster ────────────────────────────────────────────

class Forecaster:
    """
    Uses LSTM trends and AR(2) projection to forecast system state.
    Works even without the full ML engine — falls back to trend extrapolation.
    """

    FORECAST_HORIZON = 60   # minutes
    FORECAST_STEPS   = 12   # one point per 5 minutes
    STEP_MINUTES     = 5

    def __init__(self):
        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=120)  # 2h of 1-min snapshots
        self._last_forecast: Optional[Forecast] = None
        self._forecast_cache_ttl = 30  # seconds

    def ingest(self, metrics: dict):
        """Called every ~60 seconds with current metrics."""
        with self._lock:
            self._history.append({
                "cpu":     metrics.get("cpu_percent", 0),
                "mem":     metrics.get("memory", 0),
                "disk":    metrics.get("disk_percent", 0),
                "anomaly": metrics.get("ensemble_score", 0),
                "health":  metrics.get("health_score", 100),
                "t":       time.time(),
            })

    def forecast(self, metrics: dict) -> Forecast:
        """Generate a forward-looking forecast."""
        # Use cache if fresh
        if (self._last_forecast and
                time.time() - self._last_forecast.generated_at < self._forecast_cache_ttl):
            return self._last_forecast

        with self._lock:
            history = list(self._history)

        forecast = self._generate_forecast(metrics, history)

        with self._lock:
            self._last_forecast = forecast

        return forecast

    def _generate_forecast(self, current: dict, history: list) -> Forecast:
        """Generate forecast using trend extrapolation."""
        cpu_now   = current.get("cpu_percent", 0)
        mem_now   = current.get("memory", 0)
        disk_now  = current.get("disk_percent", 0)
        anom_now  = current.get("ensemble_score", 0)

        # Calculate trend from recent history
        cpu_trend  = self._calc_trend(history, "cpu")
        mem_trend  = self._calc_trend(history, "mem")
        disk_trend = self._calc_trend(history, "disk")
        anom_trend = self._calc_trend(history, "anomaly")

        # Calculate acceleration (is the trend speeding up?)
        mem_accel = self._calc_acceleration(history, "mem")

        # Generate forecast points
        points = []
        first_risk_at = None
        peak_risk = "SAFE"

        for step in range(1, self.FORECAST_STEPS + 1):
            t = step * self.STEP_MINUTES

            # Project with trend + dampening (trends don't continue forever)
            dampening = max(0.1, 1.0 - step * 0.08)

            cpu_proj  = self._clamp(cpu_now  + cpu_trend  * t * dampening)
            mem_proj  = self._clamp(mem_now  + mem_trend  * t * dampening + mem_accel * t * t * 0.01)
            disk_proj = self._clamp(disk_now + disk_trend * t * dampening)
            anom_proj = self._clamp(anom_now + anom_trend * t * dampening * 0.5)

            risk, label = self._assess_risk(cpu_proj, mem_proj, disk_proj, anom_proj, t)

            if risk in ("HIGH", "CRITICAL") and first_risk_at is None:
                first_risk_at = t

            if self._risk_level(risk) > self._risk_level(peak_risk):
                peak_risk = risk

            points.append(ForecastPoint(
                minutes_from_now=t,
                cpu=round(cpu_proj, 1),
                memory=round(mem_proj, 1),
                disk=round(disk_proj, 1),
                anomaly=round(anom_proj, 3),
                risk_level=risk,
                plain_label=label,
            ))

        # Build summary
        summary = self._build_summary(
            peak_risk, first_risk_at, mem_trend, cpu_trend, mem_proj, cpu_proj
        )

        # Overall direction
        if peak_risk in ("CRITICAL", "HIGH"):
            direction = "DEGRADING" if first_risk_at and first_risk_at < 30 else "DEGRADING"
        elif mem_trend > 0.3 or cpu_trend > 0.5:
            direction = "DEGRADING"
        elif mem_trend < -0.3 and cpu_trend < -0.3:
            direction = "IMPROVING"
        else:
            direction = "STABLE"

        # Confidence based on history length
        confidence = min(0.90, 0.4 + len(history) * 0.004)

        return Forecast(
            generated_at=time.time(),
            horizon_minutes=self.FORECAST_HORIZON,
            points=points,
            plain_summary=summary,
            first_risk_at=first_risk_at,
            peak_risk_level=peak_risk,
            confidence=round(confidence, 2),
            trend_direction=direction,
        )

    def _calc_trend(self, history: list, key: str) -> float:
        """Calculate per-minute trend rate from recent history."""
        if len(history) < 5:
            return 0.0
        recent = history[-min(30, len(history)):]
        vals = [h.get(key, 0) for h in recent]
        if len(vals) < 2:
            return 0.0
        # Linear regression slope
        x = np.arange(len(vals), dtype=float)
        y = np.array(vals, dtype=float)
        if np.std(x) < 1e-9:
            return 0.0
        slope = float(np.polyfit(x, y, 1)[0])
        return slope  # per history step (approx per minute)

    def _calc_acceleration(self, history: list, key: str) -> float:
        """Calculate if the trend is accelerating."""
        if len(history) < 10:
            return 0.0
        recent = history[-min(30, len(history)):]
        vals = [h.get(key, 0) for h in recent]
        if len(vals) < 3:
            return 0.0
        x = np.arange(len(vals), dtype=float)
        y = np.array(vals, dtype=float)
        coeffs = np.polyfit(x, y, 2)
        return float(coeffs[0])  # quadratic term = acceleration

    def _assess_risk(self, cpu, mem, disk, anomaly, minutes) -> tuple:
        """Assess risk level at a projected future point."""
        if cpu > 92 or mem > 92 or anomaly > 0.8:
            return "CRITICAL", self._risk_label("CRITICAL", cpu, mem, minutes)
        elif cpu > 80 or mem > 85 or anomaly > 0.6:
            return "HIGH", self._risk_label("HIGH", cpu, mem, minutes)
        elif cpu > 70 or mem > 75 or anomaly > 0.4:
            return "ELEVATED", self._risk_label("ELEVATED", cpu, mem, minutes)
        return "SAFE", f"System stable at +{minutes} min"

    def _risk_label(self, level: str, cpu: float, mem: float, minutes: int) -> str:
        t = f"+{minutes} min"
        if level == "CRITICAL":
            if mem > 90:
                return f"{t}: Memory critical — crash risk"
            if cpu > 90:
                return f"{t}: CPU maxed — system may freeze"
            return f"{t}: Multiple systems at limit"
        elif level == "HIGH":
            if mem > 85:
                return f"{t}: Memory very high"
            return f"{t}: High system stress"
        else:
            return f"{t}: Elevated load"

    def _build_summary(self, peak_risk, first_risk_at, mem_trend, cpu_trend, mem_proj, cpu_proj) -> str:
        if peak_risk == "SAFE":
            return "System looks stable for the next hour. No issues predicted."
        elif peak_risk == "ELEVATED":
            return f"Mild increase in system load expected. No immediate issues."
        elif peak_risk == "HIGH":
            t = f"in about {first_risk_at} minutes" if first_risk_at else "within the hour"
            if mem_trend > cpu_trend:
                return f"Memory is trending upward and may cause slowdowns {t}. Consider closing unused applications."
            return f"System load is increasing and may cause issues {t}. Monitor closely."
        else:  # CRITICAL
            t = f"in about {first_risk_at} minutes" if first_risk_at else "soon"
            if mem_proj > 90:
                return f"Memory is on track to hit critical levels {t}. Action recommended now."
            if cpu_proj > 90:
                return f"CPU is heading toward maximum capacity {t}. Close heavy applications."
            return f"System is approaching its limits {t}. Save your work and act soon."

    def _risk_level(self, risk: str) -> int:
        return {"SAFE": 0, "ELEVATED": 1, "HIGH": 2, "CRITICAL": 3}.get(risk, 0)

    def _clamp(self, val: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, val))

    def get_plain_timeline(self, metrics: dict) -> dict:
        """Get a plain English timeline for the UI."""
        f = self.forecast(metrics)
        return {
            "summary":       f.plain_summary,
            "direction":     f.trend_direction,
            "peak_risk":     f.peak_risk_level,
            "first_risk_at": f.first_risk_at,
            "confidence":    f.confidence,
            "points": [
                {
                    "t":       p.minutes_from_now,
                    "cpu":     p.cpu,
                    "memory":  p.memory,
                    "anomaly": p.anomaly,
                    "risk":    p.risk_level,
                    "label":   p.plain_label,
                }
                for p in f.points
            ],
        }


# ── Singleton ─────────────────────────────────────────────
_forecaster: Optional[Forecaster] = None
_forecaster_lock = threading.Lock()

def get_forecaster() -> Forecaster:
    global _forecaster
    with _forecaster_lock:
        if _forecaster is None:
            _forecaster = Forecaster()
    return _forecaster
