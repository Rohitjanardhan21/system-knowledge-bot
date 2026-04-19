# backend/vehicle_system/learning_engine.py

import numpy as np

class LearningEngine:

    def analyze_trip(self, trip_data):
        temps = []
        vibrations = []
        anomalies = []

        for entry in trip_data:
            d = entry["data"]

            temps.append(d.get("features", {}).get("thermal", 0))
            vibrations.append(d.get("features", {}).get("vibration_intensity", 0))
            anomalies.append(d.get("anomaly_score", 0))

        return {
            "avg_temp": float(np.mean(temps)),
            "avg_vibration": float(np.mean(vibrations)),
            "max_anomaly": float(np.max(anomalies)),
            "risk_profile": self._risk_profile(anomalies)
        }

    def _risk_profile(self, anomalies):
        if max(anomalies) > 2:
            return "HIGH"
        elif max(anomalies) > 1:
            return "MEDIUM"
        return "LOW"


learning_engine = LearningEngine()
