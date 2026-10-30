import json
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from statistics import StatisticsError, mean, stdev
from datetime import datetime, timezone
import math

log = logging.getLogger("cvis.learning")

# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------
HISTORY_FILE = Path("system_facts/history/learning.json")
WEIGHTS_FILE = Path("system_facts/history/action_weights.json")
STATS_FILE = Path("system_facts/history/action_statistics.json")

HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 200
SUPPORTED_FEEDBACK_ACTIONS = frozenset({
    "optimize_memory",
    "reduce_compute_load",
    "optimize_io",
    "inspect_mechanics",
    "increase_cooling",
    "stabilize_power",
    "monitor",
    "immediate_stabilization",
})
ACTION_ALIASES = {
    "clear_temp": "optimize_io",
    "clear_docker_cache": "optimize_io",
    "clear_logs": "optimize_io",
    "clear_pip_cache": "optimize_io",
    "drop_caches": "optimize_memory",
    "kill_process": "reduce_compute_load",
    "kill_high_cpu_process": "reduce_compute_load",
    "throttle_process": "reduce_compute_load",
}


class LearningEngine:

    def __init__(self, workspace_id="global"):
        self.workspace_id = self._normalize_workspace_id(workspace_id)
        if self.workspace_id == "global":
            self._history_file = HISTORY_FILE
            self._weights_file = WEIGHTS_FILE
            self._stats_file = STATS_FILE
        else:
            workspace_dir = HISTORY_FILE.parent / "workspaces" / (
                hashlib.sha256(self.workspace_id.encode()).hexdigest()[:16]
            )
            self._history_file = workspace_dir / "learning.json"
            self._weights_file = workspace_dir / "action_weights.json"
            self._stats_file = workspace_dir / "action_statistics.json"
        self.history = self.load_history()
        self.action_weights = self.load_weights()
        self.action_stats = self.load_stats()

    @staticmethod
    def _normalize_workspace_id(workspace_id):
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            return "global"
        return workspace_id.strip()[:128]

    # ---------------------------------------------------------
    # SAFE LOAD / SAVE
    # ---------------------------------------------------------
    def load_history(self):
        if self._history_file.exists():
            try:
                data = json.loads(self._history_file.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    raise ValueError("Learning history must be a list")
                return [h for h in data if isinstance(h, dict)]
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Unable to load learning history: {self._history_file}") from exc
        return []

    def save_history(self):
        self._atomic_write(self._history_file, self.history[-MAX_HISTORY:])

    def load_weights(self):
        if self._weights_file.exists():
            try:
                data = json.loads(self._weights_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Unable to load learning weights: {self._weights_file}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"Learning weights must be an object: {self._weights_file}")
            return {
                action: self.safe_float(weight)
                for action, weight in data.items()
                if action in SUPPORTED_FEEDBACK_ACTIONS
            }
        return {}

    def save_weights(self):
        self._atomic_write(self._weights_file, self.action_weights)

    def load_stats(self):
        if not self._stats_file.exists():
            return {}
        try:
            data = json.loads(self._stats_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unable to load learning statistics: {self._stats_file}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Learning statistics must be an object: {self._stats_file}")
        return {
            action: stats
            for action, stats in data.items()
            if action in SUPPORTED_FEEDBACK_ACTIONS and isinstance(stats, dict)
        }

    def save_stats(self):
        self._atomic_write(self._stats_file, self.action_stats)

    @staticmethod
    def _atomic_write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as destination:
                temp_path = destination.name
                json.dump(value, destination, indent=2)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temp_path, path)
        except OSError as exc:
            raise RuntimeError(f"Unable to persist learning state: {path}") from exc
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)

    # ---------------------------------------------------------
    # CLEAN VALUE
    # ---------------------------------------------------------
    def safe_float(self, v):
        try:
            val = float(v)
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return val
        except (TypeError, ValueError):
            return 0.0

    # ---------------------------------------------------------
    # UPDATE HISTORY
    # ---------------------------------------------------------
    def update(self, metrics):

        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
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
        except (TypeError, ValueError, StatisticsError):
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
    def learn_from_feedback(self, action, verification):
        self.record_outcome(action, verification, trusted=False)

    def record_outcome(self, action, verification, *, trusted=False):
        action = ACTION_ALIASES.get(action, action)
        if not isinstance(action, str) or action not in SUPPORTED_FEEDBACK_ACTIONS:
            raise ValueError("Unsupported feedback action")

        if not isinstance(verification, dict):
            raise ValueError("Verified successful outcome evidence is required")

        status = verification.get("status")
        verified = verification.get("verified") is True
        if not trusted and (status != "success" or not verified):
            raise ValueError("Verified successful outcome evidence is required")
        if status not in {"success", "partial", "failed"}:
            raise ValueError("Outcome evidence has an unsupported status")

        stats = self.action_stats.setdefault(
            action,
            {"successes": 0, "partials": 0, "failures": 0},
        )
        if status == "success" and verified:
            stats["successes"] = int(stats.get("successes", 0)) + 1
        elif status == "partial":
            stats["partials"] = int(stats.get("partials", 0)) + 1
        else:
            stats["failures"] = int(stats.get("failures", 0)) + 1

        effective_successes = stats["successes"] + stats["partials"] * 0.5
        total = effective_successes + stats["failures"] + 2.0
        self.action_weights[action] = max(
            0.1,
            min(0.9, (effective_successes + 1.0) / total),
        )
        stats["last_outcome"] = status
        stats["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.save_weights()
        self.save_stats()

    def get_action_weight(self, action):
        action = ACTION_ALIASES.get(action, action)
        return max(0.1, min(0.9, self.safe_float(
            self.action_weights.get(action, 0.5)
        )))

    def get_action_stats(self, action):
        action = ACTION_ALIASES.get(action, action)
        stats = self.action_stats.get(action, {})
        return {
            "successes": int(stats.get("successes", 0)),
            "partials": int(stats.get("partials", 0)),
            "failures": int(stats.get("failures", 0)),
            "samples": sum(
                int(stats.get(key, 0))
                for key in ("successes", "partials", "failures")
            ),
            "weight": self.get_action_weight(action),
            "last_outcome": stats.get("last_outcome"),
        }

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


_learning_engines = {}


def get_learning_engine(workspace_id="global"):
    normalized_id = LearningEngine._normalize_workspace_id(workspace_id)
    if normalized_id not in _learning_engines:
        _learning_engines[normalized_id] = LearningEngine(normalized_id)
    return _learning_engines[normalized_id]
