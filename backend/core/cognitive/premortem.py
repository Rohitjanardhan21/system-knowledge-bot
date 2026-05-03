"""
CVIS Failure Pre-Mortem Engine
===============================
"What will kill this machine — and when."

Unlike post-mortems (what happened) or predictions (next 60 min),
the pre-mortem looks weeks ahead using trend analysis and asks:
"If nothing changes, what kills this machine first?"

Usage:
    python3 premortem.py --server http://localhost:8000
    python3 premortem.py --server http://localhost:8000 --json
    
API endpoint: GET /cognitive/premortem
"""

import time
import threading
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import urllib.request
import json as _json


# ── Data structures ───────────────────────────────────────

@dataclass
class ThreatFinding:
    """A single threat — one thing that will kill the machine."""
    threat_id:        str
    failure_type:     str          # OOM, DISK_FULL, THERMAL, CRASH
    probability:      float        # 0-1
    days_until:       Optional[float]  # None = unknown
    confidence:       str          # high / medium / low
    headline:         str          # one sentence, plain English
    evidence:         list         # list of plain English evidence strings
    recommendation:   str          # what to do RIGHT NOW
    data_points:      int          # how many samples this is based on
    trend_per_day:    float        # rate of change per day


@dataclass 
class PreMortem:
    """Complete pre-mortem report."""
    generated_at:     float
    horizon_days:     int          # how far ahead we looked
    threats:          list         # list of ThreatFinding, sorted by urgency
    top_threat:       Optional[ThreatFinding]
    safe:             bool         # True if no threats found
    plain_summary:    str
    data_quality:     str          # how much data this is based on
    snapshot_count:   int


# ── Pre-Mortem Engine ─────────────────────────────────────

class PreMortemEngine:
    """
    Analyses metric trends and DNA patterns to predict
    what will kill this machine in the next 30 days.
    
    Three analysis layers:
    1. Trend extrapolation — if CPU grows 0.5%/day, when does it hit 90%?
    2. DNA pattern velocity — how fast are failure patterns accumulating?
    3. Resource exhaustion — disk/memory growth rate to full
    """

    HORIZON_DAYS    = 30      # look 30 days ahead
    MIN_SNAPSHOTS   = 50      # need at least 50 data points for meaningful trends
    CACHE_TTL       = 300     # cache pre-mortem for 5 minutes

    def __init__(self):
        self._lock          = threading.Lock()
        self._history       = deque(maxlen=8640)   # 24h at 10s intervals
        self._last_premortem: Optional[PreMortem] = None
        self._last_run      = 0.0

    def ingest(self, metrics: dict):
        """Feed live metrics into the engine."""
        with self._lock:
            self._history.append({
                "cpu":     metrics.get("cpu_percent", 0),
                "mem":     metrics.get("memory", 0),
                "disk":    metrics.get("disk_percent", 0),
                "net":     metrics.get("network_percent", 0),
                "anomaly": metrics.get("ensemble_score", 0),
                "t":       time.time(),
            })

    def run(self, dna_summary: dict = None) -> PreMortem:
        """
        Run the pre-mortem analysis.
        Returns cached result if run recently.
        """
        now = time.time()
        if self._last_premortem and (now - self._last_run) < self.CACHE_TTL:
            return self._last_premortem

        with self._lock:
            history = list(self._history)

        n = len(history)

        # Not enough data
        if n < self.MIN_SNAPSHOTS:
            result = PreMortem(
                generated_at=now,
                horizon_days=self.HORIZON_DAYS,
                threats=[],
                top_threat=None,
                safe=True,
                plain_summary=f"Pre-mortem needs more data — {n}/{self.MIN_SNAPSHOTS} snapshots collected. Check back in {max(1, (self.MIN_SNAPSHOTS - n) // 6)} minutes.",
                data_quality=f"insufficient ({n} snapshots)",
                snapshot_count=n,
            )
            self._last_premortem = result
            self._last_run = now
            return result

        threats = []

        # ── Analysis 1: Resource Exhaustion ──
        threats += self._analyse_resource_exhaustion(history)

        # ── Analysis 2: Trend Degradation ──
        threats += self._analyse_trend_degradation(history)

        # ── Analysis 3: DNA Pattern Velocity ──
        if dna_summary:
            threats += self._analyse_dna_velocity(dna_summary, history)

        # ── Analysis 4: Anomaly Trend ──
        threats += self._analyse_anomaly_trend(history)

        # Sort by urgency: lowest days_until first, then highest probability
        def urgency_key(t):
            days = t.days_until if t.days_until is not None else 999
            return (days, -t.probability)

        threats = sorted(threats, key=urgency_key)

        # Remove duplicates — keep highest priority per failure type
        seen_types = set()
        deduped = []
        for t in threats:
            if t.failure_type not in seen_types:
                seen_types.add(t.failure_type)
                deduped.append(t)

        top = deduped[0] if deduped else None
        safe = len(deduped) == 0 or all(t.probability < 0.25 for t in deduped)

        # Data quality label
        if n >= 2000:   dq = f"high ({n:,} snapshots — {n//360:.0f}h of data)"
        elif n >= 500:  dq = f"medium ({n} snapshots)"
        else:           dq = f"low ({n} snapshots — trends may shift)"

        summary = self._build_summary(deduped, safe)

        result = PreMortem(
            generated_at=now,
            horizon_days=self.HORIZON_DAYS,
            threats=deduped[:5],   # top 5 threats max
            top_threat=top,
            safe=safe,
            plain_summary=summary,
            data_quality=dq,
            snapshot_count=n,
        )

        self._last_premortem = result
        self._last_run = now
        return result

    # ── Analysis methods ──────────────────────────────────

    def _analyse_resource_exhaustion(self, history: list) -> list:
        """
        If disk/memory is growing at a steady rate,
        calculate when it hits 95% (critical threshold).
        """
        threats = []
        metrics = ["disk", "mem"]
        labels  = {"disk": "DISK_FULL", "mem": "OOM"}
        names   = {"disk": "Disk space", "mem": "Memory"}
        units   = {"disk": "%", "mem": "%"}

        # Use last 24h of data for trend
        cutoff = time.time() - 86400
        recent = [s for s in history if s.get("t", 0) > cutoff]
        if len(recent) < 20:
            recent = history  # fall back to all data

        for metric in metrics:
            vals = [s[metric] for s in recent if metric in s]
            if len(vals) < 20:
                continue

            current = vals[-1]
            mean    = statistics.mean(vals)

            # Linear regression to find trend per hour
            n = len(vals)
            x_mean = n / 2
            xy_sum = sum(i * v for i, v in enumerate(vals))
            x2_sum = sum(i * i for i in range(n))
            slope_per_sample = (xy_sum - n * x_mean * mean) / max(1, x2_sum - n * x_mean ** 2)

            # Convert slope to per-day (assuming ~360 samples/hour at 10s intervals)
            samples_per_day = len(vals) / max(1, (recent[-1].get("t", 0) - recent[0].get("t", 1)) / 86400)
            slope_per_day = slope_per_sample * samples_per_day

            # Only flag if growing meaningfully
            if slope_per_day < 0.1:
                continue

            # Days until 95%
            headroom   = 95.0 - current
            days_until = headroom / slope_per_day if slope_per_day > 0 else None

            if days_until is None or days_until > self.HORIZON_DAYS * 2:
                continue

            # Probability based on trend strength and days_until
            if days_until <= 7:     prob = 0.90
            elif days_until <= 14:  prob = 0.75
            elif days_until <= 30:  prob = 0.55
            else:                   prob = 0.30

            # Confidence based on data quality
            if len(vals) >= 500:   conf = "high"
            elif len(vals) >= 100: conf = "medium"
            else:                  conf = "low"

            # Build evidence
            evidence = [
                f"Current {names[metric].lower()}: {current:.1f}%",
                f"Growing at ~{slope_per_day:.2f}% per day",
                f"At this rate, hits 95% in ~{days_until:.0f} days",
            ]
            if slope_per_day > 1.0:
                evidence.append(f"⚠ Growth rate is high — {slope_per_day:.1f}% per day")

            # Recommendation
            recs = {
                "disk": "Run 'docker system prune -af' and check log rotation. Consider expanding disk.",
                "mem":  "Identify memory-leaking processes. Consider adding RAM or restarting heavy services weekly.",
            }

            days_str = f"~{days_until:.0f} days" if days_until else "unknown"
            headline = f"{names[metric]} will be exhausted in {days_str} at current growth rate"

            threats.append(ThreatFinding(
                threat_id=f"exhaustion_{metric}",
                failure_type=labels[metric],
                probability=prob,
                days_until=days_until,
                confidence=conf,
                headline=headline,
                evidence=evidence,
                recommendation=recs[metric],
                data_points=len(vals),
                trend_per_day=slope_per_day,
            ))

        return threats

    def _analyse_trend_degradation(self, history: list) -> list:
        """
        Detect if CPU or memory is trending toward dangerous levels
        even if not near exhaustion.
        """
        threats = []

        # Look at last 6 hours vs previous 6 hours
        now     = time.time()
        recent  = [s for s in history if s.get("t", 0) > now - 21600]
        older   = [s for s in history if now - 43200 < s.get("t", 0) <= now - 21600]

        if len(recent) < 10 or len(older) < 10:
            return threats

        for metric, label, name, threshold in [
            ("cpu",  "CPU_STRESS", "CPU",    85.0),
            ("mem",  "OOM",        "Memory", 88.0),
        ]:
            recent_mean = statistics.mean(s[metric] for s in recent if metric in s)
            older_mean  = statistics.mean(s[metric] for s in older  if metric in s)
            delta       = recent_mean - older_mean

            # Only flag if trending up meaningfully AND above 60%
            if delta < 3.0 or recent_mean < 60:
                continue

            # Extrapolate: if it keeps trending at this rate
            # delta is over 6 hours, so per day = delta * 4
            per_day   = delta * 4
            headroom  = threshold - recent_mean
            days_until = headroom / per_day if per_day > 0 else None

            if days_until and days_until > self.HORIZON_DAYS:
                continue

            prob = 0.65 if days_until and days_until <= 14 else 0.45

            evidence = [
                f"{name} averaged {recent_mean:.1f}% in last 6 hours",
                f"Up from {older_mean:.1f}% in previous 6 hours (+{delta:.1f}%)",
                f"Trending toward {threshold}% threshold",
            ]
            if days_until:
                evidence.append(f"Projected to hit {threshold}% in ~{days_until:.0f} days if trend continues")

            days_str = f"~{days_until:.0f} days" if days_until else "soon"
            threats.append(ThreatFinding(
                threat_id=f"trend_{metric}",
                failure_type=label,
                probability=prob,
                days_until=days_until,
                confidence="medium",
                headline=f"{name} is trending upward and may cause issues in {days_str}",
                evidence=evidence,
                recommendation=f"Investigate what changed in the last 6 hours. Check for new processes or scheduled jobs.",
                data_points=len(recent) + len(older),
                trend_per_day=per_day,
            ))

        return threats

    def _analyse_dna_velocity(self, dna: dict, history: list) -> list:
        """
        If failure patterns are accumulating fast,
        the machine is heading toward a bad state.
        """
        threats = []
        pattern_list = dna.get("pattern_list", [])
        total        = dna.get("total_failures", 0)

        # Find patterns with high seen count and low prevention rate
        for p in pattern_list:
            seen      = p.get("seen", 0)
            prevented = p.get("prevented", 0)
            ftype     = p.get("type", "UNKNOWN")
            accuracy  = p.get("accuracy", 0)

            # Only flag if pattern is real and not being prevented
            if seen < 5 or accuracy < 70:
                continue

            prevention_rate = prevented / max(1, seen)
            if prevention_rate > 0.5:
                continue  # being handled well

            # High seen count + low prevention = recurring unresolved issue
            if seen >= 10:
                prob = min(0.85, 0.4 + seen * 0.03)
                threats.append(ThreatFinding(
                    threat_id=f"dna_{ftype}",
                    failure_type=ftype,
                    probability=prob,
                    days_until=None,  # timing unknown from DNA alone
                    confidence="medium",
                    headline=f"{ftype} has occurred {seen} times and is not being prevented",
                    evidence=[
                        f"Seen {seen} times on this machine",
                        f"Only prevented {prevented} times ({prevention_rate*100:.0f}% prevention rate)",
                        f"Detection accuracy: {accuracy}%",
                        f"Average warning: {p.get('lead_time', 0):.0f} minutes before failure",
                    ],
                    recommendation=f"Acknowledge {ftype} predictions when they fire and take action. Currently {100-prevention_rate*100:.0f}% of {ftype} events are going unhandled.",
                    data_points=seen,
                    trend_per_day=0.0,
                ))

        return threats

    def _analyse_anomaly_trend(self, history: list) -> list:
        """
        If the ML anomaly score is trending up over days,
        something is slowly going wrong even if metrics look normal.
        """
        threats = []

        cutoff = time.time() - 86400 * 3   # last 3 days
        recent = [s for s in history if s.get("t", 0) > cutoff]

        if len(recent) < 50:
            return threats

        anomalies = [s["anomaly"] for s in recent if "anomaly" in s]
        if not anomalies:
            return threats

        # Split into thirds and compare
        third = len(anomalies) // 3
        early  = statistics.mean(anomalies[:third])
        late   = statistics.mean(anomalies[2*third:])
        delta  = late - early

        # Only flag if anomaly score is climbing meaningfully
        if delta < 0.05 or late < 0.3:
            return threats

        threats.append(ThreatFinding(
            threat_id="anomaly_trend",
            failure_type="ANOMALY_ESCALATION",
            probability=min(0.75, 0.3 + delta * 2),
            days_until=None,
            confidence="low",
            headline="ML anomaly score is gradually increasing — something is slowly degrading",
            evidence=[
                f"Anomaly score 3 days ago: {early:.3f}",
                f"Anomaly score now: {late:.3f} (+{delta:.3f})",
                "This suggests gradual system degradation even without obvious metric spikes",
                "The ML models are detecting subtle patterns that don't show in raw numbers",
            ],
            recommendation="Review recent system changes — new software, updates, or background processes. The ML models are detecting something that raw metrics aren't showing yet.",
            data_points=len(anomalies),
            trend_per_day=delta / 3,
        ))

        return threats

    def _build_summary(self, threats: list, safe: bool) -> str:
        if safe or not threats:
            return "No critical threats detected in the next 30 days. System looks stable."

        top = threats[0]

        if top.days_until and top.days_until <= 7:
            urgency = "URGENT"
        elif top.days_until and top.days_until <= 14:
            urgency = "WARNING"
        else:
            urgency = "ADVISORY"

        days_str = f"in ~{top.days_until:.0f} days" if top.days_until else "at an unknown time"
        summary  = f"[{urgency}] Most likely failure: {top.failure_type} {days_str}. "
        summary += f"{top.headline}. "

        if len(threats) > 1:
            others = [t.failure_type for t in threats[1:3]]
            summary += f"Also watching: {', '.join(others)}."

        return summary


# ── Singleton ─────────────────────────────────────────────

_premortem_engine = None
_premortem_lock   = threading.Lock()

def get_premortem_engine() -> PreMortemEngine:
    global _premortem_engine
    with _premortem_lock:
        if _premortem_engine is None:
            _premortem_engine = PreMortemEngine()
    return _premortem_engine


# ── Standalone CLI ────────────────────────────────────────

def _fetch(server, key, path):
    try:
        req = urllib.request.Request(
            f"{server}{path}",
            headers={"X-API-Key": key}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.loads(r.read())
    except Exception:
        return None


def print_premortem(server: str, key: str, as_json: bool = False):
    """Fetch data from server and print pre-mortem report."""
    import urllib.request

    print("Fetching system data...")
    health  = _fetch(server, key, "/health/full")
    dna     = _fetch(server, key, "/cognitive/dna")
    db_snap = _fetch(server, key, "/db/snapshots?limit=500")

    # Build synthetic history from snapshots if available
    engine = PreMortemEngine()
    if db_snap:
        for snap in (db_snap if isinstance(db_snap, list) else []):
            if isinstance(snap, dict):
                engine.ingest(snap)
    elif health:
        # Inject at least one point so engine has something
        engine.ingest(health)

    result = engine.run(dna_summary=dna)

    if as_json:
        import dataclasses
        def to_dict(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            return str(obj)
        print(_json.dumps(dataclasses.asdict(result), default=to_dict, indent=2))
        return

    # Plain text report
    now = __import__("datetime").datetime.now().strftime("%B %d, %Y at %H:%M")
    print()
    print("=" * 60)
    print(f"  CVIS FAILURE PRE-MORTEM — {now}")
    print(f"  \"What will kill this machine in the next {result.horizon_days} days?\"")
    print("=" * 60)
    print(f"  Data quality: {result.data_quality}")
    print()

    if result.safe or not result.threats:
        print("  ✅ No critical threats detected.")
        print(f"  {result.plain_summary}")
    else:
        print(f"  Summary: {result.plain_summary}")
        print()
        for i, t in enumerate(result.threats, 1):
            prob_pct = int(t.probability * 100)
            days_str = f"~{t.days_until:.0f} days" if t.days_until else "unknown timeline"
            print(f"  {'🔴' if prob_pct >= 70 else '🟡' if prob_pct >= 45 else '🟢'} THREAT {i}: {t.failure_type}")
            print(f"  {t.headline}")
            print(f"  Probability: {prob_pct}% | Timeline: {days_str} | Confidence: {t.confidence}")
            print()
            print("  Evidence:")
            for e in t.evidence:
                print(f"    → {e}")
            print()
            print(f"  What to do now:")
            print(f"    {t.recommendation}")
            print()
            print("  " + "─" * 54)
            print()

    print("=" * 60)
    print()


if __name__ == "__main__":
    import argparse
    import urllib.request

    parser = argparse.ArgumentParser(description="CVIS Failure Pre-Mortem")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--key",    default="test123")
    parser.add_argument("--json",   action="store_true")
    args = parser.parse_args()

    print_premortem(args.server, args.key, as_json=args.json)
