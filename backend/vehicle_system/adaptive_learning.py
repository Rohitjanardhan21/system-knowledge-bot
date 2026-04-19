# backend/vehicle_system/adaptive_learning.py

class AdaptiveLearning:

    def __init__(self):
        self.thresholds = {
            "thermal": 0.8,
            "vibration": 0.7
        }

    def update(self, signals, anomaly_score):
        # Adjust thresholds slowly based on environment
        if anomaly_score < 0.5:
            self.thresholds["thermal"] = min(1.0, self.thresholds["thermal"] + 0.001)
            self.thresholds["vibration"] = min(1.0, self.thresholds["vibration"] + 0.001)
        else:
            self.thresholds["thermal"] = max(0.6, self.thresholds["thermal"] - 0.002)
            self.thresholds["vibration"] = max(0.5, self.thresholds["vibration"] - 0.002)

    def get_thresholds(self):
        return self.thresholds


adaptive_learning = AdaptiveLearning()
