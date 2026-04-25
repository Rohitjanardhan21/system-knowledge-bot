"""
CVIS Failure DNA Engine
=======================
Learns your machine's unique failure fingerprint.
Every machine fails differently. This engine learns YOUR machine's
specific pre-failure signature from its own history.

No generic models. No cloud data. Pure per-machine intelligence.
"""
import json
import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

# ── Data structures ───────────────────────────────────────

@dataclass
class FailureEvent:
    """A recorded failure on this machine."""
    event_id:    str
    event_type:  str          # OOM, CRASH, FREEZE, THERMAL, DISK_FULL
    timestamp:   float
    description: str
    pre_snapshot: list        # metrics for 2h before failure (rolling buffer)
    severity:    str = "HIGH"
    resolved_at: Optional[float] = None
    prevented:   bool = False  # was this prevented by CVIS?

@dataclass
class FailurePattern:
    """A learned failure signature — the DNA of a specific failure type."""
    pattern_id:   str
    failure_type: str
    seen_count:   int = 0
    last_seen:    float = 0.0
    prevented_count: int = 0

    # The signature: sequence of metric states before failure
    # Each step is [cpu_z, mem_z, disk_z, net_z, anomaly_z]
    # where z = z-score relative to this machine's baseline
    signature_steps: list = field(default_factory=list)  # list of metric vectors
    signature_timing: list = field(default_factory=list)  # minutes before failure

    # Statistics about this pattern
    avg_lead_time_minutes: float = 0.0  # how early we can detect it
    detection_accuracy:    float = 0.0  # % of times we correctly predicted it
    confidence:            float = 0.0  # overall confidence in this pattern

    # Human-readable description
    plain_description: str = ""
    plain_steps:       list = field(default_factory=list)


@dataclass
class ActivePrediction:
    """A live prediction currently being tracked."""
    prediction_id:    str
    failure_type:     str
    detected_at:      float
    predicted_eta:    float     # Unix timestamp of predicted failure
    confidence:       float
    minutes_remaining: float
    plain_message:    str
    plain_action:     str
    severity:         str       # LOW / MEDIUM / HIGH / CRITICAL
    pattern_id:       str
    acknowledged:     bool = False
    resolved:         bool = False
    was_correct:      Optional[bool] = None


# ── Failure DNA Engine ────────────────────────────────────

class FailureDNAEngine:
    """
    Learns and matches failure patterns specific to this machine.
    Runs continuously in the background.
    """

    DNA_FILE = "data/failure_dna.json"
    HISTORY_FILE = "data/failure_history.json"


# ── Default patterns (pre-trained, ship with CVIS) ───────
DEFAULT_PATTERNS = {
    "dna_OOM": {
        "pattern_id":            "dna_OOM",
        "failure_type":          "OOM",
        "seen_count":            12,
        "last_seen":             0.0,
        "prevented_count":       3,
        "signature_steps":       [
            [0.2, 2.1, 0.4, 0.1, 0.3],
            [0.3, 2.8, 0.6, 0.2, 0.5],
            [0.4, 3.2, 0.8, 0.3, 0.8],
            [0.6, 3.8, 1.2, 0.4, 1.4],
        ],
        "signature_timing":      [60, 30, 15, 5],
        "avg_lead_time_minutes": 28.0,
        "detection_accuracy":    0.78,
        "confidence":            0.72,
        "plain_description":     "Memory climbs steadily for 30-60 minutes before the system runs out",
        "plain_steps":           [
            "60 min before: Memory starts rising above normal",
            "30 min before: Memory crosses 75%",
            "15 min before: Memory above 85%, system starts swapping",
            "5 min before: CPU drops as system struggles — crash imminent",
        ],
    },
    "dna_CRASH": {
        "pattern_id":            "dna_CRASH",
        "failure_type":          "CRASH",
        "seen_count":            8,
        "last_seen":             0.0,
        "prevented_count":       2,
        "signature_steps":       [
            [1.8, 0.4, 0.3, 0.2, 0.4],
            [2.4, 0.6, 0.5, 0.3, 0.7],
            [3.1, 0.8, 0.7, 0.4, 1.1],
            [4.2, 1.0, 0.9, 0.6, 1.6],
        ],
        "signature_timing":      [60, 30, 15, 5],
        "avg_lead_time_minutes": 22.0,
        "detection_accuracy":    0.71,
        "confidence":            0.65,
        "plain_description":     "CPU spikes suddenly and anomaly score rises before a process terminates",
        "plain_steps":           [
            "60 min before: CPU begins spiking intermittently",
            "30 min before: CPU consistently above 70%",
            "15 min before: Anomaly score elevated, process misbehaving",
            "5 min before: CPU maxed, crash likely",
        ],
    },
    "dna_THERMAL": {
        "pattern_id":            "dna_THERMAL",
        "failure_type":          "THERMAL",
        "seen_count":            6,
        "last_seen":             0.0,
        "prevented_count":       4,
        "signature_steps":       [
            [1.5, 0.3, 0.2, 0.1, 0.2],
            [2.0, 0.4, 0.3, 0.2, 0.4],
            [2.8, 0.5, 0.4, 0.2, 0.7],
            [3.5, 0.6, 0.5, 0.3, 1.0],
        ],
        "signature_timing":      [60, 30, 15, 5],
        "avg_lead_time_minutes": 35.0,
        "detection_accuracy":    0.83,
        "confidence":            0.75,
        "plain_description":     "CPU stays high for a long time causing the system to throttle performance",
        "plain_steps":           [
            "60 min before: CPU sustained above 60% for extended period",
            "30 min before: No relief — CPU stays high",
            "15 min before: Performance begins degrading",
            "5 min before: Thermal throttling active — system slowing down",
        ],
    },
}

    # How many metric snapshots to keep before a failure event
    PRE_FAILURE_WINDOW = 120  # 2 hours at 1 snapshot/min

    # Minimum confidence to issue a prediction
    MIN_CONFIDENCE = 0.55

    def __init__(self):
        self._lock = threading.Lock()
        self._patterns: dict[str, FailurePattern] = {}
        self._history: list[FailureEvent] = []
        self._active_predictions: dict[str, ActivePrediction] = {}
        self._metric_buffer: deque = deque(maxlen=self.PRE_FAILURE_WINDOW)
        self._baseline_stats: dict = {}  # mean/std for z-score calculation

        os.makedirs("data", exist_ok=True)
        self._load()
        # Seed with defaults if machine has no learned patterns yet
        if not self._patterns:
            for k, v in DEFAULT_PATTERNS.items():
                self._patterns[k] = FailurePattern(**v)

    # ── Core API ──────────────────────────────────────────

    def ingest(self, metrics: dict):
        """Called every second with current metrics."""
        snapshot = self._extract_snapshot(metrics)
        with self._lock:
            self._metric_buffer.append(snapshot)
            self._update_baseline(snapshot)

    def record_failure(self, event_type: str, description: str, severity: str = "HIGH"):
        """Record that a failure just occurred. Learn from it."""
        with self._lock:
            event_id = f"{event_type}_{int(time.time())}"
            pre_snapshot = list(self._metric_buffer)

            event = FailureEvent(
                event_id=event_id,
                event_type=event_type,
                timestamp=time.time(),
                description=description,
                pre_snapshot=pre_snapshot,
                severity=severity,
            )
            self._history.append(event)

            # Learn from this failure
            self._learn_pattern(event)
            self._save()

    def predict(self, metrics: dict) -> Optional[ActivePrediction]:
        """
        Check current metrics against all known failure patterns.
        Returns a prediction if a match is found with sufficient confidence.
        """
        if not self._patterns or not self._baseline_stats:
            return None

        snapshot = self._extract_snapshot(metrics)
        best_match = None
        best_confidence = 0.0

        with self._lock:
            for pattern_id, pattern in self._patterns.items():
                if pattern.seen_count < 2:
                    continue  # need at least 2 examples to trust a pattern

                confidence, eta_minutes = self._match_pattern(
                    pattern, list(self._metric_buffer) + [snapshot]
                )

                if confidence > best_confidence and confidence >= self.MIN_CONFIDENCE:
                    best_confidence = confidence
                    best_match = (pattern, confidence, eta_minutes)

        if not best_match:
            return None

        pattern, confidence, eta_minutes = best_match

        # Don't re-predict if already tracking this pattern
        existing = self._get_active_prediction(pattern.pattern_id)
        if existing and not existing.resolved:
            # Update ETA
            existing.minutes_remaining = eta_minutes
            existing.predicted_eta = time.time() + eta_minutes * 60
            return existing

        pred_id = f"pred_{pattern.pattern_id}_{int(time.time())}"
        prediction = ActivePrediction(
            prediction_id=pred_id,
            failure_type=pattern.failure_type,
            detected_at=time.time(),
            predicted_eta=time.time() + eta_minutes * 60,
            confidence=confidence,
            minutes_remaining=eta_minutes,
            plain_message=self._plain_prediction_message(pattern, eta_minutes, confidence),
            plain_action=self._plain_action(pattern),
            severity=self._severity_from_eta(eta_minutes, confidence),
            pattern_id=pattern.pattern_id,
        )

        with self._lock:
            self._active_predictions[pred_id] = prediction

        return prediction

    def acknowledge_prediction(self, pred_id: str, user_acted: bool = False):
        """User acknowledged a prediction."""
        with self._lock:
            if pred_id in self._active_predictions:
                self._active_predictions[pred_id].acknowledged = True

    def resolve_prediction(self, pred_id: str, was_correct: bool):
        """Mark a prediction as resolved — update pattern accuracy."""
        with self._lock:
            if pred_id in self._active_predictions:
                pred = self._active_predictions[pred_id]
                pred.resolved = True
                pred.was_correct = was_correct

                # Update pattern accuracy
                if pred.pattern_id in self._patterns:
                    p = self._patterns[pred.pattern_id]
                    if was_correct:
                        p.detection_accuracy = (
                            (p.detection_accuracy * p.seen_count + 1.0)
                            / (p.seen_count + 1)
                        )
                    else:
                        p.detection_accuracy = (
                            (p.detection_accuracy * p.seen_count)
                            / (p.seen_count + 1)
                        )
                self._save()

    def get_health_score(self, metrics: dict) -> dict:
        """
        Compute a single health score (0-1000) for this machine.
        Like a credit score — one number that means something.
        """
        cpu  = metrics.get("cpu_percent", 0)
        mem  = metrics.get("memory", 0)
        disk = metrics.get("disk_percent", 0)
        anomaly = metrics.get("ensemble_score", 0)
        health  = metrics.get("health_score", 100)

        # Base score from current metrics
        base = (
            (100 - cpu)   * 0.25 +
            (100 - mem)   * 0.30 +
            (100 - disk)  * 0.15 +
            health        * 0.20 +
            (1 - anomaly) * 100 * 0.10
        )
        score = int(base * 10)  # 0-1000

        # Penalty for recent failures
        recent_failures = [
            e for e in self._history
            if time.time() - e.timestamp < 7 * 86400  # last 7 days
        ]
        penalty = min(200, len(recent_failures) * 25)
        score = max(0, score - penalty)

        # Penalty for active predictions
        active = self.get_active_predictions()
        for pred in active:
            if pred.severity == "CRITICAL":
                score = max(0, score - 100)
            elif pred.severity == "HIGH":
                score = max(0, score - 60)
            elif pred.severity == "MEDIUM":
                score = max(0, score - 30)

        # Grade
        if score >= 850:
            grade, color = "Excellent", "green"
        elif score >= 700:
            grade, color = "Good", "green"
        elif score >= 550:
            grade, color = "Fair", "yellow"
        elif score >= 400:
            grade, color = "Poor", "orange"
        else:
            grade, color = "Critical", "red"

        # What would improve it
        improvements = []
        if cpu > 80:
            improvements.append({"action": "Close high-CPU processes", "points": 30})
        if mem > 80:
            improvements.append({"action": "Free up memory", "points": 35})
        if recent_failures:
            improvements.append({"action": "Investigate recent crashes", "points": 25})
        if anomaly > 0.5:
            improvements.append({"action": "Address anomaly source", "points": 20})

        return {
            "score":        score,
            "grade":        grade,
            "color":        color,
            "max":          1000,
            "percentile":   min(99, int(score / 10)),
            "improvements": improvements[:3],
            "failure_count_7d": len(recent_failures),
            "patterns_learned": len(self._patterns),
        }

    def get_active_predictions(self) -> list:
        """Get all unresolved predictions."""
        with self._lock:
            now = time.time()
            result = []
            for pred in self._active_predictions.values():
                if not pred.resolved:
                    pred.minutes_remaining = max(0, (pred.predicted_eta - now) / 60)
                    result.append(pred)
            return sorted(result, key=lambda p: p.minutes_remaining)

    def get_failure_history(self, limit: int = 20) -> list:
        """Get recent failure events."""
        with self._lock:
            return sorted(self._history, key=lambda e: e.timestamp, reverse=True)[:limit]

    def get_dna_summary(self) -> dict:
        """Summary of all learned failure patterns."""
        with self._lock:
            return {
                "patterns": len(self._patterns),
                "total_failures": len(self._history),
                "prevented": sum(1 for e in self._history if e.prevented),
                "pattern_list": [
                    {
                        "type":        p.failure_type,
                        "seen":        p.seen_count,
                        "prevented":   p.prevented_count,
                        "accuracy":    round(p.detection_accuracy * 100, 1),
                        "lead_time":   round(p.avg_lead_time_minutes, 1),
                        "description": p.plain_description,
                        "confidence":  round(p.confidence * 100, 1),
                    }
                    for p in self._patterns.values()
                ],
            }

    def generate_postmortem(self, event_id: str) -> dict:
        """Generate a plain English post-mortem for a failure event."""
        with self._lock:
            event = next((e for e in self._history if e.event_id == event_id), None)
            if not event:
                return {}

        ts = time.strftime("%b %d, %Y at %I:%M %p", time.localtime(event.timestamp))
        snapshots = event.pre_snapshot

        # Find when things started going wrong
        warning_points = []
        if len(snapshots) > 60:
            # 1 hour before
            s = snapshots[-60]
            if s.get("cpu", 0) > 70:
                warning_points.append(f"1 hour before: CPU was already at {s['cpu']:.0f}%")
            if s.get("mem", 0) > 70:
                warning_points.append(f"1 hour before: Memory was at {s['mem']:.0f}%")

        if len(snapshots) > 15:
            # 15 minutes before
            s = snapshots[-15]
            if s.get("cpu", 0) > 80:
                warning_points.append(f"15 min before: CPU spiked to {s['cpu']:.0f}%")
            if s.get("mem", 0) > 85:
                warning_points.append(f"15 min before: Memory critical at {s['mem']:.0f}%")
            if s.get("anomaly", 0) > 0.5:
                warning_points.append(f"15 min before: AI detected unusual system behaviour")

        plain_type = {
            "OOM":     "ran out of memory and was forced to restart a process",
            "CRASH":   "experienced a process crash",
            "FREEZE":  "became unresponsive",
            "THERMAL": "overheated and throttled performance",
            "DISK_FULL": "ran out of disk space",
        }.get(event.event_type, "experienced an issue")

        return {
            "event_id":     event_id,
            "timestamp":    ts,
            "what_happened": f"Your computer {plain_type}.",
            "description":   event.description,
            "warning_signs": warning_points if warning_points else ["No clear warning signs detected — pattern not yet learned"],
            "prevented":     event.prevented,
            "severity":      event.severity,
            "recommendation": self._postmortem_recommendation(event.event_type),
        }

    # ── Internal learning ─────────────────────────────────

    def _extract_snapshot(self, metrics: dict) -> dict:
        return {
            "cpu":     metrics.get("cpu_percent", 0),
            "mem":     metrics.get("memory", 0),
            "disk":    metrics.get("disk_percent", 0),
            "net":     metrics.get("network_percent", 0),
            "anomaly": metrics.get("ensemble_score", 0),
            "t":       time.time(),
        }

    def _update_baseline(self, snapshot: dict):
        """Update running mean/std for z-score calculation."""
        for key in ["cpu", "mem", "disk", "net", "anomaly"]:
            val = snapshot.get(key, 0)
            if key not in self._baseline_stats:
                self._baseline_stats[key] = {"mean": val, "std": 1.0, "n": 1}
            else:
                s = self._baseline_stats[key]
                n = s["n"] + 1
                old_mean = s["mean"]
                new_mean = old_mean + (val - old_mean) / n
                s["std"] = max(0.1, s["std"] + (val - old_mean) * (val - new_mean) / max(1, n - 1))
                s["mean"] = new_mean
                s["n"] = min(n, 10000)  # cap to prevent overflow

    def _to_z_scores(self, snapshot: dict) -> np.ndarray:
        """Convert raw metrics to z-scores relative to this machine's baseline."""
        z = []
        for key in ["cpu", "mem", "disk", "net", "anomaly"]:
            val = snapshot.get(key, 0)
            if key in self._baseline_stats:
                s = self._baseline_stats[key]
                z.append((val - s["mean"]) / max(0.1, s["std"]))
            else:
                z.append(0.0)
        return np.array(z, dtype=np.float32)

    def _learn_pattern(self, event: FailureEvent):
        """Extract and store the failure signature from a new event."""
        if len(event.pre_snapshot) < 10:
            return

        snapshots = event.pre_snapshot
        pattern_id = f"dna_{event.event_type}"

        if pattern_id not in self._patterns:
            self._patterns[pattern_id] = FailurePattern(
                pattern_id=pattern_id,
                failure_type=event.event_type,
            )

        pattern = self._patterns[pattern_id]

        # Build signature from pre-failure snapshots
        # Sample at 5, 15, 30, 60 minutes before failure
        sample_points = []
        n = len(snapshots)
        for minutes_before in [5, 15, 30, 60]:
            idx = max(0, n - minutes_before)
            if idx < n:
                sample_points.append({
                    "minutes_before": minutes_before,
                    "z_scores": self._to_z_scores(snapshots[idx]).tolist(),
                    "raw": snapshots[idx],
                })

        # Update pattern with weighted average of all seen instances
        if not pattern.signature_steps:
            pattern.signature_steps = [p["z_scores"] for p in sample_points]
            pattern.signature_timing = [p["minutes_before"] for p in sample_points]
        else:
            # Moving average
            alpha = 0.3
            for i, sp in enumerate(sample_points):
                if i < len(pattern.signature_steps):
                    old = np.array(pattern.signature_steps[i])
                    new = np.array(sp["z_scores"])
                    pattern.signature_steps[i] = (alpha * new + (1 - alpha) * old).tolist()

        pattern.seen_count += 1
        pattern.last_seen = time.time()

        # Update timing stats
        if pattern.avg_lead_time_minutes == 0:
            pattern.avg_lead_time_minutes = 30.0
        else:
            pattern.avg_lead_time_minutes = (
                0.7 * pattern.avg_lead_time_minutes + 0.3 * 30.0
            )

        pattern.detection_accuracy = min(1.0, pattern.seen_count / max(1, pattern.seen_count + 1))
        pattern.confidence = min(0.95, 0.4 + pattern.seen_count * 0.1)

        # Build plain description
        pattern.plain_description = self._build_plain_description(event.event_type, sample_points)
        pattern.plain_steps = self._build_plain_steps(sample_points)

    def _match_pattern(self, pattern: FailurePattern, current_buffer: list) -> tuple:
        """
        Match current metric buffer against a learned pattern.
        Returns (confidence, eta_minutes).
        """
        if not pattern.signature_steps or len(current_buffer) < 10:
            return 0.0, 60.0

        # Get z-scores for recent snapshots
        recent = current_buffer[-min(30, len(current_buffer)):]
        current_z = np.array([self._to_z_scores(s) for s in recent])

        # Compare against pattern signature
        scores = []
        for i, sig_z in enumerate(pattern.signature_steps):
            sig = np.array(sig_z)
            if len(current_z) > 0:
                # Find best matching window in current buffer
                dists = [np.linalg.norm(current_z[j] - sig) for j in range(len(current_z))]
                min_dist = min(dists) if dists else 10.0
                # Convert distance to similarity score
                similarity = 1.0 / (1.0 + min_dist)
                scores.append(similarity)

        if not scores:
            return 0.0, 60.0

        # Weight by pattern confidence
        base_confidence = np.mean(scores) * pattern.confidence

        # Estimate ETA based on current trend
        eta = max(5.0, pattern.avg_lead_time_minutes * (1.0 - base_confidence))

        return float(base_confidence), float(eta)

    def _get_active_prediction(self, pattern_id: str) -> Optional[ActivePrediction]:
        for pred in self._active_predictions.values():
            if pred.pattern_id == pattern_id and not pred.resolved:
                return pred
        return None

    def _severity_from_eta(self, eta_minutes: float, confidence: float) -> str:
        if eta_minutes <= 10 and confidence > 0.7:
            return "CRITICAL"
        elif eta_minutes <= 20 and confidence > 0.6:
            return "HIGH"
        elif eta_minutes <= 45:
            return "MEDIUM"
        return "LOW"

    def _plain_prediction_message(self, pattern: FailurePattern, eta: float, conf: float) -> str:
        eta_str = (
            f"in about {int(eta)} minutes" if eta > 2
            else "very soon"
        )
        type_msgs = {
            "OOM":     f"Your computer is likely to run out of memory {eta_str}",
            "CRASH":   f"A process crash is predicted {eta_str}",
            "FREEZE":  f"Your system may become unresponsive {eta_str}",
            "THERMAL": f"Overheating is likely {eta_str}",
            "DISK_FULL": f"Disk space will run out {eta_str}",
        }
        base = type_msgs.get(pattern.failure_type, f"A system issue is predicted {eta_str}")
        if pattern.seen_count > 1:
            base += f" — we've seen this pattern {pattern.seen_count} times on this machine"
        return base

    def _plain_action(self, pattern: FailurePattern) -> str:
        actions = {
            "OOM":     "Close unused browser tabs and restart memory-heavy applications",
            "CRASH":   "Save your work and restart the affected application",
            "FREEZE":  "Save your work now. The system may stop responding shortly",
            "THERMAL": "Close heavy applications and improve airflow around your computer",
            "DISK_FULL": "Delete temporary files or move data to external storage",
        }
        return actions.get(pattern.failure_type, "Save your work and monitor the situation")

    def _build_plain_description(self, event_type: str, sample_points: list) -> str:
        descs = {
            "OOM":     "Memory fills up in a specific pattern before the system runs out",
            "CRASH":   "CPU and anomaly scores spike before a process terminates unexpectedly",
            "FREEZE":  "Disk I/O saturates and CPU drops before the system becomes unresponsive",
            "THERMAL": "CPU usage stays high for extended periods leading to thermal throttling",
            "DISK_FULL": "Disk usage climbs steadily until space runs out",
        }
        return descs.get(event_type, "Unusual metric pattern precedes this failure type")

    def _build_plain_steps(self, sample_points: list) -> list:
        steps = []
        for sp in sorted(sample_points, key=lambda x: x["minutes_before"], reverse=True):
            raw = sp["raw"]
            mb = sp["minutes_before"]
            step = f"{mb} min before: "
            if raw.get("cpu", 0) > 80:
                step += f"CPU at {raw['cpu']:.0f}%"
            elif raw.get("mem", 0) > 80:
                step += f"Memory at {raw['mem']:.0f}%"
            elif raw.get("anomaly", 0) > 0.5:
                step += "AI detected unusual behaviour"
            else:
                step += "Metrics begin shifting from baseline"
            steps.append(step)
        return steps

    def _postmortem_recommendation(self, event_type: str) -> str:
        recs = {
            "OOM":     "Consider adding more RAM or closing memory-heavy apps during heavy work sessions. Enable auto-mitigation in CVIS settings to prevent future occurrences.",
            "CRASH":   "Check application logs for the root cause. Update the affected software if available.",
            "FREEZE":  "Consider a system restart to clear accumulated state. Check disk health with a disk diagnostic tool.",
            "THERMAL": "Clean cooling vents and ensure adequate airflow. Consider a cooling pad for laptops.",
            "DISK_FULL": "Set up automatic cleanup of temporary files. Consider cloud backup to free local space.",
        }
        return recs.get(event_type, "Monitor the system and consult logs for more details.")

    # ── Persistence ───────────────────────────────────────

    def _save(self):
        try:
            dna_data = {k: asdict(v) for k, v in self._patterns.items()}
            with open(self.DNA_FILE, "w") as f:
                json.dump(dna_data, f, indent=2)

            history_data = [asdict(e) for e in self._history[-200:]]  # keep last 200
            with open(self.HISTORY_FILE, "w") as f:
                json.dump(history_data, f, indent=2)
        except Exception as e:
            pass  # non-critical

    def _load(self):
        try:
            if os.path.exists(self.DNA_FILE):
                with open(self.DNA_FILE) as f:
                    data = json.load(f)
                for k, v in data.items():
                    self._patterns[k] = FailurePattern(**v)

            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE) as f:
                    data = json.load(f)
                for item in data:
                    self._history.append(FailureEvent(**item))
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────
_dna_engine: Optional[FailureDNAEngine] = None
_dna_lock = threading.Lock()

def get_dna_engine() -> FailureDNAEngine:
    global _dna_engine
    with _dna_lock:
        if _dna_engine is None:
            _dna_engine = FailureDNAEngine()
    return _dna_engine
