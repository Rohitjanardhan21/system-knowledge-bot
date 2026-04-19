import json
from pathlib import Path
from statistics import mean, stdev
from datetime import datetime
import math

# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------
HISTORY_FILE = Path("system_facts/history/learning.json")
WEIGHTS_FILE = Path("system_facts/history/action_weights.json")

HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 200


class LearningEngine:

    def __init__(self):
        self.history = self.load_history()
        self.action_weights = self.load_weights()

    # ---------------------------------------------------------
    # SAFE LOAD / SAVE
    # ---------------------------------------------------------
    def load_history(self):
        if HISTORY_FILE.exists():
            try:
                data = json.loads(HISTORY_FILE.read_text())
                return [h for h in data if isinstance(h, dict)]
            except:
                return []
        return []

    def save_history(self):
        try:
            HISTORY_FILE.write_text(
                json.dumps(self.history[-MAX_HISTORY:], indent=2)
            )
        except:
            pass

    def load_weights(self):
        if WEIGHTS_FILE.exists():
            try:
                return json.loads(WEIGHTS_FILE.read_text())
            except:
                return {}
        return {}

    def save_weights(self):
        try:
            WEIGHTS_FILE.write_text(
                json.dumps(self.action_weights, indent=2)
            )
        except:
            pass

    # ---------------------------------------------------------
    # CLEAN VALUE
    # ---------------------------------------------------------
    def safe_float(self, v):
        try:
            val = float(v)
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return val
        except:
            return 0.0

    # ---------------------------------------------------------
    # UPDATE HISTORY
    # ---------------------------------------------------------
    def update(self, metrics):

        entry = {
            "time": datetime.utcnow().isoformat(),
            "cpu": self.safe_float(metrics.get("cpu")),
            "memory": self.safe_float(metrics.get("memory")),
            "disk": self.safe_float(metrics.get("disk")),
            "context": metrics.get("context", "unknown"),
            "intent": metrics.get("intent", "unknown")
        }

        self.history.append(entry)
        self.save_history()

    # ---------------------------------------------------------
    # BASELINE
    # ---------------------------------------------------------
    def _compute_stats(self, values):

        values = [self.safe_float(v) for v in values]

        if len(values) < 5:
            return {"mean": 0.0, "std": 0.0}

        try:
            return {
                "mean": mean(values),
                "std": stdev(values) if len(values) > 1 else 0.0
            }
        except:
            return {"mean": 0.0, "std": 0.0}

    def get_baseline(self):

        cpu_vals = [h.get("cpu", 0) for h in self.history]
        mem_vals = [h.get("memory", 0) for h in self.history]
        disk_vals = [h.get("disk", 0) for h in self.history]

        return {
            "cpu": self._compute_stats(cpu_vals),
            "memory": self._compute_stats(mem_vals),
            "disk": self._compute_stats(disk_vals)
        }

    # ---------------------------------------------------------
    # ANOMALY DETECTION
    # ---------------------------------------------------------
    def detect_anomalies(self, metrics):

        baseline = self.get_baseline()
        anomalies = []

        for key in ["cpu", "memory", "disk"]:

            current = self.safe_float(metrics.get(key))
            mean_val = baseline[key]["mean"]
            std_val = baseline[key]["std"]

            if std_val <= 0:
                continue

            deviation = current - mean_val

            if deviation > 2 * std_val:
                severity = "high" if deviation > 3 * std_val else "medium"

                anomalies.append({
                    "metric": key,
                    "value": round(current, 2),
                    "baseline": round(mean_val, 2),
                    "deviation": round(deviation, 2),
                    "severity": severity
                })

        return anomalies

    # ---------------------------------------------------------
    # PATTERNS
    # ---------------------------------------------------------
    def detect_patterns(self):

        if len(self.history) < 20:
            return []

        cpu_vals = [h.get("cpu", 0) for h in self.history[-20:]]

        patterns = []

        if sum(1 for v in cpu_vals if v > 80) > 5:
            patterns.append("Frequent CPU spikes")

        if all(v > 60 for v in cpu_vals[-5:]):
            patterns.append("Sustained high load")

        return patterns

    # ---------------------------------------------------------
    # TRENDS
    # ---------------------------------------------------------
    def detect_trends(self):

        if len(self.history) < 10:
            return []

        cpu_vals = [h.get("cpu", 0) for h in self.history[-10:]]

        if cpu_vals[-1] > cpu_vals[0] + 10:
            return ["Increasing load trend"]

        if cpu_vals[-1] < cpu_vals[0] - 10:
            return ["Decreasing load trend"]

        return []

    # ---------------------------------------------------------
    # PREDICTION
    # ---------------------------------------------------------
    def predict_next(self):

        if len(self.history) < 5:
            return None

        recent = [h.get("cpu", 0) for h in self.history[-5:]]

        trend = (recent[-1] - recent[0]) / max(len(recent), 1)

        return round(recent[-1] + trend * 3, 2)

    # ---------------------------------------------------------
    # RISK
    # ---------------------------------------------------------
    def compute_risk(self, anomalies):

        if not anomalies:
            return {"level": "LOW", "score": 0.2}

        severity_map = {"medium": 0.5, "high": 0.9}

        score = max(severity_map.get(a["severity"], 0.2) for a in anomalies)

        level = "HIGH" if score > 0.8 else "MEDIUM"

        return {"level": level, "score": score}

    # ---------------------------------------------------------
    # LEARNING FROM FEEDBACK
    # ---------------------------------------------------------
    def learn_from_feedback(self, action, success):

        if action not in self.action_weights:
            self.action_weights[action] = 0.5

        if success:
            self.action_weights[action] += 0.05
        else:
            self.action_weights[action] -= 0.05

        self.action_weights[action] = max(
            0.1, min(1.0, self.action_weights[action])
        )

        self.save_weights()

    def get_action_weight(self, action):
        return self.action_weights.get(action, 0.5)

    # ---------------------------------------------------------
    # FULL ANALYSIS
    # ---------------------------------------------------------
    def analyze(self, metrics):

        self.update(metrics)

        anomalies = self.detect_anomalies(metrics)

        return {
            "baseline": self.get_baseline(),
            "anomalies": anomalies,
            "patterns": self.detect_patterns(),
            "trends": self.detect_trends(),
            "prediction": self.predict_next(),
            "risk": self.compute_risk(anomalies)
        }
