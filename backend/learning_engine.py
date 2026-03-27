import json
from pathlib import Path
from statistics import mean, stdev
from datetime import datetime

HISTORY_FILE = Path("system_facts/history/learning.json")
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 200


class LearningEngine:

    def __init__(self):
        self.history = self.load_history()

    # -----------------------------------------
    # LOAD / SAVE
    # -----------------------------------------
    def load_history(self):
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text())
        return []

    def save_history(self):
        HISTORY_FILE.write_text(json.dumps(self.history[-MAX_HISTORY:], indent=2))

    # -----------------------------------------
    # UPDATE HISTORY
    # -----------------------------------------
    def update(self, metrics):
        entry = {
            "time": datetime.utcnow().isoformat(),
            "cpu": metrics.get("cpu", 0),
            "memory": metrics.get("memory", 0),
            "disk": metrics.get("disk", 0)
        }

        self.history.append(entry)
        self.save_history()

    # -----------------------------------------
    # 🔥 ADAPTIVE THRESHOLDS
    # -----------------------------------------
    def get_thresholds(self):
        if len(self.history) < 10:
            return {
                "cpu_high": 85,
                "memory_high": 85
            }

        cpu_values = [h["cpu"] for h in self.history]
        mem_values = [h["memory"] for h in self.history]

        cpu_mean = mean(cpu_values)
        cpu_std = stdev(cpu_values) if len(cpu_values) > 1 else 0

        mem_mean = mean(mem_values)
        mem_std = stdev(mem_values) if len(mem_values) > 1 else 0

        return {
            "cpu_high": min(95, cpu_mean + 2 * cpu_std),
            "memory_high": min(95, mem_mean + 2 * mem_std)
        }

    # -----------------------------------------
    # 🔥 ANOMALY DETECTION
    # -----------------------------------------
    def detect_anomalies(self, metrics):
        thresholds = self.get_thresholds()

        anomalies = []

        if metrics.get("cpu", 0) > thresholds["cpu_high"]:
            anomalies.append("CPU anomaly")

        if metrics.get("memory", 0) > thresholds["memory_high"]:
            anomalies.append("Memory anomaly")

        return anomalies

    # -----------------------------------------
    # 🔥 PATTERN DETECTION
    # -----------------------------------------
    def detect_patterns(self):
        if len(self.history) < 20:
            return []

        cpu_values = [h["cpu"] for h in self.history[-20:]]

        spikes = sum(1 for v in cpu_values if v > 80)

        patterns = []

        if spikes > 5:
            patterns.append("Frequent CPU spikes")

        return patterns
