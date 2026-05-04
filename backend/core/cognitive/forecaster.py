"""
CVIS Forecaster
===============
Projects current metric trends forward in time using the LSTM model.
Shows users what will happen in the next 60 minutes, not just what's
happening now.

Plain English output — no ML jargon.
Includes: Trust layer, confidence labels, anomaly explainability context.
"""
import time
import threading
from dataclasses import dataclass, field
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
    risk_level:       str    # SAFE / ELEVATED / HIGH / CRITICAL
    plain_label:      str    # human-readable description
    explanation:      str    # WHY this risk level — what's driving it


@dataclass
class TrendInsight:
    """Plain-English description of a single metric trend."""
    metric:    str   # "CPU", "Memory", etc.
    direction: str   # "rising", "falling", "stable"
    rate:      str   # "quickly", "slowly", "steadily"
    concern:   bool  # True if this trend is worrying
    detail:    str   # full sentence e.g. "Memory is rising steadily at ~1.2%/min"


@dataclass
class Forecast:
    """A complete 60-minute forecast."""
    generated_at:      float
    horizon_minutes:   int
    points:            list              # list of ForecastPoint
    plain_summary:     str              # one sentence summary
    first_risk_at:     Optional[int]    # minutes until first HIGH risk (None if safe)
    peak_risk_level:   str
    confidence:        float
    confidence_label:  str              # NEW: human label e.g. "High — 90 min of data"
    trend_direction:   str              # IMPROVING / STABLE / DEGRADING / CRITICAL
    trustworthy:       bool             # NEW: False if < 5 min of data
    trend_insights:    list             # NEW: list of TrendInsight dicts
    what_to_watch:     list             # NEW: top 2 things user should monitor
    data_age_minutes:  int              # NEW: how many minutes of history used


# ── Forecaster ────────────────────────────────────────────

class Forecaster:
    """
    Uses trend extrapolation (AR + quadratic) to forecast system state.
    Works even without the full ML engine.
    Augmented with plain-English explanations for every forecast point.
    """

    FORECAST_HORIZON = 60
    FORECAST_STEPS   = 12   # one point per 5 minutes
    STEP_MINUTES     = 5
    MIN_HISTORY      = 5    # minimum snapshots before trusting forecast

    def __init__(self):
        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=120)
        self._last_forecast: Optional[Forecast] = None
        self._forecast_cache_ttl = 30  # seconds

    def ingest(self, metrics: dict):
        """Called every ~60 seconds with current metrics."""
        with self._lock:
            self._history.append({
                "cpu":     metrics.get("cpu_percent",   0),
                "mem":     metrics.get("memory",        0),
                "disk":    metrics.get("disk_percent",  0),
                "anomaly": metrics.get("ensemble_score",0),
                "health":  metrics.get("health_score",  100),
                "t":       time.time(),
            })

    def forecast(self, metrics: dict) -> Forecast:
        """Generate a forward-looking forecast."""
        if (self._last_forecast and
                time.time() - self._last_forecast.generated_at < self._forecast_cache_ttl):
            return self._last_forecast

        history_len = len(self._history)

        if history_len < self.MIN_HISTORY:
            remaining = self.MIN_HISTORY - history_len
            return Forecast(
                generated_at=time.time(), horizon_minutes=60,
                points=[], trend_insights=[], what_to_watch=[],
                plain_summary=(
                    f"Not enough data yet — forecast available after "
                    f"{remaining} more minute(s) of monitoring."
                ),
                first_risk_at=None, peak_risk_level="UNKNOWN",
                confidence=0.0,
                confidence_label=f"Too early — {history_len}/{self.MIN_HISTORY} snapshots collected",
                trend_direction="UNKNOWN",
                trustworthy=False,
                data_age_minutes=history_len,
            )

        with self._lock:
            history = list(self._history)

        result = self._generate_forecast(metrics, history)

        with self._lock:
            self._last_forecast = result

        return result

    # ------------------------------------------------------------------
    # Core forecast generation
    # ------------------------------------------------------------------

    def _generate_forecast(self, current: dict, history: list) -> Forecast:
        cpu_now   = current.get("cpu_percent",    0)
        mem_now   = current.get("memory",         0)
        disk_now  = current.get("disk_percent",   0)
        anom_now  = current.get("ensemble_score", 0)

        # Trends (per history step ≈ per minute)
        cpu_trend  = self._calc_trend(history, "cpu")
        mem_trend  = self._calc_trend(history, "mem")
        disk_trend = self._calc_trend(history, "disk")
        anom_trend = self._calc_trend(history, "anomaly")

        # Acceleration
        mem_accel  = self._calc_acceleration(history, "mem")
        cpu_accel  = self._calc_acceleration(history, "cpu")

        # Build forecast points
        points = []
        first_risk_at = None
        peak_risk = "SAFE"
        mem_proj = mem_now
        cpu_proj = cpu_now

        for step in range(1, self.FORECAST_STEPS + 1):
            t = step * self.STEP_MINUTES
            dampening = max(0.1, 1.0 - step * 0.08)

            cpu_proj  = self._clamp(cpu_now  + cpu_trend  * t * dampening + cpu_accel  * t * t * 0.01)
            mem_proj  = self._clamp(mem_now  + mem_trend  * t * dampening + mem_accel  * t * t * 0.01)
            disk_proj = self._clamp(disk_now + disk_trend * t * dampening)
            anom_proj = self._clamp(anom_now + anom_trend * t * dampening * 0.5)

            risk, label = self._assess_risk(cpu_proj, mem_proj, disk_proj, anom_proj, t)
            explanation = self._explain_point(
                risk, cpu_proj, mem_proj, disk_proj, anom_proj,
                cpu_trend, mem_trend, disk_trend, t,
            )

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
                explanation=explanation,
            ))

        # Trend direction
        direction = self._calc_direction(peak_risk, mem_trend, cpu_trend, first_risk_at)

        # Confidence
        confidence, confidence_label = self._calc_confidence(history)

        # Trend insights
        trend_insights = self._build_trend_insights(
            cpu_trend, mem_trend, disk_trend, anom_trend,
            cpu_now, mem_now, disk_now, anom_now,
        )

        # What to watch
        what_to_watch = self._build_what_to_watch(
            peak_risk, mem_trend, cpu_trend, disk_trend, anom_trend,
            mem_proj, cpu_proj,
        )

        summary = self._build_summary(
            peak_risk, first_risk_at, mem_trend, cpu_trend, mem_proj, cpu_proj
        )

        return Forecast(
            generated_at=time.time(),
            horizon_minutes=self.FORECAST_HORIZON,
            points=points,
            plain_summary=summary,
            first_risk_at=first_risk_at,
            peak_risk_level=peak_risk,
            confidence=round(confidence, 2),
            confidence_label=confidence_label,
            trend_direction=direction,
            trustworthy=confidence >= 0.50,
            trend_insights=trend_insights,
            what_to_watch=what_to_watch,
            data_age_minutes=len(history),
        )

    # ------------------------------------------------------------------
    # NEW: Point-level explanation
    # ------------------------------------------------------------------

    def _explain_point(
        self,
        risk: str,
        cpu: float, mem: float, disk: float, anomaly: float,
        cpu_trend: float, mem_trend: float, disk_trend: float,
        minutes: int,
    ) -> str:
        """
        Return a plain-English sentence explaining WHY this point
        has this risk level — what metric is driving it.
        """
        if risk == "SAFE":
            return "All metrics within normal range."

        drivers = []

        if mem > 85:
            rate = "quickly" if mem_trend > 1.0 else "steadily"
            drivers.append(f"memory is projected at {mem:.0f}% (rising {rate})")
        elif mem > 75:
            drivers.append(f"memory is elevated at {mem:.0f}%")

        if cpu > 80:
            rate = "quickly" if cpu_trend > 1.0 else "steadily"
            drivers.append(f"CPU is projected at {cpu:.0f}% (rising {rate})")
        elif cpu > 70:
            drivers.append(f"CPU is elevated at {cpu:.0f}%")

        if anomaly > 0.6:
            drivers.append(f"anomaly score is {anomaly:.2f} — unusual behaviour detected")
        elif anomaly > 0.4:
            drivers.append(f"anomaly score is elevated at {anomaly:.2f}")

        if disk > 88:
            drivers.append(f"disk usage approaching limit at {disk:.0f}%")

        if not drivers:
            return f"Combined metric pressure puts this at {risk} risk."

        if len(drivers) == 1:
            return f"At +{minutes} min: {drivers[0].capitalize()}."
        elif len(drivers) == 2:
            return f"At +{minutes} min: {drivers[0].capitalize()} and {drivers[1]}."
        else:
            return f"At +{minutes} min: {', '.join(drivers[:-1])}, and {drivers[-1]}."

    # ------------------------------------------------------------------
    # NEW: Trend insights
    # ------------------------------------------------------------------

    def _build_trend_insights(
        self,
        cpu_trend: float, mem_trend: float, disk_trend: float, anom_trend: float,
        cpu_now: float, mem_now: float, disk_now: float, anom_now: float,
    ) -> list:
        """
        Return a list of TrendInsight dicts for the 4 main metrics.
        Only includes metrics that are non-trivially trending.
        """
        insights = []

        specs = [
            ("CPU",           cpu_trend,  cpu_now,  70, "cpu_percent"),
            ("Memory",        mem_trend,  mem_now,  75, "memory"),
            ("Disk",          disk_trend, disk_now, 85, "disk_percent"),
            ("Anomaly score", anom_trend, anom_now, 0.5, "anomaly"),
        ]

        for label, trend, current, warn_threshold, _ in specs:
            unit = "" if label == "Anomaly score" else "%"

            if abs(trend) < 0.05:
                direction = "stable"
                rate      = ""
                concern   = current > warn_threshold
                detail    = (
                    f"{label} is stable at {current:.1f}{unit}."
                    if not concern
                    else f"{label} is stable but already elevated at {current:.1f}{unit}."
                )
            elif trend > 0:
                direction = "rising"
                rate      = "quickly" if abs(trend) > 0.8 else "steadily" if abs(trend) > 0.3 else "slowly"
                concern   = trend > 0.3 or current > warn_threshold
                detail    = (
                    f"{label} is rising {rate} — currently {current:.1f}{unit}, "
                    f"~{abs(trend):.2f}{unit}/min."
                )
            else:
                direction = "falling"
                rate      = "quickly" if abs(trend) > 0.8 else "steadily" if abs(trend) > 0.3 else "slowly"
                concern   = False
                detail    = (
                    f"{label} is falling {rate} — currently {current:.1f}{unit}. "
                    f"Pressure is easing."
                )

            insights.append({
                "metric":    label,
                "direction": direction,
                "rate":      rate,
                "concern":   concern,
                "detail":    detail,
            })

        return insights

    # ------------------------------------------------------------------
    # NEW: What to watch
    # ------------------------------------------------------------------

    def _build_what_to_watch(
        self,
        peak_risk: str,
        mem_trend: float, cpu_trend: float, disk_trend: float, anom_trend: float,
        mem_proj: float, cpu_proj: float,
    ) -> list:
        """
        Return up to 2 plain-English things the user should monitor.
        Ordered by urgency.
        """
        items = []

        if mem_trend > 0.5 or mem_proj > 80:
            items.append(
                f"RAM usage — currently trending up ~{mem_trend:.1f}%/min. "
                "Close unused browser tabs or apps if it crosses 85%."
            )

        if cpu_trend > 0.5 or cpu_proj > 75:
            items.append(
                f"CPU load — rising ~{cpu_trend:.1f}%/min. "
                "Check for runaway processes if it stays above 80%."
            )

        if disk_trend > 0.2:
            items.append(
                "Disk usage is slowly growing. "
                "Check for large log files or temporary data accumulating."
            )

        if anom_trend > 0.02:
            items.append(
                "Anomaly score is rising — the ML model is detecting unusual patterns. "
                "Monitor for unexpected process activity."
            )

        if not items:
            items.append("No specific concerns — system is behaving normally.")

        return items[:2]

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _calc_confidence(self, history: list) -> tuple:
        n = len(history)
        confidence = min(0.90, 0.4 + n * 0.004)

        if n >= 90:
            label = f"High — {n} min of history"
        elif n >= 30:
            label = f"Moderate — {n} min of history"
        elif n >= 10:
            label = f"Low — still learning ({n} min so far)"
        else:
            label = f"Very low — only {n} data points"

        return confidence, label

    # ------------------------------------------------------------------
    # Trend direction
    # ------------------------------------------------------------------

    def _calc_direction(
        self, peak_risk: str, mem_trend: float, cpu_trend: float, first_risk_at: Optional[int]
    ) -> str:
        if peak_risk in ("CRITICAL", "HIGH"):
            return "DEGRADING"
        if mem_trend > 0.3 or cpu_trend > 0.5:
            return "DEGRADING"
        if mem_trend < -0.3 and cpu_trend < -0.3:
            return "IMPROVING"
        return "STABLE"

    # ------------------------------------------------------------------
    # Existing helpers (unchanged)
    # ------------------------------------------------------------------

    def _calc_trend(self, history: list, key: str) -> float:
        if len(history) < 5:
            return 0.0
        recent = history[-min(30, len(history)):]
        vals = [h.get(key, 0) for h in recent]
        if len(vals) < 2:
            return 0.0
        x = np.arange(len(vals), dtype=float)
        y = np.array(vals, dtype=float)
        if np.std(x) < 1e-9:
            return 0.0
        return float(np.polyfit(x, y, 1)[0])

    def _calc_acceleration(self, history: list, key: str) -> float:
        if len(history) < 10:
            return 0.0
        recent = history[-min(30, len(history)):]
        vals = [h.get(key, 0) for h in recent]
        if len(vals) < 3:
            return 0.0
        x = np.arange(len(vals), dtype=float)
        y = np.array(vals, dtype=float)
        return float(np.polyfit(x, y, 2)[0])

    def _assess_risk(self, cpu, mem, disk, anomaly, minutes) -> tuple:
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
            if mem > 90:   return f"{t}: Memory critical — crash risk"
            if cpu > 90:   return f"{t}: CPU maxed — system may freeze"
            return f"{t}: Multiple systems at limit"
        elif level == "HIGH":
            if mem > 85:   return f"{t}: Memory very high"
            return f"{t}: High system stress"
        return f"{t}: Elevated load"

    def _build_summary(self, peak_risk, first_risk_at, mem_trend, cpu_trend, mem_proj, cpu_proj) -> str:
        if peak_risk == "SAFE":
            return "System looks stable for the next hour. No issues predicted."
        elif peak_risk == "ELEVATED":
            return "Mild increase in system load expected. No immediate issues."
        elif peak_risk == "HIGH":
            t = f"in about {first_risk_at} minutes" if first_risk_at else "within the hour"
            if mem_trend > cpu_trend:
                return (f"Memory is trending upward and may cause slowdowns {t}. "
                        "Consider closing unused applications.")
            return f"System load is increasing and may cause issues {t}. Monitor closely."
        else:
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
        """Get a plain-English timeline for the UI and /cognitive/forecast endpoint."""
        f = self.forecast(metrics)
        return {
            "summary":          f.plain_summary,
            "direction":        f.trend_direction,
            "peak_risk":        f.peak_risk_level,
            "first_risk_at":    f.first_risk_at,
            "confidence":       f.confidence,
            "confidence_label": f.confidence_label,          # NEW
            "trustworthy":      f.trustworthy,               # NEW
            "trend_insights":   f.trend_insights,            # NEW
            "what_to_watch":    f.what_to_watch,             # NEW
            "data_age_minutes": f.data_age_minutes,          # NEW
            "points": [
                {
                    "t":           p.minutes_from_now,
                    "cpu":         p.cpu,
                    "memory":      p.memory,
                    "anomaly":     p.anomaly,
                    "risk":        p.risk_level,
                    "label":       p.plain_label,
                    "explanation": p.explanation,             # NEW
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
