"""
CVIS Failure DNA Engine
Learns your machine's unique failure fingerprint.
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
    detection_accuracy:    float = 0.0
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
        detection_accuracy=0.78, confidence=0.72,
        signature_steps=[[0.2,2.1,0.4,0.1,0.3],[0.3,2.8,0.6,0.2,0.5],[0.4,3.2,0.8,0.3,0.8],[0.6,3.8,1.2,0.4,1.4]],
        signature_timing=[60,30,15,5],
        plain_description="Memory climbs steadily for 30-60 minutes before the system runs out",
        plain_steps=["60 min before: Memory starts rising","30 min before: Memory crosses 75%","15 min before: Memory above 85%","5 min before: Crash imminent"],
    ),
    "dna_CRASH": FailurePattern(
        pattern_id="dna_CRASH", failure_type="CRASH", seen_count=8,
        prevented_count=2, avg_lead_time_minutes=22.0,
        detection_accuracy=0.71, confidence=0.65,
        signature_steps=[[1.8,0.4,0.3,0.2,0.4],[2.4,0.6,0.5,0.3,0.7],[3.1,0.8,0.7,0.4,1.1],[4.2,1.0,0.9,0.6,1.6]],
        signature_timing=[60,30,15,5],
        plain_description="CPU spikes before a process terminates unexpectedly",
        plain_steps=["60 min before: CPU spiking intermittently","30 min before: CPU above 70%","15 min before: Anomaly score elevated","5 min before: CPU maxed"],
    ),
    "dna_THERMAL": FailurePattern(
        pattern_id="dna_THERMAL", failure_type="THERMAL", seen_count=6,
        prevented_count=4, avg_lead_time_minutes=35.0,
        detection_accuracy=0.83, confidence=0.75,
        signature_steps=[[1.5,0.3,0.2,0.1,0.2],[2.0,0.4,0.3,0.2,0.4],[2.8,0.5,0.4,0.2,0.7],[3.5,0.6,0.5,0.3,1.0]],
        signature_timing=[60,30,15,5],
        plain_description="CPU stays high causing thermal throttling",
        plain_steps=["60 min before: CPU sustained above 60%","30 min before: No relief","15 min before: Performance degrading","5 min before: Throttling active"],
    ),
}

class FailureDNAEngine:
    DNA_FILE     = "data/failure_dna.json"
    HISTORY_FILE = "data/failure_history.json"
    PRE_FAILURE_WINDOW = 120
    MIN_CONFIDENCE     = 0.70   # raised: only fire when genuinely confident
    MIN_SAMPLES        = 15     # need 15+ observations before trusting a pattern

    def __init__(self):
        self._lock = threading.Lock()
        self._patterns: dict = {}
        self._history: list = []
        self._active_predictions: dict = {}
        self._metric_buffer: deque = deque(maxlen=self.PRE_FAILURE_WINDOW)
        self._baseline_stats: dict = {}
        os.makedirs("data", exist_ok=True)
        self._load()
        if not self._patterns:
            self._patterns = {k: v for k, v in DEFAULT_PATTERNS.items()}

    def ingest(self, metrics: dict):
        snapshot = self._extract_snapshot(metrics)
        with self._lock:
            self._metric_buffer.append(snapshot)
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
            self._save()

    def predict(self, metrics: dict) -> Optional[ActivePrediction]:
        if not self._patterns or not self._baseline_stats:
            return None
        snapshot = self._extract_snapshot(metrics)
        best_match = None
        best_confidence = 0.0
        with self._lock:
            for pattern_id, pattern in self._patterns.items():
                # Trust gate — don't predict until we have enough observations
                if pattern.seen_count < self.MIN_SAMPLES:
                    continue
                if pattern.detection_accuracy < 0.70:
                    continue
                confidence, eta_minutes = self._match_pattern(
                    pattern, list(self._metric_buffer) + [snapshot]
                )
                if confidence > best_confidence and confidence >= self.MIN_CONFIDENCE:
                    best_confidence = confidence
                    best_match = (pattern, confidence, eta_minutes)
        if not best_match:
            return None
        pattern, confidence, eta_minutes = best_match
        existing = self._get_active_prediction(pattern.pattern_id)
        if existing and not existing.resolved:
            existing.minutes_remaining = eta_minutes
            existing.predicted_eta = time.time() + eta_minutes * 60
            return existing
        pred_id = f"pred_{pattern.pattern_id}_{int(time.time())}"
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
        return prediction

    def acknowledge_prediction(self, pred_id: str, user_acted: bool = False):
        with self._lock:
            if pred_id in self._active_predictions:
                self._active_predictions[pred_id].acknowledged = True

    def resolve_prediction(self, pred_id: str, was_correct: bool):
        with self._lock:
            if pred_id in self._active_predictions:
                pred = self._active_predictions[pred_id]
                pred.resolved = True
                pred.was_correct = was_correct
                if pred.pattern_id in self._patterns:
                    p = self._patterns[pred.pattern_id]
                    p.detection_accuracy = (
                        (p.detection_accuracy * p.seen_count + (1.0 if was_correct else 0.0))
                        / (p.seen_count + 1)
                    )
                self._save()

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
        return {"score":score,"grade":grade,"color":color,"max":1000,
                "percentile":min(99,int(score/10)),"improvements":improvements[:3],
                "failure_count_7d":len(recent_failures),"patterns_learned":len(self._patterns)}

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

    def get_dna_summary(self) -> dict:
        with self._lock:
            return {
                "patterns": len(self._patterns),
                "total_failures": len(self._history),
                "prevented": sum(1 for e in self._history if e.prevented),
                "pattern_list": [
                    {"type":p.failure_type,"seen":p.seen_count,"prevented":p.prevented_count,
                     "accuracy":round(p.detection_accuracy*100,1),"lead_time":round(p.avg_lead_time_minutes,1),
                     "description":p.plain_description,"confidence":round(p.confidence*100,1),
                     "data_quality":_data_quality_label(p.seen_count, p.detection_accuracy),
                     "trustworthy":p.seen_count >= 15 and p.detection_accuracy >= 0.70}
                    for p in self._patterns.values()
                ],
            }

    def generate_postmortem(self, event_id: str) -> dict:
        with self._lock:
            event = next((e for e in self._history if e.event_id == event_id), None)
        if not event:
            return {}
        ts = time.strftime("%b %d, %Y at %I:%M %p", time.localtime(event.timestamp))
        plain_type = {"OOM":"ran out of memory","CRASH":"experienced a process crash",
                      "FREEZE":"became unresponsive","THERMAL":"overheated"}.get(event.event_type,"experienced an issue")
        return {
            "event_id":event_id,"timestamp":ts,
            "what_happened":f"Your computer {plain_type}.",
            "description":event.description,"prevented":event.prevented,"severity":event.severity,
            "recommendation":self._postmortem_recommendation(event.event_type),
        }

    def _extract_snapshot(self, metrics: dict) -> dict:
        return {"cpu":metrics.get("cpu_percent",0),"mem":metrics.get("memory",0),
                "disk":metrics.get("disk_percent",0),"net":metrics.get("network_percent",0),
                "anomaly":metrics.get("ensemble_score",0),"t":time.time()}

    def _update_baseline(self, snapshot: dict):
        for key in ["cpu","mem","disk","net","anomaly"]:
            val = snapshot.get(key, 0)
            if key not in self._baseline_stats:
                self._baseline_stats[key] = {"mean":val,"std":1.0,"n":1}
            else:
                s = self._baseline_stats[key]
                n = s["n"] + 1
                old_mean = s["mean"]
                new_mean = old_mean + (val - old_mean) / n
                s["std"] = max(0.1, s["std"] + (val-old_mean)*(val-new_mean)/max(1,n-1))
                s["mean"] = new_mean
                s["n"] = min(n, 10000)

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

    def _learn_pattern(self, event: FailureEvent):
        if len(event.pre_snapshot) < 10:
            return
        snapshots = event.pre_snapshot
        pattern_id = f"dna_{event.event_type}"
        if pattern_id not in self._patterns:
            self._patterns[pattern_id] = FailurePattern(
                pattern_id=pattern_id, failure_type=event.event_type)
        pattern = self._patterns[pattern_id]
        sample_points = []
        n = len(snapshots)
        for minutes_before in [5,15,30,60]:
            idx = max(0, n - minutes_before)
            if idx < n:
                sample_points.append({"minutes_before":minutes_before,
                                       "z_scores":self._to_z_scores(snapshots[idx]).tolist()})
        if not pattern.signature_steps:
            pattern.signature_steps = [p["z_scores"] for p in sample_points]
            pattern.signature_timing = [p["minutes_before"] for p in sample_points]
        else:
            alpha = 0.3
            for i, sp in enumerate(sample_points):
                if i < len(pattern.signature_steps):
                    old = np.array(pattern.signature_steps[i])
                    new = np.array(sp["z_scores"])
                    pattern.signature_steps[i] = (alpha*new + (1-alpha)*old).tolist()
        pattern.seen_count += 1
        pattern.last_seen = time.time()
        pattern.avg_lead_time_minutes = 0.7*pattern.avg_lead_time_minutes + 0.3*30.0 if pattern.avg_lead_time_minutes else 30.0
        pattern.confidence = min(0.95, 0.4 + pattern.seen_count*0.1)
        pattern.detection_accuracy = min(1.0, pattern.seen_count/max(1,pattern.seen_count+1))
        pattern.plain_description = self._build_plain_description(event.event_type)

    def _match_pattern(self, pattern: FailurePattern, current_buffer: list) -> tuple:
        if not pattern.signature_steps or len(current_buffer) < 10:
            return 0.0, 60.0
        recent = current_buffer[-min(30,len(current_buffer)):]
        current_z = np.array([self._to_z_scores(s) for s in recent])
        scores = []
        for sig_z in pattern.signature_steps:
            sig = np.array(sig_z)
            if len(current_z) > 0:
                dists = [np.linalg.norm(current_z[j]-sig) for j in range(len(current_z))]
                scores.append(1.0/(1.0+min(dists)))
        if not scores:
            return 0.0, 60.0
        base_confidence = np.mean(scores) * pattern.confidence
        eta = max(5.0, pattern.avg_lead_time_minutes*(1.0-base_confidence))
        return float(base_confidence), float(eta)

    def _get_active_prediction(self, pattern_id: str):
        for pred in self._active_predictions.values():
            if pred.pattern_id == pattern_id and not pred.resolved:
                return pred
        return None

    def _severity_from_eta(self, eta: float, conf: float) -> str:
        if eta<=10 and conf>0.7: return "CRITICAL"
        if eta<=20 and conf>0.6: return "HIGH"
        if eta<=45:              return "MEDIUM"
        return "LOW"

    def _plain_prediction_message(self, pattern, eta, conf) -> str:
        eta_str = f"in about {int(eta)} minutes" if eta>2 else "very soon"
        conf_pct = int(conf * 100)
        msgs = {"OOM":f"Your computer is likely to run out of memory {eta_str}",
                "CRASH":f"A process crash is predicted {eta_str}",
                "FREEZE":f"Your system may become unresponsive {eta_str}",
                "THERMAL":f"Overheating is likely {eta_str}"}
        base = msgs.get(pattern.failure_type, f"A system issue is predicted {eta_str}")
        if pattern.seen_count >= 15:
            base += f" — seen this pattern {pattern.seen_count} times on this machine"
        else:
            base += f" — early signal ({pattern.seen_count} observations, still learning)"
        return base

    def _plain_action(self, pattern) -> str:
        return {"OOM":"Close unused browser tabs and restart memory-heavy applications",
                "CRASH":"Save your work and restart the affected application",
                "FREEZE":"Save your work now — the system may stop responding shortly",
                "THERMAL":"Close heavy applications and improve airflow around your computer"
               }.get(pattern.failure_type,"Save your work and monitor the situation")

    def _build_plain_description(self, event_type: str) -> str:
        return {"OOM":"Memory fills up before the system runs out",
                "CRASH":"CPU and anomaly scores spike before a process terminates",
                "FREEZE":"Disk I/O saturates before the system becomes unresponsive",
                "THERMAL":"CPU usage stays high leading to thermal throttling"
               }.get(event_type,"Unusual metric pattern precedes this failure type")

    def _postmortem_recommendation(self, event_type: str) -> str:
        return {"OOM":"Consider adding more RAM or closing memory-heavy apps during heavy sessions.",
                "CRASH":"Check application logs. Update the affected software if available.",
                "FREEZE":"Restart to clear accumulated state. Check disk health.",
                "THERMAL":"Clean cooling vents and ensure adequate airflow."
               }.get(event_type,"Monitor the system and consult logs for more details.")

    def _save(self):
        try:
            dna_data = {k: asdict(v) for k, v in self._patterns.items()}
            with open(self.DNA_FILE,"w") as f: json.dump(dna_data,f,indent=2)
            history_data = [asdict(e) for e in self._history[-200:]]
            with open(self.HISTORY_FILE,"w") as f: json.dump(history_data,f,indent=2)
        except Exception: pass

    def _load(self):
        try:
            if os.path.exists(self.DNA_FILE):
                with open(self.DNA_FILE) as f: data = json.load(f)
                for k,v in data.items(): self._patterns[k] = FailurePattern(**v)
            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE) as f: data = json.load(f)
                for item in data: self._history.append(FailureEvent(**item))
        except Exception: pass


def _data_quality_label(seen: int, accuracy: float) -> str:
    """Human-readable data quality label shown on dashboard."""
    if seen >= 20 and accuracy >= 0.85: return "high — well trained"
    if seen >= 15 and accuracy >= 0.70: return "medium — learning"
    if seen >= 7:                        return "low — early stage"
    return "insufficient — not yet reliable"


_dna_engine = None
_dna_lock = threading.Lock()

def get_dna_engine() -> FailureDNAEngine:
    global _dna_engine
    with _dna_lock:
        if _dna_engine is None:
            _dna_engine = FailureDNAEngine()
    return _dna_engine
