"""
CVIS Silent Degradation Detector
Detects long-term chronic drift in system metrics using linear regression
over 30-day daily-average windows. Finds slow death before it's visible.
"""
import time, threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

_lock = threading.Lock()
_instance = None

# ── Thresholds ────────────────────────────────────────────────────────────────
CRITICAL_THRESHOLDS = {
    "cpu_percent":  90.0,
    "memory":       90.0,
    "health_score": 200.0,   # health degrades downward
}

# Minimum slope (per day) to be considered degrading — filters noise
MIN_SLOPE = {
    "cpu_percent":  0.15,   # 0.15% CPU per day
    "memory":       0.10,   # 0.10% memory per day
    "health_score": -1.0,   # -1 point per day (negative = degrading)
}

# Number of daily buckets required before reporting
MIN_DAYS = 7


@dataclass
class MetricDegradation:
    metric:           str
    label:            str
    current_value:    float
    baseline_value:   float          # value 30 days ago (projected)
    slope_per_day:    float          # change per day (positive = rising)
    degrading:        bool
    days_degrading:   int            # how long the trend has held
    days_to_critical: Optional[int]  # None if not on track to critical
    projected_at:     Optional[str]  # human date string
    severity:         str            # LOW / MEDIUM / HIGH / CRITICAL
    description:      str


@dataclass
class DegradationReport:
    generated_at:     float
    is_degrading:     bool
    degrading_since:  Optional[str]   # human date of onset
    summary:          str
    overall_severity: str
    metrics:          list[MetricDegradation] = field(default_factory=list)
    recommendation:   str = ""


def _human_date(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%b %d")


def _days_from_now(days: int) -> str:
    import datetime
    d = datetime.datetime.now() + datetime.timedelta(days=days)
    return d.strftime("%b %d, %Y")


class DegradationDetector:
    """
    Maintains a rolling 30-day buffer of hourly snapshots,
    aggregated into daily averages for trend analysis.
    """

    def __init__(self):
        # hourly_buckets[metric][day_key] = list of values
        self._hourly: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        # daily_avgs[metric] = [(timestamp, avg_value), ...]  last 30 days
        self._daily: dict[str, list[tuple]] = defaultdict(list)
        self._last_report: Optional[DegradationReport] = None
        self._last_bucket_flush: float = 0.0
        self._FLUSH_INTERVAL = 3600   # flush hourly buckets → daily every hour

    def ingest(self, metrics: dict):
        """Call this every poll cycle with current metrics."""
        now = time.time()
        import datetime
        day_key = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d")

        for metric in ("cpu_percent", "memory", "health_score"):
            val = metrics.get(metric)
            if val is not None:
                self._hourly[metric][day_key].append(float(val))

        # Flush hourly buckets to daily averages once per hour
        if now - self._last_bucket_flush > self._FLUSH_INTERVAL:
            self._flush_to_daily()
            self._last_bucket_flush = now

    def _flush_to_daily(self):
        """Aggregate today's hourly readings into a daily average."""
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        now   = time.time()

        for metric, days in self._hourly.items():
            for day_key, values in list(days.items()):
                if not values:
                    continue
                avg = float(np.mean(values))
                # Parse day_key to timestamp (midnight of that day)
                try:
                    dt = datetime.datetime.strptime(day_key, "%Y-%m-%d")
                    ts = dt.timestamp()
                except Exception:
                    ts = now

                # Update or append daily entry
                existing = [i for i, (t, _) in enumerate(self._daily[metric])
                            if abs(t - ts) < 86400]
                if existing:
                    self._daily[metric][existing[0]] = (ts, avg)
                else:
                    self._daily[metric].append((ts, avg))

            # Keep only last 35 days
            self._daily[metric] = sorted(self._daily[metric], key=lambda x: x[0])[-35:]

    def _analyse_metric(self, metric: str, label: str) -> Optional[MetricDegradation]:
        points = self._daily.get(metric, [])
        if len(points) < MIN_DAYS:
            return None

        xs = np.array([p[0] for p in points], dtype=np.float64)
        ys = np.array([p[1] for p in points], dtype=np.float64)

        # Normalise x to days from first point
        xs_days = (xs - xs[0]) / 86400.0

        # Linear regression
        coeffs = np.polyfit(xs_days, ys, 1)
        slope   = float(coeffs[0])   # units per day
        intercept = float(coeffs[1])

        current   = float(ys[-1])
        baseline  = float(intercept)  # projected value at day 0

        days_span = float(xs_days[-1])

        # Is this metric degrading?
        is_health = metric == "health_score"
        min_slope = MIN_SLOPE[metric]

        if is_health:
            degrading = slope < min_slope   # health should not fall
        else:
            degrading = slope > abs(min_slope)  # cpu/mem should not rise

        if not degrading:
            severity = "LOW"
            days_to_critical = None
            projected_at = None
        else:
            # How many days until critical threshold?
            critical = CRITICAL_THRESHOLDS[metric]
            if is_health:
                # health falling — days until it hits critical floor
                if slope < 0 and current > critical:
                    days_to_critical = int((critical - current) / slope)
                else:
                    days_to_critical = None
            else:
                # cpu/mem rising — days until it hits critical ceiling
                if slope > 0 and current < critical:
                    days_to_critical = int((critical - current) / slope)
                else:
                    days_to_critical = None

            if days_to_critical is not None and days_to_critical > 0:
                projected_at = _days_from_now(days_to_critical)
            else:
                projected_at = None

            if days_to_critical is None or days_to_critical > 90:
                severity = "LOW"
            elif days_to_critical > 30:
                severity = "MEDIUM"
            elif days_to_critical > 14:
                severity = "HIGH"
            else:
                severity = "CRITICAL"

        # Description
        rate_str = f"{abs(slope):.2f}/day"
        if degrading:
            if is_health:
                desc = f"Falling {rate_str} — down {abs(current - baseline):.1f} pts from baseline"
            else:
                desc = f"Rising {rate_str} — up {abs(current - baseline):.1f}% from baseline"
        else:
            desc = "Stable — no significant long-term drift"

        # Estimate days_degrading from regression onset
        if degrading and days_span > 0:
            # Find approximate day where trend began exceeding noise
            days_degrading = max(1, int(days_span * 0.7))
        else:
            days_degrading = 0

        return MetricDegradation(
            metric=metric,
            label=label,
            current_value=round(current, 1),
            baseline_value=round(baseline, 1),
            slope_per_day=round(slope, 3),
            degrading=degrading,
            days_degrading=days_degrading,
            days_to_critical=days_to_critical,
            projected_at=projected_at,
            severity=severity,
            description=desc,
        )

    def get_report(self) -> DegradationReport:
        with _lock:
            labels = {
                "cpu_percent":  "CPU usage",
                "memory":       "Memory usage",
                "health_score": "Health score",
            }
            results = []
            for metric, label in labels.items():
                r = self._analyse_metric(metric, label)
                if r:
                    results.append(r)

            degrading = [r for r in results if r.degrading]
            overall   = "LOW"
            if degrading:
                severities = [r.severity for r in degrading]
                for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    if s in severities:
                        overall = s
                        break

            # Find earliest degradation onset
            max_days = max((r.days_degrading for r in degrading), default=0)
            if max_days > 0:
                import datetime
                onset_ts = time.time() - max_days * 86400
                degrading_since = _human_date(onset_ts)
            else:
                degrading_since = None

            # Summary
            if not degrading:
                summary = "No long-term degradation detected. All metrics are stable over the last 30 days."
                rec = "Continue monitoring. No action needed."
            else:
                worst = max(degrading, key=lambda r: ["LOW","MEDIUM","HIGH","CRITICAL"].index(r.severity))
                eta   = f" Projected critical in {worst.days_to_critical} days." if worst.days_to_critical else ""
                summary = f"{len(degrading)} metric{'s' if len(degrading)>1 else ''} showing chronic drift for ~{max_days} days.{eta}"
                rec = (
                    "Investigate recently added processes or background jobs. "
                    "Check for memory leaks, cron jobs, or services added in the last month."
                )

            report = DegradationReport(
                generated_at=time.time(),
                is_degrading=bool(degrading),
                degrading_since=degrading_since,
                summary=summary,
                overall_severity=overall,
                metrics=results,
                recommendation=rec,
            )
            self._last_report = report
            return report

    def get_report_dict(self) -> dict:
        r = self.get_report()
        return {
            "generated_at":     r.generated_at,
            "is_degrading":     r.is_degrading,
            "degrading_since":  r.degrading_since,
            "summary":          r.summary,
            "overall_severity": r.overall_severity,
            "recommendation":   r.recommendation,
            "metrics": [
                {
                    "metric":           m.metric,
                    "label":            m.label,
                    "current_value":    m.current_value,
                    "baseline_value":   m.baseline_value,
                    "slope_per_day":    m.slope_per_day,
                    "degrading":        m.degrading,
                    "days_degrading":   m.days_degrading,
                    "days_to_critical": m.days_to_critical,
                    "projected_at":     m.projected_at,
                    "severity":         m.severity,
                    "description":      m.description,
                }
                for m in r.metrics
            ],
            "has_data": len(r.metrics) > 0,
            "days_of_data": len(self._daily.get("cpu_percent", [])),
        }


def get_degradation_detector() -> DegradationDetector:
    global _instance
    if _instance is None:
        _instance = DegradationDetector()
    return _instance
