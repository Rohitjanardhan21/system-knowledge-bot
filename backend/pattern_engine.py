# ---------------------------------------------------------
# 🧠 PATTERN ENGINE (ADVANCED TEMPORAL INTELLIGENCE)
# ---------------------------------------------------------

from collections import deque
from statistics import mean, stdev
from datetime import datetime


class PatternEngine:

    def __init__(self, maxlen=200):
        self.history = deque(maxlen=maxlen)
        self.pattern_memory = []

    # -----------------------------------------------------
    # UPDATE HISTORY
    # -----------------------------------------------------
    def update(self, features):

        entry = {
            "time": datetime.utcnow().isoformat(),
            **features
        }

        self.history.append(entry)

    # -----------------------------------------------------
    # HELPER: GET VALUES
    # -----------------------------------------------------
    def _get_series(self, key, window=20):
        return [h.get(key, 0) for h in list(self.history)[-window:]]

    # -----------------------------------------------------
    # 🔥 1. GRADUAL DRIFT (VERY IMPORTANT)
    # -----------------------------------------------------
    def detect_drift(self):

        if len(self.history) < 10:
            return None

        cpu_vals = self._get_series("compute", 10)

        if cpu_vals[-1] > cpu_vals[0] + 15:
            return {
                "type": "increasing_load_drift",
                "severity": "medium",
                "message": "Gradual increase in compute load detected"
            }

        return None

    # -----------------------------------------------------
    # 🔥 2. OSCILLATION / INSTABILITY
    # -----------------------------------------------------
    def detect_oscillation(self):

        if len(self.history) < 15:
            return None

        vals = self._get_series("compute", 15)

        changes = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]

        spikes = sum(1 for c in changes if c > 20)

        if spikes > 5:
            return {
                "type": "system_instability",
                "severity": "high",
                "message": "Frequent oscillations detected"
            }

        return None

    # -----------------------------------------------------
    # 🔥 3. SUSTAINED STRESS
    # -----------------------------------------------------
    def detect_sustained_load(self):

        if len(self.history) < 10:
            return None

        vals = self._get_series("compute", 10)

        if all(v > 70 for v in vals[-5:]):
            return {
                "type": "sustained_high_load",
                "severity": "high",
                "message": "System under sustained load"
            }

        return None

    # -----------------------------------------------------
    # 🔥 4. THERMAL PATTERN (INDUSTRIAL USE)
    # -----------------------------------------------------
    def detect_thermal_pattern(self):

        if len(self.history) < 10:
            return None

        temps = self._get_series("thermal", 10)

        if all(t > 75 for t in temps[-5:]):
            return {
                "type": "thermal_overload_pattern",
                "severity": "critical",
                "message": "Sustained high temperature detected"
            }

        return None

    # -----------------------------------------------------
    # 🔥 5. VIBRATION FAULT PATTERN (MECHANICAL SYSTEMS)
    # -----------------------------------------------------
    def detect_vibration_pattern(self):

        if len(self.history) < 15:
            return None

        vib = self._get_series("vibration_intensity", 15)

        if mean(vib) > 0.7 and stdev(vib) > 0.3:
            return {
                "type": "mechanical_instability",
                "severity": "high",
                "message": "Abnormal vibration patterns detected"
            }

        return None

    # -----------------------------------------------------
    # 🔥 6. RECURRING ANOMALY
    # -----------------------------------------------------
    def detect_recurring_anomaly(self):

        if len(self.history) < 20:
            return None

        cpu_vals = self._get_series("compute", 20)

        spikes = sum(1 for v in cpu_vals if v > 85)

        if spikes > 6:
            return {
                "type": "recurring_spikes",
                "severity": "medium",
                "message": "Repeated high-load spikes observed"
            }

        return None

    # -----------------------------------------------------
    # 🔥 7. PATTERN AGGREGATOR
    # -----------------------------------------------------
    def detect_patterns(self):

        detectors = [
            self.detect_drift,
            self.detect_oscillation,
            self.detect_sustained_load,
            self.detect_thermal_pattern,
            self.detect_vibration_pattern,
            self.detect_recurring_anomaly
        ]

        patterns = []

        for detector in detectors:
            result = detector()
            if result:
                patterns.append(result)

        return patterns

    # -----------------------------------------------------
    # 🔥 8. MEMORY (LEARNING OVER TIME)
    # -----------------------------------------------------
    def update_memory(self, patterns):

        for p in patterns:
            self.pattern_memory.append({
                "time": datetime.utcnow().isoformat(),
                "pattern": p["type"],
                "severity": p["severity"]
            })

        # keep last 100
        self.pattern_memory = self.pattern_memory[-100:]

    # -----------------------------------------------------
    # 🔥 9. FULL PIPELINE
    # -----------------------------------------------------
    def analyze(self, features):

        self.update(features)

        patterns = self.detect_patterns()

        self.update_memory(patterns)

        return {
            "patterns": patterns,
            "pattern_memory": self.pattern_memory[-10:]
        }
