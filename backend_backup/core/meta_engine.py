class MetaEngine:

    def evaluate(self, confidence, anomaly_score):
        if confidence > 0.8:
            reliability = "HIGH"
        elif confidence > 0.5:
            reliability = "MEDIUM"
        else:
            reliability = "LOW"

        return {
            "confidence": confidence,
            "uncertainty": round(1 - confidence, 2),
            "reliability": reliability,
            "anomaly_level": anomaly_score
        }


meta_engine = MetaEngine()
