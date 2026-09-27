from backend.core.storage.db import save_prediction
"""
CVIS Failure DNA Engine
Learns your machine's unique failure fingerprint.
Includes: Trust Layer + Anomaly Explainability
"""
import json, os, time, threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional
import numpy as np

@dataclass
class FailureEvent:
    event_id:     str
    event_type:   str
    timestamp:    float
    description:  str
    pre_snapshot: list
    severity:     str = "HIGH"
    resolved_at:  Optional[float] = None
    prevented:    bool = False

@dataclass
class FailurePattern:
    pattern_id:            str
    failure_type:          str
    seen_count:            int = 0
    last_seen:             float = 0.0
    prevented_count:       int = 0
    signature_steps:       list = field(default_factory=list)
    signature_timing:      list = field(default_factory=list)
    avg_lead_time_minutes: float = 0.0

    # Prediction validation is tracked separately from failure observations.
    # seen_count tells us how many failures formed the pattern.
    # validated_predictions tells us how many predictions were actually
    # resolved and judged correct/incorrect.
    validated_predictions: int = 0
    correct_predictions:   int = 0
    detection_accuracy:    Optional[float] = None

    confidence:            float = 0.0
    plain_description:     str = ""
    plain_steps:           list = field(default_factory=list)

@dataclass
class ActivePrediction:
    prediction_id:     str
    failure_type:      str
    detected_at:       float
    predicted_eta:     float
    confidence:        float
    minutes_remaining: float
    plain_message:     str
    plain_action:      str
    severity:          str
    pattern_id:        str
    acknowledged:      bool = False
    resolved:          bool = False
    was_correct:       Optional[bool] = None

DEFAULT_PATTERNS = {
    "dna_OOM": FailurePattern(
        pattern_id="dna_OOM", failure_type="OOM", seen_count=12,
        prevented_count=3, avg_lead_time_minutes=28.0,
        detection_accuracy=None, confidence=0.72,
        signature_steps=[[0.2,2.1,0.4,0.1,0.3],[0.3,2.8,0.6,0.2,0.5],[0.4,3.2,0.8,0.3,0.8],[0.6,3.8,1.2,0.4,1.4]],
        signature_timing=[60,30,15,5],
        plain_description="Memory climbs steadily for 30-60 minutes before the system runs out",
        plain_steps=["60 min before: Memory starts rising","30 min before: Memory crosses 75%","15 min before: Memory above 85%","5 min before: Crash imminent"],
    ),
    "dna_CRASH": FailurePattern(
        pattern_id="dna_CRASH", failure_type="CRASH", seen_count=8,
        prevented_count=2, avg_lead_time_minutes=22.0,
        detection_accuracy=None, confidence=0.65,
        signature_steps=[[1.8,0.4,0.3,0.2,0.4],[2.4,0.6,0.5,0.3,0.7],[3.1,0.8,0.7,0.4,1.1],[4.2,1.0,0.9,0.6,1.6]],
        signature_timing=[60,30,15,5],
        plain_description="CPU spikes before a process terminates unexpectedly",
        plain_steps=["60 min before: CPU spiking intermittently","30 min before: CPU above 70%","15 min before: Anomaly score elevated","5 min before: CPU maxed"],
    ),
    "dna_THERMAL": FailurePattern(
        pattern_id="dna_THERMAL", failure_type="THERMAL", seen_count=6,
        prevented_count=4, avg_lead_time_minutes=35.0,
        detection_accuracy=None, confidence=0.75,
        signature_steps=[[1.5,0.3,0.2,0.1,0.2],[2.0,0.4,0.3,0.2,0.4],[2.8,0.5,0.4,0.2,0.7],[3.5,0.6,0.5,0.3,1.0]],
        signature_timing=[60,30,15,5],
        plain_description="CPU stays high causing thermal throttling",
        plain_steps=["60 min before: CPU sustained above 60%","30 min before: No relief","15 min before: Performance degrading","5 min before: Throttling active"],
    ),
}

# ---------------------------------------------------------------------------
# Metric display helpers
# ---------------------------------------------------------------------------

_METRIC_LABELS = {
    "cpu":     "CPU usage",
    "mem":     "RAM usage",
    "disk":    "Disk usage",
    "net":     "Network I/O",
    "anomaly": "Anomaly score",
}

_PATTERN_TRIGGERS = {
    "OOM":        ["mem", "anomaly"],
    "CRASH":      ["cpu", "anomaly"],
    "THERMAL":    ["cpu"],
    "FREEZE":     ["disk", "cpu"],
    "CPU_STRESS": ["cpu", "anomaly"],
    "DISK_FULL":  ["disk"],
}

_NORMAL_THRESHOLDS = {
    "cpu":     70.0,
    "mem":     75.0,
    "disk":    85.0,
    "net":     60.0,
    "anomaly": 0.50,
}

# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class FailureDNAEngine:
    DNA_FILE     = "data/failure_dna.json"
    HISTORY_FILE = "data/failure_history.json"
    PRE_FAILURE_WINDOW = 120
    MIN_CONFIDENCE     = 0.70
    MIN_SAMPLES        = 6

    def __init__(self, dna_file: str = None, history_file: str = None):
        self._lock = threading.RLock()
        self._patterns: dict = {}
        self._history: list = []
        self._active_predictions: dict = {}
        self._metric_buffer: deque = deque(maxlen=self.PRE_FAILURE_WINDOW)
        self._baseline_stats: dict = {}

        # Allow persistence paths to be supplied before loading state.
        # This is important for restart/persistence tests and for callers
        # that need isolated DNA state.
        if dna_file is not None:
            self.DNA_FILE = dna_file
        if history_file is not None:
            self.HISTORY_FILE = history_file

        os.makedirs(os.path.dirname(self.DNA_FILE) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.HISTORY_FILE) or ".", exist_ok=True)

        self._load()

        if not self._patterns:
            self._patterns = {k: v for k, v in DEFAULT_PATTERNS.items()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, metrics: dict):
        snapshot = self._extract_snapshot(metrics)

        with self._lock:
            # Always keep the live trajectory in the buffer.
            self._metric_buffer.append(snapshot)

            # Do not let active anomalies/stress redefine "normal".
            # Baseline statistics should represent stable system behaviour.
            cpu = snapshot.get("cpu", 0)
            mem = snapshot.get("mem", 0)
            disk = snapshot.get("disk", 0)
            anomaly = snapshot.get("anomaly", 0)

            is_stable = (
                cpu < 70.0 and
                mem < 75.0 and
                disk < 85.0 and
                anomaly < 0.50
            )

            if is_stable:
                self._update_baseline(snapshot)

    def record_failure(self, event_type: str, description: str, severity: str = "HIGH"):
        with self._lock:
            event_id = f"{event_type}_{int(time.time())}"
            pre_snapshot = list(self._metric_buffer)
            event = FailureEvent(
                event_id=event_id, event_type=event_type,
                timestamp=time.time(), description=description,
                pre_snapshot=pre_snapshot, severity=severity,
            )
            self._history.append(event)
            self._learn_pattern(event)

            # Validate an active prediction only when the observed
            # incident type matches the prediction type.
            #
            # A matching incident means the prediction was correct.
            # A different incident must not validate the prediction.
            # Resolve ONLY predictions whose failure type exactly matches
            # the observed failure. A different failure must leave the
            # original prediction unresolved and unvalidated.
            observed_type = str(event_type).strip().upper()

            matching_predictions = [
                pred for pred in self._active_predictions.values()
                if (
                    not pred.resolved
                    and str(pred.failure_type).strip().upper() == observed_type
                )
            ]

            for pred in matching_predictions:
                self.resolve_prediction(
                    pred.prediction_id,
                    was_correct=True,
                )

            self._save()

    def predict(self, metrics: dict) -> Optional[ActivePrediction]:
        # --------------------------------------------------------------
        # Lifecycle housekeeping MUST happen before any early return.
        # Expired predictions are terminal lifecycle states and must be
        # retired even when the current metric trajectory cannot produce
        # a new prediction.
        # --------------------------------------------------------------
        now = time.time()
        expired_ids = []

        with self._lock:
            for pred_id, pred in self._active_predictions.items():
                if pred.resolved:
                    continue

                try:
                    predicted_eta = float(pred.predicted_eta)
                except (TypeError, ValueError):
                    continue

                if predicted_eta <= now:
                    expired_ids.append(pred_id)

            for pred_id in expired_ids:
                pred = self._active_predictions.get(pred_id)
                if pred is None or pred.resolved:
                    continue

                pred.resolved = True
                pred.was_correct = False

        if expired_ids:
            self._save()

        if not self._patterns or not self._baseline_stats:
            return None

        snapshot = self._extract_snapshot(metrics)

        # Retain the live trajectory across predict() calls so pattern
        # matching can evaluate the required sequence of observations.
        with self._lock:
            self._metric_buffer.append(snapshot)

        # Retire predictions whose ETA has already passed before
        # constructing the active prediction map. An expired prediction
        # must never be refreshed or reused for a new prediction cycle.
        #
        # Expiry is a lifecycle outcome, NOT prediction validation:
        # it must not increment validated_predictions, correct count,
        # or detection accuracy.
        now = time.time()

        # Retire predictions whose ETA has already passed before
        # evaluating a new prediction cycle. Expired predictions must
        # never remain reusable merely because they were acknowledged.
        expired_ids = []
        for pred_id, pred in list(self._active_predictions.items()):
            if pred.resolved:
                continue

            try:
                predicted_eta = float(pred.predicted_eta)
            except (TypeError, ValueError):
                continue

            if predicted_eta <= now:
                expired_ids.append(pred_id)

        for pred_id in expired_ids:
            pred = self._active_predictions.get(pred_id)
            if pred is None or pred.resolved:
                continue

            # Expiry is a terminal lifecycle state. It is not a
            # validated prediction and must not alter learning accuracy.
            pred.resolved = True
            pred.was_correct = False

        if expired_ids:
            self._save()

        expired_ids = []

        with self._lock:
            for pred_id, pred in self._active_predictions.items():
                if pred.resolved:
                    continue

                try:
                    predicted_eta = float(pred.predicted_eta)
                except (TypeError, ValueError):
                    continue

                if predicted_eta <= now:
                    expired_ids.append(pred_id)

            for pred_id in expired_ids:
                pred = self._active_predictions.get(pred_id)
                if pred is None or pred.resolved:
                    continue

                # Terminal stale state. Keep acknowledgement/history
                # intact while preventing future reuse.
                pred.resolved = True
                pred.was_correct = False

        if expired_ids:
            self._save()

        # Existing unresolved predictions must be refreshable even when
        # subsequent observations weaken the historical match below the
        # creation threshold. The prediction remains active until explicitly
        # resolved.
        active_by_pattern = {}
        with self._lock:
            for pred in self._active_predictions.values():
                if not pred.resolved and pred.pattern_id:
                    active_by_pattern[pred.pattern_id] = pred

        best_match = None
        best_confidence = 0.0
        with self._lock:
            for pattern_id, pattern in self._patterns.items():
                if pattern.seen_count < self.MIN_SAMPLES:
                    continue
                if (
                    pattern.validated_predictions > 0
                    and pattern.detection_accuracy is not None
                    and pattern.detection_accuracy < 0.70
                ):
                    continue
                confidence, eta_minutes = self._match_pattern(
                    pattern, list(self._metric_buffer)
                )
                # New predictions require MIN_CONFIDENCE. Existing active
                # predictions may continue to refresh with weaker evidence.
                active_exists = pattern_id in active_by_pattern
                if confidence > best_confidence and (
                    confidence >= self.MIN_CONFIDENCE or active_exists
                ):
                    best_confidence = confidence
                    best_match = (pattern, confidence, eta_minutes)
        if not best_match:
            return None
        pattern, confidence, eta_minutes = best_match
        existing = self._get_active_prediction(pattern.pattern_id)
        if existing and not existing.resolved:
            existing.minutes_remaining = eta_minutes
            existing.predicted_eta = time.time() + eta_minutes * 60
            existing.confidence = confidence

            # Refresh all user-facing fields so ETA, confidence,
            # message and severity always describe the current state.
            existing.plain_message = self._plain_prediction_message(
                pattern, eta_minutes, confidence
            )
            existing.plain_action = self._plain_action(pattern)
            existing.severity = self._severity_from_eta(
                eta_minutes, confidence
            )

            # Persist refreshed active prediction so the updated
            # state survives restart.
            self._save()

            return existing
        # Generate a collision-resistant prediction ID. Multiple prediction
        # cycles can occur within the same second, so second-resolution
        # timestamps alone are insufficient.
        pred_id = f"pred_{pattern.pattern_id}_{time.time_ns()}"
        prediction = ActivePrediction(
            prediction_id=pred_id, failure_type=pattern.failure_type,
            detected_at=time.time(), predicted_eta=time.time() + eta_minutes * 60,
            confidence=confidence, minutes_remaining=eta_minutes,
            plain_message=self._plain_prediction_message(pattern, eta_minutes, confidence),
            plain_action=self._plain_action(pattern),
            severity=self._severity_from_eta(eta_minutes, confidence),
            pattern_id=pattern.pattern_id,
        )
        with self._lock:
            self._active_predictions[pred_id] = prediction

        # Persist newly created prediction for ground-truth evaluation.
        try:
            import asyncio
            payload = {
                "prediction_id": prediction.prediction_id,
                "device_id": None,
                "failure_type": prediction.failure_type,
                "created_at": prediction.detected_at,
                "expected_at": prediction.predicted_eta,
                "confidence": prediction.confidence,
                "risk_score": prediction.confidence,
                "lead_time_seconds": prediction.minutes_remaining * 60,
                "status": "active",
                "evidence": {
                    "pattern_id": prediction.pattern_id,
                    "message": prediction.plain_message,
                },
                "model_version": "failure_dna",
            }

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(save_prediction(payload))
            except RuntimeError:
                asyncio.run(save_prediction(payload))
        except Exception as e:
            log.warning("Prediction persistence skipped: %s", e)

        return prediction

    def acknowledge_prediction(self, pred_id: str, user_acted: bool = False):
        with self._lock:
            if pred_id in self._active_predictions:
                self._active_predictions[pred_id].acknowledged = True

    def resolve_prediction(self, pred_id: str, was_correct: bool):
        with self._lock:
            pred = self._active_predictions.get(pred_id)

            if pred is None:
                return

            # Resolution is immutable and idempotent.
            # A prediction must never contribute to validation statistics
            # more than once.
            if pred.resolved:
                return

            pred.resolved = True
            pred.was_correct = bool(was_correct)

            # Return the resolved object so callers can verify resolution immediately.

            if pred.pattern_id in self._patterns:
                p = self._patterns[pred.pattern_id]

                # Prediction accuracy is based ONLY on predictions
                # that have actually been resolved and validated.
                p.validated_predictions += 1

                if pred.was_correct:
                    p.correct_predictions += 1

                p.detection_accuracy = (
                    p.correct_predictions / p.validated_predictions
                    if p.validated_predictions > 0
                    else None
                )

            # Keep resolved predictions in the registry so their outcome
            # survives persistence and restart.  They are no longer eligible
            # for active matching because all lookup paths require
            # ``not pred.resolved``.
            self._save()
            return pred

    def is_prediction_trustworthy(self, pattern_id: str) -> bool:
        """
        Return whether a learned pattern has enough historical observations
        and validated prediction outcomes to be considered trustworthy.

        Trust policy is centralized in _is_pattern_trustworthy().
        """
        with self._lock:
            pattern = self._patterns.get(pattern_id)

            if pattern is None:
                return False

            return self._is_pattern_trustworthy(pattern)

    def get_health_score(self, metrics: dict) -> dict:
        cpu     = metrics.get("cpu_percent", 0)
        mem     = metrics.get("memory", 0)
        disk    = metrics.get("disk_percent", 0)
        anomaly = metrics.get("ensemble_score", 0)
        health  = metrics.get("health_score", 100)
        base = ((100-cpu)*0.25 + (100-mem)*0.30 + (100-disk)*0.15 + health*0.20 + (1-anomaly)*100*0.10)
        score = int(base * 10)
        recent_failures = [e for e in self._history if time.time() - e.timestamp < 7*86400]
        score = max(0, score - min(200, len(recent_failures) * 25))
        active = self.get_active_predictions()
        for pred in active:
            score = max(0, score - {"CRITICAL":100,"HIGH":60,"MEDIUM":30}.get(pred.severity, 0))
        if score >= 850:   grade, color = "Excellent", "green"
        elif score >= 700: grade, color = "Good",      "green"
        elif score >= 550: grade, color = "Fair",      "yellow"
        elif score >= 400: grade, color = "Poor",      "orange"
        else:              grade, color = "Critical",  "red"
        improvements = []
        if cpu > 80:             improvements.append({"action":"Close high-CPU processes","points":30})
        if mem > 80:             improvements.append({"action":"Free up memory","points":35})
        if recent_failures:      improvements.append({"action":"Investigate recent crashes","points":25})
        if anomaly > 0.5:        improvements.append({"action":"Address anomaly source","points":20})

        # Data quality context
        snapshot_count = len(self._metric_buffer)
        data_quality = (
            "sufficient" if snapshot_count >= 50
            else f"building — {snapshot_count} snapshots collected"
        )

        return {
            "score": score, "grade": grade, "color": color, "max": 1000,
            "percentile": min(99, int(score/10)), "improvements": improvements[:3],
            "failure_count_7d": len(recent_failures), "patterns_learned": len(self._patterns),
            "data_quality": data_quality, "snapshot_count": snapshot_count,
        }

    def get_active_predictions(self) -> list:
        with self._lock:
            now = time.time()
            result = []
            for pred in self._active_predictions.values():
                if not pred.resolved:
                    pred.minutes_remaining = max(0, (pred.predicted_eta - now) / 60)
                    result.append(pred)
            return sorted(result, key=lambda p: p.minutes_remaining)

    def get_failure_history(self, limit: int = 20) -> list:
        with self._lock:
            return sorted(self._history, key=lambda e: e.timestamp, reverse=True)[:limit]

    def _is_pattern_trustworthy(self, pattern: FailurePattern) -> bool:
        """
        A pattern is trustworthy only when it has enough observations
        and enough validated prediction accuracy.

        This is the single source of truth for all user-facing
        trustworthiness fields.
        """
        return (
            pattern.seen_count >= 15
            and pattern.validated_predictions >= 5
            and pattern.detection_accuracy is not None
            and pattern.detection_accuracy >= 0.70
        )

    def get_dna_summary(self) -> dict:
        with self._lock:
            return {
                "patterns": len(self._patterns),
                "total_failures": len(self._history),
                "prevented": sum(1 for e in self._history if e.prevented),
                "pattern_list": [
                    {
                        "type": p.failure_type,
                        "seen": p.seen_count,
                        "prevented": p.prevented_count,
                        "accuracy": (
                            round(p.detection_accuracy * 100, 1)
                            if p.detection_accuracy is not None
                            else None
                        ),
                        "lead_time": round(p.avg_lead_time_minutes, 1),
                        "description": p.plain_description,
                        "confidence": round(p.confidence * 100, 1),
                        "data_quality": _data_quality_label(p.seen_count, p.detection_accuracy),
                        "trustworthy": self._is_pattern_trustworthy(p),
                    }
                    for p in self._patterns.values()
                ],
            }

    def generate_postmortem(self, event_id: str) -> dict:
        with self._lock:
            event = next((e for e in self._history if e.event_id == event_id), None)
        if not event:
            return {}
        ts = time.strftime("%b %d, %Y at %I:%M %p", time.localtime(event.timestamp))
        plain_type = {
            "OOM":     "ran out of memory",
            "CRASH":   "experienced a process crash",
            "FREEZE":  "became unresponsive",
            "THERMAL": "overheated",
        }.get(event.event_type, "experienced an issue")
        return {
            "event_id": event_id, "timestamp": ts,
            "what_happened": f"Your computer {plain_type}.",
            "description": event.description, "prevented": event.prevented,
            "severity": event.severity,
            "recommendation": self._postmortem_recommendation(event.event_type),
        }

    # ------------------------------------------------------------------
    # NEW: Anomaly Explainability
    # ------------------------------------------------------------------

    def explain(self, current_metrics: dict, pattern_name: str) -> dict:
        """
        Build a plain-English explanation of why CVIS is worried about
        a given failure type, based on current metrics vs learned baseline.

        Returns a dict with:
          summary         — one-sentence headline
          evidence        — list of plain-English observations
          lead_time       — expected time to failure at current rate
          last_similar    — timestamp of last similar recorded event (or None)
          confidence_label — human label for confidence level
          triggered_by    — which metrics are driving the alert
        """
        pattern_id = f"dna_{pattern_name}" if not pattern_name.startswith("dna_") else pattern_name
        with self._lock:
            pattern = self._patterns.get(pattern_id)
            baseline = dict(self._baseline_stats)
            buffer   = list(self._metric_buffer)
            history  = list(self._history)

        if not pattern:
            return {"summary": "No pattern data available yet.", "evidence": []}

        snapshot = self._extract_snapshot(current_metrics)
        evidence = []
        triggered_by = []

        # --- Compare current readings against learned baseline ---
        metric_map = {
            "cpu":     ("cpu_percent",     current_metrics.get("cpu_percent",  0)),
            "mem":     ("memory",          current_metrics.get("memory",       0)),
            "disk":    ("disk_percent",    current_metrics.get("disk_percent", 0)),
            "net":     ("network_percent", current_metrics.get("network_percent", 0)),
            "anomaly": ("ensemble_score",  current_metrics.get("ensemble_score",  0)),
        }

        relevant_keys = _PATTERN_TRIGGERS.get(pattern_name, list(metric_map.keys()))

        for key in relevant_keys:
            if key not in metric_map:
                continue
            api_key, current_val = metric_map[key]
            label = _METRIC_LABELS.get(key, key)

            if key in baseline:
                b = baseline[key]
                mean_val = b["mean"]
                std_val  = max(0.1, b["std"])

                # Format values
                if key == "anomaly":
                    cur_str  = f"{current_val:.2f}"
                    mean_str = f"{mean_val:.2f}"
                    unit     = ""
                else:
                    cur_str  = f"{current_val:.1f}"
                    mean_str = f"{mean_val:.1f}"
                    unit     = "%"

                # High deviation — primary signal
                if current_val > mean_val + 2 * std_val:
                    evidence.append(
                        f"{label} is {cur_str}{unit} — significantly above your normal of {mean_str}{unit}"
                    )
                    triggered_by.append(key)

                # Moderate deviation — supporting signal
                elif current_val > mean_val + std_val:
                    evidence.append(
                        f"{label} is {cur_str}{unit} — above your usual {mean_str}{unit}"
                    )
                    triggered_by.append(key)

            else:
                # No baseline yet — compare against fixed safe thresholds
                threshold = _NORMAL_THRESHOLDS.get(key)
                if threshold and current_val > threshold:
                    label = _METRIC_LABELS.get(key, key)
                    unit  = "" if key == "anomaly" else "%"
                    evidence.append(
                        f"{label} is {current_val:.1f}{unit} — above the safe threshold of {threshold}{unit}"
                    )
                    triggered_by.append(key)

        # --- Recent trend from buffer (last 10 readings) ---
        if len(buffer) >= 10:
            recent_10 = buffer[-10:]
            for key in relevant_keys:
                vals = [s.get(key, 0) for s in recent_10]
                if len(vals) >= 2:
                    trend = vals[-1] - vals[0]
                    label = _METRIC_LABELS.get(key, key)
                    unit  = "" if key == "anomaly" else "%"
                    if trend > 8:
                        evidence.append(
                            f"{label} has risen {trend:.1f}{unit} over the last 10 readings"
                        )
                    elif trend < -8:
                        evidence.append(
                            f"{label} has dropped {abs(trend):.1f}{unit} over the last 10 readings"
                        )

        # --- Historical match --- 
        last_similar = None
        similar_events = [
            e for e in sorted(history, key=lambda x: x.timestamp, reverse=True)
            if e.event_type == pattern_name
        ]
        if similar_events:
            last_event = similar_events[0]
            last_similar = time.strftime(
                "%b %d, %Y at %I:%M %p", time.localtime(last_event.timestamp)
            )
            evidence.append(
                f"CVIS has seen this {pattern_name} pattern {len(similar_events)} time(s) on this machine — "
                f"last occurred {last_similar}"
            )

        # --- Pattern-specific context from known steps ---
        if pattern.plain_steps:
            evidence.append(
                f"Typical progression: {pattern.plain_steps[1] if len(pattern.plain_steps) > 1 else pattern.plain_steps[0]}"
            )

        # --- If no evidence found, explain why ---
        if not evidence:
            evidence.append(
                "Metrics are within normal range — this is an early anomaly signal based on ML pattern matching."
            )

        # --- Current matcher state ---
        # Use the same live matcher used by predict() so the explanation
        # cannot disagree with the prediction's confidence or ETA.
        try:
            match_confidence, match_eta = self._match_pattern(
                pattern,
                buffer + [snapshot],
            )
        except Exception:
            match_confidence = pattern.confidence
            match_eta = pattern.avg_lead_time_minutes

        conf_pct = int(round(match_confidence * 100))
        eta_minutes = max(0.0, float(match_eta))
        eta_str = f"~{int(round(eta_minutes))} minutes"

        summary = self._build_explanation_summary(
            pattern_name,
            conf_pct,
            eta_str,
            len(similar_events) if similar_events else 0,
        )

        # --- Confidence label ---
        if conf_pct >= 90:
            confidence_label = "Very high — strong signal"
        elif conf_pct >= 75:
            confidence_label = "High — reliable signal"
        elif conf_pct >= 60:
            confidence_label = "Moderate — pattern emerging"
        else:
            confidence_label = "Low — early indication"

        return {
            "summary":          summary,
            "evidence":         evidence,
            "lead_time":        f"{eta_str} at current trajectory",
            "last_similar":     last_similar,
            "confidence_label": confidence_label,
            "triggered_by":     triggered_by,
            "pattern_seen":     pattern.seen_count,
            "trustworthy":      self._is_pattern_trustworthy(pattern),
        }

    def explain_prediction(self, prediction: ActivePrediction, current_metrics: dict) -> dict:
        """
        Build an explanation using the live ActivePrediction state.

        The prediction object is the source of truth for the current ETA
        and confidence. Historical pattern statistics remain useful for
        context, but must not overwrite the live prediction state.
        """
        explanation = self.explain(
            current_metrics,
            prediction.failure_type
        )

        eta = max(0.0, float(prediction.minutes_remaining))
        conf = float(prediction.confidence)

        if eta < 1:
            eta_str = "less than a minute"
        elif eta < 2:
            eta_str = "about 1 minute"
        else:
            eta_str = f"about {int(round(eta))} minutes"

        conf_pct = int(round(conf * 100))

        explanation["lead_time"] = (
            f"{eta_str} at current trajectory"
        )

        explanation["confidence_label"] = (
            "Very high — strong signal" if conf >= 0.90 else
            "High — strong signal" if conf >= 0.75 else
            "Moderate — early signal" if conf >= 0.60 else
            "Low — weak signal"
        )

        explanation["current_eta_minutes"] = round(eta, 1)
        explanation["current_confidence"] = conf_pct

        return explanation

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_explanation_summary(self, failure_type: str, conf_pct: int, eta_str: str, occurrences: int) -> str:
        base = {
            "OOM":        f"Memory is building toward exhaustion ({conf_pct}% confidence, {eta_str} away)",
            "CRASH":      f"CPU pattern matches a pre-crash signature ({conf_pct}% confidence, {eta_str} away)",
            "THERMAL":    f"Sustained CPU load is heading toward thermal throttling ({conf_pct}% confidence)",
            "FREEZE":     f"Disk and CPU activity suggests the system may become unresponsive ({conf_pct}% confidence)",
            "CPU_STRESS": f"CPU stress pattern detected ({conf_pct}% confidence, {eta_str} away)",
            "DISK_FULL":  f"Disk is filling at a rate that will cause issues ({conf_pct}% confidence, {eta_str} away)",
        }.get(failure_type, f"An anomalous pattern matching {failure_type} has been detected ({conf_pct}% confidence)")

        if occurrences >= 15:
            base += f" — this exact pattern has preceded {occurrences} events on your machine"
        elif occurrences > 0:
            base += f" — seen {occurrences} time(s) previously on this machine"

        return base

    def _extract_snapshot(self, metrics: dict) -> dict:
        def safe_float(value, default=0.0):
            try:
                if value is None:
                    return default
                value = float(value)
                if not np.isfinite(value):
                    return default
                return value
            except (TypeError, ValueError):
                return default

        return {
            "cpu":     safe_float(metrics.get("cpu_percent", 0)),
            "mem":     safe_float(metrics.get("memory", 0)),
            "disk":    safe_float(metrics.get("disk_percent", 0)),
            "net":     safe_float(metrics.get("network_percent", 0)),
            "anomaly": safe_float(metrics.get("anomaly_score", 0)),
            "t":       time.time(),
        }

    def _update_baseline(self, snapshot: dict):
        for key in ["cpu", "mem", "disk", "net", "anomaly"]:
            val = float(snapshot.get(key, 0))

            if key not in self._baseline_stats:
                self._baseline_stats[key] = {
                    "mean": val,
                    "m2": 0.0,
                    "std": 1.0,
                    "n": 1,
                }
                continue

            s = self._baseline_stats[key]

            n_old = s["n"]
            n_new = min(n_old + 1, 10000)

            old_mean = s["mean"]
            delta = val - old_mean

            # Welford online variance update
            new_mean = old_mean + delta / n_new
            delta2 = val - new_mean

            s["m2"] = s.get("m2", 0.0) + delta * delta2
            s["mean"] = new_mean
            s["n"] = n_new

            if n_new > 1:
                variance = s["m2"] / (n_new - 1)
                s["std"] = max(0.1, float(np.sqrt(variance)))
            else:
                s["std"] = 1.0

    def _to_z_scores(self, snapshot: dict) -> np.ndarray:
        z = []
        for key in ["cpu","mem","disk","net","anomaly"]:
            val = snapshot.get(key, 0)
            if key in self._baseline_stats:
                s = self._baseline_stats[key]
                z.append((val - s["mean"]) / max(0.1, s["std"]))
            else:
                z.append(0.0)
        return np.array(z, dtype=np.float32)

    def learn(self, event):
        """Public learning contract.

        Learn from a FailureEvent, retain the event in history, and
        persist both learned patterns and history.
        """
        with self._lock:
            self._learn_pattern(event)
            self._history.append(event)
            self._save()
        return event

    def _learn_pattern(self, event: FailureEvent):
        if len(event.pre_snapshot) < 10:
            return
        snapshots  = event.pre_snapshot
        pattern_id = f"dna_{event.event_type}"
        if pattern_id not in self._patterns:
            self._patterns[pattern_id] = FailurePattern(
                pattern_id=pattern_id, failure_type=event.event_type)
        pattern = self._patterns[pattern_id]
        sample_points = []
        n = len(snapshots)
        for minutes_before in [5, 15, 30, 60]:
            idx = max(0, n - minutes_before)
            if idx < n:
                sample_points.append({
                    "minutes_before": minutes_before,
                    "z_scores": self._to_z_scores(snapshots[idx]).tolist(),
                })
        if not pattern.signature_steps:
            pattern.signature_steps  = [p["z_scores"] for p in sample_points]
            pattern.signature_timing = [p["minutes_before"] for p in sample_points]
        else:
            alpha = 0.3
            for i, sp in enumerate(sample_points):
                if i < len(pattern.signature_steps):
                    old = np.array(pattern.signature_steps[i])
                    new = np.array(sp["z_scores"])
                    pattern.signature_steps[i] = (alpha*new + (1-alpha)*old).tolist()
        pattern.seen_count            += 1
        pattern.last_seen              = time.time()
        pattern.avg_lead_time_minutes  = (
            0.7 * pattern.avg_lead_time_minutes + 0.3 * 30.0
            if pattern.avg_lead_time_minutes else 30.0
        )
        # Learning more examples increases historical pattern confidence,
        # but does NOT imply that predictions were correct.
        pattern.confidence = min(
            0.95,
            0.4 + pattern.seen_count * 0.1
        )

        # Do not manufacture prediction accuracy from the number
        # of failure observations. Accuracy must come only from
        # validated predictions in resolve_prediction().

        # detection_accuracy is updated only when an active prediction
        # is explicitly resolved as correct or incorrect.
        pattern.plain_description = self._build_plain_description(
            event.event_type
        )

    def _match_pattern(self, pattern: FailurePattern, current_buffer: list) -> tuple:
        """
        Match a learned failure signature against the current trajectory.

        Historical similarity alone is not sufficient for an active prediction.
        The current system must also show live evidence and a relevant rising
        trajectory before confidence can become meaningful.
        """
        if not pattern.signature_steps or len(current_buffer) < 10:
            return 0.0, 60.0

        # Evaluate the most recent trajectory window. Once an active
        # prediction exists, repeated identical post-detection samples
        # must not displace the learned failure progression.
        window_size = max(10, len(pattern.signature_steps) * 2 + 2)
        recent = current_buffer[-min(window_size, len(current_buffer)):]
        current_z = np.array(
            [self._to_z_scores(s) for s in recent],
            dtype=np.float32
        )

        signatures = [
            np.asarray(sig, dtype=np.float32)
            for sig in pattern.signature_steps
        ]

        step_scores = []
        positions = []
        start_pos = 0

        for sig in signatures:
            if start_pos >= len(current_z):
                break

            candidates = current_z[start_pos:]
            dists = np.linalg.norm(candidates - sig, axis=1)

            if len(dists) == 0:
                break

            local_idx = int(np.argmin(dists))
            distance = float(dists[local_idx])
            similarity = 1.0 / (1.0 + distance)

            # Do not accept extremely distant historical points as matches.
            if distance > 4.0:
                continue

            step_scores.append(similarity)
            actual_pos = start_pos + local_idx
            positions.append(actual_pos)
            start_pos = actual_pos + 1

        if not step_scores:
            return 0.0, 60.0

        coverage = len(step_scores) / max(1, len(signatures))

        if len(step_scores) == len(signatures):
            weights = np.arange(1, len(step_scores) + 1, dtype=np.float32)
            sequence_score = float(
                np.average(np.asarray(step_scores), weights=weights)
            )
        else:
            sequence_score = float(np.mean(step_scores))

        # Complete historical progression is useful, but cannot by itself
        # create a live prediction.
        progression_bonus = 0.05 if len(step_scores) == len(signatures) else 0.0

        latest = current_z[-1]
        cpu_z, mem_z, disk_z, net_z, anomaly_z = latest

        signal_boost = 0.0

        if pattern.failure_type == "OOM":
            live_signal = max(0.0, min(1.0, (mem_z - 0.5) / 2.0))
            live_signal += max(0.0, min(0.5, (anomaly_z - 0.3)))
        elif pattern.failure_type == "CRASH":
            live_signal = max(0.0, min(1.0, (cpu_z - 0.8) / 2.0))
            live_signal += max(0.0, min(0.5, (anomaly_z - 0.3)))
        elif pattern.failure_type == "THERMAL":
            live_signal = max(0.0, min(1.0, (cpu_z - 0.8) / 2.0))
        else:
            live_signal = max(0.0, min(1.0, anomaly_z))

        signal_boost = min(0.20, live_signal * 0.20)

        # Measure the recent direction of the relevant metric.
        trend = 0.0

        if len(current_z) >= 5:
            earlier = current_z[-5]

            if pattern.failure_type == "OOM":
                trend = float(latest[1] - earlier[1])
            elif pattern.failure_type in ("CRASH", "THERMAL"):
                trend = float(latest[0] - earlier[0])
            else:
                trend = float(latest[4] - earlier[4])

        # Only a rising trajectory receives a positive trend contribution.
        trend_boost = max(0.0, min(0.10, trend * 0.05))

        # Flat/falling trajectories must actively suppress predictions.
        # Strongly rising trajectories should not be penalized: the live
        # direction is evidence supporting the failure progression.
        if trend > 0.20:
            trend_factor = 1.0
        elif trend > 0:
            trend_factor = 0.85 + (trend / 0.20) * 0.15
        else:
            trend_factor = max(0.0, min(0.50, 0.5 + trend * 0.5))

        base_confidence = (
            0.45 * sequence_score
            + 0.15 * coverage
            + 0.10 * pattern.confidence
            + progression_bonus
            + signal_boost
            + trend_boost
        )

        # Current live evidence is mandatory. Historical matching alone
        # cannot produce a strong prediction.
        if live_signal < 0.10:
            base_confidence *= 0.35

        # A non-rising trajectory suppresses the prediction further.
        if trend <= 0:
            base_confidence *= 0.50

        base_confidence *= trend_factor

        base_confidence = float(max(0.0, min(0.99, base_confidence)))

        # ETA should not collapse purely because historical similarity is high.
        # Use the learned lead time only when current evidence is meaningful.
        if base_confidence >= 0.70 and live_signal >= 0.35 and trend > 0:
            eta_factor = max(0.35, 1.0 - base_confidence * 0.65)
            eta = pattern.avg_lead_time_minutes * eta_factor
        elif base_confidence >= 0.50 and live_signal >= 0.20 and trend > 0:
            eta = pattern.avg_lead_time_minutes
        else:
            eta = 60.0

        return base_confidence, float(max(5.0, min(60.0, eta)))

    def _get_active_prediction(self, pattern_id: str):
        now = time.time()

        with self._lock:
            candidates = [
                pred for pred in self._active_predictions.values()
                if (
                    pred.pattern_id == pattern_id
                    and not pred.resolved
                    and (
                        pred.predicted_eta is None
                        or pred.predicted_eta > now
                    )
                )
            ]

            if not candidates:
                return None

            # There should normally be only one active prediction per
            # pattern. If multiple exist, retain the newest valid one.
            return max(
                candidates,
                key=lambda pred: pred.detected_at
            )

    def _severity_from_eta(self, eta: float, conf: float) -> str:
        if eta <= 10 and conf > 0.7: return "CRITICAL"
        if eta <= 20 and conf > 0.6: return "HIGH"
        if eta <= 45:                return "MEDIUM"
        return "LOW"

    def _plain_prediction_message(self, pattern, eta, conf) -> str:
        eta_str  = f"in about {int(eta)} minutes" if eta > 2 else "very soon"
        conf_pct = int(conf * 100)
        msgs = {
            "OOM":     f"Your computer is likely to run out of memory {eta_str}",
            "CRASH":   f"A process crash is predicted {eta_str}",
            "FREEZE":  f"Your system may become unresponsive {eta_str}",
            "THERMAL": f"Overheating is likely {eta_str}",
        }
        base = msgs.get(pattern.failure_type, f"A system issue is predicted {eta_str}")
        if pattern.seen_count >= 15:
            base += f" — seen this pattern {pattern.seen_count} times on this machine"
        else:
            base += f" — early signal ({pattern.seen_count} observations, still learning)"
        return base

    def _plain_action(self, pattern) -> str:
        return {
            "OOM":     "Close unused browser tabs and restart memory-heavy applications",
            "CRASH":   "Save your work and restart the affected application",
            "FREEZE":  "Save your work now — the system may stop responding shortly",
            "THERMAL": "Close heavy applications and improve airflow around your computer",
        }.get(pattern.failure_type, "Save your work and monitor the situation")

    def _build_plain_description(self, event_type: str) -> str:
        return {
            "OOM":     "Memory fills up before the system runs out",
            "CRASH":   "CPU and anomaly scores spike before a process terminates",
            "FREEZE":  "Disk space utilization saturates before the system becomes unresponsive",
            "THERMAL": "CPU usage stays high leading to thermal throttling",
        }.get(event_type, "Unusual metric pattern precedes this failure type")

    def _postmortem_recommendation(self, event_type: str) -> str:
        return {
            "OOM":     "Consider adding more RAM or closing memory-heavy apps during heavy sessions.",
            "CRASH":   "Check application logs. Update the affected software if available.",
            "FREEZE":  "Restart to clear accumulated state. Check disk health.",
            "THERMAL": "Clean cooling vents and ensure adequate airflow.",
        }.get(event_type, "Monitor the system and consult logs for more details.")

    def _save(self):
        try:
            dna_data = {
                "patterns": {
                    k: asdict(v) for k, v in self._patterns.items()
                },
                # Persist both active and resolved predictions so
                # prediction outcomes survive restart. Resolved entries
                # remain historical state and are excluded from active
                # matching by _get_active_prediction()/predict().
                "active_predictions": {
                    k: asdict(v)
                    for k, v in self._active_predictions.items()
                },
            }

            with open(self.DNA_FILE, "w") as f:
                json.dump(dna_data, f, indent=2)

            history_data = [asdict(e) for e in self._history[-200:]]
            with open(self.HISTORY_FILE, "w") as f:
                json.dump(history_data, f, indent=2)

        except Exception:
            pass

    def _load(self):
        try:
            if os.path.exists(self.DNA_FILE):
                with open(self.DNA_FILE) as f:
                    data = json.load(f)

                # Backward compatibility with the old format where
                # pattern IDs were stored directly at the top level.
                if "patterns" in data:
                    pattern_data = data.get("patterns", {})
                    prediction_data = data.get("active_predictions", {})
                else:
                    pattern_data = data
                    prediction_data = {}

                for k, v in pattern_data.items():
                    self._patterns[k] = FailurePattern(**v)

                for k, v in prediction_data.items():
                    try:
                        prediction = ActivePrediction(**v)

                        # Restore both active and resolved predictions.
                        # Resolved predictions remain historical state.
                        # Only unresolved predictions are eligible for active
                        # matching; resolved entries remain available for
                        # lifecycle/history inspection after restart.
                        self._active_predictions[k] = prediction
                    except Exception:
                        # Ignore malformed individual predictions without
                        # preventing the rest of the DNA state from loading.
                        continue

            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE) as f:
                    data = json.load(f)

                for item in data:
                    self._history.append(FailureEvent(**item))

        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data_quality_label(seen: int, accuracy: Optional[float]) -> str:
    """Human-readable data quality label shown on dashboard."""

    # Failure observations alone do not establish prediction accuracy.
    if accuracy is None:
        if seen >= 7:
            return "low — prediction accuracy not yet validated"
        return "insufficient — not yet reliable"

    if seen >= 20 and accuracy >= 0.85:
        return "high — well trained"
    if seen >= 15 and accuracy >= 0.70:
        return "medium — learning"
    if seen >= 7:
        return "low — early stage"

    return "insufficient — not yet reliable"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_dna_engine = None
_dna_lock   = threading.Lock()

def get_dna_engine() -> FailureDNAEngine:
    global _dna_engine
    with _dna_lock:
        if _dna_engine is None:
            _dna_engine = FailureDNAEngine()
    return _dna_engine
