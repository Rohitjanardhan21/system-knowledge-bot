# backend/vehicle_system/confidence_engine.py

import numpy as np

class ConfidenceEngine:

    def compute(self, history):
        if len(history) < 5:
            return 0.5

        values = [h.get("thermal", 0) for h in history]

        variance = np.var(values)

        confidence = max(0.3, min(1.0, 1 - variance))

        return round(confidence, 2)


confidence_engine = ConfidenceEngine()
